"""Contract smoke tests — prove the wiring and that the `/v1` surface is complete.

These use the in-process app (no network). `make contract-test` runs schemathesis against
a live server for property-based fuzzing on top of this.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from orchestrator.gateway.deps import get_engine
from orchestrator.main import app
from runtime.chat import ChatResult

client = TestClient(app)


class _FakeEngine:
    """Stands in for the ChatEngine so /chat is testable without a llama-server."""

    def __init__(self, raises: Exception | None = None) -> None:
        self._raises = raises

    def chat(self, **kwargs) -> ChatResult:
        if self._raises:
            raise self._raises
        return ChatResult(conversation_id="conv-123", reply="ok")


@pytest.fixture
def override_engine():
    def _apply(engine):
        app.dependency_overrides[get_engine] = lambda: engine

    yield _apply
    app.dependency_overrides.clear()

PUBLIC_PATHS = [
    "/v1/health",
    "/v1/ready",
    "/v1/chat",
    "/v1/diagnose",
    "/v1/generate_question",
    "/v1/mastery/{student_id}",
    "/v1/verify",
]


def test_health_ok():
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ready_shape():
    r = client.get("/v1/ready")
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"ready", "checks"}


def test_openapi_exposes_full_v1_contract():
    paths = app.openapi()["paths"]
    for p in PUBLIC_PATHS:
        assert p in paths, f"contract is missing {p}"


def test_internal_services_are_not_in_public_contract():
    # Mounted sub-apps are implementation detail — they must not leak into /v1's schema.
    paths = app.openapi()["paths"]
    assert not any(p.startswith("/internal") for p in paths)


def test_stubbed_endpoints_return_501_not_500():
    # A declared-but-unimplemented endpoint is 501, never a crash.
    r = client.post("/v1/verify", json={"expression": "1+1 == 2"})
    assert r.status_code == 501


def test_chat_rejects_malformed_body():
    # Validation runs before the engine dependency, so this needs no override.
    r = client.post("/v1/chat", json={"message": "no student id"})
    assert r.status_code == 422


def test_chat_returns_reply_and_conversation_id(override_engine):
    override_engine(_FakeEngine())
    r = client.post("/v1/chat", json={"student_id": "s1", "message": "hi"})
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "ok"
    assert body["conversation_id"] == "conv-123"


def test_chat_returns_503_when_inference_unreachable(override_engine):
    override_engine(_FakeEngine(raises=httpx.ConnectError("no server")))
    r = client.post("/v1/chat", json={"student_id": "s1", "message": "hi"})
    assert r.status_code == 503
