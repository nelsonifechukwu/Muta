"""Direct-listener boundaries that nginx cannot enforce for Host-mode learners."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from orchestrator.gateway.body_limit import RequestBodyLimitMiddleware
from orchestrator.gateway.sharing import get_sharing_service
from orchestrator.main import app


def test_streaming_body_limit_rejects_content_length_and_chunked_bodies():
    limited = FastAPI()
    limited.add_middleware(RequestBodyLimitMiddleware, max_bytes=8)

    @limited.post("/")
    async def consume(request: Request):
        return {"size": len(await request.body())}

    client = TestClient(limited)
    assert client.post("/", content=b"123456789").status_code == 413
    assert client.post("/", content=iter((b"1234", b"5678", b"9"))).status_code == 413
    assert client.post("/", content=b"12345678").json() == {"size": 8}


def test_direct_https_listener_emits_browser_security_headers():
    client = TestClient(
        app,
        base_url="https://muta.test:8443",
        client=("192.168.1.20", 51000),
    )

    response = client.get("/v1/health")

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "microphone=(self)" in response.headers["permissions-policy"]
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["strict-transport-security"] == "max-age=31536000"


def test_remote_diagnostics_metrics_and_session_controls_are_not_member_features(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("MUTA_SHARE_STRICT", "1")
    monkeypatch.setenv("MUTA_SHARE_DB_PATH", str(tmp_path / "share.sqlite3"))
    get_sharing_service.cache_clear()
    service = get_sharing_service()
    service.update_settings(enabled=True, memory_mode="competition")
    service.signup("Ada", "private classroom password", throttle_key="signup")
    service.approve(service.users()[0]["id"])
    issued = service.login("ada", "private classroom password", throttle_key="login")
    member = TestClient(
        app,
        base_url="https://muta.test:8443",
        client=("192.168.1.20", 51000),
    )
    member.cookies.set("muta_share_session", issued.token)
    try:
        assert member.get("/v1/metrics").status_code == 403
        assert member.post("/v1/session/private/resume").status_code == 403
        for path in ("/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"):
            assert member.get(path).status_code == 404
    finally:
        service.close()
        get_sharing_service.cache_clear()


def test_host_session_controls_require_csrf_even_on_loopback(monkeypatch, tmp_path):
    monkeypatch.setenv("MUTA_SHARE_STRICT", "1")
    monkeypatch.setenv("MUTA_SHARE_DB_PATH", str(tmp_path / "share.sqlite3"))
    get_sharing_service.cache_clear()
    service = get_sharing_service()
    issued = service.issue_host_session("operator")
    host = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 51001))
    host.cookies.set("muta_share_session", issued.token)
    try:
        for action in ("suspend", "resume"):
            path = f"/v1/session/untrusted/{action}"
            assert host.post(path).status_code == 403
            assert host.post(path, headers={"X-Muta-CSRF": "wrong"}).status_code == 403
    finally:
        service.close()
        get_sharing_service.cache_clear()


def test_remote_or_rebound_host_session_cannot_open_voice_websocket(monkeypatch, tmp_path):
    monkeypatch.setenv("MUTA_SHARE_STRICT", "1")
    monkeypatch.setenv("MUTA_SHARE_DB_PATH", str(tmp_path / "share.sqlite3"))
    get_sharing_service.cache_clear()
    service = get_sharing_service()
    service.update_settings(enabled=True, memory_mode="competition")
    issued = service.issue_host_session("operator")
    try:
        remote = TestClient(
            app,
            base_url="https://muta.test:8443",
            client=("192.168.1.20", 51000),
        )
        remote.cookies.set("muta_share_session", issued.token)
        with remote.websocket_connect("/v1/audio/voice") as ws:
            assert ws.receive_json()["reason"] == "host-local-only"

        local = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 51001))
        local.cookies.set("muta_share_session", issued.token)
        with local.websocket_connect(
            "/v1/audio/voice", headers={"origin": "http://attacker.invalid"}
        ) as ws:
            assert ws.receive_json()["reason"] == "host-local-only"
    finally:
        service.close()
        get_sharing_service.cache_clear()
