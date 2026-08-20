"""Adversarial lifecycle tests for server-owned, replayable generation jobs."""

from __future__ import annotations

import threading
import time

import pytest

from orchestrator.gateway.generations import GenerationCapacityError, GenerationManager


def _wait_finished(job, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while job.snapshot().state == "running" and time.monotonic() < deadline:
        time.sleep(0.005)
    assert job.snapshot().state != "running", "generation worker did not finish"


def test_disconnecting_a_subscriber_does_not_stop_the_generation():
    continue_engine = threading.Event()
    producer_closed = threading.Event()

    def producer():
        try:
            yield 'data: {"delta": "first"}\n\n'
            assert continue_engine.wait(1.0)
            yield 'data: {"delta": " second"}\n\n'
            yield 'data: {"done": true}\n\n'
        finally:
            producer_closed.set()

    manager = GenerationManager()
    job = manager.start(student_id="ada", conversation_id="conv-1", producer=producer())

    subscriber = job.subscribe()
    assert "first" in next(subscriber)
    subscriber.close()  # browser refresh / navigation

    assert job.snapshot().state == "running"
    continue_engine.set()
    _wait_finished(job)
    assert producer_closed.is_set()

    replay = list(job.subscribe())
    assert any("first" in frame for frame in replay)
    assert any("second" in frame for frame in replay)
    assert any('"done": true' in frame for frame in replay)


def test_frame_offset_replays_only_events_the_client_has_not_seen():
    def producer():
        yield 'data: {"delta": "a"}\n\n'
        yield 'data: {"delta": "b"}\n\n'
        yield 'data: {"done": true}\n\n'

    job = GenerationManager().start(student_id="ada", conversation_id="conv-1", producer=producer())
    _wait_finished(job)
    all_frames = list(job.subscribe())
    assert len(all_frames) == 3  # two deltas + done
    assert list(job.subscribe(after=2)) == all_frames[2:]


def test_stop_is_cooperative_and_publishes_a_terminal_event():
    continue_engine = threading.Event()

    def producer():
        yield 'data: {"delta": "partial"}\n\n'
        assert continue_engine.wait(1.0)
        yield 'data: {"delta": "must not escape"}\n\n'

    job = GenerationManager().start(student_id="ada", conversation_id="conv-1", producer=producer())
    subscriber = job.subscribe()
    assert "partial" in next(subscriber)

    assert job.request_stop() is True
    continue_engine.set()
    remaining = list(subscriber)
    _wait_finished(job)

    assert job.snapshot().state == "stopped"
    assert not any("must not escape" in frame for frame in remaining)
    assert any('"stopped": true' in frame and '"done": true' in frame for frame in remaining)
    assert job.request_stop() is False


def test_stop_signals_the_producers_interruptible_retry_wait():
    cancel = threading.Event()

    def producer():
        yield 'data: {"recovering": "resuming"}\n\n'
        assert cancel.wait(1.0)

    job = GenerationManager().start(
        student_id="ada",
        conversation_id="conv-retry",
        producer=producer(),
        cancel_event=cancel,
    )
    subscriber = job.subscribe()
    assert "recovering" in next(subscriber)

    assert job.request_stop() is True
    assert cancel.wait(0.1)
    _wait_finished(job)
    assert job.snapshot().state == "stopped"


def test_registry_never_exposes_another_students_job():
    manager = GenerationManager()
    private = manager.start(
        student_id="ada",
        conversation_id="conv-2",
        producer=iter(['data: {"done": true}\n\n']),
    )
    assert manager.get(private.id, student_id="bimpe") is None


def test_capacity_and_single_chat_policy_are_reserved_atomically():
    manager = GenerationManager(max_active=2, max_queued=0)
    first = manager.reserve("ada", allow_parallel=True, conversation_id="algebra")
    with pytest.raises(GenerationCapacityError, match="conversation"):
        manager.reserve("ada", allow_parallel=True, conversation_id="algebra")
    with pytest.raises(GenerationCapacityError, match="learner"):
        manager.reserve("ada", allow_parallel=False, conversation_id="geometry")

    second = manager.reserve("bimpe", allow_parallel=True, conversation_id="physics")
    with pytest.raises(GenerationCapacityError, match="queue is full"):
        manager.reserve("chidi", allow_parallel=True, conversation_id="chemistry")
    manager.cancel_reservation(first)
    manager.cancel_reservation(second)


def test_model_transition_and_generation_admission_share_one_lock():
    manager = GenerationManager(max_active=2)
    reservation = manager.reserve("ada", allow_parallel=True)
    with pytest.raises(GenerationCapacityError, match="active replies"):
        manager.run_when_idle(lambda: "switched")
    manager.cancel_reservation(reservation)
    assert manager.run_when_idle(lambda: "switched") == "switched"


def test_client_request_id_finds_a_completed_replay_after_refresh():
    manager = GenerationManager()
    job = manager.start(
        student_id="ada",
        conversation_id="conv-refresh",
        client_request_id="browser-request-1",
        producer=iter(['data: {"done": true}\n\n']),
    )
    _wait_finished(job)
    assert manager.matching("ada", "browser-request-1")[0].job_id == job.id
    assert manager.matching("bimpe", "browser-request-1") == []


def test_busy_generation_is_queued_then_promoted_without_resubmitting():
    first_can_finish = threading.Event()
    queued_can_finish = threading.Event()

    def first_producer():
        yield 'data: {"delta": "first"}\n\n'
        assert first_can_finish.wait(1.0)
        yield 'data: {"done": true}\n\n'

    def queued_producer():
        yield 'data: {"delta": "second"}\n\n'
        assert queued_can_finish.wait(1.0)
        yield 'data: {"done": true}\n\n'

    manager = GenerationManager(max_active=1, max_queued=2)
    first = manager.start(student_id="ada", conversation_id="one", producer=first_producer())
    queued = manager.start(student_id="ada", conversation_id="two", producer=queued_producer())

    snapshot = queued.snapshot()
    assert snapshot.state == "queued" and snapshot.queue_position == 1
    assert [row.job_id for row in manager.active("ada")] == [first.id, queued.id]
    subscription = queued.subscribe()
    assert '"queued": true' in next(subscription) and '"queue_position": 1' in queued._events[0]

    first_can_finish.set()
    deadline = time.monotonic() + 1.0
    while queued.snapshot().state == "queued" and time.monotonic() < deadline:
        time.sleep(0.005)
    assert queued.snapshot().state == "running"
    assert '"started": true' in next(subscription)
    assert '"second"' in next(subscription)

    queued_can_finish.set()
    _wait_finished(first)
    _wait_finished(queued)


def test_stopping_a_queued_job_removes_it_and_advances_the_next_position():
    running_gate = threading.Event()
    last_gate = threading.Event()
    cleaned = threading.Event()

    def blocked(gate: threading.Event):
        yield 'data: {"delta": "working"}\n\n'
        assert gate.wait(1.0)
        yield 'data: {"done": true}\n\n'

    manager = GenerationManager(max_active=1, max_queued=2)
    running = manager.start(student_id="ada", conversation_id="one", producer=blocked(running_gate))
    cancelled = manager.start(
        student_id="ada",
        conversation_id="two",
        producer=iter(['data: {"done": true}\n\n']),
        queued_cleanup=cleaned.set,
    )
    last = manager.start(student_id="ada", conversation_id="three", producer=blocked(last_gate))
    assert cancelled.snapshot().queue_position == 1
    assert last.snapshot().queue_position == 2

    assert cancelled.request_stop() is True
    assert cancelled.snapshot().state == "stopped"
    assert cleaned.is_set()
    assert last.snapshot().queue_position == 1
    assert any('"queue_position": 1' in frame for frame in last._events)

    running_gate.set()
    deadline = time.monotonic() + 1.0
    while last.snapshot().state == "queued" and time.monotonic() < deadline:
        time.sleep(0.005)
    assert last.snapshot().state == "running"
    last_gate.set()
    _wait_finished(running)
    _wait_finished(last)


def test_queue_has_an_independent_hard_bound():
    manager = GenerationManager(max_active=1, max_queued=1)
    active = manager.reserve("ada", allow_parallel=True, conversation_id="one")
    queued = manager.reserve("bimpe", allow_parallel=True, conversation_id="two")
    with pytest.raises(GenerationCapacityError, match="queue is full"):
        manager.reserve("chidi", allow_parallel=True, conversation_id="three")
    manager.cancel_reservation(active)
    manager.cancel_reservation(queued)


def test_promotion_waits_until_the_physical_session_lane_can_be_bound():
    first_gate = threading.Event()
    lane_available = threading.Event()

    def blocked():
        yield 'data: {"delta": "working"}\n\n'
        assert first_gate.wait(1.0)
        yield 'data: {"done": true}\n\n'

    manager = GenerationManager(max_active=1, max_queued=1)
    first = manager.start(student_id="ada", conversation_id="one", producer=blocked())
    queued = manager.start(
        student_id="ada",
        conversation_id="two",
        producer=iter(['data: {"done": true}\n\n']),
        before_start=lane_available.is_set,
    )

    first_gate.set()
    _wait_finished(first)
    assert queued.snapshot().state == "queued"

    lane_available.set()
    # A later terminal transition retries the FIFO head; model transitions cannot overtake it.
    trigger = manager.start(
        student_id="ada",
        conversation_id="three",
        producer=iter(['data: {"done": true}\n\n']),
    )
    _wait_finished(queued)
    _wait_finished(trigger)


def test_post_acceptance_admission_refusal_fails_in_band_and_advances_fifo():
    mode = {"value": "wait"}
    cleaned = threading.Event()

    def claim_head() -> bool:
        if mode["value"] == "refuse":
            raise RuntimeError("memory pressure — try again shortly")
        return False

    manager = GenerationManager(max_active=1, max_queued=2)
    refused = manager.start(
        student_id="ada",
        conversation_id="one",
        producer=iter(['data: {"done": true}\n\n']),
        queued_cleanup=cleaned.set,
        before_start=claim_head,
    )
    next_job = manager.start(
        student_id="ada",
        conversation_id="two",
        producer=iter(['data: {"done": true}\n\n']),
    )
    assert refused.snapshot().state == "queued"
    assert next_job.snapshot().state == "queued"

    mode["value"] = "refuse"
    deadline = time.monotonic() + 1.0
    while manager.active("ada") and time.monotonic() < deadline:
        time.sleep(0.005)

    assert refused.snapshot().state == "failed"
    assert next_job.snapshot().state == "completed"
    assert cleaned.is_set()
    assert manager.active("ada") == []
    assert manager._queue == []
    assert any('"error": "memory pressure' in frame for frame in refused._events)
    assert any('"done": true' in frame and '"failed": true' in frame for frame in refused._events)


def test_shutdown_rejects_new_reservations_and_starts():
    manager = GenerationManager(max_active=1)
    manager.shutdown()
    with pytest.raises(GenerationCapacityError, match="shutting down"):
        manager.reserve("ada", allow_parallel=True, conversation_id="one")
