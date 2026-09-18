from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


round2 = _load("train_lora_round2")


class FakeTokenizer:
    def __init__(self, *, full=None):
        self.full = full or [1, 2, 3, 4, 5]

    def apply_chat_template(self, messages, **_kwargs):
        return [1, 2, 3] if len(messages) == 1 else self.full


def _row():
    return {"id": "row-1", "mode": "chat", "prompt": "p", "completion": "c"}


def test_completion_mask_contains_only_assistant_tokens():
    result = round2.tokenize_chat_row(_row(), tokenizer=FakeTokenizer(), max_length=8)
    assert result["labels"] == [-100, -100, -100, 4, 5]
    assert result["assistant_tokens"] == 2
    assert result["sequence_length"] == 5


def test_tokenizer_preflight_refuses_truncation():
    with pytest.raises(round2.CampaignInputError, match="tokenizes to 5 > 4"):
        round2.tokenize_chat_row(_row(), tokenizer=FakeTokenizer(), max_length=4)


def test_tokenizer_refuses_empty_completion():
    with pytest.raises(round2.CampaignInputError, match="no trainable tokens"):
        round2.tokenize_chat_row(_row(), tokenizer=FakeTokenizer(full=[1, 2, 3]), max_length=8)


def test_lineage_verification_hashes_the_training_base(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    (base / "model.safetensors").write_bytes(b"weights")
    inventory = round2.inventory_tree(base)
    receipt = tmp_path / "lineage.json"
    receipt.write_text(
        json.dumps(
            {
                "lineage": "warm",
                "training_base": {"tree_sha256": inventory["tree_sha256"]},
            }
        )
    )
    verified = round2._verify_lineage(receipt, expected_lineage="warm", model_path=base)
    assert verified["observed"]["tree_sha256"] == inventory["tree_sha256"]


def test_projection_ignores_heterogeneous_nested_metadata(tmp_path):
    source = tmp_path / "rows.jsonl"
    rows = [
        {
            **_row(),
            "provenance": {"source_id": "muta_verified_stem_v2"},
            "verification": {"inputs": {"a": 1}},
        },
        {
            **_row(),
            "id": "row-2",
            "provenance": {"source_id": "deepmind_mathematics"},
            "verification": {"inputs": {"different": "shape", "b": 2}},
        },
    ]
    source.write_text("".join(json.dumps(row) + "\n" for row in rows))
    projected = list(round2.projected_jsonl_rows([str(source)]))
    assert projected == [
        {
            "id": "row-1",
            "prompt": "p",
            "completion": "c",
            "mode": "chat",
            "source_id": "muta_verified_stem_v2",
        },
        {
            "id": "row-2",
            "prompt": "p",
            "completion": "c",
            "mode": "chat",
            "source_id": "deepmind_mathematics",
        },
    ]


def test_lineage_verification_rejects_modified_base(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    model = base / "model.safetensors"
    model.write_bytes(b"weights")
    inventory = round2.inventory_tree(base)
    receipt = tmp_path / "lineage.json"
    receipt.write_text(
        json.dumps(
            {
                "lineage": "clean",
                "training_base": {"tree_sha256": inventory["tree_sha256"]},
            }
        )
    )
    model.write_bytes(b"changed")
    with pytest.raises(round2.CampaignInputError, match="does not match"):
        round2._verify_lineage(receipt, expected_lineage="clean", model_path=base)


def test_tokenizer_must_match_clean_lineage(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    (base / "model.safetensors").write_bytes(b"weights")
    (base / "tokenizer.json").write_bytes(b"tokens")
    (base / "tokenizer_config.json").write_bytes(b"config")
    inventory = round2.inventory_tree(base)
    receipt = tmp_path / "clean.json"
    receipt.write_text(
        json.dumps(
            {
                "lineage": "clean",
                "training_base": inventory,
            }
        )
    )
    verified = round2._verify_tokenizer(base, lineage_path=receipt)
    assert set(verified["files"]) == {"tokenizer.json", "tokenizer_config.json"}
