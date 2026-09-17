import json
from pathlib import Path

import pytest

from corpus.audit_training_intake import (
    EXPRESSIVE_SOURCE_KEYS,
    _manifest_consistency,
    classify_labels,
    make_row_decision,
    map_existing_topic_to_broad,
    sha256_file,
)


def fixture_record(**overrides):
    record = {
        "record_id": "waec-test-record-0001",
        "subject": "physics",
        "year": 2024,
        "paper": "Paper 2",
        "question_format": "free_response",
        "question_text": "Calculate the current in a simple circuit.",
        "options": [],
        "correct_answer": None,
        "worked_solution": None,
        "marking_scheme": None,
        "examiner_observation": None,
        "generated_solution": None,
        "answer_status": "missing",
        "content_status": "complete",
        "assets": [],
        "extraction_warnings": [],
        "source": {"source_type": "waec_html"},
    }
    record.update(overrides)
    return record


def test_classification_emits_only_broad_labels():
    topics, skills = classify_labels(fixture_record())
    assert "electricity_and_circuits" in topics
    assert "calculation" in skills


def test_deepmind_topics_map_to_existing_broad_coverage():
    assert map_existing_topic_to_broad("numbers_gcd_composed") == "number_and_numeration"
    assert map_existing_topic_to_broad("probability_swr_p_sequence") == "probability"
    assert map_existing_topic_to_broad("algebra_sequence_nth_term") == "sequences_and_series"


def test_missing_answer_is_blocked_and_never_copied():
    decision = make_row_decision(fixture_record())
    assert decision["training_decision"] == "blocked"
    assert decision["answer_assurance"] == "missing"
    assert decision["answer_independently_verified"] is False
    assert "answer_missing" in decision["exclusion_reasons"]
    assert not (EXPRESSIVE_SOURCE_KEYS & decision.keys())
    serialized = json.dumps(decision)
    assert "Calculate the current" not in serialized


def test_publisher_answer_is_not_treated_as_independent_verification():
    decision = make_row_decision(
        fixture_record(
            correct_answer="2 A",
            worked_solution="A publisher calculation.",
            answer_status="published",
        )
    )
    assert decision["answer_assurance"] == "publisher_only"
    assert decision["answer_independently_verified"] is False
    assert "answer_not_independently_verified" in decision["exclusion_reasons"]


def test_manifest_consistency_reports_pre_dedupe_count_mismatch():
    rows = [
        {"source": {"source_type": "waec_html"}},
        {"source": {"source_type": "cheetah_pdf"}},
    ]
    manifest = {
        "coverage": {
            "total_records": 2,
            "by_source": {"waec_html": 1, "cheetah_pdf": 1},
        },
        "sources": {"waec": {"records": 3}, "cheetah": {"records": 1}},
    }
    result = _manifest_consistency(manifest, rows)
    assert result["consistent"] is False
    assert result["mismatches"] == [
        {"field": "sources.waec.records", "declared": 3, "actual": 1}
    ]


def test_checked_in_corpus_hash_and_row_count_are_stable():
    path = Path(__file__).resolve().parents[1] / "waec" / "questions.jsonl"
    if not path.is_file():
        pytest.skip("private WAEC corpus snapshot is intentionally absent")
    assert sha256_file(path) == "80763c51494653901a996d7735253a07e810b1e0f7c5debd50f92170237d0509"
    assert sum(1 for line in path.open(encoding="utf-8") if line.strip()) == 1906
