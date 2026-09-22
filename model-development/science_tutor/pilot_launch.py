"""Materialize immutable matched pilots; explicitly qualify and launch one later.

No SSH, sbatch submission, automatic retries, downloads, resume or promotion.
The materialize mode is CPU-only and does not copy training text or model files.
"""

from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import json
import math
import os
import pwd
import re
import shlex
import signal
import subprocess
import sys
import time
import traceback
from contextlib import contextmanager
from pathlib import Path

try:
    from . import calibrate, train
    from .tokenization import tokenize_messages
except ImportError:
    import calibrate
    import train
    from tokenization import tokenize_messages


KINDS = ("upstream_fresh", "muta_fresh", "pilot_adapter")
PLACEMENT = {"upstream_fresh": "oracle", "muta_fresh": "csd3", "pilot_adapter": "csd3"}
FROZEN = {
    "train.py": "a800ca3bf599b234c4fa61f50a37b0638496269bd811a6656598cf5543291bd0",
    "tokenization.py": "93d251a9b0394cf9033622386ebbb352a3393cbe516f985795c5289f2a85bfd4",
    "calibrate.py": "1dbbfd2072516d39c60ac4ab90be03e8f23b4215f5a1da44aef3ed2745119a57",
}
SOURCE_NAMES = set(FROZEN) | {"pilot_launch.py"}
ACCOUNT = "mlmi-ein21-sl2-gpu"
PARTITION = "ampere"
WALL_SECONDS = 110 * 60
HOST_ROOTS = {
    "oracle": "/lambda/nfs/awf-tmp/muta/campaign-20260918/science-tutor-20260919",
    "csd3": "/rds/user/ein21/hpc-work/muta-round2/science-tutor-20260919",
}


def source_hashes():
    result = {
        name: train.file_receipt(Path(__file__).with_name(name))["sha256"]
        for name in sorted(SOURCE_NAMES)
    }
    if any(result[name] != sha for name, sha in FROZEN.items()):
        raise train.AdmissionError(
            "previously reviewed trainer/tokenizer/calibration source changed"
        )
    return result


def validate_spec(spec):
    if (
        set(spec)
        != {
            "schema_version",
            "repository_head_commit",
            "data",
            "tokenizer",
            "hosts",
            "microbatches",
        }
        or spec["schema_version"] != 1
    ):
        raise train.AdmissionError("unexpected pilot materialization spec")
    if not re.fullmatch(r"[0-9a-f]{40}", spec["repository_head_commit"]):
        raise train.AdmissionError("actual repository HEAD commit is required")
    if (
        set(spec["data"]) != {"train", "dev", "admission"}
        or set(spec["hosts"]) != {"oracle", "csd3"}
        or set(spec["microbatches"]) != set(KINDS)
    ):
        raise train.AdmissionError("exact train/dev/admission, two hosts and three pilots required")
    if len({Path(ref["path"]).name for ref in spec["data"].values()}) != 3:
        raise train.AdmissionError("staged input filenames must be distinct")
    for value in spec["microbatches"].values():
        if type(value) is not int or value not in (1, 2, 4):
            raise train.AdmissionError(
                "microbatch must be an explicitly qualified choice of 1, 2 or 4"
            )
    fields = {
        "release",
        "data",
        "tokenizer",
        "runs",
        "control",
        "python",
        "upstream_base",
        "muta_base",
        "pilot_adapter",
        "uid",
    }
    for name, host in spec["hosts"].items():
        if set(host) != fields or type(host["uid"]) is not int or host["uid"] < 1:
            raise train.AdmissionError("missing exact host path/UID descriptor")
        if name == "oracle" and host["uid"] != 1000:
            raise train.AdmissionError("Oracle UID must be 1000")
        for key in fields - {"uid"}:
            if not isinstance(host[key], str) or not Path(host[key]).is_absolute():
                raise train.AdmissionError("host paths must be explicit absolute paths")
        for key in ("release", "runs", "control"):
            if not Path(host[key]).is_relative_to(HOST_ROOTS[name]) or Path(host[key]) == Path(
                HOST_ROOTS[name]
            ):
                raise train.AdmissionError(
                    "new outputs/releases must remain in the new campaign namespace"
                )
        if len({host[key] for key in ("release", "runs", "control")}) != 3:
            raise train.AdmissionError("source, run and control directories must be separate")
        paths = [Path(host[key]) for key in ("release", "runs", "control")]
        if any(
            first.is_relative_to(second) for first in paths for second in paths if first != second
        ):
            raise train.AdmissionError("source, run and control trees cannot nest")


def admitted_schedule(spec):
    refs = {name: train.verify_ref(ref) for name, ref in spec["data"].items()}
    admission = train.read_json(spec["data"]["admission"]["path"])
    if (
        admission.get("schema_version") != 1
        or admission.get("status") != "admitted"
        or admission.get("group_disjoint") is not True
        or admission.get("overlength_policy") != "excluded_before_freeze"
    ):
        raise train.AdmissionError("a real, reviewed dataset admission is required")
    raw = {name: train.load_rows(spec["data"][name]["path"]) for name in ("train", "dev")}
    for name, rows in raw.items():
        expected = {
            "sha256": refs[name]["sha256"],
            "rows": len(rows),
            "row_ids_sha256": train.digest(sorted(row["id"] for row in rows)),
        }
        if any(admission.get(name, {}).get(key) != value for key, value in expected.items()):
            raise train.AdmissionError("dataset admission binding mismatch")
    for key in ("id", "group_id"):
        if {row[key] for row in raw["train"]} & {row[key] for row in raw["dev"]}:
            raise train.AdmissionError("train/dev identity or conversation group overlap")
    tokenizer_ref = train.verify_ref(spec["tokenizer"], tree=True)
    observed = {item["path"]: item["sha256"] for item in tokenizer_ref["files"]}
    if any(observed.get(key) != value for key, value in train.TOKENIZER_FILES.items()):
        raise train.AdmissionError("common upstream tokenizer bytes differ")
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        spec["tokenizer"]["path"], local_files_only=True, trust_remote_code=False
    )
    tokens = {
        name: [
            tokenize_messages(row["messages"], tokenizer=tokenizer, max_length=4096) for row in rows
        ]
        for name, rows in raw.items()
    }
    if len(raw["train"]) < 64:
        raise train.AdmissionError("qualification requires at least one real effective batch")
    steps = math.ceil(len(raw["train"]) / 64)
    order, receipt = train.deterministic_schedule(
        raw["train"], seed=3407, effective_batch_size=64, max_steps=steps
    )
    budget = sum(tokens["train"][index]["trainable_tokens"] for index in order)
    counts = {
        name: {
            "rows": len(rows),
            "assistant_turns": sum(row["assistant_turns"] for row in rows),
            "sequence_tokens": sum(row["sequence_tokens"] for row in rows),
            "trainable_tokens": sum(row["trainable_tokens"] for row in rows),
            "max_sequence_tokens": max(row["sequence_tokens"] for row in rows),
        }
        for name, rows in tokens.items()
    }
    return {
        "input_receipts": refs,
        "tokenizer_receipt": tokenizer_ref,
        "counts": counts,
        "schedule": {**receipt, "max_steps": steps, "trainable_tokens": budget},
        "chat_template_sha256": hashlib.sha256(tokenizer.chat_template.encode()).hexdigest(),
    }


def make_config(spec, prepared, kind):
    host_name = PLACEMENT[kind]
    host = spec["hosts"][host_name]
    run_id = "science-pilot-" + kind.replace("_", "-") + "-v1"
    initialization = {
        "kind": kind,
        "base": {
            "path": host["upstream_base"] if kind == "upstream_fresh" else host["muta_base"],
            "tree_sha256": train.BASE_TREES[kind],
        },
        "tokenizer": {
            "path": host["tokenizer"],
            "tree_sha256": prepared["tokenizer_receipt"]["tree_sha256"],
        },
    }
    if kind == "pilot_adapter":
        initialization["adapter"] = {
            "path": host["pilot_adapter"],
            "tree_sha256": train.PILOT_TREE,
            "parent_base_tree_sha256": train.BASE_TREES[kind],
        }
    data = {
        name: {"path": str(Path(host["data"]) / Path(ref["path"]).name), "sha256": ref["sha256"]}
        for name, ref in prepared["input_receipts"].items()
    }
    batch = spec["microbatches"][kind]
    result = {
        "schema_version": 1,
        "run_id": run_id,
        "output": str(Path(host["runs"]) / run_id),
        "gpu_lock": calibrate.GPU_LOCK
        if host_name == "oracle"
        else f"/tmp/muta-science-tutor-{run_id}.gpu.lock",
        "initialization": initialization,
        "data": data,
        "tokenization": {
            "max_length": 4096,
            "chat_template_sha256": prepared["chat_template_sha256"],
            "split_policy": "preserve_whole_conversation",
        },
        "training": {
            "seed": 3407,
            "micro_batch_size": batch,
            "gradient_accumulation": 64 // batch,
            "effective_batch_size": 64,
            "max_steps": prepared["schedule"]["max_steps"],
            "expected_trainable_tokens": prepared["schedule"]["trainable_tokens"],
            "learning_rate": 5e-6,
            "weight_decay": 0.0,
            "warmup_ratio": 0.03,
            "logging_steps": 1,
            "eval_batch_size": 1,
            "gradient_checkpointing": True,
        },
        "lora": {"r": 16, "alpha": 16, "dropout": 0.0, "target_modules": sorted(train.TARGETS)},
        "notes": "Matched one-epoch pilot; host/kernel/runtime differences are not isolated initialization effects. Pilot adapter loads once with a fresh optimizer. No loss-only checkpoint selection.",
    }
    train.validate_config(result)
    return result


def sbatch_text(host, manifest_sha, kind):
    run_id = "science-pilot-" + kind.replace("_", "-") + "-v1"
    command = [
        host["python"],
        str(Path(host["release"]) / "sources/pilot_launch.py"),
        "launch",
        "--manifest",
        str(Path(host["release"]) / "campaign.json"),
        "--manifest-sha256",
        manifest_sha,
        "--kind",
        kind,
    ]
    return "\n".join(
        [
            "#!/bin/bash",
            "# Draft only: root must review fresh credits, queues and exact bundle hashes before submission.",
            f"#SBATCH --account={ACCOUNT}",
            f"#SBATCH --partition={PARTITION}",
            "#SBATCH --gres=gpu:1",
            "#SBATCH --nodes=1",
            "#SBATCH --ntasks=1",
            "#SBATCH --cpus-per-task=8",
            "#SBATCH --mem=32G",
            "#SBATCH --time=01:50:00",
            f"#SBATCH --job-name={run_id}",
            f"#SBATCH --output={host['control']}/{run_id}-slurm-%j.out",
            "set -euo pipefail",
            "export PYTHONDONTWRITEBYTECODE=1",
            "exec " + shlex.join(command),
            "",
        ]
    )


def materialize(args):
    ref = train.verify_ref({"path": str(Path(args.spec).absolute()), "sha256": args.spec_sha256})
    spec = train.read_json(args.spec)
    validate_spec(spec)
    sources = source_hashes()
    prepared = admitted_schedule(spec)
    output = Path(args.output).absolute()
    output.mkdir(parents=True, exist_ok=False)
    try:
        source_dir = output / "sources"
        source_dir.mkdir()
        for name in sorted(SOURCE_NAMES):
            with (source_dir / name).open("xb") as handle:
                handle.write(Path(__file__).with_name(name).read_bytes())
        runs = {}
        for kind in KINDS:
            cfg = make_config(spec, prepared, kind)
            path = output / "configs" / f"{kind}.json"
            train.write_new(path, cfg)
            host = spec["hosts"][PLACEMENT[kind]]
            runs[kind] = {
                "host": PLACEMENT[kind],
                "config": {
                    "path": str(Path(host["release"]) / "configs" / path.name),
                    "sha256": train.sha256_file(path),
                },
                "control": str(Path(host["control"]) / cfg["run_id"]),
            }
        manifest = {
            "schema_version": 1,
            "repository_head_commit": spec["repository_head_commit"],
            "working_tree_source_snapshot": True,
            "materialization_spec": ref,
            "source_sha256": sources,
            "hosts": spec["hosts"],
            "microbatches": spec["microbatches"],
            "runs": runs,
            "prepared": prepared,
            "csd3_budget": {
                "reported_available_gpu_hours": 4,
                "maximum_total_requested_gpu_hours": 2 * WALL_SECONDS / 3600,
                "fresh_balance_and_queue_check_required_before_submission": True,
            },
        }
        train.write_new(output / "campaign.json", manifest)
        manifest_sha = train.sha256_file(output / "campaign.json")
        (output / "jobs").mkdir()
        for kind in ("muta_fresh", "pilot_adapter"):
            with (output / "jobs" / f"{kind}.sbatch").open("x") as handle:
                handle.write(sbatch_text(spec["hosts"]["csd3"], manifest_sha, kind))
        if source_hashes() != sources:
            raise train.AdmissionError("source changed while creating release snapshot")
        for name, sha in sources.items():
            if train.sha256_file(source_dir / name) != sha:
                raise train.AdmissionError("staged source mismatch")
        receipt = {
            "status": "materialized_not_launched",
            "campaign_sha256": manifest_sha,
            "inventory": train.tree_receipt(output),
            "data_or_model_copies_created": 0,
        }
        train.write_new(output / "BUNDLE.json", receipt)
        for path in output.rglob("*"):
            if path.is_file():
                path.chmod(0o444)
        return receipt
    except BaseException as exc:
        train.write_new(
            output / "MATERIALIZATION_FAILED.json",
            {"error": str(exc), "traceback": traceback.format_exc(), "automatic_retry": False},
        )
        raise


def load_run(args):
    ref = train.verify_ref(
        {"path": str(Path(args.manifest).absolute()), "sha256": args.manifest_sha256}
    )
    manifest = train.read_json(args.manifest)
    if (
        manifest.get("schema_version") != 1
        or set(manifest.get("runs", {})) != set(KINDS)
        or source_hashes() != manifest.get("source_sha256")
    ):
        raise train.AdmissionError("campaign/source identity mismatch")
    run = manifest["runs"][args.kind]
    if run["host"] != PLACEMENT[args.kind]:
        raise train.AdmissionError("unreviewed host relocation")
    host = manifest["hosts"][run["host"]]
    if (
        os.getuid() != host["uid"]
        or Path(sys.executable).resolve() != Path(host["python"]).resolve()
    ):
        raise train.AdmissionError("wrong host UID or Python interpreter")
    if Path(__file__).resolve() != (Path(host["release"]) / "sources/pilot_launch.py").resolve():
        raise train.AdmissionError("not executing the declared immutable release")
    config_ref = train.verify_ref(run["config"])
    config = train.read_json(run["config"]["path"])
    # Reconstruct instead of trusting mutable numeric fields or authority labels.
    spec = {"hosts": manifest["hosts"], "microbatches": manifest["microbatches"]}
    expected = make_config(spec, manifest["prepared"], args.kind)
    if config != expected:
        raise train.AdmissionError("pilot config is not the frozen matched treatment")
    train.validate_config(config)
    return manifest, run, host, config, {"manifest": ref, "config": config_ref}


def seconds(text):
    if not re.fullmatch(r"(?:\d+-)?(?:\d+:)?\d{1,2}:\d{2}", text):
        raise train.AdmissionError("unrecognized bounded Slurm time")
    days, clock = text.split("-") if "-" in text else ("0", text)
    components = list(map(int, clock.split(":")))
    hours, minutes, sec = components if len(components) == 3 else [0, *components]
    if minutes >= 60 or sec >= 60:
        raise train.AdmissionError("invalid Slurm minute/second component")
    return int(days) * 86400 + hours * 3600 + minutes * 60 + sec


def command(args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=15).stdout


def allocation_snapshot(host_name, *, own_pid=None):
    if host_name == "oracle":
        return calibrate.host_snapshot(own_pid=own_pid)
    job = os.environ.get("SLURM_JOB_ID", "")
    allocated = os.environ.get("SLURM_JOB_GPUS", "").split(",")
    visible = os.environ.get("CUDA_VISIBLE_DEVICES", "").split(",")
    if (
        not job.isdigit()
        or len(allocated) != 1
        or not allocated[0]
        or len(visible) != 1
        or not visible[0]
        or pwd.getpwuid(os.getuid()).pw_name != "ein21"
    ):
        raise train.AdmissionError("one owned Slurm GPU allocation is required")
    details = dict(
        field.split("=", 1)
        for field in shlex.split(command(["scontrol", "show", "job", "-o", job]))
        if "=" in field
    )
    if (
        details.get("Account") != ACCOUNT
        or details.get("Partition") != PARTITION
        or details.get("JobState") != "RUNNING"
        or details.get("NumNodes") != "1"
        or details.get("NumTasks") != "1"
        or details.get("UserId", "").split("(")[0] != "ein21"
        or "gres/gpu=1" not in details.get("AllocTRES", "").split(",")
        or seconds(details.get("TimeLimit", "")) > WALL_SECONDS
    ):
        raise train.AdmissionError(
            "Slurm ownership/account/resources/time differ from reviewed allocation"
        )
    gpus = calibrate.parse_gpu_rows(
        command(
            [
                "nvidia-smi",
                "--query-gpu=index,uuid,name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ]
        )
    )
    selected = [
        gpu for gpu in gpus if str(gpu["index"]) == allocated[0] or gpu["uuid"] == allocated[0]
    ]
    if len(selected) != 1 or "A100" not in selected[0]["name"]:
        raise train.AdmissionError("cannot bind Slurm GPU to one physical A100")
    processes = []
    for row in csv.reader(
        command(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,gpu_uuid,used_gpu_memory",
                "--format=csv,noheader,nounits",
            ]
        ).splitlines(),
        skipinitialspace=True,
    ):
        if row and row[1].strip() == selected[0]["uuid"]:
            processes.append(
                {"pid": int(row[0]), "gpu_uuid": row[1].strip(), "memory_mib": row[2].strip()}
            )
    if any(row["pid"] != own_pid for row in processes):
        raise train.AdmissionError(f"allocated GPU has another compute process: {processes}")
    remaining = seconds(command(["squeue", "-h", "-j", job, "-o", "%L"]).strip())
    return {
        "gpu": selected[0],
        "compute_processes": processes,
        "job_id": job,
        "job": details,
        "remaining_seconds": remaining,
        "observed_unix": time.time(),
    }


@contextmanager
def gpu_lock(config, host_name):
    if host_name == "oracle":
        with calibrate.oracle_lock(config["gpu_lock"]):
            yield
    else:
        path = Path(config["gpu_lock"])
        if path.exists() and (path.is_symlink() or path.stat().st_uid != os.getuid()):
            raise train.AdmissionError("CSD3 run lock has wrong ownership")
        with train.exclusive_lock(path):
            yield


def qualify(args):
    manifest, run, _host, config, refs = load_run(args)
    output = Path(run["control"]) / "qualification"
    output.mkdir(parents=True, exist_ok=False)
    try:
        tokenizer, data, _schedule, prepared = train.prepare(config)
        with gpu_lock(config, run["host"]):
            before = allocation_snapshot(run["host"])
            import torch

            if (
                not torch.cuda.is_available()
                or torch.cuda.device_count() != 1
                or not torch.cuda.is_bf16_supported()
            ):
                raise train.AdmissionError("one visible BF16 CUDA GPU required")
            torch.manual_seed(3407)
            torch.cuda.manual_seed_all(3407)
            torch.backends.cuda.matmul.allow_tf32 = False
            torch.backends.cudnn.allow_tf32 = False
            torch.backends.cudnn.benchmark = False
            model, parameters, initialized = train.initialize_model(config, torch=torch)
            model.train()
            initial_identity = train._adapter_identity(model, torch)
            own = allocation_snapshot(run["host"], own_pid=os.getpid())
            if not any(row["pid"] == os.getpid() for row in own["compute_processes"]):
                raise train.AdmissionError(
                    "CUDA model did not appear on the allocated physical GPU"
                )
            optimizer = torch.optim.AdamW(
                parameters, lr=5e-6, weight_decay=0.0, betas=(0.9, 0.999), eps=1e-8
            )
            indices = sorted(
                range(len(data["train"])), key=lambda i: (-data["train"][i]["sequence_tokens"], i)
            )[:64]
            if len(indices) != 64:
                raise train.AdmissionError("qualification requires 64 admitted rows")
            items = [data["train"][index] for index in indices]
            token_count = sum(row["trainable_tokens"] for row in items)
            batch_size = config["training"]["micro_batch_size"]
            free, total = torch.cuda.mem_get_info()
            projection = calibrate.memory_projection(
                microbatch=batch_size,
                length=items[0]["sequence_tokens"],
                vocab_size=model.config.vocab_size,
                total_bytes=total,
                free_bytes=free,
                measurements=[],
            )
            if not projection["admit"]:
                raise train.AdmissionError(
                    "real-data qualification would breach conservative memory projection"
                )
            torch.cuda.empty_cache()
            baseline_reserved = torch.cuda.memory_reserved()
            free, total = torch.cuda.mem_get_info()
            torch.cuda.reset_peak_memory_stats()
            optimizer.zero_grad(set_to_none=True)
            torch.cuda.synchronize()
            started = time.perf_counter()
            loss_value = 0.0
            for offset in range(0, 64, batch_size):
                chunk = items[offset : offset + batch_size]
                targets = sum(row["trainable_tokens"] for row in chunk)
                batch = train.collate(
                    chunk, pad_token_id=tokenizer.pad_token_id, torch_module=torch, device="cuda:0"
                )
                with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                    loss = model(**batch).loss
                if not bool(torch.isfinite(loss)):
                    raise RuntimeError("nonfinite qualification loss")
                (loss * (targets / token_count)).backward()
                loss_value += float(loss.detach()) * targets / token_count
                del loss, batch
            grad_norm = torch.nn.utils.clip_grad_norm_(parameters, 1.0, error_if_nonfinite=True)
            optimizer.step()
            torch.cuda.synchronize()
            elapsed = time.perf_counter() - started
            dev_probe = train.evaluate(
                model,
                [max(data["dev"], key=lambda row: row["sequence_tokens"])],
                tokenizer=tokenizer,
                torch=torch,
                batch_size=1,
            )
            changed = train._adapter_identity(model, torch) != initial_identity
            state_bytes = sum(
                value.numel() * value.element_size()
                for item in optimizer.state.values()
                for value in item.values()
                if torch.is_tensor(value)
            )
            peak_reserved = torch.cuda.max_memory_reserved()
            estimated_used = total - free + max(0, peak_reserved - baseline_reserved)
            if (
                not changed
                or not state_bytes
                or any(not bool(torch.isfinite(parameter).all()) for parameter in parameters)
            ):
                raise RuntimeError(
                    "AdamW qualification did not make a finite real update/allocate state"
                )
            if (
                estimated_used
                + max(calibrate.HEADROOM_BYTES, math.ceil(total * calibrate.HEADROOM_FRACTION))
                > total
            ):
                raise RuntimeError("real optimizer qualification exceeded memory headroom")
            after = allocation_snapshot(run["host"], own_pid=os.getpid())
            projection_seconds = elapsed * config["training"]["max_steps"] * 1.5 + 600
            if run["host"] == "csd3" and projection_seconds > after["remaining_seconds"]:
                raise RuntimeError(
                    "conservative longest-batch runtime projection exceeds remaining Slurm allocation"
                )
            result = {
                "status": "qualified",
                "config_sha256": refs["config"]["sha256"],
                "source_sha256": manifest["source_sha256"],
                "dataset_sha256": {
                    name: config["data"][name]["sha256"] for name in ("train", "dev", "admission")
                },
                "gpu": before["gpu"],
                "host_after": after,
                "environment": train.environment_receipt(),
                "initialization": initialized,
                "effective_rows": 64,
                "microbatch": batch_size,
                "indices_sha256": train.digest(indices),
                "row_token_hashes_sha256": train.digest([row["input_ids_sha256"] for row in items]),
                "longest_sequence_tokens": items[0]["sequence_tokens"],
                "supervised_tokens": token_count,
                "weighted_loss_not_accuracy": loss_value,
                "grad_norm": float(grad_norm),
                "optimizer": "torch.optim.AdamW",
                "optimizer_state_bytes": state_bytes,
                "optimizer_step_executed": True,
                "diagnostic_adapter_changed": True,
                "weights_saved": False,
                "candidate_state_reused": False,
                "effective_batch_step_seconds": elapsed,
                "conservative_training_seconds": projection_seconds,
                "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                "peak_reserved_bytes": peak_reserved,
                "estimated_whole_device_peak_used_bytes": estimated_used,
                "memory_headroom_passed": True,
            }
            result.update(preflight_counts=prepared["counts"], longest_development_probe=dev_probe)
            train.write_new(output / "COMPLETED.json", result)
            del optimizer, model, parameters
            gc.collect()
            torch.cuda.empty_cache()
            return result
    except BaseException as exc:
        train.write_new(
            output / "FAILED.json",
            {
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "automatic_retry": False,
                "config_sha256": refs["config"]["sha256"],
            },
        )
        raise


def child(command_line, log):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    with Path(log).open("xb") as handle:
        process = subprocess.Popen(command_line, stdout=handle, stderr=subprocess.STDOUT, env=env)
        try:
            code = process.wait()
        except BaseException:
            if process.poll() is None:
                process.terminate()  # Only the child created here; never a discovered process.
                process.wait(timeout=30)
            raise
    if code != 0:
        raise RuntimeError(f"owned child exited {code}; retained log {log}; no retry")


def launch(args):
    manifest, run, host, config, refs = load_run(args)
    control = Path(run["control"])
    control.mkdir(parents=True, exist_ok=False)
    try:
        if Path(config["output"]).exists():
            raise train.AdmissionError("pilot output already exists; no implicit retry/resume")
        train.write_new(
            control / "REQUEST.json",
            {
                "refs": refs,
                "source_sha256": manifest["source_sha256"],
                "pid": os.getpid(),
                "time_unix": time.time(),
                "mode": "disposable qualification then fresh pilot",
            },
        )
        snapshot = allocation_snapshot(run["host"])
        train.write_new(control / "host-before.json", snapshot)
        command_line = [
            host["python"],
            str(Path(__file__).resolve()),
            "qualify",
            "--manifest",
            refs["manifest"]["path"],
            "--manifest-sha256",
            refs["manifest"]["sha256"],
            "--kind",
            args.kind,
        ]
        child(command_line, control / "qualification.stdout.log")
        qualification_ref = train.file_receipt(control / "qualification/COMPLETED.json")
        qualification = train.read_json(qualification_ref["path"])
        if (
            qualification.get("status") != "qualified"
            or qualification.get("config_sha256") != refs["config"]["sha256"]
            or qualification.get("source_sha256") != manifest["source_sha256"]
            or qualification.get("weights_saved") is not False
            or qualification.get("candidate_state_reused") is not False
            or qualification.get("memory_headroom_passed") is not True
        ):
            raise train.AdmissionError("real-data optimizer qualification receipt mismatch")
        before_train = allocation_snapshot(run["host"])
        if before_train["gpu"]["uuid"] != qualification["gpu"]["uuid"]:
            raise train.AdmissionError("GPU changed after qualification")
        if (
            run["host"] == "csd3"
            and qualification["conservative_training_seconds"] > before_train["remaining_seconds"]
        ):
            raise train.AdmissionError("insufficient remaining allocation after qualification")
        load_run(args)
        train.write_new(
            control / "training-admission.json",
            {
                "qualification": qualification_ref,
                "host": before_train,
                "config": refs["config"],
                "source_sha256": manifest["source_sha256"],
            },
        )
        child(
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
        completed_ref = train.file_receipt(Path(config["output"]) / "COMPLETED.json")
        completed = train.read_json(completed_ref["path"])
        if (
            completed.get("status") != "complete"
            or completed.get("config_sha256") != refs["config"]["sha256"]
            or completed.get("completed_steps") != config["training"]["max_steps"]
            or completed.get("consumed_trainable_tokens")
            != config["training"]["expected_trainable_tokens"]
            or completed.get("source_sha256")
            != {name: manifest["source_sha256"][name] for name in ("train.py", "tokenization.py")}
        ):
            raise train.AdmissionError("trainer terminal evidence mismatch")
        for record in completed["run_inventory"]["files"]:
            path = Path(config["output"]) / record["path"]
            if (
                not path.resolve().is_relative_to(Path(config["output"]).resolve())
                or train.file_receipt(path)["sha256"] != record["sha256"]
            ):
                raise train.AdmissionError("trainer evidence inventory mismatch")
        load_run(args)
        result = {
            "status": "complete",
            "run_kind": args.kind,
            "qualification": qualification_ref,
            "trainer_completion": completed_ref,
            "config_sha256": refs["config"]["sha256"],
            "host_after": allocation_snapshot(run["host"]),
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    materializer = sub.add_parser("materialize")
    materializer.add_argument("--spec", type=Path, required=True)
    materializer.add_argument("--spec-sha256", required=True)
    materializer.add_argument("--output", type=Path, required=True)
    for name in ("launch", "qualify"):
        command_parser = sub.add_parser(name)
        command_parser.add_argument("--manifest", type=Path, required=True)
        command_parser.add_argument("--manifest-sha256", required=True)
        command_parser.add_argument("--kind", choices=KINDS, required=True)
    args = parser.parse_args()

    def stopped(signum, _frame):
        raise InterruptedError(f"received signal {signum}; no automatic retry")

    signal.signal(signal.SIGTERM, stopped)
    signal.signal(signal.SIGINT, stopped)
    print(
        json.dumps(
            {"materialize": materialize, "launch": launch, "qualify": qualify}[args.mode](args),
            ensure_ascii=False,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
