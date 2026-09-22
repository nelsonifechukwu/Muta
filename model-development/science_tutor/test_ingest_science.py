import importlib.util
import json
from pathlib import Path

import pytest

MODULE = Path(__file__).with_name("ingest_science.py")
SPEC = importlib.util.spec_from_file_location("ingest_science", MODULE)
science = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(science)


def test_offline_normalization_checks_preserved_bytes(tmp_path):
    root, receipts = tmp_path / "raw", tmp_path / "receipts"
    receipts.mkdir()
    (root / "scienceqa").mkdir(parents=True)
    files = []
    for name, url in science.FILES["scienceqa"].items():
        path = root / "scienceqa" / name
        path.write_bytes(b"original")
        files.append({"source": "scienceqa", "path": str(path), "url": url,
                      "revision": science.PINS["scienceqa"], "bytes": 8,
                      "sha256": science.sha256_bytes(b"original")})
    (receipts / "science-downloads.json").write_text(json.dumps({"files": files}))
    assert len(science.verify_raw_inputs("scienceqa", root, receipts)) == 3
    (root / "scienceqa" / "README.md").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="changed"):
        science.verify_raw_inputs("scienceqa", root, receipts)


def scienceqa(**changes):
    row = {
        "subject": "natural science",
        "topic": "biology",
        "image": None,
        "question": "Which structure contains a plant cell's DNA?",
        "hint": "",
        "lecture": "",
        "solution": "The nucleus contains most of a plant cell's DNA and controls many cellular activities.",
        "choices": ["nucleus", "cell wall"],
        "answer": 0,
        "split": "test",
    }
    row.update(changes)
    return row


def test_source_test_partition_preserved():
    row, error = science.normalize_scienceqa("123", scienceqa())
    assert error is None
    assert row["source_split"] == "test"
    assert row["group_id"] == "scienceqa:123"
    assert row["messages"][0]["role"] == "user"
    assert not row["quality"]["independent_verification"]


def test_exclude_image_even_if_question_seems_standalone():
    assert science.normalize_scienceqa("x", scienceqa(image="image.png"))[1] == "image_present"


def test_text_visual_dependency_and_broken_markup():
    assert (
        science.normalize_scienceqa("x", scienceqa(question="Look at the diagram. What is A?"))[0]
        is None
    )
    assert (
        science.normalize_scienceqa(
            "x", scienceqa(solution="The <img src='foo'> proves this is the right answer.")
        )[0]
        is None
    )
    assert (
        science.normalize_scienceqa(
            "x",
            scienceqa(
                solution="Look at each picture and decide which material is smoother to touch."
            ),
        )[0]
        is None
    )
    assert (
        science.normalize_scienceqa(
            "x", scienceqa(lecture="Look at the pencil drawing to compare lengths.")
        )[0]
        is None
    )


def test_independent_review_family_exclusions():
    assert (
        science.normalize_scienceqa("x", scienceqa(skill="Identify rocks using properties"))[1]
        == "reviewed_family_rock_mineral_overgeneralization"
    )
    assert (
        science.normalize_scienceqa("x", scienceqa(skill="Identify minerals using properties"))[0]
        is None
    )
    assert (
        science.normalize_scienceqa("x", scienceqa(skill="How do mass and force affect motion?"))[0]
        is None
    )
    assert (
        science.normalize_scienceqa(
            "x",
            scienceqa(
                solution="The copper turns green because the newly formed copper oxide has a green colour."
            ),
        )[1]
        == "reviewed_family_green_copper_chemistry"
    )
    assert (
        science.normalize_scienceqa(
            "x", scienceqa(question="What happens when polish removes tarnish from silver?")
        )[1]
        == "reviewed_family_ambiguous_silver_polishing"
    )


def test_invalid_answer_index_and_non_science():
    assert science.normalize_scienceqa("x", scienceqa(answer=True))[0] is None
    assert science.normalize_scienceqa("x", scienceqa(answer=2))[0] is None
    assert science.normalize_scienceqa("x", scienceqa(subject="language science"))[0] is None


def test_context_is_only_added_to_question_and_lecture_not_leaked():
    row, _ = science.normalize_scienceqa(
        "x",
        scienceqa(hint="A typical plant cell is being considered.", lecture="TEACHER-ONLY LECTURE"),
    )
    assert "A typical plant cell" in row["messages"][0]["content"]
    assert "TEACHER-ONLY" not in row["messages"][0]["content"]


def sciq(**changes):
    row = {
        "question": "Which organelle contains DNA?",
        "correct_answer": "nucleus",
        "distractor1": "wall",
        "distractor2": "membrane",
        "distractor3": "vacuole",
        "support": "The nucleus contains genetic information in the form of DNA, which helps direct the activities of a cell.",
    }
    row.update(changes)
    return row


def test_sciq_deterministic_rotation_and_grounded_support():
    rows = [science.normalize_sciq("train", n, sciq())[0] for n in range(50)]
    assert len({r["answer_index"] for r in rows}) == 4
    assert all(r["choices"][r["answer_index"]] == "nucleus" for r in rows)
    assert all(r["subject"] == "science_unspecified" for r in rows)
    assert (
        science.normalize_sciq(
            "train",
            1,
            sciq(
                support="There is no answer in this unrelated passage, which has enough words to pass the size check."
            ),
        )[0]
        is None
    )


def test_sciq_duplicate_choices_rejected():
    assert science.normalize_sciq("train", 1, sciq(distractor1="NUCLEUS"))[0] is None


def test_sciinstruct_no_fabricated_answer_key_or_correctness():
    row, reason = science.normalize_sciinstruct(
        1,
        {
            "content": "Explain why a metal spoon can conduct heat.",
            "summary": "Metals have mobile electrons that transfer energy through the material, while vibrations of the lattice also contribute to thermal conduction.",
            "subject": "physics",
        },
    )
    assert reason is None and row["answer"] is None
    assert row["quality"]["tier"] == "synthetic_source_explanation_unverified"
    assert not row["quality"]["independent_check"]
    assert row["quality"]["admission"].startswith("quarantine")


def test_sciinstruct_rejects_advanced_and_nonenglish():
    item = {
        "content": "Find the canonical transformation of this Hamiltonian.",
        "summary": "A" * 100,
        "subject": "physics",
    }
    assert science.normalize_sciinstruct(1, item)[1] == "advanced_topic_outside_school_pilot"
    item["content"] = "This contains some non-English text: 中文"
    assert science.normalize_sciinstruct(1, item)[1] == "non_english_text"


def test_receipt_counts_reconcile(tmp_path):
    result = science.write_candidates(
        "scienceqa",
        [("test", "good", scienceqa()), ("test", "bad", scienceqa(image="x"))],
        tmp_path / "data",
        tmp_path / "receipts",
    )
    assert result["source_rows_examined"] == result["candidate_rows"] + result["excluded_rows"]
    assert result["candidate_rows_by_source_split"] == {"test": 1}
    assert result["audit_status"] == "pending_independent_review"


def test_jsonl_extension_mismatch_and_malformed_line():
    import pytest

    assert science.read_source_json('{"content":"a"}\n{"content":"b"}\n') == [
        {"content": "a"},
        {"content": "b"},
    ]
    assert science.read_source_json('[{"content":"a"}]') == [{"content": "a"}]
    with pytest.raises(ValueError):
        science.read_source_json('{"content":"a"}\nBROKEN\n')


def test_synthetic_source_quarantined_even_if_mechanical_checks_pass(tmp_path):
    item = {
        "content": "Explain why a metal spoon can conduct heat.",
        "summary": "Metals have mobile electrons that transfer energy through the material, while vibrations of the lattice also contribute to thermal conduction.",
        "subject": "physics_chemistry",
    }
    result = science.write_candidates(
        "sciinstruct", [("train", 0, item)], tmp_path / "data", tmp_path / "receipt"
    )
    assert result["candidate_rows"] == 0
    assert result["excluded_rows"] == 1
    assert result["unverified_synthetic_rows_passing_mechanical_screen_but_quarantined"] == 1
