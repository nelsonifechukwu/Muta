"""Learning-twin tests (TDD §8.4, T12).

The twin is both the personalisation state and the prompt's session-summary layer, so a
corrupt or half-written twin degrades two things at once — which is why the write path gets
as much attention here as the arithmetic.
"""

from __future__ import annotations

import json

from orchestrator.pedagogy.twin import MAX_SUMMARIES, LearningTwin, TwinStore


def test_mastery_updates_are_smoothed_not_replaced():
    """One lucky answer must not declare mastery, and one slip must not erase it."""
    twin = LearningTwin("ada")
    assert twin.record_mastery("quadratics", 1.0) == 1.0  # first observation stands alone
    after_slip = twin.record_mastery("quadratics", 0.0)
    assert 0.5 < after_slip < 1.0


def test_mastery_is_clamped():
    twin = LearningTwin("ada")
    assert twin.record_mastery("x", 5.0) == 1.0
    assert twin.record_mastery("y", -3.0) == 0.0


def test_weakest_and_top_errors_drive_the_next_lesson():
    twin = LearningTwin("ada")
    for node, score in [("indices", 0.2), ("surds", 0.9), ("bearings", 0.4)]:
        twin.record_mastery(node, score)
    twin.record_error("sign-error", 3)
    twin.record_error("units-dropped")
    assert twin.weakest(2) == ["indices", "bearings"]
    assert twin.top_errors(1) == ["sign-error"]


def test_summaries_are_capped_because_they_go_into_every_prompt():
    twin = LearningTwin("ada")
    for i in range(MAX_SUMMARIES + 4):
        twin.add_summary(f"session {i}")
    assert len(twin.summaries) == MAX_SUMMARIES
    assert twin.summaries[-1] == f"session {MAX_SUMMARIES + 3}"


def test_blank_summaries_are_ignored():
    twin = LearningTwin("ada")
    twin.add_summary("   ")
    assert twin.summaries == []


def test_prompt_summary_is_short_because_it_cannot_be_cache_reused():
    """It sits after the shared prefix (§7.3), so every character is per-student context that
    each turn must re-prefill."""
    twin = LearningTwin("ada")
    twin.record_mastery("indices", 0.1)
    twin.record_error("sign-error", 2)
    twin.add_summary("x" * 2000)
    summary = twin.prompt_summary(max_chars=300)
    assert len(summary) <= 300
    assert "indices" in summary and "sign-error" in summary


def test_prompt_summary_of_a_new_student_is_empty_not_noise():
    assert LearningTwin("new").prompt_summary() == ""


# --- persistence --------------------------------------------------------------------------


def test_round_trip(tmp_path):
    store = TwinStore(tmp_path / "twins")
    twin = LearningTwin("ada")
    twin.record_mastery("quadratics", 0.8)
    twin.record_error("sign-error")
    twin.bump("minutes", 12.5)
    twin.add_summary("Factorised three quadratics unaided.")
    store.save(twin)

    loaded = store.load("ada")
    assert loaded.mastery == twin.mastery
    assert loaded.error_counts == {"sign-error": 1}
    assert loaded.pace == {"minutes": 12.5}
    assert loaded.summaries == twin.summaries


def test_unknown_student_gets_a_blank_twin_not_an_error(tmp_path):
    twin = TwinStore(tmp_path / "twins").load("never-seen")
    assert twin.student_id == "never-seen" and twin.mastery == {}


def test_writes_are_atomic_so_a_power_cut_cannot_truncate_a_twin(tmp_path):
    """tmp → fsync → rename: a reader sees the old twin or the new one, never half of one."""
    store = TwinStore(tmp_path / "twins")
    store.save(LearningTwin("ada", mastery={"a": 0.5}))

    seen: list[str] = []
    original = json.dump

    def failing_dump(obj, fh, **kw):
        original(obj, fh, **kw)
        seen.append("wrote")
        raise OSError("power cut")

    import orchestrator.pedagogy.twin as twin_mod

    twin_mod.json.dump = failing_dump
    try:
        try:
            store.save(LearningTwin("ada", mastery={"a": 0.9}))
        except OSError:
            pass
    finally:
        twin_mod.json.dump = original

    assert seen, "the failure must happen after a partial write, or this proves nothing"
    assert store.load("ada").mastery == {"a": 0.5}, "the old twin must survive intact"
    assert not list((tmp_path / "twins").glob(".twin-*")), "no temp files left behind"


def test_a_corrupt_twin_is_quarantined_not_overwritten(tmp_path):
    """Personalisation is lost; the session is not. The bad file is kept as evidence."""
    store = TwinStore(tmp_path / "twins")
    path = store.path_for("ada")
    path.write_text("{not json")

    twin = store.load("ada")
    assert twin.mastery == {}
    assert path.with_suffix(".json.corrupt").is_file()


def test_unknown_fields_from_a_future_schema_are_ignored(tmp_path):
    store = TwinStore(tmp_path / "twins")
    store.path_for("ada").write_text(json.dumps({"mastery": {"a": 1.0}, "invented_field": 42}))
    assert store.load("ada").mastery == {"a": 1.0}


def test_student_ids_cannot_escape_the_twin_directory(tmp_path):
    store = TwinStore(tmp_path / "twins")
    assert store.path_for("../../etc/passwd").parent == (tmp_path / "twins")


def test_all_ids_lists_known_students(tmp_path):
    store = TwinStore(tmp_path / "twins")
    for name in ("ada", "bimpe"):
        store.save(LearningTwin(name))
    assert store.all_ids() == ["ada", "bimpe"]
