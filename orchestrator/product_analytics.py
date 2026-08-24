"""Consent-gated, offline-safe fleet heartbeat for shipped Muta installations.

This module is deliberately separate from ``orchestrator.telemetry``. The latter is local
performance telemetry used by the learner UI; this module is the only product data that can
leave the laptop. It never carries prompts, conversations, files, usernames, email, hostname,
or coordinates. The cloud collector derives an approximate location from the request IP and
discards that IP.
"""

from __future__ import annotations

import hashlib
import logging
import os
import platform
import secrets
import sqlite3
import threading
import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import httpx

from orchestrator.version import git_sha, version
from runtime.paths import data_root

log = logging.getLogger("muta.product_analytics")

Consent = Literal["unknown", "granted", "declined"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat()


@dataclass(frozen=True)
class FleetConfig:
    url: str | None
    ingest_key: str | None
    sync_interval_s: float = 60.0
    timeout_s: float = 5.0
    active_window_s: float = 300.0

    @classmethod
    def from_env(cls) -> FleetConfig:
        url = os.environ.get("MUTA_FLEET_URL", "").strip().rstrip("/") or None
        if url:
            parsed = urlsplit(url)
            loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            if not parsed.netloc or (parsed.scheme != "https" and not (
                parsed.scheme == "http" and loopback
            )):
                raise ValueError("MUTA_FLEET_URL must use HTTPS (HTTP is allowed on loopback only)")
        key = os.environ.get("MUTA_FLEET_INGEST_KEY", "").strip() or None
        return cls(
            url=url,
            ingest_key=key,
            sync_interval_s=max(15.0, float(os.environ.get("MUTA_FLEET_SYNC_INTERVAL_S", "60"))),
            timeout_s=max(1.0, float(os.environ.get("MUTA_FLEET_TIMEOUT_S", "5"))),
            active_window_s=max(
                60.0, float(os.environ.get("MUTA_FLEET_ACTIVE_WINDOW_S", "300"))
            ),
        )

    @property
    def configured(self) -> bool:
        return bool(self.url and self.ingest_key)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS product_analytics_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    installation_id TEXT NOT NULL,
    consent TEXT NOT NULL CHECK (consent IN ('unknown', 'granted', 'declined')),
    consented_at TEXT,
    last_synced_at TEXT,
    deletion_pending INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
"""


class ProductAnalyticsState:
    """One mode-0600 SQLite row: consent and delivery bookkeeping, never learner data."""

    def __init__(self, path: Path | str | None = None) -> None:
        configured = path or os.environ.get("MUTA_FLEET_STATE_PATH")
        self.path = Path(configured) if configured else data_root() / "product-analytics.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with suppress(OSError):
            self.path.parent.chmod(0o700)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock, self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.executescript(_SCHEMA)
            self._conn.execute(
                "INSERT OR IGNORE INTO product_analytics_state "
                "(id, installation_id, consent, updated_at) VALUES (1, ?, 'unknown', ?)",
                (str(uuid.uuid4()), _iso()),
            )
        with suppress(OSError):
            self.path.chmod(0o600)

    def snapshot(self) -> dict:
        with self._lock:
            row = self._conn.execute(
                "SELECT installation_id, consent, consented_at, last_synced_at, "
                "deletion_pending, updated_at FROM product_analytics_state WHERE id = 1"
            ).fetchone()
        return {
            **dict(row),
            "deletion_pending": bool(row["deletion_pending"]),
        }

    def set_consent(self, allowed: bool) -> dict:
        current = self.snapshot()
        next_consent: Consent = "granted" if allowed else "declined"
        # Once erasure is queued it survives repeated declines and a premature re-opt-in.
        # Sync deletes/rotates the old identity first, then a granted choice may send the new ID.
        pending = bool(
            current["deletion_pending"]
            or (not allowed and current["consent"] == "granted")
        )
        now = _iso()
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE product_analytics_state SET consent = ?, consented_at = ?, "
                "deletion_pending = ?, updated_at = ? WHERE id = 1",
                (next_consent, now, int(pending), now),
            )
        return self.snapshot()

    def mark_synced(self) -> None:
        now = _iso()
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE product_analytics_state SET last_synced_at = ?, updated_at = ? "
                "WHERE id = 1",
                (now, now),
            )

    def finish_remote_deletion(self) -> None:
        """Rotate identity after cloud erasure so a later opt-in cannot relink the old row."""
        now = _iso()
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE product_analytics_state SET installation_id = ?, "
                "deletion_pending = 0, last_synced_at = NULL, updated_at = ? WHERE id = 1",
                (str(uuid.uuid4()), now),
            )

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class ProductAnalytics:
    """In-memory activity clock plus a best-effort background delivery thread."""

    def __init__(
        self,
        *,
        state: ProductAnalyticsState | None = None,
        config: FleetConfig | None = None,
    ) -> None:
        self.state = state or ProductAnalyticsState()
        self.config = config or FleetConfig.from_env()
        self._activity_lock = threading.Lock()
        self._last_activity_at = _now()
        self._subject_key = secrets.token_bytes(16)
        self._active_subjects: dict[str, datetime] = {
            self._subject_digest(None): self._last_activity_at
        }
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    def _prune_activity_locked(self, now: datetime) -> None:
        cutoff = now.timestamp() - self.config.active_window_s
        self._active_subjects = {
            subject: seen
            for subject, seen in self._active_subjects.items()
            if seen.timestamp() >= cutoff
        }
        # Defensive cap: activity is aggregate-only and no installation should have thousands
        # of simultaneously active local accounts.
        if len(self._active_subjects) > 4096:
            newest = sorted(
                self._active_subjects.items(), key=lambda item: item[1], reverse=True
            )[:4096]
            self._active_subjects = dict(newest)

    def _subject_digest(self, subject: str | None) -> str:
        value = (subject or "local-operator").encode("utf-8", errors="replace")
        return hashlib.blake2b(value, key=self._subject_key, digest_size=12).hexdigest()

    def touch(self, subject: str | None = None) -> None:
        with self._activity_lock:
            self._last_activity_at = _now()
            self._active_subjects[self._subject_digest(subject)] = self._last_activity_at
            self._prune_activity_locked(self._last_activity_at)

    def status(self, *, manageable: bool) -> dict:
        row = self.state.snapshot()
        configured = self.config.configured
        return {
            "configured": configured,
            "manageable": manageable,
            "consent": row["consent"],
            "prompt_required": bool(manageable and configured and row["consent"] == "unknown"),
            "location_mode": "approximate_ip" if configured else "none",
            "last_synced_at": row["last_synced_at"],
            "deletion_pending": row["deletion_pending"],
            "data_shared": [
                "random installation ID",
                "app version/build and operating-system/processor family",
                "last-use time",
                "aggregate active and registered local-user counts",
                "approximate city-level network location",
            ]
            if configured
            else [],
        }

    def set_consent(self, allowed: bool) -> dict:
        row = self.state.set_consent(allowed)
        self._wake.set()
        return row

    def _user_count(self) -> int:
        """One local operator plus approved LAN accounts; no identity leaves this process."""
        try:
            from orchestrator.gateway.sharing import get_sharing_service

            approved = sum(
                1 for user in get_sharing_service().users() if user.get("status") == "approved"
            )
            return 1 + approved
        except Exception:  # noqa: BLE001 - analytics is never allowed to affect tutoring
            return 1

    def _heartbeat(self, installation_id: str) -> dict:
        with self._activity_lock:
            active_at = self._last_activity_at
            self._prune_activity_locked(_now())
            active_user_count = len(self._active_subjects)
        return {
            "installation_id": installation_id,
            "app_version": version(),
            "build_id": git_sha(),
            "platform": platform.system().lower() or "unknown",
            "architecture": platform.machine().lower() or "unknown",
            "active_at": _iso(active_at),
            "sent_at": _iso(),
            "local_user_count": self._user_count(),
            "active_local_user_count": active_user_count,
        }

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.ingest_key}",
            "Content-Type": "application/json",
            "User-Agent": f"Muta/{version()} fleet-heartbeat",
        }

    def sync_once(self) -> bool:
        """Deliver one deletion or heartbeat. False includes offline and intentional no-op."""
        if not self.config.configured:
            return False
        row = self.state.snapshot()
        assert self.config.url is not None
        try:
            if row["deletion_pending"]:
                response = httpx.delete(
                    f"{self.config.url}/v1/installations/{row['installation_id']}",
                    headers=self._headers(),
                    timeout=self.config.timeout_s,
                )
                response.raise_for_status()
                self.state.finish_remote_deletion()
                return True
            if row["consent"] != "granted":
                return False
            response = httpx.post(
                f"{self.config.url}/v1/heartbeat",
                headers=self._headers(),
                json=self._heartbeat(row["installation_id"]),
                timeout=self.config.timeout_s,
            )
            response.raise_for_status()
            self.state.mark_synced()
            return True
        except (httpx.HTTPError, OSError):
            # Offline is normal. Keep only the latest state and converge on the next attempt.
            log.debug("fleet sync deferred; collector is unreachable", exc_info=True)
            return False
        except Exception:  # malformed optional telemetry cannot hurt tutoring
            log.exception("fleet sync failed without affecting local tutoring")
            return False

    def start(self) -> None:
        if not self.config.configured or self._thread is not None:
            return

        def loop() -> None:
            while not self._stop.is_set():
                self._wake.clear()
                self.sync_once()
                self._wake.wait(self.config.sync_interval_s)

        self._thread = threading.Thread(target=loop, name="fleet-sync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)


@lru_cache(maxsize=1)
def get_product_analytics() -> ProductAnalytics:
    return ProductAnalytics()
