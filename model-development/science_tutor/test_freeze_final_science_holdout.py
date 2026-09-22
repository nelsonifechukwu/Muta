"""CPU-only tests for the final source-heldout MC freeze."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "freeze_final_science_holdout",
    Path(__file__).with_name("freeze_final_science_holdout.py"),
)
assert SPEC and SPEC.loader
freeze = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(freeze)


@pytest.fixture(scope="module")
def source_payload() -> bytes:
    return freeze.load_inputs(freeze.ROOT)[freeze.SOURCE]


def changed(payload: bytes, transform) -> bytes:
    rows = freeze.jsonl_rows(payload)
    transform(rows)
    return b"".join(freeze.canonical(row) + b"\n" for row in rows)


def test_actual_source_freezes_every_mc_once_with_fixed_order(source_payload):
    artifacts, metadata = freeze.assemble(source_payload)
    prompts = freeze.jsonl_rows(artifacts["prompts.jsonl"])
    keys = freeze.jsonl_rows(artifacts["keys.jsonl"])

    assert len(prompts) == len(keys) == 1_590
    assert len({row["id"] for row in prompts}) == 1_590
    assert metadata["sources"] == {"scienceqa": 733, "sciq": 857}
    assert metadata["unique_groups"] == 1_582
    assert metadata["excluded"] == [
        {
            "id": freeze.EXCLUDED_ID,
            "source": "mathdial",
            "reason": "non_multiple_choice_multi_turn_dialogue",
        }
    ]
    assert [row["id"] for row in prompts] == [row["id"] for row in keys]
    assert [(row["source"], row["id"]) for row in prompts] == sorted(
        (row["source"], row["id"]) for row in prompts
    )
    assert freeze.assemble(source_payload) == (artifacts, metadata)


def test_prompt_pack_is_exact_answer_free_projection(source_payload):
    artifacts, _ = freeze.assemble(source_payload)
    prompts = freeze.jsonl_rows(artifacts["prompts.jsonl"])
    keys = {row["id"]: row for row in freeze.jsonl_rows(artifacts["keys.jsonl"])}
    source = {row["id"]: row for row in freeze.jsonl_rows(source_payload)}

    forbidden = {
        "answer",
        "answer_index",
        "answer_letter",
        "answer_text",
        "assistant_target",
        "source_solution",
        "source_lecture",
        "rubric",
    }
    for prompt in prompts:
        original = source[prompt["id"]]
        assert set(prompt) == {"id", "source", "subject", "group_id", "messages"}
        assert not (set(prompt) & forbidden)
        assert prompt["messages"] == freeze.prompt_messages(original)
        assert [message["role"] for message in prompt["messages"]] == ["user"]
        assert original["messages"][-1] not in prompt["messages"]
        assert keys[prompt["id"]]["model_messages_sha256"] == freeze.sha(
            freeze.canonical(prompt["messages"])
        )
        assert keys[prompt["id"]]["source_assistant_target_sha256"] == freeze.sha(
            original["messages"][-1]["content"].encode()
        )


def test_key_ledger_matches_source_without_claiming_independent_verification(source_payload):
    artifacts, _ = freeze.assemble(source_payload)
    source = {row["id"]: row for row in freeze.jsonl_rows(source_payload)}
    for key in freeze.jsonl_rows(artifacts["keys.jsonl"]):
        original = source[key["id"]]
        assert key["choices"] == original["choices"]
        assert key["answer_index"] == original["answer_index"]
        assert key["answer_letter"] == chr(65 + original["answer_index"])
        assert key["answer_text"] == original["answer"]
        assert key["key_status"] == "source_key_not_independently_verified"
        assert key["source_row_canonical_sha256"] == freeze.sha(freeze.canonical(original))


def test_temp_freeze_receipts_all_inputs_and_never_changes_sources(tmp_path, source_payload):
    before = {
        path: freeze.sha(freeze.safe_read(freeze.ROOT, path))
        for path in (
            freeze.SOURCE,
            freeze.SOURCE_MANIFEST,
            freeze.BUILDER,
            freeze.TESTS,
            freeze.PLAN,
        )
    }
    output = tmp_path / "frozen"
    builder_sha = freeze.sha(Path(freeze.__file__).read_bytes())
    manifest = freeze.freeze(reviewed_builder_sha256=builder_sha, destination=output)

    assert {path.name for path in output.iterdir()} == {
        "prompts.jsonl",
        "keys.jsonl",
        "manifest.json",
    }
    assert json.loads((output / "manifest.json").read_bytes()) == manifest
    assert manifest["rows"] == 1_590
    assert manifest["source_rows"] == 1_591
    assert manifest["excluded_rows"] == 1
    assert manifest["inference_performed"] is False
    assert manifest["answer_leakage_checks"]["assistant_messages_in_prompts"] == 0
    for name, receipt in manifest["artifacts"].items():
        payload = (output / name).read_bytes()
        assert freeze.sha(payload) == receipt["sha256"]
        assert len(payload) == receipt["bytes"]
        assert len(freeze.jsonl_rows(payload)) == receipt["rows"]
    bindings = {row["path"]: row["sha256"] for row in manifest["input_bindings"]}
    assert bindings == before
    assert before == {path: freeze.sha(freeze.safe_read(freeze.ROOT, path)) for path in before}


def test_freeze_refuses_overwrite_and_unreviewed_builder(tmp_path):
    output = tmp_path / "frozen"
    output.mkdir()
    with pytest.raises(ValueError, match="refuse overwrite"):
        freeze.freeze(reviewed_builder_sha256="0" * 64, destination=output)
    with pytest.raises(ValueError, match="reviewed builder hash mismatch"):
        freeze.freeze(reviewed_builder_sha256="0" * 64, destination=tmp_path / "new")


@pytest.mark.parametrize(
    "payload",
    [b'{"id":1,"id":2}', b'{"x":NaN}', b'{"x":Infinity}', b"", b"{}\n\n{}\n"],
)
def test_strict_json_and_jsonl_reject_bad_inputs(payload):
    with pytest.raises((ValueError, json.JSONDecodeError)):
        if b"\n" in payload or not payload:
            freeze.jsonl_rows(payload)
        else:
            freeze.parse(payload)


def test_duplicate_id_and_key_drift_are_rejected(source_payload):
    duplicate = changed(
        source_payload,
        lambda rows: rows.__setitem__(1, copy.deepcopy(rows[0])),
    )
    with pytest.raises(ValueError, match="duplicate source row ID"):
        freeze.assemble(duplicate)

    def break_key(rows):
        row = next(item for item in rows if item.get("source") == "scienceqa")
        row["answer_index"] = (row["answer_index"] + 1) % len(row["choices"])

    with pytest.raises(ValueError, match="source answer/choice mismatch"):
        freeze.assemble(changed(source_payload, break_key))


def test_mc_cannot_be_silently_reclassified_as_excluded(source_payload):
    def reclassify(rows):
        row = next(item for item in rows if item.get("source") == "scienceqa")
        row["source"] = "mathdial"

    with pytest.raises(ValueError, match="unexpected non-MC holdout row"):
        freeze.assemble(changed(source_payload, reclassify))


def test_model_facing_instruction_is_uniform(source_payload):
    artifacts, _ = freeze.assemble(source_payload)
    prompts = freeze.jsonl_rows(artifacts["prompts.jsonl"])
    assert all(row["messages"][0]["content"].endswith(freeze.PROMPT_INSTRUCTION) for row in prompts)
