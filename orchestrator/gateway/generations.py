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
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone

log = logging.getLogger("muta.gateway.generations")

_DONE_MARKER = '"done": true'
_ERROR_MARKER = '"error"'


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@dataclass(frozen=True)
class GenerationSnapshot:
    job_id: str
    student_id: str
    conversation_id: str
    state: str
    created_at: str


class GenerationJob:
    """One engine iterator consumed by one worker and replayed to many subscribers."""

    def __init__(
        self,
        *,
        student_id: str,
        conversation_id: str,
        producer: Iterator[str],
        job_id: str | None = None,
    ) -> None:
        self.id = job_id or uuid.uuid4().hex
        self.student_id = student_id
        self.conversation_id = conversation_id
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.completed_at: float | None = None
        self.state = "running"
        self._producer = producer
        self._condition = threading.Condition()
        # The leading frame lets every subscriber bind the stream before replaying tokens.
        self._events = [_sse({"job_id": self.id, "conversation_id": self.conversation_id})]
        self._stop_requested = False
        self._thread = threading.Thread(
            target=self._run,
            name=f"muta-generation-{self.id[:8]}",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def snapshot(self) -> GenerationSnapshot:
        with self._condition:
            state = self.state
        return GenerationSnapshot(
            job_id=self.id,
            student_id=self.student_id,
            conversation_id=self.conversation_id,
            state=state,
            created_at=self.created_at,
        )

    def request_stop(self) -> bool:
        """Request cooperative cancellation. The worker closes the producer on its own thread.

        Closing a generator from the request thread while it is blocked inside ``next()`` can
        raise ``generator already executing`` and leak an inference slot. Waiting until the
        next engine event keeps ownership and cleanup on the worker that consumes it.
        """
        with self._condition:
            if self.state != "running":
                return False
            self._stop_requested = True
            self._condition.notify_all()
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
                elif self.state != "running":
                    return
                else:
                    self._condition.wait(timeout=10.0)
                    if cursor >= len(self._events) and self.state == "running":
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


class GenerationManager:
    """Thread-safe process registry with bounded retention for completed replay buffers."""

    def __init__(self, *, completed_ttl_s: float = 300.0) -> None:
        self.completed_ttl_s = completed_ttl_s
        self._lock = threading.RLock()
        self._jobs: dict[str, GenerationJob] = {}

    def start(
        self,
        *,
        student_id: str,
        conversation_id: str,
        producer: Iterator[str],
    ) -> GenerationJob:
        job = GenerationJob(
            student_id=student_id,
            conversation_id=conversation_id,
            producer=producer,
        )
        with self._lock:
            self._prune_locked()
            self._jobs[job.id] = job
        job.start()
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
                if job.student_id == student_id and job.state == "running"
            ]
        return sorted(rows, key=lambda row: row.created_at)

    def _prune_locked(self) -> None:
        now = time.monotonic()
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job.completed_at is not None and now - job.completed_at >= self.completed_ttl_s
        ]
        for job_id in expired:
            self._jobs.pop(job_id, None)
