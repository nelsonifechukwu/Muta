"""Sessions, slots and admission control (TDD §8, T12).

A **session** is a student's persistent state (twin + optionally a saved KV snapshot). A
**slot** is a live decode lane in CORE-TEXT. Sessions outnumber slots by design: 30 phones,
6 slots.

Admission, for a request from session S (§8.2):

1. S already holds a slot → queue on it;
2. a free slot exists → bind;
3. an idle-bound slot exists (nothing in flight, idle > 20 s) → suspend that session, bind S;
4. otherwise → queue, and tell the student how many are ahead.

Fairness is a per-turn output-token budget rather than a time slice: tutor answers are short,
and the failure mode worth preventing is one student's 3000-token essay holding a lane while
five wait for a hint.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

log = logging.getLogger("muta.gateway.sessions")

#: §8.2 — a bound slot with nothing in flight for this long may be taken.
IDLE_STEAL_SECONDS = 20.0
#: §8.2 — per-session output-token budget per turn.
TURN_TOKEN_BUDGET = 1200


class Admission(str, Enum):
    BOUND = "bound"  # got a slot (fresh or reused)
    RESUMED = "resumed"  # got a slot and a snapshot was restored into it
    QUEUED = "queued"  # no slot; position reported
    REFUSED = "refused"  # ladder L3: not accepting new sessions right now


@dataclass
class Slot:
    index: int
    session_id: str | None = None
    busy: bool = False
    last_activity: float = 0.0

    @property
    def free(self) -> bool:
        return self.session_id is None

    def idle_seconds(self, now: float) -> float:
        return now - self.last_activity


@dataclass
class Decision:
    admission: Admission
    slot: Slot | None = None
    queue_position: int = 0
    suspended_session: str | None = None
    message: str = ""

    @property
    def admitted(self) -> bool:
        return self.admission in (Admission.BOUND, Admission.RESUMED)


@dataclass
class SessionManager:
    """Slot bookkeeping and the §8.2 policy. Knows nothing about HTTP or llama-server: the
    suspend/resume hooks are injected, so the policy is testable without either."""

    slots_count: int = 6
    idle_steal_seconds: float = IDLE_STEAL_SECONDS
    token_budget: int = TURN_TOKEN_BUDGET
    clock: Callable[[], float] = time.monotonic
    #: Injected side effects: persist/restore a session's KV (runtime.slots.SlotClient).
    suspend_hook: Callable[[int, str], None] | None = None
    resume_hook: Callable[[int, str], bool] | None = None
    #: Ladder view: how many slots may be used right now, and whether to accept new sessions.
    effective_slots: Callable[[], int] | None = None
    accepts_new_sessions: Callable[[], bool] = lambda: True

    slots: list[Slot] = field(init=False)
    queue: list[str] = field(default_factory=list, init=False)
    suspended: set[str] = field(default_factory=set, init=False)
    stats: dict[str, int] = field(default_factory=dict, init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def __post_init__(self) -> None:
        self.slots = [Slot(index=i) for i in range(self.slots_count)]

    # --- helpers ----------------------------------------------------------------------
    def _usable(self) -> list[Slot]:
        limit = self.effective_slots() if self.effective_slots else self.slots_count
        return self.slots[: max(1, min(limit, self.slots_count))]

    def _count(self, key: str) -> None:
        self.stats[key] = self.stats.get(key, 0) + 1

    def slot_for(self, session_id: str) -> Slot | None:
        with self._lock:
            return next((s for s in self.slots if s.session_id == session_id), None)

    # --- admission --------------------------------------------------------------------
    def acquire(self, session_id: str) -> Decision:
        with self._lock:
            return self._acquire_locked(session_id)

    def _acquire_locked(self, session_id: str) -> Decision:
        now = self.clock()
        usable = self._usable()

        held = self.slot_for(session_id)
        if held is not None and held in usable:
            held.busy = True
            held.last_activity = now
            self._count("reused")
            return Decision(Admission.BOUND, slot=held)

        # L3 is a fail-closed admission wall for any session that does not already own a
        # usable lane. Check before binding a currently-free slot or stealing an idle one;
        # otherwise the first new learner after an emergency would slip straight through.
        if not self.accepts_new_sessions():
            self._count("refused")
            return Decision(
                Admission.REFUSED,
                message="I'm at capacity for a moment — keep your question ready and try again shortly.",
            )

        free = next((s for s in usable if s.free), None)
        if free is not None:
            return self._bind(free, session_id, now)

        stealable = [
            s for s in usable if not s.busy and s.idle_seconds(now) > self.idle_steal_seconds
        ]
        if stealable:
            victim = max(stealable, key=lambda s: s.idle_seconds(now))  # the longest-idle one
            evicted = victim.session_id
            self._suspend(victim)
            decision = self._bind(victim, session_id, now)
            decision.suspended_session = evicted
            return decision

        if session_id not in self.queue:
            self.queue.append(session_id)
        position = self.queue.index(session_id) + 1
        self._count("queued")
        return Decision(
            Admission.QUEUED,
            queue_position=position,
            message=_queue_message(position),
        )

    def _bind(self, slot: Slot, session_id: str, now: float) -> Decision:
        slot.session_id = session_id
        slot.busy = True
        slot.last_activity = now
        if session_id in self.queue:
            self.queue.remove(session_id)

        if session_id in self.suspended and self.resume_hook is not None:
            restored = False
            try:
                restored = bool(self.resume_hook(slot.index, session_id))
            except Exception as e:  # noqa: BLE001 — a restore miss is a re-prefill, not an error
                log.warning(
                    "resume failed for %s (%s) — falling back to summary re-prefill", session_id, e
                )
            self.suspended.discard(session_id)
            if restored:
                self._count("resumed")
                return Decision(Admission.RESUMED, slot=slot)
        self._count("bound")
        return Decision(Admission.BOUND, slot=slot)

    def _suspend(self, slot: Slot) -> None:
        session_id = slot.session_id
        if session_id is None:
            return
        if self.suspend_hook is not None:
            try:
                self.suspend_hook(slot.index, session_id)
                self.suspended.add(session_id)
            except Exception as e:  # noqa: BLE001
                # A failed save (disk full, §S12) costs a re-prefill later; it must not stop
                # the student who is waiting for the slot now.
                log.warning("suspend failed for %s (%s) — session will re-prefill", session_id, e)
        slot.session_id = None
        slot.busy = False
        self._count("suspended")

    def release(self, session_id: str) -> None:
        """Turn finished: the slot stays bound (so the next turn is free) but is idle."""
        with self._lock:
            if session_id in self.queue:
                self.queue.remove(session_id)
            slot = self.slot_for(session_id)
            if slot is not None:
                if session_id.startswith("generation:"):
                    # Durable chat jobs use one lease per reply, not a reusable learner/KV
                    # session. Free it outright so GenerationManager can bind the FIFO head to
                    # the same physical lane before promotion.
                    slot.session_id = None
                    slot.busy = False
                    slot.last_activity = 0.0
                else:
                    slot.busy = False
                    slot.last_activity = self.clock()

    def evict(self, session_id: str) -> bool:
        """Explicit suspend — the ladder does this at L3 to reclaim idle slots."""
        with self._lock:
            slot = self.slot_for(session_id)
            if slot is None:
                return False
            self._suspend(slot)
            return True

    def suspend_idle(self, *, older_than: float | None = None) -> list[str]:
        """L3 action: suspend every idle bound session, newest last."""
        with self._lock:
            threshold = self.idle_steal_seconds if older_than is None else older_than
            now = self.clock()
            victims = [
                s
                for s in self.slots
                if not s.free and not s.busy and s.idle_seconds(now) >= threshold
            ]
            names = [s.session_id for s in victims if s.session_id]
            for slot in victims:
                self._suspend(slot)
            return names

    # --- reporting ---------------------------------------------------------------------
    def status(self) -> dict:
        with self._lock:
            now = self.clock()
            return {
                "slots": [
                    {
                        "index": s.index,
                        "session": s.session_id,
                        "busy": s.busy,
                        "idle_seconds": round(s.idle_seconds(now), 1) if not s.free else None,
                    }
                    for s in self.slots
                ],
                "usable_slots": len(self._usable()),
                "queue": list(self.queue),
                "suspended": sorted(self.suspended),
                "stats": dict(self.stats),
            }


def _queue_message(position: int) -> str:
    if position == 1:
        return "You're next — one moment."
    return f"{position - 1} student{'s' if position > 2 else ''} ahead of you — hold on a moment."
