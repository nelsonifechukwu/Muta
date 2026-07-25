"""Lifespan supervision: autostart gating, and the ready probe's degraded shapes."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from orchestrator import main as main_mod
from orchestrator.main import app

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
    monkeypatch.setattr(main_mod, "_start_engine_thread", lambda *a, **k: started.append(a))
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
