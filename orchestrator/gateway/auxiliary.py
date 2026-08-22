"""Event-loop-friendly admission for singleton/bounded auxiliary inference engines."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field


class AuxiliaryQueueFull(RuntimeError):
    pass


class OwnerWorkRejected(RuntimeError):
    pass


@dataclass(eq=False)
class _OwnerWork:
    cancel: threading.Event = field(default_factory=threading.Event)
    done: threading.Event = field(default_factory=threading.Event)


class OwnerWorkManager:
    """Cancellation/drain barrier for member-owned work outside GenerationManager."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._work: dict[str, set[_OwnerWork]] = {}
        self._blocked: set[str] = set()

    @contextmanager
    def track(self, owner_id: str) -> Iterator[threading.Event]:
        work = _OwnerWork()
        with self._condition:
            if owner_id in self._blocked:
                raise OwnerWorkRejected("this account can no longer start background work")
            self._work.setdefault(owner_id, set()).add(work)
        try:
            yield work.cancel
        finally:
            with self._condition:
                jobs = self._work.get(owner_id)
                if jobs is not None:
                    jobs.discard(work)
                    if not jobs:
                        self._work.pop(owner_id, None)
                work.done.set()
                self._condition.notify_all()

    def stop_owner(self, owner_id: str, *, timeout: float = 5.0) -> bool:
        deadline = time.monotonic() + timeout
        with self._condition:
            self._blocked.add(owner_id)
            for work in self._work.get(owner_id, ()):
                work.cancel.set()
            while self._work.get(owner_id):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
        return True


_OWNER_WORK = OwnerWorkManager()


def get_owner_work_manager() -> OwnerWorkManager:
    return _OWNER_WORK


@asynccontextmanager
async def auxiliary_slot(
    slots: threading.BoundedSemaphore,
    *,
    timeout_s: float = 30.0,
) -> AsyncIterator[None]:
    """Wait for a native inference slot without occupying an AnyIO worker thread."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while not slots.acquire(blocking=False):
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise AuxiliaryQueueFull("the auxiliary inference queue is busy")
        await asyncio.sleep(min(0.05, remaining))
    try:
        yield
    finally:
        slots.release()
