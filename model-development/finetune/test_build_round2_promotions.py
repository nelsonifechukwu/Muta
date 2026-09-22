from __future__ import annotations

import copy
import csv
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


promotions = _load("build_round2_promotions")
launcher = _load("launch_round2_full")


@pytest.fixture(autouse=True)
def historical_v2_source_snapshot(monkeypatch):
    """These legacy tests replay v2 under its pinned historical source hashes.

    The production verifier deliberately rejects the newer continuation trainer;
    current-source v3 is exercised separately in test_round2_promotion_v3.py.
    """
    actual = promotions.sha256_file
    historical = {
        "train_lora_round2.py": promotions.CANONICAL_TRAINING_SOURCE_SHA256["trainer_sha256"],
        "launch_round2_full.py": promotions.CANONICAL_TRAINING_SOURCE_SHA256[
            "full_launcher_sha256"
        ],
    }

    def snapshot_sha(path):
        if path.resolve().parent == HERE and path.name in historical:
            return historical[path.name]
        return actual(path)

    monkeypatch.setattr(promotions, "sha256_file", snapshot_sha)


def _write(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _pilot_config():
    return {
        "schema_version": 1,
        "campaign_id": "test-campaign",
        "frozen_before_results": True,
        "dataset": {
            "rows": 300_350,
            "fingerprint_sha256": "a" * 64,
            "pilot_rows": 20_000,
            "private_policy": "include",
        },
        "validation": {"rows": 5_000, "fingerprint_sha256": "b" * 64},
        "shared": {
            "training_method": "BF16 LoRA",
            "max_length": 512,
            "epochs": 1.0,
            "batch_size": 64,
            "gradient_accumulation": 1,
            "global_batch_per_gpu": 64,
            "warmup_ratio": 0.03,
            "weight_decay": 0.0,
            "seed": 3407,
            "eval_steps": 100,
            "save_steps": 100,
            "logging_steps": 5,
            "completion_only_loss": True,
        },
        "candidates": [
            {
                "id": "clean-r16",
                "lineage": "clean",
                "rank": 16,
                "learning_rate": 1e-5,
            },
            {
                "id": "warm-r32",
                "lineage": "warm",
                "rank": 32,
                "learning_rate": 5e-6,
            },
        ],
    }


def _result_row(identifier: str, lineage: str, rank: int, learning_rate: float):
    return {
        "candidate_id": identifier,
        "lineage": lineage,
        "rank": rank,
        "learning_rate": learning_rate,
        "best_dev_loss": 1.2,
        "train_loss": 1.3,
        "adapter_sha256": ("c" if lineage == "clean" else "d") * 64,
        "training_manifest_sha256": ("e" if lineage == "clean" else "f") * 64,
        "training_base_tree_sha256": ("1" if lineage == "clean" else "2") * 64,
        "incumbent_gguf_sha256": None if lineage == "clean" else "3" * 64,
        "status": "complete",
    }


def _seal_evaluation(root: Path) -> None:
    (root / "artifact-inventory.json").unlink(missing_ok=True)
    (root / "COMPLETED.json").unlink(missing_ok=True)
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            files.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": promotions.sha256_file(path),
                }
            )
    _write(
        root / "artifact-inventory.json",
        {
            "schema_version": 1,
            "file_count": len(files),
            "bytes": sum(row["bytes"] for row in files),
            "files": files,
        },
    )
    _write(
        root / "COMPLETED.json",
        {
            "status": "completed",
            "artifact_inventory_sha256": promotions.sha256_file(root / "artifact-inventory.json"),
            "summary_csv_sha256": promotions.sha256_file(root / "summary.csv"),
            "summary_markdown_sha256": promotions.sha256_file(root / "summary.md"),
            "aggregate_responses_sha256": promotions.sha256_file(root / "responses.jsonl"),
        },
    )


def _make_evaluation(tmp_path, config, results):
    root = tmp_path / "evaluation"
    root.mkdir()
    prompts = [{"id": f"prompt-{ordinal}", "text": f"Exact prompt {ordinal}"} for ordinal in (1, 2)]
    _write(root / "prompts.json", prompts)
    prompt_set = promotions.hashlib.sha256(
        json.dumps(
            prompts,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    evaluated_candidates = [
        {"id": "upstream-control", "backend": "hf"},
        {"id": "incumbent-control", "backend": "gguf"},
        *[{"id": candidate["id"], "backend": "peft"} for candidate in config["candidates"]],
    ]
    candidate_snapshot = {
        "schema_version": 1,
        "candidates": evaluated_candidates,
    }
    _write(root / "candidate-manifest.json", candidate_snapshot)
    _write(
        root / "run.json",
        {
            "schema_version": 1,
            "prompt_suite": "judges",
            "prompt_count": 2,
            "prompt_set_sha256": prompt_set,
            "runtime": {
                "git": {
                    "available": True,
                    "commit": "7" * 40,
                    "dirty": False,
                },
                "script": {
                    "sha256": promotions.sha256_file(
                        HERE.parents[1] / "bench/round2_candidate_eval.py"
                    )
                },
            },
            "candidate_manifest": {
                "sha256": promotions.sha256_file(root / "candidate-manifest.json")
            },
        },
    )
    aggregate = []
    result_by_id = {row["candidate_id"]: row for row in results["rows"]}
    for candidate in evaluated_candidates:
        candidate_id = candidate["id"]
        result = result_by_id.get(candidate_id)
        candidate_dir = root / "candidates" / candidate_id
        candidate_dir.mkdir(parents=True)
        observed = {}
        identity_sha = promotions.hashlib.sha256(candidate_id.encode()).hexdigest()
        if result is not None:
            observed["adapter"] = {"tree_sha256": result["adapter_sha256"]}
            observed["base_model"] = {"tree_sha256": result["training_base_tree_sha256"]}
        elif candidate["backend"] == "hf":
            observed["model"] = {"tree_sha256": "1" * 64}
        if candidate["backend"] == "gguf":
            observed["model"] = {"sha256": "3" * 64}
            observed["server"] = {"sha256": "8" * 64}
        _write(
            candidate_dir / "identity.json",
            {
                "candidate_id": candidate_id,
                "candidate_identity_sha256": identity_sha,
                "backend": candidate["backend"],
                "observed": observed,
            },
        )
        rows = []
        for ordinal, prompt in enumerate(prompts, 1):
            raw = f"raw::{candidate_id}::{ordinal}".encode()
            raw_path = candidate_dir / "raw" / f"{ordinal:03d}.bin"
            raw_path.parent.mkdir(exist_ok=True)
            raw_path.write_bytes(raw)
            row = {
                "candidate_id": candidate_id,
                "candidate_backend": candidate["backend"],
                "model": candidate_id,
                "model_sha256": identity_sha,
                "ordinal": ordinal,
                "id": prompt["id"],
                "text": prompt["text"],
                "prompt": prompt,
                "prompt_sha256": promotions.hashlib.sha256(prompt["text"].encode()).hexdigest(),
                "prompt_set_sha256": prompt_set,
                "raw_output": {
                    "path": raw_path.relative_to(candidate_dir).as_posix(),
                    "bytes": len(raw),
                    "sha256": promotions.hashlib.sha256(raw).hexdigest(),
                },
            }
            if candidate["backend"] == "gguf":
                row["server_sha256"] = "8" * 64
            rows.append(row)
        responses = candidate_dir / "responses.jsonl"
        responses.write_text("".join(json.dumps(row) + "\n" for row in rows))
        _write(
            candidate_dir / "result.json",
            {
                "candidate_id": candidate_id,
                "backend": candidate["backend"],
                "status": "complete",
                "prompts": 2,
                "expected_prompts": 2,
                "responses_sha256": promotions.sha256_file(responses),
            },
        )
        aggregate.extend(rows)
    (root / "responses.jsonl").write_text("".join(json.dumps(row) + "\n" for row in aggregate))
    (root / "summary.md").write_text("complete\n")
    with (root / "summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("candidate_id", "status"))
        writer.writeheader()
        for candidate in evaluated_candidates:
            writer.writerow({"candidate_id": candidate["id"], "status": "complete"})
    _seal_evaluation(root)
    return root


def _inputs(tmp_path):
    config_path = tmp_path / "pilot.json"
    config = _pilot_config()
    _write(config_path, config)
    results_path = tmp_path / "pilot-results.json"
    results = {
        "schema_version": 1,
        "campaign_id": config["campaign_id"],
        "source": {"pilot_config_sha256": promotions.sha256_file(config_path)},
        "rows": [
            _result_row("clean-r16", "clean", 16, 1e-5),
            _result_row("warm-r32", "warm", 32, 5e-6),
        ],
    }
    _write(results_path, results)
    _write(
        tmp_path / "compiler-receipt.json",
        {
            "schema_version": 1,
            "compiler": {"sha256": promotions.sha256_file(HERE / "compile_round2_pilots.py")},
            "git": {"available": True, "commit": "5" * 40, "dirty": False},
            "artifacts": {
                "pilot-results.json": {
                    "bytes": results_path.stat().st_size,
                    "sha256": promotions.sha256_file(results_path),
                }
            },
        },
    )
    evaluation = _make_evaluation(tmp_path, config, results)
    return config_path, results_path, evaluation


def _build(tmp_path):
    config_path, results_path, evaluation = _inputs(tmp_path)
    return promotions.build_promotion_config(
        pilot_config_path=config_path,
        pilot_results_path=results_path,
        pilot_evaluation_dir=evaluation,
        best_clean_id="clean-r16",
        best_warm_id="warm-r32",
        rights_clean_rows=300_000,
        clean_selection_note="Best clean on preregistered evaluation.",
        warm_selection_note="Best warm on preregistered evaluation.",
    )


def _write_safetensors(path: Path, value: int) -> None:
    header_object = {"__metadata__": {"format": "pt"}}
    offset = 0
    for name, shape in promotions.QWEN25_RANK16_LORA_SHAPES.items():
        size = 2
        for dimension in shape:
            size *= dimension
        header_object[name] = {
            "dtype": "BF16",
            "shape": shape,
            "data_offsets": [offset, offset + size],
        }
        offset += size
    header = json.dumps(header_object, separators=(",", ":")).encode()
    padding = (-len(header)) % 8
    header += b" " * padding
    with path.open("wb") as handle:
        handle.write(len(header).to_bytes(8, "little"))
        handle.write(header)
        handle.seek(offset - 1, os.SEEK_CUR)
        handle.write(bytes([value % 256]))


def _zero_tensor_safetensors_bytes() -> bytes:
    header = json.dumps(
        {
            "base_model.model.layers.0.self_attn.q_proj.lora_A.weight": {
                "dtype": "BF16",
                "shape": [0],
                "data_offsets": [0, 0],
            }
        },
        separators=(",", ":"),
    ).encode()
    return len(header).to_bytes(8, "little") + header


def _adapter_config() -> dict:
    return {
        "peft_type": "LORA",
        "task_type": "CAUSAL_LM",
        "r": 16,
        "lora_alpha": 16,
        "target_modules": [
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
    }


def _copy_test_loss_curve(root: Path, metric_rows: list[dict]) -> None:
    cache_key = hashlib.sha256(
        json.dumps(metric_rows, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]
    cache = Path(tempfile.gettempdir()) / f"muta-promotion-test-loss-curve-v2-{cache_key}"
    png = cache.with_suffix(".png")
    svg = cache.with_suffix(".svg")
    if not png.is_file() or not svg.is_file():
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        train = [(row["step"], row["loss"]) for row in metric_rows if "loss" in row]
        evaluation = [(row["step"], row["eval_loss"]) for row in metric_rows if "eval_loss" in row]
        figure, axis = plt.subplots(figsize=(8, 5))
        axis.plot(*zip(*train, strict=True), label="train", linewidth=1.5)
        axis.plot(*zip(*evaluation, strict=True), label="validation", marker="o")
        axis.set(xlabel="optimizer step", ylabel="loss", title="Muta fine-tuning loss")
        axis.grid(alpha=0.25)
        axis.legend()
        figure.tight_layout()
        figure.savefig(png, dpi=180)
        figure.savefig(svg)
        plt.close(figure)
    shutil.copyfile(png, root / "loss-curve.png")
    shutil.copyfile(svg, root / "loss-curve.svg")


def _make_promotion_smoke(tmp_path: Path, *, steps: int = 24) -> Path:
    root = tmp_path / f"promotion-smoke-{steps}"
    root.mkdir()
    trainer_sha = promotions.sha256_file(HERE / "train_lora_round2.py")
    campaign_io_sha = promotions.sha256_file(HERE / "campaign_io.py")
    train_lora_sha = promotions.sha256_file(HERE / "train_lora.py")
    train_fingerprint = "037edf28cccff62d90c23e2d6caf56b9998dea6928080f98af2a513f9f92910e"
    validation_fingerprint = "c056e1744fe148f847354527aa7c7caf6b1fc24fec509f9834d700345e68cc8b"
    train_manifest_sha = "93b7dbcbad72350e099d8951effcbc9a253693dc364b25ffc165102a6e844f4e"
    validation_manifest_sha = "2bbde7545eef5ddd531705e6e71ebc09321e3c7bfbb371ec89ed471696dda301"
    clean_lineage_sha = "e92c17e795759007127c8a52783f29e7f2a8a0d438c3fc9fc1e5fa4af5dfe9e6"
    clean_base_sha = "ae1baefcdac4c037b545696abffc1bd07824c109572163664333b5a5c0dda892"
    milestones = promotions.milestone_steps(steps)
    best_step = milestones[-2]
    scheduled_eval_loss = {
        milestone: 1.5 + abs(milestone - best_step) / steps for milestone in milestones
    }
    metric_rows = []
    for step in range(1, steps + 1):
        metric_rows.append({"epoch": step / steps, "loss": 2.0 - step / 100, "step": step})
        if step in scheduled_eval_loss:
            metric_rows.append(
                {
                    "epoch": step / steps,
                    "eval_loss": scheduled_eval_loss[step],
                    "step": step,
                }
            )
    metric_rows.append({"epoch": 1.0, "step": steps, "train_loss": 1.4})
    metric_rows.append({"epoch": 1.0, "eval_loss": scheduled_eval_loss[best_step], "step": steps})
    (root / "metrics.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in metric_rows),
        encoding="utf-8",
    )
    metric_fields = sorted({field for row in metric_rows for field in row})
    with (root / "metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=metric_fields)
        writer.writeheader()
        writer.writerows(metric_rows)
    _copy_test_loss_curve(root, metric_rows)
    (root / "stdout.log").write_text(
        ("train optimizer step; evaluate milestone; save checkpoint\n" * 16),
        encoding="utf-8",
    )

    adapter_dir = root / "adapter"
    adapter_dir.mkdir()
    _write_safetensors(adapter_dir / "adapter_model.safetensors", best_step)
    _write(adapter_dir / "adapter_config.json", _adapter_config())
    checkpoint_root = root / "checkpoints"
    checkpoint_root.mkdir()
    for checkpoint_step in milestones:
        checkpoint = checkpoint_root / f"checkpoint-{checkpoint_step}"
        checkpoint.mkdir()
        scheduled_eval_index = next(
            index
            for index, row in enumerate(metric_rows)
            if row.get("step") == checkpoint_step and "eval_loss" in row
        )
        eligible = {
            step: loss for step, loss in scheduled_eval_loss.items() if step <= checkpoint_step
        }
        checkpoint_best_step = min(eligible, key=eligible.get)
        _write(
            checkpoint / "trainer_state.json",
            {
                "global_step": checkpoint_step,
                "max_steps": steps,
                "best_metric": eligible[checkpoint_best_step],
                "best_model_checkpoint": str(
                    checkpoint_root / f"checkpoint-{checkpoint_best_step}"
                ),
                "log_history": metric_rows[: scheduled_eval_index + 1],
            },
        )
        checkpoint_weights = checkpoint / "adapter_model.safetensors"
        if checkpoint_step == best_step:
            os.link(adapter_dir / "adapter_model.safetensors", checkpoint_weights)
        else:
            _write_safetensors(checkpoint_weights, checkpoint_step)
        _write(checkpoint / "adapter_config.json", _adapter_config())
        for name in ("optimizer.pt", "scheduler.pt", "rng_state.pth", "training_args.bin"):
            checkpoint.joinpath(name).write_bytes(b"PK\x03\x04trainer-state-evidence")
    _write(
        checkpoint_root / "trainer_state.json",
        {
            "global_step": steps,
            "max_steps": steps,
            "best_metric": scheduled_eval_loss[best_step],
            "best_model_checkpoint": str(checkpoint_root / f"checkpoint-{best_step}"),
            "log_history": metric_rows,
        },
    )
    tokenizer = {
        "lineage_receipt_sha256": clean_lineage_sha,
        "files": {
            name: {"path": f"/verified-tokenizer/{name}", **receipt}
            for name, receipt in promotions.CANONICAL_TOKENIZER["files"].items()
        },
    }
    resolved = {
        "script_sha256": trainer_sha,
        "campaign_io_sha256": campaign_io_sha,
        "campaign_config": None,
        "tokenizer": tokenizer,
        "dataset": {
            "dataset_fingerprint_sha256": train_fingerprint,
            "manifest_sha256": train_manifest_sha,
        },
        "validation": {
            "dataset_fingerprint_sha256": validation_fingerprint,
            "manifest_sha256": validation_manifest_sha,
        },
        "max_steps": steps,
        "expected_planned_steps": steps,
        "milestone_steps": milestones,
        "pilot_rows": 1_536,
        "expected_train_rows": 1_536,
        "validation_rows": 64,
        "expected_validation_rows": 64,
        "lineage": "clean",
        "lineage_receipt_sha256": clean_lineage_sha,
        "rank": 16,
        "lora_alpha": 16,
        "learning_rate": 1e-5,
        "epochs": 1.0,
        "max_length": 512,
        "seed": 3407,
        "batch_size": 64,
        "eval_batch_size": 64,
        "gradient_accumulation": 1,
        "warmup_ratio": 0.03,
        "weight_decay": 0.0,
        "private_policy": "include",
        "logging_steps": 1,
        "resume_from_checkpoint": None,
        "resume_checkpoint_step": None,
    }
    _write(root / "resolved-config.json", resolved)
    (root / "resolved-config.json.sha256").write_text(
        f"{promotions.sha256_file(root / 'resolved-config.json')}  resolved-config.json\n",
        encoding="ascii",
    )
    manifest = {
        "schema_version": 2,
        "run_name": f"promotion-smoke-{steps}",
        "planned_steps": steps,
        "max_steps": steps,
        "trainer_global_step": steps,
        "scripts": {
            "train_lora_round2.py": trainer_sha,
            "campaign_io.py": campaign_io_sha,
            "train_lora.py": train_lora_sha,
        },
        "git": {"available": True, "commit": "7" * 40, "dirty": False},
        "dataset": {
            "dataset_fingerprint_sha256": train_fingerprint,
            "manifest_sha256": train_manifest_sha,
            "row_count": 300_350,
        },
        "validation": {
            "dataset_fingerprint_sha256": validation_fingerprint,
            "manifest_sha256": validation_manifest_sha,
            "row_count": 5_000,
        },
        "schedule": {
            "kind": "milestones",
            "requested_steps": milestones,
            "observed_eval_steps": milestones,
            "session_save_callback_steps": milestones,
            "surviving_checkpoint_steps": milestones,
        },
        "completion_only_loss": True,
        "training_method": "lora_bf16",
        "lineage": "clean",
        "rank": 16,
        "lora_alpha": 16,
        "learning_rate": 1e-5,
        "epochs": 1.0,
        "batch_size": 64,
        "eval_batch_size": 64,
        "gradient_accumulation": 1,
        "warmup_ratio": 0.03,
        "weight_decay": 0.0,
        "private_policy": "include",
        "target_modules": list(promotions.LORA_TARGET_MODULES),
        "max_length": 512,
        "seed": 3407,
        "pilot_rows": 1_536,
        "validation_rows": 64,
        "logging_steps": 1,
        "global_batch_per_gpu": 64,
        "campaign_config": None,
        "tokenizer": tokenizer,
        "tokenization": {
            "train": {
                "rows": 1_536,
                "assistant_tokens": 12_000,
                "sequence_tokens": 24_000,
                "max_sequence_tokens": 384,
            },
            "validation": {
                "rows": 64,
                "assistant_tokens": 512,
                "sequence_tokens": 1_024,
                "max_sequence_tokens": 320,
            },
        },
        "train_ordered_id_sha256": "1" * 64,
        "validation_ordered_id_sha256": "2" * 64,
        "base_lineage": {
            "receipt_sha256": clean_lineage_sha,
            "observed": {"tree_sha256": clean_base_sha},
        },
        "adapter": promotions.inventory_tree(adapter_dir),
        "adapter_selection": {
            "policy": "minimum_eval_loss",
            "best_metric_name": "eval_loss",
            "best_metric": scheduled_eval_loss[best_step],
            "best_checkpoint_step": best_step,
            "best_checkpoint_relative_path": f"checkpoints/checkpoint-{best_step}",
            "best_checkpoint_adapter_model_sha256": promotions.sha256_file(
                checkpoint_root / f"checkpoint-{best_step}" / "adapter_model.safetensors"
            ),
            "final_adapter_model_sha256": promotions.sha256_file(
                adapter_dir / "adapter_model.safetensors"
            ),
            "best_checkpoint_adapter_config_sha256": promotions.sha256_file(
                checkpoint_root / f"checkpoint-{best_step}" / "adapter_config.json"
            ),
            "final_adapter_config_sha256": promotions.sha256_file(
                adapter_dir / "adapter_config.json"
            ),
        },
        "train_metrics": {"train_loss": 1.4},
        "validation_metrics": {"eval_loss": scheduled_eval_loss[best_step]},
        "resume": {
            "requested": False,
            "retry_from_scratch": False,
            "checkpoint_step": None,
            "treatment_signature_sha256": "3" * 64,
            "initial_resolved_config_sha256": promotions.sha256_file(root / "resolved-config.json"),
        },
        "elapsed_seconds": 12.5,
        "gpu_memory": {
            phase: {
                "device_name": "NVIDIA A100-SXM4-40GB",
                "current_allocated_bytes": 1,
                "current_reserved_bytes": 2,
                "peak_allocated_bytes": 3,
                "peak_reserved_bytes": 4,
                "device_total_bytes": 40_000_000_000,
            }
            for phase in ("before_training", "training", "final_evaluation")
        },
        "environment": {
            "hostname": "verified-smoke-host",
            "platform": "Linux-x86_64",
            "python": "3.12.3",
            "torch": "2.7.0",
            "cuda": "12.8",
            "gpu": "NVIDIA A100-SXM4-40GB",
            "packages": {
                "torch": "2.7.0",
                "transformers": "5.5.0",
                "peft": "0.20.0",
                "safetensors": "0.8.0",
                "unsloth": "2026.8.19",
                "matplotlib": __import__("matplotlib").__version__,
            },
        },
        "metrics": {
            name: {
                "bytes": (root / name).stat().st_size,
                "sha256": promotions.sha256_file(root / name),
            }
            for name in (
                "metrics.csv",
                "metrics.jsonl",
                "loss-curve.png",
                "loss-curve.svg",
            )
        },
    }
    _write(root / "training-manifest.json", manifest)
    _write(
        root / "COMPLETED.json",
        {
            "run_name": manifest["run_name"],
            "training_manifest_sha256": promotions.sha256_file(root / "training-manifest.json"),
        },
    )
    return root


def _canonical_paths() -> dict[str, Path]:
    return {
        "pilot_config_path": REPO / "provenance/configs/pilot-sweep.json",
        "pilot_results_path": (
            REPO / "provenance/results/pilots-combined-20260918/pilot-results.json"
        ),
        "canonical_comparison_dir": (REPO / "provenance/results/all-gguf-cuda-comparison-20260918"),
        "export_root": REPO / "provenance/exports",
        "hardened_resume_verification": (
            REPO / "provenance/calibration/hardened-smoke-20260918/receipts/verification.json"
        ),
    }


def _reseal_smoke_metrics(root: Path, rows: list[dict]) -> None:
    (root / "metrics.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    fields = sorted({field for row in rows for field in row})
    with (root / "metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    _copy_test_loss_curve(root, rows)
    state_path = root / "checkpoints/trainer_state.json"
    state = json.loads(state_path.read_text())
    state["log_history"] = rows
    _write(state_path, state)
    manifest_path = root / "training-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for name in ("metrics.csv", "metrics.jsonl", "loss-curve.png", "loss-curve.svg"):
        manifest["metrics"][name] = {
            "bytes": (root / name).stat().st_size,
            "sha256": promotions.sha256_file(root / name),
        }
    _write(manifest_path, manifest)
    terminal = json.loads((root / "COMPLETED.json").read_text())
    terminal["training_manifest_sha256"] = promotions.sha256_file(manifest_path)
    _write(root / "COMPLETED.json", terminal)


def _reseal_smoke_manifest(root: Path, manifest: dict) -> None:
    manifest_path = root / "training-manifest.json"
    _write(manifest_path, manifest)
    terminal = json.loads((root / "COMPLETED.json").read_text())
    terminal["training_manifest_sha256"] = promotions.sha256_file(manifest_path)
    _write(root / "COMPLETED.json", terminal)


def _build_canonical(tmp_path: Path) -> dict:
    return promotions.build_canonical_gguf_promotion_config(
        **_canonical_paths(),
        promotion_smoke_dir=_make_promotion_smoke(tmp_path),
        best_clean_id="clean-r16-lr1e5",
        best_warm_id="warm-r16-lr5e6",
        rights_clean_rows=300_000,
        clean_selection_note=(
            "Domain-priority selection: stronger reviewed STEM than clean-r32; "
            "judges score regressed from 47 to 34."
        ),
        warm_selection_note=(
            "Warm written-core and judges leader; reviewed MC regressions remain disclosed."
        ),
    )


def test_milestones_are_exact_quarter_half_and_end():
    assert promotions.milestone_steps(4693) == [1174, 2347, 4693]
    assert promotions.milestone_steps(4688) == [1172, 2344, 4688]


def test_builds_three_frozen_full_runs_without_selecting_automatically(tmp_path):
    config = _build(tmp_path)
    assert config["frozen_before_full_runs"] is True
    assert config["shared"]["global_batch"] == 64
    assert config["shared"]["checkpoint_schedule"] == "quarter_half_end"
    clean, warm, rights_clean = config["candidates"]
    assert clean["source_pilot_id"] == "clean-r16"
    assert clean["planned_rows"] == 300_350
    assert clean["planned_steps"] == 4693
    assert clean["milestone_steps"] == [1174, 2347, 4693]
    assert warm["source_pilot_id"] == "warm-r32"
    assert warm["private_policy"] == "include"
    assert rights_clean["source_pilot_id"] == "warm-r32"
    assert rights_clean["private_policy"] == "exclude"
    assert rights_clean["planned_rows"] == 300_000
    assert rights_clean["milestone_steps"] == [1172, 2344, 4688]


def test_promotion_refuses_incomplete_or_wrong_lineage_selection(tmp_path):
    config_path, results_path, evaluation = _inputs(tmp_path)
    results = json.loads(results_path.read_text())
    results["rows"][0]["status"] = "running"
    _write(results_path, results)
    receipt_path = tmp_path / "compiler-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["artifacts"]["pilot-results.json"] = {
        "bytes": results_path.stat().st_size,
        "sha256": promotions.sha256_file(results_path),
    }
    _write(receipt_path, receipt)
    with pytest.raises(promotions.PilotResultError, match="must complete"):
        promotions.build_promotion_config(
            pilot_config_path=config_path,
            pilot_results_path=results_path,
            pilot_evaluation_dir=evaluation,
            best_clean_id="clean-r16",
            best_warm_id="warm-r32",
            rights_clean_rows=300_000,
            clean_selection_note="reason",
            warm_selection_note="reason",
        )


def test_promotion_requires_global_batch_64(tmp_path):
    config_path, results_path, evaluation = _inputs(tmp_path)
    with pytest.raises(promotions.PilotResultError, match="global batch"):
        promotions.build_promotion_config(
            pilot_config_path=config_path,
            pilot_results_path=results_path,
            pilot_evaluation_dir=evaluation,
            best_clean_id="clean-r16",
            best_warm_id="warm-r32",
            rights_clean_rows=300_000,
            clean_selection_note="reason",
            warm_selection_note="reason",
            batch_size=16,
            gradient_accumulation=2,
        )


def test_frozen_config_refuses_overwrite(tmp_path):
    config = _build(tmp_path)
    output = tmp_path / "full.json"
    receipt = promotions.write_frozen_config(output, config)
    assert receipt["sha256"] == promotions.sha256_file(output)
    assert output.with_suffix(".json.sha256").is_file()
    with pytest.raises(FileExistsError):
        promotions.write_frozen_config(output, config)


def test_full_launcher_refuses_config_changed_after_freeze(tmp_path):
    config = _build(tmp_path)
    output = tmp_path / "full.json"
    promotions.write_frozen_config(output, config)
    loaded, digest = launcher.load_frozen_config(output)
    assert loaded["campaign_id"] == config["campaign_id"]
    assert digest == promotions.sha256_file(output)
    output.write_text(output.read_text() + "\n")
    with pytest.raises(promotions.PilotResultError, match="receipt mismatch"):
        launcher.load_frozen_config(output)


def test_full_launcher_passes_exact_rows_steps_and_milestones(tmp_path):
    config = _build(tmp_path)
    candidate = config["candidates"][2]
    args = type(
        "Args",
        (),
        {
            "python": Path("python"),
            "config": tmp_path / "full.json",
            "clean_base": Path("clean-base"),
            "warm_base": Path("warm-base"),
            "clean_lineage": Path("clean.json"),
            "warm_lineage": Path("warm.json"),
            "dataset_manifest": Path("dataset.json"),
            "validation_manifest": Path("validation.json"),
            "output_root": tmp_path / "runs",
            "eval_batch_size": None,
            "dataloader_workers": 8,
            "resume_from_checkpoint": Path("checkpoint-2344"),
        },
    )()
    command = launcher.build_command(
        args,
        config,
        candidate,
        config_sha256="1" * 64,
    )
    joined = " ".join(map(str, command))
    assert "--model warm-base" in joined
    assert "--private-policy exclude" in joined
    assert "--expected-train-rows 300000" in joined
    assert "--expected-planned-steps 4688" in joined
    assert "--milestone-steps 1172,2344,4688" in joined
    assert "--resume-from-checkpoint checkpoint-2344" in joined
    assert "--pilot-rows" not in joined


def test_frozen_full_config_rejects_private_policy_row_count_drift(tmp_path):
    config = _build(tmp_path)
    config["candidates"][0]["planned_rows"] -= 1
    config["candidates"][0]["planned_steps"] = promotions.math.ceil(
        config["candidates"][0]["planned_rows"] / config["shared"]["global_batch"]
    )
    config["candidates"][0]["milestone_steps"] = promotions.milestone_steps(
        config["candidates"][0]["planned_steps"]
    )
    with pytest.raises(promotions.PilotResultError, match="private-data policies"):
        promotions.validate_promotion_config(config)


def test_promotion_requires_every_pilot_complete(tmp_path):
    config_path, results_path, evaluation = _inputs(tmp_path)
    results = json.loads(results_path.read_text())
    results["rows"][1]["status"] = "failed"
    _write(results_path, results)
    receipt_path = tmp_path / "compiler-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["artifacts"]["pilot-results.json"] = {
        "bytes": results_path.stat().st_size,
        "sha256": promotions.sha256_file(results_path),
    }
    _write(receipt_path, receipt)
    with pytest.raises(promotions.PilotResultError, match="every configured pilot"):
        promotions.build_promotion_config(
            pilot_config_path=config_path,
            pilot_results_path=results_path,
            pilot_evaluation_dir=evaluation,
            best_clean_id="clean-r16",
            best_warm_id="warm-r32",
            rights_clean_rows=300_000,
            clean_selection_note="reason",
            warm_selection_note="reason",
        )


def test_promotion_rejects_pilot_evaluated_on_wrong_base(tmp_path):
    config_path, results_path, evaluation = _inputs(tmp_path)
    identity_path = evaluation / "candidates" / "warm-r32" / "identity.json"
    identity = json.loads(identity_path.read_text())
    identity["observed"]["base_model"]["tree_sha256"] = "4" * 64
    _write(identity_path, identity)
    _seal_evaluation(evaluation)
    with pytest.raises(promotions.PilotResultError, match="wrong training base"):
        promotions.build_promotion_config(
            pilot_config_path=config_path,
            pilot_results_path=results_path,
            pilot_evaluation_dir=evaluation,
            best_clean_id="clean-r16",
            best_warm_id="warm-r32",
            rights_clean_rows=300_000,
            clean_selection_note="reason",
            warm_selection_note="reason",
        )


def test_canonical_gguf_promotion_revalidates_and_launches(tmp_path):
    config = _build_canonical(tmp_path)
    assert config["schema_version"] == 2
    assert config["selection_protocol"] == "canonical_matched_gguf_semantic_addendum_v1"
    assert config["source_pilots"]["best_clean_id"] == "clean-r16-lr1e5"
    assert config["source_pilots"]["best_warm_id"] == "warm-r16-lr5e6"
    assert config["source_pilots"]["export_manifests"]["count"] == 8
    assert config["training_gates"]["hardened_interruption_resume"]["planned_steps"] == 12
    assert config["training_gates"]["promotion_smoke"]["planned_steps"] == 24
    candidate = next(
        row for row in config["candidates"] if row["id"] == "full-best-warm-private-enriched"
    )
    args = type(
        "Args",
        (),
        {
            "python": Path("python"),
            "config": tmp_path / "full-v2.json",
            "clean_base": Path("clean-base"),
            "warm_base": Path("warm-base"),
            "clean_lineage": Path("clean.json"),
            "warm_lineage": Path("warm.json"),
            "dataset_manifest": Path("dataset.json"),
            "validation_manifest": Path("validation.json"),
            "output_root": tmp_path / "runs",
            "eval_batch_size": None,
            "dataloader_workers": 8,
            "resume_from_checkpoint": None,
        },
    )()
    command = launcher.build_command(args, config, candidate, config_sha256="1" * 64)
    assert "--model" in command
    assert "warm-base" in command
    assert "--expected-train-rows" in command
    assert "300350" in command


def test_canonical_promotion_rejects_arbitrary_selections_before_reading_evidence(tmp_path):
    with pytest.raises(promotions.PilotResultError, match="frozen full-data addendum"):
        promotions.build_canonical_gguf_promotion_config(
            pilot_config_path=tmp_path / "missing-pilot.json",
            pilot_results_path=tmp_path / "missing-results.json",
            canonical_comparison_dir=tmp_path / "missing-comparison",
            export_root=tmp_path / "missing-exports",
            hardened_resume_verification=tmp_path / "missing-resume.json",
            promotion_smoke_dir=tmp_path / "missing-smoke",
            best_clean_id="clean-r32-lr1e5",
            best_warm_id="warm-r16-lr5e6",
            rights_clean_rows=300_000,
            clean_selection_note="reason",
            warm_selection_note="reason",
        )


def test_promotion_smoke_is_distinct_and_at_least_twenty_steps(tmp_path):
    pilot_config = json.loads(_canonical_paths()["pilot_config_path"].read_text())
    with pytest.raises(promotions.PilotResultError, match="20-100"):
        promotions.verify_promotion_smoke_run(
            _make_promotion_smoke(tmp_path, steps=12),
            pilot_config=pilot_config,
        )


@pytest.mark.parametrize("mutation", ["reorder", "duplicate", "module_change", "other_field"])
def test_promotion_smoke_adapter_config_only_ignores_target_module_order(tmp_path, mutation):
    pilot_config = json.loads(_canonical_paths()["pilot_config_path"].read_text())
    smoke = _make_promotion_smoke(tmp_path)
    checkpoint = smoke / "checkpoints/checkpoint-6"
    config_path = checkpoint / "adapter_config.json"
    config = json.loads(config_path.read_text())
    config["target_modules"].reverse()
    if mutation == "duplicate":
        config["target_modules"].append(config["target_modules"][0])
    elif mutation == "module_change":
        config["target_modules"][0] = "lm_head"
    elif mutation == "other_field":
        config["lora_dropout"] = 0.25
    _write(config_path, config)
    original_bytes = config_path.read_bytes()
    observed_inventory = promotions.inventory_tree(checkpoint)
    if mutation == "reorder":
        result = promotions.verify_promotion_smoke_run(smoke, pilot_config=pilot_config)
        assert result["checkpoint_inventories"]["6"] == observed_inventory
        assert config_path.read_bytes() == original_bytes
        assert promotions.sha256_file(config_path) != promotions.sha256_file(
            smoke / "adapter/adapter_config.json"
        )
    else:
        with pytest.raises(promotions.PilotResultError, match="adapter config"):
            promotions.verify_promotion_smoke_run(smoke, pilot_config=pilot_config)


def test_promotion_smoke_rejects_consistently_resealed_missing_optimizer_step(tmp_path):
    pilot_config = json.loads(_canonical_paths()["pilot_config_path"].read_text())
    smoke = _make_promotion_smoke(tmp_path)
    rows = promotions._read_jsonl(smoke / "metrics.jsonl")
    rows = [row for row in rows if not (row.get("step") == 20 and "loss" in row)]
    _reseal_smoke_metrics(smoke, rows)
    with pytest.raises(promotions.PilotResultError, match="every optimizer step"):
        promotions.verify_promotion_smoke_run(smoke, pilot_config=pilot_config)


@pytest.mark.parametrize("bad_loss", [None, "not-a-number", float("inf"), float("nan")])
def test_promotion_smoke_rejects_consistently_resealed_nonnumeric_losses(tmp_path, bad_loss):
    pilot_config = json.loads(_canonical_paths()["pilot_config_path"].read_text())
    smoke = _make_promotion_smoke(tmp_path)
    rows = promotions._read_jsonl(smoke / "metrics.jsonl")
    rows[0]["loss"] = bad_loss
    _reseal_smoke_metrics(smoke, rows)
    with pytest.raises(promotions.PilotResultError, match="finite numeric|finite non-negative"):
        promotions.verify_promotion_smoke_run(smoke, pilot_config=pilot_config)


def test_promotion_smoke_rejects_nonminimum_selected_checkpoint(tmp_path):
    pilot_config = json.loads(_canonical_paths()["pilot_config_path"].read_text())
    smoke = _make_promotion_smoke(tmp_path)
    manifest = json.loads((smoke / "training-manifest.json").read_text())
    wrong_step = manifest["schedule"]["requested_steps"][-1]
    checkpoint = smoke / f"checkpoints/checkpoint-{wrong_step}"
    final_adapter = smoke / "adapter/adapter_model.safetensors"
    final_adapter.unlink()
    os.link(checkpoint / "adapter_model.safetensors", final_adapter)
    selection = manifest["adapter_selection"]
    selection["best_checkpoint_step"] = wrong_step
    selection["best_checkpoint_relative_path"] = f"checkpoints/checkpoint-{wrong_step}"
    selection["best_checkpoint_adapter_model_sha256"] = promotions.sha256_file(
        checkpoint / "adapter_model.safetensors"
    )
    selection["final_adapter_model_sha256"] = promotions.sha256_file(final_adapter)
    manifest["adapter"] = promotions.inventory_tree(smoke / "adapter")
    _reseal_smoke_manifest(smoke, manifest)
    with pytest.raises(promotions.PilotResultError, match="selected checkpoint"):
        promotions.verify_promotion_smoke_run(smoke, pilot_config=pilot_config)


def test_promotion_smoke_rejects_consistently_resealed_fake_safetensors(tmp_path):
    pilot_config = json.loads(_canonical_paths()["pilot_config_path"].read_text())
    smoke = _make_promotion_smoke(tmp_path)
    manifest = json.loads((smoke / "training-manifest.json").read_text())
    best_step = manifest["adapter_selection"]["best_checkpoint_step"]
    best_weights = smoke / f"checkpoints/checkpoint-{best_step}/adapter_model.safetensors"
    final_weights = smoke / "adapter/adapter_model.safetensors"
    best_weights.write_bytes(b"selected-adapter")
    final_weights.write_bytes(b"selected-adapter")
    manifest["adapter"] = promotions.inventory_tree(smoke / "adapter")
    for field in (
        "best_checkpoint_adapter_model_sha256",
        "final_adapter_model_sha256",
    ):
        manifest["adapter_selection"][field] = promotions.sha256_file(final_weights)
    _reseal_smoke_manifest(smoke, manifest)
    with pytest.raises(promotions.PilotResultError, match="safetensors"):
        promotions.verify_promotion_smoke_run(smoke, pilot_config=pilot_config)


def test_promotion_smoke_rejects_zero_element_safetensors(tmp_path):
    pilot_config = json.loads(_canonical_paths()["pilot_config_path"].read_text())
    smoke = _make_promotion_smoke(tmp_path)
    manifest = json.loads((smoke / "training-manifest.json").read_text())
    best_step = manifest["adapter_selection"]["best_checkpoint_step"]
    best_weights = smoke / f"checkpoints/checkpoint-{best_step}/adapter_model.safetensors"
    final_weights = smoke / "adapter/adapter_model.safetensors"
    forged = _zero_tensor_safetensors_bytes()
    best_weights.write_bytes(forged)
    final_weights.write_bytes(forged)
    manifest["adapter"] = promotions.inventory_tree(smoke / "adapter")
    for field in (
        "best_checkpoint_adapter_model_sha256",
        "final_adapter_model_sha256",
    ):
        manifest["adapter_selection"][field] = promotions.sha256_file(final_weights)
    _reseal_smoke_manifest(smoke, manifest)
    with pytest.raises(promotions.PilotResultError, match="rank-16 LoRA signature|tensor metadata"):
        promotions.verify_promotion_smoke_run(smoke, pilot_config=pilot_config)


def test_promotion_smoke_rejects_near_tie_nonminimum_checkpoint(tmp_path):
    pilot_config = json.loads(_canonical_paths()["pilot_config_path"].read_text())
    smoke = _make_promotion_smoke(tmp_path)
    manifest = json.loads((smoke / "training-manifest.json").read_text())
    milestones = manifest["schedule"]["requested_steps"]
    wrong_step = milestones[0]
    true_best_step = manifest["adapter_selection"]["best_checkpoint_step"]
    rows = promotions._read_jsonl(smoke / "metrics.jsonl")
    wrong_eval = next(row for row in rows if row.get("step") == wrong_step and "eval_loss" in row)
    wrong_eval["eval_loss"] = manifest["adapter_selection"]["best_metric"] + 5e-13
    _reseal_smoke_metrics(smoke, rows)
    for checkpoint_step in milestones:
        checkpoint_state_path = (
            smoke / f"checkpoints/checkpoint-{checkpoint_step}/trainer_state.json"
        )
        checkpoint_state = json.loads(checkpoint_state_path.read_text())
        checkpoint_state["log_history"] = rows[: len(checkpoint_state["log_history"])]
        if checkpoint_step == wrong_step:
            checkpoint_state["best_metric"] = wrong_eval["eval_loss"]
        _write(checkpoint_state_path, checkpoint_state)
    manifest = json.loads((smoke / "training-manifest.json").read_text())
    wrong_checkpoint = smoke / f"checkpoints/checkpoint-{wrong_step}"
    final_weights = smoke / "adapter/adapter_model.safetensors"
    final_weights.unlink()
    os.link(wrong_checkpoint / "adapter_model.safetensors", final_weights)
    selection = manifest["adapter_selection"]
    selection["best_checkpoint_step"] = wrong_step
    selection["best_checkpoint_relative_path"] = f"checkpoints/checkpoint-{wrong_step}"
    selection["best_checkpoint_adapter_model_sha256"] = promotions.sha256_file(
        wrong_checkpoint / "adapter_model.safetensors"
    )
    selection["final_adapter_model_sha256"] = promotions.sha256_file(final_weights)
    manifest["adapter"] = promotions.inventory_tree(smoke / "adapter")
    assert wrong_step != true_best_step
    _reseal_smoke_manifest(smoke, manifest)
    with pytest.raises(promotions.PilotResultError, match="selected checkpoint"):
        promotions.verify_promotion_smoke_run(smoke, pilot_config=pilot_config)


def test_promotion_smoke_rejects_fake_loss_curve(tmp_path):
    pilot_config = json.loads(_canonical_paths()["pilot_config_path"].read_text())
    smoke = _make_promotion_smoke(tmp_path)
    png = smoke / "loss-curve.png"
    png.write_bytes(b"not-a-png")
    manifest = json.loads((smoke / "training-manifest.json").read_text())
    manifest["metrics"][png.name] = {
        "bytes": png.stat().st_size,
        "sha256": promotions.sha256_file(png),
    }
    _reseal_smoke_manifest(smoke, manifest)
    with pytest.raises(promotions.PilotResultError, match="PNG is invalid"):
        promotions.verify_promotion_smoke_run(smoke, pilot_config=pilot_config)


def test_promotion_smoke_rejects_valid_but_placeholder_loss_curve(tmp_path):
    import base64

    pilot_config = json.loads(_canonical_paths()["pilot_config_path"].read_text())
    smoke = _make_promotion_smoke(tmp_path)
    png = smoke / "loss-curve.png"
    svg = smoke / "loss-curve.svg"
    png.write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
    )
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0L1 1"/></svg>\n',
        encoding="utf-8",
    )
    manifest = json.loads((smoke / "training-manifest.json").read_text())
    for path in (png, svg):
        manifest["metrics"][path.name] = {
            "bytes": path.stat().st_size,
            "sha256": promotions.sha256_file(path),
        }
    _reseal_smoke_manifest(smoke, manifest)
    with pytest.raises(promotions.PilotResultError, match="loss-curve PNG structure"):
        promotions.verify_promotion_smoke_run(smoke, pilot_config=pilot_config)


def test_hardened_resume_rejects_consistently_resealed_lineage_forgery(tmp_path):
    source = REPO / "provenance/calibration/hardened-smoke-20260918"
    copied = tmp_path / "hardened"
    shutil.copytree(source, copied)
    verification_path = copied / "receipts/verification.json"
    verification = json.loads(verification_path.read_text())
    verification["inputs"]["clean_lineage_sha256"] = "0" * 64
    _write(verification_path, verification)
    digest = promotions.sha256_file(verification_path)
    (copied / "receipts/verification.json.sha256").write_text(
        f"{digest}  verification.json\n", encoding="ascii"
    )
    sums = []
    for path in sorted(candidate for candidate in copied.rglob("*") if candidate.is_file()):
        relative = path.relative_to(copied).as_posix()
        if relative == "SHA256SUMS":
            continue
        sums.append(f"{promotions.sha256_file(path)}  ./{relative}\n")
    (copied / "SHA256SUMS").write_text("".join(sums), encoding="ascii")
    pilot_config = json.loads(_canonical_paths()["pilot_config_path"].read_text())
    with pytest.raises(promotions.PilotResultError, match="retained authority"):
        promotions.verify_hardened_resume_evidence(
            verification_path,
            pilot_config=pilot_config,
        )


def test_canonical_comparison_rejects_consistently_resealed_report_forgery(tmp_path):
    paths = _canonical_paths()
    copied = tmp_path / "comparison"
    shutil.copytree(paths["canonical_comparison_dir"], copied)
    comparison_path = copied / "comparison.json"
    comparison = json.loads(comparison_path.read_text())
    comparison["inputs"]["math_review"]["sha256"] = "0" * 64
    _write(comparison_path, comparison)
    terminal_path = copied / "COMPLETED.json"
    terminal = json.loads(terminal_path.read_text())
    terminal["files"]["comparison.json"] = promotions.sha256_file(comparison_path)
    _write(terminal_path, terminal)
    pilot_config = json.loads(paths["pilot_config_path"].read_text())
    with pytest.raises(promotions.PilotResultError, match="retained authority"):
        promotions.verify_canonical_gguf_semantic_evidence(
            copied,
            pilot_config=pilot_config,
        )


def test_export_verifier_rejects_adapter_join_tampering(tmp_path):
    paths = _canonical_paths()
    pilot_config = json.loads(paths["pilot_config_path"].read_text())
    pilot_results = json.loads(paths["pilot_results_path"].read_text())
    comparison = promotions.verify_canonical_gguf_semantic_evidence(
        paths["canonical_comparison_dir"],
        pilot_config=pilot_config,
    )
    export_root = tmp_path / "exports"
    for manifest_path in sorted(paths["export_root"].glob("pilot-*/quantization-manifest.json")):
        destination = export_root / manifest_path.parent.name / manifest_path.name
        destination.parent.mkdir(parents=True)
        shutil.copyfile(manifest_path, destination)
    tampered_path = export_root / "pilot-clean-r16-lr1e5/quantization-manifest.json"
    tampered = json.loads(tampered_path.read_text())
    tampered["inputs"]["adapter"]["tree_sha256"] = "0" * 64
    _write(tampered_path, tampered)
    with pytest.raises(promotions.PilotResultError, match="adapter does not match"):
        promotions.verify_export_manifests(
            export_root,
            pilot_config=pilot_config,
            pilot_results=pilot_results,
            comparison_receipt=comparison,
        )


def test_export_verifier_rejects_base_join_tampering(tmp_path):
    paths = _canonical_paths()
    pilot_config = json.loads(paths["pilot_config_path"].read_text())
    pilot_results = json.loads(paths["pilot_results_path"].read_text())
    comparison = promotions.verify_canonical_gguf_semantic_evidence(
        paths["canonical_comparison_dir"],
        pilot_config=pilot_config,
    )
    export_root = tmp_path / "exports"
    for manifest_path in sorted(paths["export_root"].glob("pilot-*/quantization-manifest.json")):
        destination = export_root / manifest_path.parent.name / manifest_path.name
        destination.parent.mkdir(parents=True)
        shutil.copyfile(manifest_path, destination)
    tampered_path = export_root / "pilot-warm-r16-lr5e6/quantization-manifest.json"
    tampered = json.loads(tampered_path.read_text())
    tampered["inputs"]["base"]["tree_sha256"] = "0" * 64
    _write(tampered_path, tampered)
    with pytest.raises(promotions.PilotResultError, match="base does not match"):
        promotions.verify_export_manifests(
            export_root,
            pilot_config=pilot_config,
            pilot_results=pilot_results,
            comparison_receipt=comparison,
        )


def test_schema_v2_rejects_legacy_hybrid_and_source_mutation(tmp_path):
    config = _build_canonical(tmp_path)
    downgraded = copy.deepcopy(config)
    downgraded["schema_version"] = 1
    with pytest.raises(promotions.PilotResultError, match="schema-v1"):
        promotions.validate_promotion_config(downgraded)
    hybrid = copy.deepcopy(config)
    hybrid["source_pilots"]["matched_prompt_evaluation"] = {}
    with pytest.raises(promotions.PilotResultError, match="legacy PEFT"):
        promotions.validate_promotion_config(hybrid)
    mutated = copy.deepcopy(config)
    mutated["source_code"]["trainer_sha256"] = "0" * 64
    with pytest.raises(promotions.PilotResultError, match="executable source changed"):
        promotions.validate_promotion_config(mutated, enforce_authority=False)
    dependency_forgery = copy.deepcopy(config)
    dependency_forgery["source_code"]["campaign_io_sha256"] = "0" * 64
    dependency_forgery["training_gates"]["hardened_interruption_resume"]["script_sha256"][
        "campaign_io.py"
    ] = "0" * 64
    dependency_forgery["training_gates"]["promotion_smoke"]["script_sha256"]["campaign_io.py"] = (
        "0" * 64
    )
    with pytest.raises(promotions.PilotResultError, match="helper source hashes"):
        promotions.validate_promotion_config(dependency_forgery, enforce_authority=False)


def test_schema_v2_rejects_consistent_selection_and_dataset_forgery(tmp_path):
    config = _build_canonical(tmp_path)
    forged = copy.deepcopy(config)
    forged["dataset"]["fingerprint_sha256"] = "0" * 64
    forged["training_gates"]["hardened_interruption_resume"]["train_fingerprint_sha256"] = "0" * 64
    forged["training_gates"]["promotion_smoke"]["train_fingerprint_sha256"] = "0" * 64
    clean = next(
        candidate
        for candidate in forged["candidates"]
        if candidate["id"] == "full-best-clean-private-enriched"
    )
    clean["rank"] = 999
    clean["learning_rate"] = 0.1
    with pytest.raises(promotions.PilotResultError, match="retained authority"):
        promotions.validate_promotion_config(forged, enforce_authority=False)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_length", 2048),
        ("seed", 1),
        ("warmup_ratio", 0.9),
        ("weight_decay", 100.0),
        ("weight_decay", False),
        ("epochs", True),
        ("logging_steps", 999),
        ("batch_size", 16),
        ("gradient_accumulation", 4),
    ],
)
def test_schema_v2_rejects_precommit_shared_treatment_drift(tmp_path, field, value):
    config = _build_canonical(tmp_path)
    config["shared"][field] = value
    if field in {"batch_size", "gradient_accumulation"}:
        config["shared"]["global_batch"] = (
            config["shared"]["batch_size"] * config["shared"]["gradient_accumulation"]
        )
    with pytest.raises(
        promotions.PilotResultError, match="shared treatment|global batch|invalid full-run shared"
    ):
        promotions.validate_promotion_config(config, enforce_authority=False)


def test_schema_v2_rejects_runtime_input_authority_drift(tmp_path):
    config = _build_canonical(tmp_path)
    config["runtime_input_authority"]["lineages"]["warm"]["base_tree_sha256"] = "0" * 64
    with pytest.raises(promotions.PilotResultError, match="runtime input authority"):
        promotions.validate_promotion_config(config, enforce_authority=False)


@pytest.mark.parametrize("field", ["png_pixel_sha256", "svg_series_sha256"])
def test_schema_v2_requires_loss_curve_render_bindings(tmp_path, field):
    config = _build_canonical(tmp_path)
    del config["training_gates"]["promotion_smoke"]["loss_curve"][field]
    with pytest.raises(promotions.PilotResultError, match="semantic training evidence"):
        promotions.validate_promotion_config(config, enforce_authority=False)


def test_launcher_requires_exact_committed_schema_v2_blob(tmp_path, monkeypatch):
    config = _build_canonical(tmp_path)
    output = tmp_path / "full.json"
    _write(output, config)
    output.with_suffix(".json.sha256").write_text(
        f"{promotions.sha256_file(output)}  {output.name}\n", encoding="ascii"
    )
    committed = json.dumps(config)

    def fake_git(*_args, **_kwargs):
        return type("Process", (), {"returncode": 0, "stdout": committed})()

    monkeypatch.setattr(promotions.subprocess, "run", fake_git)
    loaded, _digest = launcher.load_frozen_config(output)
    assert loaded == config
    forged = copy.deepcopy(config)
    forged["candidates"][0]["rank"] = 999
    _write(output, forged)
    output.with_suffix(".json.sha256").write_text(
        f"{promotions.sha256_file(output)}  {output.name}\n", encoding="ascii"
    )
    with pytest.raises(promotions.PilotResultError):
        launcher.load_frozen_config(output)


def test_schema_v2_writer_rejects_noncanonical_output_path(tmp_path):
    config = _build_canonical(tmp_path)
    with pytest.raises(promotions.PilotResultError, match="must be written"):
        promotions.write_frozen_config(tmp_path / "wrong-name.json", config)


def test_cli_requires_one_complete_evidence_mode():
    shared = [
        "--pilot-config",
        "pilot.json",
        "--pilot-results",
        "results.json",
        "--best-clean-id",
        "clean-r16-lr1e5",
        "--best-warm-id",
        "warm-r16-lr5e6",
        "--rights-clean-rows",
        "300000",
        "--clean-selection-note",
        "clean",
        "--warm-selection-note",
        "warm",
        "--output",
        "full.json",
    ]
    with pytest.raises(SystemExit):
        promotions.parse_args(
            [
                *shared,
                "--canonical-comparison-dir",
                "comparison",
            ]
        )
    with pytest.raises(SystemExit):
        promotions.parse_args(
            [
                *shared,
                "--pilot-evaluation-dir",
                "legacy",
                "--export-root",
                "exports",
            ]
        )
