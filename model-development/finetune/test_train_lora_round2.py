from __future__ import annotations

import argparse
import importlib.util
import json
import os
import select
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import numpy as np
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


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX trainer/DataLoader fork regression")
def test_forked_worker_cannot_keep_dead_trainers_run_lock(tmp_path):
    ready_read, ready_write = os.pipe()
    finish_read, finish_write = os.pipe()
    child_pid = None
    try:
        with round2._exclusive_run_lock(tmp_path):
            child_pid = os.fork()
            if child_pid == 0:
                try:
                    os.close(ready_read)
                    os.close(finish_write)
                    os.write(ready_write, b"ready")
                    os.read(finish_read, 1)
                finally:
                    os._exit(0)
            os.close(ready_write)
            ready_write = -1
            os.close(finish_read)
            finish_read = -1
            assert select.select([ready_read], [], [], 5)[0], "forked worker did not start"
            assert os.read(ready_read, 5) == b"ready"
            # Closing the child's inherited FD must not unlock the live parent.
            with (
                pytest.raises(RuntimeError, match="another trainer"),
                round2._exclusive_run_lock(tmp_path),
            ):
                pass
        # The child is still alive; without the at-fork close this fails because
        # its inherited open-file-description retains the parent's flock.
        assert os.waitpid(child_pid, os.WNOHANG) == (0, 0)
        with round2._exclusive_run_lock(tmp_path):
            pass
    finally:
        if finish_write >= 0:
            os.close(finish_write)
            finish_write = -1
        if child_pid:
            os.waitpid(child_pid, 0)
        for descriptor in (ready_read, ready_write, finish_read):
            if descriptor >= 0:
                os.close(descriptor)


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


def _required_args():
    return [
        "--model",
        "base",
        "--base-lineage",
        "lineage.json",
        "--tokenizer",
        "tokens",
        "--tokenizer-lineage",
        "clean.json",
        "--lineage",
        "warm",
        "--dataset-manifest",
        "train.json",
        "--validation-manifest",
        "dev.json",
        "--output",
        "output",
        "--run-name",
        "continuation",
    ]


def test_initial_adapter_cli_flags_are_paired_and_hashed():
    assert round2.parse_args(_required_args()).initial_adapter is None
    for extra in (
        ["--initial-adapter", "pilot/adapter"],
        ["--expected-initial-adapter-tree-sha256", "a" * 64],
        ["--initial-adapter", "pilot/adapter", "--expected-initial-adapter-tree-sha256", "wrong"],
    ):
        with pytest.raises(SystemExit):
            round2.parse_args(_required_args() + extra)
    args = round2.parse_args(
        _required_args()
        + [
            "--initial-adapter",
            "pilot/adapter",
            "--expected-initial-adapter-tree-sha256",
            "a" * 64,
        ]
    )
    assert args.initial_adapter == Path("pilot/adapter")


def _initial_adapter_fixture(tmp_path, *, config_update=None, manifest_update=None):
    adapter = tmp_path / "pilot" / "adapter"
    adapter.mkdir(parents=True)
    config = {
        "base_model_name_or_path": "/old-host/incumbent-muta-merged",
        "r": 16,
        "lora_alpha": 16,
        "target_modules": list(round2.LORA_TARGET_MODULES),
        "peft_type": "LORA",
        "task_type": "CAUSAL_LM",
        "bias": "none",
        "lora_dropout": 0,
        **(config_update or {}),
    }
    (adapter / "adapter_config.json").write_text(json.dumps(config))
    (adapter / "adapter_model.safetensors").write_bytes(b"fixture weights")
    inventory = round2.inventory_tree(adapter)
    lineage = {"observed": {"tree_sha256": "b" * 64}}
    manifest = {
        "run_name": "warm-r16-lr5e6",
        "lineage": "warm",
        "adapter": inventory,
        "rank": 16,
        "lora_alpha": 16,
        "target_modules": list(round2.LORA_TARGET_MODULES),
        "base_lineage": {
            "observed": {
                "tree_sha256": "b" * 64,
                "root": "/old-host/incumbent-muta-merged",
            }
        },
        "tokenization": {"train": {"rows": 20000}},
        "trainer_global_step": 313,
        **(manifest_update or {}),
    }
    manifest_path = adapter.parent / "training-manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    (adapter.parent / "COMPLETED.json").write_text(
        json.dumps(
            {
                "run_name": "warm-r16-lr5e6",
                "training_manifest_sha256": round2.sha256_file(manifest_path),
            }
        )
    )
    args = round2.parse_args(_required_args())
    args.model = tmp_path / "base-on-new-host"
    args.initial_adapter = adapter
    args.expected_initial_adapter_tree_sha256 = inventory["tree_sha256"]
    return args, lineage


def test_initial_adapter_verifies_entire_inventory_and_cross_host_base(tmp_path):
    args, lineage = _initial_adapter_fixture(tmp_path)
    receipt = round2._verify_initial_adapter(args, lineage=lineage)
    assert receipt["prior_training_rows"] == 20000
    assert receipt["source_run_name"] == "warm-r16-lr5e6"
    (args.initial_adapter / "extra.txt").write_text("added file")
    with pytest.raises(round2.CampaignInputError, match="tree SHA-256 mismatch"):
        round2._verify_initial_adapter(args, lineage=lineage)


@pytest.mark.parametrize(
    "field,value",
    [
        ("r", 32),
        ("lora_alpha", 32),
        ("target_modules", ["q_proj"]),
        ("use_rslora", True),
        ("rank_pattern", {"q_proj": 8}),
        ("base_model_name_or_path", "different-base"),
    ],
)
def test_initial_adapter_refuses_incompatible_config(tmp_path, field, value):
    args, lineage = _initial_adapter_fixture(tmp_path, config_update={field: value})
    with pytest.raises(round2.CampaignInputError):
        round2._verify_initial_adapter(args, lineage=lineage)


def test_initial_adapter_refuses_wrong_hash_and_base(tmp_path):
    args, lineage = _initial_adapter_fixture(tmp_path)
    original_hash = args.expected_initial_adapter_tree_sha256
    args.expected_initial_adapter_tree_sha256 = "0" * 64
    with pytest.raises(round2.CampaignInputError, match="tree SHA-256 mismatch"):
        round2._verify_initial_adapter(args, lineage=lineage)
    args.expected_initial_adapter_tree_sha256 = original_hash
    lineage["observed"]["tree_sha256"] = "c" * 64
    with pytest.raises(round2.CampaignInputError, match="base lineage mismatch"):
        round2._verify_initial_adapter(args, lineage=lineage)


def test_initial_adapter_refuses_modified_source_manifest(tmp_path):
    args, lineage = _initial_adapter_fixture(tmp_path)
    (args.initial_adapter.parent / "training-manifest.json").write_text("{}")
    with pytest.raises(round2.CampaignInputError, match="manifest receipt mismatch"):
        round2._verify_initial_adapter(args, lineage=lineage)


def test_resume_signature_binds_initial_adapter_and_fresh_vs_continuation(tmp_path):
    args = round2.parse_args(_required_args())
    artifact = SimpleNamespace(manifest_sha256="d" * 64, fingerprint="e" * 64)
    inputs = {
        "args": args,
        "dataset": artifact,
        "validation": artifact,
        "lineage": {"observed": {"tree_sha256": "b" * 64}, "receipt_sha256": "f" * 64},
        "tokenizer_receipt": {},
        "campaign_config": None,
        "script_dir": HERE,
        "packages": {},
    }
    fresh = round2._resume_signature(**inputs)
    initial = {"inventory": {"tree_sha256": "1" * 64}}
    continuation = round2._resume_signature(**inputs, initial_adapter=initial)
    assert fresh["sha256"] != continuation["sha256"]
    initial["inventory"]["tree_sha256"] = "2" * 64
    assert (
        round2._resume_signature(**inputs, initial_adapter=initial)["sha256"]
        != continuation["sha256"]
    )
    # Resume path does not alter the stage identity; initial adapter identity does.
    args.resume_from_checkpoint = tmp_path / "checkpoints" / "checkpoint-12"
    assert round2._resume_signature(**inputs)["sha256"] == fresh["sha256"]


class ArrayTensor:
    """Small CPU tensor double: production code still uses real torch on the GPU."""

    def __init__(self, value, *, trainable=False):
        self.value = np.asarray(value, dtype=np.float32)
        self.requires_grad = trainable

    @property
    def shape(self):
        return self.value.shape

    @property
    def dtype(self):
        return self.value.dtype

    def detach(self):
        return self

    def cpu(self):
        return self

    def contiguous(self):
        return self

    def view(self, dtype):
        return SimpleNamespace(numpy=lambda: self.value.view(dtype))

    def numel(self):
        return self.value.size

    def copy_(self, other):
        self.value[:] = other.value


class TensorTorch:
    uint8 = np.uint8
    no_grad = staticmethod(nullcontext)

    @staticmethod
    def isfinite(value):
        return np.isfinite(value.value)


def _model_and_source():
    prefix = "base_model.model.model.layers.0.self_attn.q_proj"
    parameters = {
        f"{prefix}.base_layer.weight": ArrayTensor([[9, 8], [7, 6]]),
        f"{prefix}.lora_A.default.weight": ArrayTensor([[0, 0]], trainable=True),
        f"{prefix}.lora_B.default.weight": ArrayTensor([[0], [0]], trainable=True),
    }
    source = {
        f"{prefix}.lora_A.weight": ArrayTensor([[1, 2]]),
        f"{prefix}.lora_B.weight": ArrayTensor([[3], [4]]),
    }
    model = SimpleNamespace(
        peft_config={"default": object()},
        active_adapters=["default"],
        named_parameters=lambda: list(parameters.items()),
        modules=list,
    )
    return model, source, parameters


def test_initial_adapter_copies_all_exact_weights_without_merging_or_training_base():
    model, source, parameters = _model_and_source()
    before_base = next(iter(parameters.values())).value.copy()
    receipt = round2._copy_initial_adapter_state(model, source, torch_module=TensorTorch)
    assert receipt["tensor_count"] == 2
    assert receipt["trainable_parameters"] == 4
    assert receipt["source_tensor_sha256"] == receipt["loaded_tensor_sha256"]
    assert receipt["before_tensor_sha256"] != receipt["loaded_tensor_sha256"]
    assert receipt["exact_source_values_loaded"] is True
    for name, tensor in source.items():
        target = parameters[name.replace(".weight", ".default.weight")]
        np.testing.assert_array_equal(tensor.value, target.value)
    np.testing.assert_array_equal(before_base, next(iter(parameters.values())).value)


@pytest.mark.parametrize(
    "mutation", ["missing", "extra", "shape", "nan", "base_trainable", "two_adapters", "merged"]
)
def test_initial_adapter_tensor_loading_fails_closed(mutation):
    model, source, parameters = _model_and_source()
    if mutation == "missing":
        source.pop(next(iter(source)))
    elif mutation == "extra":
        source["extra.weight"] = ArrayTensor([1])
    elif mutation == "shape":
        source[next(iter(source))] = ArrayTensor([1])
    elif mutation == "nan":
        source[next(iter(source))].value[0, 0] = np.nan
    elif mutation == "base_trainable":
        next(iter(parameters.values())).requires_grad = True
    elif mutation == "two_adapters":
        model.peft_config["other"] = object()
    elif mutation == "merged":
        model.modules = lambda: [SimpleNamespace(merged_adapters=["default"])]
    with pytest.raises(round2.CampaignInputError):
        round2._copy_initial_adapter_state(model, source, torch_module=TensorTorch)


def test_own_stage_resume_does_not_load_original_pilot_weights():
    args = SimpleNamespace(resume_from_checkpoint=Path("checkpoints/checkpoint-12"))
    receipt = round2._initialize_adapter(
        None, args=args, receipt={"verified": True}, torch_module=None
    )
    assert receipt == {"operation": "defer_to_own_stage_checkpoint", "pilot_weights_loaded": False}
