"""The degradation ladder (TDD §5.3, §5.4, T14).

    L0 normal   free ≥ 1.2 GiB          everything on
    L1          free < 1.2 GiB          no new CORE-VISION spawns; vision queues
    L2          free < 0.8 GiB          new sessions get ctx 2048; Kokoro → Piper
    L3          free < 0.5 GiB          pause TTS; suspend idle slots; refuse new sessions kindly
    L4          core RSS > cap − 100 MiB  admission drops to 4 effective slots; never kill core

"Free envelope" is `MemAvailable` minus a 300 MiB floor, polled every 2 s.

The ladder exists because the alternative is the kernel deciding. An OOM kill of the core
server is a hard failure — disqualification, not a deduction — so the system gives up
features in a chosen order, early, while it still can. Every level is reversible: the ladder
walks back down as memory returns, or the first `free()` after a spike leaves the demo
permanently degraded.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable

log = logging.getLogger("muta.gateway.ladder")

MiB = 1024**2
GiB = 1024**3

#: §5.3 thresholds, in bytes of free envelope.
L1_THRESHOLD = int(1.2 * GiB)
L2_THRESHOLD = int(0.8 * GiB)
L3_THRESHOLD = int(0.5 * GiB)
#: The floor subtracted from MemAvailable before anything is called "free".
RESERVE_BYTES = 300 * MiB
#: §5.1 — CORE-TEXT's cap; L4 triggers 100 MiB below it. Overridable because the right cap
#: is a property of the box: 4300 MiB encodes the competition 7 GB budget, while the dev
#: compose stack loads core + speculation draft (~4.2 GiB tree under emulation) and sizes
#: the cap for its own VM via MUTA_CORE_CAP_MIB.
CORE_CAP_BYTES = int(os.environ.get("MUTA_CORE_CAP_MIB", "4300")) * MiB
L4_MARGIN_BYTES = 100 * MiB
POLL_SECONDS = 2.0

#: Hysteresis: recovery needs this much more than the trigger, so a level does not flap
#: between L1 and L0 while a vision instance is being reaped.
HYSTERESIS_BYTES = 128 * MiB


class Level(IntEnum):
    L0 = 0
    L1 = 1
    L2 = 2
    L3 = 3
    L4 = 4


def mem_available_bytes() -> int:
    """`MemAvailable` on Linux; psutil elsewhere so the ladder is testable on a dev Mac.

    MemAvailable, not MemFree: page cache holding the mmap'd weights is *available* to
    reclaim, and treating it as used would report the box as full the moment the model
    loaded.
    """
    available = 0
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    available = int(line.split()[1]) * 1024
                    break
    except OSError:
        pass
    if not available:
        try:
            import psutil

            available = int(psutil.virtual_memory().available)
        except Exception:  # noqa: BLE001
            available = 8 * GiB  # unknown: assume healthy rather than degrade a working system
    # MemAvailable can describe the host instead of the container. memory.current includes
    # the complete backend tree, catching gateway/ASR/vision growth an engine RSS probe misses.
    for root in ("/sys/fs/cgroup", "/sys/fs/cgroup/memory"):
        try:
            with open(f"{root}/memory.max") as limit_file:
                limit_raw = limit_file.read().strip()
            with open(f"{root}/memory.current") as current_file:
                current_raw = current_file.read().strip()
        except OSError:
            try:
                with open(f"{root}/memory.limit_in_bytes") as limit_file:
                    limit_raw = limit_file.read().strip()
                with open(f"{root}/memory.usage_in_bytes") as current_file:
                    current_raw = current_file.read().strip()
            except OSError:
                continue
        try:
            if limit_raw != "max":
                limit = int(limit_raw)
                if 0 < limit < (1 << 60):
                    available = min(available, max(0, limit - int(current_raw)))
        except ValueError:
            pass
        break
    return available


@dataclass
class LadderState:
    level: Level = Level.L0
    free_bytes: int = 0
    core_rss_bytes: int = 0
    changed_at: float = 0.0
    reason: str = ""

    @property
    def free_gib(self) -> float:
        return self.free_bytes / GiB

    def as_dict(self) -> dict:
        return {
            "level": f"L{int(self.level)}",
            "free_gib": round(self.free_gib, 2),
            "core_rss_gib": round(self.core_rss_bytes / GiB, 2),
            "reason": self.reason,
            "vision_allowed": self.level < Level.L1,
            "tts_allowed": self.level < Level.L3,
            "new_sessions_allowed": self.level < Level.L3,
            "context_per_slot": self.context_for_new_session(),
            "effective_slots": self.effective_slots(),
        }

    # --- the policy each level implies -------------------------------------------------
    def context_for_new_session(self, default: int = 4096) -> int:
        return 2048 if self.level >= Level.L2 else default

    def effective_slots(self, configured: int = 6) -> int:
        # L4: shed slots via admission rather than restarting the server with `-np 4`, which
        # would drop every live session to save one.
        return min(configured, 4) if self.level >= Level.L4 else configured

    @property
    def vision_allowed(self) -> bool:
        return self.level < Level.L1

    @property
    def tts_allowed(self) -> bool:
        return self.level < Level.L3

    @property
    def accepts_new_sessions(self) -> bool:
        return self.level < Level.L3

    @property
    def premium_tts_allowed(self) -> bool:
        return self.level < Level.L2  # D5: Kokoro → Piper at L2


@dataclass
class DegradationLadder:
    """Polls memory, publishes a level, and tells callers what they may still do."""

    free_probe: Callable[[], int] = mem_available_bytes
    core_rss_probe: Callable[[], int] = lambda: 0
    reserve_bytes: int = RESERVE_BYTES
    core_cap_bytes: int = CORE_CAP_BYTES
    poll_seconds: float = POLL_SECONDS
    clock: Callable[[], float] = time.monotonic

    state: LadderState = field(default_factory=LadderState)
    _last_poll: float = field(default=-1e9, init=False)
    transitions: list[tuple[Level, Level, str]] = field(default_factory=list, init=False)

    def free_envelope(self) -> int:
        return max(0, self.free_probe() - self.reserve_bytes)

    def evaluate(self) -> LadderState:
        """Recompute the level. Cheap enough to call per request; polls at most every 2 s."""
        now = self.clock()
        if now - self._last_poll < self.poll_seconds:
            return self.state
        self._last_poll = now

        free = self.free_envelope()
        core_rss = self.core_rss_probe()
        level, reason = self._classify(free, core_rss)

        if level != self.state.level:
            log.info("ladder %s → %s (%s)", self.state.level.name, level.name, reason)
            self.transitions.append((self.state.level, level, reason))
        self.state = LadderState(
            level=level,
            free_bytes=free,
            core_rss_bytes=core_rss,
            changed_at=now if level != self.state.level else self.state.changed_at,
            reason=reason,
        )
        return self.state

    def _classify(self, free: int, core_rss: int) -> tuple[Level, str]:
        if core_rss and core_rss > self.core_cap_bytes - L4_MARGIN_BYTES:
            return Level.L4, f"core RSS {core_rss / GiB:.2f} GiB is within 100 MiB of its cap"
        # Hysteresis applies only when recovering, so degradation is immediate and recovery
        # is deliberate — the expensive direction is the one to be slow about.
        bump = HYSTERESIS_BYTES if self.state.level > Level.L0 else 0
        if free < L3_THRESHOLD:
            return Level.L3, f"free envelope {free / GiB:.2f} GiB"
        if free < L2_THRESHOLD + (bump if self.state.level >= Level.L2 else 0):
            return Level.L2, f"free envelope {free / GiB:.2f} GiB"
        if free < L1_THRESHOLD + (bump if self.state.level >= Level.L1 else 0):
            return Level.L1, f"free envelope {free / GiB:.2f} GiB"
        return Level.L0, "healthy"

    # --- what callers ask --------------------------------------------------------------
    def may_spawn_vision(self) -> bool:
        return self.evaluate().vision_allowed

    def may_start_session(self) -> bool:
        return self.evaluate().accepts_new_sessions

    def context_for_new_session(self, default: int = 4096) -> int:
        return self.evaluate().context_for_new_session(default)

    def busy_message(self) -> str:
        """What a student sees at L3. Not an error: a queue with a reason (C-7)."""
        return (
            "A lot of students are working right now, so I'm pausing new sessions for a "
            "moment. Keep your question ready — I'll be with you shortly."
        )
