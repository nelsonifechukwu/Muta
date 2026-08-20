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


def test_registry_never_exposes_another_students_job():
    manager = GenerationManager()
    private = manager.start(
        student_id="ada",
        conversation_id="conv-2",
        producer=iter(['data: {"done": true}\n\n']),
    )
    assert manager.get(private.id, student_id="bimpe") is None


def test_capacity_and_single_chat_policy_are_reserved_atomically():
    manager = GenerationManager(max_active=2)
    first = manager.reserve("ada", allow_parallel=True, conversation_id="algebra")
    with pytest.raises(GenerationCapacityError, match="conversation"):
        manager.reserve("ada", allow_parallel=True, conversation_id="algebra")
    with pytest.raises(GenerationCapacityError, match="learner"):
        manager.reserve("ada", allow_parallel=False, conversation_id="geometry")

    second = manager.reserve("bimpe", allow_parallel=True, conversation_id="physics")
    with pytest.raises(GenerationCapacityError, match="slots"):
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
