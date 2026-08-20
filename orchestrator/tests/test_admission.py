"""Admission control on the UI's real chat path (/v1/chat/stream), not just the /tutor twin."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from orchestrator.gateway import deps
from orchestrator.gateway.sessions import SessionManager
from orchestrator.main import app

client = TestClient(app)


class _StreamEngine:
    """Minimal ChatEngine stand-in whose stream yields a couple of tokens."""

    def stream_events_chat(self, **kwargs):
        return "conv-1", 1, iter([("content", "Two plus two is four.")])


@pytest.fixture
def _fakes():
    app.dependency_overrides[deps.get_engine] = lambda: _StreamEngine()
    yield
    app.dependency_overrides.clear()


def _done(text: str) -> dict:
    return json.loads([ln for ln in text.splitlines() if '"done": true' in ln][-1][len("data: "):])


def test_stream_done_carries_admission_state_and_releases_the_slot(_fakes):
    body = client.post(
        "/v1/chat/stream",
        headers={"Authorization": "Bearer s1"},
        json={"student_id": "s1", "message": "2+2?"},
    ).text
    done = _done(body)
    assert "degradation_level" in done and done["queued"] is False
    # The slot was released: the manager reports no active sessions after the stream drained.
    assert deps.get_sessions().status().get("active", 0) == 0


def test_stream_refuses_when_the_ladder_says_no_new_sessions(_fakes):
    # The one slot is busy with another student and the ladder (L3) refuses new sessions →
    # the newcomer is refused with a friendly message rather than piling onto the engine.
    refusing = SessionManager(slots_count=1, accepts_new_sessions=lambda: False)
    refusing.acquire("someone-else")  # occupy the only slot (busy, not idle-stealable)
    app.dependency_overrides[deps.get_sessions] = lambda: refusing
    r = client.post(
        "/v1/chat/stream",
        headers={"Authorization": "Bearer newcomer"},
        json={"student_id": "newcomer", "message": "hi"},
    )
    assert r.status_code == 503
    assert "detail" in r.json()  # a friendly busy message, not a stack trace
