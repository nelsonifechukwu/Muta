"""Connectivity probe — a cached verdict, never on a request path.

Offline is a state, not an error: the verdict rides `/v1/ready` as a top-level `online`
field (NOT a `checks` entry — `ready = all(checks)` and an offline-but-healthy stack is
still ready).
"""

from __future__ import annotations

import httpx

from orchestrator.gateway.connectivity import ConnectivityProbe


def test_probe_reports_online_when_head_succeeds(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "head",
        lambda url, timeout, follow_redirects: httpx.Response(
            200, request=httpx.Request("HEAD", url)
        ),
    )
    probe = ConnectivityProbe()
    assert probe.probe_once() is True
    assert probe.online() is True


def test_probe_reports_offline_on_transport_error(monkeypatch):
    def boom(url, timeout, follow_redirects):
        raise httpx.ConnectError("down", request=httpx.Request("HEAD", url))

    monkeypatch.setattr(httpx, "head", boom)
    probe = ConnectivityProbe()
    assert probe.probe_once() is False
    assert probe.online() is False


def test_online_is_none_before_the_first_probe():
    assert ConnectivityProbe().online() is None


def test_any_http_status_counts_as_online(monkeypatch):
    # A captive portal or a 403 from the probe URL still proves the network routes.
    monkeypatch.setattr(
        httpx,
        "head",
        lambda url, timeout, follow_redirects: httpx.Response(
            403, request=httpx.Request("HEAD", url)
        ),
    )
    assert ConnectivityProbe().probe_once() is True


def test_forced_offline_never_touches_the_network(monkeypatch):
    def unexpected_network(*args, **kwargs):
        raise AssertionError("forced-offline probe touched the network")

    monkeypatch.setenv("MUTA_OFFLINE", "1")
    monkeypatch.setattr(httpx, "head", unexpected_network)
    probe = ConnectivityProbe()
    probe.start()
    assert probe.online() is False
    assert probe.probe_once() is False
    assert probe._thread is None


def test_ready_reports_the_connectivity_verdict():
    from fastapi.testclient import TestClient

    from orchestrator.gateway.connectivity import get_connectivity
    from orchestrator.main import app

    probe = get_connectivity()
    probe._online = True  # the probe thread is not running under tests
    try:
        body = TestClient(app).get("/v1/ready").json()
        assert body["online"] is True
    finally:
        probe._online = None
