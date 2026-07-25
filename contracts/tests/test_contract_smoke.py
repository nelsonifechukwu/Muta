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


class _FakeStore:
    """Duck-types the ConversationStore surface the conversation routes touch."""

    def __init__(self) -> None:
        self.conversations = {
            "conv-123": {
                "id": "conv-123",
                "student_id": "s1",
                "title": "hello",
                "mode": "socratic",
                "created_at": "2026-07-25T00:00:00+00:00",
                "updated_at": "2026-07-25T00:00:00+00:00",
            }
        }
        self.deleted: list[str] = []

    def list_conversations(self, student_id):
        return [c for c in self.conversations.values() if c["student_id"] == student_id]

    def get_conversation(self, cid):
        return self.conversations.get(cid)

    def delete_conversation(self, cid):
        self.deleted.append(cid)

    def list_messages(self, cid):
        return [
            {
                "id": 1,
                "role": "user",
                "content": "hi",
                "created_at": "2026-07-25T00:00:00+00:00",
                "attachments": [{"id": 7, "kind": "image", "mime": "image/png"}],
            }
        ]

    def get_attachment(self, aid):
        return None  # the smoke test exercises the 404 path

    def link_attachment(self, aid, cid, message_id):
        pass


class _FakeEngine:
    """Stands in for the ChatEngine so /chat is testable without a llama-server."""

    def __init__(self, raises: Exception | None = None) -> None:
        self._raises = raises
        self.store = _FakeStore()

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
    "/v1/chat/stream",
    "/v1/conversations",
    "/v1/conversations/{conversation_id}/messages",
    "/v1/conversations/{conversation_id}",
    "/v1/attachments/{attachment_id}",
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
    r = client.post("/v1/diagnose", json={"student_id": "s1"})
    assert r.status_code == 501


def test_verify_checks_a_claim():
    # /v1/verify is no longer a stub: it runs SymPy in the tool sandbox (TDD §7.5).
    r = client.post("/v1/verify", json={"expression": "d/dx(x^2) == 2*x"})
    assert r.status_code == 200
    assert r.json()["verified"] is False  # d/dx is not evaluated symbolically here

    r = client.post("/v1/verify", json={"expression": "(x+1)^2 == x^2 + 2x + 1"})
    assert r.json()["verified"] is True


def test_verify_rejects_a_non_claim_without_pretending_to_check_it():
    r = client.post("/v1/verify", json={"expression": "the quadratic formula"})
    body = r.json()
    assert body["verified"] is False and "lhs == rhs" in body["detail"]


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


def test_conversations_lists_a_students_threads(override_engine):
    override_engine(_FakeEngine())
    r = client.get("/v1/conversations", params={"student_id": "s1"})
    assert r.status_code == 200
    body = r.json()
    assert body["conversations"][0]["id"] == "conv-123"
    assert body["conversations"][0]["title"] == "hello"


def test_conversation_messages_include_attachment_refs(override_engine):
    override_engine(_FakeEngine())
    r = client.get("/v1/conversations/conv-123/messages")
    assert r.status_code == 200
    msg = r.json()["messages"][0]
    assert msg["attachments"] == [{"id": 7, "kind": "image", "mime": "image/png"}]


def test_conversation_messages_404_for_unknown_thread(override_engine):
    override_engine(_FakeEngine())
    r = client.get("/v1/conversations/nope/messages")
    assert r.status_code == 404


def test_conversation_delete(override_engine):
    engine = _FakeEngine()
    override_engine(engine)
    r = client.delete("/v1/conversations/conv-123")
    assert r.status_code == 200
    assert r.json() == {"id": "conv-123", "deleted": True}
    assert engine.store.deleted == ["conv-123"]


def test_attachment_404_for_unknown_id(override_engine):
    override_engine(_FakeEngine())
    r = client.get("/v1/attachments/999")
    assert r.status_code == 404
