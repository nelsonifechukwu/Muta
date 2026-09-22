"""Heldout identity, leakage, exact arithmetic and semantic-reducer contract tests."""

from __future__ import annotations

import copy
import importlib.util
import json
from collections import Counter
from fractions import Fraction
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "heldout_curriculum", Path(__file__).with_name("heldout_curriculum.py")
)
assert SPEC and SPEC.loader
heldout = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(heldout)


def test_exact_grid_fixed_balanced_splits_and_never_train():
    rows = heldout.build_cases()
    assert len(rows) == len({r["id"] for r in rows}) == 16
    assert Counter((r["subject"], r["capabilities"][0]) for r in rows) == Counter(
        (s, c) for s in heldout.SUBJECTS for c in heldout.GROUPS
    )
    assert Counter((r["subject"], r["split"]) for r in rows) == Counter(
        {(s, p): 2 for s in heldout.SUBJECTS for p in ("dev", "final")}
    )
    for split in ("dev", "final"):
        assert Counter(r["capabilities"][0] for r in rows if r["split"] == split) == Counter(
            {c: 2 for c in heldout.GROUPS}
        )
    assert not (
        {r["group_id"] for r in rows if r["split"] == "dev"}
        & {r["group_id"] for r in rows if r["split"] == "final"}
    )
    for row in rows:
        assert row["train_eligible"] is False
        assert row["usage"] == "evaluation_only_never_train"
        assert row["split"] == row["original_split"]
        assert row["eligibility"] == "pending_independent_review_and_overlap_screen"
        assert row["quality"]["all_statements_independently_verified"] is False


def test_complete_context_and_explicit_learner_request():
    for row in heldout.build_cases():
        assert [m["role"] for m in row["messages"]] == ["user", "assistant", "user"]
        assert all(len(m["content"].split()) >= 8 for m in row["messages"])
        assert row["messages"][-1]["content"].endswith(heldout.REQUEST)
        assert len(row["student_misconception"].split()) > 5
        assert len(row["expected_core_science"]) == 4
        assert row["reference_ids"]
        assert all(ref in heldout.REFERENCES for ref in row["reference_ids"])
        assert all("https://" not in m["content"] for m in row["messages"])


def test_model_input_excludes_rubrics_answers_and_source_notes():
    for row in heldout.build_cases():
        payload = heldout.model_input(row)
        assert set(payload) == {"id", "group_id", "split", "messages"}
        assert payload["messages"] == row["messages"]
        assert payload["messages"] is not row["messages"]
        assert "expected_core_science" not in payload
        assert "numeric_checks" not in payload
        assert "reference_urls" not in payload
        payload["messages"][0]["content"] = "changed"
        assert row["messages"][0]["content"] != "changed"


def test_rubric_has_four_semantic_criteria_per_axis_and_error_cap():
    for row in heldout.build_cases():
        rubric = row["rubric"]
        assert [c["id"] for c in rubric["science"]] == ["S1", "S2", "S3", "S4"]
        assert [c["id"] for c in rubric["tutoring"]] == ["T1", "T2", "T3", "T4"]
        assert len(rubric["critical_errors"]) == 2
        assert all(c["points"] == 1 for axis in ("science", "tutoring") for c in rubric[axis])
        assert "not keyword presence" in rubric["judge_requirement"]
        assert "caps science at 1/4" in rubric["critical_error_rule"]


def test_exact_independent_numeric_answers():
    expected = {
        "logger_energy": Fraction(6),
        "logger_average": Fraction(6),
        "oxide_product": Fraction(1, 5),
        "oxygen_left": Fraction(1, 20),
        "division_intervals": Fraction(3),
        "cell_count": Fraction(160),
        "clock_halflives": Fraction(4),
        "clock_age": Fraction(9600000),
    }
    assert heldout.independent_numeric_values() == expected
    seen = []
    for row in heldout.build_cases():
        assert bool(row["numeric_checks"]) == (row["capabilities"] == ["quantitative"])
        answers = {
            c["id"]: {"value": str(expected[c["id"]]), "unit": c["canonical_unit"]}
            for c in row["numeric_checks"]
        }
        assert all(r["passed"] for r in heldout.check_numeric_answers(row, answers).values())
        seen.extend(answers)
    assert Counter(seen) == Counter(expected.keys())


def test_numeric_equivalent_units_and_wrong_dimensions():
    row = next(r for r in heldout.build_cases() if r["source_id"] == "logger-two-power-modes")
    answers = {
        "logger_energy": {"value": "21.6", "unit": "kJ"},
        "logger_average": {"value": "0.006", "unit": "kW"},
    }
    assert all(r["passed"] for r in heldout.check_numeric_answers(row, answers).values())
    answers["logger_energy"] = {"value": "6", "unit": "W"}
    assert heldout.check_numeric_answers(row, answers)["logger_energy"] == {
        "passed": False,
        "reason": "unsupported_or_wrong_unit",
    }
    answers["logger_energy"] = {"value": "21", "unit": "Wh"}
    assert heldout.check_numeric_answers(row, answers)["logger_energy"]["passed"] is False


@pytest.mark.parametrize("bad", ["NaN", "inf", "1/0", "6 Wh"])
def test_invalid_numbers_fail_explicitly(bad):
    row = next(r for r in heldout.build_cases() if r["source_id"] == "logger-two-power-modes")
    with pytest.raises(ValueError, match="Invalid finite"):
        heldout.check_numeric_answers(
            row,
            {
                "logger_energy": {"value": bad, "unit": "Wh"},
                "logger_average": {"value": "6", "unit": "W"},
            },
        )


def test_missing_extra_or_wrong_case_numeric_keys_are_rejected():
    row = next(r for r in heldout.build_cases() if r["source_id"] == "logger-two-power-modes")
    with pytest.raises(ValueError, match="keys must exactly match"):
        heldout.check_numeric_answers(row, {})


def judgment(flag, value, response):
    return {
        flag: value,
        "evidence": [response] if value else [],
        "rationale": "Explicit test assessor judgment; this function does not validate its semantics.",
    }


def assessment_fixture(row, response, met=True):
    return {
        "science": {c["id"]: judgment("met", met, response) for c in row["rubric"]["science"]},
        "tutoring": {c["id"]: judgment("met", met, response) for c in row["rubric"]["tutoring"]},
        "critical_errors": {
            c["id"]: judgment("present", False, response) for c in row["rubric"]["critical_errors"]
        },
        "additional_errors": [],
    }


def test_semantic_reducer_boundaries_and_provenance():
    row = heldout.build_cases()[0]
    response = "A test response supplied to the reducer, not automatically semantically graded."
    for met, score in ((True, 4), (False, 0)):
        assessment = assessment_fixture(row, response, met)
        result = heldout.score_assessment(row, response, assessment)
        assert result["science"] == result["tutoring"] == score
        assert result["case_id"] == row["id"]
        assert result["response_sha256"] == heldout.sha(response.encode())
        assert result["semantic_judge_validated_by_this_function"] is False


def test_listed_and_unlisted_critical_errors_cap_science_not_tutoring():
    row = heldout.build_cases()[0]
    response = "Response evidence for the synthetic scoring-contract test."
    for additional in (False, True):
        assessment = assessment_fixture(row, response)
        if additional:
            assessment["additional_errors"] = [judgment("present", True, response)]
        else:
            assessment["critical_errors"]["E1"] = judgment("present", True, response)
        result = heldout.score_assessment(row, response, assessment)
        assert result["science"] == 1
        assert result["science_before_critical_cap"] == result["tutoring"] == 4
        assert result["critical_errors_present"] == 1


@pytest.mark.parametrize(
    "change",
    [
        "extra_id",
        "missing_error",
        "integer_flag",
        "invented_evidence",
        "empty_positive",
        "empty_rationale",
    ],
)
def test_malformed_or_unsubstantiated_assessments_rejected(change):
    row = heldout.build_cases()[0]
    response = "Actual model response text."
    assessment = assessment_fixture(row, response)
    if change == "extra_id":
        assessment["science"]["S5"] = judgment("met", True, response)
    elif change == "missing_error":
        del assessment["critical_errors"]["E1"]
    elif change == "integer_flag":
        assessment["science"]["S1"]["met"] = 1
    elif change == "invented_evidence":
        assessment["science"]["S1"]["evidence"] = ["not actually present"]
    elif change == "empty_positive":
        assessment["science"]["S1"]["evidence"] = []
    elif change == "empty_rationale":
        assessment["science"]["S1"]["rationale"] = "  "
    with pytest.raises(ValueError):
        heldout.score_assessment(row, response, assessment)


def test_duplicate_cells_and_bad_split_fail_before_artifacts(monkeypatch, tmp_path):
    changed = copy.deepcopy(heldout.CASES)
    changed[0]["split"] = "train"
    monkeypatch.setattr(heldout, "CASES", changed)
    with pytest.raises(ValueError, match="two dev and two final"):
        heldout.build(tmp_path / "data", tmp_path / "provenance")
    assert not (tmp_path / "data").exists()


def test_changed_numeric_gold_is_rejected(monkeypatch):
    changed = dict(heldout.NUMERIC)
    _value, unit, units, span = changed["cell_count"]
    changed["cell_count"] = ("26", unit, units, span)
    monkeypatch.setattr(heldout, "NUMERIC", changed)
    with pytest.raises(ValueError, match="Numeric/rubric mismatch"):
        heldout.build_cases()


def test_deterministic_all_case_packet_and_answer_free_prompt_files(tmp_path):
    output, provenance = tmp_path / "data", tmp_path / "provenance"
    manifest = heldout.build(output, provenance)
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert heldout.build(output, provenance) == manifest
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    packet = [
        json.loads(line)
        for line in (provenance / "heldout16-review-packet.jsonl").read_text().splitlines()
    ]
    assert len(packet) == 16
    assert [item["case"] for item in packet] == heldout.build_cases()
    assert manifest["train"] == 0
    assert manifest["numeric_checks"] == 8
    for split in ("dev", "final"):
        cases = [
            json.loads(line) for line in (output / f"{split}_cases.jsonl").read_text().splitlines()
        ]
        prompts = [
            json.loads(line)
            for line in (output / f"{split}_prompts.jsonl").read_text().splitlines()
        ]
        assert len(cases) == len(prompts) == 8
        assert prompts == [heldout.model_input(c) for c in cases]
    for artifact in manifest["artifacts"].values():
        assert heldout.sha(Path(artifact["path"]).read_bytes()) == artifact["sha256"]
