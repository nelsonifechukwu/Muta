"""Tests for the chat TUI.

The rendering is pure over the app's own state, and the samplers are attached to this test
process, so the panel and transcript can be exercised without a live app, a real server, or a
terminal. Streaming/HTTP is covered by the gateway route tests, not re-driven here.
"""

from __future__ import annotations

import os

import pytest

from bench import tui


def _app() -> tui.MutaTUI:
    # Attach the RAM sampler to this test process so peak RSS is real and non-zero.
    return tui.MutaTUI("http://127.0.0.1:8000", gateway_pid=os.getpid(), engine_pid=None)


def test_metrics_panel_shows_the_scored_terms():
    app = _app()
    app._mem.start([os.getpid()])
    app._therm.start()
    try:
        import time

        time.sleep(0.4)
        rendered = app._render_metrics().plain
    finally:
        app._mem.stop()
        app._therm.stop()
    assert "S_perf" in rendered
    assert "S_eff" in rendered
    assert "GB" in rendered
    # Unmeasured temperature is an em dash, never a fabricated 0.
    assert "temp" in rendered


def test_transcript_renders_both_roles_and_the_streaming_cursor():
    app = _app()
    app.messages = [("you", "what is 2+2?"), ("muta", "It is 4.")]
    app.streaming = "partial reply"
    text = app._render_transcript().plain
    assert "you" in text and "what is 2+2?" in text
    assert "muta" in text and "It is 4." in text
    assert "partial reply" in text
    assert "▍" in text  # the live cursor while a reply streams


def test_thinking_is_shown_dimmed_until_the_answer_arrives():
    app = _app()
    # Reasoning has started, no answer content yet -> a "thinking…" block, not a frozen screen.
    app.thinking = "let me work through this"
    app.streaming = ""
    text = app._render_transcript().plain
    assert "thinking…" in text
    assert "let me work through this" in text

    # Once the answer starts, the thinking collapses and the answer shows.
    app.streaming = "The answer is 132."
    text = app._render_transcript().plain
    assert "thinking…" not in text
    assert "The answer is 132." in text


def test_over_budget_is_called_out_in_the_panel(monkeypatch):
    app = _app()

    class _Huge:
        peak_rss_gb = 9.0
        steady_state_rss_gb = 8.5

    monkeypatch.setattr(app._mem, "report", lambda: _Huge())
    monkeypatch.setattr(app._mem, "latest_rss_mb", lambda: 9000.0)
    assert "OVER BUDGET" in app._render_metrics().plain


def test_live_tps_climbs_as_tokens_arrive():
    """Regression: TPS must update DURING streaming, not stay 0 until the reply finishes."""
    app = _app()
    app._begin_stream()

    app._record_token(100.0)  # first token: a rate needs an interval, so still 0
    assert app.live_tps == 0.0

    app._record_token(100.5)  # 2 tokens, 0.5s window -> (2-1)/0.5 = 2.0 t/s
    assert app.live_tps == pytest.approx(2.0)

    app._record_token(101.0)  # 3 tokens, 1.0s window -> (3-1)/1.0 = 2.0 t/s
    assert app.live_tps == pytest.approx(2.0)


def test_begin_stream_resets_the_rate_window():
    app = _app()
    app._begin_stream()
    app._record_token(50.0)
    app._record_token(50.25)
    assert app.live_tps > 0
    # A new turn must not carry the previous turn's token count into its rate.
    app._begin_stream()
    assert app._stream_tokens == 0
    app._record_token(200.0)
    assert app.live_tps > 0  # unchanged until the 2nd token; not NaN/exploding


def test_build_app_errors_clearly_when_no_app_is_running(monkeypatch):
    monkeypatch.setattr(tui, "resolve_pid", lambda *a, **k: (_ for _ in ()).throw(
        tui.MonitorError("could not find a running Muta gateway. fix: ./run.sh --serve")
    ))
    rc = tui.main(["--port", "8000"])
    assert rc == 1
