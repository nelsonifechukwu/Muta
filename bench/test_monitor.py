"""Tests for the live HUD.

`render_lines` is a pure function over already-collected values, so the panel can be tested
without starting a process, a server, or a terminal.
"""

from __future__ import annotations

import os

import pytest

from bench import monitor
from bench.sampler import MemoryReport, ThermalReport

MEM = MemoryReport(peak_rss_mb=2365.44, steady_state_rss_mb=2129.92, peak_vms_mb=9000.0)
COOL = ThermalReport(cpu_percent_p99=84.0, core_temp_c_peak=None, throttled=False)
HOT = ThermalReport(cpu_percent_p99=99.0, core_temp_c_peak=90.0, throttled=False)
METRICS = {"count": 8, "last_tps": 11.4, "avg_tps": 9.8, "window": 64, "from_wall_clock": False}


def _text(**kwargs) -> str:
    args = {"pid": 4821, "names": ["llama-server", "python"], "elapsed_s": 252.0}
    args.update(kwargs)
    return "\n".join(monitor.render_lines(**args))


def test_shows_peak_and_steady_in_gb():
    out = _text(memory=MEM, thermal=COOL, metrics=METRICS)
    assert "2.31 GB" in out  # 2365.44 MB
    assert "2.08 GB" in out  # 2129.92 MB


def test_shows_the_scored_terms():
    out = _text(memory=MEM, thermal=COOL, metrics=METRICS)
    assert "S_eff" in out and "S_perf" in out


def test_unmeasured_temperature_is_a_dash_never_zero():
    out = _text(memory=MEM, thermal=COOL, metrics=METRICS)
    assert "—" in out
    assert "0.0 °C" not in out


def test_hot_run_is_shown_as_penalised():
    """90 C penalises even though upstream would report throttled=False."""
    out = _text(memory=MEM, thermal=HOT, metrics=METRICS)
    assert "90.0" in out
    assert "−10" in out or "-10" in out


def test_degrades_when_metrics_endpoint_is_absent():
    out = _text(memory=MEM, thermal=COOL, metrics=None)
    assert "no /internal/bench/metrics" in out
    assert "2.31 GB" in out  # RSS still shown


def test_over_budget_is_called_out():
    huge = MemoryReport(peak_rss_mb=8000.0, steady_state_rss_mb=7800.0, peak_vms_mb=9000.0)
    assert "OVER" in _text(memory=huge, thermal=COOL, metrics=METRICS).upper()


def test_resolve_pid_prefers_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr(monitor, "PIDFILE", tmp_path / "muta.pid")
    assert monitor.resolve_pid(1234) == 1234


def test_resolve_pid_reads_the_pidfile(tmp_path, monkeypatch):
    pidfile = tmp_path / "muta.pid"
    pidfile.write_text(f"{os.getpid()}\n")
    monkeypatch.setattr(monitor, "PIDFILE", pidfile)
    assert monitor.resolve_pid() == os.getpid()


def test_resolve_pid_ignores_a_stale_pidfile(tmp_path, monkeypatch):
    pidfile = tmp_path / "muta.pid"
    pidfile.write_text("999999999\n")  # not a live process
    monkeypatch.setattr(monitor, "PIDFILE", pidfile)
    monkeypatch.setattr(monitor, "_pid_listening_on", lambda port: None)
    with pytest.raises(monitor.MonitorError) as exc:
        monitor.resolve_pid()
    assert "make dev" in str(exc.value)


def test_resolve_pid_error_lists_what_it_tried(tmp_path, monkeypatch):
    monkeypatch.setattr(monitor, "PIDFILE", tmp_path / "absent.pid")
    monkeypatch.setattr(monitor, "_pid_listening_on", lambda port: None)
    with pytest.raises(monitor.MonitorError) as exc:
        monitor.resolve_pid()
    message = str(exc.value)
    assert "--pid" in message and "8000" in message
