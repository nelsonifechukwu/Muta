"""One place that makes the app's logs actually appear.

The shipped container runs `uvicorn orchestrator.main:app` with no logging configuration, so
every `muta.*` INFO record (engine launch/ready, ladder transitions, connectivity flips,
vision spawn/reap, handled degradations) propagated to a handler-less root and was dropped —
an operator could not diagnose a student-reported failure from logs at all. Calling
`configure_logging()` at app import installs a single stderr handler on the root logger with a
timestamped, named, levelled format, so Docker's log driver captures a usable record.

Level comes from `MUTA_LOG_LEVEL` (default INFO) so debug can be turned on without a code
edit. uvicorn's own access/error loggers are left alone — this only fixes the app loggers.
"""

from __future__ import annotations

import logging
import os

from orchestrator.request_context import RequestIdFilter

_FORMAT = "%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%dT%H:%M:%S%z"
_configured = False


def configure_logging(*, force: bool = False) -> None:
    """Install a stderr root handler once. Idempotent — safe to call from both the app import
    and a `__main__` entrypoint."""
    global _configured
    if _configured and not force:
        return
    level_name = os.environ.get("MUTA_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)
    # Replace any prior basicConfig handler so the format is consistent, but don't touch
    # uvicorn's dedicated loggers (they have propagate=False and their own handlers).
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))
    handler.addFilter(RequestIdFilter())  # stamps %(request_id)s onto every record
    root.addHandler(handler)

    # The muta namespace follows the root level explicitly, so a stray library that raised the
    # root level cannot silence our own diagnostics.
    logging.getLogger("muta").setLevel(level)
    _configured = True
