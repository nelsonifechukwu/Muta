from __future__ import annotations

import csv
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


promotions = _load("build_round2_promotions")
launcher = _load("launch_round2_full")


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
