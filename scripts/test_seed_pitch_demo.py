from __future__ import annotations

from orchestrator.gateway.sharing import SharingService
from runtime.sqlite_memory import SQLiteConversationStore
from scripts.seed_pitch_demo import COURSE_NAME, QUESTION, seed_demo


def test_pitch_seed_is_complete_and_idempotent(tmp_path):
    first = seed_demo(tmp_path, password="MutaDemo2026!")
    second = seed_demo(tmp_path, password="MutaDemo2026!")

    assert first == second
    service = SharingService(tmp_path / "muta-share.sqlite3")
    store = SQLiteConversationStore(f"sqlite:///{tmp_path / 'muta.sqlite3'}")
    try:
        assert service.settings()["enabled"] is True
        assert [row["name"] for row in service.courses()] == [COURSE_NAME]
        course = service.courses()[0]
        assert course["teaching_style"] == "hints"
        assert course["lock_style"] is True
        assert course["withhold_final_answers"] is True
        posts = [row for row in service.class_posts(limit=100) if row["body"] == QUESTION]
        assert len(posts) == 1
        thread = service.class_thread(posts[0]["id"])
        assert len(thread["replies"]) == 2
        assert sum(row["teacher_verified"] for row in thread["replies"]) == 1
        settings = store.get_settings(first["learners"]["Ada"])
        assert settings["study_country"] == "NG"
        assert settings["preferred_style"] == "analogy"
    finally:
        store.close()
        service.close()
