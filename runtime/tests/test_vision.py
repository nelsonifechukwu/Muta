"""CORE-VISION manager tests (TDD §6.3, T10).

No real llama-server is launched: the manager's contract is spawn / deny / reap, and each of
those is a decision about memory that has to hold whether or not an engine binary exists.
"""

from __future__ import annotations

import subprocess
import threading
import time

import pytest

from runtime.profiles import BundlePaths
from runtime.tests.test_profiles import bundle  # noqa: F401 — fixture reuse
from runtime.vision import (
    IDLE_TTL_SECONDS,
    SPAWN_BUDGET_SECONDS,
    STARTUP_TIMEOUT_SECONDS,
    VisionDenied,
    VisionManager,
    _wrap_with_scope,
    ffmpeg_frames_command,
)


class FakeProcess:
    def __init__(self, *, exits: int | None = None) -> None:
        self.returncode = exits
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9


@pytest.fixture
def manager(bundle, monkeypatch):  # noqa: F811
    ticks = {"now": 0.0}

    def clock() -> float:
        return ticks["now"]

    spawned: list[list[str]] = []
    process = FakeProcess()

    def fake_popen(argv, **_kw):
        spawned.append(argv)
        return process

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    mgr = VisionManager(paths=BundlePaths(bundle.root), clock=clock)
    monkeypatch.setattr(mgr, "_healthy", lambda: True)
    mgr.ticks, mgr.spawned, mgr.fake_process = ticks, spawned, process  # type: ignore[attr-defined]
    return mgr


def test_first_request_spawns_and_returns_a_url(manager):
    url = manager.ensure()
    assert url.endswith(":8082") and manager.running
    assert len(manager.spawned) == 1


def test_second_request_reuses_the_running_instance(manager):
    manager.ensure()
    manager.ensure()
    assert len(manager.spawned) == 1 and manager.spawns == 1


def test_the_ladder_can_refuse_a_spawn_and_the_message_is_for_a_student(manager):
    """S2 failure path: at ladder ≥ L1 vision is denied, and the student is told what to do
    instead — never shown an error (C-7)."""
    manager.admit = lambda: False
    with pytest.raises(VisionDenied) as e:
        manager.ensure()
    assert "type the problem" in str(e.value)
    assert not manager.running and not manager.spawned


def test_an_already_running_instance_serves_even_under_pressure(manager):
    """Denial applies to new spawns; killing a live instance mid-answer would be worse than
    the memory it frees."""
    manager.ensure()
    manager.admit = lambda: False
    assert manager.ensure().endswith(":8082")


def test_missing_model_is_a_denial_not_a_crash(bundle, monkeypatch):  # noqa: F811
    (bundle.root / "models" / "core" / "mmproj-q8_0.gguf").unlink()
    mgr = VisionManager(paths=BundlePaths(bundle.root))
    with pytest.raises(VisionDenied, match="not staged"):
        mgr.ensure()


def test_a_server_that_dies_during_startup_is_reported(bundle, monkeypatch):  # noqa: F811
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: FakeProcess(exits=1))
    mgr = VisionManager(paths=BundlePaths(bundle.root))
    with pytest.raises(VisionDenied, match="exited during startup"):
        mgr.ensure()


def test_idle_instance_is_reaped_after_the_ttl(manager):
    manager.ensure()
    manager.ticks["now"] = IDLE_TTL_SECONDS - 1
    assert manager.reap_if_idle() is False and manager.running

    manager.ticks["now"] = IDLE_TTL_SECONDS + 1
    assert manager.reap_if_idle() is True
    assert not manager.running and manager.fake_process.terminated


def test_a_request_in_flight_blocks_the_reaper(manager):
    """A transcription at the Qwen-VL token floor legitimately runs past the 120 s TTL on a
    slow box, and `last_used` is only stamped at `ensure()` — so the reaper saw a busy server
    as idle and killed it mid-read. Latent until the client timeout grew past the TTL."""
    manager.ensure()
    with manager.in_use():
        manager.ticks["now"] = IDLE_TTL_SECONDS + 30
        assert manager.reap_if_idle() is False, "reaped a server that was serving a request"
    # The clock restarts when the request finishes, and idle reaping resumes.
    manager.ticks["now"] += IDLE_TTL_SECONDS + 1
    assert manager.reap_if_idle() is True


def test_active_read_blocks_capacity_reconfiguration_then_idle_engine_stops(manager):
    manager.ensure()
    with manager.in_use():
        assert manager.stop_for_reconfigure() is False
        assert manager.running

    assert manager.stop_for_reconfigure() is True
    assert not manager.running
    assert manager.fake_process.terminated


def test_auxiliary_image_reads_are_serialized(manager):
    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()

    def first() -> None:
        with manager.in_use():
            first_entered.set()
            assert release_first.wait(timeout=2)

    def second() -> None:
        with manager.in_use():
            second_entered.set()

    one = threading.Thread(target=first)
    two = threading.Thread(target=second)
    one.start()
    assert first_entered.wait(timeout=2)
    two.start()
    assert not second_entered.wait(timeout=0.1)
    release_first.set()
    one.join(timeout=2)
    two.join(timeout=2)
    assert second_entered.is_set()


def test_use_resets_the_idle_clock(manager):
    manager.ensure()
    manager.ticks["now"] = IDLE_TTL_SECONDS - 1
    manager.touch()
    manager.ticks["now"] = IDLE_TTL_SECONDS + 1
    assert manager.reap_if_idle() is False, "an in-use instance must not be reaped"


def test_reaping_a_stopped_manager_is_a_no_op(manager):
    assert manager.reap_if_idle() is False


def test_the_idle_reaper_does_not_kill_an_instance_that_is_still_starting(manager):
    """Regression: the second image upload of a session used to fail, permanently.

    `ensure()` stamped `last_used` only *after* `_spawn()` returned, but `_spawn()` blocks for
    the whole model load. In that window `running` is already True (Popen returned) while
    `last_used` still holds the *previous* use — which, once an instance has been reaped, is
    always older than the TTL. The 30 s reaper tick therefore saw a fully idle instance and
    killed the server mid-load. Every upload after the first then burned the full 60 s startup
    timeout and came back refused.
    """
    manager.ensure()  # first use: spawns and stamps last_used
    manager.ticks["now"] = IDLE_TTL_SECONDS + 1
    assert manager.reap_if_idle() is True  # correctly reaped once genuinely idle

    # A later upload. The cold mmproj load takes ~15 s, so a reaper tick lands inside it.
    manager.ticks["now"] = 10_000.0
    manager.fake_process.returncode = None  # Popen hands back a fresh process

    def loading_then_ready() -> bool:
        manager.ticks["now"] += 5.0
        manager.reap_if_idle()  # the concurrent _vision_reaper task ticks
        # A killed server never answers /health again.
        return manager.fake_process.returncode is None and manager.ticks["now"] >= 10_015.0

    manager._healthy = loading_then_ready
    url = manager.ensure()
    assert url.endswith(":8082")
    assert manager.running, "the idle reaper killed a server that was still starting up"


def test_concurrent_requests_spawn_exactly_one_instance(bundle, monkeypatch):  # noqa: F811
    """Two uploads in flight at once must not race two servers onto the same port.

    The loser exits with EADDRINUSE, and since both callers are waiting on the same port, the
    winner's student is told the reader is broken. A classroom is six phones; an impatient
    student is two clicks. Both are the normal case, not the edge case.
    """
    in_popen, release = threading.Event(), threading.Event()
    spawned: list[list[str]] = []

    def fake_popen(argv, **_kw):
        spawned.append(argv)
        in_popen.set()  # the first caller is inside the spawn
        release.wait(timeout=5)  # hold it there while the second one tries
        return FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    mgr = VisionManager(paths=BundlePaths(bundle.root))
    monkeypatch.setattr(mgr, "_healthy", lambda: True)

    first = threading.Thread(target=mgr.ensure, daemon=True)
    first.start()
    assert in_popen.wait(timeout=5), "the first spawn never started"
    second = threading.Thread(target=mgr.ensure, daemon=True)
    second.start()
    time.sleep(0.2)  # give the second caller every chance to race past the `running` check
    release.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert len(spawned) == 1, f"raced {len(spawned)} vision servers onto one port"


def test_startup_timeout_is_env_tunable_for_slow_boxes(bundle, monkeypatch):  # noqa: F811
    """60 s covers a warm spawn on the target; a cold load under emulation can exceed it and
    every image comes back "did not become ready". MUTA_RT_VISION_STARTUP_S widens the
    window per box — the same pattern as MUTA_RT_STARTUP_TIMEOUT_S for the core engine."""
    monkeypatch.setenv("MUTA_RT_VISION_STARTUP_S", "300")
    mgr = VisionManager(paths=BundlePaths(bundle.root))
    assert mgr.startup_timeout_s == 300.0


def test_startup_timeout_defaults_to_the_module_constant(bundle):  # noqa: F811
    mgr = VisionManager(paths=BundlePaths(bundle.root))
    assert mgr.startup_timeout_s == STARTUP_TIMEOUT_SECONDS


def test_the_startup_deadline_comes_from_the_manager_field(manager):
    """The field must actually drive `_wait_until_ready`, not just sit on the dataclass."""
    manager.startup_timeout_s = 5.0

    def never_healthy() -> bool:
        manager.ticks["now"] += 1.0
        return False

    manager._healthy = never_healthy
    with pytest.raises(VisionDenied, match="did not become ready"):
        manager.ensure()
    assert manager.ticks["now"] <= 10.0, "deadline ignored the field and used the 60 s constant"


def test_slow_spawn_is_logged_against_the_budget(manager, caplog):
    """§6.3 budgets ≤ 6 s from warm weights; past that the student watches a spinner."""
    original = manager._healthy
    calls = {"n": 0}

    def slow_health():
        calls["n"] += 1
        manager.ticks["now"] += SPAWN_BUDGET_SECONDS + 1
        return original()

    manager._healthy = slow_health
    with caplog.at_level("WARNING"):
        manager.ensure()
    assert any("vision spawn took" in r.message for r in caplog.records)


def test_status_is_reportable(manager):
    manager.ensure()
    status = manager.status()
    assert status["running"] and status["ttl_seconds"] == IDLE_TTL_SECONDS and status["spawns"] == 1


# --- process wrapping --------------------------------------------------------------------


def test_systemd_scope_carries_the_marginal_memory_cap(monkeypatch):
    from runtime.profiles import Invocation

    monkeypatch.setattr("runtime.vision.shutil.which", lambda _n: "/usr/bin/systemd-run")
    argv = _wrap_with_scope(Invocation(["llama-server", "-m", "x.gguf"]))
    assert argv[:2] == ["systemd-run", "--scope"]
    assert "MemoryMax=1100M" in argv  # §5.1: the vision instance's marginal budget
    assert "Slice=tutor.slice" in argv
    assert argv[-2:] == ["-m", "x.gguf"]


def test_without_systemd_the_command_runs_bare(monkeypatch):
    from runtime.profiles import Invocation

    monkeypatch.setattr("runtime.vision.shutil.which", lambda _n: None)
    assert _wrap_with_scope(Invocation(["llama-server"])) == ["llama-server"]


def test_ffmpeg_caps_frames_and_resolution():
    """S4: video is 8 frames at 1 fps, longest side 1280 — a context budget, not an
    aesthetic choice."""
    argv = ffmpeg_frames_command("clip.mp4", "/tmp/f_%02d.jpg")
    assert argv[argv.index("-frames:v") + 1] == "8"
    assert "fps=1,scale='min(1280,iw)':-2" in argv[argv.index("-vf") + 1]
