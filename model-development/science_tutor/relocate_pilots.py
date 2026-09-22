"""Bounded P2/P3 Oracle relocation; the executed pilots-v1 release is immutable.

Only cancel-pending mutates Slurm, and only for two exact PENDING job IDs.
Materialize is local/CPU-only. Launch needs verified cancellation evidence.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import pwd
import shlex
import signal
import sys
import time
import traceback
from pathlib import Path

try:
    from . import pilot_launch as pilot
except ImportError:
    import pilot_launch as pilot

train = pilot.train
JOBS = {"muta_fresh": "35822349", "pilot_adapter": "35822350"}
ORIGINAL_SHA = "1e5130d7583951eadbb14fc958935a30a3638070e49bdb03c60bc8a048cb1c11"
PILOT_SHA = "05f9a1e766e711f8998f188096eea5398fe1c34349629547a5754a3053edc41d"
RELEASE_NAME = "pilots-oracle-relocation-v1"
SOURCE_NAMES = pilot.SOURCE_NAMES | {"relocate_pilots.py"}


def source_hashes():
    sources = pilot.source_hashes()
    if sources["pilot_launch.py"] != PILOT_SHA:
        raise train.AdmissionError("frozen qualification/launch helper changed")
    sources["relocate_pilots.py"] = train.sha256_file(__file__)
    return sources


def original_bundle(path):
    path = Path(path)
    train.verify_ref({"path": str(path.absolute() / "campaign.json"), "sha256": ORIGINAL_SHA})
    manifest = train.read_json(path / "campaign.json")
    configs = {}
    for kind in JOBS:
        local = path / "configs" / f"{kind}.json"
        train.verify_ref(
            {"path": str(local.absolute()), "sha256": manifest["runs"][kind]["config"]["sha256"]}
        )
        configs[kind] = train.read_json(local)
    return manifest, configs


def oracle_host(original):
    host = copy.deepcopy(original["hosts"]["oracle"])
    for field in ("release", "runs", "control"):
        host[field] = str(Path(host[field]).with_name(RELEASE_NAME))
    return host


def relocated_config(original, config, kind):
    host = oracle_host(original)
    result = copy.deepcopy(config)
    result["run_id"] += "-oracle-relocation"
    result["output"] = str(Path(host["runs"]) / result["run_id"])
    result["gpu_lock"] = pilot.calibrate.GPU_LOCK
    for name, ref in result["data"].items():
        ref["path"] = str(Path(host["data"]) / Path(config["data"][name]["path"]).name)
    init = result["initialization"]
    init["base"]["path"] = host["muta_base"]
    init["tokenizer"]["path"] = host["tokenizer"]
    if kind == "pilot_adapter":
        init["adapter"]["path"] = host["pilot_adapter"]
    train.validate_config(result)
    return result


def materialize(args):
    original, configs = original_bundle(args.original_bundle)
    sources = source_hashes()
    if {name: sources[name] for name in pilot.SOURCE_NAMES} != original["source_sha256"]:
        raise train.AdmissionError("snapshot sources differ from executed original release")
    host = oracle_host(original)
    output = Path(args.output).absolute()
    output.mkdir(parents=True, exist_ok=False)
    for name in sorted(SOURCE_NAMES):
        target = output / "sources" / name
        target.parent.mkdir(exist_ok=True)
        with target.open("xb") as handle:
            handle.write(Path(__file__).with_name(name).read_bytes())
    # Preserve the exact original JSON bytes, including formatting, for pinned hashes.
    for relative in ["campaign.json", *(f"configs/{kind}.json" for kind in JOBS)]:
        target = output / "original" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write((Path(args.original_bundle) / relative).read_bytes())
    runs = {}
    for kind, cfg in configs.items():
        relocated = relocated_config(original, cfg, kind)
        target = output / "configs" / f"{kind}.json"
        train.write_new(target, relocated)
        runs[kind] = {
            "host": "oracle",
            "config": {
                "path": str(Path(host["release"]) / "configs" / target.name),
                "sha256": train.sha256_file(target),
            },
            "control": str(Path(host["control"]) / relocated["run_id"]),
        }
    manifest = {
        "schema_version": 1,
        "scope": "pending P2 and P3 only; same treatment, new Oracle paths",
        "original_campaign_sha256": ORIGINAL_SHA,
        "cancelled_jobs_required": JOBS,
        "source_sha256": sources,
        "hosts": {"oracle": host},
        "runs": runs,
    }
    train.write_new(output / "relocation.json", manifest)
    if source_hashes() != sources:
        raise train.AdmissionError("source changed during materialization")
    original_bundle(output / "original")
    for name, sha in sources.items():
        if train.sha256_file(output / "sources" / name) != sha:
            raise train.AdmissionError("copied source hash mismatch")
    receipt = {
        "status": "materialized_not_launched",
        "manifest_sha256": train.sha256_file(output / "relocation.json"),
        "inventory": train.tree_receipt(output),
    }
    train.write_new(output / "BUNDLE.json", receipt)
    for target in output.rglob("*"):
        if target.is_file():
            target.chmod(0o444)
    return receipt


def pending_details(text, kind, original):
    details = dict(field.split("=", 1) for field in shlex.split(text) if "=" in field)
    config_path = original["runs"][kind]["config"]["path"]
    expected_command = str(Path(config_path).parent.parent / "jobs" / f"{kind}.sbatch")
    if (
        details.get("JobId") != JOBS[kind]
        or details.get("JobState") != "PENDING"
        or details.get("UserId", "").split("(")[0] != "ein21"
        or details.get("Account") != pilot.ACCOUNT
        or details.get("JobName") != "science-pilot-" + kind.replace("_", "-") + "-v1"
        or details.get("Command") != expected_command
        or details.get("RunTime") != "00:00:00"
        or details.get("Restarts", "0") != "0"
    ):
        raise train.AdmissionError(
            "exact original job is not pristine PENDING; cancellation refused"
        )
    return details


def terminal_jobs(raw):
    rows = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        fields = line.strip().rstrip("|").split("|")
        if len(fields) != 5 or fields[0] not in JOBS.values() or fields[0] in rows:
            raise train.AdmissionError("unexpected, duplicate or step accounting row")
        job, state, start, end, elapsed = fields
        if (
            state.split()[0] != "CANCELLED"
            or start not in {"Unknown", "None", "N/A"}
            or elapsed != "0"
            or end in {"Unknown", "None", "N/A", ""}
        ):
            raise train.AdmissionError("job is not terminal CANCELLED without ever starting")
        rows[job] = {"state": state, "start": start, "end": end, "elapsed_raw": elapsed}
    if set(rows) != set(JOBS.values()):
        raise train.AdmissionError("missing terminal cancellation accounting")
    return rows


def cancel_pending(args):
    original, _ = original_bundle(args.original_bundle)
    if pwd.getpwuid(os.getuid()).pw_name != "ein21":
        raise train.AdmissionError("cancellation must run as CSD3 ein21")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    evidence = {
        "schema_version": 1,
        "original_campaign_sha256": ORIGINAL_SHA,
        "jobs": JOBS,
        "before": {},
        "command": ["scancel", "--state=PENDING", *JOBS.values()],
    }
    try:
        for kind, job in JOBS.items():
            raw = pilot.command(["scontrol", "show", "job", "-o", job])
            evidence["before"][kind] = raw
            pending_details(raw, kind, original)
        train.write_new(output / "REQUEST.json", evidence)
        evidence["scancel_stdout"] = pilot.command(evidence["command"])
        # Accounting can lag. Every attempt is retained and the wait is bounded.
        for attempt in range(15):
            raw = pilot.command(
                [
                    "sacct",
                    "-n",
                    "-P",
                    "-j",
                    ",".join(JOBS.values()),
                    "--format=JobIDRaw,State,Start,End,ElapsedRaw",
                ]
            )
            train.write_new(output / f"accounting-{attempt:02d}.json", {"stdout": raw})
            try:
                evidence["terminal_jobs"] = terminal_jobs(raw)
                break
            except train.AdmissionError:
                if attempt == 14:
                    raise
                time.sleep(2)
        evidence.update(status="cancelled_pending_only", terminal_stdout=raw, time_unix=time.time())
        train.write_new(output / "COMPLETED.json", evidence)
        return train.file_receipt(output / "COMPLETED.json")
    except BaseException as exc:
        train.write_new(
            output / "FAILED.json",
            {"error": str(exc), "evidence": evidence, "automatic_retry": False},
        )
        raise


def verify_cancellation(ref, original):
    receipt = train.verify_ref(ref)
    result = train.read_json(ref["path"])
    if (
        result.get("status") != "cancelled_pending_only"
        or result.get("schema_version") != 1
        or result.get("original_campaign_sha256") != ORIGINAL_SHA
        or result.get("jobs") != JOBS
        or result.get("command") != ["scancel", "--state=PENDING", *JOBS.values()]
        or set(result.get("before", {})) != set(JOBS)
    ):
        raise train.AdmissionError("cancellation receipt identity mismatch")
    for kind in JOBS:
        pending_details(result["before"][kind], kind, original)
    if terminal_jobs(result["terminal_stdout"]) != result.get("terminal_jobs"):
        raise train.AdmissionError("terminal cancellation evidence differs")
    return receipt


def load_run(args):
    ref = train.verify_ref(
        {"path": str(Path(args.manifest).absolute()), "sha256": args.manifest_sha256}
    )
    manifest = train.read_json(ref["path"])
    release = Path(ref["path"]).parent
    original, configs = original_bundle(release / "original")
    host = oracle_host(original)
    if (
        manifest.get("schema_version") != 1
        or manifest.get("original_campaign_sha256") != ORIGINAL_SHA
        or manifest.get("cancelled_jobs_required") != JOBS
        or manifest.get("hosts") != {"oracle": host}
        or set(manifest.get("runs", {})) != set(JOBS)
        or manifest.get("source_sha256") != source_hashes()
        or release.resolve() != Path(host["release"]).resolve()
        or Path(__file__).resolve() != (release / "sources/relocate_pilots.py").resolve()
        or os.getuid() != 1000
        or Path(sys.executable).resolve() != Path(host["python"]).resolve()
    ):
        raise train.AdmissionError("relocation release/source/Oracle identity mismatch")
    run = manifest["runs"][args.kind]
    expected = relocated_config(original, configs[args.kind], args.kind)
    expected_path = str(release / "configs" / f"{args.kind}.json")
    if (
        run.get("host") != "oracle"
        or run.get("control") != str(Path(host["control"]) / expected["run_id"])
        or run["config"]["path"] != expected_path
    ):
        raise train.AdmissionError("relocated output/config/control path mismatch")
    config_ref = train.verify_ref(run["config"])
    config = train.read_json(expected_path)
    if config != expected:
        raise train.AdmissionError("relocation changed the frozen treatment")
    cancellation_ref = verify_cancellation(
        {"path": str(Path(args.cancellation).absolute()), "sha256": args.cancellation_sha256},
        original,
    )
    return (
        manifest,
        run,
        host,
        config,
        {"manifest": ref, "config": config_ref, "cancellation": cancellation_ref},
    )


def exact_inventory(root, inventory, *, excluded=()):
    observed = train.tree_receipt(root)
    files = [row for row in observed["files"] if row["path"] not in excluded]
    expected = inventory["files"]
    digest = train.hashlib.sha256(
        "\n".join(f"{row['sha256']}  {row['path']}" for row in files).encode()
    ).hexdigest()
    if (
        inventory.get("root") != str(Path(root).resolve())
        or files != expected
        or inventory.get("tree_sha256") != digest
        or inventory.get("file_count") != len(files)
        or inventory.get("bytes") != sum(row["bytes"] for row in files)
    ):
        raise train.AdmissionError("terminal evidence inventory mismatch")


def terminal_schedule(config, config_sha, sources, result):
    output = Path(config["output"])
    for name in ("resolved_config", "metrics"):
        ref = result[name]
        path = Path(ref["path"])
        if (name == "resolved_config" and path != output / "resolved-config.json") or (
            name == "metrics"
            and (path.parent != output / "attempts" or not path.name.endswith("-metrics.jsonl"))
        ):
            raise train.AdmissionError("terminal evidence reference escapes this run")
        train.verify_ref(ref)
    resolved = train.read_json(result["resolved_config"]["path"])
    if (
        resolved["config"] != config
        or resolved["config_file"]["sha256"] != config_sha
        or {name: ref["sha256"] for name, ref in resolved["sources"].items()} != sources
    ):
        raise train.AdmissionError("resolved trainer config/source mismatch")
    prepared = resolved["prepared"]
    original, _ = original_bundle(Path(__file__).resolve().parent.parent / "original")
    frozen = original["prepared"]
    if any(
        prepared["data"][key]["sha256"] != ref["sha256"] for key, ref in config["data"].items()
    ) or any(
        prepared["schedule"].get(key) != value
        for key, value in frozen["schedule"].items()
        if key != "max_steps"
    ):
        raise train.AdmissionError("resolved dataset/schedule differs from frozen campaign")
    rows = [row for row in prepared["row_receipts"] if row["split"] == "train"]
    order, receipt = train.deterministic_schedule(
        rows, seed=config["training"]["seed"], effective_batch_size=64, max_steps=126
    )
    if any(prepared["schedule"].get(key) != value for key, value in receipt.items()) or any(
        type(row["trainable_tokens"]) is not int or row["trainable_tokens"] <= 0 for row in rows
    ):
        raise train.AdmissionError("resolved row schedule mismatch")
    totals = {
        step: sum(rows[index]["trainable_tokens"] for index in order[(step - 1) * 64 : step * 64])
        for step in range(1, 127)
    }
    cumulative, budget = {}, 0
    for step, tokens in totals.items():
        budget += tokens
        cumulative[step] = budget
    if budget != config["training"]["expected_trainable_tokens"]:
        raise train.AdmissionError("resolved rows differ from frozen token budget")
    metrics = [
        json.loads(line) for line in Path(result["metrics"]["path"]).read_text().splitlines()
    ]
    steps = [row for row in metrics if row.get("kind") == "train_step"]
    if [row["step"] for row in steps] != list(totals) or any(
        row["trainable_tokens"] != totals[row["step"]]
        or row["cumulative_trainable_tokens"] != cumulative[row["step"]]
        or row["effective_rows"] != 64
        for row in steps
    ):
        raise train.AdmissionError("training metrics differ from resolved schedule")
    return cumulative


def verify_terminal(config, config_sha, sources):
    output = Path(config["output"])
    ref = train.file_receipt(output / "COMPLETED.json")
    result = train.read_json(ref["path"])
    trainer_sources = {name: sources[name] for name in ("train.py", "tokenization.py")}
    milestones = [config["training"]["max_steps"] // 2, config["training"]["max_steps"]]
    if (
        result.get("status") != "complete"
        or result.get("run_id") != config["run_id"]
        or result.get("config_sha256") != config_sha
        or result.get("source_sha256") != trainer_sources
        or result.get("completed_steps") != milestones[-1]
        or result.get("consumed_trainable_tokens")
        != config["training"]["expected_trainable_tokens"]
        or result.get("resumed_from_step") != 0
        or result.get("milestones") != milestones
    ):
        raise train.AdmissionError("trainer terminal identity mismatch")
    exact_inventory(output, result["run_inventory"], excluded=("COMPLETED.json",))
    token_budget = terminal_schedule(config, config_sha, trainer_sources, result)
    if {p.name for p in (output / "checkpoints").iterdir()} != {
        f"checkpoint-{step}" for step in milestones
    }:
        raise train.AdmissionError("unexpected/partial checkpoint")
    inventories = result["all_checkpoints"]
    if len(inventories) != 2 or result["session_checkpoints"] != inventories:
        raise train.AdmissionError("fresh run checkpoint inventory mismatch")
    for step, inventory in zip(milestones, inventories, strict=True):
        checkpoint = output / "checkpoints" / f"checkpoint-{step}"
        if inventory["root"] != str(checkpoint.resolve()):
            raise train.AdmissionError("checkpoint inventory path mismatch")
        exact_inventory(checkpoint, inventory)
        required = {
            "adapter_model.safetensors",
            "adapter_config.json",
            "training-state.pt",
            "state.json",
            "COMPLETE.json",
        }
        names = {row["path"] for row in inventory["files"]}
        if (
            not required <= names
            or names - required - {"README.md"}
            or any(row["bytes"] <= 0 for row in inventory["files"])
        ):
            raise train.AdmissionError("missing or unexpected checkpoint artifacts")
        seal = train.read_json(checkpoint / "COMPLETE.json")
        state = train.read_json(checkpoint / "state.json")
        if (
            seal.get("step") != step
            or state.get("step") != step
            or seal.get("consumed_trainable_tokens") != token_budget[step]
            or state.get("consumed_trainable_tokens") != token_budget[step]
            or seal.get("config_sha256") != config_sha
            or seal.get("source_sha256") != trainer_sources
            or seal.get("files") != [r for r in inventory["files"] if r["path"] != "COMPLETE.json"]
        ):
            raise train.AdmissionError("checkpoint seal mismatch")
    return ref


def qualify(args):
    # Only the admission loader changes. Frozen numerical qualification code is reused.
    pilot.load_run = load_run
    return pilot.qualify(args)


def launch(args):
    manifest, run, host, config, refs = load_run(args)
    control = Path(run["control"])
    control.mkdir(parents=True, exist_ok=False)
    try:
        if Path(config["output"]).exists():
            raise train.AdmissionError("pilot output exists; no retry/resume")
        train.write_new(
            control / "REQUEST.json",
            {
                "refs": refs,
                "source_sha256": manifest["source_sha256"],
                "pid": os.getpid(),
                "time_unix": time.time(),
            },
        )
        train.write_new(control / "host-before.json", pilot.allocation_snapshot("oracle"))
        command = [
            host["python"],
            str(Path(__file__).resolve()),
            "qualify",
            "--manifest",
            refs["manifest"]["path"],
            "--manifest-sha256",
            refs["manifest"]["sha256"],
            "--kind",
            args.kind,
            "--cancellation",
            refs["cancellation"]["path"],
            "--cancellation-sha256",
            refs["cancellation"]["sha256"],
        ]
        pilot.child(command, control / "qualification.stdout.log")
        qualification_ref = train.file_receipt(control / "qualification/COMPLETED.json")
        qualification = train.read_json(qualification_ref["path"])
        required = {
            "status": "qualified",
            "config_sha256": refs["config"]["sha256"],
            "source_sha256": manifest["source_sha256"],
            "weights_saved": False,
            "candidate_state_reused": False,
            "memory_headroom_passed": True,
            "optimizer_step_executed": True,
            "diagnostic_adapter_changed": True,
            "effective_rows": 64,
            "microbatch": 4,
            "optimizer": "torch.optim.AdamW",
            "dataset_sha256": {name: value["sha256"] for name, value in config["data"].items()},
        }
        if (
            any(qualification.get(key) != value for key, value in required.items())
            or qualification.get("optimizer_state_bytes", 0) <= 0
        ):
            raise train.AdmissionError("disposable qualification receipt mismatch")
        snapshot = pilot.allocation_snapshot("oracle")
        if snapshot["gpu"]["uuid"] != qualification["gpu"]["uuid"]:
            raise train.AdmissionError("GPU changed after qualification")
        load_run(args)
        train.write_new(
            control / "training-admission.json",
            {
                "qualification": qualification_ref,
                "host": snapshot,
                "refs": refs,
                "source_sha256": manifest["source_sha256"],
            },
        )
        pilot.child(
            [
                host["python"],
                str(Path(__file__).with_name("train.py")),
                "--config",
                refs["config"]["path"],
                "--config-sha256",
                refs["config"]["sha256"],
            ],
            control / "training.stdout.log",
        )
        completed_ref = verify_terminal(config, refs["config"]["sha256"], manifest["source_sha256"])
        load_run(args)
        result = {
            "status": "complete",
            "run_kind": args.kind,
            "refs": refs,
            "qualification": qualification_ref,
            "trainer_completion": completed_ref,
            "host_after": pilot.allocation_snapshot("oracle"),
            "inventory": train.tree_receipt(control),
        }
        train.write_new(control / "COMPLETED.json", result)
        return result
    except BaseException as exc:
        train.write_new(
            control / "FAILED.json",
            {
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "automatic_retry": False,
                "time_unix": time.time(),
            },
        )
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    for mode in ("materialize", "cancel-pending"):
        command = sub.add_parser(mode)
        command.add_argument("--original-bundle", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
    for mode in ("launch", "qualify"):
        command = sub.add_parser(mode)
        command.add_argument("--manifest", type=Path, required=True)
        command.add_argument("--manifest-sha256", required=True)
        command.add_argument("--cancellation", type=Path, required=True)
        command.add_argument("--cancellation-sha256", required=True)
        command.add_argument("--kind", choices=tuple(JOBS), required=True)
    args = parser.parse_args(argv)

    def stopped(signum, _frame):
        raise RuntimeError(f"received signal {signum}; no automatic retry")

    signal.signal(signal.SIGTERM, stopped)
    result = {
        "materialize": materialize,
        "cancel-pending": cancel_pending,
        "launch": launch,
        "qualify": qualify,
    }[args.mode](args)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
