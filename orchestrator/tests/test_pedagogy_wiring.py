"""The pedagogy loop, end to end through /v1: question bank, exam scoring, mastery, diagnose.

These were 501 stubs (or orphaned modules) before the production-hardening pass; this proves
they are wired and that the exam-answer → mastery evidence loop actually moves the twin.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orchestrator.gateway import deps
from orchestrator.main import app

client = TestClient(app)
AUTH = {"Authorization": "Bearer stud-1"}  # dev-mode token == student id


@pytest.fixture
def twin_root(tmp_path, monkeypatch):
    monkeypatch.setenv("TUTOR_ROOT", str(tmp_path))
    deps.get_twin_store.cache_clear()
    yield tmp_path
    deps.get_twin_store.cache_clear()


def test_generate_question_returns_real_bank_items(twin_root):
    r = client.post(
        "/v1/generate_question",
        json={"subject": "math", "topic": "quadratic", "difficulty": 3, "count": 2},
    )
    assert r.status_code == 200
    qs = r.json()["questions"]
    assert 1 <= len(qs) <= 2
    assert qs[0]["worked_solution"] and qs[0]["correct_answer"]


def test_exam_answer_correct_raises_mastery(twin_root):
    r = client.post(
        "/v1/exam/answer",
        json={"student_id": "stud-1", "topic": "arithmetic", "candidate": "2+2", "expected": "4"},
        headers=AUTH,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["checked"] is True and body["verified"] is True
    m = client.get("/v1/mastery/stud-1", headers=AUTH).json()
    assert m["mastery"].get("arithmetic", 0.0) > 0.0


def test_exam_answer_wrong_records_zero_and_error(twin_root):
    r = client.post(
        "/v1/exam/answer",
        json={"student_id": "stud-1", "topic": "algebra", "candidate": "5", "expected": "4"},
        headers=AUTH,
    )
    body = r.json()
    assert body["checked"] is True and body["verified"] is False
    m = client.get("/v1/mastery/stud-1", headers=AUTH).json()
    assert m["mastery"].get("algebra") == 0.0
    # algebra is now the weakest topic → diagnose surfaces it.
    d = client.post(
        "/v1/diagnose", json={"student_id": "stud-1", "subject": "math"}, headers=AUTH
    ).json()
    assert "algebra" in d["weak_topics"]


def test_mastery_and_exam_answer_require_auth(twin_root):
    assert client.get("/v1/mastery/stud-1").status_code == 401
    assert (
        client.post(
            "/v1/exam/answer",
            json={"student_id": "stud-1", "topic": "x", "candidate": "1", "expected": "1"},
        ).status_code
        == 401
    )


def test_cannot_submit_or_view_another_students_data(twin_root):
    r = client.post(
        "/v1/exam/answer",
        json={"student_id": "someone-else", "topic": "x", "candidate": "1", "expected": "1"},
        headers=AUTH,
    )
    assert r.status_code == 403
    assert client.get("/v1/mastery/someone-else", headers=AUTH).status_code == 403
