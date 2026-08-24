"""Publish recent generation rates so an external monitor can read them.

`bench/monitor.py` runs as a separate process — deliberately, because a sampler inside the
gateway adds its own RSS to the tree it reports, and to the tree the official profiler would
measure. But an external observer can never see a generation, so the app publishes them here.

Mounted at `/internal/bench`, never on `/v1`: the contract is frozen and this is telemetry,
not product surface.

The buffer is bounded at 64 floats (~1 KB). RAM is a scored term; an unbounded buffer inside
the very tree being measured would be self-defeating.
"""

from __future__ import annotations

import threading
from collections import deque

from orchestrator._common import make_service
from runtime.client import Generation
from runtime.paths import data_root

WINDOW = 64
PIDFILE = data_root() / "muta.pid"

_lock = threading.Lock()
_rates: deque[float] = deque(maxlen=WINDOW)
_last_tokens = 0
_last_from_wall_clock = False



def record(generation: Generation) -> None:
    """Record one completed generation. Zero-rate generations are not data points."""
    global _last_tokens, _last_from_wall_clock
    if generation.tokens_per_second <= 0:
        return
    with _lock:
        _rates.append(generation.tokens_per_second)
        _last_tokens = generation.completion_tokens
        _last_from_wall_clock = generation.from_wall_clock


def snapshot() -> dict:
    with _lock:
        rates = list(_rates)
        tokens = _last_tokens
        wall = _last_from_wall_clock
    return {
        "count": len(rates),
        "window": WINDOW,
        "last_tps": rates[-1] if rates else 0.0,
        "avg_tps": sum(rates) / len(rates) if rates else 0.0,
        "last_completion_tokens": tokens,
        "from_wall_clock": wall,
    }


def reset() -> None:
    global _last_tokens, _last_from_wall_clock
    with _lock:
        _rates.clear()
        _last_tokens = 0
        _last_from_wall_clock = False


app = make_service("bench")


@app.get("/metrics", tags=["ops"])
def metrics() -> dict:
    """Recent generation rates. Read by bench/monitor.py; not part of the /v1 contract."""
    return snapshot()
