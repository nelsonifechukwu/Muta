"""Lifespan supervision: autostart gating, and the ready probe's degraded shapes."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient

from orchestrator import main as main_mod
from orchestrator.main import app
from runtime.config import RuntimeConfig

client = TestClient(app)


def _run_lifespan() -> None:
    async def _inner() -> None:
        async with main_mod._lifespan(app):
            pass

    asyncio.run(_inner())


def test_lifespan_autostart_off_never_touches_the_engine(monkeypatch):
    monkeypatch.delenv("MUTA_RT_AUTOSTART", raising=False)
    started: list = []
    monkeypatch.setattr(main_mod, "_start_engine_thread", lambda *a, **k: started.append(a))
    _run_lifespan()
    assert started == []


def test_lifespan_autostart_on_starts_engine_and_creates_dirs(monkeypatch, tmp_path):
    monkeypatch.setenv("MUTA_RT_AUTOSTART", "1")
    monkeypatch.setenv("TUTOR_ROOT", str(tmp_path))
    started: list = []
    stopped: list = []

    def _fake_start(*a, **k):
        # The supervisor returns (thread, stop_event); the lifespan unpacks and later .set()s it.
        started.append(a)
        return (None, main_mod.threading.Event())

    monkeypatch.setattr(main_mod, "_start_engine_thread", _fake_start)
    monkeypatch.setattr(
        main_mod.LlamaServer, "stop", lambda self: stopped.append(True), raising=True
    )

    class _FakeVision:
        def stop(self) -> None:
            pass

        def reap_if_idle(self) -> bool:
            return False

    monkeypatch.setattr(main_mod, "get_vision", lambda: _FakeVision())
    _run_lifespan()

    assert len(started) == 1
    assert (tmp_path / "data" / "logs").is_dir()
    assert (tmp_path / "data" / "kv-slots").is_dir()
    assert stopped == [True]


def test_persisted_competition_host_selects_safe_model_before_engine_start(monkeypatch, tmp_path):
    large = RuntimeConfig(
        model_dir=tmp_path,
        model_file="large.gguf",
        autostart=True,
        auto_download=False,
        _env_file=None,
    )
    small = large.model_copy(update={"model_file": "small.gguf"})

    class Planner:
        def plan(self, mode, cfg):
            assert mode == "competition"
            fits = cfg.model_file == "small.gguf"
            return SimpleNamespace(fits=fits, n_parallel=2, n_ctx=2048)

    class Manager:
        def __init__(self, cfg, **_kwargs):
            assert cfg.model_file == "large.gguf"

        def candidate_config(self, model_id):
            assert model_id == "qwen3.5-0.8b-q4_k_m"
            return small

    monkeypatch.setattr(main_mod, "CapacityPlanner", Planner)
    monkeypatch.setattr(main_mod, "ModelManager", Manager)

    cfg, profile = main_mod._persisted_share_runtime(
        large,
        {"enabled": True, "memory_mode": "competition"},
        root=tmp_path,
        log_file=tmp_path / "engine.log",
    )

    assert profile.fits is True
    assert cfg.model_file == "small.gguf"


def test_ready_reports_db_check_and_stays_200_when_down(monkeypatch):
    # Point both probes at nothing: ready must answer quickly, 200, ready:false.
    monkeypatch.setenv("MUTA_RT_SERVER_PORT", "1")  # nothing listens on port 1
    monkeypatch.setenv("MUTA_RT_DB_URL", "postgresql://muta:muta@127.0.0.1:1/muta")
    r = client.get("/v1/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is False
    assert set(body["checks"]) == {"gateway", "inference", "db"}
    assert body["checks"]["gateway"] is True
    assert body["checks"]["db"] is False
