from __future__ import annotations

import argparse
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


class FakeCuda:
    @staticmethod
    def current_device():
        return 2

    @staticmethod
    def get_device_properties(device):
        assert device == 2
        return type("Properties", (), {"name": "Fake A100", "total_memory": 40_000})()

    @staticmethod
    def memory_allocated(device):
        assert device == 2
        return 11_000

    @staticmethod
    def memory_reserved(device):
        assert device == 2
        return 12_000

    @staticmethod
    def max_memory_allocated(device):
        assert device == 2
        return 31_000

    @staticmethod
    def max_memory_reserved(device):
        assert device == 2
        return 32_000


class FakeControl:
    should_evaluate = False
    should_save = False


def _row():
    return {"id": "row-1", "mode": "chat", "prompt": "p", "completion": "c"}


def test_cuda_memory_receipt_uses_exact_byte_counters():
    torch = type("FakeTorch", (), {"cuda": FakeCuda})()
    assert round2._cuda_memory_receipt(torch) == {
        "device_index": 2,
        "device_name": "Fake A100",
        "device_total_bytes": 40_000,
        "current_allocated_bytes": 11_000,
        "current_reserved_bytes": 12_000,
        "peak_allocated_bytes": 31_000,
        "peak_reserved_bytes": 32_000,
    }


def test_parse_milestone_steps_requires_unique_ascending_positive_values():
    assert round2.parse_milestone_steps("1174,2347,4693") == (1174, 2347, 4693)
    for value in ("", "1,,2", "0,2", "2,1", "1,1", "one,2"):
        with pytest.raises(argparse.ArgumentTypeError):
            round2.parse_milestone_steps(value)


def test_milestone_control_only_requests_eval_and_save_at_exact_steps():
    untouched = round2.apply_milestone_control(
        step=75,
        milestones=(25, 50, 100),
        control=FakeControl(),
    )
    assert not untouched.should_evaluate
    assert not untouched.should_save
    selected = round2.apply_milestone_control(
        step=50,
        milestones=(25, 50, 100),
        control=FakeControl(),
    )
    assert selected.should_evaluate
    assert selected.should_save


def test_milestone_evidence_accepts_save_total_limit_rotation():
    round2.validate_milestone_evidence(
        milestones=(25, 50, 75, 100),
        observed_eval_steps=[25, 50, 75, 100],
        session_save_steps=[25, 50, 75, 100],
        surviving_checkpoint_steps=[50, 75, 100],
        resume_step=None,
        planned_steps=100,
    )


def test_milestone_evidence_requires_only_post_resume_save_callbacks():
    round2.validate_milestone_evidence(
        milestones=(25, 50, 75, 100),
        observed_eval_steps=[25, 50, 75, 100],
        session_save_steps=[75, 100],
        surviving_checkpoint_steps=[50, 75, 100],
        resume_step=50,
        planned_steps=100,
    )
    with pytest.raises(RuntimeError, match="save callbacks"):
        round2.validate_milestone_evidence(
            milestones=(25, 50, 75, 100),
            observed_eval_steps=[25, 50, 75, 100],
            session_save_steps=[100],
            surviving_checkpoint_steps=[50, 75, 100],
            resume_step=50,
            planned_steps=100,
        )


def test_campaign_config_receipt_refuses_changed_config(tmp_path):
    config = tmp_path / "campaign.json"
    config.write_text("{}")
    digest = round2.sha256_file(config)
    assert round2._campaign_config_receipt(config, expected_sha256=digest)["sha256"] == digest
    config.write_text('{"changed": true}')
    with pytest.raises(round2.CampaignInputError, match="SHA-256 mismatch"):
        round2._campaign_config_receipt(config, expected_sha256=digest)


def test_checkpoint_must_be_a_complete_direct_child_of_run(tmp_path):
    root = tmp_path / "checkpoints"
    checkpoint = root / "checkpoint-25"
    checkpoint.mkdir(parents=True)
    (checkpoint / "trainer_state.json").write_text("{}")
    assert round2._checkpoint_step(checkpoint, checkpoint_root=root) == 25
    outside = tmp_path / "other" / "checkpoint-25"
    outside.mkdir(parents=True)
    (outside / "trainer_state.json").write_text("{}")
    with pytest.raises(round2.CampaignInputError, match="outside this run"):
        round2._checkpoint_step(outside, checkpoint_root=root)


def test_checkpoint_inventory_refuses_partial_save(tmp_path):
    root = tmp_path / "checkpoints"
    complete = root / "checkpoint-25"
    complete.mkdir(parents=True)
    (complete / "trainer_state.json").write_text("{}")
    partial = root / "checkpoint-50"
    partial.mkdir()
    with pytest.raises(round2.CampaignInputError, match="incomplete checkpoint evidence"):
        round2._complete_checkpoint_steps(root)
    (partial / "trainer_state.json").write_text("{}")
    assert round2._complete_checkpoint_steps(root) == [25, 50]


def test_run_directory_lock_refuses_concurrent_trainer(tmp_path):
    with (
        round2._exclusive_run_lock(tmp_path),
        pytest.raises(RuntimeError, match="another trainer"),
        round2._exclusive_run_lock(tmp_path),
    ):
        pass


def test_final_adapter_is_bound_to_best_checkpoint(tmp_path):
    checkpoint = tmp_path / "checkpoints" / "checkpoint-50"
    checkpoint.mkdir(parents=True)
    (checkpoint / "trainer_state.json").write_text("{}")
    (checkpoint / "adapter_model.safetensors").write_bytes(b"best")
    (checkpoint / "adapter_config.json").write_bytes(b"config")
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    (adapter / "adapter_model.safetensors").write_bytes(b"best")
    (adapter / "adapter_config.json").write_bytes(b"config")
    state = type(
        "State",
        (),
        {"best_model_checkpoint": str(checkpoint), "best_metric": 1.25},
    )()
    trainer = type("Trainer", (), {"state": state})()
    receipt = round2._selected_adapter_receipt(
        trainer=trainer,
        output=tmp_path,
        adapter_dir=adapter,
        milestones=(25, 50, 100),
    )
    assert receipt["best_checkpoint_step"] == 50
    assert receipt["policy"] == "minimum_eval_loss"
    assert receipt["final_adapter_config_sha256"] == round2.sha256_file(
        adapter / "adapter_config.json"
    )
    (adapter / "adapter_model.safetensors").write_bytes(b"last-not-best")
    with pytest.raises(RuntimeError, match="do not match"):
        round2._selected_adapter_receipt(
            trainer=trainer,
            output=tmp_path,
            adapter_dir=adapter,
            milestones=(25, 50, 100),
        )


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
