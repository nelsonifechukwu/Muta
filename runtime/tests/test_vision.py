"""CORE-VISION manager tests (TDD §6.3, T10).

No real llama-server is launched: the manager's contract is spawn / deny / reap, and each of
those is a decision about memory that has to hold whether or not an engine binary exists.
"""

from __future__ import annotations

import subprocess

import pytest

from runtime.profiles import BundlePaths
from runtime.tests.test_profiles import bundle  # noqa: F401 — fixture reuse
from runtime.vision import (
    IDLE_TTL_SECONDS,
    SPAWN_BUDGET_SECONDS,
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


def test_use_resets_the_idle_clock(manager):
    manager.ensure()
    manager.ticks["now"] = IDLE_TTL_SECONDS - 1
    manager.touch()
    manager.ticks["now"] = IDLE_TTL_SECONDS + 1
    assert manager.reap_if_idle() is False, "an in-use instance must not be reaped"


def test_reaping_a_stopped_manager_is_a_no_op(manager):
    assert manager.reap_if_idle() is False


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
