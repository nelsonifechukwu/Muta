"""The pedagogy loop, end to end through /v1: question bank, exam scoring, mastery, diagnose.

These were 501 stubs (or orphaned modules) before the production-hardening pass; this proves
they are wired and that the exam-answer → mastery evidence loop actually moves the twin.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orchestrator.gateway import deps, routes
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


def test_offline_unit_checkpoint_verifies_all_five_and_records_mastery(twin_root):
    response = client.post(
        "/v1/units/checkpoint",
        headers=AUTH,
        json={
            "student_id": "stud-1",
            "unit_id": "linear-equations-keeping-the-balance",
            "answers": {"q1": "x = 8", "q2": "-4", "q3": "5", "q4": "3", "q5": "7"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["checked"] is True
    assert body["score"] == 1.0
    assert body["mastery"] == 1.0
    assert body["progress_saved"] is True
    assert len(body["results"]) == 5
    assert all(result["verified"] for result in body["results"])
    mastery = client.get("/v1/mastery/stud-1", headers=AUTH).json()
    assert mastery["mastery"]["linear_equations"] == 1.0


@pytest.mark.parametrize(
    ("unit_id", "topic", "answers"),
    [
        ("forces-and-motion", "forces_motion", {"q1": "0", "q2": "4", "q3": "5", "q4": "12", "q5": "-3"}),
        ("balancing-chemical-equations", "chemical_equations", {"q1": "2", "q2": "1", "q3": "3", "q4": "2", "q5": "3"}),
        ("photosynthesis-energy-flow", "photosynthesis", {"q1": "6", "q2": "6", "q3": "6", "q4": "6", "q5": "12"}),
    ],
)
def test_stem_unit_checkpoints_are_authoritative(twin_root, unit_id, topic, answers):
    response = client.post(
        "/v1/units/checkpoint",
        headers=AUTH,
        json={"student_id": "stud-1", "unit_id": unit_id, "answers": answers},
    )
    assert response.status_code == 200
    assert response.json()["score"] == 1.0
    assert client.get("/v1/mastery/stud-1", headers=AUTH).json()["mastery"][topic] == 1.0


def test_offline_unit_checkpoint_rejects_unknown_or_incomplete_packs(twin_root):
    unknown = client.post(
        "/v1/units/checkpoint",
        headers=AUTH,
        json={"student_id": "stud-1", "unit_id": "imported-unit", "answers": {"q1": "8"}},
    )
    assert unknown.status_code == 404

    incomplete = client.post(
        "/v1/units/checkpoint",
        headers=AUTH,
        json={
            "student_id": "stud-1",
            "unit_id": "linear-equations-keeping-the-balance",
            "answers": {"q1": "8"},
        },
    )
    assert incomplete.status_code == 422


def test_corrupt_authoritative_unit_fails_closed_without_changing_mastery(
    twin_root, monkeypatch
):
    from orchestrator.pedagogy import units

    monkeypatch.setattr(
        units,
        "load_unit",
        lambda _unit_id: (_ for _ in ()).throw(ValueError("bad packaged unit")),
    )
    response = client.post(
        "/v1/units/checkpoint",
        headers=AUTH,
        json={
            "student_id": "stud-1",
            "unit_id": "linear-equations-keeping-the-balance",
            "answers": {"q1": "8", "q2": "-4", "q3": "5", "q4": "3", "q5": "7"},
        },
    )

    assert response.status_code == 503
    assert "no progress was changed" in response.json()["detail"]
    assert deps.get_twin_store().load("stud-1").mastery.get("linear_equations") is None


def test_exam_answer_cannot_forge_verified_unit_mastery(twin_root):
    response = client.post(
        "/v1/exam/answer",
        headers=AUTH,
        json={
            "student_id": "stud-1",
            "topic": "linear_equations",
            "candidate": "1",
            "expected": "1",
        },
    )

    assert response.status_code == 422
    mastery = client.get("/v1/mastery/stud-1", headers=AUTH).json()
    assert "linear_equations" not in mastery["mastery"]


def test_offline_unit_checkpoint_degrades_without_reporting_unpersisted_mastery(
    twin_root, monkeypatch
):
    real_store = deps.get_twin_store()

    class FailingStore:
        def load(self, student_id):
            return real_store.load(student_id)

        def save(self, twin):
            raise OSError("disk full")

    monkeypatch.setattr(routes, "get_twin_store", lambda: FailingStore())
    response = client.post(
        "/v1/units/checkpoint",
        headers=AUTH,
        json={
            "student_id": "stud-1",
            "unit_id": "linear-equations-keeping-the-balance",
            "answers": {"q1": "8", "q2": "-4", "q3": "5", "q4": "3", "q5": "7"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["checked"] is True
    assert body["score"] == 1.0
    assert body["mastery"] == 0.0
    assert body["progress_saved"] is False
    assert real_store.load("stud-1").mastery.get("linear_equations") is None
