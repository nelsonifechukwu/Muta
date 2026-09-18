#!/usr/bin/env python3
"""Compile validated round-two pilot receipts into terse result tables."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from campaign_io import inventory_tree, sha256_file

CANDIDATE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
PRIVATE_SOURCES = frozenset({"waec_elearning", "cheetahwaec"})
TABLE_FIELDS = (
    "candidate_id",
    "host",
    "lineage",
    "rank",
    "learning_rate",
    "best_dev_loss",
    "train_loss",
    "runtime_seconds",
    "steps",
    "peak_vram_gib",
    "torch_version",
    "cuda_version",
    "gpu_name",
    "git_commit",
    "adapter_sha256",
    "status",
    "detail",
)


class PilotResultError(ValueError):
    """Raised when pilot inputs cannot form an unambiguous result set."""


def _batch_settings(config: dict[str, Any]) -> dict[str, int]:
    shared = config["shared"]
    try:
        batch_size = int(shared["batch_size"])
        gradient_accumulation = int(shared["gradient_accumulation"])
        global_batch = int(shared["global_batch_per_gpu"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PilotResultError("pilot config has invalid batch settings") from exc
    if (
        batch_size < 1
        or gradient_accumulation < 1
        or batch_size * gradient_accumulation != global_batch
    ):
        raise PilotResultError("pilot config batch settings are inconsistent")
    return {
        "batch_size": batch_size,
        "eval_batch_size": batch_size,
        "gradient_accumulation": gradient_accumulation,
        "global_batch_per_gpu": global_batch,
    }


def _verify_protocol_deviation(
    path: Path | None, *, config_path: Path, config: dict[str, Any]
) -> dict[str, Any] | None:
    if path is None:
        return None
    path = path.resolve()
    receipt = _read_json(path)
    if (
        receipt.get("schema_version") != 1
        or receipt.get("campaign_id") != config.get("campaign_id")
        or receipt.get("approved_before_candidate_results") is not True
    ):
        raise PilotResultError("invalid or post-result protocol deviation receipt")
    frozen = receipt.get("frozen_pilot_config", {})
    if frozen.get("sha256") != sha256_file(config_path):
        raise PilotResultError("protocol deviation does not bind the pilot config")
    configured = receipt.get("configured")
    actual = receipt.get("allowed_actual")
    if configured != _batch_settings(config):
        raise PilotResultError("protocol deviation configured batch does not match config")
    # This is deliberately narrow: one measured A100 implementation change, not
    # a general permission to alter the frozen optimization treatment.
    if actual != {
        "batch_size": 64,
        "eval_batch_size": 64,
        "gradient_accumulation": 1,
        "global_batch_per_gpu": 64,
    }:
        raise PilotResultError("protocol deviation permits an unapproved batch treatment")
    evidence = receipt.get("evidence")
    if not isinstance(evidence, dict) or not evidence:
        raise PilotResultError("protocol deviation has no calibration evidence")
    required_evidence = {
        "COMPLETED.json",
        "gpu-samples.csv",
        "loss-curve.png",
        "loss-curve.svg",
        "metrics.csv",
        "metrics.jsonl",
        "resolved-config.json",
        "training-manifest.json",
    }
    if not required_evidence.issubset(evidence):
        raise PilotResultError("protocol deviation omits required calibration evidence")
    for name, file_receipt in evidence.items():
        if not isinstance(name, str) or not isinstance(file_receipt, dict):
            raise PilotResultError("invalid calibration evidence receipt")
        _verify_file_receipt(path.parent, name, file_receipt)
    calibration_manifest = _read_json(path.parent / "training-manifest.json")
    for field in ("batch_size", "gradient_accumulation", "global_batch_per_gpu"):
        expected = actual[field]
        if calibration_manifest.get(field) != expected:
            raise PilotResultError(f"calibration manifest changes {field}")
    if calibration_manifest.get("trainer_global_step") != receipt.get("calibration", {}).get(
        "steps"
    ):
        raise PilotResultError("calibration step receipt mismatch")
    completed = _read_json(path.parent / "COMPLETED.json")
    if completed.get("training_manifest_sha256") != sha256_file(
        path.parent / "training-manifest.json"
    ):
        raise PilotResultError("calibration terminal receipt is not bound to its manifest")
    maxima = [0.0, 0.0, 0.0]
    sample_count = 0
    try:
        with (path.parent / "gpu-samples.csv").open(newline="", encoding="utf-8") as handle:
            for row in csv.reader(handle):
                if not row:
                    continue
                if len(row) != 4:
                    raise PilotResultError("calibration GPU sample has the wrong columns")
                values = [_finite_number(value.strip(), label="GPU sample") for value in row[1:]]
                maxima = [max(old, new) for old, new in zip(maxima, values, strict=True)]
                sample_count += 1
    except OSError as exc:
        raise PilotResultError("cannot read calibration GPU samples") from exc
    calibration = receipt.get("calibration", {})
    expected_maxima = [
        calibration.get("max_observed_memory_used_mib"),
        calibration.get("max_observed_gpu_utilization_percent"),
        calibration.get("max_observed_power_draw_w"),
    ]
    if sample_count < 1 or maxima != expected_maxima:
        raise PilotResultError("calibration GPU maxima do not match raw samples")
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "configured": configured,
        "actual": actual,
        "calibration_evidence": {
            name: dict(file_receipt) for name, file_receipt in sorted(evidence.items())
        },
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PilotResultError(f"cannot read JSON: {path}") from exc
    if not isinstance(value, dict):
        raise PilotResultError(f"JSON root is not an object: {path}")
    return value


def _finite_number(value: Any, *, label: str) -> float:
    if isinstance(value, bool):
        raise PilotResultError(f"{label} is not numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise PilotResultError(f"{label} is not numeric") from exc
    if not math.isfinite(number):
        raise PilotResultError(f"{label} is not finite")
    return number


def validate_pilot_config(config: dict[str, Any]) -> list[dict[str, Any]]:
    if config.get("schema_version") != 1:
        raise PilotResultError("pilot config schema_version must be 1")
    if config.get("frozen_before_results") is not True:
        raise PilotResultError("pilot config was not frozen before results")
    dataset = config.get("dataset")
    validation = config.get("validation")
    shared = config.get("shared")
    if (
        not isinstance(dataset, dict)
        or not isinstance(validation, dict)
        or not isinstance(shared, dict)
    ):
        raise PilotResultError("pilot config is missing dataset, validation, or shared settings")
    for section, field in ((dataset, "rows"), (dataset, "pilot_rows"), (validation, "rows")):
        if not isinstance(section.get(field), int) or section[field] < 1:
            raise PilotResultError(f"pilot config has invalid {field}")
    if dataset["pilot_rows"] > dataset["rows"]:
        raise PilotResultError("pilot rows exceed full dataset rows")
    for label, section in (("dataset", dataset), ("validation", validation)):
        digest = section.get("fingerprint_sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise PilotResultError(f"pilot config has invalid {label} fingerprint")
    if dataset.get("private_policy") not in {"include", "exclude"}:
        raise PilotResultError("pilot config has invalid private policy")
    for field in (
        "max_length",
        "seed",
        "batch_size",
        "gradient_accumulation",
        "global_batch_per_gpu",
        "eval_steps",
        "save_steps",
        "logging_steps",
    ):
        if not isinstance(shared.get(field), int) or shared[field] < 1:
            raise PilotResultError(f"pilot config has invalid shared field: {field}")
    _batch_settings(config)
    for field in ("epochs", "warmup_ratio", "weight_decay"):
        value = _finite_number(shared.get(field), label=f"shared {field}")
        if field != "weight_decay" and value <= 0:
            raise PilotResultError(f"pilot config has invalid shared field: {field}")
        if field == "weight_decay" and value < 0:
            raise PilotResultError(f"pilot config has invalid shared field: {field}")
    if shared.get("completion_only_loss") is not True:
        raise PilotResultError("pilot config must use completion-only loss")
    if shared.get("training_method") != "BF16 LoRA":
        raise PilotResultError("pilot config training method must be BF16 LoRA")
    candidates = config.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise PilotResultError("pilot config has no candidates")
    identifiers: list[str] = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise PilotResultError(f"candidate {index} is not an object")
        identifier = candidate.get("id")
        if not isinstance(identifier, str) or not CANDIDATE_ID.fullmatch(identifier):
            raise PilotResultError(f"unsafe candidate ID: {identifier!r}")
        identifiers.append(identifier)
        if candidate.get("lineage") not in {"clean", "warm"}:
            raise PilotResultError(f"invalid lineage for {identifier}")
        if not isinstance(candidate.get("rank"), int) or candidate["rank"] < 1:
            raise PilotResultError(f"invalid rank for {identifier}")
        if _finite_number(candidate.get("learning_rate"), label=f"{identifier} learning rate") <= 0:
            raise PilotResultError(f"invalid learning rate for {identifier}")
    if len(set(identifiers)) != len(identifiers):
        raise PilotResultError("pilot config contains duplicate candidate IDs")
    return candidates


def _verify_file_receipt(run_dir: Path, name: str, receipt: dict[str, Any]) -> None:
    path = (run_dir / name).resolve()
    root = run_dir.resolve()
    if path.parent != root or not path.is_file():
        raise PilotResultError(f"missing or unsafe artifact: {name}")
    if path.stat().st_size != receipt.get("bytes"):
        raise PilotResultError(f"artifact byte mismatch: {name}")
    if sha256_file(path) != receipt.get("sha256"):
        raise PilotResultError(f"artifact SHA-256 mismatch: {name}")


def _load_metric_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise PilotResultError(f"metrics row {line_number} is not an object")
                rows.append(value)
    except (OSError, json.JSONDecodeError) as exc:
        raise PilotResultError(f"cannot read metrics: {path}") from exc
    return rows


def _expected(
    config: dict[str, Any],
    candidate: dict[str, Any],
    protocol_deviation: dict[str, Any] | None,
) -> dict[str, Any]:
    batch = protocol_deviation["actual"] if protocol_deviation else _batch_settings(config)
    return {
        "run_name": candidate["id"],
        "lineage": candidate["lineage"],
        "rank": candidate["rank"],
        "learning_rate": float(candidate["learning_rate"]),
        "pilot_rows": int(config["dataset"]["pilot_rows"]),
        "private_policy": config["dataset"]["private_policy"],
        "max_length": int(config["shared"]["max_length"]),
        "seed": int(config["shared"]["seed"]),
        **batch,
    }


def _validate_completed_run(
    run_dir: Path,
    *,
    config: dict[str, Any],
    candidate: dict[str, Any],
    protocol_deviation: dict[str, Any] | None,
) -> dict[str, Any]:
    completed_path = run_dir / "COMPLETED.json"
    training_path = run_dir / "training-manifest.json"
    completed = _read_json(completed_path)
    training = _read_json(training_path)
    if training.get("schema_version") != 2:
        raise PilotResultError("training manifest schema_version must be 2")
    if completed.get("run_name") not in (None, candidate["id"]):
        raise PilotResultError("COMPLETED receipt has the wrong run name")
    observed_manifest_sha = sha256_file(training_path)
    if completed.get("training_manifest_sha256") != observed_manifest_sha:
        raise PilotResultError("COMPLETED receipt does not bind the training manifest")

    for field, expected in _expected(config, candidate, protocol_deviation).items():
        observed = training.get(field)
        if field == "learning_rate":
            observed = _finite_number(observed, label=field)
        if observed != expected:
            raise PilotResultError(f"{field} mismatch: {observed!r} != {expected!r}")
    if (
        training.get("training_method") != "lora_bf16"
        or training.get("completion_only_loss") is not True
        or training.get("lora_alpha") != candidate["rank"]
        or training.get("max_steps") != -1
    ):
        raise PilotResultError("training method differs from the frozen BF16 LoRA treatment")
    expected_modules = {
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
        "gate_proj",
        "up_proj",
        "down_proj",
    }
    if set(training.get("target_modules", [])) != expected_modules:
        raise PilotResultError("LoRA target modules differ from the frozen treatment")

    base_lineage = training.get("base_lineage")
    lineage_receipt = base_lineage.get("receipt") if isinstance(base_lineage, dict) else None
    observed_base = base_lineage.get("observed") if isinstance(base_lineage, dict) else None
    if not isinstance(lineage_receipt, dict) or not isinstance(observed_base, dict):
        raise PilotResultError("training manifest has no base-lineage identity")
    training_base_tree_sha = observed_base.get("tree_sha256")
    if (
        lineage_receipt.get("lineage") != candidate["lineage"]
        or not re.fullmatch(r"[0-9a-f]{64}", str(training_base_tree_sha or ""))
        or lineage_receipt.get("training_base", {}).get("tree_sha256") != training_base_tree_sha
        or not re.fullmatch(r"[0-9a-f]{64}", str(base_lineage.get("receipt_sha256", "")))
    ):
        raise PilotResultError("training base does not match its lineage receipt")
    incumbent_gguf_sha = None
    if candidate["lineage"] == "warm":
        incumbent_gguf_sha = (
            lineage_receipt.get("prior_stage", {}).get("published_gguf", {}).get("sha256")
        )
        if not re.fullmatch(r"[0-9a-f]{64}", str(incumbent_gguf_sha or "")):
            raise PilotResultError("warm lineage does not bind the incumbent GGUF control")

    resolved_path = run_dir / "resolved-config.json"
    resolved = _read_json(resolved_path)
    shared = config["shared"]
    resolved_expected = {
        "run_name": candidate["id"],
        "lineage": candidate["lineage"],
        "rank": candidate["rank"],
        "lora_alpha": candidate["rank"],
        "learning_rate": float(candidate["learning_rate"]),
        "max_length": shared["max_length"],
        "epochs": float(shared["epochs"]),
        "warmup_ratio": float(shared["warmup_ratio"]),
        "weight_decay": float(shared["weight_decay"]),
        "eval_steps": shared["eval_steps"],
        "save_steps": shared["save_steps"],
        "logging_steps": shared["logging_steps"],
        "pilot_rows": config["dataset"]["pilot_rows"],
        "private_policy": config["dataset"]["private_policy"],
        "seed": shared["seed"],
        **{
            field: value
            for field, value in (
                protocol_deviation["actual"] if protocol_deviation else _batch_settings(config)
            ).items()
            if field != "global_batch_per_gpu"
        },
    }
    for field, expected in resolved_expected.items():
        observed = resolved.get(field)
        if field in {"learning_rate", "epochs", "warmup_ratio", "weight_decay"}:
            observed = _finite_number(observed, label=f"resolved {field}")
        if observed != expected:
            raise PilotResultError(
                f"resolved config {field} mismatch: {observed!r} != {expected!r}"
            )

    dataset = training.get("dataset", {})
    if dataset.get("dataset_fingerprint_sha256") != config["dataset"]["fingerprint_sha256"]:
        raise PilotResultError("training dataset fingerprint mismatch")
    if dataset.get("row_count") != config["dataset"]["rows"]:
        raise PilotResultError("training dataset artifact row count mismatch")
    validation = training.get("validation", {})
    if validation.get("dataset_fingerprint_sha256") != config["validation"]["fingerprint_sha256"]:
        raise PilotResultError("validation dataset fingerprint mismatch")
    if validation.get("row_count") != config["validation"]["rows"]:
        raise PilotResultError("validation artifact row count mismatch")
    for section, expected_fingerprint in (
        (resolved.get("dataset", {}), config["dataset"]["fingerprint_sha256"]),
        (resolved.get("validation", {}), config["validation"]["fingerprint_sha256"]),
    ):
        if section.get("dataset_fingerprint_sha256") != expected_fingerprint:
            raise PilotResultError("resolved config dataset fingerprint mismatch")

    tokenization = training.get("tokenization", {})
    if tokenization.get("train", {}).get("rows") != config["dataset"]["pilot_rows"]:
        raise PilotResultError("pilot row count mismatch")
    if tokenization.get("validation", {}).get("rows") != config["validation"]["rows"]:
        raise PilotResultError("validation row count mismatch")
    train_order_sha = training.get("train_ordered_id_sha256")
    validation_order_sha = training.get("validation_ordered_id_sha256")
    if not re.fullmatch(r"[0-9a-f]{64}", str(train_order_sha or "")) or not re.fullmatch(
        r"[0-9a-f]{64}", str(validation_order_sha or "")
    ):
        raise PilotResultError("training manifest has no exact train/validation row-order digest")

    metrics_receipts = training.get("metrics")
    required_metrics = {
        "metrics.jsonl",
        "metrics.csv",
        "loss-curve.png",
        "loss-curve.svg",
    }
    if not isinstance(metrics_receipts, dict) or not required_metrics.issubset(metrics_receipts):
        raise PilotResultError("training manifest has no metrics receipts")
    for name, receipt in metrics_receipts.items():
        if not isinstance(name, str) or not isinstance(receipt, dict):
            raise PilotResultError("invalid metrics receipt")
        _verify_file_receipt(run_dir, name, receipt)
    metric_rows = _load_metric_rows(run_dir / "metrics.jsonl")
    train_summary_indices = [
        index
        for index, row in enumerate(metric_rows)
        if "train_runtime" in row and "train_loss" in row
    ]
    if len(train_summary_indices) != 1:
        raise PilotResultError("metrics do not contain exactly one terminal training summary")
    # Trainer.evaluate() is called once after train() so the saved best adapter can
    # be measured.  It logs at the current global step and must never be allowed to
    # impersonate a missed scheduled evaluation at that same step.
    scheduled_rows = metric_rows[: train_summary_indices[0]]
    post_training_rows = metric_rows[train_summary_indices[0] + 1 :]
    post_training_evals = [row for row in post_training_rows if "eval_loss" in row]
    if len(post_training_evals) != 1:
        raise PilotResultError(
            "metrics must contain exactly one explicit post-training best-model evaluation"
        )
    post_training_loss = _finite_number(
        post_training_evals[0]["eval_loss"], label="post-training eval_loss"
    )
    validation_metrics = training.get("validation_metrics")
    if not isinstance(validation_metrics, dict) or not math.isclose(
        _finite_number(validation_metrics.get("eval_loss"), label="validation_metrics eval_loss"),
        post_training_loss,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise PilotResultError("post-training evaluation does not match validation_metrics")
    dev_losses = [
        _finite_number(row["eval_loss"], label="eval_loss")
        for row in scheduled_rows
        if "eval_loss" in row
    ]
    if not dev_losses:
        raise PilotResultError("metrics contain no validation loss")
    if any(loss < 0 for loss in dev_losses):
        raise PilotResultError("metrics contain a negative validation loss")

    train_metrics = training.get("train_metrics")
    if not isinstance(train_metrics, dict):
        raise PilotResultError("training manifest has no train_metrics")
    train_loss = _finite_number(train_metrics.get("train_loss"), label="train_loss")
    runtime = _finite_number(train_metrics.get("train_runtime"), label="train_runtime")
    if train_loss < 0 or runtime <= 0:
        raise PilotResultError("training loss/runtime is outside its valid range")
    steps = training.get("trainer_global_step")
    planned_steps = training.get("planned_steps")
    if not isinstance(steps, int) or steps < 1 or steps != planned_steps:
        raise PilotResultError("completed step count does not match planned steps")
    effective_global_batch = (
        protocol_deviation["actual"]["global_batch_per_gpu"]
        if protocol_deviation
        else _batch_settings(config)["global_batch_per_gpu"]
    )
    expected_steps = math.ceil(
        math.ceil(config["dataset"]["pilot_rows"] / effective_global_batch)
        * float(config["shared"]["epochs"])
    )
    if steps != expected_steps:
        raise PilotResultError(
            f"completed step count {steps} != frozen expected steps {expected_steps}"
        )
    if training.get("warmup_steps") != math.ceil(steps * float(config["shared"]["warmup_ratio"])):
        raise PilotResultError("warmup step count differs from the frozen schedule")
    training_counts = training.get("training_source_counts")
    if (
        not isinstance(training_counts, dict)
        or sum(training_counts.values()) != config["dataset"]["pilot_rows"]
    ):
        raise PilotResultError("training source counts do not cover the selected pilot rows")
    counts_before = training.get("source_counts_before_policy")
    counts_after = training.get("source_counts_after_policy")
    if not isinstance(counts_before, dict) or not isinstance(counts_after, dict):
        raise PilotResultError("training manifest has no private-policy source counts")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for counts in (counts_before, counts_after, training_counts)
        for value in counts.values()
    ):
        raise PilotResultError("training source counts are invalid")
    if sum(counts_before.values()) != config["dataset"]["rows"]:
        raise PilotResultError("pre-policy source counts do not cover the dataset")
    if config["dataset"]["private_policy"] == "include":
        if counts_after != counts_before or not (PRIVATE_SOURCES & counts_before.keys()):
            raise PilotResultError("include policy changed the available source counts")
    elif not (PRIVATE_SOURCES & counts_before.keys()) or PRIVATE_SOURCES & counts_after.keys():
        raise PilotResultError("exclude policy did not remove private sources")
    if not set(training_counts).issubset(counts_after):
        raise PilotResultError("selected training rows contain an unavailable source")
    eval_interval = int(config["shared"]["eval_steps"])
    expected_eval_steps = list(range(eval_interval, steps + 1, eval_interval))
    if not expected_eval_steps or expected_eval_steps[-1] != steps:
        expected_eval_steps.append(steps)
    observed_eval_steps = [
        int(row["step"])
        for row in scheduled_rows
        if "eval_loss" in row and row.get("step") is not None
    ]
    if observed_eval_steps != expected_eval_steps:
        raise PilotResultError(
            f"validation steps {observed_eval_steps} != frozen schedule {expected_eval_steps}"
        )

    memory = training.get("gpu_memory", {}).get("training", {})
    peak_vram = memory.get("peak_reserved_bytes")
    if not isinstance(peak_vram, int) or peak_vram < 1:
        raise PilotResultError("training manifest has no peak VRAM receipt")

    adapter_receipt = training.get("adapter")
    if not isinstance(adapter_receipt, dict):
        raise PilotResultError("training manifest has no adapter receipt")
    observed_adapter = inventory_tree(run_dir / "adapter")
    for field in ("tree_sha256", "file_count", "bytes"):
        if observed_adapter[field] != adapter_receipt.get(field):
            raise PilotResultError(f"adapter {field} mismatch")
    trainer_state_path = run_dir / "checkpoints" / "trainer_state.json"
    trainer_state = _read_json(trainer_state_path)
    best_path_raw = trainer_state.get("best_model_checkpoint")
    best_metric = _finite_number(trainer_state.get("best_metric"), label="best_metric")
    if best_metric < 0:
        raise PilotResultError("best_metric is negative")
    if not isinstance(best_path_raw, str):
        raise PilotResultError("trainer state has no best checkpoint")
    checkpoint_root = (run_dir / "checkpoints").resolve()
    # Trainer records an absolute host path.  Run trees are intentionally copied
    # between Oracle, CSD3, and the local provenance compiler, so relocate only
    # the validated checkpoint basename into this candidate's exact run root.
    best_name = Path(best_path_raw).name
    best_suffix = best_name.removeprefix("checkpoint-")
    best_path = checkpoint_root / best_name
    if not best_suffix.isdigit() or not (best_path / "trainer_state.json").is_file():
        raise PilotResultError("best checkpoint is missing or incomplete")
    best_step = int(best_suffix)
    if (
        best_step not in observed_eval_steps
        or not math.isclose(best_metric, min(dev_losses), rel_tol=0.0, abs_tol=1e-12)
        or not math.isclose(post_training_loss, best_metric, rel_tol=0.0, abs_tol=1e-12)
    ):
        raise PilotResultError("best checkpoint does not match minimum validation loss")
    final_weights = run_dir / "adapter" / "adapter_model.safetensors"
    best_weights = best_path / "adapter_model.safetensors"
    if not final_weights.is_file() or not best_weights.is_file():
        raise PilotResultError("final or best-checkpoint adapter weights are missing")
    final_weight_sha = sha256_file(final_weights)
    best_weight_sha = sha256_file(best_weights)
    if final_weight_sha != best_weight_sha:
        raise PilotResultError("final adapter is not Trainer's minimum-loss checkpoint")
    final_config = run_dir / "adapter" / "adapter_config.json"
    best_config = best_path / "adapter_config.json"
    if not final_config.is_file() or not best_config.is_file():
        raise PilotResultError("final or best-checkpoint adapter config is missing")
    final_config_sha = sha256_file(final_config)
    if final_config_sha != sha256_file(best_config):
        raise PilotResultError("final adapter config does not match Trainer's best checkpoint")
    best_state = _read_json(best_path / "trainer_state.json")
    if best_state.get("global_step") != best_step or trainer_state.get("global_step") != steps:
        raise PilotResultError("checkpoint trainer state does not match its optimizer step")
    checkpoint_dirs = list(checkpoint_root.glob("checkpoint-*"))
    incomplete_checkpoints = [
        path.name
        for path in checkpoint_dirs
        if not path.is_dir()
        or not path.name.removeprefix("checkpoint-").isdigit()
        or not (path / "trainer_state.json").is_file()
    ]
    if incomplete_checkpoints:
        raise PilotResultError(
            "checkpoint tree contains incomplete evidence: "
            + ", ".join(sorted(incomplete_checkpoints))
        )
    surviving_steps = sorted(int(path.name.removeprefix("checkpoint-")) for path in checkpoint_dirs)
    if (
        steps not in surviving_steps
        or best_step not in surviving_steps
        or len(surviving_steps) > 3
        or not set(surviving_steps).issubset(observed_eval_steps)
    ):
        raise PilotResultError("surviving checkpoints violate the frozen retention schedule")
    hostname = training.get("environment", {}).get("hostname")
    if not isinstance(hostname, str) or not hostname:
        raise PilotResultError("training manifest has no host receipt")
    environment = training.get("environment", {})
    packages = environment.get("packages", {})
    torch_version = environment.get("torch") or packages.get("torch")
    cuda_version = environment.get("cuda")
    if not isinstance(torch_version, str) or not isinstance(cuda_version, str):
        raise PilotResultError("training manifest has no exact Torch/CUDA environment")
    git = training.get("git", {})
    if git.get("available") is not True or git.get("dirty") is not False:
        raise PilotResultError("training Git receipt is unavailable or dirty")
    git_commit = git.get("commit")
    trainer_script_sha = training.get("scripts", {}).get("train_lora_round2.py")
    if not re.fullmatch(r"[0-9a-f]{40,64}", str(git_commit or "")) or not re.fullmatch(
        r"[0-9a-f]{64}", str(trainer_script_sha or "")
    ):
        raise PilotResultError("training manifest has no exact Git/script identity")
    environment_payload = {
        "hostname": hostname,
        "platform": environment.get("platform"),
        "python": environment.get("python"),
        "torch": torch_version,
        "cuda": cuda_version,
        "gpu": environment.get("gpu"),
        "packages": packages,
    }
    environment_sha = hashlib.sha256(
        json.dumps(environment_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    return {
        "host": hostname,
        "best_dev_loss": min(dev_losses),
        "train_loss": train_loss,
        "runtime_seconds": runtime,
        "steps": steps,
        "peak_vram_gib": peak_vram / (1024**3),
        "torch_version": torch_version,
        "cuda_version": cuda_version,
        "gpu_name": environment.get("gpu", ""),
        "git_commit": git_commit,
        "trainer_script_sha256": trainer_script_sha,
        "train_ordered_id_sha256": train_order_sha,
        "validation_ordered_id_sha256": validation_order_sha,
        "training_base_tree_sha256": training_base_tree_sha,
        "base_lineage_receipt_sha256": base_lineage["receipt_sha256"],
        "incumbent_gguf_sha256": incumbent_gguf_sha,
        "training_environment_sha256": environment_sha,
        "training_environment": environment_payload,
        "adapter_sha256": observed_adapter["tree_sha256"],
        "training_manifest_sha256": observed_manifest_sha,
        "completed_sha256": sha256_file(completed_path),
        "resolved_config_sha256": sha256_file(resolved_path),
        "adapter_selection": {
            "policy": "minimum_eval_loss",
            "best_metric": best_metric,
            "best_checkpoint_step": best_step,
            "trainer_state_sha256": sha256_file(trainer_state_path),
            "adapter_model_sha256": final_weight_sha,
            "adapter_config_sha256": final_config_sha,
            "scheduled_eval_steps": observed_eval_steps,
            "surviving_checkpoint_steps": surviving_steps,
        },
    }


def _status_row(
    *,
    config: dict[str, Any],
    candidate: dict[str, Any],
    run_dir: Path | None,
    protocol_deviation: dict[str, Any] | None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "candidate_id": candidate["id"],
        "host": candidate.get("preferred_host", ""),
        "lineage": candidate["lineage"],
        "rank": candidate["rank"],
        "learning_rate": candidate["learning_rate"],
        "best_dev_loss": None,
        "train_loss": None,
        "runtime_seconds": None,
        "steps": None,
        "peak_vram_gib": None,
        "torch_version": "",
        "cuda_version": "",
        "gpu_name": "",
        "git_commit": "",
        "adapter_sha256": "",
        "status": "missing",
        "detail": "",
        "run_dir": str(run_dir.resolve()) if run_dir else "",
        "training_manifest_sha256": "",
        "completed_sha256": "",
    }
    if run_dir is None:
        return row
    markers = {
        name: (run_dir / name).is_file()
        for name in ("COMPLETED.json", "FAILED.json", "RUNNING.json")
    }
    if markers["COMPLETED.json"]:
        if markers["FAILED.json"] or markers["RUNNING.json"]:
            row.update(status="invalid", detail="conflicting terminal markers")
            return row
        try:
            row.update(
                _validate_completed_run(
                    run_dir,
                    config=config,
                    candidate=candidate,
                    protocol_deviation=protocol_deviation,
                )
            )
        except (AttributeError, KeyError, OSError, PilotResultError, TypeError, ValueError) as exc:
            row.update(status="invalid", detail=str(exc))
            return row
        row["status"] = "complete"
        return row
    if markers["FAILED.json"]:
        try:
            failed = _read_json(run_dir / "FAILED.json")
            detail = ": ".join(
                part
                for part in (str(failed.get("exception", "")), str(failed.get("message", "")))
                if part
            )
        except PilotResultError as exc:
            detail = str(exc)
        row.update(status="failed", detail=detail)
        return row
    if markers["RUNNING.json"]:
        row["status"] = "running"
        return row
    row.update(status="incomplete", detail="run directory has no state marker")
    return row


def compile_results(
    *,
    config_path: Path,
    run_roots: list[Path],
    protocol_deviation_path: Path | None = None,
) -> tuple[dict[str, Any], bool]:
    config_path = config_path.resolve()
    config = _read_json(config_path)
    candidates = validate_pilot_config(config)
    protocol_deviation = _verify_protocol_deviation(
        protocol_deviation_path,
        config_path=config_path,
        config=config,
    )
    resolved_roots = [root.resolve() for root in run_roots]
    if not resolved_roots or any(not root.is_dir() for root in resolved_roots):
        raise PilotResultError("every run root must be an existing directory")
    if len(set(resolved_roots)) != len(resolved_roots):
        raise PilotResultError("duplicate run roots are not allowed")

    locations: dict[str, list[Path]] = {candidate["id"]: [] for candidate in candidates}
    for root in resolved_roots:
        for identifier, candidate_locations in locations.items():
            path = root / identifier
            if path.exists():
                if not path.is_dir():
                    raise PilotResultError(f"candidate path is not a directory: {path}")
                candidate_locations.append(path)
    duplicates = {key: value for key, value in locations.items() if len(value) > 1}
    if duplicates:
        detail = "; ".join(
            f"{identifier}: {', '.join(str(path) for path in paths)}"
            for identifier, paths in sorted(duplicates.items())
        )
        raise PilotResultError(f"duplicate candidate run directories: {detail}")

    rows = [
        _status_row(
            config=config,
            candidate=candidate,
            run_dir=locations[candidate["id"]][0] if locations[candidate["id"]] else None,
            protocol_deviation=protocol_deviation,
        )
        for candidate in candidates
    ]
    adapter_owners: dict[str, str] = {}
    for row in rows:
        digest = row["adapter_sha256"]
        if row["status"] != "complete" or not digest:
            continue
        if digest in adapter_owners:
            raise PilotResultError(
                "duplicate completed adapter digest: "
                f"{adapter_owners[digest]} and {row['candidate_id']}"
            )
        adapter_owners[digest] = row["candidate_id"]

    complete_rows = [row for row in rows if row["status"] == "complete"]
    script_hashes = {row["trainer_script_sha256"] for row in complete_rows}
    commits = {row["git_commit"] for row in complete_rows}
    if len(script_hashes) > 1 or len(commits) > 1:
        raise PilotResultError("completed pilots mix trainer scripts or Git commits")
    train_orders = {row["train_ordered_id_sha256"] for row in complete_rows}
    validation_orders = {row["validation_ordered_id_sha256"] for row in complete_rows}
    if len(train_orders) > 1 or len(validation_orders) > 1:
        raise PilotResultError("completed pilots did not use identical ordered dataset rows")
    environment_groups: dict[str, list[str]] = {}
    for row in complete_rows:
        environment_groups.setdefault(row["training_environment_sha256"], []).append(
            row["candidate_id"]
        )
    warnings = []
    if len(environment_groups) > 1:
        warnings.append(
            "Completed pilots use different training environments; host/runtime effects are "
            "confounded with treatments unless a matched bridge run is reported."
        )

    result = {
        "schema_version": 1,
        "campaign_id": config.get("campaign_id"),
        "generated_unix": time.time(),
        "source": {
            "pilot_config": str(config_path),
            "pilot_config_bytes": config_path.stat().st_size,
            "pilot_config_sha256": sha256_file(config_path),
            "run_roots": [str(root) for root in resolved_roots],
            "protocol_deviation": protocol_deviation,
        },
        "counts": {
            status: sum(row["status"] == status for row in rows)
            for status in ("complete", "running", "failed", "incomplete", "missing", "invalid")
        },
        "environment_groups": environment_groups,
        "warnings": warnings,
        "rows": rows,
    }
    result["promotion_ready"] = bool(rows) and all(row["status"] == "complete" for row in rows)
    return result, any(row["status"] == "invalid" for row in rows)


def _display(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.8g}"
    return str(value)


def _git_receipt(repo: Path) -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain=v1"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        return {"available": False}
    return {"available": True, "commit": commit, "dirty": bool(status), "status": status}


def write_results(output: Path, result: dict[str, Any]) -> dict[str, Any]:
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"result output already exists: {output}")
    script = Path(__file__).resolve()
    repo = script.parents[2]
    # Capture cleanliness before creating an untracked result tree inside the
    # repository; otherwise every valid compiler run would receipt itself dirty.
    git_receipt = _git_receipt(repo)
    output.parent.mkdir(parents=True, exist_ok=True)
    work = output.with_name(f".{output.name}.tmp-{os.getpid()}")
    if work.exists():
        raise FileExistsError(f"temporary result output already exists: {work}")
    work.mkdir()
    json_path = work / "pilot-results.json"
    csv_path = work / "pilot-results.csv"
    markdown_path = work / "pilot-results.md"
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TABLE_FIELDS)
        writer.writeheader()
        for row in result["rows"]:
            writer.writerow({field: _display(row.get(field)) for field in TABLE_FIELDS})
    headers = [field.replace("_", " ") for field in TABLE_FIELDS]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in result["rows"]:
        values = [_display(row.get(field)).replace("|", "\\|") for field in TABLE_FIELDS]
        lines.append("| " + " | ".join(values) + " |")
    if result.get("warnings"):
        lines.extend(["", "Warnings:", ""])
        lines.extend(f"- {warning}" for warning in result["warnings"])
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    artifacts = {
        path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in (json_path, csv_path, markdown_path)
    }
    receipt = {
        "schema_version": 1,
        "host": platform.node(),
        "pid": os.getpid(),
        "compiler": {
            "path": str(script),
            "bytes": script.stat().st_size,
            "sha256": sha256_file(script),
        },
        "git": git_receipt,
        "artifacts": artifacts,
    }
    (work / "compiler-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(work, output)
    return receipt


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, action="append", required=True)
    parser.add_argument("--protocol-deviation", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    result, invalid = compile_results(
        config_path=args.config,
        run_roots=args.run_root,
        protocol_deviation_path=args.protocol_deviation,
    )
    write_results(args.output, result)
    if invalid or not result["promotion_ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
