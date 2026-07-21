"""Streaming must surface Qwen3 reasoning, not just the answer.

With thinking on, llama-server streams the chain of thought in a separate `reasoning_content`
delta. A consumer reading only `content` sees nothing during the think phase and appears to
hang — so `stream_events` yields both, tagged, while `stream` stays answer-only for callers
that don't want the reasoning.
"""

from __future__ import annotations

import httpx

from runtime.client import InferenceClient


class _FakeStream:
    """Stands in for httpx.stream()'s context manager over an SSE body."""

    def __init__(self, lines: list[str]):
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        pass

    def iter_lines(self):
        yield from self._lines


_SSE = [
    'data: {"choices":[{"delta":{"reasoning_content":"Let me think. "}}]}',
    'data: {"choices":[{"delta":{"reasoning_content":"12*11 = 132. "}}]}',
    'data: {"choices":[{"delta":{"content":"The answer "}}]}',
    'data: {"choices":[{"delta":{"content":"is 132."}}]}',
    "data: [DONE]",
]


def test_stream_events_tags_reasoning_and_content(monkeypatch):
    monkeypatch.setattr(httpx, "stream", lambda *a, **k: _FakeStream(list(_SSE)))
    events = list(InferenceClient().stream_events([{"role": "user", "content": "hi"}]))
    assert events == [
        ("reasoning", "Let me think. "),
        ("reasoning", "12*11 = 132. "),
        ("content", "The answer "),
        ("content", "is 132."),
    ]


def test_stream_drops_reasoning_and_yields_only_the_answer(monkeypatch):
    monkeypatch.setattr(httpx, "stream", lambda *a, **k: _FakeStream(list(_SSE)))
    assert list(InferenceClient().stream([{"role": "user", "content": "hi"}])) == [
        "The answer ",
        "is 132.",
    ]
