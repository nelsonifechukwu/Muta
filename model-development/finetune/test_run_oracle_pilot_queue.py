from __future__ import annotations

import argparse
import importlib.util
import json
import os
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


queue = _load("run_oracle_pilot_queue")


def _config():
    return {
        "candidates": [
            {"id": "oracle-a", "preferred_host": "oracle"},
            {"id": "csd3-a", "preferred_host": "csd3"},
            {"id": "oracle-b", "preferred_host": "oracle"},
        ]
    }


def _args(tmp_path):
    return argparse.Namespace(
        python=Path("python"),
        config=Path("config.json"),
        host_filter="oracle",
        clean_base=Path("clean-base"),
        warm_base=Path("warm-base"),
        clean_lineage=Path("clean.json"),
        warm_lineage=Path("warm.json"),
        dataset_manifest=Path("dataset.json"),
        validation_manifest=Path("validation.json"),
        output_root=tmp_path,
        batch_size=32,
        eval_batch_size=None,
        gradient_accumulation=2,
        dataloader_workers=8,
    )


def test_candidate_selection_defaults_to_oracle_config_order():
    assert queue.select_candidate_ids(
        _config(), host_filter="oracle", requested=None
    ) == ["oracle-a", "oracle-b"]


def test_candidate_selection_refuses_wrong_host():
    with pytest.raises(ValueError, match="do not belong"):
        queue.select_candidate_ids(
            _config(), host_filter="oracle", requested=["csd3-a"]
        )


def test_latest_checkpoint_requires_trainer_state_and_uses_highest_step(tmp_path):
    for name in ("checkpoint-9", "checkpoint-100", "checkpoint-invalid"):
        (tmp_path / "checkpoints" / name).mkdir(parents=True)
    (tmp_path / "checkpoints" / "checkpoint-9" / "trainer_state.json").write_text("{}")
    (tmp_path / "checkpoints" / "checkpoint-100" / "trainer_state.json").write_text(
        "{}"
    )
    assert queue.latest_checkpoint(tmp_path).name == "checkpoint-100"


def test_launcher_command_propagates_tuning_and_resume_options(tmp_path):
    checkpoint = tmp_path / "checkpoints" / "checkpoint-100"
    command = queue.build_launcher_command(_args(tmp_path), "oracle-a", checkpoint)
    joined = " ".join(map(str, command))
    assert "--candidate-id oracle-a" in joined
    assert "--host-filter oracle" in joined
    assert "--batch-size 32" in joined
    assert "--gradient-accumulation 2" in joined
    assert "--resume-from-checkpoint" in joined


def test_running_process_marker_detects_current_pid(tmp_path):
    marker = tmp_path / "RUNNING.json"
    marker.write_text(json.dumps({"pid": os.getpid()}))
    assert queue.running_process_alive(marker)


def test_running_process_marker_without_pid_is_treated_as_stale(tmp_path):
    marker = tmp_path / "RUNNING.json"
    marker.write_text("{}")
    assert not queue.running_process_alive(marker)
