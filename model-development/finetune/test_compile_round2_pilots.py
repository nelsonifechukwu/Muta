from __future__ import annotations

import importlib.util
import json
import shutil
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


compiler = _load("compile_round2_pilots")
REPO = HERE.parents[1]


def _config(candidates=None):
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
            "batch_size": 16,
            "gradient_accumulation": 4,
            "seed": 3407,
            "global_batch_per_gpu": 64,
            "warmup_ratio": 0.03,
            "weight_decay": 0.0,
            "eval_steps": 100,
            "save_steps": 100,
            "logging_steps": 5,
            "completion_only_loss": True,
        },
        "candidates": candidates
        or [
            {
                "id": "warm-r16-lr1e5",
                "lineage": "warm",
                "rank": 16,
                "learning_rate": 1e-5,
                "preferred_host": "csd3",
            }
        ],
    }


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _make_complete_run(root: Path, candidate: dict, config: dict) -> Path:
    run = root / candidate["id"]
    run.mkdir(parents=True)
    adapter = run / "adapter"
    adapter.mkdir()
    (adapter / "adapter_model.safetensors").write_bytes(f"weights-{candidate['id']}".encode())
    (adapter / "adapter_config.json").write_text('{"r": 16}\n')
    adapter_receipt = compiler.inventory_tree(adapter)
    metrics = [
        {"loss": 1.7, "step": 100},
        {"eval_loss": 1.4, "step": 100},
        {"eval_loss": 1.35, "step": 200},
        {"eval_loss": 1.32, "step": 300},
        {"eval_loss": 1.3, "step": 313},
        {"train_loss": 1.5, "train_runtime": 123.25, "step": 313},
        {"eval_loss": 1.3, "step": 313},
    ]
    metrics_path = run / "metrics.jsonl"
    metrics_path.write_text("".join(json.dumps(row) + "\n" for row in metrics))
    for name in ("metrics.csv", "loss-curve.png", "loss-curve.svg"):
        (run / name).write_bytes(f"test-{name}".encode())
    metric_receipt = {
        name: {
            "bytes": (run / name).stat().st_size,
            "sha256": compiler.sha256_file(run / name),
        }
        for name in ("metrics.jsonl", "metrics.csv", "loss-curve.png", "loss-curve.svg")
    }
    manifest = {
        "schema_version": 2,
        "run_name": candidate["id"],
        "lineage": candidate["lineage"],
        "base_lineage": {
            "receipt_sha256": "9" * 64,
            "observed": {"tree_sha256": "8" * 64},
            "receipt": {
                "lineage": candidate["lineage"],
                "training_base": {"tree_sha256": "8" * 64},
                "prior_stage": {
                    "published_gguf": {"sha256": "7" * 64},
                },
            },
        },
        "rank": candidate["rank"],
        "learning_rate": candidate["learning_rate"],
        "pilot_rows": config["dataset"]["pilot_rows"],
        "private_policy": config["dataset"]["private_policy"],
        "training_method": "lora_bf16",
        "completion_only_loss": True,
        "lora_alpha": candidate["rank"],
        "target_modules": [
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        "max_length": config["shared"]["max_length"],
        "seed": config["shared"]["seed"],
        "global_batch_per_gpu": config["shared"]["global_batch_per_gpu"],
        "batch_size": config["shared"]["batch_size"],
        "eval_batch_size": config["shared"]["batch_size"],
        "gradient_accumulation": config["shared"]["gradient_accumulation"],
        "dataset": {
            "dataset_fingerprint_sha256": config["dataset"]["fingerprint_sha256"],
            "row_count": config["dataset"]["rows"],
        },
        "validation": {
            "dataset_fingerprint_sha256": config["validation"]["fingerprint_sha256"],
            "row_count": config["validation"]["rows"],
        },
        "tokenization": {
            "train": {"rows": config["dataset"]["pilot_rows"]},
            "validation": {"rows": config["validation"]["rows"]},
        },
        "train_ordered_id_sha256": "5" * 64,
        "validation_ordered_id_sha256": "6" * 64,
        "train_metrics": {"train_loss": 1.5, "train_runtime": 123.25},
        "validation_metrics": {"eval_loss": 1.3},
        "trainer_global_step": 313,
        "planned_steps": 313,
        "max_steps": -1,
        "warmup_steps": 10,
        "source_counts_before_policy": {
            "test": config["dataset"]["rows"] - 350,
            "waec_elearning": 47,
            "cheetahwaec": 303,
        },
        "source_counts_after_policy": {
            "test": config["dataset"]["rows"] - 350,
            "waec_elearning": 47,
            "cheetahwaec": 303,
        },
        "training_source_counts": {"test": config["dataset"]["pilot_rows"]},
        "gpu_memory": {"training": {"peak_reserved_bytes": 8 * 1024**3}},
        "environment": {
            "hostname": "gpu-test-01",
            "python": "3.12.3",
            "torch": "2.7.0",
            "cuda": "12.8",
            "gpu": "Fake A100",
            "packages": {"torch": "2.7.0", "transformers": "5.5.0"},
        },
        "git": {"available": True, "dirty": False, "commit": "1" * 40},
        "scripts": {"train_lora_round2.py": "2" * 64},
        "adapter": adapter_receipt,
        "metrics": metric_receipt,
    }
    manifest_path = run / "training-manifest.json"
    _write_json(manifest_path, manifest)
    _write_json(
        run / "resolved-config.json",
        {
            "run_name": candidate["id"],
            "lineage": candidate["lineage"],
            "rank": candidate["rank"],
            "lora_alpha": candidate["rank"],
            "learning_rate": candidate["learning_rate"],
            "max_length": config["shared"]["max_length"],
            "epochs": config["shared"]["epochs"],
            "batch_size": config["shared"]["batch_size"],
            "eval_batch_size": config["shared"]["batch_size"],
            "gradient_accumulation": config["shared"]["gradient_accumulation"],
            "global_batch_per_gpu": config["shared"]["global_batch_per_gpu"],
            "warmup_ratio": config["shared"]["warmup_ratio"],
            "weight_decay": config["shared"]["weight_decay"],
            "eval_steps": config["shared"]["eval_steps"],
            "save_steps": config["shared"]["save_steps"],
            "logging_steps": config["shared"]["logging_steps"],
            "pilot_rows": config["dataset"]["pilot_rows"],
            "private_policy": config["dataset"]["private_policy"],
            "seed": config["shared"]["seed"],
            "dataset": {"dataset_fingerprint_sha256": config["dataset"]["fingerprint_sha256"]},
            "validation": {
                "dataset_fingerprint_sha256": config["validation"]["fingerprint_sha256"]
            },
        },
    )
    _write_json(
        run / "COMPLETED.json",
        {
            "run_name": candidate["id"],
            "training_manifest_sha256": compiler.sha256_file(manifest_path),
        },
    )
    checkpoint_root = run / "checkpoints"
    for step in (200, 300, 313):
        checkpoint = checkpoint_root / f"checkpoint-{step}"
        checkpoint.mkdir(parents=True)
        _write_json(checkpoint / "trainer_state.json", {"global_step": step})
        (checkpoint / "adapter_model.safetensors").write_bytes(
            (adapter / "adapter_model.safetensors").read_bytes()
        )
        (checkpoint / "adapter_config.json").write_bytes(
            (adapter / "adapter_config.json").read_bytes()
        )
    _write_json(
        checkpoint_root / "trainer_state.json",
        {
            "global_step": 313,
            "best_metric": 1.3,
            "best_model_checkpoint": "/remote/oracle/run/checkpoints/checkpoint-313",
        },
    )
    return run


def test_compiler_validates_complete_run_and_writes_terse_tables(tmp_path, monkeypatch):
    config = _config()
    config_path = tmp_path / "pilot.json"
    _write_json(config_path, config)
    runs = tmp_path / "runs"
    runs.mkdir()
    run = _make_complete_run(runs, config["candidates"][0], config)

    result, invalid = compiler.compile_results(config_path=config_path, run_roots=[runs])
    assert not invalid
    assert result["promotion_ready"] is True
    row = result["rows"][0]
    assert row["status"] == "complete"
    assert row["host"] == "gpu-test-01"
    assert row["best_dev_loss"] == 1.3
    assert row["train_loss"] == 1.5
    assert row["runtime_seconds"] == 123.25
    assert row["steps"] == 313
    assert row["peak_vram_gib"] == 8.0
    assert row["adapter_sha256"] == compiler.inventory_tree(run / "adapter")["tree_sha256"]
    assert row["training_base_tree_sha256"] == "8" * 64
    assert row["incumbent_gguf_sha256"] == "7" * 64

    output = tmp_path / "summary"
    monkeypatch.setattr(
        compiler,
        "_git_receipt",
        lambda _repo: {"available": True, "dirty": output.exists()},
    )
    compiler.write_results(output, result)
    assert (output / "pilot-results.csv").is_file()
    markdown = (output / "pilot-results.md").read_text()
    assert "best dev loss" in markdown
    assert "warm-r16-lr1e5" in markdown
    receipt = json.loads((output / "compiler-receipt.json").read_text())
    assert receipt["git"]["dirty"] is False
    assert set(receipt["artifacts"]) == {
        "pilot-results.csv",
        "pilot-results.json",
        "pilot-results.md",
    }


def test_compiler_marks_completed_hyperparameter_mismatch_invalid(tmp_path):
    config = _config()
    config_path = tmp_path / "pilot.json"
    _write_json(config_path, config)
    runs = tmp_path / "runs"
    runs.mkdir()
    run = _make_complete_run(runs, config["candidates"][0], config)
    manifest_path = run / "training-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["rank"] = 32
    _write_json(manifest_path, manifest)
    completed = {
        "run_name": config["candidates"][0]["id"],
        "training_manifest_sha256": compiler.sha256_file(manifest_path),
    }
    _write_json(run / "COMPLETED.json", completed)

    result, invalid = compiler.compile_results(config_path=config_path, run_roots=[runs])
    assert invalid
    assert result["rows"][0]["status"] == "invalid"
    assert "rank mismatch" in result["rows"][0]["detail"]


def test_compiler_derives_expected_steps_from_frozen_rows_and_batch(tmp_path):
    config = _config()
    config_path = tmp_path / "pilot.json"
    _write_json(config_path, config)
    runs = tmp_path / "runs"
    runs.mkdir()
    run = _make_complete_run(runs, config["candidates"][0], config)
    manifest_path = run / "training-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["trainer_global_step"] = 300
    manifest["planned_steps"] = 300
    _write_json(manifest_path, manifest)
    _write_json(
        run / "COMPLETED.json",
        {
            "run_name": config["candidates"][0]["id"],
            "training_manifest_sha256": compiler.sha256_file(manifest_path),
        },
    )
    result, invalid = compiler.compile_results(config_path=config_path, run_roots=[runs])
    assert invalid
    assert "frozen expected steps 313" in result["rows"][0]["detail"]


def test_compiler_rejects_unreceipted_batch_split_even_when_global_batch_matches(tmp_path):
    config = _config()
    config_path = tmp_path / "pilot.json"
    _write_json(config_path, config)
    runs = tmp_path / "runs"
    runs.mkdir()
    run = _make_complete_run(runs, config["candidates"][0], config)
    manifest_path = run / "training-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.update(batch_size=32, eval_batch_size=32, gradient_accumulation=2)
    _write_json(manifest_path, manifest)
    resolved_path = run / "resolved-config.json"
    resolved = json.loads(resolved_path.read_text())
    resolved.update(batch_size=32, eval_batch_size=32, gradient_accumulation=2)
    _write_json(resolved_path, resolved)
    _write_json(
        run / "COMPLETED.json",
        {
            "run_name": config["candidates"][0]["id"],
            "training_manifest_sha256": compiler.sha256_file(manifest_path),
        },
    )
    result, invalid = compiler.compile_results(config_path=config_path, run_roots=[runs])
    assert invalid
    assert "batch_size mismatch" in result["rows"][0]["detail"]


def test_compiler_rejects_private_include_policy_that_dropped_sources(tmp_path):
    config = _config()
    config_path = tmp_path / "pilot.json"
    _write_json(config_path, config)
    runs = tmp_path / "runs"
    runs.mkdir()
    run = _make_complete_run(runs, config["candidates"][0], config)
    manifest_path = run / "training-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["source_counts_after_policy"].pop("waec_elearning")
    _write_json(manifest_path, manifest)
    _write_json(
        run / "COMPLETED.json",
        {
            "run_name": config["candidates"][0]["id"],
            "training_manifest_sha256": compiler.sha256_file(manifest_path),
        },
    )
    result, invalid = compiler.compile_results(config_path=config_path, run_roots=[runs])
    assert invalid
    assert "include policy" in result["rows"][0]["detail"]


def test_post_training_eval_cannot_impersonate_missing_scheduled_eval(tmp_path):
    config = _config()
    config_path = tmp_path / "pilot.json"
    _write_json(config_path, config)
    runs = tmp_path / "runs"
    runs.mkdir()
    run = _make_complete_run(runs, config["candidates"][0], config)
    metrics_path = run / "metrics.jsonl"
    rows = [json.loads(line) for line in metrics_path.read_text().splitlines()]
    # Remove the scheduled step-313 eval while retaining the explicit eval that
    # follows Trainer's terminal train summary.
    removed = False
    rewritten = []
    for row in rows:
        if not removed and row.get("step") == 313 and "eval_loss" in row:
            removed = True
            continue
        rewritten.append(row)
    metrics_path.write_text("".join(json.dumps(row) + "\n" for row in rewritten))
    manifest_path = run / "training-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["metrics"]["metrics.jsonl"] = {
        "bytes": metrics_path.stat().st_size,
        "sha256": compiler.sha256_file(metrics_path),
    }
    _write_json(manifest_path, manifest)
    _write_json(
        run / "COMPLETED.json",
        {
            "run_name": config["candidates"][0]["id"],
            "training_manifest_sha256": compiler.sha256_file(manifest_path),
        },
    )
    result, invalid = compiler.compile_results(config_path=config_path, run_roots=[runs])
    assert invalid
    assert "frozen schedule" in result["rows"][0]["detail"]


def test_compiler_requires_best_adapter_config_not_only_matching_weights(tmp_path):
    config = _config()
    config_path = tmp_path / "pilot.json"
    _write_json(config_path, config)
    runs = tmp_path / "runs"
    runs.mkdir()
    run = _make_complete_run(runs, config["candidates"][0], config)
    (run / "adapter" / "adapter_config.json").write_text('{"r": 32}\n')
    manifest_path = run / "training-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["adapter"] = compiler.inventory_tree(run / "adapter")
    _write_json(manifest_path, manifest)
    _write_json(
        run / "COMPLETED.json",
        {
            "run_name": config["candidates"][0]["id"],
            "training_manifest_sha256": compiler.sha256_file(manifest_path),
        },
    )
    result, invalid = compiler.compile_results(config_path=config_path, run_roots=[runs])
    assert invalid
    assert "adapter config" in result["rows"][0]["detail"]


def test_compiler_rejects_incomplete_checkpoint_evidence(tmp_path):
    config = _config()
    config_path = tmp_path / "pilot.json"
    _write_json(config_path, config)
    runs = tmp_path / "runs"
    runs.mkdir()
    run = _make_complete_run(runs, config["candidates"][0], config)
    (run / "checkpoints" / "checkpoint-250").mkdir()
    result, invalid = compiler.compile_results(config_path=config_path, run_roots=[runs])
    assert invalid
    assert "incomplete evidence" in result["rows"][0]["detail"]


def test_compiler_rejects_duplicate_candidate_directories(tmp_path):
    config = _config()
    config_path = tmp_path / "pilot.json"
    _write_json(config_path, config)
    roots = [tmp_path / "oracle", tmp_path / "csd3"]
    for root in roots:
        root.mkdir()
        (root / config["candidates"][0]["id"]).mkdir()
    with pytest.raises(compiler.PilotResultError, match="duplicate candidate run"):
        compiler.compile_results(config_path=config_path, run_roots=roots)


def test_compiler_rejects_different_ordered_training_rows_across_candidates(tmp_path):
    candidates = [
        {"id": "warm-a", "lineage": "warm", "rank": 16, "learning_rate": 1e-5},
        {"id": "warm-b", "lineage": "warm", "rank": 16, "learning_rate": 2e-5},
    ]
    config = _config(candidates=candidates)
    config_path = tmp_path / "pilot.json"
    _write_json(config_path, config)
    runs = tmp_path / "runs"
    runs.mkdir()
    _make_complete_run(runs, candidates[0], config)
    second = _make_complete_run(runs, candidates[1], config)
    manifest_path = second / "training-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["train_ordered_id_sha256"] = "4" * 64
    _write_json(manifest_path, manifest)
    _write_json(
        second / "COMPLETED.json",
        {
            "run_name": candidates[1]["id"],
            "training_manifest_sha256": compiler.sha256_file(manifest_path),
        },
    )
    with pytest.raises(compiler.PilotResultError, match="identical ordered dataset rows"):
        compiler.compile_results(config_path=config_path, run_roots=[runs])


def test_compiler_rejects_duplicate_config_ids():
    candidate = _config()["candidates"][0]
    with pytest.raises(compiler.PilotResultError, match="duplicate candidate IDs"):
        compiler.validate_pilot_config(_config(candidates=[candidate, dict(candidate)]))


def test_compiler_reports_missing_running_and_failed(tmp_path):
    candidates = [
        {"id": "missing", "lineage": "clean", "rank": 16, "learning_rate": 1e-5},
        {"id": "running", "lineage": "warm", "rank": 16, "learning_rate": 1e-5},
        {"id": "failed", "lineage": "warm", "rank": 32, "learning_rate": 1e-5},
    ]
    config = _config(candidates=candidates)
    config_path = tmp_path / "pilot.json"
    _write_json(config_path, config)
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "running").mkdir()
    _write_json(runs / "running" / "RUNNING.json", {"pid": 12})
    (runs / "failed").mkdir()
    _write_json(
        runs / "failed" / "FAILED.json",
        {"exception": "RuntimeError", "message": "boom"},
    )
    result, invalid = compiler.compile_results(config_path=config_path, run_roots=[runs])
    assert not invalid
    assert result["promotion_ready"] is False
    assert [row["status"] for row in result["rows"]] == ["missing", "running", "failed"]


def test_real_protocol_deviation_is_narrow_and_calibration_bound(tmp_path):
    config_path = REPO / "provenance/configs/pilot-sweep.json"
    config = json.loads(config_path.read_text())
    source = REPO / "provenance/calibration/oracle-b64-20260918"
    copied = tmp_path / "calibration"
    shutil.copytree(source, copied)
    receipt_path = copied / "protocol-deviation.json"
    verified = compiler._verify_protocol_deviation(
        receipt_path,
        config_path=config_path,
        config=config,
    )
    assert verified["actual"] == {
        "batch_size": 64,
        "eval_batch_size": 64,
        "gradient_accumulation": 1,
        "global_batch_per_gpu": 64,
    }

    receipt = json.loads(receipt_path.read_text())
    receipt["allowed_actual"].update(
        batch_size=32,
        eval_batch_size=32,
        gradient_accumulation=2,
    )
    _write_json(receipt_path, receipt)
    with pytest.raises(compiler.PilotResultError, match="unapproved batch treatment"):
        compiler._verify_protocol_deviation(
            receipt_path,
            config_path=config_path,
            config=config,
        )
