"""Admission control + degradation ladder tests (TDD §5.3, §8.2, T12, T14).

These two are tested together because they are one policy: how much work the box accepts
given how much memory it has. The failure they exist to prevent is the kernel deciding
instead — an OOM kill of the core server is a hard failure, not a slow score.
"""

from __future__ import annotations

import threading

import pytest

from orchestrator.gateway.ladder import DegradationLadder, GiB, Level
from orchestrator.gateway.sessions import (
    IDLE_STEAL_SECONDS,
    TURN_TOKEN_BUDGET,
    Admission,
    SessionManager,
)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# --- ladder -------------------------------------------------------------------------------


def ladder_at(free_gib: float, *, core_rss_gib: float = 0.0, state=None) -> DegradationLadder:
    ladder = DegradationLadder(
        free_probe=lambda: int(free_gib * GiB),
        core_rss_probe=lambda: int(core_rss_gib * GiB),
        reserve_bytes=0,
        poll_seconds=0.0,
    )
    if state is not None:
        ladder.state = state
    return ladder


@pytest.mark.parametrize(
    "free_gib,expected",
    [(4.0, Level.L0), (1.5, Level.L0), (1.0, Level.L1), (0.7, Level.L2), (0.4, Level.L3)],
)
def test_levels_follow_the_free_envelope(free_gib, expected):
    assert ladder_at(free_gib).evaluate().level is expected


def test_l4_fires_on_core_rss_regardless_of_free_memory():
    """The core server approaching its own cgroup cap is the dangerous case: plenty of free
    RAM on the box does not help a process about to be killed by its own limit."""
    state = ladder_at(4.0, core_rss_gib=4.25).evaluate()
    assert state.level is Level.L4 and "within 100 MiB" in state.reason


def test_the_reserve_floor_is_subtracted_from_available():
    ladder = DegradationLadder(free_probe=lambda: int(1.3 * GiB), poll_seconds=0.0)
    # 1.3 GiB available − 300 MiB floor ≈ 1.0 GiB envelope → L1, not L0.
    assert ladder.evaluate().level is Level.L1


@pytest.mark.parametrize(
    "level,vision,tts,new_sessions,ctx",
    [
        (Level.L0, True, True, True, 4096),
        (Level.L1, False, True, True, 4096),
        (Level.L2, False, True, True, 2048),
        (Level.L3, False, False, False, 2048),
    ],
)
def test_each_level_gives_up_exactly_what_the_tdd_says(level, vision, tts, new_sessions, ctx):
    from orchestrator.gateway.ladder import LadderState

    state = LadderState(level=level)
    assert state.vision_allowed is vision
    assert state.tts_allowed is tts
    assert state.accepts_new_sessions is new_sessions
    assert state.context_for_new_session() == ctx


def test_l2_swaps_premium_tts_for_piper():
    from orchestrator.gateway.ladder import LadderState

    assert LadderState(level=Level.L1).premium_tts_allowed is True
    assert LadderState(level=Level.L2).premium_tts_allowed is False  # D5


def test_l4_sheds_slots_by_admission_not_by_restarting_the_server():
    from orchestrator.gateway.ladder import LadderState

    assert LadderState(level=Level.L4).effective_slots(configured=6) == 4
    assert LadderState(level=Level.L0).effective_slots(configured=6) == 6


def test_the_ladder_walks_back_down_when_memory_returns():
    """T14's chaos test in miniature: balloon → L3 → release → L0. A ladder that only
    descends leaves the demo permanently degraded after one spike."""
    free = {"gib": 0.4}
    ladder = DegradationLadder(free_probe=lambda: int(free["gib"] * GiB), reserve_bytes=0, poll_seconds=0.0)
    assert ladder.evaluate().level is Level.L3
    free["gib"] = 4.0
    assert ladder.evaluate().level is Level.L0
    assert [(a.name, b.name) for a, b, _ in ladder.transitions] == [("L0", "L3"), ("L3", "L0")]


def test_recovery_has_hysteresis_so_the_level_does_not_flap():
    free = {"gib": 1.0}  # L1
    ladder = DegradationLadder(free_probe=lambda: int(free["gib"] * GiB), reserve_bytes=0, poll_seconds=0.0)
    assert ladder.evaluate().level is Level.L1
    free["gib"] = 1.25  # just over the L1 line, inside the hysteresis band
    assert ladder.evaluate().level is Level.L1, "recovery must be deliberate, degradation immediate"
    free["gib"] = 1.5
    assert ladder.evaluate().level is Level.L0


def test_polling_is_rate_limited():
    calls = {"n": 0}

    def probe() -> int:
        calls["n"] += 1
        return 4 * GiB

    clock = Clock()
    ladder = DegradationLadder(free_probe=probe, poll_seconds=2.0, clock=clock)
    for _ in range(10):
        ladder.evaluate()
    assert calls["n"] == 1
    clock.advance(2.5)
    ladder.evaluate()
    assert calls["n"] == 2


def test_unknown_memory_assumes_healthy_rather_than_degrading(monkeypatch):
    """A probe failure must not silently switch the demo into L3."""
    import orchestrator.gateway.ladder as ladder_mod

    monkeypatch.setattr(ladder_mod, "open", lambda *_a, **_k: (_ for _ in ()).throw(OSError()), raising=False)
    monkeypatch.setitem(__import__("sys").modules, "psutil", None)
    assert ladder_mod.mem_available_bytes() >= 4 * GiB


def test_status_dict_is_what_the_health_panel_renders():
    body = ladder_at(1.0).evaluate().as_dict()
    assert body["level"] == "L1" and body["vision_allowed"] is False
    assert body["free_gib"] == 1.0 and "reason" in body


# --- admission control --------------------------------------------------------------------


@pytest.fixture
def manager():
    clock = Clock()
    suspended: list[tuple[int, str]] = []
    resumed: list[tuple[int, str]] = []
    mgr = SessionManager(
        slots_count=2,
        clock=clock,
        suspend_hook=lambda index, session: suspended.append((index, session)),
        resume_hook=lambda index, session: resumed.append((index, session)) or True,
    )
    mgr.clock_obj, mgr.suspended_calls, mgr.resumed_calls = clock, suspended, resumed  # type: ignore[attr-defined]
    return mgr


def test_a_free_slot_is_bound(manager):
    decision = manager.acquire("ada")
    assert decision.admission is Admission.BOUND and decision.slot.index == 0


def test_the_same_session_keeps_its_slot(manager):
    first = manager.acquire("ada")
    manager.release("ada")
    second = manager.acquire("ada")
    assert second.slot is first.slot and manager.stats["reused"] == 1


def test_a_third_student_queues_with_a_position(manager):
    manager.acquire("ada")
    manager.acquire("bimpe")
    decision = manager.acquire("chidi")
    assert decision.admission is Admission.QUEUED and decision.queue_position == 1
    assert "one moment" in decision.message.lower()

    fourth = manager.acquire("dami")
    assert fourth.queue_position == 2 and "1 student ahead" in fourth.message

    manager.release("chidi")
    assert "chidi" not in manager.queue
    assert manager.acquire("dami").queue_position == 1


def test_generation_admission_is_an_ephemeral_physical_lane_lease():
    manager = SessionManager(slots_count=1)
    first = manager.acquire("generation:first")
    assert first.admitted and first.slot is not None

    manager.release("generation:first")
    assert first.slot.free and first.slot.busy is False

    second = manager.acquire("generation:second")
    assert second.admitted and second.slot is first.slot


def test_concurrent_acquire_cannot_bind_one_physical_slot_twice():
    manager = SessionManager(slots_count=1)
    barrier = threading.Barrier(3)
    decisions = []

    def acquire(name: str) -> None:
        barrier.wait()
        decisions.append(manager.acquire(name))

    workers = [threading.Thread(target=acquire, args=(name,)) for name in ("ada", "bimpe")]
    for worker in workers:
        worker.start()
    barrier.wait()
    for worker in workers:
        worker.join(timeout=1.0)

    assert sorted(decision.admission for decision in decisions) == [
        Admission.BOUND,
        Admission.QUEUED,
    ]
    assert sum(slot.busy for slot in manager.slots) == 1


def test_an_idle_slot_is_taken_over_and_its_session_suspended(manager):
    """This is the 30-students-on-6-slots mechanism: the idle session's KV goes to disk and
    comes back on a restore, instead of being re-prefilled from scratch."""
    manager.acquire("ada")
    manager.release("ada")
    manager.acquire("bimpe")
    manager.release("bimpe")
    manager.clock_obj.advance(IDLE_STEAL_SECONDS + 1)

    decision = manager.acquire("chidi")
    assert decision.admitted
    assert decision.suspended_session in {"ada", "bimpe"}
    assert manager.suspended_calls, "the victim's KV must be saved before the slot is reused"


def test_a_busy_slot_is_never_stolen(manager):
    manager.acquire("ada")  # busy: request in flight
    manager.acquire("bimpe")
    manager.clock_obj.advance(IDLE_STEAL_SECONDS * 10)
    assert manager.acquire("chidi").admission is Admission.QUEUED


def test_a_suspended_session_is_restored_when_it_returns():
    clock = Clock()
    resumed: list[tuple[int, str]] = []
    mgr = SessionManager(
        slots_count=1,  # one lane, so the second student must displace the first
        clock=clock,
        suspend_hook=lambda *_a: None,
        resume_hook=lambda index, session: bool(resumed.append((index, session)) or True),
    )
    mgr.acquire("ada")
    mgr.release("ada")
    clock.advance(IDLE_STEAL_SECONDS + 1)
    mgr.acquire("bimpe")  # takes ada's slot; ada is suspended to disk
    mgr.release("bimpe")
    clock.advance(IDLE_STEAL_SECONDS + 1)

    decision = mgr.acquire("ada")
    assert decision.admission is Admission.RESUMED
    assert resumed[-1][1] == "ada", "the snapshot must be restored into the slot it lands in"


def test_a_restore_miss_still_binds_the_slot():
    """Restore-miss falls back to a summary re-prefill (§8.3) — the student waits a beat,
    they do not lose the session."""
    clock = Clock()
    mgr = SessionManager(
        slots_count=1,
        clock=clock,
        suspend_hook=lambda *_a: None,
        resume_hook=lambda *_a: False,  # snapshot evicted or corrupt
    )
    mgr.acquire("ada")
    mgr.release("ada")
    clock.advance(IDLE_STEAL_SECONDS + 1)
    mgr.acquire("bimpe")
    mgr.release("bimpe")
    clock.advance(IDLE_STEAL_SECONDS + 1)

    decision = mgr.acquire("ada")
    assert decision.admission is Admission.BOUND and decision.slot is not None


def test_a_failing_suspend_hook_does_not_block_the_waiting_student():
    """Disk full (S12): the save fails, so that session re-prefills later — but the student
    who needs the slot right now still gets it."""
    clock = Clock()

    def explode(*_a):
        raise OSError("No space left on device")

    mgr = SessionManager(slots_count=1, clock=clock, suspend_hook=explode)
    mgr.acquire("ada")
    mgr.release("ada")
    clock.advance(IDLE_STEAL_SECONDS + 1)
    assert mgr.acquire("bimpe").admitted


def test_l3_refuses_new_sessions_with_a_human_message(manager):
    manager.accepts_new_sessions = lambda: False
    manager.acquire("ada")
    manager.acquire("bimpe")
    decision = manager.acquire("chidi")
    assert decision.admission is Admission.REFUSED
    assert "capacity" in decision.message and "try again" in decision.message


def test_l3_refuses_a_new_session_even_when_a_physical_slot_is_free():
    manager = SessionManager(slots_count=1, accepts_new_sessions=lambda: False)
    decision = manager.acquire("brand-new")
    assert decision.admission is Admission.REFUSED
    assert manager.slots[0].free


def test_l4_narrows_the_usable_slot_pool():
    mgr = SessionManager(slots_count=6, effective_slots=lambda: 4)
    for name in ("a", "b", "c", "d"):
        assert mgr.acquire(name).admitted
    assert mgr.acquire("e").admission is Admission.QUEUED, "slots 5 and 6 are shed at L4"


def test_suspend_idle_reclaims_every_quiet_slot(manager):
    manager.acquire("ada")
    manager.release("ada")
    manager.acquire("bimpe")  # still busy
    manager.clock_obj.advance(IDLE_STEAL_SECONDS + 1)

    assert manager.suspend_idle() == ["ada"]
    assert manager.slot_for("ada") is None and manager.slot_for("bimpe") is not None


def test_status_reports_what_the_operator_needs(manager):
    manager.acquire("ada")
    status = manager.status()
    assert status["slots"][0]["session"] == "ada" and status["slots"][0]["busy"] is True
    assert status["usable_slots"] == 2


def test_the_fairness_budget_is_the_tdd_number():
    assert SessionManager().token_budget == TURN_TOKEN_BUDGET == 1200
