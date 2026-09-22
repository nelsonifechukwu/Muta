"""CPU-only tests for the corrected final source-heldout MC freeze."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "freeze_final_science_holdout_v2",
    Path(__file__).with_name("freeze_final_science_holdout_v2.py"),
)
assert SPEC and SPEC.loader
freeze = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(freeze)


@pytest.fixture(scope="module")
def loaded() -> dict[str, bytes]:
    return freeze.load_inputs(freeze.ROOT)


def test_actual_source_excludes_exact_reviewed_context_failures(loaded):
    artifacts, metadata = freeze.assemble(loaded[freeze.base.SOURCE], loaded[freeze.RAW_SCIENCEQA])
    prompts = freeze.base.jsonl_rows(artifacts["prompts.jsonl"])
    keys = freeze.base.jsonl_rows(artifacts["keys.jsonl"])

    assert len(prompts) == len(keys) == freeze.EXPECTED_ROWS == 1_582
    assert [row["id"] for row in prompts] == [row["id"] for row in keys]
    assert len({row["id"] for row in prompts}) == 1_582
    assert metadata["sources"] == {"scienceqa": 725, "sciq": 857}
    assert metadata["unique_groups"] == 1_574
    assert {row["id"] for row in metadata["excluded"]} == {
        freeze.base.EXCLUDED_ID,
        *freeze.MISSING_CONTEXT_IDS,
    }
    assert not ({row["id"] for row in prompts} & set(freeze.MISSING_CONTEXT_IDS))
    assert [row["id"] for row in prompts] == sorted(
        (row["id"] for row in prompts),
        key=lambda row_id: (0 if row_id.startswith("scienceqa:") else 1, row_id),
    )


def test_all_reviewed_exclusions_have_missing_text_context_evidence(loaded):
    source = {row["id"]: row for row in freeze.base.jsonl_rows(loaded[freeze.base.SOURCE])}
    raw = freeze.base.parse(loaded[freeze.RAW_SCIENCEQA])
    freeze._validate_reviewed_exclusions(list(source.values()), raw)

    for row_id in freeze.MISSING_CONTEXT_IDS:
        row = source[row_id]
        assert row["question"] == freeze.THERMOMETER_QUESTION
        assert row["source_metadata"]["skill"] == "Read a thermometer"
        assert all(freeze.TEMPERATURE.fullmatch(choice) for choice in row["choices"])
        assert "red liquid" in row["source_solution"].casefold()
        assert raw[row["source_id"]]["image"] is None
        assert not raw[row["source_id"]]["hint"].strip()


def test_broad_question_deictic_sweep_has_only_reviewed_or_text_closed_rows(loaded):
    source = [
        row
        for row in freeze.base.jsonl_rows(loaded[freeze.base.SOURCE])
        if row.get("source") == "scienceqa"
    ]
    pattern = re.compile(
        r"\b(?:shown|displayed|indicated|pictured|illustrated|depicted|above|below|"
        r"diagram|figure|image|picture|graph|chart|map|thermometer|look at|observe)\b",
        re.IGNORECASE,
    )
    candidates = [row for row in source if pattern.search(row["question"])]
    missing = [row for row in candidates if row["id"] in freeze.MISSING_CONTEXT_IDS]
    retained = [row for row in candidates if row["id"] not in freeze.MISSING_CONTEXT_IDS]

    assert len(source) == 733
    assert len(candidates) == 27
    assert {row["id"] for row in missing} == set(freeze.MISSING_CONTEXT_IDS)
    assert len(retained) == 19
    for row in retained:
        skill = row["source_metadata"]["skill"]
        if skill.startswith("Use evidence to classify"):
            assert all(len(choice.split()) >= 8 for choice in row["choices"])
        else:
            assert skill == "Identify reactants and products"
            assert "This passage describes a chemical reaction." in row["question"]


def test_temp_freeze_is_append_only_hash_bound_and_answer_isolated(tmp_path, loaded):
    output = tmp_path / "final-science-mc-v2"
    builder_sha = freeze.base.sha(Path(freeze.__file__).read_bytes())
    manifest = freeze.freeze(
        reviewed_builder_sha256=builder_sha,
        destination=output,
    )

    assert {path.name for path in output.iterdir()} == {
        "prompts.jsonl",
        "keys.jsonl",
        "manifest.json",
    }
    assert json.loads((output / "manifest.json").read_bytes()) == manifest
    assert manifest["release"] == "final-science-mc-v2"
    assert manifest["rows"] == 1_582
    assert manifest["source_rows"] == 1_591
    assert manifest["excluded_rows"] == 9
    assert manifest["inference_performed"] is False
    assert manifest["context_dependency_review"]["missing_context_excluded"] == 8
    for name, receipt in manifest["artifacts"].items():
        payload = (output / name).read_bytes()
        assert freeze.base.sha(payload) == receipt["sha256"]
        assert len(payload) == receipt["bytes"]
        assert len(freeze.base.jsonl_rows(payload)) == receipt["rows"]

    prompts = freeze.base.jsonl_rows((output / "prompts.jsonl").read_bytes())
    assert all(set(row) == {"id", "source", "subject", "group_id", "messages"} for row in prompts)
    assert all([message["role"] for message in row["messages"]] == ["user"] for row in prompts)
    bindings = {row["path"]: row["sha256"] for row in manifest["input_bindings"]}
    assert bindings[freeze.BUILDER] == builder_sha
    assert bindings[freeze.BASE_BUILDER] == freeze.base.sha(
        (freeze.ROOT / freeze.BASE_BUILDER).read_bytes()
    )
    assert bindings[freeze.RAW_SCIENCEQA] == freeze.RAW_SCIENCEQA_SHA256


def test_freeze_refuses_overwrite_and_unreviewed_builder(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(ValueError, match="refuse overwrite"):
        freeze.freeze(reviewed_builder_sha256="0" * 64, destination=output)
    with pytest.raises(ValueError, match="reviewed builder hash mismatch"):
        freeze.freeze(reviewed_builder_sha256="0" * 64, destination=tmp_path / "new")
