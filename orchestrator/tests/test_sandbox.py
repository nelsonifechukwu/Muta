"""Sandbox tests (TDD T8: "0 sandbox escapes (rlimit tests)").

Every limit is tested by actually hitting it. A jail that has never been hit is a jail
nobody has checked — and the failure mode it prevents (a runaway tool taking the 7 GiB
budget with it) shows up as an OOM kill, which is a disqualification rather than a bug.
"""

from __future__ import annotations

import sys
import time

import pytest

from orchestrator.tools import sandbox
from orchestrator.tools.sandbox import (
    RENDERER_LIMITS,
    VERIFIER_LIMITS,
    Limits,
    WorkerPool,
    run_once,
    sandbox_env,
)


@pytest.fixture
def allow_test_ops(monkeypatch):
    """The worker's limit-probing ops are gated on an env var that `sandbox_env()` never
    sets, so production calls cannot reach them however the model is prompted."""
    monkeypatch.setattr(
        sandbox, "sandbox_env", lambda: {**sandbox_env(), "MUTA_SANDBOX_ALLOW_TEST_OPS": "1"}
    )


@pytest.fixture
def pool():
    p = WorkerPool(1, VERIFIER_LIMITS).start()
    yield p
    p.close()


# --- the jail ----------------------------------------------------------------------------


def test_test_ops_are_unreachable_with_the_production_environment():
    result = run_once("_test", {"mode": "sleep", "seconds": 0.1})
    assert not result.ok and "test ops are disabled" in result.error


def test_wall_clock_timeout_kills_the_child(allow_test_ops):
    started = time.monotonic()
    result = run_once("_test", {"mode": "sleep", "seconds": 30}, Limits(wall_seconds=1.0))
    assert result.killed and "timeout" in result.error
    assert time.monotonic() - started < 5, "the parent must not wait for the child to finish"


def test_cpu_limit_stops_an_infinite_loop(allow_test_ops):
    """A `while True` burns CPU without ever blocking; a wall-clock timeout alone would let
    it keep a core busy until the parent noticed."""
    result = run_once("_test", {"mode": "cpu"}, Limits(cpu_seconds=1, wall_seconds=20))
    assert result.killed
    assert "CPU limit" in result.error or "no result" in result.error


@pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="RLIMIT_AS is not enforced on macOS (the kernel kills much later, via jetsam); "
    "the deploy target is Linux, where this is the real guard",
)
def test_memory_limit_stops_a_runaway_allocation(allow_test_ops):
    result = run_once("_test", {"mode": "memory"}, Limits(address_space_mib=128, wall_seconds=20))
    assert result.killed


def test_network_is_denied_inside_the_worker(allow_test_ops):
    """`unshare -rn` is the real guarantee on Linux; this is the portable half, and it is
    what holds on a dev Mac where namespaces do not exist."""
    result = run_once("_test", {"mode": "network"})
    assert not result.ok
    assert "network access is disabled" in result.error


def test_worker_environment_is_replaced_not_inherited(monkeypatch):
    monkeypatch.setenv("SECRET_TOKEN", "hunter2")
    env = sandbox_env()
    assert "SECRET_TOKEN" not in env
    assert env["MPLBACKEND"] == "Agg" and env["OMP_NUM_THREADS"] == "1"


def test_library_path_is_explicit_so_the_worker_can_import_sympy():
    """`-I` would drop PYTHONPATH and every verification would silently degrade to a string
    comparison — the bug this test exists to prevent recurring."""
    result = run_once("verify", {"candidate": "2*x", "expected": "x + x"})
    assert result.ok and result.value["equivalent"] is True
    assert "symbolic comparison unavailable" not in result.value["detail"]


# --- shapes ------------------------------------------------------------------------------


def test_unknown_op_is_data_not_a_crash():
    result = run_once("does_not_exist", {})
    assert not result.ok and "unknown op" in result.error and not result.killed


def test_bad_arguments_fail_cleanly():
    result = run_once("render", {"kind": "quantum", "code": ""})
    assert result.failed_cleanly and "unknown render kind" in result.error


def test_pool_reuses_a_warm_worker(pool):
    first = pool.submit("verify", {"candidate": "x", "expected": "x"})
    second = pool.submit("verify", {"candidate": "y", "expected": "y"})
    assert first.ok and second.ok
    # The import cost is paid once; the second call should be an order of magnitude cheaper.
    assert second.seconds < max(first.seconds, 0.05)


def test_pool_replaces_a_worker_it_had_to_kill(allow_test_ops):
    pool = WorkerPool(1, Limits(wall_seconds=1.0)).start()
    try:
        timed_out = pool.submit("_test", {"mode": "sleep", "seconds": 30})
        assert timed_out.killed
        recovered = pool.submit("ping", {})
        assert recovered.ok, "a timeout must not poison the pool for every later request"
    finally:
        pool.close()


def test_pool_close_is_idempotent(pool):
    pool.close()
    pool.close()


def test_renderer_limits_are_looser_than_verifier_limits():
    """Documented deviation from §7.5's single 256 MiB figure: NumPy + Matplotlib reserve
    more virtual address space than that at import, so the TDD value would kill the diagram
    path at startup rather than bounding it."""
    assert RENDERER_LIMITS.address_space_mib > VERIFIER_LIMITS.address_space_mib
    assert VERIFIER_LIMITS.address_space_mib == 256  # the TDD number, where it applies
    assert VERIFIER_LIMITS.cpu_seconds == 5 and VERIFIER_LIMITS.open_files == 32
