"""Opt-in web grounding on /v1/chat/stream: prompt suffix + sources on the done event.

Grounded only when ALL of: the student opted in (`use_web`), `MUTA_SEARCH_URL` is set,
and the box is online. Every other combination must produce the byte-identical request
the tutor already serves, with `"sources": []`.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from orchestrator.gateway import deps, routes
from orchestrator.gateway.connectivity import get_connectivity
from orchestrator.gateway.websearch import Source
from orchestrator.main import app

client = TestClient(app)

SNIPPETS = [
    Source(title="Projectile motion", url="https://a.example/1", snippet="R = v^2 sin(2θ)/g."),
]


class CaptureEngine:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def stream_events_chat(self, **kwargs):
        self.calls.append(kwargs)
        return "conv-1", 1, iter([("content", "grounded answer")])


@pytest.fixture
def wired(monkeypatch):
    engine = CaptureEngine()
    app.dependency_overrides[deps.get_engine] = lambda: engine
    monkeypatch.setattr(routes, "fetch_snippets", lambda q, base_url, **kw: list(SNIPPETS))
    probe = get_connectivity()
    probe._online = True
    yield engine
    probe._online = None
    app.dependency_overrides.clear()


def _post(body_extra: dict | None = None) -> str:
    body = {"student_id": "s1", "message": "range of a projectile?", **(body_extra or {})}
    return client.post("/v1/chat/stream", json=body).text


def _done(text: str) -> dict:
    return json.loads([ln for ln in text.splitlines() if '"done": true' in ln][-1][len("data: "):])


def test_grounded_when_opted_in_online_and_configured(wired, monkeypatch):
    monkeypatch.setenv("MUTA_SEARCH_URL", "http://searx.local")
    text = _post({"use_web": True})
    prompt = wired.calls[-1]["system_prompt"]
    assert "[1] Projectile motion" in prompt
    assert "R = v^2 sin(2θ)/g." in prompt
    assert _done(text)["sources"] == [{"title": "Projectile motion", "url": "https://a.example/1"}]


def test_toggle_off_means_untouched_prompt(wired, monkeypatch):
    monkeypatch.setenv("MUTA_SEARCH_URL", "http://searx.local")
    text = _post()
    assert "[1]" not in wired.calls[-1]["system_prompt"]
    assert _done(text)["sources"] == []


def test_unconfigured_endpoint_means_ungrounded(wired, monkeypatch):
    monkeypatch.delenv("MUTA_SEARCH_URL", raising=False)
    text = _post({"use_web": True})
    assert "[1]" not in wired.calls[-1]["system_prompt"]
    assert _done(text)["sources"] == []


def test_offline_means_ungrounded(wired, monkeypatch):
    monkeypatch.setenv("MUTA_SEARCH_URL", "http://searx.local")
    get_connectivity()._online = False
    text = _post({"use_web": True})
    assert "[1]" not in wired.calls[-1]["system_prompt"]
    assert _done(text)["sources"] == []
