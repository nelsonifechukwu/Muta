"""CPU-only tests for the selected science-checkpoint export gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from science_tutor import prepare_selected_export as gate


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def file_ref(path: Path) -> dict:
    return {"path": str(path), "sha256": gate.sha256_file(path)}


def tree_ref(path: Path) -> dict:
    return {"path": str(path), "tree_sha256": gate.tree_receipt(path)["tree_sha256"]}


@pytest.fixture
def admitted(tmp_path: Path):
    config_sha = "1" * 64
    train_sha = "2" * 64
    dev_sha = "3" * 64
    admission_sha = "4" * 64
    tensor_sha = "5" * 64
    source_sha = {"train.py": "6" * 64, "tokenization.py": "7" * 64}

    base = tmp_path / "base"
    base.mkdir()
    (base / "config.json").write_text("{}\n", encoding="utf-8")
    tokenizer = tmp_path / "tokenizer"
    tokenizer.mkdir()
    (tokenizer / "tokenizer.json").write_text("{}\n", encoding="utf-8")

    checkpoint = tmp_path / "run/checkpoints/checkpoint-3"
    checkpoint.mkdir(parents=True)
    (checkpoint / "README.md").write_text("fixture\n", encoding="utf-8")
    (checkpoint / "adapter_config.json").write_text("{}\n", encoding="utf-8")
    (checkpoint / "adapter_model.safetensors").write_bytes(b"adapter")
    (checkpoint / "training-state.pt").write_bytes(b"optimizer is evidence only")
    write_json(
        checkpoint / "state.json",
        {"step": 3, "adapter": {"tensor_sha256": tensor_sha, "tensor_count": 2}},
    )
    sealed_files = gate.tree_receipt(checkpoint)["files"]
    write_json(
        checkpoint / "COMPLETE.json",
        {
            "schema_version": 1,
            "step": 3,
            "config_sha256": config_sha,
            "source_sha256": source_sha,
            "files": sealed_files,
        },
    )
    checkpoint_receipt = gate.tree_receipt(checkpoint)

    resolved = tmp_path / "run/resolved-config.json"
    write_json(
        resolved,
        {
            "config_file": {"sha256": config_sha},
            "config": {
                "data": {
                    "train": {"sha256": train_sha},
                    "dev": {"sha256": dev_sha},
                    "admission": {"sha256": admission_sha},
                },
                "initialization": {
                    "kind": "muta_fresh",
                    "base": {"tree_sha256": gate.tree_receipt(base)["tree_sha256"]},
                    "tokenizer": {
                        "tree_sha256": gate.tree_receipt(tokenizer)["tree_sha256"]
                    },
                },
            },
        },
    )
    run_complete = tmp_path / "run/COMPLETED.json"
    write_json(
        run_complete,
        {"config_sha256": config_sha, "all_checkpoints": [checkpoint_receipt]},
    )
    lineage = tmp_path / "base-lineage.json"
    write_json(
        lineage,
        {"training_base": {"tree_sha256": gate.tree_receipt(base)["tree_sha256"]}},
    )
    declaration = tmp_path / "selection.md"
    declaration.write_text("selected after frozen development review\n", encoding="utf-8")
    scores = tmp_path / "scores.json"
    write_json(scores, {"selected": "p2-half"})
    r1_review = tmp_path / "r1-review.json"
    write_json(r1_review, {"accepted": 7, "rejected": 26})
    r1_decision = tmp_path / "r1-decision.json"
    write_json(
        r1_decision,
        {
            "decision": "SKIP_R1_NO_MEANINGFUL_EXPANSION",
            "training_action": {"launch_r1": False},
            "selected_export_candidate": {
                "candidate_id": "P2-half",
                "parent": {"tree_sha256": gate.tree_receipt(base)["tree_sha256"]},
                "checkpoint": {
                    "step": 3,
                    "tree_sha256": checkpoint_receipt["tree_sha256"],
                    "checkpoint_seal_sha256": gate.sha256_file(
                        checkpoint / "COMPLETE.json"
                    ),
                },
            },
            "evidence": {
                "independent_review": {"sha256": gate.sha256_file(r1_review)},
                "development_winner_declaration": {
                    "sha256": gate.sha256_file(declaration)
                },
            },
        },
    )

    config = {
        "schema_version": 1,
        "selection_id": "p2_half",
        "checkpoint_step": 3,
        "checkpoint": tree_ref(checkpoint),
        "checkpoint_seal": file_ref(checkpoint / "COMPLETE.json"),
        "run_complete": file_ref(run_complete),
        "resolved_config": file_ref(resolved),
        "base": tree_ref(base),
        "base_lineage": file_ref(lineage),
        "tokenizer": tree_ref(tokenizer),
        "selection_declaration": file_ref(declaration),
        "selection_scores": file_ref(scores),
        "r1_expansion_review": file_ref(r1_review),
        "r1_admission_decision": file_ref(r1_decision),
        "expected_training": {
            "config_sha256": config_sha,
            "train_sha256": train_sha,
            "dev_sha256": dev_sha,
            "admission_sha256": admission_sha,
            "source_sha256": source_sha,
            "adapter_model_sha256": gate.sha256_file(
                checkpoint / "adapter_model.safetensors"
            ),
            "adapter_tensor_sha256": tensor_sha,
        },
    }
    return config, checkpoint


def test_prepare_joins_selection_checkpoint_parent_and_tokenizer(admitted):
    config, checkpoint = admitted
    result = gate.prepare(config)
    assert result["status"] == "admitted_for_merge_and_q4_k_m_export"
    assert result["adapter"]["tree_sha256"] == gate.tree_receipt(checkpoint)["tree_sha256"]
    assert result["checkpoint_step"] == 3
    assert "optimizer state" in result["limitations"][1]


def test_prepare_rejects_mutated_checkpoint_after_config_freeze(admitted):
    config, checkpoint = admitted
    (checkpoint / "adapter_model.safetensors").write_bytes(b"mutated")
    with pytest.raises(gate.ExportAdmissionError, match="checkpoint tree mismatch"):
        gate.prepare(config)


def test_prepare_rejects_run_that_does_not_retain_selected_checkpoint(admitted):
    config, _checkpoint = admitted
    run = Path(config["run_complete"]["path"])
    write_json(run, {"config_sha256": "1" * 64, "all_checkpoints": []})
    config["run_complete"] = file_ref(run)
    with pytest.raises(gate.ExportAdmissionError, match="does not retain"):
        gate.prepare(config)


def test_write_exclusive_never_overwrites(tmp_path: Path):
    path = tmp_path / "authority.json"
    gate.write_exclusive(path, {"first": True})
    with pytest.raises(FileExistsError):
        gate.write_exclusive(path, {"second": True})
