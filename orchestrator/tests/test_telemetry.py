"""TelemetryHub — window math, null degradation, peak monotonicity, bounded state."""

from __future__ import annotations

from fastapi.testclient import TestClient

from orchestrator import telemetry
from orchestrator.main import app
from orchestrator.telemetry import TelemetryHub
from runtime import system_metrics

client = TestClient(app)


def test_rate_is_tokens_over_trailing_window(monkeypatch):
    hub = TelemetryHub()
    clock = {"now": 100.0}
    monkeypatch.setattr(telemetry.time, "monotonic", lambda: clock["now"])
    hub.begin("c1")
    for _ in range(10):
        hub.tick("c1")
        clock["now"] += 0.1
    # 10 ticks over ~0.9s inside the 2s window → ~11 tok/s.
    rate = hub.rate("c1")
    assert rate is not None
    assert 9.0 < rate < 13.0


def test_rate_is_none_when_idle(monkeypatch):
    hub = TelemetryHub()
    clock = {"now": 100.0}
    monkeypatch.setattr(telemetry.time, "monotonic", lambda: clock["now"])
    hub.tick("c1")
    clock["now"] += 60.0  # long past the window
    assert hub.rate("c1") is None


def test_snapshot_null_temp_means_null_throttled(monkeypatch):
    hub = TelemetryHub()
    monkeypatch.setattr(system_metrics, "family_rss_bytes", lambda pid: 2 * 1024**3)
    monkeypatch.setattr(system_metrics, "read_temp_c", lambda: None)
    hub.sample_once()
    snap = hub.snapshot("c1")
    assert snap["cpu_temp_c"] is None
    assert snap["throttled"] is None
    assert snap["rss_gb"] == 2.0


def test_snapshot_throttled_true_above_85(monkeypatch):
    hub = TelemetryHub()
    monkeypatch.setattr(system_metrics, "family_rss_bytes", lambda pid: 1024**3)
    monkeypatch.setattr(system_metrics, "read_temp_c", lambda: 91.5)
    hub.sample_once()
    snap = hub.snapshot("c1")
    assert snap["cpu_temp_c"] == 91.5
    assert snap["throttled"] is True


def test_peak_rss_is_monotonic(monkeypatch):
    hub = TelemetryHub()
    readings = iter([100 * 1024**2, 50 * 1024**2])
    monkeypatch.setattr(system_metrics, "family_rss_bytes", lambda pid: next(readings))
    monkeypatch.setattr(system_metrics, "read_temp_c", lambda: None)
    hub.sample_once()
    hub.sample_once()
    snap = hub.snapshot("c1")
    assert snap["rss_gb"] < snap["peak_rss_gb"]


def test_generating_flag_follows_begin_end():
    hub = TelemetryHub()
    hub._wake.clear()
    hub.begin("c1")
    assert hub.snapshot("c1")["generating"] is True
    assert hub._wake.is_set()  # an idle 10-second wait is interrupted immediately
    hub.end("c1")
    assert hub.snapshot("c1")["generating"] is False


def test_stale_conversations_are_pruned(monkeypatch):
    hub = TelemetryHub()
    clock = {"now": 100.0}
    monkeypatch.setattr(telemetry.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(system_metrics, "family_rss_bytes", lambda pid: 0)
    monkeypatch.setattr(system_metrics, "read_temp_c", lambda: None)
    hub.tick("old")
    clock["now"] += telemetry.TICKS_IDLE_TTL_S + 1
    hub.sample_once()
    assert "old" not in hub._ticks


def test_read_temp_c_none_when_no_sensors(monkeypatch):
    monkeypatch.setattr(system_metrics.psutil, "sensors_temperatures", dict, raising=False)
    monkeypatch.setattr(system_metrics.shutil, "which", lambda name: None)
    assert system_metrics.read_temp_c() is None


def test_telemetry_snapshot_endpoint_shape():
    r = client.get("/v1/conversations/whatever/telemetry")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {
        "rss_gb",
        "peak_rss_gb",
        "cpu_temp_c",
        "throttled",
        "tokens_per_second",
        "generating",
    }
