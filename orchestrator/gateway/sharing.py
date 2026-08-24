"""Durable, offline accounts and sessions for Muta's LAN Host mode.

The conversation store may be PostgreSQL (Compose) or SQLite (portable/native).  Sharing
control deliberately stays in one small SQLite database under ``TUTOR_ROOT/data`` so account
behaviour and host recovery are identical in both deployments.  Passwords use stdlib scrypt;
session/enrollment secrets are never stored, only their SHA-256 digests.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import threading
import time
import unicodedata
import uuid
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Literal

from runtime.paths import data_root

SESSION_PREFIX = "msh_"
HOST_ROLE = "host"
MEMBER_ROLE = "member"
SESSION_COOKIE = "muta_share_session"

_USERNAME_EDGE = re.compile(r"^[^._-].*[^._-]$|^[^._-]$")
_SESSION_IDLE = timedelta(hours=24)
_SESSION_ABSOLUTE = timedelta(days=30)
_ENROLLMENT_LIFETIME = timedelta(hours=24)
_MAX_PENDING = 100


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat()


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def normalize_username(value: str) -> tuple[str, str]:
    display = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not 3 <= len(display) <= 32:
        raise ValueError("username must be between 3 and 32 characters")
    if not _USERNAME_EDGE.match(display):
        raise ValueError("username cannot start or end with punctuation")
    if not all(ch.isalnum() or ch in "._-" for ch in display):
        raise ValueError("username may contain letters, numbers, dots, dashes and underscores")
    return display.casefold(), display


def _validate_password(password: str) -> bytes:
    raw = str(password or "").encode("utf-8")
    if len(raw) < 8:
        raise ValueError("password must be at least 8 characters")
    if len(raw) > 256:
        raise ValueError("password is too long")
    return raw


_SCRYPT_SLOTS = threading.BoundedSemaphore(
    max(1, int(os.environ.get("MUTA_SHARE_SCRYPT_CONCURRENCY", "2")))
)


def _password_hash(password: bytes, salt: bytes) -> bytes:
    # N=2^14, r=8, p=1 uses ~16 MiB briefly and is intentionally bounded.  A global rate
    # limiter below stops a LAN peer from turning that cost into unbounded memory pressure.
    with _SCRYPT_SLOTS:
        return hashlib.scrypt(password, salt=salt, n=2**14, r=8, p=1, dklen=32)


@dataclass(frozen=True)
class SharePrincipal:
    subject: str
    role: Literal["host", "member"]
    session_id: str
    username: str | None = None


@dataclass(frozen=True)
class IssuedSession:
    principal: SharePrincipal
    token: str
    csrf_token: str
    expires_at: str


class AuthenticationError(ValueError):
    pass


class EnrollmentError(ValueError):
    pass


class LoginThrottle:
    """Small process-local limiter for the expensive password endpoints.

    It is a protection layer, not identity state, so losing it on restart is harmless.  Both
    per-key and global windows are bounded to prevent a rotating-username scrypt flood.
    """

    def __init__(self, *, window_s: float = 300.0, per_key: int = 6, global_limit: int = 60):
        self.window_s = window_s
        self.per_key = per_key
        self.global_limit = global_limit
        self._lock = threading.Lock()
        self._events: dict[str, list[float]] = {}
        self._global: list[float] = []

    def check(self, key: str) -> None:
        now = time.monotonic()
        cutoff = now - self.window_s
        with self._lock:
            self._global = [stamp for stamp in self._global if stamp >= cutoff]
            events = [stamp for stamp in self._events.get(key, []) if stamp >= cutoff]
            self._events[key] = events
            if len(events) >= self.per_key or len(self._global) >= self.global_limit:
                raise AuthenticationError("too many attempts — wait a few minutes and try again")
            events.append(now)
            self._global.append(now)

    def clear(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)


_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS share_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    enabled INTEGER NOT NULL DEFAULT 0,
    memory_mode TEXT NOT NULL DEFAULT 'competition'
        CHECK (memory_mode IN ('competition', 'system')),
    updated_at TEXT NOT NULL
);
INSERT OR IGNORE INTO share_settings (id, enabled, memory_mode, updated_at)
VALUES (1, 0, 'competition', '1970-01-01T00:00:00+00:00');

CREATE TABLE IF NOT EXISTS share_users (
    id TEXT PRIMARY KEY,
    username_key TEXT NOT NULL UNIQUE,
    username TEXT NOT NULL,
    password_salt BLOB NOT NULL,
    password_hash BLOB NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'deleting')),
    created_at TEXT NOT NULL,
    approved_at TEXT,
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS share_sessions (
    id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    csrf_hash TEXT NOT NULL,
    subject TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('host', 'member')),
    user_id TEXT REFERENCES share_users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    idle_expires_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_share_sessions_user ON share_sessions(user_id, revoked_at);

CREATE TABLE IF NOT EXISTS share_enrollments (
    id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES share_users(id) ON DELETE SET NULL,
    secret_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'approved', 'rejected', 'removed', 'expired')
    ),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    exchange_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_share_enrollments_user ON share_enrollments(user_id, status);
"""


class SharingService:
    def __init__(self, path: Path | str | None = None) -> None:
        configured = (
            path
            or os.environ.get("MUTA_SHARE_DB_PATH")
            or data_root() / "muta-share.sqlite3"
        )
        self.path = Path(configured)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with suppress(OSError):
            self.path.parent.chmod(0o700)
        self._lock = threading.RLock()
        self._operations = threading.Condition(self._lock)
        self._active_member_writes: dict[str, int] = {}
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(_SCHEMA)
        with suppress(OSError):
            self.path.chmod(0o600)
        self.login_throttle = LoginThrottle()
        self.signup_throttle = LoginThrottle(per_key=3, global_limit=30)
        # Unknown-user verification takes the same scrypt path as a real account.
        self._dummy_salt = hashlib.sha256(b"muta-share-dummy-salt").digest()[:16]
        self._dummy_hash = _password_hash(b"not-a-real-password", self._dummy_salt)

    # --- host settings ---------------------------------------------------------------
    def settings(self) -> dict:
        with self._lock:
            row = self._conn.execute(
                "SELECT enabled, memory_mode, updated_at FROM share_settings WHERE id = 1"
            ).fetchone()
        return {
            "enabled": bool(row["enabled"]),
            "memory_mode": row["memory_mode"],
            "updated_at": row["updated_at"],
        }

    def update_settings(self, *, enabled: bool, memory_mode: str) -> dict:
        if memory_mode not in {"competition", "system"}:
            raise ValueError("unknown memory mode")
        with self._lock, self._conn:
            old = self.settings()
            self._conn.execute(
                "UPDATE share_settings SET enabled = ?, memory_mode = ?, "
                "updated_at = ? WHERE id = 1",
                (int(enabled), memory_mode, _iso()),
            )
            if old["enabled"] and not enabled:
                # Pausing hosting preserves accounts/data but requires a fresh login when it is
                # enabled again.  No stolen classroom cookie survives an operator shutdown.
                self._conn.execute(
                    "UPDATE share_sessions SET revoked_at = ? "
                    "WHERE role = 'member' AND revoked_at IS NULL",
                    (_iso(),),
                )
        return self.settings()

    # --- enrollment and password authentication ------------------------------------
    def _reap_expired_pending_locked(self, now: datetime) -> int:
        rows = self._conn.execute(
            "SELECT id, user_id FROM share_enrollments "
            "WHERE status = 'pending' AND expires_at <= ?",
            (_iso(now),),
        ).fetchall()
        if not rows:
            return 0
        enrollment_ids = [row["id"] for row in rows]
        user_ids = [row["user_id"] for row in rows if row["user_id"]]
        self._conn.executemany(
            "UPDATE share_enrollments SET status = 'expired', updated_at = ? WHERE id = ?",
            [(_iso(now), enrollment_id) for enrollment_id in enrollment_ids],
        )
        if user_ids:
            self._conn.executemany(
                "DELETE FROM share_users WHERE id = ? AND status = 'pending'",
                [(user_id,) for user_id in user_ids],
            )
        return len(user_ids)

    def signup(self, username: str, password: str, *, throttle_key: str) -> dict:
        self.signup_throttle.check(throttle_key)
        key, display = normalize_username(username)
        raw_password = _validate_password(password)
        # Reject cheap, known failures before allocating scrypt's ~16 MiB working set.
        with self._lock, self._conn:
            self._reap_expired_pending_locked(_now())
            if not self.settings()["enabled"]:
                raise EnrollmentError("this Muta host is not accepting sign-ups")
            pending = self._conn.execute(
                "SELECT COUNT(*) AS n FROM share_users WHERE status = 'pending'"
            ).fetchone()["n"]
            if pending >= _MAX_PENDING:
                raise EnrollmentError("the approval list is full — ask the host to clear it")
            if self._conn.execute(
                "SELECT 1 FROM share_users WHERE username_key = ?", (key,)
            ).fetchone():
                raise EnrollmentError("that username is already registered on this Muta")
        salt = secrets.token_bytes(16)
        digest = _password_hash(raw_password, salt)
        now = _now()
        user_id = str(uuid.uuid4())
        enrollment_id = uuid.uuid4().hex
        secret = secrets.token_urlsafe(32)
        with self._lock, self._conn:
            if not self.settings()["enabled"]:
                raise EnrollmentError("this Muta host is not accepting sign-ups")
            pending = self._conn.execute(
                "SELECT COUNT(*) AS n FROM share_users WHERE status = 'pending'"
            ).fetchone()["n"]
            if pending >= _MAX_PENDING:
                raise EnrollmentError("the approval list is full — ask the host to clear it")
            try:
                self._conn.execute(
                    "INSERT INTO share_users "
                    "(id, username_key, username, password_salt, password_hash, "
                    "status, created_at) "
                    "VALUES (?, ?, ?, ?, ?, 'pending', ?)",
                    (user_id, key, display, salt, digest, _iso(now)),
                )
            except sqlite3.IntegrityError as exc:
                raise EnrollmentError("that username is already registered on this Muta") from exc
            self._conn.execute(
                "INSERT INTO share_enrollments "
                "(id, user_id, secret_hash, status, created_at, expires_at, updated_at) "
                "VALUES (?, ?, ?, 'pending', ?, ?, ?)",
                (
                    enrollment_id,
                    user_id,
                    _digest(secret),
                    _iso(now),
                    _iso(now + _ENROLLMENT_LIFETIME),
                    _iso(now),
                ),
            )
        return {
            "enrollment_id": enrollment_id,
            "enrollment_secret": secret,
            "status": "pending",
            "username": display,
            "expires_at": _iso(now + _ENROLLMENT_LIFETIME),
        }

    def enrollment(self, enrollment_id: str, secret: str) -> tuple[dict, IssuedSession | None]:
        now = _now()
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT e.*, u.username, u.status AS user_status FROM share_enrollments e "
                "LEFT JOIN share_users u ON u.id = e.user_id WHERE e.id = ?",
                (enrollment_id,),
            ).fetchone()
            if row is None or not hmac.compare_digest(row["secret_hash"], _digest(secret or "")):
                raise EnrollmentError("unknown approval request")
            status = row["status"]
            if _parse(row["expires_at"]) <= now and status in {"pending", "approved"}:
                status = "expired"
                self._conn.execute(
                    "UPDATE share_enrollments SET status = 'expired', updated_at = ? WHERE id = ?",
                    (_iso(now), enrollment_id),
                )
            can_login = status == "expired" and row["user_status"] == "approved"
            if status == "approved" and row["user_status"] == "approved":
                # Allow at most three exchanges inside the short enrollment lifetime.  This
                # makes a lost HTTP response recoverable without making the approval secret a
                # permanent login credential.
                if int(row["exchange_count"]) >= 3:
                    return (
                        {"status": "approved", "username": row["username"], "can_login": True},
                        None,
                    )
                session = self._issue_session_locked(
                    subject=row["user_id"], role=MEMBER_ROLE, username=row["username"]
                )
                self._conn.execute(
                    "UPDATE share_enrollments SET exchange_count = exchange_count + 1, "
                    "updated_at = ? WHERE id = ?",
                    (_iso(now), enrollment_id),
                )
                return (
                    {"status": "approved", "username": row["username"], "can_login": True},
                    session,
                )
            return (
                {"status": status, "username": row["username"], "can_login": can_login},
                None,
            )

    def login(self, username: str, password: str, *, throttle_key: str) -> IssuedSession:
        key, _display = normalize_username(username)
        self.login_throttle.check(throttle_key)
        raw_password = _validate_password(password)
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM share_users WHERE username_key = ?", (key,)
            ).fetchone()
        salt = bytes(row["password_salt"]) if row else self._dummy_salt
        expected = bytes(row["password_hash"]) if row else self._dummy_hash
        valid = hmac.compare_digest(_password_hash(raw_password, salt), expected)
        if not valid or row is None:
            raise AuthenticationError("incorrect username or password")
        if row["status"] == "pending":
            raise AuthenticationError("your sign-up is still waiting for host approval")
        if row["status"] != "approved" or not self.settings()["enabled"]:
            raise AuthenticationError("this account cannot sign in right now")
        with self._lock, self._conn:
            session = self._issue_session_locked(
                subject=row["id"], role=MEMBER_ROLE, username=row["username"]
            )
            self._conn.execute(
                "UPDATE share_users SET last_login_at = ? WHERE id = ?", (_iso(), row["id"])
            )
        self.login_throttle.clear(throttle_key)
        return session

    # --- sessions --------------------------------------------------------------------
    def issue_host_session(self, operator_id: str) -> IssuedSession:
        with self._lock, self._conn:
            return self._issue_session_locked(subject=operator_id, role=HOST_ROLE, username=None)

    def _issue_session_locked(
        self, *, subject: str, role: Literal["host", "member"], username: str | None
    ) -> IssuedSession:
        now = _now()
        token = SESSION_PREFIX + secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        session_id = uuid.uuid4().hex
        expires = now + _SESSION_ABSOLUTE
        idle = now + _SESSION_IDLE
        self._conn.execute(
            "INSERT INTO share_sessions "
            "(id, token_hash, csrf_hash, subject, role, user_id, created_at, last_seen_at, "
            "idle_expires_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                _digest(token),
                _digest(csrf),
                subject,
                role,
                subject if role == MEMBER_ROLE else None,
                _iso(now),
                _iso(now),
                _iso(idle),
                _iso(expires),
            ),
        )
        return IssuedSession(
            principal=SharePrincipal(subject, role, session_id, username),
            token=token,
            csrf_token=csrf,
            expires_at=_iso(expires),
        )

    def resolve_session(self, token: str | None, *, touch: bool = True) -> SharePrincipal | None:
        if not token or not token.startswith(SESSION_PREFIX):
            return None
        now = _now()
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT s.*, u.username, u.status AS user_status FROM share_sessions s "
                "LEFT JOIN share_users u ON u.id = s.user_id "
                "WHERE s.token_hash = ? AND s.revoked_at IS NULL",
                (_digest(token),),
            ).fetchone()
            if row is None:
                return None
            expired = _parse(row["expires_at"]) <= now or _parse(row["idle_expires_at"]) <= now
            member_invalid = row["role"] == MEMBER_ROLE and (
                row["user_status"] != "approved" or not self.settings()["enabled"]
            )
            if expired or member_invalid:
                self._conn.execute(
                    "UPDATE share_sessions SET revoked_at = ? WHERE id = ?", (_iso(now), row["id"])
                )
                return None
            if touch and (now - _parse(row["last_seen_at"])) >= timedelta(minutes=5):
                self._conn.execute(
                    "UPDATE share_sessions SET last_seen_at = ?, idle_expires_at = ? WHERE id = ?",
                    (_iso(now), _iso(now + _SESSION_IDLE), row["id"]),
                )
        return SharePrincipal(row["subject"], row["role"], row["id"], row["username"])

    def verify_csrf(self, session_id: str, token: str | None) -> bool:
        if not token:
            return False
        with self._lock:
            row = self._conn.execute(
                "SELECT csrf_hash FROM share_sessions WHERE id = ? AND revoked_at IS NULL",
                (session_id,),
            ).fetchone()
        return bool(row and hmac.compare_digest(row["csrf_hash"], _digest(token)))

    def logout(self, token: str | None) -> bool:
        if not token:
            return False
        with self._lock, self._conn:
            changed = self._conn.execute(
                "UPDATE share_sessions SET revoked_at = ? "
                "WHERE token_hash = ? AND revoked_at IS NULL",
                (_iso(), _digest(token)),
            ).rowcount
        return bool(changed)

    # --- host roster and lifecycle ---------------------------------------------------
    @contextmanager
    def member_write(self, user_id: str) -> Iterator[None]:
        """Lease one durable member mutation against host removal.

        Removal changes the account to ``deleting`` under the same condition. A mutation
        that obtained its lease first completes and is then erased; a late mutation is
        refused. This closes the authenticate → long upload/decode → post-removal insert race.
        """
        with self._operations:
            row = self._conn.execute(
                "SELECT status FROM share_users WHERE id = ?", (user_id,)
            ).fetchone()
            if row is None or row["status"] != "approved" or not self.settings()["enabled"]:
                raise AuthenticationError("this account can no longer save data")
            self._active_member_writes[user_id] = self._active_member_writes.get(user_id, 0) + 1
        try:
            yield
        finally:
            with self._operations:
                remaining = self._active_member_writes.get(user_id, 1) - 1
                if remaining > 0:
                    self._active_member_writes[user_id] = remaining
                else:
                    self._active_member_writes.pop(user_id, None)
                self._operations.notify_all()

    def users(self) -> list[dict]:
        with self._lock, self._conn:
            self._reap_expired_pending_locked(_now())
            rows = self._conn.execute(
                "SELECT id, username, status, created_at, approved_at, last_login_at "
                "FROM share_users ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, created_at"
            ).fetchall()
        return [dict(row) for row in rows]

    def approve(self, user_id: str) -> dict:
        now = _iso()
        with self._lock, self._conn:
            changed = self._conn.execute(
                "UPDATE share_users SET status = 'approved', approved_at = ? "
                "WHERE id = ? AND status = 'pending'",
                (now, user_id),
            ).rowcount
            if not changed:
                raise LookupError("unknown pending user")
            self._conn.execute(
                "UPDATE share_enrollments SET status = 'approved', updated_at = ? "
                "WHERE user_id = ? AND status = 'pending'",
                (now, user_id),
            )
            row = self._conn.execute(
                "SELECT id, username, status, created_at, approved_at, last_login_at "
                "FROM share_users WHERE id = ?",
                (user_id,),
            ).fetchone()
        return dict(row)

    def reject(self, user_id: str) -> None:
        now = _iso()
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT status FROM share_users WHERE id = ?", (user_id,)
            ).fetchone()
            if row is None or row["status"] != "pending":
                raise LookupError("unknown pending user")
            self._conn.execute(
                "UPDATE share_enrollments SET status = 'rejected', user_id = NULL, updated_at = ? "
                "WHERE user_id = ?",
                (now, user_id),
            )
            self._conn.execute("DELETE FROM share_users WHERE id = ?", (user_id,))

    def begin_removal(self, user_id: str, *, write_timeout_s: float = 5.0) -> str:
        now = _iso()
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT username, status FROM share_users WHERE id = ?", (user_id,)
            ).fetchone()
            if row is None:
                raise LookupError("unknown user")
            self._conn.execute(
                "UPDATE share_users SET status = 'deleting' WHERE id = ?", (user_id,)
            )
            self._conn.execute(
                "UPDATE share_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                (now, user_id),
            )
            self._conn.execute(
                "UPDATE share_enrollments SET status = 'removed', updated_at = ? WHERE user_id = ?",
                (now, user_id),
            )
        deadline = time.monotonic() + max(0.0, write_timeout_s)
        with self._operations:
            while self._active_member_writes.get(user_id, 0):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError("a learner data write is still draining")
                self._operations.wait(remaining)
        return row["username"]

    def finalize_removal(self, user_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE share_enrollments SET user_id = NULL WHERE user_id = ?", (user_id,)
            )
            self._conn.execute("DELETE FROM share_users WHERE id = ?", (user_id,))

    def deleting_ids(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id FROM share_users WHERE status = 'deleting'"
            ).fetchall()
        return [row["id"] for row in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


@lru_cache(maxsize=1)
def get_sharing_service() -> SharingService:
    return SharingService()
