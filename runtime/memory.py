"""Persistent conversation memory, with Postgres control and portable SQLite backends.

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
from datetime import datetime, timedelta, timezone

# --- Schema migrations ------------------------------------------------------------------
# Ordered, append-only. Each runs once; the version is recorded in `schema_migrations`. A
# deployed muta-pgdata volume upgrades by running only the versions it has not seen, so a new
# column reaches an existing fleet instead of being silently skipped by CREATE IF NOT EXISTS.
# Migrations must be idempotent (IF NOT EXISTS / ADD COLUMN IF NOT EXISTS) so re-applying the
# base schema over a pre-migration database is safe. NEVER edit a shipped migration — add a
# new one.

_MIGRATION_1_BASE = """
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

# Ownership on attachments: without an owner column the GET-by-id endpoint cannot tell whose
# photo/recording an id belongs to (the enumerable-IDOR fix). `owner_id` is set at upload; an
# attachment is accessible to its owner, or to the owner of the conversation it is linked to.
_MIGRATION_2_ATTACHMENT_OWNER = """
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS owner_id TEXT;
CREATE INDEX IF NOT EXISTS idx_attachments_owner ON attachments(owner_id, created_at);
"""

_MIGRATION_3_LEARNING_RESOURCES = """
CREATE TABLE IF NOT EXISTS learning_resources (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    name TEXT NOT NULL,
    mime TEXT NOT NULL CHECK (mime = 'application/pdf'),
    data BYTEA NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('processing', 'ready', 'failed')),
    page_count INT,
    embedder_identity TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_learning_resources_owner
    ON learning_resources(owner_id, created_at DESC);
CREATE TABLE IF NOT EXISTS resource_chunks (
    id BIGSERIAL PRIMARY KEY,
    resource_id TEXT NOT NULL REFERENCES learning_resources(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    page_number INT NOT NULL,
    text TEXT NOT NULL,
    embedding JSONB NOT NULL,
    UNIQUE(resource_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_resource_chunks_resource
    ON resource_chunks(resource_id, chunk_index);
CREATE TABLE IF NOT EXISTS message_sources (
    id BIGSERIAL PRIMARY KEY,
    message_id BIGINT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    resource_id TEXT NOT NULL REFERENCES learning_resources(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    page_number INT NOT NULL,
    chunk_index INT NOT NULL,
    excerpt TEXT NOT NULL,
    UNIQUE(message_id, resource_id, page_number, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_message_sources_message ON message_sources(message_id, id);
"""

_MIGRATION_4_PINNED_CONVERSATIONS = """
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS pinned BOOLEAN NOT NULL DEFAULT FALSE;
"""

_MIGRATIONS: list[tuple[int, str]] = [
    (1, _MIGRATION_1_BASE),
    (2, _MIGRATION_2_ATTACHMENT_OWNER),
    (3, _MIGRATION_3_LEARNING_RESOURCES),
    (4, _MIGRATION_4_PINNED_CONVERSATIONS),
]


def _apply_migrations(conn) -> None:
    """Run every migration the database has not recorded yet, each in its own transaction."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(version INT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    applied = {
        r["version"] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()
    }
    for version, sql in _MIGRATIONS:
        if version in applied:
            continue
        with conn.transaction():
            conn.execute(sql)
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (%s, %s)",
                (version, _now()),
            )


# Postgres restarts once during first-boot init; a fixed DSN that is *about* to be ready is
# the normal case under compose, so construction waits rather than failing fast.
_OPEN_TIMEOUT_S = 30.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConversationStore:
    """Store selector plus the Postgres implementation used by the Compose control.

    A ``sqlite:///`` DSN returns the API-compatible portable implementation. PostgreSQL
    concurrency comes from the connection pool: every method checks out a connection only for
    its own statement(s), so FastAPI threadpool handlers never share one connection.
    """

    def __new__(cls, dsn: str = "sqlite:///data/muta.sqlite3"):
        if cls is ConversationStore and str(dsn).startswith("sqlite:///"):
            from runtime.sqlite_memory import SQLiteConversationStore

            return SQLiteConversationStore(str(dsn))
        return super().__new__(cls)

    def __init__(self, dsn: str = "sqlite:///data/muta.sqlite3") -> None:
        # Desktop builds are SQLite-only and deliberately omit libpq. Keep the server-only
        # native dependency outside module import so freezing the portable product does not
        # drag Postgres client libraries into every platform package.
        from psycopg.rows import dict_row
        from psycopg.types.json import Jsonb
        from psycopg_pool import ConnectionPool

        self.dsn = str(dsn)
        self._jsonb = Jsonb
        self._pool = ConnectionPool(
            self.dsn,
            min_size=1,
            max_size=8,
            kwargs={"row_factory": dict_row},
            # Validate a connection on checkout (one round trip): after a Postgres restart the
            # pool otherwise hands out stale connections that fail on first use, surfacing as a
            # 500 to the student. `check` discards and replaces them transparently.
            check=ConnectionPool.check_connection,
            open=False,
        )
        try:
            self._pool.open(wait=True, timeout=_OPEN_TIMEOUT_S)
            with self._pool.connection() as conn:
                _apply_migrations(conn)
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
                "SELECT * FROM conversations WHERE student_id = %s "
                "ORDER BY pinned DESC, updated_at DESC",
                (student_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_conversation(self, conversation_id: str, *, owner_id: str | None = None) -> bool:
        """Delete a conversation (messages/attachments cascade). Returns True when a row was
        actually removed. With ``owner_id`` the delete only touches a conversation that student
        owns, so the caller can 404 rather than silently reporting success for someone else's
        (or a nonexistent) thread."""
        with self._pool.connection() as conn:
            if owner_id is None:
                cur = conn.execute("DELETE FROM conversations WHERE id = %s", (conversation_id,))
            else:
                cur = conn.execute(
                    "DELETE FROM conversations WHERE id = %s AND student_id = %s",
                    (conversation_id, owner_id),
                )
            return cur.rowcount > 0

    def set_conversation_pinned(
        self, conversation_id: str, *, owner_id: str, pinned: bool
    ) -> bool:
        with self._pool.connection() as conn:
            cur = conn.execute(
                "UPDATE conversations SET pinned = %s WHERE id = %s AND student_id = %s",
                (pinned, conversation_id, owner_id),
            )
            return cur.rowcount > 0

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

    def add_user_message_with_attachments(
        self,
        conversation_id: str,
        content: str,
        attachment_ids: list[int],
        *,
        owner_id: str,
    ) -> int:
        """Atomically persist a user turn and bind its already-validated attachments."""
        ts = _now()
        unique_ids = list(dict.fromkeys(attachment_ids))
        with self._pool.connection() as conn, conn.transaction():
            owner = conn.execute(
                "SELECT 1 FROM conversations WHERE id = %s AND student_id = %s",
                (conversation_id, owner_id),
            ).fetchone()
            if owner is None:
                raise PermissionError("conversation belongs to another learner")
            row = conn.execute(
                "INSERT INTO messages (conversation_id, role, content, created_at) "
                "VALUES (%s, 'user', %s, %s) RETURNING id",
                (conversation_id, content, ts),
            ).fetchone()
            message_id = int(row["id"])
            for attachment_id in unique_ids:
                linked = conn.execute(
                    "UPDATE attachments SET conversation_id = %s, message_id = %s "
                    "WHERE id = %s AND owner_id = %s AND message_id IS NULL "
                    "AND (conversation_id IS NULL OR conversation_id = %s)",
                    (
                        conversation_id,
                        message_id,
                        attachment_id,
                        owner_id,
                        conversation_id,
                    ),
                )
                if linked.rowcount != 1:
                    raise RuntimeError("attachment link failed")
            conn.execute(
                "UPDATE conversations SET updated_at = %s WHERE id = %s",
                (ts, conversation_id),
            )
        return message_id

    def update_message(self, message_id: int, content: str) -> None:
        """Rewrite a message's body in place, keeping its id (and therefore its position in
        the conversation's serial ordering).

        This exists for streaming: a reply is written to its row as it arrives, so what
        survives a disconnect no longer depends on a generator being finalized. Ordering is
        by serial id, so growing the row in place cannot reshuffle history.
        """
        ts = _now()
        with self._pool.connection() as conn, conn.transaction():
            row = conn.execute(
                "UPDATE messages SET content = %s WHERE id = %s RETURNING conversation_id",
                (content, message_id),
            ).fetchone()
            if row is not None:
                conn.execute(
                    "UPDATE conversations SET updated_at = %s WHERE id = %s",
                    (ts, row["conversation_id"]),
                )

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

    def get_first_user_message(self, conversation_id: str) -> dict | None:
        """Return one opening user row without materializing the conversation transcript."""
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT role, content, created_at FROM messages "
                "WHERE conversation_id = %s AND role = 'user' ORDER BY id ASC LIMIT 1",
                (conversation_id,),
            ).fetchone()
        return dict(row) if row else None

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
            sources = conn.execute(
                "SELECT ms.message_id, ms.resource_id, ms.title, ms.page_number, "
                "ms.chunk_index, ms.excerpt FROM message_sources ms "
                "JOIN messages m ON m.id = ms.message_id "
                "WHERE m.conversation_id = %s ORDER BY ms.id ASC",
                (conversation_id,),
            ).fetchall()
        by_message: dict[int, list[dict]] = {}
        for r in refs:
            by_message.setdefault(r["message_id"], []).append(
                {"id": r["id"], "kind": r["kind"], "mime": r["mime"]}
            )
        by_source_message: dict[int, list[dict]] = {}
        for row in sources:
            by_source_message.setdefault(row["message_id"], []).append(
                {
                    "resource_id": row["resource_id"],
                    "title": row["title"],
                    "page": row["page_number"],
                    "chunk_index": row["chunk_index"],
                    "excerpt": row["excerpt"],
                }
            )
        out = []
        for m in msgs:
            d = dict(m)
            d["attachments"] = by_message.get(m["id"], [])
            d["resource_citations"] = by_source_message.get(m["id"], [])
            out.append(d)
        return out

    def last_message_id(self, conversation_id: str, role: str | None = None) -> int | None:
        with self._pool.connection() as conn:
            if role is None:
                row = conn.execute(
                    "SELECT id FROM messages WHERE conversation_id = %s ORDER BY id DESC LIMIT 1",
                    (conversation_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT id FROM messages WHERE conversation_id = %s AND role = %s "
                    "ORDER BY id DESC LIMIT 1",
                    (conversation_id, role),
                ).fetchone()
        return int(row["id"]) if row else None

    def first_message_id_after(
        self, conversation_id: str, role: str, after_id: int | None
    ) -> int | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT id FROM messages WHERE conversation_id = %s AND role = %s AND id > %s "
                "ORDER BY id ASC LIMIT 1",
                (conversation_id, role, int(after_id or 0)),
            ).fetchone()
        return int(row["id"]) if row else None

    def add_message_sources(self, message_id: int, sources: list[dict]) -> list[dict]:
        persisted: list[dict] = []
        with self._pool.connection() as conn, conn.transaction():
            for source in sources:
                cursor = conn.execute(
                    "INSERT INTO message_sources "
                    "(message_id, resource_id, title, page_number, chunk_index, excerpt) "
                    "SELECT %s, r.id, %s, %s, %s, %s FROM learning_resources r "
                    "WHERE r.id = %s ON CONFLICT DO NOTHING",
                    (
                        message_id,
                        source["title"],
                        source["page"],
                        source["chunk_index"],
                        source["excerpt"],
                        source["resource_id"],
                    ),
                )
                if cursor.rowcount:
                    persisted.append(dict(source))
        return persisted

    def get_message_sources(self, message_id: int) -> list[dict]:
        """Return the source rows that still exist for one persisted assistant message."""
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT resource_id, title, page_number, chunk_index, excerpt "
                "FROM message_sources WHERE message_id = %s ORDER BY id ASC",
                (message_id,),
            ).fetchall()
        return [
            {
                "resource_id": row["resource_id"],
                "title": row["title"],
                "page": row["page_number"],
                "chunk_index": row["chunk_index"],
                "excerpt": row["excerpt"],
            }
            for row in rows
        ]

    # --- learner resources -----------------------------------------------------------

    def create_resource(self, owner_id: str, name: str, mime: str, data: bytes) -> str:
        resource_id = uuid.uuid4().hex
        ts = _now()
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO learning_resources "
                "(id, owner_id, name, mime, data, status, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, 'processing', %s, %s)",
                (resource_id, owner_id, name, mime, data, ts, ts),
            )
        return resource_id

    def list_resources(self, owner_id: str) -> list[dict]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT id, name, mime, status, page_count, error, created_at, updated_at "
                "FROM learning_resources WHERE owner_id = %s ORDER BY created_at DESC",
                (owner_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_resource(
        self, resource_id: str, *, owner_id: str, include_data: bool = False
    ) -> dict | None:
        columns = (
            "*"
            if include_data
            else (
                "id, owner_id, name, mime, status, page_count, embedder_identity, error, "
                "created_at, updated_at"
            )
        )
        with self._pool.connection() as conn:
            row = conn.execute(
                f"SELECT {columns} FROM learning_resources WHERE id = %s AND owner_id = %s",
                (resource_id, owner_id),
            ).fetchone()
        return dict(row) if row else None

    def list_processing_resources(self) -> list[dict]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT id, owner_id FROM learning_resources WHERE status = 'processing' "
                "ORDER BY created_at ASC"
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_resource_processing(self, resource_id: str, *, owner_id: str) -> bool:
        with self._pool.connection() as conn:
            cur = conn.execute(
                "UPDATE learning_resources SET status = 'processing', error = NULL, "
                "updated_at = %s WHERE id = %s AND owner_id = %s",
                (_now(), resource_id, owner_id),
            )
        return cur.rowcount > 0

    def mark_resource_failed(self, resource_id: str, *, owner_id: str, error: str) -> bool:
        with self._pool.connection() as conn:
            cur = conn.execute(
                "UPDATE learning_resources SET status = 'failed', error = %s, updated_at = %s "
                "WHERE id = %s AND owner_id = %s",
                (error[:500], _now(), resource_id, owner_id),
            )
        return cur.rowcount > 0

    def replace_resource_chunks(
        self,
        resource_id: str,
        *,
        owner_id: str,
        chunks: list[dict],
        page_count: int,
        embedder_identity: str,
    ) -> bool:
        with self._pool.connection() as conn, conn.transaction():
            owned = conn.execute(
                "SELECT 1 FROM learning_resources WHERE id = %s AND owner_id = %s FOR UPDATE",
                (resource_id, owner_id),
            ).fetchone()
            if owned is None:
                return False
            conn.execute("DELETE FROM resource_chunks WHERE resource_id = %s", (resource_id,))
            for chunk in chunks:
                conn.execute(
                    "INSERT INTO resource_chunks "
                    "(resource_id, chunk_index, page_number, text, embedding) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (
                        resource_id,
                        chunk["chunk_index"],
                        chunk["page"],
                        chunk["text"],
                        self._jsonb(chunk["embedding"]),
                    ),
                )
            conn.execute(
                "UPDATE learning_resources SET status = 'ready', page_count = %s, "
                "embedder_identity = %s, error = NULL, updated_at = %s "
                "WHERE id = %s AND owner_id = %s",
                (page_count, embedder_identity, _now(), resource_id, owner_id),
            )
        return True

    def get_resource_chunks(self, resource_ids: list[str], *, owner_id: str) -> list[dict]:
        if not resource_ids:
            return []
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT c.resource_id, r.name AS title, c.chunk_index, c.page_number, "
                "c.text, c.embedding FROM resource_chunks c "
                "JOIN learning_resources r ON r.id = c.resource_id "
                "WHERE r.owner_id = %s AND r.status = 'ready' "
                "AND c.resource_id = ANY(%s) ORDER BY c.resource_id, c.chunk_index",
                (owner_id, resource_ids),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_resource(self, resource_id: str, *, owner_id: str) -> bool:
        with self._pool.connection() as conn:
            cur = conn.execute(
                "DELETE FROM learning_resources WHERE id = %s AND owner_id = %s",
                (resource_id, owner_id),
            )
        return cur.rowcount > 0

    # --- attachments ------------------------------------------------------------------

    def add_attachment(
        self,
        kind: str,
        mime: str,
        data: bytes,
        *,
        conversation_id: str | None = None,
        message_id: int | None = None,
        owner_id: str | None = None,
    ) -> int:
        with self._pool.connection() as conn:
            row = conn.execute(
                "INSERT INTO attachments (conversation_id, message_id, kind, mime, data, "
                "owner_id, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (conversation_id, message_id, kind, mime, data, owner_id, _now()),
            ).fetchone()
        return int(row["id"])

    def get_attachment(self, attachment_id: int, *, owner_id: str | None = None) -> dict | None:
        """Fetch an attachment's bytes. With ``owner_id`` the row is returned only when that
        student owns it directly (uploaded it) or owns the conversation it is linked to —
        otherwise None, so the endpoint 404s instead of leaking another student's file."""
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT a.id, a.conversation_id, a.message_id, a.kind, a.mime, a.data, "
                "a.owner_id, a.created_at, c.student_id AS conversation_owner "
                "FROM attachments a LEFT JOIN conversations c ON c.id = a.conversation_id "
                "WHERE a.id = %s",
                (attachment_id,),
            ).fetchone()
        if row is None:
            return None
        if owner_id is not None and owner_id not in (
            row.get("owner_id"),
            row.get("conversation_owner"),
        ):
            return None
        return dict(row)

    def link_attachment(
        self,
        attachment_id: int,
        conversation_id: str,
        message_id: int | None = None,
        *,
        owner_id: str | None = None,
    ) -> None:
        with self._pool.connection() as conn:
            if owner_id is None:
                conn.execute(
                    "UPDATE attachments SET conversation_id = %s, message_id = %s WHERE id = %s",
                    (conversation_id, message_id, attachment_id),
                )
            else:
                conn.execute(
                    "UPDATE attachments SET conversation_id = %s, message_id = %s "
                    "WHERE id = %s AND owner_id = %s AND EXISTS ("
                    "SELECT 1 FROM conversations WHERE id = %s AND student_id = %s)",
                    (
                        conversation_id,
                        message_id,
                        attachment_id,
                        owner_id,
                        conversation_id,
                        owner_id,
                    ),
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
                (student_id, self._jsonb(settings), _now()),
            )

    def patch_settings(self, student_id: str, changes: dict) -> dict:
        """Atomically merge independent preference controls and return the stored object."""
        with self._pool.connection() as conn:
            row = conn.execute(
                "INSERT INTO user_settings (student_id, settings, updated_at) "
                "VALUES (%s, %s, %s) "
                "ON CONFLICT (student_id) DO UPDATE SET "
                "settings = user_settings.settings || EXCLUDED.settings, "
                "updated_at = EXCLUDED.updated_at RETURNING settings",
                (student_id, self._jsonb(changes), _now()),
            ).fetchone()
        return dict(row["settings"])

    # --- retention & erasure ----------------------------------------------------------

    def delete_student(self, student_id: str) -> dict[str, int]:
        """Erase everything owned by one student: their conversations (messages + linked
        attachments cascade), any attachments they uploaded (including a historical bad
        cross-link), and their settings. Returns per-table deleted counts. This is the
        primitive a parent/guardian-facing 'delete my child's data' request is built on."""
        with self._pool.connection() as conn, conn.transaction():
            owned_attachments = conn.execute(
                "DELETE FROM attachments WHERE owner_id = %s",
                (student_id,),
            ).rowcount
            convos = conn.execute(
                "DELETE FROM conversations WHERE student_id = %s", (student_id,)
            ).rowcount
            resources = conn.execute(
                "DELETE FROM learning_resources WHERE owner_id = %s", (student_id,)
            ).rowcount
            settings = conn.execute(
                "DELETE FROM user_settings WHERE student_id = %s", (student_id,)
            ).rowcount
        return {
            "conversations": convos,
            # Retain the frozen response-field name; the count is now the safer superset.
            "orphan_attachments": owned_attachments,
            "resources": resources,
            "settings": settings,
        }

    def reap_orphan_attachments(self, older_than_seconds: float) -> int:
        """Delete never-linked attachments (conversation_id IS NULL) older than the cutoff —
        photos/recordings whose chat was never sent. ISO-8601 UTC timestamps sort
        lexicographically, so a string comparison is a chronological one. Returns the count."""
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=older_than_seconds)).isoformat()
        with self._pool.connection() as conn:
            return conn.execute(
                "DELETE FROM attachments WHERE conversation_id IS NULL AND created_at < %s",
                (cutoff,),
            ).rowcount

    def delete_settings(self, student_id: str) -> None:
        with self._pool.connection() as conn:
            conn.execute("DELETE FROM user_settings WHERE student_id = %s", (student_id,))

    def close(self) -> None:
        self._pool.close()
