"""Structural/numeric gates, not a substitute for independent scientific review."""

from __future__ import annotations

import copy
import importlib.util
import json
from collections import Counter
from fractions import Fraction
from pathlib import Path
from urllib.parse import urlparse

import pytest

SPEC = importlib.util.spec_from_file_location(
    "authored_curriculum", Path(__file__).with_name("authored_curriculum.py")
)
assert SPEC and SPEC.loader
curriculum = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(curriculum)


def test_exact_subject_capability_grid_and_distinct_scenarios():
    rows = curriculum.build_rows()
    assert len(rows) == 32
    assert Counter((r["subject"], r["capabilities"][0]) for r in rows) == Counter(
        (subject, capability)
        for subject in curriculum.SUBJECTS
        for capability in curriculum.CAPABILITIES
    )
    for key in ("id", "source_id", "group_id"):
        assert len({r[key] for r in rows}) == 32
    assert len({r["messages"][0]["content"] for r in rows}) == 32


def test_full_dialogues_include_repair_transfer_and_confirmation():
    for row in curriculum.build_rows():
        messages = row["messages"]
        assert [m["role"] for m in messages] == ["user", "assistant"] * 3
        assert all(len(m["content"].split()) >= 5 for m in messages)
        metadata = row["source_metadata"]
        assert metadata["learner_error_turn_indices"] == [2]
        assert metadata["repair_and_transfer_turn_index"] == 3
        assert metadata["transfer_response_turn_index"] == 4
        assert "?" in messages[3]["content"]
        assert messages[2]["content"] != messages[4]["content"]
        assert len(metadata["claims_for_review"]) >= 2


def test_no_false_approval_or_holdout_claims():
    for row in curriculum.build_rows():
        assert row["eligibility"] == "candidate_pending_review"
        assert row["original_split"] == "authored_unsplit"
        assert row["quality"]["independent_scientific_verification"] is False
        assert row["quality"]["content_review"] == "pending_all_assistant_statements"
        assert row["fresh_holdout_admission"].startswith("not_claimed")
        assert row["source_metadata"]["family_independence"] == "not_claimed"
        assert row["license"] == "LicenseRef-Project-Original"


def test_primary_references_are_outside_messages():
    allowed_domains = (
        "nasa.gov",
        "usgs.gov",
        "nist.gov",
        "energy.gov",
        "genome.gov",
        "noaa.gov",
        "nih.gov",
    )
    for row in curriculum.build_rows():
        meta = row["source_metadata"]
        assert meta["reference_ids"]
        assert meta["source_passages_reproduced"] is False
        assert meta["reference_urls"] == [
            curriculum.REFERENCES[key][1] for key in meta["reference_ids"]
        ]
        for url in meta["reference_urls"]:
            parsed = urlparse(url)
            assert parsed.scheme == "https"
            assert any(
                parsed.hostname == d or parsed.hostname.endswith("." + d) for d in allowed_domains
            )
            assert all(url not in m["content"] for m in row["messages"])
            assert "openstax" not in url


def test_independent_exact_arithmetic_and_actual_text_targets():
    expected = {
        "heat_capacity": Fraction(225),
        "heat_rise": Fraction(4),
        "heat_transfer_capacity": Fraction(450),
        "heat_transfer_rise": Fraction(2),
        "dilution_concentration": Fraction(24),
        "dilution_sample_mass": Fraction(6),
        "herbivore_efficiency": Fraction(20),
        "carnivore_efficiency": Fraction(25),
        "rain_volume": Fraction(36, 25),
        "rain_collected_volume": Fraction(27, 25),
        "rain_collected_litres": Fraction(1080),
    }
    assert curriculum.independent_numeric_values() == expected
    seen = []
    for row in curriculum.build_rows():
        checks = row["quality"]["numeric_checks"]
        assert bool(checks) == (row["capabilities"] == ["quantitative_reasoning"])
        for check in checks:
            assert Fraction(check["computed_exact"]) == expected[check["check"]]
            assert check["status"] == "passed"
            assert check["target_turn_index"] in (3, 4)
            assert check["target_span"] in row["messages"][check["target_turn_index"]]["content"]
            seen.append(check["check"])
    assert Counter(seen) == Counter(expected.keys())


def test_numeric_target_mutation_is_rejected(monkeypatch):
    changed = dict(curriculum.NUMERIC_TARGETS)
    changed["heat_rise"] = ("5", "K")
    monkeypatch.setattr(curriculum, "NUMERIC_TARGETS", changed)
    with pytest.raises(ValueError, match="Numeric mismatch"):
        curriculum.build_rows()


def test_actual_tutor_answer_mutation_is_rejected(monkeypatch):
    changed = copy.deepcopy(curriculum.SCENARIOS)
    row = next(r for r in changed if r["slug"] == "thermal-block-energy-budget")
    row["turns"][3] = row["turns"][3].replace("4 K", "5 K")
    monkeypatch.setattr(curriculum, "SCENARIOS", changed)
    with pytest.raises(ValueError, match="Numeric target text mismatch"):
        curriculum.build_rows()


def test_duplicate_cell_fails_before_writing(monkeypatch, tmp_path):
    changed = copy.deepcopy(curriculum.SCENARIOS)
    changed.append(changed[0])
    monkeypatch.setattr(curriculum, "SCENARIOS", changed)
    with pytest.raises(ValueError, match="exactly one scenario"):
        curriculum.build(tmp_path / "data", tmp_path / "provenance")
    assert not (tmp_path / "data").exists()


def test_reproducible_outputs_complete_review_packet_and_hashes(tmp_path):
    output, provenance = tmp_path / "data", tmp_path / "provenance"
    manifest = curriculum.build(output, provenance)
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert curriculum.build(output, provenance) == manifest
    assert {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before
    rows = [json.loads(line) for line in (output / "candidates.jsonl").read_text().splitlines()]
    packet = [
        json.loads(line)
        for line in (provenance / "authored-review-packet.jsonl").read_text().splitlines()
    ]
    assert [item["row"] for item in packet] == rows
    assert all(item["review_status"] == "pending_independent_review" for item in packet)
    assert manifest["rows"] == manifest["groups"] == 32
    assert manifest["assistant_turns"] == 96
    assert manifest["numeric_checks_passed"] == 11
    assert manifest["admitted_to_training"] is False
    assert manifest["no_holdout_constructed"] is True
    for artifact in manifest["artifacts"].values():
        payload = Path(artifact["path"]).read_bytes()
        assert curriculum.digest(payload) == artifact["sha256"]
        assert len(payload) == artifact["bytes"]
    assert sorted(p.name for p in output.iterdir()) == ["candidates.jsonl"]
    receipt = json.loads((provenance / "authored-reference-receipt.json").read_text())
    assert receipt["read_date"] == "2026-09-19"
    assert len(receipt["references"]) == len(curriculum.REFERENCES)
    assert "not a public license grant" in receipt["original_text_rights"]
