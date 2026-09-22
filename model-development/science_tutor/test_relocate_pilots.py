"""CPU-only relocation safety checks; never invoke Slurm or a real GPU."""

import argparse
import copy
import json
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from science_tutor import relocate_pilots as relocation

train = relocation.train
ORIGINAL = Path(__file__).resolve().parents[2] / "provenance/science-tutor-20260919/pilots-v1"


def pending(kind, original, state="PENDING"):
    return " ".join(
        [
            f"JobId={relocation.JOBS[kind]}",
            f"JobState={state}",
            "UserId=ein21(49198)",
            f"Account={relocation.pilot.ACCOUNT}",
            f"JobName=science-pilot-{kind.replace('_', '-')}-v1",
            f"Command={original['hosts']['csd3']['release']}/jobs/{kind}.sbatch",
            "RunTime=00:00:00",
            "Restarts=0",
        ]
    )


def terminal():
    return "\n".join(
        f"{job}|CANCELLED by 49198|Unknown|2026-09-19T20:00:00|0|"
        for job in relocation.JOBS.values()
    )


def cancellation(original):
    return {
        "schema_version": 1,
        "status": "cancelled_pending_only",
        "original_campaign_sha256": relocation.ORIGINAL_SHA,
        "jobs": relocation.JOBS,
        "command": ["scancel", "--state=PENDING", *relocation.JOBS.values()],
        "before": {kind: pending(kind, original) for kind in relocation.JOBS},
        "terminal_stdout": terminal(),
        "terminal_jobs": relocation.terminal_jobs(terminal()),
    }


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    original, _ = relocation.original_bundle(ORIGINAL)
    host = relocation.oracle_host(original)
    host.update(
        release=str(tmp_path / "release"),
        runs=str(tmp_path / "runs"),
        control=str(tmp_path / "control"),
        python=sys.executable,
    )
    monkeypatch.setattr(relocation, "oracle_host", lambda _: copy.deepcopy(host))
    args = argparse.Namespace(original_bundle=ORIGINAL, output=tmp_path / "release")
    receipt = relocation.materialize(args)
    cancel_path = tmp_path / "cancellation.json"
    train.write_new(cancel_path, cancellation(original))
    monkeypatch.setattr(relocation, "__file__", str(args.output / "sources/relocate_pilots.py"))
    monkeypatch.setattr(relocation.os, "getuid", lambda: 1000)
    return argparse.Namespace(
        manifest=args.output / "relocation.json",
        manifest_sha256=receipt["manifest_sha256"],
        cancellation=cancel_path,
        cancellation_sha256=train.sha256_file(cancel_path),
        kind="muta_fresh",
    )


def rewrite(path, value):
    path = Path(path)
    path.chmod(0o644)
    path.write_text(json.dumps(value))


def test_snapshot_sources_and_original_configs_are_unchanged(bundle):
    manifest, _, _, config, refs = relocation.load_run(bundle)
    original, old = relocation.original_bundle(ORIGINAL)
    assert config["training"] == old[bundle.kind]["training"]
    assert config["lora"] == old[bundle.kind]["lora"]
    assert (
        config["initialization"]["base"]["tree_sha256"]
        == old[bundle.kind]["initialization"]["base"]["tree_sha256"]
    )
    assert manifest["source_sha256"] == relocation.source_hashes()
    assert refs["cancellation"]["sha256"] == bundle.cancellation_sha256
    for name, sha in original["source_sha256"].items():
        assert train.sha256_file(bundle.manifest.parent / "sources" / name) == sha
    bundle.kind = "pilot_adapter"
    _, _, _, config, _ = relocation.load_run(bundle)
    assert (
        config["initialization"]["adapter"]["tree_sha256"]
        == old[bundle.kind]["initialization"]["adapter"]["tree_sha256"]
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("learning_rate", 1e-5),
        ("micro_batch_size", 2),
        ("max_steps", 127),
        ("expected_trainable_tokens", 257342),
        ("seed", 3408),
    ],
)
def test_rehashed_numeric_change_is_rejected(bundle, field, value):
    manifest = train.read_json(bundle.manifest)
    ref = manifest["runs"][bundle.kind]["config"]
    config = train.read_json(ref["path"])
    config["training"][field] = value
    rewrite(ref["path"], config)
    ref["sha256"] = train.sha256_file(ref["path"])
    rewrite(bundle.manifest, manifest)
    bundle.manifest_sha256 = train.sha256_file(bundle.manifest)
    with pytest.raises(train.AdmissionError, match="frozen treatment"):
        relocation.load_run(bundle)


def test_cancellation_required_and_running_state_rejected(bundle):
    value = train.read_json(bundle.cancellation)
    value["before"]["muta_fresh"] = value["before"]["muta_fresh"].replace(
        "JobState=PENDING", "JobState=RUNNING"
    )
    rewrite(bundle.cancellation, value)
    bundle.cancellation_sha256 = train.sha256_file(bundle.cancellation)
    with pytest.raises(train.AdmissionError, match="PENDING"):
        relocation.load_run(bundle)


@pytest.mark.parametrize(
    "replacement",
    [
        ("CANCELLED by 49198", "RUNNING"),
        ("Unknown", "2026-09-19T19:59:58"),
        ("|0|", "|2|"),
        ("35822349|", "35822351|"),
    ],
)
def test_terminal_evidence_rejects_running_started_or_wrong_jobs(replacement):
    with pytest.raises(train.AdmissionError):
        relocation.terminal_jobs(terminal().replace(*replacement))


def test_cancel_uses_only_conditional_exact_ids(tmp_path, monkeypatch):
    original, _ = relocation.original_bundle(ORIGINAL)
    calls = []

    def command(argv):
        calls.append(argv)
        if argv[0] == "scontrol":
            kind = next(k for k, v in relocation.JOBS.items() if v == argv[-1])
            return pending(kind, original)
        if argv[0] == "sacct":
            return terminal()
        assert argv == ["scancel", "--state=PENDING", "35822349", "35822350"]
        return ""

    monkeypatch.setattr(relocation.pilot, "command", command)
    monkeypatch.setattr(
        relocation.pwd, "getpwuid", lambda _: types.SimpleNamespace(pw_name="ein21")
    )
    args = argparse.Namespace(original_bundle=ORIGINAL, output=tmp_path / "cancel")
    receipt = relocation.cancel_pending(args)
    relocation.verify_cancellation(receipt, original)
    assert sum(call[0] == "scancel" for call in calls) == 1
    with pytest.raises(FileExistsError):
        relocation.cancel_pending(args)
    assert sum(call[0] == "scancel" for call in calls) == 1


def test_running_job_is_never_cancelled(tmp_path, monkeypatch):
    original, _ = relocation.original_bundle(ORIGINAL)
    calls = []

    def command(argv):
        calls.append(argv)
        return pending("muta_fresh", original, "RUNNING")

    monkeypatch.setattr(relocation.pilot, "command", command)
    monkeypatch.setattr(
        relocation.pwd, "getpwuid", lambda _: types.SimpleNamespace(pw_name="ein21")
    )
    with pytest.raises(train.AdmissionError):
        relocation.cancel_pending(
            argparse.Namespace(original_bundle=ORIGINAL, output=tmp_path / "cancel")
        )
    assert all(call[0] == "scontrol" for call in calls)


def test_duplicate_launch_does_not_touch_gpu(bundle, monkeypatch):
    _, run, _, _, _ = relocation.load_run(bundle)
    Path(run["control"]).mkdir(parents=True)
    monkeypatch.setattr(
        relocation.pilot, "allocation_snapshot", lambda _: pytest.fail("GPU reached")
    )
    monkeypatch.setattr(relocation.pilot, "child", lambda *args: pytest.fail("child reached"))
    with pytest.raises(FileExistsError):
        relocation.launch(bundle)


def test_existing_output_rejected_before_gpu(bundle, monkeypatch):
    _, _, _, config, _ = relocation.load_run(bundle)
    Path(config["output"]).mkdir(parents=True)
    monkeypatch.setattr(
        relocation.pilot, "allocation_snapshot", lambda _: pytest.fail("GPU reached")
    )
    with pytest.raises(train.AdmissionError, match="output exists"):
        relocation.launch(bundle)


def fake_completed(config, config_sha, sources):
    output = Path(config["output"])
    inventories = []
    trainer_sources = {name: sources[name] for name in ("train.py", "tokenization.py")}
    resolved = train.read_json(ORIGINAL / "artifacts/upstream-fresh-v1/run/resolved-config.json")
    resolved.update(
        config=config,
        config_file={"sha256": config_sha},
        sources={name: {"sha256": sha} for name, sha in trainer_sources.items()},
    )
    train.write_new(output / "resolved-config.json", resolved)
    rows = [row for row in resolved["prepared"]["row_receipts"] if row["split"] == "train"]
    order, _ = train.deterministic_schedule(rows, seed=3407, effective_batch_size=64, max_steps=126)
    metrics, cumulative, consumed = [], {}, 0
    for step in range(1, 127):
        tokens = sum(
            rows[index]["trainable_tokens"] for index in order[(step - 1) * 64 : step * 64]
        )
        consumed += tokens
        cumulative[step] = consumed
        metrics.append(
            {
                "kind": "train_step",
                "step": step,
                "trainable_tokens": tokens,
                "cumulative_trainable_tokens": consumed,
                "effective_rows": 64,
            }
        )
    metrics_path = output / "attempts/fixture-metrics.jsonl"
    metrics_path.parent.mkdir()
    metrics_path.write_text("\n".join(json.dumps(row) for row in metrics))
    for step in (63, 126):
        checkpoint = output / "checkpoints" / f"checkpoint-{step}"
        train.write_new(
            checkpoint / "state.json", {"step": step, "consumed_trainable_tokens": cumulative[step]}
        )
        for name in ("adapter_model.safetensors", "adapter_config.json", "training-state.pt"):
            train.write_new(checkpoint / name, {"fixture": True})
        seal = {
            "step": step,
            "consumed_trainable_tokens": cumulative[step],
            "config_sha256": config_sha,
            "source_sha256": trainer_sources,
            "files": train.tree_receipt(checkpoint)["files"],
        }
        train.write_new(checkpoint / "COMPLETE.json", seal)
        inventories.append(train.tree_receipt(checkpoint))
    value = {
        "status": "complete",
        "run_id": config["run_id"],
        "config_sha256": config_sha,
        "source_sha256": trainer_sources,
        "completed_steps": 126,
        "consumed_trainable_tokens": 257341,
        "resumed_from_step": 0,
        "milestones": [63, 126],
        "all_checkpoints": inventories,
        "session_checkpoints": inventories,
        "resolved_config": train.file_receipt(output / "resolved-config.json"),
        "metrics": train.file_receipt(metrics_path),
        "run_inventory": train.tree_receipt(output),
    }
    train.write_new(output / "COMPLETED.json", value)


@pytest.mark.parametrize(
    "attack", [None, "extra", "tamper", "symlink", "missing", "forged_checkpoint_seal"]
)
def test_terminal_inventories(bundle, attack):
    manifest, _, _, config, refs = relocation.load_run(bundle)
    fake_completed(config, refs["config"]["sha256"], manifest["source_sha256"])
    output = Path(config["output"])
    if attack == "extra":
        train.write_new(output / "extra.json", {})
    elif attack == "tamper":
        (output / "checkpoints/checkpoint-63/state.json").write_text("changed")
    elif attack == "symlink":
        (output / "extra").symlink_to(output / "COMPLETED.json")
    elif attack == "missing":
        (output / "checkpoints/checkpoint-63/state.json").unlink()
    elif attack == "forged_checkpoint_seal":
        target = output / "COMPLETED.json"
        receipt = train.read_json(target)
        receipt["all_checkpoints"][0]["tree_sha256"] = "0" * 64
        rewrite(target, receipt)
    if attack is None:
        assert relocation.verify_terminal(
            config, refs["config"]["sha256"], manifest["source_sha256"]
        )["sha256"]
    else:
        with pytest.raises(train.AdmissionError):
            relocation.verify_terminal(config, refs["config"]["sha256"], manifest["source_sha256"])


@pytest.mark.parametrize("attack", ["missing_adapter", "wrong_halfway_tokens", "wrong_metrics"])
def test_resealed_terminal_incompleteness_is_rejected(bundle, attack):
    manifest, _, _, config, refs = relocation.load_run(bundle)
    fake_completed(config, refs["config"]["sha256"], manifest["source_sha256"])
    output = Path(config["output"])
    completed = train.read_json(output / "COMPLETED.json")
    checkpoint = output / "checkpoints/checkpoint-63"
    if attack == "missing_adapter":
        (checkpoint / "adapter_model.safetensors").unlink()
    elif attack == "wrong_halfway_tokens":
        state = train.read_json(checkpoint / "state.json")
        state["consumed_trainable_tokens"] += 1
        rewrite(checkpoint / "state.json", state)
    else:
        metrics = Path(completed["metrics"]["path"])
        value = [json.loads(line) for line in metrics.read_text().splitlines()]
        value[62]["cumulative_trainable_tokens"] += 1
        metrics.write_text("\n".join(json.dumps(row) for row in value))
        completed["metrics"] = train.file_receipt(metrics)
    seal = train.read_json(checkpoint / "COMPLETE.json")
    seal["files"] = [
        row for row in train.tree_receipt(checkpoint)["files"] if row["path"] != "COMPLETE.json"
    ]
    rewrite(checkpoint / "COMPLETE.json", seal)
    inventories = [
        train.tree_receipt(output / "checkpoints" / f"checkpoint-{step}") for step in (63, 126)
    ]
    completed.update(all_checkpoints=inventories, session_checkpoints=inventories)
    (output / "COMPLETED.json").unlink()
    completed["run_inventory"] = train.tree_receipt(output)
    train.write_new(output / "COMPLETED.json", completed)
    with pytest.raises(train.AdmissionError):
        relocation.verify_terminal(config, refs["config"]["sha256"], manifest["source_sha256"])
