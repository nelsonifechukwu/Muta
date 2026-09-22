from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import run_round2_full_queue as queue


def write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data))


@pytest.fixture
def setup(tmp_path, monkeypatch):
    config_sha = "a" * 64
    args = SimpleNamespace(
        config=tmp_path / "config.json",
        expected_config_sha256=config_sha,
        queue_dir=tmp_path / "queue",
        output_root=tmp_path / "full",
        python=Path("python"),
        clean_base=tmp_path / "clean",
        warm_base=tmp_path / "warm",
        clean_lineage=tmp_path / "clean.json",
        warm_lineage=tmp_path / "warm.json",
        dataset_manifest=tmp_path / "data.json",
        validation_manifest=tmp_path / "dev.json",
        initial_adapter=tmp_path / "pilot/adapter",
        dataloader_workers=8,
        gpu=0,
        max_stage_seconds=123,
    )
    candidates = [
        {
            "id": name,
            "planned_rows": 300350,
            "planned_steps": 4693,
            "lineage": "clean" if index == 0 else "warm",
            "rank": 16,
            "learning_rate": 1e-5 if index == 0 else 5e-6,
            "initial_adapter_tree_sha256": None if index == 0 else "d" * 64,
            "source_pilot_training_manifest_sha256": "e" * 64,
        }
        for index, name in enumerate(queue.CANDIDATES)
    ]
    config = {
        "schema_version": 3,
        "candidates": candidates,
        "source_code": {"trainer_sha256": "f" * 64},
        "runtime_input_authority": {
            "lineages": {lineage: {"base_tree_sha256": "b" * 64} for lineage in ("clean", "warm")}
        },
    }
    write(args.config, config)
    calls = []

    def load(path, *, expected_sha256):
        assert path == args.config and expected_sha256 == config_sha
        return config, config_sha

    monkeypatch.setattr(queue, "load_frozen_config", load)
    monkeypatch.setattr(
        queue,
        "select_candidate",
        lambda cfg, candidate_id, candidate_index: next(
            item for item in cfg["candidates"] if item["id"] == candidate_id
        ),
    )
    monkeypatch.setattr(queue, "check_gpu_idle", lambda gpu: {"gpu": gpu, "stdout": ""})
    monkeypatch.setattr(queue, "gpu_lock_path", lambda gpu: tmp_path / f"gpu-{gpu}.lock")
    return args, candidates, calls


def install_process(monkeypatch, setup, *, fail_stage=None, timeout_stage=None, corrupt_stage=None):
    args, candidates, calls = setup
    active = []

    class Process:
        def __init__(self, command, **kwargs):
            assert not active, "queue must never overlap its stages"
            self.index = len(calls) + 1
            self.pid = 1000 + self.index
            self.returncode = None
            self.command = command
            assert kwargs["start_new_session"] is True
            assert kwargs["env"]["CUDA_VISIBLE_DEVICES"] == "0"
            assert len(kwargs["pass_fds"]) == 1
            os.fstat(kwargs["pass_fds"][0])
            calls.append(command)
            active.append(self.pid)

        def wait(self, timeout):
            assert timeout == args.max_stage_seconds
            if self.index == timeout_stage:
                raise subprocess.TimeoutExpired(self.command, timeout)
            active.clear()
            self.returncode = 7 if self.index == fail_stage else 0
            if self.returncode == 0:
                candidate = candidates[self.index - 1]
                output = args.output_root / candidate["id"]
                manifest = {
                    "run_name": candidate["id"],
                    "trainer_global_step": 4693,
                    "planned_steps": 4693,
                    "pilot_rows": None,
                    "private_policy": "include",
                    "lineage": candidate["lineage"],
                    "rank": candidate["rank"],
                    "learning_rate": candidate["learning_rate"],
                    "campaign_config": {"sha256": args.expected_config_sha256},
                    "tokenization": {"train": {"rows": 300350}},
                    "base_lineage": {"observed": {"tree_sha256": "b" * 64}},
                    "scripts": {"train_lora_round2.py": "f" * 64},
                    "resume": {"requested": False},
                    "initial_adapter_receipt": None,
                    "initial_adapter_load": None,
                }
                if self.index == 2:
                    manifest["initial_adapter_receipt"] = {
                        "inventory": {"tree_sha256": "d" * 64},
                        "training_base_tree_sha256": "b" * 64,
                        "training_manifest_sha256": "e" * 64,
                    }
                    manifest["initial_adapter_load"] = {
                        "operation": "copy_exact_adapter_tensors_once_no_merge",
                        "exact_source_values_loaded": True,
                        "source_tensor_sha256": "c" * 64,
                        "loaded_tensor_sha256": "c" * 64,
                        "source_tree_sha256_before": "d" * 64,
                        "source_tree_sha256_after": "d" * 64,
                    }
                if self.index == corrupt_stage:
                    manifest["tokenization"]["train"]["rows"] = 20000
                write(output / "training-manifest.json", manifest)
                write(
                    output / "COMPLETED.json",
                    {
                        "run_name": candidate["id"],
                        "training_manifest_sha256": queue.sha256_file(
                            output / "training-manifest.json"
                        ),
                    },
                )
            return self.returncode

        def poll(self):
            return self.returncode

    monkeypatch.setattr(queue.subprocess, "Popen", Process)


def test_queue_runs_exact_order_and_records_proof(setup, monkeypatch):
    args, _, calls = setup
    install_process(monkeypatch, setup)
    result = queue.run_queue(args)
    assert result["state"] == "complete"
    assert [command[command.index("--candidate-id") + 1] for command in calls] == list(
        queue.CANDIDATES
    )
    assert all(
        command[command.index("--expected-config-sha256") + 1] == "a" * 64 for command in calls
    )
    assert "--initial-adapter" not in calls[0]
    assert calls[1][calls[1].index("--initial-adapter") + 1] == str(args.initial_adapter)
    assert all("--resume-from-checkpoint" not in command for command in calls)
    assert result["stages"][0]["training_rows"] == 300350
    assert len(result["stages"][1]["training_manifest_sha256"]) == 64
    assert (args.queue_dir / "stage-1-started.json").exists()
    assert (args.queue_dir / "stage-2-exit.json").exists()
    assert json.loads((args.queue_dir / "status.json").read_text())["state"] == "complete"


@pytest.mark.parametrize("candidate_index", [0, 1])
def test_existing_run_preserved_without_process_launch(setup, monkeypatch, candidate_index):
    args, candidates, calls = setup
    output = args.output_root / candidates[candidate_index]["id"]
    output.mkdir(parents=True)
    (output / "RUNNING.json").write_text("existing healthy work")
    install_process(monkeypatch, setup)
    with pytest.raises(FileExistsError, match="preserved"):
        queue.run_queue(args)
    assert calls == []
    assert (output / "RUNNING.json").read_text() == "existing healthy work"


def test_existing_queue_lock_is_never_reused(setup, monkeypatch):
    args, _, calls = setup
    args.queue_dir.mkdir()
    (args.queue_dir / "sentinel").write_text("original")
    install_process(monkeypatch, setup)
    with pytest.raises(FileExistsError):
        queue.run_queue(args)
    assert calls == []
    assert (args.queue_dir / "sentinel").read_text() == "original"


@pytest.mark.parametrize("kind", ["exit", "incomplete", "timeout"])
def test_queue_stops_first_failure_without_retry(setup, monkeypatch, kind):
    args, _, calls = setup
    install_process(
        monkeypatch,
        setup,
        fail_stage=1 if kind == "exit" else None,
        corrupt_stage=1 if kind == "incomplete" else None,
        timeout_stage=1 if kind == "timeout" else None,
    )
    with pytest.raises((RuntimeError, subprocess.TimeoutExpired)):
        queue.run_queue(args)
    assert len(calls) == 1
    failed = json.loads((args.queue_dir / "FAILED.json").read_text())
    assert failed["automatic_retry"] is False
    assert failed["child_pid_preserved"] == (1001 if kind == "timeout" else None)
    assert not (args.output_root / queue.CANDIDATES[1]).exists()
    assert not (args.queue_dir / "COMPLETED.json").exists()


def test_gpu_busy_between_stages_stops_without_interference(setup, monkeypatch):
    args, _, calls = setup
    install_process(monkeypatch, setup)
    checks = []

    def idle(_gpu):
        checks.append(1)
        if len(checks) == 2:
            raise RuntimeError("another healthy process occupies GPU; preserved")
        return {"stdout": ""}

    monkeypatch.setattr(queue, "check_gpu_idle", idle)
    with pytest.raises(RuntimeError, match="preserved"):
        queue.run_queue(args)
    assert len(calls) == 1
    failed = json.loads((args.queue_dir / "FAILED.json").read_text())
    assert len(failed["completed_stages"]) == 1


@pytest.mark.parametrize("returncode,stdout", [(0, ""), (0, "123, python\n"), (1, "")])
def test_gpu_probe_fails_closed(monkeypatch, returncode, stdout):
    monkeypatch.setattr(
        queue.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            returncode=returncode, stdout=stdout, stderr="probe error" if returncode else ""
        ),
    )
    if returncode or stdout:
        with pytest.raises(RuntimeError):
            queue.check_gpu_idle(0)
    else:
        assert queue.check_gpu_idle(0)["stdout"] == ""


def test_no_arbitrary_candidate_in_oracle_queue(setup):
    with pytest.raises(ValueError, match="only accepts"):
        queue.launch_command(setup[0], "full-best-warm-private-enriched")


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_receipt",
        "missing_load",
        "wrong_base",
        "wrong_source",
        "checkpoint_resume",
        "wrong_tensors",
        "changed_source_after",
        "fresh_has_initializer",
    ],
)
def test_completed_stage_requires_correct_initializer_proof(setup, monkeypatch, mutation):
    args, candidates, _ = setup
    install_process(monkeypatch, setup)
    queue.run_queue(args)
    candidate = candidates[0 if mutation == "fresh_has_initializer" else 1]
    output = args.output_root / candidate["id"]
    manifest = json.loads((output / "training-manifest.json").read_text())
    if mutation == "missing_receipt":
        del manifest["initial_adapter_receipt"]
    elif mutation == "missing_load":
        del manifest["initial_adapter_load"]
    elif mutation == "wrong_base":
        manifest["initial_adapter_receipt"]["training_base_tree_sha256"] = "0" * 64
    elif mutation == "wrong_source":
        manifest["initial_adapter_receipt"]["training_manifest_sha256"] = "0" * 64
    elif mutation == "checkpoint_resume":
        manifest["initial_adapter_load"] = {
            "operation": "defer_to_own_stage_checkpoint",
            "pilot_weights_loaded": False,
        }
    elif mutation == "wrong_tensors":
        manifest["initial_adapter_load"]["loaded_tensor_sha256"] = "0" * 64
    elif mutation == "changed_source_after":
        manifest["initial_adapter_load"]["source_tree_sha256_after"] = "0" * 64
    else:
        manifest["initial_adapter_receipt"] = {"inventory": {"tree_sha256": "d" * 64}}
    write(output / "training-manifest.json", manifest)
    write(
        output / "COMPLETED.json",
        {
            "run_name": candidate["id"],
            "training_manifest_sha256": queue.sha256_file(output / "training-manifest.json"),
        },
    )
    with pytest.raises(RuntimeError, match="initializer"):
        queue.completed_stage(
            output, candidate, args.expected_config_sha256, json.loads(args.config.read_text())
        )


def test_gpu_lock_excludes_different_output_roots(setup, monkeypatch):
    args, _, calls = setup
    install_process(monkeypatch, setup)
    descriptor = queue.acquire_gpu_lock(0)
    original = queue.gpu_lock_path(0).read_bytes()
    try:
        with pytest.raises(RuntimeError, match="GPU lock"):
            queue.run_queue(args)
        assert calls == []
        assert queue.gpu_lock_path(0).read_bytes() == original
    finally:
        os.close(descriptor)


def test_inherited_gpu_lock_survives_parent_descriptor_close(setup):
    descriptor = queue.acquire_gpu_lock(0)
    child_copy = os.dup(descriptor)
    os.close(descriptor)
    try:
        with pytest.raises(RuntimeError, match="GPU lock"):
            queue.acquire_gpu_lock(0)
    finally:
        os.close(child_copy)
    subsequent = queue.acquire_gpu_lock(0)
    os.close(subsequent)
