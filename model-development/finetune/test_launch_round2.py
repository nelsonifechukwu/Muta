from __future__ import annotations

import argparse
import importlib.util
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


launcher = _load("launch_round2")


def _config():
    return {
        "dataset": {
            "pilot_rows": 20,
            "private_policy": "include",
            "fingerprint_sha256": "a" * 64,
        },
        "validation": {"rows": 5, "fingerprint_sha256": "b" * 64},
        "shared": {
            "max_length": 512,
            "epochs": 1.0,
            "batch_size": 16,
            "gradient_accumulation": 4,
            "global_batch_per_gpu": 64,
            "warmup_ratio": 0.03,
            "weight_decay": 0.0,
            "eval_steps": 10,
            "save_steps": 10,
            "logging_steps": 1,
            "seed": 3407,
        },
        "candidates": [
            {
                "id": "clean",
                "lineage": "clean",
                "rank": 16,
                "learning_rate": 1e-5,
                "preferred_host": "oracle",
            },
            {
                "id": "warm",
                "lineage": "warm",
                "rank": 8,
                "learning_rate": 5e-6,
                "preferred_host": "csd3",
            },
        ],
    }


def test_host_filtered_array_selects_only_that_hosts_candidates():
    selected = launcher.select_candidate(
        _config(), candidate_id=None, candidate_index=0, host_filter="csd3"
    )
    assert selected["id"] == "warm"


def test_command_uses_correct_lineage_and_frozen_hyperparameters(tmp_path):
    args = argparse.Namespace(
        python=Path("python"),
        clean_base=Path("clean-base"),
        warm_base=Path("warm-base"),
        clean_lineage=Path("clean.json"),
        warm_lineage=Path("warm.json"),
        dataset_manifest=Path("manifest.json"),
        validation_manifest=Path("dev-manifest.json"),
        output_root=tmp_path,
        config=tmp_path / "pilot.json",
        batch_size=None,
        eval_batch_size=None,
        gradient_accumulation=None,
        dataloader_workers=4,
        resume_from_checkpoint=None,
    )
    command = launcher.build_command(
        args,
        _config(),
        _config()["candidates"][1],
        config_sha256="c" * 64,
        protocol_deviation=None,
    )
    joined = " ".join(command)
    assert "--model warm-base" in joined
    assert "--lineage warm" in joined
    assert "--tokenizer clean-base" in joined
    assert "--rank 8" in joined
    assert "--learning-rate 5e-06" in joined
    assert "--pilot-rows 20" in joined
    assert "--expected-planned-steps 1" in joined
    assert "--expected-campaign-config-sha256 " + "c" * 64 in joined


def test_zero_batch_override_is_rejected_not_silently_ignored(tmp_path):
    args = argparse.Namespace(
        python=Path("python"),
        clean_base=Path("clean-base"),
        warm_base=Path("warm-base"),
        clean_lineage=Path("clean.json"),
        warm_lineage=Path("warm.json"),
        dataset_manifest=Path("manifest.json"),
        validation_manifest=Path("dev-manifest.json"),
        output_root=tmp_path,
        config=tmp_path / "pilot.json",
        batch_size=0,
        eval_batch_size=None,
        gradient_accumulation=None,
        dataloader_workers=4,
        resume_from_checkpoint=None,
    )
    with pytest.raises(launcher.PilotResultError, match="not frozen/approved"):
        launcher.build_command(
            args,
            _config(),
            _config()["candidates"][0],
            config_sha256="c" * 64,
            protocol_deviation=None,
        )


def test_expected_steps_include_frozen_epoch_count(tmp_path):
    config = _config()
    config["shared"]["epochs"] = 1.5
    args = argparse.Namespace(
        python=Path("python"),
        clean_base=Path("clean-base"),
        warm_base=Path("warm-base"),
        clean_lineage=Path("clean.json"),
        warm_lineage=Path("warm.json"),
        dataset_manifest=Path("manifest.json"),
        validation_manifest=Path("dev-manifest.json"),
        output_root=tmp_path,
        config=tmp_path / "pilot.json",
        batch_size=None,
        eval_batch_size=None,
        gradient_accumulation=None,
        dataloader_workers=4,
        resume_from_checkpoint=None,
    )
    command = launcher.build_command(
        args,
        config,
        config["candidates"][0],
        config_sha256="c" * 64,
        protocol_deviation=None,
    )
    joined = " ".join(command)
    assert "--expected-planned-steps 2" in joined
