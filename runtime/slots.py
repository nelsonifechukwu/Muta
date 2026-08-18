"""Slot save/restore — how 6 slots serve 30 students (TDD §8.3, T12).

`--slot-save-path` turns a slot's KV cache into a file:

    POST :8081/slots/{id}?action=save    {"filename": "<session>.bin"}
    POST :8081/slots/{id}?action=restore {"filename": "<session>.bin"}

A restore costs one disk read instead of a full prefill, which is what makes suspend/resume
cheap enough to do on every idle slot. A *missed* restore (evicted or corrupt snapshot) is
not a cold start either: the system+syllabus prefix is still in the prompt cache
(`--cache-ram`), so the miss costs one summary re-prefill.

The snapshot directory is capped and LRU-reaped. At classroom-6-short a snapshot is ~150 MiB;
thirty of them is 4.5 GiB, and a full disk turns "suspend" into a failed write in the middle
of a lesson.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

log = logging.getLogger("muta.runtime.slots")

#: TDD §8.3 — LRU cap on the snapshot directory.
SNAPSHOT_DIR_CAP_BYTES = 4 * 1024**3


class SlotError(RuntimeError):
    pass


@dataclass
class SlotClient:
    """Talks to llama-server's slot endpoints. Failures are reported, never swallowed: a
    silent save failure means a student's session vanishes at resume time."""

    base_url: str = "http://127.0.0.1:8081"
    api_key: str | None = None
    timeout: float = 30.0

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def _post(self, slot_id: int, action: str, filename: str) -> dict:
        try:
            response = httpx.post(
                f"{self.base_url.rstrip('/')}/slots/{slot_id}",
                params={"action": action},
                json={"filename": filename},
                headers=self._headers(),
                timeout=self.timeout,
            )
        except httpx.HTTPError as e:
            raise SlotError(f"slot {action} failed: {e}") from e
        if response.status_code >= 400:
            raise SlotError(f"slot {action} failed ({response.status_code}): {response.text[:200]}")
        return response.json() if response.content else {}

    def save(self, slot_id: int, session_id: str) -> dict:
        return self._post(slot_id, "save", snapshot_name(session_id))

    def restore(self, slot_id: int, session_id: str) -> dict:
        return self._post(slot_id, "restore", snapshot_name(session_id))

    def erase(self, slot_id: int) -> dict:
        return self._post(slot_id, "erase", "")

    def slots(self) -> list[dict]:
        """Per-slot state from `--slots`. The gateway's view of who is busy."""
        try:
            response = httpx.get(f"{self.base_url}/slots", headers=self._headers(), timeout=5.0)
            response.raise_for_status()
            return list(response.json())
        except (httpx.HTTPError, ValueError) as e:
            raise SlotError(f"could not read slot state: {e}") from e


def snapshot_name(session_id: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in session_id)
    return f"{safe}.bin"


@dataclass
class SnapshotReaper:
    """LRU eviction over the snapshot directory (§8.3)."""

    directory: Path
    cap_bytes: int = SNAPSHOT_DIR_CAP_BYTES

    def total_bytes(self) -> int:
        return sum(f.stat().st_size for f in self._snapshots())

    def _snapshots(self) -> list[Path]:
        if not self.directory.is_dir():
            return []
        return [f for f in self.directory.glob("*.bin") if f.is_file()]

    def reap(self, *, keep: set[str] | None = None) -> list[Path]:
        """Evict oldest-used snapshots until the directory fits. Returns what was removed.

        `keep` protects live sessions: evicting the snapshot of a student who is mid-answer
        converts a cheap restore into a cold start for the one person actively waiting.
        """
        protected = {snapshot_name(s) for s in (keep or set())}
        files = sorted(self._snapshots(), key=lambda f: f.stat().st_atime)
        total = sum(f.stat().st_size for f in files)
        removed: list[Path] = []
        for f in files:
            if total <= self.cap_bytes:
                break
            if f.name in protected:
                continue
            size = f.stat().st_size
            f.unlink(missing_ok=True)
            total -= size
            removed.append(f)
        if removed:
            log.info("reaped %d snapshots (%.1f GiB now)", len(removed), total / 1024**3)
        return removed

    def has(self, session_id: str) -> bool:
        return (self.directory / snapshot_name(session_id)).is_file()

    def drop(self, session_id: str) -> bool:
        path = self.directory / snapshot_name(session_id)
        if path.is_file():
            path.unlink()
            return True
        return False

    def clear(self) -> list[Path]:
        """Remove all saved KV state after a model replacement.

        Slot snapshots encode the old model's KV tensors and are never compatible with the
        replacement, even when context geometry happens to match. Conversation messages stay
        in SQLite and are re-prefilled normally.
        """
        removed: list[Path] = []
        for path in self._snapshots():
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                # The new SessionManager starts with no suspended ids, so even a file that
                # cannot be removed is ineligible for restore. Keep the model switch healthy.
                log.warning("could not remove stale KV snapshot %s: %s", path, exc)
                continue
            removed.append(path)
        return removed

    def touch(self, session_id: str) -> None:
        """Mark a snapshot as recently used so LRU order reflects sessions, not writes."""
        path = self.directory / snapshot_name(session_id)
        if path.is_file():
            now = time.time()
            import os

            os.utime(path, (now, path.stat().st_mtime))
