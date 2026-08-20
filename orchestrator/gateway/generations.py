"""Server-owned chat generations with replayable SSE subscriptions.

The browser is a subscriber, not the owner of inference. A page refresh, a conversation
switch, or a dropped TCP connection may close one subscriber, but the worker keeps consuming
the engine iterator so ChatEngine can write the answer through to durable conversation
memory. Jobs are intentionally process-local: persisted messages remain authoritative, while
this registry only bridges short-lived browser reconnects to a live gateway process.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone

log = logging.getLogger("muta.gateway.generations")

_DONE_MARKER = '"done": true'
_ERROR_MARKER = '"error"'
_TERMINAL_STATES = frozenset({"completed", "failed", "stopped"})


class GenerationCapacityError(RuntimeError):
    """The fixed engine-slot budget or per-learner parallel policy rejected a new job."""


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@dataclass(frozen=True)
class GenerationSnapshot:
    job_id: str
    student_id: str
    conversation_id: str
    state: str
    created_at: str
    client_request_id: str | None = None
    queue_position: int = 0


@dataclass(frozen=True)
class _Reservation:
    student_id: str
    conversation_id: str | None
    client_request_id: str | None
    created_at: float


class GenerationJob:
    """One engine iterator consumed by one worker and replayed to many subscribers."""

    def __init__(
        self,
        *,
        student_id: str,
        conversation_id: str,
        producer: Iterator[str],
        job_id: str | None = None,
        client_request_id: str | None = None,
        on_terminal: Callable[[GenerationJob], None] | None = None,
        queued_cleanup: Callable[[], None] | None = None,
        before_start: Callable[[], bool] | None = None,
    ) -> None:
        self.id = job_id or uuid.uuid4().hex
        self.student_id = student_id
        self.conversation_id = conversation_id
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.client_request_id = client_request_id
        self.completed_at: float | None = None
        self.state = "queued"
        self._producer = producer
        self._on_terminal = on_terminal
        self._queued_cleanup = queued_cleanup
        self._before_start = before_start
        self._condition = threading.Condition()
        # The producer's leading conversation-id frame remains byte-compatible with the
        # original /chat/stream contract. New job clients already receive both ids from the
        # JSON start response, so injecting registry metadata here would duplicate that frame.
        self._events: list[str] = []
        self._stop_requested = False
        self._queue_position = 0
        self.was_queued = False
        self._thread = threading.Thread(
            target=self._run,
            name=f"muta-generation-{self.id[:8]}",
            daemon=True,
        )

    def start(self) -> bool:
        with self._condition:
            if self.state != "queued":
                return False
            # SessionManager and GenerationManager must agree on the same physical lane.
            # Run this while the queued state lock is held so Stop cannot race a successful
            # admission and leave a newly-bound session slot behind.
            if self._before_start is not None and not self._before_start():
                return False
            self.state = "running"
            self._queue_position = 0
            if self.was_queued:
                self._events.append(
                    _sse(
                        {
                            "job_id": self.id,
                            "conversation_id": self.conversation_id,
                            "queued": False,
                            "started": True,
                        }
                    )
                )
            self._condition.notify_all()
        try:
            self._thread.start()
        except Exception:
            with self._condition:
                self.state = "failed"
                self.completed_at = time.monotonic()
                cleanup = self._queued_cleanup
                self._queued_cleanup = None
                self._condition.notify_all()
            if cleanup is not None:
                cleanup()
            raise
        with self._condition:
            # Once the worker exists, the producer's own finally owns cleanup. Drop the
            # queued-only closure so the retained replay job does not pin request objects.
            self._queued_cleanup = None
        return True

    def set_queue_position(self, position: int) -> None:
        with self._condition:
            if self.state != "queued" or self._queue_position == position:
                return
            self._queue_position = position
            self.was_queued = True
            self._events.append(
                _sse(
                    {
                        "job_id": self.id,
                        "conversation_id": self.conversation_id,
                        "queued": True,
                        "queue_position": position,
                    }
                )
            )
            self._condition.notify_all()

    def reject_queued(self, message: str) -> bool:
        """Terminalize a job whose physical admission was refused after HTTP 202.

        The start endpoint can return a normal HTTP error only while it is still synchronous.
        Once the browser owns a queued job id, refusal must travel through that job's replay
        stream and release its unopened producer exactly once.
        """
        with self._condition:
            if self.state != "queued":
                return False
            self._events.extend(
                [
                    _sse(
                        {
                            "job_id": self.id,
                            "conversation_id": self.conversation_id,
                            "error": message,
                        }
                    ),
                    _sse(
                        {
                            "done": True,
                            "failed": True,
                            "job_id": self.id,
                            "conversation_id": self.conversation_id,
                        }
                    ),
                ]
            )
            self.state = "failed"
            self.completed_at = time.monotonic()
            cleanup = self._queued_cleanup
            self._queued_cleanup = None
            self._condition.notify_all()
        if cleanup is not None:
            try:
                cleanup()
            except Exception:
                log.exception("refused generation job %s cleanup failed", self.id)
        return True

    def snapshot(self) -> GenerationSnapshot:
        with self._condition:
            state = self.state
        return GenerationSnapshot(
            job_id=self.id,
            student_id=self.student_id,
            conversation_id=self.conversation_id,
            state=state,
            created_at=self.created_at,
            client_request_id=self.client_request_id,
            queue_position=self._queue_position,
        )

    def request_stop(self) -> bool:
        """Request cooperative cancellation. The worker closes the producer on its own thread.

        Closing a generator from the request thread while it is blocked inside ``next()`` can
        raise ``generator already executing`` and leak an inference slot. Waiting until the
        next engine event keeps ownership and cleanup on the worker that consumes it.
        """
        with self._condition:
            if self.state not in {"queued", "running"}:
                return False
            self._stop_requested = True
            if self.state == "queued":
                self._events.append(
                    _sse(
                        {
                            "done": True,
                            "stopped": True,
                            "job_id": self.id,
                            "conversation_id": self.conversation_id,
                        }
                    )
                )
                self.state = "stopped"
                self.completed_at = time.monotonic()
                queued_cleanup = self._queued_cleanup
                self._queued_cleanup = None
            else:
                queued_cleanup = None
            self._condition.notify_all()
            queued_stop = self.state == "stopped"
        if queued_stop and self._on_terminal is not None:
            if queued_cleanup is not None:
                try:
                    queued_cleanup()
                except Exception:  # a cancelled job must still leave the queue
                    log.exception("queued generation job %s cleanup failed", self.id)
            self._on_terminal(self)
        return True

    def subscribe(self, after: int = 0) -> Iterator[str]:
        """Replay frames from ``after`` and then tail the job until it reaches a terminal state.

        ``after`` is the number of frames a client has already processed. A short SSE comment
        keeps otherwise-quiet subscriptions observable by disconnect detection without adding
        an application event to the replay count.
        """
        cursor = max(0, after)
        while True:
            frame: str | None = None
            with self._condition:
                if cursor < len(self._events):
                    frame = self._events[cursor]
                    cursor += 1
                elif self.state in _TERMINAL_STATES:
                    return
                else:
                    self._condition.wait(timeout=10.0)
                    if cursor >= len(self._events) and self.state not in _TERMINAL_STATES:
                        frame = ": keep-alive\n\n"
            if frame is not None:
                yield frame

    def _publish(self, frame: str) -> None:
        with self._condition:
            self._events.append(frame)
            self._condition.notify_all()

    def _run(self) -> None:
        terminal_seen = False
        failed = False
        try:
            for frame in self._producer:
                with self._condition:
                    should_stop = self._stop_requested
                if should_stop:
                    break
                terminal_seen = terminal_seen or _DONE_MARKER in frame
                failed = failed or _ERROR_MARKER in frame
                self._publish(frame)
        except Exception:  # protect persistence/slot cleanup at this thread boundary
            failed = True
            log.exception("generation job %s failed", self.id)
            self._publish(
                _sse(
                    {
                        "job_id": self.id,
                        "conversation_id": self.conversation_id,
                        "error": "the tutor dropped the connection — try again",
                    }
                )
            )
        finally:
            close = getattr(self._producer, "close", None)
            if close is not None:
                try:
                    close()
                except Exception:  # cleanup failure must still wake subscribers
                    failed = True
                    log.exception("generation job %s could not close its producer", self.id)

            with self._condition:
                stopped = self._stop_requested
            if stopped and not terminal_seen:
                self._publish(
                    _sse(
                        {
                            "done": True,
                            "stopped": True,
                            "job_id": self.id,
                            "conversation_id": self.conversation_id,
                        }
                    )
                )
            elif failed and not terminal_seen:
                self._publish(
                    _sse(
                        {
                            "done": True,
                            "failed": True,
                            "job_id": self.id,
                            "conversation_id": self.conversation_id,
                        }
                    )
                )

            with self._condition:
                self.state = "stopped" if stopped else "failed" if failed else "completed"
                self.completed_at = time.monotonic()
                self._condition.notify_all()
            if self._on_terminal is not None:
                self._on_terminal(self)


class GenerationManager:
    """Thread-safe active lanes plus a bounded FIFO of replayable generation jobs."""

    def __init__(
        self,
        *,
        completed_ttl_s: float = 300.0,
        reservation_ttl_s: float = 300.0,
        max_active: int | None = None,
        max_queued: int = 32,
    ) -> None:
        self.completed_ttl_s = completed_ttl_s
        self.reservation_ttl_s = reservation_ttl_s
        self.max_active = max_active
        self.max_queued = max(0, max_queued)
        self._lock = threading.RLock()
        self._jobs: dict[str, GenerationJob] = {}
        self._reservations: dict[str, _Reservation] = {}
        self._queue: list[str] = []
        self._shutting_down = False
        self._promotion_retry_pending = False

    def reserve(
        self,
        student_id: str,
        *,
        allow_parallel: bool,
        conversation_id: str | None = None,
        client_request_id: str | None = None,
    ) -> str:
        """Atomically reserve an active-or-queued job before mutating chat history."""
        with self._lock:
            self._prune_locked()
            if self._shutting_down:
                raise GenerationCapacityError("generation service is shutting down")
            live = sum(job.state in {"queued", "running"} for job in self._jobs.values())
            occupied = live + len(self._reservations)
            if (
                self.max_active is not None
                and occupied >= self.max_active + self.max_queued
            ):
                raise GenerationCapacityError(
                    "the local reply queue is full — please try again shortly"
                )
            same_student = any(
                job.student_id == student_id and job.state in {"queued", "running"}
                for job in self._jobs.values()
            ) or any(row.student_id == student_id for row in self._reservations.values())
            if same_student and not allow_parallel:
                raise GenerationCapacityError("a reply is already running for this learner")
            if conversation_id and (
                any(
                    job.student_id == student_id
                    and job.conversation_id == conversation_id
                    and job.state in {"queued", "running"}
                    for job in self._jobs.values()
                )
                or any(
                    row.student_id == student_id and row.conversation_id == conversation_id
                    for row in self._reservations.values()
                )
            ):
                raise GenerationCapacityError("a reply is already running in this conversation")
            if client_request_id and (
                any(
                    job.student_id == student_id
                    and job.client_request_id == client_request_id
                    for job in self._jobs.values()
                )
                or any(
                    row.student_id == student_id
                    and row.client_request_id == client_request_id
                    for row in self._reservations.values()
                )
            ):
                raise GenerationCapacityError("this generation request is already being handled")
            reservation_id = uuid.uuid4().hex
            self._reservations[reservation_id] = _Reservation(
                student_id=student_id,
                conversation_id=conversation_id,
                client_request_id=client_request_id,
                created_at=time.monotonic(),
            )
            return reservation_id

    def cancel_reservation(self, reservation_id: str) -> None:
        with self._lock:
            self._reservations.pop(reservation_id, None)

    def start(
        self,
        *,
        student_id: str,
        conversation_id: str,
        producer: Iterator[str],
        reservation_id: str | None = None,
        client_request_id: str | None = None,
        queued_cleanup: Callable[[], None] | None = None,
        before_start: Callable[[], bool] | None = None,
    ) -> GenerationJob:
        if reservation_id is None:
            reservation_id = self.reserve(
                student_id,
                allow_parallel=True,
                conversation_id=conversation_id,
                client_request_id=client_request_id,
            )
        job = GenerationJob(
            student_id=student_id,
            conversation_id=conversation_id,
            producer=producer,
            client_request_id=client_request_id,
            on_terminal=self._job_terminal,
            queued_cleanup=queued_cleanup,
            before_start=before_start,
        )
        with self._lock:
            self._prune_locked()
            if self._shutting_down:
                raise GenerationCapacityError("generation service is shutting down")
            reserved = self._reservations.get(reservation_id)
            if reserved is None or reserved.student_id != student_id:
                raise GenerationCapacityError("generation reservation expired")
            if reserved.client_request_id != client_request_id:
                raise GenerationCapacityError("generation reservation does not match this request")
            if any(
                existing.student_id == student_id
                and existing.conversation_id == conversation_id
                and existing.state in {"queued", "running"}
                for existing in self._jobs.values()
            ):
                raise GenerationCapacityError("a reply is already running in this conversation")
            self._reservations.pop(reservation_id, None)
            self._jobs[job.id] = job
            self._queue.append(job.id)
            try:
                self._promote_locked(propagate_for=job.id)
            except Exception:
                self._queue = [job_id for job_id in self._queue if job_id != job.id]
                self._jobs.pop(job.id, None)
                raise
        return job

    def get(self, job_id: str, *, student_id: str | None = None) -> GenerationJob | None:
        with self._lock:
            self._prune_locked()
            job = self._jobs.get(job_id)
            if job is None or (student_id is not None and job.student_id != student_id):
                return None
            return job

    def active(self, student_id: str) -> list[GenerationSnapshot]:
        with self._lock:
            self._prune_locked()
            rows = [
                job.snapshot()
                for job in self._jobs.values()
                if job.student_id == student_id and job.state in {"queued", "running"}
            ]
        return sorted(rows, key=lambda row: row.created_at)

    def matching(self, student_id: str, client_request_id: str) -> list[GenerationSnapshot]:
        """Return retained jobs for one browser request, including completed replay buffers."""
        with self._lock:
            self._prune_locked()
            rows = [
                job.snapshot()
                for job in self._jobs.values()
                if job.student_id == student_id and job.client_request_id == client_request_id
            ]
        return sorted(rows, key=lambda row: row.created_at)

    def running_count(self) -> int:
        with self._lock:
            self._prune_locked()
            return sum(job.state == "running" for job in self._jobs.values())

    def run_when_idle(self, operation: Callable[[], object]) -> object:
        """Run a model lifecycle transition atomically against generation admission."""
        with self._lock:
            self._prune_locked()
            if any(
                job.state in {"queued", "running"} for job in self._jobs.values()
            ) or self._reservations:
                raise GenerationCapacityError("wait for active replies before changing models")
            return operation()

    def shutdown(self, timeout_s: float = 2.0) -> None:
        """Request cancellation and briefly drain workers during application shutdown."""
        with self._lock:
            self._shutting_down = True
            jobs = [job for job in self._jobs.values() if job.state == "running"]
            queued = [job for job in self._jobs.values() if job.state == "queued"]
            self._reservations.clear()
        for job in queued:
            job.request_stop()
        for job in jobs:
            job.request_stop()
        deadline = time.monotonic() + max(0.0, timeout_s)
        for job in jobs:
            job._thread.join(timeout=max(0.0, deadline - time.monotonic()))

    def _job_terminal(self, job: GenerationJob) -> None:
        with self._lock:
            self._queue = [job_id for job_id in self._queue if job_id != job.id]
            if not self._shutting_down:
                self._promote_locked()

    def _promote_locked(self, *, propagate_for: str | None = None) -> None:
        limit = self.max_active
        while self._queue and (limit is None or self.running_count() < limit):
            job_id = self._queue.pop(0)
            job = self._jobs.get(job_id)
            if job is None or job.state != "queued":
                continue
            try:
                started = job.start()
            except Exception as exc:
                # The caller of start() can still return an ordinary HTTP error for its own
                # synchronous admission. A previously accepted FIFO job, however, already has
                # subscribers: terminalize it in-band and keep the queue moving.
                if job_id == propagate_for:
                    raise
                detail = getattr(exc, "detail", None)
                message = detail if isinstance(detail, str) and detail else str(exc)
                job.reject_queued(message or "the tutor cannot start this reply right now")
                continue
            if not started:
                self._queue.insert(0, job_id)
                self._schedule_promotion_retry_locked()
                break
        self._refresh_queue_positions_locked()

    def _schedule_promotion_retry_locked(self) -> None:
        if self._promotion_retry_pending or self._shutting_down:
            return
        self._promotion_retry_pending = True
        retry = threading.Timer(0.25, self._retry_promotions)
        retry.name = "muta-generation-promotion-retry"
        retry.daemon = True
        retry.start()

    def _retry_promotions(self) -> None:
        with self._lock:
            self._promotion_retry_pending = False
            if not self._shutting_down:
                self._promote_locked()

    def _refresh_queue_positions_locked(self) -> None:
        live_queue: list[str] = []
        for job_id in self._queue:
            job = self._jobs.get(job_id)
            if job is not None and job.state == "queued":
                live_queue.append(job_id)
        self._queue = live_queue
        for position, job_id in enumerate(self._queue, start=1):
            self._jobs[job_id].set_queue_position(position)

    def _prune_locked(self) -> None:
        now = time.monotonic()
        self._reservations = {
            reservation_id: reservation
            for reservation_id, reservation in self._reservations.items()
            if now - reservation.created_at < self.reservation_ttl_s
        }
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job.completed_at is not None and now - job.completed_at >= self.completed_ttl_s
        ]
        for job_id in expired:
            self._jobs.pop(job_id, None)
        self._queue = [job_id for job_id in self._queue if job_id in self._jobs]
