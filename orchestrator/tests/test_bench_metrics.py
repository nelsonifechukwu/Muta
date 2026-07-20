"""The HUD is an external process and never sees a generation, so the app publishes them.

This lives under /internal/*, never /v1 — the contract is frozen.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orchestrator import bench_metrics
from runtime.client import Generation


def _gen(tps: float, tokens: int = 10) -> Generation:
    return Generation(
        text="x",
        prompt_tokens=5,
        completion_tokens=tokens,
        elapsed_s=1.0,
        tokens_per_second=tps,
        from_wall_clock=False,
    )


@pytest.fixture(autouse=True)
def _clean():
    bench_metrics.reset()
    yield
    bench_metrics.reset()


def test_empty_snapshot_is_zeroed_not_absent():
    snap = bench_metrics.snapshot()
    assert snap["count"] == 0
    assert snap["last_tps"] == 0.0
    assert snap["avg_tps"] == 0.0


def test_records_last_and_average():
    bench_metrics.record(_gen(10.0))
    bench_metrics.record(_gen(20.0))
    snap = bench_metrics.snapshot()
    assert snap["count"] == 2
    assert snap["last_tps"] == 20.0
    assert snap["avg_tps"] == 15.0


def test_ring_buffer_is_bounded():
    for i in range(200):
        bench_metrics.record(_gen(float(i)))
    assert bench_metrics.snapshot()["count"] == bench_metrics.WINDOW
    assert bench_metrics.snapshot()["last_tps"] == 199.0
    # RAM is the scored term; an unbounded buffer inside the measured tree is self-defeating.
    assert bench_metrics.WINDOW <= 64


def test_zero_rate_generations_are_ignored():
    """A refused or empty completion is not a 0 tok/s data point; it is no data point."""
    bench_metrics.record(_gen(0.0, tokens=0))
    assert bench_metrics.snapshot()["count"] == 0


def test_endpoint_serves_the_snapshot():
    bench_metrics.record(_gen(12.5))
    body = TestClient(bench_metrics.app).get("/metrics").json()
    assert body["last_tps"] == 12.5


def test_endpoint_is_not_on_the_v1_contract():
    from orchestrator.main import app as assembled

    paths = assembled.openapi()["paths"]
    assert not any("bench" in path for path in paths)
    assert not any(path.startswith("/internal") for path in paths)
