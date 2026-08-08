"""End-to-end student journey through the real /v1 app: sign in, stream a lesson, persist it,
reload history, stay isolated from other students, score an exam answer into mastery, delete.

Uses a real ConversationStore (the compose db) with a fake inference client, so persistence,
auth/ownership, admission and the pedagogy loop are all exercised together without needing a
llama-server. Skips cleanly when the db is down (same policy as the store unit tests).
"""

from __future__ import annotations

import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from orchestrator.gateway import deps
from orchestrator.main import app
from runtime.chat import ChatEngine
from runtime.client import Generation
from runtime.memory import ConversationStore

_DSN = os.environ.get("MUTA_TEST_DB_URL", "postgresql://muta:muta@127.0.0.1:15432/muta")


class _FakeClient:
    last_source = "local"

    def stream_events(self, messages, **kw):
        # An explicit standalone identity line so the conservative self-check has something to
        # verify (inline-with-prose equations are deliberately not checked).
        yield ("content", "Let's add them.\n2 + 2 = 4\nSo the total is four.")

    def chat_with_timings(self, messages, **kw):
        return Generation(
            text="Two plus two is four.", prompt_tokens=1, completion_tokens=5,
            elapsed_s=0.1, tokens_per_second=50.0, from_wall_clock=True,
        )


@pytest.fixture
def journey(tmp_path, monkeypatch):
    try:
        store = ConversationStore(_DSN)
    except Exception:  # noqa: BLE001 — db down → skip, don't fail (Makefile contract)
        pytest.skip("compose db not reachable; run `docker compose up -d db`")
    engine = ChatEngine(_FakeClient(), store, max_history_messages=20)
    app.dependency_overrides[deps.get_engine] = lambda: engine
    monkeypatch.setenv("TUTOR_ROOT", str(tmp_path))
    deps.get_twin_store.cache_clear()
    client = TestClient(app)
    yield client, store
    app.dependency_overrides.clear()
    deps.get_twin_store.cache_clear()
    store.close()


def _token(client, student_id):
    r = client.post("/v1/auth/session", json={"student_id": student_id})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _done(text):
    return json.loads([ln for ln in text.splitlines() if '"done": true' in ln][-1][len("data: "):])


def test_full_student_journey(journey):
    client, _store = journey
    alice = f"alice-{uuid.uuid4().hex[:8]}"
    mallory = f"mallory-{uuid.uuid4().hex[:8]}"
    a_auth = _token(client, alice)

    # 1. Alice streams a lesson; the done event carries the self-check + admission state.
    body = client.post("/v1/chat/stream", json={"student_id": alice, "message": "what is 2+2?"}).text
    done = _done(body)
    cid = done["conversation_id"]
    assert done["verified"] is True  # "2 + 2 = 4" checked out
    assert "degradation_level" in done

    # 2. The thread persisted and shows up in her sidebar, with the turns.
    convos = client.get("/v1/conversations", params={"student_id": alice}, headers=a_auth).json()
    assert cid in [c["id"] for c in convos["conversations"]]
    msgs = client.get(f"/v1/conversations/{cid}/messages", headers=a_auth).json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]

    # 3. Mallory cannot see or delete Alice's thread (ownership isolation).
    m_auth = _token(client, mallory)
    assert client.get(f"/v1/conversations/{cid}/messages", headers=m_auth).status_code == 404
    assert client.delete(f"/v1/conversations/{cid}", headers=m_auth).status_code == 404
    assert client.get("/v1/conversations/messages", headers=m_auth).status_code in (404, 405)

    # 4. Alice practises an exam question; a correct answer moves her mastery.
    r = client.post(
        "/v1/exam/answer",
        json={"student_id": alice, "topic": "arithmetic", "candidate": "2+2", "expected": "4"},
        headers=a_auth,
    )
    assert r.json()["verified"] is True
    mastery = client.get(f"/v1/mastery/{alice}", headers=a_auth).json()
    assert mastery["mastery"].get("arithmetic", 0.0) > 0.0

    # 5. Alice erases her own data; the thread is gone.
    erased = client.request("DELETE", f"/v1/students/{alice}", headers=a_auth)
    assert erased.status_code == 200 and erased.json()["conversations"] >= 1
    assert client.get(f"/v1/conversations/{cid}/messages", headers=a_auth).status_code == 404
