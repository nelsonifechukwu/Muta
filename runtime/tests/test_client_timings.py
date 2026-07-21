"""The product path needs token counts to compute TPS; `chat()` returns only a str.

Preference order for TPS: llama-server's own `timings.predicted_per_second`, else
completion_tokens / wall-clock. The fallback is flagged so a derived number is never mistaken
for one the engine measured.
"""

from __future__ import annotations

import httpx
import pytest

from runtime.client import Generation, InferenceClient


def _mount(monkeypatch, payload: dict) -> None:
    def fake_post(url, **kwargs):
        return httpx.Response(200, json=payload, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)


def test_prefers_engine_reported_rate(monkeypatch):
    _mount(
        monkeypatch,
        {
            "choices": [{"message": {"content": "hello"}}],
            "usage": {"prompt_tokens": 40, "completion_tokens": 12},
            "timings": {"predicted_per_second": 11.75, "predicted_n": 12},
        },
    )
    g = InferenceClient().chat_with_timings([{"role": "user", "content": "hi"}])
    assert isinstance(g, Generation)
    assert g.text == "hello"
    assert g.completion_tokens == 12
    assert g.tokens_per_second == pytest.approx(11.75)
    assert g.from_wall_clock is False


def test_falls_back_to_wall_clock_and_flags_it(monkeypatch):
    _mount(
        monkeypatch,
        {
            "choices": [{"message": {"content": "hello"}}],
            "usage": {"prompt_tokens": 40, "completion_tokens": 20},
        },
    )
    g = InferenceClient().chat_with_timings([{"role": "user", "content": "hi"}])
    assert g.from_wall_clock is True
    assert g.tokens_per_second > 0.0
    assert g.completion_tokens == 20


def test_zero_completion_tokens_yields_zero_not_a_division_error(monkeypatch):
    _mount(
        monkeypatch,
        {
            "choices": [{"message": {"content": ""}}],
            "usage": {"prompt_tokens": 40, "completion_tokens": 0},
        },
    )
    g = InferenceClient().chat_with_timings([{"role": "user", "content": "hi"}])
    assert g.tokens_per_second == 0.0


def test_missing_usage_block_does_not_raise(monkeypatch):
    _mount(monkeypatch, {"choices": [{"message": {"content": "hi"}}]})
    g = InferenceClient().chat_with_timings([{"role": "user", "content": "hi"}])
    assert g.completion_tokens == 0
    assert g.tokens_per_second == 0.0


def test_chat_still_returns_a_plain_string(monkeypatch):
    """No existing caller may need to change."""
    _mount(
        monkeypatch,
        {
            "choices": [{"message": {"content": "plain"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        },
    )
    assert InferenceClient().chat([{"role": "user", "content": "hi"}]) == "plain"
