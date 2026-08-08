"""Web snippets — SearXNG-shaped, fail-silent: grounding is a bonus, never a blocker."""

from __future__ import annotations

import httpx

from orchestrator.gateway.websearch import Source, fetch_snippets

_RESULTS = {
    "results": [
        {"title": "Projectile motion", "url": "https://a.example/1", "content": "Range R = v^2 sin(2θ)/g."},
        {"title": "Kinematics", "url": "https://a.example/2", "content": "Time of flight 2v sinθ/g."},
        {"title": "Extra", "url": "https://a.example/3", "content": "More."},
        {"title": "Beyond k", "url": "https://a.example/4", "content": "Dropped."},
    ]
}


def _fake_get(payload):
    def get(url, params=None, timeout=None):
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    return get


def test_maps_the_top_k_results(monkeypatch):
    monkeypatch.setattr(httpx, "get", _fake_get(_RESULTS))
    out = fetch_snippets("projectile range", base_url="http://searx.local", k=3)
    assert out[0] == Source(
        title="Projectile motion", url="https://a.example/1", snippet="Range R = v^2 sin(2θ)/g."
    )
    assert len(out) == 3


def test_transport_error_is_an_empty_list(monkeypatch):
    def boom(url, params=None, timeout=None):
        raise httpx.ConnectError("down", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", boom)
    assert fetch_snippets("q", base_url="http://searx.local") == []


def test_malformed_body_is_an_empty_list(monkeypatch):
    monkeypatch.setattr(httpx, "get", _fake_get({"unexpected": "shape"}))
    assert fetch_snippets("q", base_url="http://searx.local") == []


def test_missing_fields_are_skipped_not_crashed(monkeypatch):
    monkeypatch.setattr(
        httpx, "get", _fake_get({"results": [{"title": "no url or content"}, None]})
    )
    assert fetch_snippets("q", base_url="http://searx.local") == []
