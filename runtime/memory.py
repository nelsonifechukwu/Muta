"""Persistent conversation memory over Postgres.

Tables: `conversations` (one per chat thread), `messages` (the turns), `attachments`
(images/audio bound to a conversation/message), `user_settings` (one JSONB blob per
student). Multi-turn context is reconstructed by replaying a conversation's messages back
to the model. The DB lives in the compose `db` service; the DSN comes from
`MUTA_RT_DB_URL`.

Porting invariants kept from the SQLite original:
- message ordering is by the serial `id`, never `created_at`;
- `get_messages(limit=N)` returns the most recent N in chronological order;
- timestamps are ISO-8601 UTC strings (they sort lexicographically = chronologically),
  so row dicts keep the exact shapes callers already consume.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    student_id  TEXT NOT NULL,
    mode        TEXT,
    persona     TEXT,
    subject     TEXT,
    language    TEXT,
    title       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id              BIGSERIAL PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, id);
CREATE INDEX IF NOT EXISTS idx_conversations_student
    ON conversations(student_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS attachments (
    id              BIGSERIAL PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
    message_id      BIGINT REFERENCES messages(id) ON DELETE SET NULL,
    kind            TEXT NOT NULL CHECK (kind IN ('image', 'audio')),
    mime            TEXT NOT NULL,
    data            BYTEA NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attachments_conversation ON attachments(conversation_id, id);
CREATE TABLE IF NOT EXISTS user_settings (
    student_id  TEXT PRIMARY KEY,
    settings    JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at  TEXT NOT NULL
);
"""

# Postgres restarts once during first-boot init; a fixed DSN that is *about* to be ready is
# the normal case under compose, so construction waits rather than failing fast.
_OPEN_TIMEOUT_S = 30.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConversationStore:
    """Postgres-backed store. Concurrency comes from the connection pool: every method
    checks a connection out for just its own statement(s), so FastAPI threadpool handlers
    never contend on a shared lock."""

    def __init__(self, dsn: str = "postgresql://muta:muta@127.0.0.1:15432/muta") -> None:
        self.dsn = str(dsn)
        self._pool = ConnectionPool(
            self.dsn,
            min_size=1,
            max_size=8,
            kwargs={"row_factory": dict_row},
            open=False,
        )
        try:
            self._pool.open(wait=True, timeout=_OPEN_TIMEOUT_S)
            with self._pool.connection() as conn:
                conn.execute(_SCHEMA)
        except Exception:
            # A half-constructed store has no owner to close it — every retry against a
            # down db would otherwise leak a pool and its reconnect worker thread.
            self._pool.close()
            raise

    def ping(self) -> bool:
        try:
            with self._pool.connection(timeout=2.0) as conn:
                conn.execute("SELECT 1")
            return True
        except Exception:  # noqa: BLE001 — any failure means "db not reachable"
            return False

    # --- conversations ----------------------------------------------------------------

    def create_conversation(
        self,
        student_id: str,
        *,
        mode: str | None = None,
        persona: str | None = None,
        subject: str | None = None,
        language: str | None = None,
        title: str | None = None,
    ) -> str:
        cid = uuid.uuid4().hex
        ts = _now()
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO conversations "
                "(id, student_id, mode, persona, subject, language, title, created_at, updated_at)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (cid, student_id, mode, persona, subject, language, title, ts, ts),
            )
        return cid

    def get_conversation(self, conversation_id: str) -> dict | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = %s", (conversation_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_conversations(self, student_id: str) -> list[dict]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM conversations WHERE student_id = %s ORDER BY updated_at DESC",
                (student_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_conversation(self, conversation_id: str) -> None:
        with self._pool.connection() as conn:
            conn.execute("DELETE FROM conversations WHERE id = %s", (conversation_id,))

    def set_title(self, conversation_id: str, title: str) -> None:
        """First write wins — the title is the opening message, not the latest one."""
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE conversations SET title = %s WHERE id = %s AND title IS NULL",
                (title, conversation_id),
            )

    # --- messages ---------------------------------------------------------------------

    def add_message(self, conversation_id: str, role: str, content: str) -> int:
        ts = _now()
        with self._pool.connection() as conn, conn.transaction():
            row = conn.execute(
                "INSERT INTO messages (conversation_id, role, content, created_at) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (conversation_id, role, content, ts),
            ).fetchone()
            conn.execute(
                "UPDATE conversations SET updated_at = %s WHERE id = %s",
                (ts, conversation_id),
            )
        return int(row["id"])

    def get_messages(self, conversation_id: str, limit: int | None = None) -> list[dict]:
        """Messages in chronological order. With ``limit``, the most recent ``limit``."""
        with self._pool.connection() as conn:
            if limit is None:
                rows = conn.execute(
                    "SELECT role, content, created_at FROM messages "
                    "WHERE conversation_id = %s ORDER BY id ASC",
                    (conversation_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT role, content, created_at FROM messages "
                    "WHERE conversation_id = %s ORDER BY id DESC LIMIT %s",
                    (conversation_id, limit),
                ).fetchall()
                rows = list(reversed(rows))
        return [dict(r) for r in rows]

    def list_messages(self, conversation_id: str) -> list[dict]:
        """Full history for a UI: message ids plus linked attachment refs (no blob bytes)."""
        with self._pool.connection() as conn:
            msgs = conn.execute(
                "SELECT id, role, content, created_at FROM messages "
                "WHERE conversation_id = %s ORDER BY id ASC",
                (conversation_id,),
            ).fetchall()
            refs = conn.execute(
                "SELECT id, message_id, kind, mime FROM attachments "
                "WHERE conversation_id = %s AND message_id IS NOT NULL ORDER BY id ASC",
                (conversation_id,),
            ).fetchall()
        by_message: dict[int, list[dict]] = {}
        for r in refs:
            by_message.setdefault(r["message_id"], []).append(
                {"id": r["id"], "kind": r["kind"], "mime": r["mime"]}
            )
        out = []
        for m in msgs:
            d = dict(m)
            d["attachments"] = by_message.get(m["id"], [])
            out.append(d)
        return out

    # --- attachments ------------------------------------------------------------------

    def add_attachment(
        self,
        kind: str,
        mime: str,
        data: bytes,
        *,
        conversation_id: str | None = None,
        message_id: int | None = None,
    ) -> int:
        with self._pool.connection() as conn:
            row = conn.execute(
                "INSERT INTO attachments (conversation_id, message_id, kind, mime, data, "
                "created_at) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (conversation_id, message_id, kind, mime, data, _now()),
            ).fetchone()
        return int(row["id"])

    def get_attachment(self, attachment_id: int) -> dict | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT id, conversation_id, message_id, kind, mime, data, created_at "
                "FROM attachments WHERE id = %s",
                (attachment_id,),
            ).fetchone()
        return dict(row) if row else None

    def link_attachment(
        self, attachment_id: int, conversation_id: str, message_id: int | None = None
    ) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE attachments SET conversation_id = %s, message_id = %s WHERE id = %s",
                (conversation_id, message_id, attachment_id),
            )

    # --- user settings ----------------------------------------------------------------

    def get_settings(self, student_id: str) -> dict:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT settings FROM user_settings WHERE student_id = %s", (student_id,)
            ).fetchone()
        return dict(row["settings"]) if row else {}

    def put_settings(self, student_id: str, settings: dict) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO user_settings (student_id, settings, updated_at) "
                "VALUES (%s, %s, %s) "
                "ON CONFLICT (student_id) DO UPDATE "
                "SET settings = EXCLUDED.settings, updated_at = EXCLUDED.updated_at",
                (student_id, Jsonb(settings), _now()),
            )

    def close(self) -> None:
        self._pool.close()
