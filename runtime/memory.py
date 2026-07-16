"""Persistent conversation memory over SQLite.

Two tables: `conversations` (one per chat thread) and `messages` (the turns). Multi-turn
context is reconstructed by replaying a conversation's messages back to the model. This is
the durable "learning-twin adjacent" store the product needs offline; the DB file lives in
`data/` (gitignored) and travels with the deployment.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
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
CREATE INDEX IF NOT EXISTS idx_conversations_student ON conversations(student_id, updated_at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConversationStore:
    """Thread-safe SQLite store. Pass ``":memory:"`` for an ephemeral DB (tests)."""

    def __init__(self, db_path: str | Path = "data/muta.sqlite3") -> None:
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False + a lock: FastAPI may call from its threadpool.
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

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
        with self._lock:
            self._conn.execute(
                "INSERT INTO conversations "
                "(id, student_id, mode, persona, subject, language, title, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (cid, student_id, mode, persona, subject, language, title, ts, ts),
            )
            self._conn.commit()
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
        return [dict(r) for r in rows]

    def delete_conversation(self, conversation_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
            self._conn.commit()

    # --- messages ---------------------------------------------------------------------

    def add_message(self, conversation_id: str, role: str, content: str) -> int:
        ts = _now()
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO messages (conversation_id, role, content, created_at) "
                "VALUES (?, ?, ?, ?)",
                (conversation_id, role, content, ts),
            )
            self._conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (ts, conversation_id)
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def get_messages(self, conversation_id: str, limit: int | None = None) -> list[dict]:
        """Messages in chronological order. With ``limit``, the most recent ``limit``."""
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
        return [dict(r) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
