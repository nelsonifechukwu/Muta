"""Live telemetry for the web UI: RSS + peak (whole process tree), CPU temp, throttle flag,
and a per-conversation rolling tokens/sec.

Design constraints:
- bounded memory forever (a compose service runs for days — bench's TreeSampler appends
  samples unboundedly and is deliberately NOT reused here);
- unmeasurable metrics are None, never an exception (Docker on macOS has no sensors);
- readable from async handlers without blocking: one daemon thread refreshes shared
  attributes at 1 Hz, handlers only take a lock for a dict copy.
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from functools import lru_cache

from bench.sampler import family_rss_bytes, read_temp_c

_GB = 1024**3
SAMPLE_INTERVAL_S = 1.0
RATE_WINDOW_S = 2.0
# The scoring rule's cliff (score.py applies the same 85 °C line to bench runs).
THROTTLE_TEMP_C = 85.0
# Drop a conversation's tick history after this much silence.
TICKS_IDLE_TTL_S = 300.0


class TelemetryHub:
    def __init__(self, root_pid: int | None = None) -> None:
        self._root_pid = root_pid or os.getpid()
        self._lock = threading.Lock()
        self._rss_bytes = 0
        self._peak_rss_bytes = 0
        self._temp_c: float | None = None
        # Sticky miss: inside the backend container `sensors -u` exists but reads nothing on
        # a macOS VM — don't pay a subprocess every second forever for a permanent None.
        self._temp_unavailable = False
        self._ticks: dict[str, deque[tuple[float, int]]] = {}
        self._generating: set[str] = set()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # --- sampling ---------------------------------------------------------------------

    def start(self) -> None:
        with self._lock:
            if self._thread is not None:
                return
            self._thread = threading.Thread(target=self._run, name="telemetry-hub", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            self.sample_once()
            self._stop.wait(SAMPLE_INTERVAL_S)

    def sample_once(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        rss = family_rss_bytes(self._root_pid)
        temp: float | None = None
        if not self._temp_unavailable:
            try:
                temp = read_temp_c()
            except Exception:  # noqa: BLE001 — telemetry must never take the service down
                temp = None
            if temp is None:
                self._temp_unavailable = True
        with self._lock:
            if rss:
                self._rss_bytes = rss
                self._peak_rss_bytes = max(self._peak_rss_bytes, rss)
            self._temp_c = temp
            stale = [
                cid
                for cid, ticks in self._ticks.items()
                if cid not in self._generating
                and (not ticks or now - ticks[-1][0] > TICKS_IDLE_TTL_S)
            ]
            for cid in stale:
                del self._ticks[cid]

    # --- per-conversation generation tracking -----------------------------------------

    def begin(self, conversation_id: str) -> None:
        with self._lock:
            self._generating.add(conversation_id)
            self._ticks.setdefault(conversation_id, deque(maxlen=4096))

    def end(self, conversation_id: str) -> None:
        with self._lock:
            self._generating.discard(conversation_id)

    def tick(self, conversation_id: str, n_tokens: int = 1) -> None:
        with self._lock:
            self._ticks.setdefault(conversation_id, deque(maxlen=4096)).append(
                (time.monotonic(), n_tokens)
            )

    def rate(self, conversation_id: str, now: float | None = None) -> float | None:
        """Tokens/sec over the trailing window; None when nothing recent (idle → UI shows —)."""
        now = time.monotonic() if now is None else now
        with self._lock:
            ticks = list(self._ticks.get(conversation_id, ()))
        recent = [(t, n) for t, n in ticks if now - t <= RATE_WINDOW_S]
        if not recent:
            return None
        span = now - recent[0][0]
        if span <= 0:
            return None
        return sum(n for _, n in recent) / span

    # --- reads ------------------------------------------------------------------------

    def snapshot(self, conversation_id: str) -> dict:
        with self._lock:
            rss = self._rss_bytes
            peak = self._peak_rss_bytes
            temp = self._temp_c
            generating = conversation_id in self._generating
        rate = self.rate(conversation_id)
        return {
            "rss_gb": round(rss / _GB, 3),
            "peak_rss_gb": round(peak / _GB, 3),
            "cpu_temp_c": temp,
            "throttled": None if temp is None else temp > THROTTLE_TEMP_C,
            "tokens_per_second": round(rate, 2) if rate is not None else None,
            "generating": generating,
        }


@lru_cache(maxsize=1)
def get_hub() -> TelemetryHub:
    return TelemetryHub()
