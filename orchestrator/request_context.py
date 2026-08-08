"""Per-request correlation id, threaded from the edge into every log line.

A single X-Request-ID lets an operator follow one student's failing turn across the log:
browser → nginx → gateway → (engine). Without it, `--parallel 2` plus several students
interleave SSE/WS activity with no way to attribute a log line to a request.

The id lives in a ContextVar (so it survives the async→threadpool hop FastAPI does for sync
handlers — anyio copies the context into the worker thread) and a logging.Filter stamps it
onto every record, defaulting to "-" for logs emitted outside any request (startup, the engine
supervisor, background samplers).
"""

from __future__ import annotations

import logging
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("muta_request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True
