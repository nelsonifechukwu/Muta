"""Adversarial lifecycle tests for server-owned, replayable generation jobs."""

from __future__ import annotations

import threading
import time

from orchestrator.gateway.generations import GenerationManager


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
    assert "job_id" in next(subscriber)
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
    assert len(all_frames) == 4  # registry metadata + two deltas + done
    assert list(job.subscribe(after=2)) == all_frames[2:]


def test_stop_is_cooperative_and_publishes_a_terminal_event():
    continue_engine = threading.Event()

    def producer():
        yield 'data: {"delta": "partial"}\n\n'
        assert continue_engine.wait(1.0)
        yield 'data: {"delta": "must not escape"}\n\n'

    job = GenerationManager().start(student_id="ada", conversation_id="conv-1", producer=producer())
    subscriber = job.subscribe()
    next(subscriber)  # metadata
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
