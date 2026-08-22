"""Portable SQLite implementation of Muta's conversation-store contract.

The Compose control uses Postgres.  A native/offline bundle cannot require a database daemon,
so ``sqlite:`` DSNs select this implementation instead.  It intentionally mirrors every
method and row shape of :class:`runtime.memory.ConversationStore`.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, id);
CREATE INDEX IF NOT EXISTS idx_conversations_student
    ON conversations(student_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS attachments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
    message_id      INTEGER REFERENCES messages(id) ON DELETE SET NULL,
    kind            TEXT NOT NULL CHECK (kind IN ('image', 'audio')),
    mime            TEXT NOT NULL,
    data            BLOB NOT NULL,
    owner_id        TEXT,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attachments_conversation ON attachments(conversation_id, id);
CREATE TABLE IF NOT EXISTS user_settings (
    student_id  TEXT PRIMARY KEY,
    settings    TEXT NOT NULL DEFAULT '{}',
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS learning_resources (
    id                  TEXT PRIMARY KEY,
    owner_id            TEXT NOT NULL,
    name                TEXT NOT NULL,
    mime                TEXT NOT NULL CHECK (mime = 'application/pdf'),
    data                BLOB NOT NULL,
    status              TEXT NOT NULL CHECK (status IN ('processing', 'ready', 'failed')),
    page_count          INTEGER,
    embedder_identity   TEXT,
    error               TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_learning_resources_owner
    ON learning_resources(owner_id, created_at DESC);
CREATE TABLE IF NOT EXISTS resource_chunks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id     TEXT NOT NULL REFERENCES learning_resources(id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    page_number     INTEGER NOT NULL,
    text            TEXT NOT NULL,
    embedding       TEXT NOT NULL,
    UNIQUE(resource_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_resource_chunks_resource
    ON resource_chunks(resource_id, chunk_index);
CREATE TABLE IF NOT EXISTS message_sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id      INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    resource_id     TEXT NOT NULL REFERENCES learning_resources(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    page_number     INTEGER NOT NULL,
    chunk_index     INTEGER NOT NULL,
    excerpt         TEXT NOT NULL,
    UNIQUE(message_id, resource_id, page_number, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_message_sources_message ON message_sources(message_id, id);
"""

_LATEST_SCHEMA_VERSION = 3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def path_from_dsn(dsn: str) -> str:
    """Translate Muta's deliberately small SQLite URL surface to a sqlite3 path.

    ``sqlite:///data/muta.sqlite3`` is repo-relative, ``sqlite:////tmp/muta.sqlite3`` is
    absolute, and ``sqlite:///:memory:`` is the standard in-memory test database.
    """
    if not dsn.startswith("sqlite:///"):
        raise ValueError(f"not a SQLite DSN: {dsn}")
    raw = dsn[len("sqlite:///") :]
    if raw == ":memory:":
        return raw
    return f"/{raw[1:]}" if raw.startswith("/") else raw


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Upgrade old portable databases in place; append a new numbered block per change."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations").fetchall()}
    if 1 not in applied:
        # Idempotent for the original pre-migration SQLite database: CREATE IF NOT EXISTS
        # preserves its conversation/message rows while adding the newer tables.
        conn.executescript(_SCHEMA)
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)", (1, _now())
        )
    if 2 not in applied:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(attachments)").fetchall()}
        if "owner_id" not in columns:
            conn.execute("ALTER TABLE attachments ADD COLUMN owner_id TEXT")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_attachments_owner ON attachments(owner_id, created_at)"
        )
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)", (2, _now())
        )
    if 3 not in applied:
        # The full schema is idempotent and keeps the portable and Postgres stores aligned.
        conn.executescript(_SCHEMA)
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)", (3, _now())
        )
    conn.commit()


class SQLiteConversationStore:
    """Thread-safe, daemon-free store for the portable two-process deployment."""

    def __init__(self, dsn: str = "sqlite:///data/muta.sqlite3") -> None:
        self.dsn = str(dsn)
        self.db_path = path_from_dsn(self.dsn)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.execute("PRAGMA busy_timeout=5000")
            _apply_migrations(self._conn)

    def ping(self) -> bool:
        try:
            with self._lock:
                self._conn.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

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
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO conversations "
                "(id, student_id, mode, persona, subject, language, title, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (cid, student_id, mode, persona, subject, language, title, ts, ts),
            )
        return cid

    def get_conversation(self, conversation_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_conversations(self, student_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM conversations WHERE student_id = ? ORDER BY updated_at DESC",
                (student_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_conversation(self, conversation_id: str, *, owner_id: str | None = None) -> bool:
        with self._lock, self._conn:
            if owner_id is None:
                cur = self._conn.execute(
                    "DELETE FROM conversations WHERE id = ?", (conversation_id,)
                )
            else:
                cur = self._conn.execute(
                    "DELETE FROM conversations WHERE id = ? AND student_id = ?",
                    (conversation_id, owner_id),
                )
        return cur.rowcount > 0

    def set_title(self, conversation_id: str, title: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE conversations SET title = ? WHERE id = ? AND title IS NULL",
                (title, conversation_id),
            )

    def add_message(self, conversation_id: str, role: str, content: str) -> int:
        ts = _now()
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO messages (conversation_id, role, content, created_at) "
                "VALUES (?, ?, ?, ?)",
                (conversation_id, role, content, ts),
            )
            self._conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (ts, conversation_id)
            )
        return int(cur.lastrowid)

    def update_message(self, message_id: int, content: str) -> None:
        ts = _now()
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT conversation_id FROM messages WHERE id = ?", (message_id,)
            ).fetchone()
            if row is None:
                return
            self._conn.execute(
                "UPDATE messages SET content = ? WHERE id = ?", (content, message_id)
            )
            self._conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (ts, row["conversation_id"]),
            )

    def get_messages(self, conversation_id: str, limit: int | None = None) -> list[dict]:
        with self._lock:
            if limit is None:
                rows = self._conn.execute(
                    "SELECT role, content, created_at FROM messages "
                    "WHERE conversation_id = ? ORDER BY id ASC",
                    (conversation_id,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT role, content, created_at FROM messages "
                    "WHERE conversation_id = ? ORDER BY id DESC LIMIT ?",
                    (conversation_id, limit),
                ).fetchall()
                rows = list(reversed(rows))
        return [dict(row) for row in rows]

    def list_messages(self, conversation_id: str) -> list[dict]:
        with self._lock:
            messages = self._conn.execute(
                "SELECT id, role, content, created_at FROM messages "
                "WHERE conversation_id = ? ORDER BY id ASC",
                (conversation_id,),
            ).fetchall()
            refs = self._conn.execute(
                "SELECT id, message_id, kind, mime FROM attachments "
                "WHERE conversation_id = ? AND message_id IS NOT NULL ORDER BY id ASC",
                (conversation_id,),
            ).fetchall()
            sources = self._conn.execute(
                "SELECT ms.message_id, ms.resource_id, ms.title, ms.page_number, "
                "ms.chunk_index, ms.excerpt FROM message_sources ms "
                "JOIN messages m ON m.id = ms.message_id "
                "WHERE m.conversation_id = ? ORDER BY ms.id ASC",
                (conversation_id,),
            ).fetchall()
        by_message: dict[int, list[dict]] = {}
        for row in refs:
            by_message.setdefault(row["message_id"], []).append(
                {"id": row["id"], "kind": row["kind"], "mime": row["mime"]}
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
        result = []
        for row in messages:
            message = dict(row)
            message["attachments"] = by_message.get(row["id"], [])
            message["resource_citations"] = by_source_message.get(row["id"], [])
            result.append(message)
        return result

    def last_message_id(self, conversation_id: str, role: str | None = None) -> int | None:
        with self._lock:
            if role is None:
                row = self._conn.execute(
                    "SELECT id FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT 1",
                    (conversation_id,),
                ).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT id FROM messages WHERE conversation_id = ? AND role = ? "
                    "ORDER BY id DESC LIMIT 1",
                    (conversation_id, role),
                ).fetchone()
        return int(row["id"]) if row else None

    def first_message_id_after(
        self, conversation_id: str, role: str, after_id: int | None
    ) -> int | None:
        floor = int(after_id or 0)
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM messages WHERE conversation_id = ? AND role = ? AND id > ? "
                "ORDER BY id ASC LIMIT 1",
                (conversation_id, role, floor),
            ).fetchone()
        return int(row["id"]) if row else None

    def add_message_sources(self, message_id: int, sources: list[dict]) -> None:
        with self._lock, self._conn:
            for source in sources:
                # The learner can delete a resource while its answer is streaming. Insert
                # from the live parent row so that race becomes a skipped citation rather
                # than a foreign-key error during generation cleanup.
                self._conn.execute(
                    "INSERT OR IGNORE INTO message_sources "
                    "(message_id, resource_id, title, page_number, chunk_index, excerpt) "
                    "SELECT ?, r.id, ?, ?, ?, ? FROM learning_resources r WHERE r.id = ?",
                    (
                        message_id,
                        source["title"],
                        source["page"],
                        source["chunk_index"],
                        source["excerpt"],
                        source["resource_id"],
                    ),
                )

    # --- learner resources -----------------------------------------------------------

    def create_resource(self, owner_id: str, name: str, mime: str, data: bytes) -> str:
        resource_id = uuid.uuid4().hex
        ts = _now()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO learning_resources "
                "(id, owner_id, name, mime, data, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 'processing', ?, ?)",
                (resource_id, owner_id, name, mime, data, ts, ts),
            )
        return resource_id

    def list_resources(self, owner_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, name, mime, status, page_count, error, created_at, updated_at "
                "FROM learning_resources WHERE owner_id = ? ORDER BY created_at DESC",
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
        with self._lock:
            row = self._conn.execute(
                f"SELECT {columns} FROM learning_resources WHERE id = ? AND owner_id = ?",
                (resource_id, owner_id),
            ).fetchone()
        return dict(row) if row else None

    def list_processing_resources(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, owner_id FROM learning_resources WHERE status = 'processing' "
                "ORDER BY created_at ASC"
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_resource_processing(self, resource_id: str, *, owner_id: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "UPDATE learning_resources SET status = 'processing', error = NULL, "
                "updated_at = ? WHERE id = ? AND owner_id = ?",
                (_now(), resource_id, owner_id),
            )
        return cur.rowcount > 0

    def mark_resource_failed(self, resource_id: str, *, owner_id: str, error: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "UPDATE learning_resources SET status = 'failed', error = ?, updated_at = ? "
                "WHERE id = ? AND owner_id = ?",
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
        with self._lock, self._conn:
            owned = self._conn.execute(
                "SELECT 1 FROM learning_resources WHERE id = ? AND owner_id = ?",
                (resource_id, owner_id),
            ).fetchone()
            if owned is None:
                return False
            self._conn.execute("DELETE FROM resource_chunks WHERE resource_id = ?", (resource_id,))
            self._conn.executemany(
                "INSERT INTO resource_chunks "
                "(resource_id, chunk_index, page_number, text, embedding) VALUES (?, ?, ?, ?, ?)",
                [
                    (
                        resource_id,
                        chunk["chunk_index"],
                        chunk["page"],
                        chunk["text"],
                        json.dumps(chunk["embedding"], separators=(",", ":")),
                    )
                    for chunk in chunks
                ],
            )
            self._conn.execute(
                "UPDATE learning_resources SET status = 'ready', page_count = ?, "
                "embedder_identity = ?, error = NULL, updated_at = ? "
                "WHERE id = ? AND owner_id = ?",
                (page_count, embedder_identity, _now(), resource_id, owner_id),
            )
        return True

    def get_resource_chunks(self, resource_ids: list[str], *, owner_id: str) -> list[dict]:
        if not resource_ids:
            return []
        marks = ",".join("?" for _ in resource_ids)
        with self._lock:
            rows = self._conn.execute(
                "SELECT c.resource_id, r.name AS title, c.chunk_index, c.page_number, "
                "c.text, c.embedding FROM resource_chunks c "
                "JOIN learning_resources r ON r.id = c.resource_id "
                f"WHERE r.owner_id = ? AND r.status = 'ready' AND c.resource_id IN ({marks}) "
                "ORDER BY c.resource_id, c.chunk_index",
                (owner_id, *resource_ids),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["embedding"] = json.loads(item["embedding"])
            result.append(item)
        return result

    def delete_resource(self, resource_id: str, *, owner_id: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM learning_resources WHERE id = ? AND owner_id = ?",
                (resource_id, owner_id),
            )
        return cur.rowcount > 0

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
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO attachments (conversation_id, message_id, kind, mime, data, "
                "owner_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (conversation_id, message_id, kind, mime, data, owner_id, _now()),
            )
        return int(cur.lastrowid)

    def get_attachment(self, attachment_id: int, *, owner_id: str | None = None) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT a.id, a.conversation_id, a.message_id, a.kind, a.mime, a.data, "
                "a.owner_id, a.created_at, c.student_id AS conversation_owner "
                "FROM attachments a LEFT JOIN conversations c ON c.id = a.conversation_id "
                "WHERE a.id = ?",
                (attachment_id,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        if owner_id is not None and owner_id not in (
            result.get("owner_id"),
            result.get("conversation_owner"),
        ):
            return None
        return result

    def link_attachment(
        self,
        attachment_id: int,
        conversation_id: str,
        message_id: int | None = None,
        *,
        owner_id: str | None = None,
    ) -> None:
        with self._lock, self._conn:
            if owner_id is None:
                self._conn.execute(
                    "UPDATE attachments SET conversation_id = ?, message_id = ? WHERE id = ?",
                    (conversation_id, message_id, attachment_id),
                )
            else:
                self._conn.execute(
                    "UPDATE attachments SET conversation_id = ?, message_id = ? "
                    "WHERE id = ? AND owner_id = ? AND EXISTS ("
                    "SELECT 1 FROM conversations WHERE id = ? AND student_id = ?)",
                    (
                        conversation_id,
                        message_id,
                        attachment_id,
                        owner_id,
                        conversation_id,
                        owner_id,
                    ),
                )

    def get_settings(self, student_id: str) -> dict:
        with self._lock:
            row = self._conn.execute(
                "SELECT settings FROM user_settings WHERE student_id = ?", (student_id,)
            ).fetchone()
        return json.loads(row["settings"]) if row else {}

    def put_settings(self, student_id: str, settings: dict) -> None:
        payload = json.dumps(settings, separators=(",", ":"), sort_keys=True)
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO user_settings (student_id, settings, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT (student_id) DO UPDATE SET "
                "settings = excluded.settings, updated_at = excluded.updated_at",
                (student_id, payload, _now()),
            )

    def patch_settings(self, student_id: str, changes: dict) -> dict:
        """Atomically merge independent preference controls and return the stored object."""
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT settings FROM user_settings WHERE student_id = ?", (student_id,)
            ).fetchone()
            values = json.loads(row["settings"]) if row else {}
            values.update(changes)
            payload = json.dumps(values, separators=(",", ":"), sort_keys=True)
            self._conn.execute(
                "INSERT INTO user_settings (student_id, settings, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT (student_id) DO UPDATE SET "
                "settings = excluded.settings, updated_at = excluded.updated_at",
                (student_id, payload, _now()),
            )
        return values

    def delete_student(self, student_id: str) -> dict[str, int]:
        with self._lock, self._conn:
            owned_attachments = self._conn.execute(
                "DELETE FROM attachments WHERE owner_id = ?",
                (student_id,),
            ).rowcount
            conversations = self._conn.execute(
                "DELETE FROM conversations WHERE student_id = ?", (student_id,)
            ).rowcount
            resources = self._conn.execute(
                "DELETE FROM learning_resources WHERE owner_id = ?", (student_id,)
            ).rowcount
            settings = self._conn.execute(
                "DELETE FROM user_settings WHERE student_id = ?", (student_id,)
            ).rowcount
        return {
            "conversations": conversations,
            "orphan_attachments": owned_attachments,
            "resources": resources,
            "settings": settings,
        }

    def reap_orphan_attachments(self, older_than_seconds: float) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=older_than_seconds)).isoformat()
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM attachments WHERE conversation_id IS NULL AND created_at < ?",
                (cutoff,),
            )
        return cur.rowcount

    def delete_settings(self, student_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM user_settings WHERE student_id = ?", (student_id,))

    def close(self) -> None:
        with self._lock:
            self._conn.close()
