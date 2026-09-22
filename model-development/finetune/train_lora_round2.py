#!/usr/bin/env python3
"""Train one provenance-complete Muta round-two BF16 LoRA candidate."""

from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import random
import re
import subprocess
import time
import traceback
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from campaign_io import (
    CampaignInputError,
    inventory_tree,
    select_lowest_hash_indices,
    select_pilot_indices,
    sha256_file,
    verify_dataset_manifest,
)
from train_lora import common_prefix_length, message_content, normalize_token_ids

PRIVATE_SOURCES = frozenset({"waec_elearning", "cheetahwaec"})
LORA_TARGET_MODULES = (
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
)


def parse_milestone_steps(value: str) -> tuple[int, ...]:
    parts = value.split(",")
    if not parts or any(not part for part in parts):
        raise argparse.ArgumentTypeError("milestone steps must be comma-separated integers")
    try:
        steps = tuple(int(part) for part in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "milestone steps must be comma-separated integers"
        ) from exc
    if not steps or any(step < 1 for step in steps):
        raise argparse.ArgumentTypeError("milestone steps must be positive")
    if tuple(sorted(set(steps))) != steps:
        raise argparse.ArgumentTypeError("milestone steps must be unique and ascending")
    return steps


def apply_milestone_control(*, step: int, milestones: tuple[int, ...], control):
    """Request evaluation and checkpointing only at an explicit optimizer step."""
    if step in milestones:
        control.should_evaluate = True
        control.should_save = True
    return control


def validate_milestone_evidence(
    *,
    milestones: tuple[int, ...],
    observed_eval_steps: list[int],
    session_save_steps: list[int],
    surviving_checkpoint_steps: list[int],
    resume_step: int | None,
    planned_steps: int,
) -> None:
    """Validate milestones without mistaking checkpoint rotation for a missed save."""
    if not milestones:
        return
    if observed_eval_steps != list(milestones):
        raise RuntimeError(
            f"observed validation steps {observed_eval_steps} != milestones {list(milestones)}"
        )
    expected_session_saves = [
        step for step in milestones if resume_step is None or step > resume_step
    ]
    if session_save_steps != expected_session_saves:
        raise RuntimeError(
            "observed checkpoint-save callbacks "
            f"{session_save_steps} != session milestones {expected_session_saves}"
        )
    if (
        planned_steps not in surviving_checkpoint_steps
        or len(surviving_checkpoint_steps) > 3
        or not set(surviving_checkpoint_steps).issubset(milestones)
    ):
        raise RuntimeError(
            "surviving checkpoints violate final/save_total_limit/milestone constraints: "
            f"{surviving_checkpoint_steps}"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--base-lineage", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--tokenizer-lineage", type=Path, required=True)
    parser.add_argument("--lineage", choices=("clean", "warm"), required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--validation-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--learning-rate", type=float, default=1e-5)
    parser.add_argument("--rank", type=int, choices=(8, 16, 32, 64), default=16)
    parser.add_argument("--lora-alpha", type=int)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--eval-batch-size", type=int, default=16)
    parser.add_argument("--gradient-accumulation", type=int, default=4)
    parser.add_argument("--max-steps", type=int, default=-1)
    parser.add_argument("--eval-steps", type=int, default=250)
    parser.add_argument("--save-steps", type=int)
    parser.add_argument("--logging-steps", type=int, default=10)
    parser.add_argument("--warmup-ratio", type=float, default=0.03)
    parser.add_argument("--weight-decay", type=float, default=0.0)
    parser.add_argument("--pilot-rows", type=int)
    parser.add_argument("--validation-rows", type=int)
    parser.add_argument("--expected-train-rows", type=int)
    parser.add_argument("--expected-validation-rows", type=int)
    parser.add_argument("--expected-planned-steps", type=int)
    parser.add_argument("--expected-dataset-fingerprint")
    parser.add_argument("--expected-validation-fingerprint")
    parser.add_argument("--campaign-config", type=Path)
    parser.add_argument("--expected-campaign-config-sha256")
    parser.add_argument("--milestone-steps", type=parse_milestone_steps)
    parser.add_argument(
        "--private-policy",
        choices=("include", "exclude"),
        default="include",
    )
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument("--resume-from-checkpoint", type=Path)
    parser.add_argument("--initial-adapter", type=Path)
    parser.add_argument("--expected-initial-adapter-tree-sha256")
    parser.add_argument("--dataloader-workers", type=int, default=4)
    args = parser.parse_args(argv)
    if args.max_length < 64:
        parser.error("--max-length must be at least 64")
    for name in (
        "batch_size",
        "eval_batch_size",
        "gradient_accumulation",
        "eval_steps",
        "save_steps",
        "logging_steps",
        "lora_alpha",
    ):
        value = getattr(args, name)
        if value is not None and value < 1:
            parser.error(f"--{name.replace('_', '-')} must be positive")
    if args.max_steps == 0 or args.max_steps < -1:
        parser.error("--max-steps must equal -1 or be positive")
    for name in ("epochs", "learning_rate", "warmup_ratio", "weight_decay"):
        value = getattr(args, name)
        if not math.isfinite(value):
            parser.error(f"--{name.replace('_', '-')} must be finite")
    if args.epochs <= 0 or args.learning_rate <= 0:
        parser.error("--epochs and --learning-rate must be positive")
    if not 0 <= args.warmup_ratio <= 1:
        parser.error("--warmup-ratio must be between zero and one")
    if args.weight_decay < 0:
        parser.error("--weight-decay must be non-negative")
    if args.dataloader_workers < 0:
        parser.error("--dataloader-workers must be non-negative")
    if args.pilot_rows is not None and args.pilot_rows < 1:
        parser.error("--pilot-rows must be positive")
    if args.validation_rows is not None and args.validation_rows < 1:
        parser.error("--validation-rows must be positive")
    for name in (
        "expected_train_rows",
        "expected_validation_rows",
        "expected_planned_steps",
    ):
        if getattr(args, name) is not None and getattr(args, name) < 1:
            parser.error(f"--{name.replace('_', '-')} must be positive")
    for name in (
        "expected_dataset_fingerprint",
        "expected_validation_fingerprint",
        "expected_campaign_config_sha256",
        "expected_initial_adapter_tree_sha256",
    ):
        value = getattr(args, name)
        if value is not None and (
            len(value) != 64 or any(char not in "0123456789abcdef" for char in value)
        ):
            parser.error(f"--{name.replace('_', '-')} must be lowercase SHA-256")
    if (args.campaign_config is None) != (args.expected_campaign_config_sha256 is None):
        parser.error(
            "--campaign-config and --expected-campaign-config-sha256 must be supplied together"
        )
    if args.lora_alpha is None:
        args.lora_alpha = args.rank
    if (args.initial_adapter is None) != (args.expected_initial_adapter_tree_sha256 is None):
        parser.error(
            "--initial-adapter and --expected-initial-adapter-tree-sha256 must be supplied together"
        )
    if args.save_steps is None:
        args.save_steps = args.eval_steps
    return args


def _json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


@contextmanager
def _exclusive_run_lock(output: Path):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    lock_path = output / ".training.lock"
    with lock_path.open("a", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"another trainer owns this run directory: {output}") from exc
        # DataLoader/Dataset workers fork after this point. FD_CLOEXEC does not
        # protect a flock from fork inheritance: an orphan worker could retain
        # the parent's open-file-description lock after the trainer is killed.
        # Close only the child's reference; LOCK_UN would also unlock the parent.
        def close_in_forked_worker():
            if not handle.closed:
                handle.close()

        os.register_at_fork(after_in_child=close_in_forked_worker)
        yield


def _git_receipt(repo: Path) -> dict[str, Any]:
    def git(*parts: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo), *parts],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    try:
        sha = git("rev-parse", "HEAD")
        status = git("status", "--porcelain=v1")
        diff = subprocess.run(
            ["git", "-C", str(repo), "diff", "--binary", "HEAD"],
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return {"available": False}
    return {
        "available": True,
        "commit": sha,
        "dirty": bool(status),
        "status": status.splitlines(),
        "diff_sha256": hashlib.sha256(diff).hexdigest(),
    }


def _package_versions() -> dict[str, str]:
    names = (
        "accelerate",
        "bitsandbytes",
        "datasets",
        "huggingface-hub",
        "matplotlib",
        "numpy",
        "peft",
        "safetensors",
        "torch",
        "transformers",
        "triton",
        "trl",
        "unsloth",
        "xformers",
    )
    versions = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not-installed"
    return versions


def _verify_lineage(path: Path, *, expected_lineage: str, model_path: Path) -> dict:
    lineage = json.loads(path.read_text(encoding="utf-8"))
    if lineage.get("lineage") != expected_lineage:
        raise CampaignInputError(
            f"lineage receipt says {lineage.get('lineage')!r}, expected {expected_lineage!r}"
        )
    expected_tree = lineage.get("training_base", {}).get("tree_sha256")
    if not expected_tree:
        raise CampaignInputError("lineage receipt has no training-base tree digest")
    observed = inventory_tree(model_path)
    if observed["tree_sha256"] != expected_tree:
        raise CampaignInputError("training-base tree digest does not match lineage receipt")
    return {"receipt": lineage, "receipt_sha256": sha256_file(path), "observed": observed}


def _verify_tokenizer(path: Path, *, lineage_path: Path) -> dict[str, Any]:
    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    if lineage.get("lineage") != "clean":
        raise CampaignInputError("tokenizer lineage must be the clean upstream receipt")
    expected = {
        row["path"]: row
        for row in lineage["training_base"]["files"]
        if row["path"] in {"tokenizer.json", "tokenizer_config.json"}
    }
    if set(expected) != {"tokenizer.json", "tokenizer_config.json"}:
        raise CampaignInputError("clean lineage is missing tokenizer receipts")
    observed = {}
    for name, receipt in expected.items():
        target = path / name
        if not target.is_file() or sha256_file(target) != receipt["sha256"]:
            raise CampaignInputError(f"tokenizer receipt mismatch: {name}")
        observed[name] = {
            "path": str(target.resolve()),
            "bytes": target.stat().st_size,
            "sha256": receipt["sha256"],
        }
    return {
        "lineage_receipt_sha256": sha256_file(lineage_path),
        "files": observed,
    }


def _verify_initial_adapter(
    args: argparse.Namespace, *, lineage: dict[str, Any]
) -> dict[str, Any] | None:
    """Bind a new-stage initializer to a completed pilot and its unmerged parent."""
    if args.initial_adapter is None:
        return None
    path = args.initial_adapter
    if path.is_symlink() or path.name != "adapter":
        raise CampaignInputError("initial adapter must be a completed run's adapter directory")
    observed = inventory_tree(path)
    if observed["tree_sha256"] != args.expected_initial_adapter_tree_sha256:
        raise CampaignInputError("initial adapter tree SHA-256 mismatch")
    root = path.parent
    manifest_path, completion_path = root / "training-manifest.json", root / "COMPLETED.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        completion = json.loads(completion_path.read_text(encoding="utf-8"))
        config = json.loads((path / "adapter_config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CampaignInputError("initial adapter needs complete pilot provenance/config") from exc
    if completion.get("training_manifest_sha256") != sha256_file(manifest_path):
        raise CampaignInputError("initial adapter training-manifest receipt mismatch")
    if completion.get("run_name") != manifest.get("run_name"):
        raise CampaignInputError("initial adapter completion run identity mismatch")
    expected = manifest.get("adapter", {})
    for key in ("tree_sha256", "files", "bytes", "file_count"):
        if expected.get(key) != observed[key]:
            raise CampaignInputError(f"initial adapter manifest inventory mismatch: {key}")
    prior_base = manifest.get("base_lineage", {}).get("observed", {})
    if (
        prior_base.get("tree_sha256") != lineage["observed"]["tree_sha256"]
        or manifest.get("lineage") != args.lineage
        or config.get("base_model_name_or_path") != prior_base.get("root")
        or (args.model / "adapter_config.json").exists()
    ):
        raise CampaignInputError("initial adapter base lineage mismatch or stacked adapter base")
    if (
        config.get("r") != args.rank
        or config.get("lora_alpha") != args.lora_alpha
        or manifest.get("rank") != args.rank
        or manifest.get("lora_alpha") != args.lora_alpha
    ):
        raise CampaignInputError("initial adapter rank/alpha mismatch")
    if (
        config.get("peft_type") != "LORA"
        or config.get("task_type") != "CAUSAL_LM"
        or set(config.get("target_modules") or ()) != set(LORA_TARGET_MODULES)
        or set(manifest.get("target_modules") or ()) != set(LORA_TARGET_MODULES)
        or config.get("bias") != "none"
        or config.get("lora_dropout") != 0
    ):
        raise CampaignInputError("initial adapter type/modules/dropout/bias mismatch")
    for key in (
        "rank_pattern",
        "alpha_pattern",
        "modules_to_save",
        "use_dora",
        "use_rslora",
        "use_qalora",
        "use_bdlora",
        "lora_bias",
        "fan_in_fan_out",
        "layer_replication",
        "layers_pattern",
        "layers_to_transform",
        "target_parameters",
        "exclude_modules",
        "trainable_token_indices",
        "alora_invocation_tokens",
        "arrow_config",
        "corda_config",
        "eva_config",
        "loftq_config",
        "lora_ga_config",
        "monteclora_config",
        "velora_config",
        "megatron_config",
        "ensure_weight_tying",
    ):
        if config.get(key):
            raise CampaignInputError(f"unsupported initial adapter configuration: {key}")
    if not (path / "adapter_model.safetensors").is_file():
        raise CampaignInputError("initial adapter must have adapter_model.safetensors")
    return {
        "kind": "completed_pilot_adapter_new_stage",
        "optimizer_and_schedule": "fresh; own-stage checkpoints alone may resume state",
        "inventory": observed,
        "config": config,
        "training_manifest_sha256": sha256_file(manifest_path),
        "completion_sha256": sha256_file(completion_path),
        "source_run_name": manifest["run_name"],
        "training_base_tree_sha256": prior_base["tree_sha256"],
        "prior_training_rows": manifest.get("tokenization", {}).get("train", {}).get("rows"),
        "prior_trainer_global_step": manifest.get("trainer_global_step"),
    }


def _adapter_tensor_digest(state: dict, torch_module) -> str:
    digest = hashlib.sha256()
    for name, value in sorted(state.items()):
        value = value.detach().cpu().contiguous()
        header = json.dumps(
            [name, str(value.dtype), list(value.shape)], separators=(",", ":")
        ).encode("utf-8")
        digest.update(len(header).to_bytes(8, "big"))
        digest.update(header)
        digest.update(value.view(torch_module.uint8).numpy().tobytes())
    return digest.hexdigest()


def _copy_initial_adapter_state(model, state: dict, *, torch_module) -> dict[str, Any]:
    """Copy (never merge) the exact adapter tensor set into the single trainable slot."""
    if set(model.peft_config) != {"default"} or model.active_adapters != ["default"]:
        raise CampaignInputError("initialization requires exactly one active default adapter")
    expected = {}
    for name, parameter in model.named_parameters():
        match = re.fullmatch(r"(.+)\.(lora_[AB])\.default\.weight", name)
        if match:
            if not parameter.requires_grad:
                raise CampaignInputError(f"initial adapter tensor is not trainable: {name}")
            expected[f"{match[1]}.{match[2]}.weight"] = parameter
        elif parameter.requires_grad or ".lora_" in name:
            raise CampaignInputError(f"unexpected trainable or adapter parameter: {name}")
    for module in model.modules():
        if (
            getattr(module, "merged_adapters", ())
            or getattr(module, "disable_adapters", False) is True
        ):
            raise CampaignInputError("initialization refuses merged or disabled adapters")
    if not expected or set(state) != set(expected):
        raise CampaignInputError(
            "initial adapter tensor keys mismatch: "
            f"missing={sorted(set(expected) - set(state))}, "
            f"unexpected={sorted(set(state) - set(expected))}"
        )
    for name, parameter in expected.items():
        value = state[name]
        if value.shape != parameter.shape or value.dtype != parameter.dtype:
            raise CampaignInputError(f"initial adapter shape/dtype mismatch: {name}")
        if not bool(torch_module.isfinite(value).all()):
            raise CampaignInputError(f"nonfinite initial adapter tensor: {name}")
    before = _adapter_tensor_digest(expected, torch_module)
    source = _adapter_tensor_digest(state, torch_module)
    with torch_module.no_grad():
        for name, parameter in expected.items():
            parameter.copy_(state[name])
    loaded = _adapter_tensor_digest(expected, torch_module)
    if loaded != source:
        raise CampaignInputError("initial adapter loaded tensor values do not match source")
    return {
        "operation": "copy_exact_adapter_tensors_once_no_merge",
        "tensor_count": len(expected),
        "trainable_parameters": sum(parameter.numel() for parameter in expected.values()),
        "tensor_keys": sorted(expected),
        "before_tensor_sha256": before,
        "source_tensor_sha256": source,
        "loaded_tensor_sha256": loaded,
        "exact_source_values_loaded": True,
    }


def _initialize_adapter(model, *, args, receipt, torch_module) -> dict[str, Any] | None:
    if receipt is None:
        return None
    # Resume restores this stage's adapter, optimizer and schedule through Trainer.
    # Never replace the resumed checkpoint with the original pilot initializer.
    if args.resume_from_checkpoint is not None:
        return {"operation": "defer_to_own_stage_checkpoint", "pilot_weights_loaded": False}
    from safetensors.torch import load_file

    expected_sha = receipt["inventory"]["tree_sha256"]
    if inventory_tree(args.initial_adapter)["tree_sha256"] != expected_sha:
        raise CampaignInputError("initial adapter changed before loading")
    state = load_file(str(args.initial_adapter / "adapter_model.safetensors"), device="cpu")
    loaded = _copy_initial_adapter_state(model, state, torch_module=torch_module)
    if inventory_tree(args.initial_adapter)["tree_sha256"] != expected_sha:
        raise CampaignInputError("initial adapter changed during loading")
    return {
        **loaded,
        "source_tree_sha256_before": expected_sha,
        "source_tree_sha256_after": expected_sha,
    }


def _row_source(row: dict) -> str:
    if row.get("source_id"):
        return str(row["source_id"])
    provenance = row.get("provenance")
    if not isinstance(provenance, dict) or not provenance.get("source_id"):
        raise CampaignInputError(f"row {row.get('id')} has no provenance.source_id")
    return str(provenance["source_id"])


def projected_jsonl_rows(paths: list[str]):
    """Project heterogeneous records into one stable training schema."""
    for raw_path in paths:
        path = Path(raw_path)
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    yield {
                        "id": str(row["id"]),
                        "prompt": str(row["prompt"]),
                        "completion": str(row["completion"]),
                        "mode": str(row["mode"]),
                        "source_id": _row_source(row),
                    }
                except (KeyError, TypeError, json.JSONDecodeError) as exc:
                    raise CampaignInputError(
                        f"invalid projected training row at {path}:{line_number}"
                    ) from exc


def _write_metrics(output: Path, log_history: list[dict[str, Any]]) -> None:
    metrics = output / "metrics.jsonl"
    with metrics.open("w", encoding="utf-8") as handle:
        for row in log_history:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    fields = sorted({key for row in log_history for key in row})
    with (output / "metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(log_history)

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    train = [(row.get("step"), row["loss"]) for row in log_history if "loss" in row]
    evaluation = [(row.get("step"), row["eval_loss"]) for row in log_history if "eval_loss" in row]
    if not train and not evaluation:
        raise RuntimeError("Trainer history contains no loss values")
    figure, axis = plt.subplots(figsize=(8, 5))
    if train:
        axis.plot(*zip(*train, strict=True), label="train", linewidth=1.5)
    if evaluation:
        axis.plot(*zip(*evaluation, strict=True), label="validation", marker="o")
    axis.set(xlabel="optimizer step", ylabel="loss", title="Muta fine-tuning loss")
    axis.grid(alpha=0.25)
    axis.legend()
    figure.tight_layout()
    figure.savefig(output / "loss-curve.png", dpi=180)
    figure.savefig(output / "loss-curve.svg")
    plt.close(figure)


def _id_digest(ids: list[str]) -> str:
    return hashlib.sha256("\n".join(ids).encode()).hexdigest()


def _campaign_config_receipt(
    path: Path | None, *, expected_sha256: str | None
) -> dict[str, Any] | None:
    if path is None:
        if expected_sha256 is not None:
            raise CampaignInputError("campaign config digest was supplied without its file")
        return None
    path = path.resolve()
    if not path.is_file() or expected_sha256 is None:
        raise CampaignInputError("campaign config and expected digest must both be supplied")
    observed = sha256_file(path)
    if observed != expected_sha256:
        raise CampaignInputError(
            f"campaign config SHA-256 mismatch: {observed} != {expected_sha256}"
        )
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": observed}


def _checkpoint_step(path: Path, *, checkpoint_root: Path) -> int:
    """Return a checkpoint step only for a direct, complete child of this run."""
    path = path.resolve()
    checkpoint_root = checkpoint_root.resolve()
    if path.parent != checkpoint_root:
        raise CampaignInputError(f"checkpoint is outside this run: {path}")
    suffix = path.name.removeprefix("checkpoint-")
    if not suffix.isdigit() or not (path / "trainer_state.json").is_file():
        raise CampaignInputError(f"invalid or incomplete checkpoint: {path}")
    return int(suffix)


def _complete_checkpoint_steps(checkpoint_root: Path) -> list[int]:
    """List direct checkpoints, refusing evidence from an interrupted save."""
    steps = []
    incomplete = []
    for checkpoint in checkpoint_root.glob("checkpoint-*"):
        suffix = checkpoint.name.removeprefix("checkpoint-")
        if suffix.isdigit() and (checkpoint / "trainer_state.json").is_file():
            steps.append(int(suffix))
        else:
            incomplete.append(checkpoint.name)
    if incomplete:
        raise CampaignInputError(
            "incomplete checkpoint evidence must be preserved and resolved before resume: "
            + ", ".join(sorted(incomplete))
        )
    return sorted(steps)


def _selected_adapter_receipt(
    *, trainer, output: Path, adapter_dir: Path, milestones: tuple[int, ...]
) -> dict[str, Any]:
    """Prove which validation-selected checkpoint produced the final adapter."""
    best_path_raw = trainer.state.best_model_checkpoint
    best_metric = trainer.state.best_metric
    if (
        not best_path_raw
        or best_metric is None
        or not math.isfinite(float(best_metric))
        or float(best_metric) < 0
    ):
        raise RuntimeError("Trainer did not identify a finite best validation checkpoint")
    best_path = Path(best_path_raw)
    if not best_path.is_absolute():
        best_path = (Path.cwd() / best_path).resolve()
    step = _checkpoint_step(best_path, checkpoint_root=output / "checkpoints")
    if milestones and step not in milestones:
        raise RuntimeError(f"best checkpoint step {step} is not a requested milestone")
    checkpoint_weights = best_path / "adapter_model.safetensors"
    final_weights = adapter_dir / "adapter_model.safetensors"
    if not checkpoint_weights.is_file() or not final_weights.is_file():
        raise RuntimeError("best checkpoint or final adapter has no safetensors weights")
    checkpoint_sha = sha256_file(checkpoint_weights)
    final_sha = sha256_file(final_weights)
    if checkpoint_sha != final_sha:
        raise RuntimeError("final adapter weights do not match Trainer's best checkpoint")
    checkpoint_config = best_path / "adapter_config.json"
    final_config = adapter_dir / "adapter_config.json"
    if not checkpoint_config.is_file() or not final_config.is_file():
        raise RuntimeError("best checkpoint or final adapter has no adapter config")
    checkpoint_config_sha = sha256_file(checkpoint_config)
    final_config_sha = sha256_file(final_config)
    if checkpoint_config_sha != final_config_sha:
        raise RuntimeError("final adapter config does not match Trainer's best checkpoint")
    return {
        "policy": "minimum_eval_loss",
        "best_metric_name": "eval_loss",
        "best_metric": float(best_metric),
        "best_checkpoint_step": step,
        "best_checkpoint_relative_path": best_path.relative_to(output).as_posix(),
        "best_checkpoint_adapter_model_sha256": checkpoint_sha,
        "final_adapter_model_sha256": final_sha,
        "best_checkpoint_adapter_config_sha256": checkpoint_config_sha,
        "final_adapter_config_sha256": final_config_sha,
    }


def _resume_signature(
    *,
    args: argparse.Namespace,
    dataset,
    validation,
    lineage: dict[str, Any],
    tokenizer_receipt: dict[str, Any],
    campaign_config: dict[str, Any] | None,
    script_dir: Path,
    packages: dict[str, str],
    initial_adapter: dict[str, Any] | None = None,
) -> dict[str, Any]:
    treatment = {
        "run_name": args.run_name,
        "lineage": args.lineage,
        "training_base_tree_sha256": lineage["observed"]["tree_sha256"],
        "base_lineage_receipt_sha256": lineage["receipt_sha256"],
        "tokenizer": tokenizer_receipt,
        "dataset_manifest_sha256": dataset.manifest_sha256,
        "dataset_fingerprint_sha256": dataset.fingerprint,
        "validation_manifest_sha256": validation.manifest_sha256,
        "validation_fingerprint_sha256": validation.fingerprint,
        "campaign_config_sha256": campaign_config["sha256"] if campaign_config else None,
        "initial_adapter": initial_adapter,
        "max_length": args.max_length,
        "epochs": args.epochs,
        "learning_rate": args.learning_rate,
        "warmup_ratio": args.warmup_ratio,
        "weight_decay": args.weight_decay,
        "rank": args.rank,
        "lora_alpha": args.lora_alpha,
        "batch_size": args.batch_size,
        "eval_batch_size": args.eval_batch_size,
        "gradient_accumulation": args.gradient_accumulation,
        "max_steps": args.max_steps,
        "eval_steps": args.eval_steps,
        "save_steps": args.save_steps,
        "logging_steps": args.logging_steps,
        "pilot_rows": args.pilot_rows,
        "validation_rows": args.validation_rows,
        "expected_train_rows": args.expected_train_rows,
        "expected_validation_rows": args.expected_validation_rows,
        "expected_planned_steps": args.expected_planned_steps,
        "milestone_steps": list(args.milestone_steps or ()),
        "private_policy": args.private_policy,
        "seed": args.seed,
        "dataloader_workers": args.dataloader_workers,
        "world_size": int(os.environ.get("WORLD_SIZE", "1")),
        "packages": packages,
        "scripts": {
            "train_lora_round2.py": sha256_file(Path(__file__)),
            "campaign_io.py": sha256_file(script_dir / "campaign_io.py"),
            "train_lora.py": sha256_file(script_dir / "train_lora.py"),
        },
    }
    digest = hashlib.sha256(
        json.dumps(treatment, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {"sha256": digest, "treatment": treatment}


def _cuda_memory_receipt(torch_module) -> dict[str, int | str]:
    """Capture allocator counters in bytes without relying on human-formatted logs."""
    device = torch_module.cuda.current_device()
    properties = torch_module.cuda.get_device_properties(device)
    return {
        "device_index": device,
        "device_name": properties.name,
        "device_total_bytes": properties.total_memory,
        "current_allocated_bytes": torch_module.cuda.memory_allocated(device),
        "current_reserved_bytes": torch_module.cuda.memory_reserved(device),
        "peak_allocated_bytes": torch_module.cuda.max_memory_allocated(device),
        "peak_reserved_bytes": torch_module.cuda.max_memory_reserved(device),
    }


def tokenize_chat_row(row, *, tokenizer, max_length: int) -> dict[str, list[int] | int]:
    """Apply the model template and mask every non-assistant token."""
    if row.get("mode") != "chat":
        raise CampaignInputError(f"row {row.get('id')} is not chat mode")
    multimodal_chat = hasattr(tokenizer, "image_processor")
    prompt_messages = [
        {
            "role": "user",
            "content": message_content(row["prompt"], multimodal=multimodal_chat),
        }
    ]
    full_messages = prompt_messages + [
        {
            "role": "assistant",
            "content": message_content(row["completion"], multimodal=multimodal_chat),
        }
    ]
    prompt_ids = normalize_token_ids(
        tokenizer.apply_chat_template(prompt_messages, tokenize=True, add_generation_prompt=True)
    )
    full_ids = normalize_token_ids(
        tokenizer.apply_chat_template(full_messages, tokenize=True, add_generation_prompt=False)
    )
    start = common_prefix_length(prompt_ids, full_ids)
    if start >= len(full_ids):
        raise CampaignInputError(f"completion produced no trainable tokens for row {row.get('id')}")
    if len(full_ids) > max_length:
        raise CampaignInputError(f"row {row.get('id')} tokenizes to {len(full_ids)} > {max_length}")
    return {
        "input_ids": full_ids,
        "attention_mask": [1] * len(full_ids),
        "labels": [-100] * start + full_ids[start:],
        "sequence_length": len(full_ids),
        "assistant_tokens": len(full_ids) - start,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output / "COMPLETED.json").exists():
        raise FileExistsError(f"completed run already exists: {output}")

    # Unsloth otherwise writes generated modules into the current working tree.
    # A per-run cache also prevents concurrent candidates from racing over the
    # same generated module directory.
    os.environ.setdefault(
        "UNSLOTH_COMPILE_LOCATION",
        str(
            output.parent
            / (
                ".unsloth-compiled-cache-"
                + hashlib.sha256(args.run_name.encode("utf-8")).hexdigest()[:16]
            )
        ),
    )

    script_dir = Path(__file__).resolve().parent
    repo = script_dir.parents[1]
    dataset = verify_dataset_manifest(args.dataset_manifest)
    validation = verify_dataset_manifest(args.validation_manifest)
    if (
        args.expected_dataset_fingerprint is not None
        and dataset.fingerprint != args.expected_dataset_fingerprint
    ):
        raise CampaignInputError(
            "training dataset fingerprint does not match the frozen campaign config"
        )
    if (
        args.expected_validation_fingerprint is not None
        and validation.fingerprint != args.expected_validation_fingerprint
    ):
        raise CampaignInputError(
            "validation dataset fingerprint does not match the frozen campaign config"
        )
    campaign_config = _campaign_config_receipt(
        args.campaign_config,
        expected_sha256=args.expected_campaign_config_sha256,
    )
    lineage = _verify_lineage(
        args.base_lineage,
        expected_lineage=args.lineage,
        model_path=args.model,
    )
    tokenizer_receipt = _verify_tokenizer(args.tokenizer, lineage_path=args.tokenizer_lineage)
    initial_adapter = _verify_initial_adapter(args, lineage=lineage)
    packages = _package_versions()
    resume_signature = _resume_signature(
        args=args,
        dataset=dataset,
        validation=validation,
        lineage=lineage,
        tokenizer_receipt=tokenizer_receipt,
        campaign_config=campaign_config,
        script_dir=script_dir,
        packages=packages,
        initial_adapter=initial_adapter,
    )
    resume_step = None
    retry_from_scratch = False
    initial_resolved_path = output / "resolved-config.json"
    initial_resolved_receipt_path = output / "resolved-config.json.sha256"

    def verify_initial_resolved_receipt() -> None:
        try:
            parts = initial_resolved_receipt_path.read_text(encoding="ascii").strip().split()
        except OSError as exc:
            raise CampaignInputError("original resolved config has no immutable receipt") from exc
        if (
            len(parts) != 2
            or parts[0] != sha256_file(initial_resolved_path)
            or parts[1] != initial_resolved_path.name
        ):
            raise CampaignInputError("original resolved config receipt mismatch")

    if args.resume_from_checkpoint is not None:
        resume_step = _checkpoint_step(
            args.resume_from_checkpoint,
            checkpoint_root=output / "checkpoints",
        )
        if not initial_resolved_path.is_file():
            raise CampaignInputError("cannot resume without the original resolved config")
        verify_initial_resolved_receipt()
        complete_steps = _complete_checkpoint_steps(output / "checkpoints")
        if not complete_steps or resume_step != max(complete_steps):
            raise CampaignInputError("resume must use this run's latest complete checkpoint")
        try:
            initial_resolved = json.loads(initial_resolved_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CampaignInputError("cannot read original resolved config for resume") from exc
        if (
            Path(
                str(initial_resolved.get("resolved_output", initial_resolved.get("output", "")))
            ).resolve()
            != output
        ):
            raise CampaignInputError(
                "cross-path resume is unsupported because Trainer stores absolute best-checkpoint paths"
            )
        if initial_resolved.get("resume_signature", {}).get("sha256") != resume_signature["sha256"]:
            raise CampaignInputError("resume treatment differs from the original run")
    elif initial_resolved_path.exists():
        verify_initial_resolved_receipt()
        try:
            initial_resolved = json.loads(initial_resolved_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CampaignInputError("cannot read original resolved config for retry") from exc
        if initial_resolved.get("resume_signature", {}).get("sha256") != resume_signature["sha256"]:
            raise CampaignInputError("retry treatment differs from the original run")
        checkpoint_dirs = list((output / "checkpoints").glob("checkpoint-*"))
        if checkpoint_dirs:
            raise FileExistsError(
                "checkpoint evidence exists; resume an exact complete checkpoint instead"
            )
        retry_from_scratch = True
    elif list((output / "checkpoints").glob("checkpoint-*")):
        raise FileExistsError("checkpoint evidence exists without an original resolved config")

    resolved = {
        key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()
    }
    resolved.update(
        {
            "dataset": dataset.receipt(),
            "validation": validation.receipt(),
            "resolved_output": str(output),
            "campaign_config": campaign_config,
            "resume_signature": resume_signature,
            "resume_checkpoint_step": resume_step,
            "lineage_receipt_sha256": lineage["receipt_sha256"],
            "tokenizer": tokenizer_receipt,
            "initial_adapter_receipt": initial_adapter,
            "script_sha256": sha256_file(Path(__file__)),
            "campaign_io_sha256": sha256_file(script_dir / "campaign_io.py"),
            "git": _git_receipt(repo),
            "packages": packages,
        }
    )
    if args.resume_from_checkpoint is None and not retry_from_scratch:
        _json_write(initial_resolved_path, resolved)
        with initial_resolved_receipt_path.open("x", encoding="ascii") as handle:
            handle.write(f"{sha256_file(initial_resolved_path)}  {initial_resolved_path.name}\n")
    else:
        resume_dir = output / "resume-sessions"
        resume_dir.mkdir(exist_ok=True)
        action = f"resume-step-{resume_step}" if resume_step is not None else "retry-from-scratch"
        resume_path = resume_dir / f"{action}-{time.time_ns()}.json"
        _json_write(resume_path, resolved)
    running_path = output / "RUNNING.json"
    if running_path.is_file():
        running_sessions = output / "running-sessions"
        running_sessions.mkdir(exist_ok=True)
        os.replace(
            running_path,
            running_sessions / f"RUNNING-{time.time_ns()}.json",
        )
    _json_write(
        running_path,
        {
            "run_name": args.run_name,
            "started_unix": time.time(),
            "hostname": platform.node(),
            "pid": os.getpid(),
        },
    )
    failed_path = output / "FAILED.json"
    if failed_path.is_file():
        failed_sessions = output / "failed-sessions"
        failed_sessions.mkdir(exist_ok=True)
        os.replace(
            failed_path,
            failed_sessions / f"FAILED-{time.time_ns()}.json",
        )

    random.seed(args.seed)
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    from unsloth import FastLanguageModel  # noqa: I001
    import torch
    from datasets import Dataset, DatasetDict, Features, Value
    from transformers import (
        AutoTokenizer,
        DataCollatorForSeq2Seq,
        Trainer,
        TrainerCallback,
        TrainingArguments,
    )

    torch.manual_seed(args.seed)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(args.model),
        max_seq_length=args.max_length,
        load_in_4bit=False,
        load_in_16bit=True,
        full_finetuning=False,
        use_exact_model_name=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(
        str(args.tokenizer),
        use_fast=True,
        fix_mistral_regex=True,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=args.rank,
        target_modules=list(LORA_TARGET_MODULES),
        lora_alpha=args.lora_alpha,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=args.seed,
        max_seq_length=args.max_length,
    )
    initial_adapter_load = _initialize_adapter(
        model, args=args, receipt=initial_adapter, torch_module=torch
    )
    if initial_adapter_load is not None:
        _json_write(
            output / "initialization-sessions" / f"adapter-load-{time.time_ns()}.json",
            {
                "initial_adapter_receipt": initial_adapter,
                "load": initial_adapter_load,
                "resume_checkpoint_step": resume_step,
                "trainer_sha256": sha256_file(Path(__file__)),
            },
        )
    features = Features(
        {
            "id": Value("string"),
            "prompt": Value("string"),
            "completion": Value("string"),
            "mode": Value("string"),
            "source_id": Value("string"),
        }
    )
    train = Dataset.from_generator(
        projected_jsonl_rows,
        gen_kwargs={"paths": [str(path) for path in dataset.shard_paths]},
        features=features,
    )
    validation_rows = Dataset.from_generator(
        projected_jsonl_rows,
        gen_kwargs={"paths": [str(path) for path in validation.shard_paths]},
        features=features,
    )
    if len(train) != dataset.row_count:
        raise CampaignInputError(
            f"loaded {len(train)} rows from a {dataset.row_count}-row artifact"
        )

    source_counts_before = Counter(_row_source(row) for row in train)
    if args.private_policy == "exclude":
        train = train.filter(
            lambda row: row["source_id"] not in PRIVATE_SOURCES,
            desc="excluding private-use exam rows",
        )
    source_counts = Counter(_row_source(row) for row in train)
    if args.private_policy == "exclude" and PRIVATE_SOURCES & source_counts.keys():
        raise CampaignInputError("private-source exclusion failed")
    if args.pilot_rows:
        indices = select_pilot_indices(train["id"], rows=args.pilot_rows, seed=args.seed)
        train = train.select(indices)
    if args.validation_rows:
        indices = select_lowest_hash_indices(
            validation_rows["id"],
            rows=args.validation_rows,
            seed=args.seed,
            namespace="validation-subset",
        )
        validation_rows = validation_rows.select(indices)
    if args.expected_train_rows is not None and len(train) != args.expected_train_rows:
        raise CampaignInputError(
            f"selected training rows {len(train)} != expected {args.expected_train_rows}"
        )
    if (
        args.expected_validation_rows is not None
        and len(validation_rows) != args.expected_validation_rows
    ):
        raise CampaignInputError(
            "selected validation rows "
            f"{len(validation_rows)} != expected {args.expected_validation_rows}"
        )
    train = train.shuffle(seed=args.seed)
    validation_rows = validation_rows.shuffle(seed=args.seed)
    training_source_counts = Counter(train["source_id"])
    raw = DatasetDict(train=train, validation=validation_rows)

    text_tokenizer = getattr(tokenizer, "tokenizer", tokenizer)

    def tokenize(row):
        return tokenize_chat_row(row, tokenizer=tokenizer, max_length=args.max_length)

    tokenized = raw.map(
        tokenize,
        remove_columns=raw["train"].column_names,
        desc="tokenizing completion-masked chat examples",
    )
    if not tokenized["train"] or not tokenized["validation"]:
        raise CampaignInputError("tokenization removed an entire split")
    if min(tokenized["train"]["assistant_tokens"]) < 1:
        raise CampaignInputError("a training row has no assistant tokens")

    length_receipt = {
        split: {
            "rows": len(tokenized[split]),
            "sequence_tokens": sum(tokenized[split]["sequence_length"]),
            "assistant_tokens": sum(tokenized[split]["assistant_tokens"]),
            "max_sequence_tokens": max(tokenized[split]["sequence_length"]),
        }
        for split in ("train", "validation")
    }
    tokenized = tokenized.remove_columns(["sequence_length", "assistant_tokens"])

    world_size = int(os.environ.get("WORLD_SIZE", "1"))
    steps_per_epoch = math.ceil(
        len(tokenized["train"]) / (args.batch_size * args.gradient_accumulation * world_size)
    )
    planned_steps = (
        args.max_steps if args.max_steps > 0 else math.ceil(steps_per_epoch * args.epochs)
    )
    if args.expected_planned_steps is not None and planned_steps != args.expected_planned_steps:
        raise CampaignInputError(
            f"planned steps {planned_steps} != expected {args.expected_planned_steps}"
        )
    milestones = args.milestone_steps or ()
    if milestones and milestones[-1] != planned_steps:
        raise CampaignInputError(
            f"final milestone {milestones[-1]} != planned steps {planned_steps}"
        )
    warmup_steps = math.ceil(planned_steps * args.warmup_ratio)
    trainer_interval = planned_steps + 1 if milestones else args.eval_steps
    saved_milestone_steps: list[int] = []

    class ExplicitMilestoneCallback(TrainerCallback):
        def on_step_end(self, _args, state, control, **_kwargs):
            return apply_milestone_control(
                step=state.global_step,
                milestones=milestones,
                control=control,
            )

        def on_save(self, _args, state, control, **_kwargs):
            # ``save_total_limit`` may immediately rotate an older milestone out
            # of the checkpoint directory.  Record the callback event rather
            # than incorrectly requiring every historical checkpoint to survive.
            if state.global_step in milestones:
                saved_milestone_steps.append(int(state.global_step))
            return control

    training_args = TrainingArguments(
        output_dir=str(output / "checkpoints"),
        num_train_epochs=args.epochs,
        max_steps=args.max_steps,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.eval_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation,
        learning_rate=args.learning_rate,
        warmup_steps=warmup_steps,
        weight_decay=args.weight_decay,
        lr_scheduler_type="cosine",
        bf16=True,
        fp16=False,
        logging_steps=args.logging_steps,
        logging_first_step=True,
        eval_strategy="steps",
        eval_steps=trainer_interval,
        save_strategy="steps",
        save_steps=trainer_interval if milestones else args.save_steps,
        save_total_limit=3,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        optim="adamw_8bit",
        seed=args.seed,
        data_seed=args.seed,
        report_to="none",
        prediction_loss_only=True,
        remove_unused_columns=False,
        dataloader_num_workers=args.dataloader_workers,
    )
    collator = DataCollatorForSeq2Seq(
        tokenizer=text_tokenizer,
        padding=True,
        label_pad_token_id=-100,
        return_tensors="pt",
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized["train"],
        eval_dataset=tokenized["validation"],
        data_collator=collator,
        callbacks=[ExplicitMilestoneCallback()] if milestones else None,
    )
    torch.cuda.synchronize()
    gpu_memory_before_training = _cuda_memory_receipt(torch)
    torch.cuda.reset_peak_memory_stats()
    started = time.time()
    result = trainer.train(
        resume_from_checkpoint=(
            str(args.resume_from_checkpoint) if args.resume_from_checkpoint else None
        )
    )
    torch.cuda.synchronize()
    gpu_memory_training = _cuda_memory_receipt(torch)
    # Capture scheduled evidence before the explicit post-training evaluation.
    # Trainer has already reloaded the minimum-loss checkpoint when
    # load_best_model_at_end=True; the extra evaluation must not masquerade as a
    # missed final scheduled milestone.
    observed_eval_steps = [
        int(row["step"])
        for row in trainer.state.log_history
        if "eval_loss" in row and row.get("step") is not None
    ]
    observed_checkpoints = sorted(
        int(path.name.removeprefix("checkpoint-"))
        for path in (output / "checkpoints").glob("checkpoint-*")
        if path.name.removeprefix("checkpoint-").isdigit()
        and (path / "trainer_state.json").is_file()
    )
    validate_milestone_evidence(
        milestones=milestones,
        observed_eval_steps=observed_eval_steps,
        session_save_steps=saved_milestone_steps,
        surviving_checkpoint_steps=observed_checkpoints,
        resume_step=resume_step,
        planned_steps=planned_steps,
    )
    torch.cuda.reset_peak_memory_stats()
    evaluation = trainer.evaluate()
    if trainer.state.best_metric is None or not math.isclose(
        float(evaluation.get("eval_loss", math.nan)),
        float(trainer.state.best_metric),
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise RuntimeError(
            "post-training evaluation does not match Trainer's selected best checkpoint"
        )
    torch.cuda.synchronize()
    gpu_memory_evaluation = _cuda_memory_receipt(torch)
    trainer.save_state()
    adapter_dir = output / "adapter"
    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    adapter_selection = _selected_adapter_receipt(
        trainer=trainer,
        output=output,
        adapter_dir=adapter_dir,
        milestones=milestones,
    )
    _write_metrics(output, trainer.state.log_history)

    training_manifest = {
        "schema_version": 2,
        "run_name": args.run_name,
        "lineage": args.lineage,
        "base_lineage": lineage,
        "initial_adapter_receipt": initial_adapter,
        "initial_adapter_load": initial_adapter_load,
        "tokenizer": tokenizer_receipt,
        "campaign_config": campaign_config,
        "seed": args.seed,
        "max_length": args.max_length,
        "epochs": args.epochs,
        "learning_rate": args.learning_rate,
        "warmup_ratio": args.warmup_ratio,
        "weight_decay": args.weight_decay,
        "rank": args.rank,
        "lora_alpha": args.lora_alpha,
        "training_method": "lora_bf16",
        "completion_only_loss": True,
        "target_modules": list(LORA_TARGET_MODULES),
        "dataset": dataset.receipt(),
        "private_policy": args.private_policy,
        "source_counts_before_policy": dict(sorted(source_counts_before.items())),
        "source_counts_after_policy": dict(sorted(source_counts.items())),
        "training_source_counts": dict(sorted(training_source_counts.items())),
        "pilot_rows": args.pilot_rows,
        "validation_rows": args.validation_rows,
        "train_ordered_id_sha256": _id_digest(train["id"]),
        "validation_ordered_id_sha256": _id_digest(validation_rows["id"]),
        "validation": {
            **validation.receipt(),
        },
        "tokenization": length_receipt,
        "batch_size": args.batch_size,
        "eval_batch_size": args.eval_batch_size,
        "gradient_accumulation": args.gradient_accumulation,
        "eval_steps": args.eval_steps,
        "save_steps": args.save_steps,
        "logging_steps": args.logging_steps,
        "global_batch_per_gpu": args.batch_size * args.gradient_accumulation,
        "max_steps": args.max_steps,
        "planned_steps": planned_steps,
        "warmup_steps": warmup_steps,
        "schedule": {
            "kind": "milestones" if milestones else "periodic",
            "requested_steps": list(milestones),
            "observed_eval_steps": observed_eval_steps,
            "session_save_callback_steps": saved_milestone_steps,
            "surviving_checkpoint_steps": observed_checkpoints,
            "trainer_interval": trainer_interval,
        },
        "train_metrics": result.metrics,
        "validation_metrics": evaluation,
        "adapter_selection": adapter_selection,
        "resume": {
            "requested": args.resume_from_checkpoint is not None,
            "retry_from_scratch": retry_from_scratch,
            "checkpoint_step": resume_step,
            "treatment_signature_sha256": resume_signature["sha256"],
            "initial_resolved_config_sha256": sha256_file(initial_resolved_path),
        },
        "trainer_global_step": trainer.state.global_step,
        "trainer_epoch": trainer.state.epoch,
        "elapsed_seconds": round(time.time() - started, 3),
        "gpu_memory": {
            "before_training": gpu_memory_before_training,
            "training": gpu_memory_training,
            "final_evaluation": gpu_memory_evaluation,
        },
        "environment": {
            "hostname": platform.node(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(0),
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "unsloth_compile_location": os.environ.get("UNSLOTH_COMPILE_LOCATION"),
            "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
            "slurm_array_job_id": os.environ.get("SLURM_ARRAY_JOB_ID"),
            "slurm_array_task_id": os.environ.get("SLURM_ARRAY_TASK_ID"),
            "packages": _package_versions(),
        },
        "git": _git_receipt(repo),
        "scripts": {
            "train_lora_round2.py": sha256_file(Path(__file__)),
            "campaign_io.py": sha256_file(script_dir / "campaign_io.py"),
            "train_lora.py": sha256_file(script_dir / "train_lora.py"),
        },
        "adapter": inventory_tree(adapter_dir),
        "metrics": {
            name: {
                "bytes": (output / name).stat().st_size,
                "sha256": sha256_file(output / name),
            }
            for name in (
                "metrics.jsonl",
                "metrics.csv",
                "loss-curve.png",
                "loss-curve.svg",
            )
        },
    }
    _json_write(output / "training-manifest.json", training_manifest)
    completed = {
        "run_name": args.run_name,
        "completed_unix": time.time(),
        "training_manifest_sha256": sha256_file(output / "training-manifest.json"),
    }
    _json_write(output / "COMPLETED.json", completed)
    (output / "RUNNING.json").unlink(missing_ok=True)
    (output / "FAILED.json").unlink(missing_ok=True)
    return training_manifest


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    with _exclusive_run_lock(args.output):
        try:
            manifest = run(args)
        except BaseException as exc:
            args.output.mkdir(parents=True, exist_ok=True)
            if not (args.output / "COMPLETED.json").is_file():
                _json_write(
                    args.output / "FAILED.json",
                    {
                        "run_name": args.run_name,
                        "failed_unix": time.time(),
                        "exception": type(exc).__name__,
                        "message": str(exc),
                        "traceback": traceback.format_exc(),
                    },
                )
            raise
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
