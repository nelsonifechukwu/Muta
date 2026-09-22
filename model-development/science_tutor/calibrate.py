"""Bounded, backward-only Oracle diagnostic. Never updates or saves model weights.

Requires a reviewed hash-bound config/source manifest. No automatic retry, model
download, training data access, optimizer construction or process termination.
Synthetic repeated text tests memory/throughput, not science accuracy.
"""

from __future__ import annotations

import argparse
import csv
import fcntl
import gc
import hashlib
import json
import math
import os
import re
import signal
import stat
import subprocess
import time
import traceback
from contextlib import contextmanager
from pathlib import Path

try:
    from . import train
    from .tokenization import tokenize_messages
except ImportError:
    import train
    from tokenization import tokenize_messages


GPU_LOCK = "/tmp/muta-round2-full-uid-1000-gpu-0.lock"
EXPECTED_UID = 1000
LENGTHS = (512, 2048, 4096)
MICROBATCHES = (1, 2, 4)
WARMUP_ITERATIONS = 1
MEASURED_ITERATIONS = 2
GIB = 1024**3
HEADROOM_BYTES = 4 * GIB
HEADROOM_FRACTION = 0.15
SOURCE_NAMES = {"calibrate.py", "train.py", "tokenization.py"}


def validate_config(config):
    required = {
        "schema_version",
        "run_id",
        "output",
        "gpu_lock",
        "source_manifest",
        "initialization",
        "chat_template_sha256",
    }
    if not isinstance(config, dict) or set(config) != required or config["schema_version"] != 1:
        raise train.AdmissionError("unexpected calibration config/schema")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]+", config["run_id"]):
        raise train.AdmissionError("invalid run ID")
    if not Path(config["output"]).is_absolute() or config["gpu_lock"] != GPU_LOCK:
        raise train.AdmissionError("absolute output and exact shared Oracle GPU lock required")
    init = config["initialization"]
    if set(init) != {"kind", "base", "tokenizer"} or init["kind"] != "upstream_fresh":
        raise train.AdmissionError("diagnostic requires upstream parent and a fresh adapter")
    if init["base"].get("tree_sha256") != train.BASE_TREES["upstream_fresh"]:
        raise train.AdmissionError("wrong upstream parent identity")
    if not re.fullmatch(r"[0-9a-f]{64}", config["chat_template_sha256"]):
        raise train.AdmissionError("invalid chat template SHA256")


def verify_sources(ref):
    receipt = train.verify_ref(ref)
    manifest = train.read_json(ref["path"])
    if set(manifest) != {
        "schema_version",
        "source_revision",
        "repository_head_commit",
        "working_tree_source_snapshot",
        "files",
    }:
        raise train.AdmissionError("unexpected source manifest fields")
    if manifest["schema_version"] != 1 or manifest["working_tree_source_snapshot"] is not True:
        raise train.AdmissionError("source snapshot identity is missing")
    if not isinstance(manifest["source_revision"], str) or not manifest["source_revision"].strip():
        raise train.AdmissionError("source revision label is missing")
    if not re.fullmatch(r"[0-9a-f]{40}", manifest["repository_head_commit"]):
        raise train.AdmissionError("repository HEAD commit is missing")
    if set(manifest["files"]) != SOURCE_NAMES:
        raise train.AdmissionError("source manifest must bind all three executed modules")
    files = {
        name: train.file_receipt(Path(__file__).with_name(name)) for name in sorted(SOURCE_NAMES)
    }
    if any(files[name]["sha256"] != manifest["files"][name] for name in SOURCE_NAMES):
        raise train.AdmissionError("reviewed source hash mismatch")
    return {"manifest": receipt, "declaration": manifest, "observed_files": files}


def prepare(config):
    validate_config(config)
    sources = verify_sources(config["source_manifest"])
    identities = {
        key: train.verify_ref(config["initialization"][key], tree=True)
        for key in ("base", "tokenizer")
    }
    observed = {row["path"]: row["sha256"] for row in identities["tokenizer"]["files"]}
    if any(observed.get(name) != sha for name, sha in train.TOKENIZER_FILES.items()):
        raise train.AdmissionError("not the reviewed common upstream tokenizer")
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        config["initialization"]["tokenizer"]["path"],
        local_files_only=True,
        trust_remote_code=False,
    )
    if (
        hashlib.sha256(tokenizer.chat_template.encode()).hexdigest()
        != config["chat_template_sha256"]
    ):
        raise train.AdmissionError("chat template hash mismatch")
    if tokenizer.pad_token_id is None:
        raise train.AdmissionError("explicit padding token is required")
    cases = {length: diagnostic_row(tokenizer, length) for length in LENGTHS}
    return tokenizer, cases, {"sources": sources, "initialization": identities}


def diagnostic_row(tokenizer, target_length):
    """Repeat normal words to the token limit; only explicit right padding is allowed."""
    if target_length not in LENGTHS:
        raise train.AdmissionError("unapproved diagnostic length")

    def candidate(repetitions):
        return tokenize_messages(
            [
                {
                    "role": "system",
                    "content": "Synthetic memory calibration only. This is not training data.",
                },
                {"role": "user", "content": "Explain why scientific explanations need evidence."},
                {
                    "role": "assistant",
                    "content": "Evidence supports explanations." + " Evidence" * repetitions,
                },
            ],
            tokenizer=tokenizer,
            max_length=target_length * 4,
        )

    low, high = 0, target_length
    while low < high:
        middle = (low + high + 1) // 2
        if candidate(middle)["sequence_tokens"] <= target_length:
            low = middle
        else:
            high = middle - 1
    row = candidate(low)
    active = row["sequence_tokens"]
    padding = target_length - active
    if not 0 <= padding < 8:
        raise train.AdmissionError("synthetic token fill did not reach the requested length")
    row["input_ids"] += [tokenizer.pad_token_id] * padding
    row["attention_mask"] += [0] * padding
    row["labels"] += [-100] * padding
    row.update(
        sequence_tokens=target_length,
        active_sequence_tokens=active,
        explicit_padding_tokens=padding,
        diagnostic_only=True,
        input_ids_sha256=train.digest(row["input_ids"]),
        labels_sha256=train.digest(row["labels"]),
    )
    return row


def parse_gpu_rows(text):
    rows = []
    for fields in csv.reader(text.splitlines(), skipinitialspace=True):
        if not fields:
            continue
        if len(fields) != 5:
            raise train.AdmissionError("unexpected nvidia-smi GPU record")
        index, uuid, name, total, free = (value.strip() for value in fields)
        rows.append(
            {
                "index": int(index),
                "uuid": uuid,
                "name": name,
                "total_bytes": int(total) * 1024**2,
                "free_bytes": int(free) * 1024**2,
            }
        )
    return rows


def host_snapshot(*, own_pid=None):
    def command(args):
        return subprocess.run(args, check=True, capture_output=True, text=True, timeout=15).stdout

    gpus = parse_gpu_rows(
        command(
            [
                "nvidia-smi",
                "--query-gpu=index,uuid,name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ]
        )
    )
    if (
        len(gpus) != 1
        or gpus[0]["index"] != 0
        or "A100" not in gpus[0]["name"]
        or not 38 * GIB <= gpus[0]["total_bytes"] <= 42 * GIB
    ):
        raise train.AdmissionError("expected one physical Oracle A100 40 GB")
    processes = []
    raw = command(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,gpu_uuid,used_gpu_memory",
            "--format=csv,noheader,nounits",
        ]
    )
    for fields in csv.reader(raw.splitlines(), skipinitialspace=True):
        if not fields:
            continue
        if len(fields) != 3:
            raise train.AdmissionError("unexpected nvidia-smi process record")
        pid, uuid, memory = (value.strip() for value in fields)
        pid = int(pid)
        uid = command(["ps", "-o", "uid=", "-p", str(pid)]).strip()
        processes.append({"pid": pid, "uid": int(uid), "gpu_uuid": uuid, "memory_mib": memory})
    if any(row["pid"] != own_pid or row["uid"] != EXPECTED_UID for row in processes):
        raise train.AdmissionError(f"GPU is not idle/owned solely by this diagnostic: {processes}")
    return {
        "observed_unix": time.time(),
        "gpu": gpus[0],
        "compute_processes": processes,
        "own_pid_allowed": own_pid,
    }


@contextmanager
def oracle_lock(path):
    if path != GPU_LOCK or os.getuid() != EXPECTED_UID:
        raise train.AdmissionError("wrong shared GPU lock or execution UID")
    flags = os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != EXPECTED_UID or info.st_nlink != 1:
            raise train.AdmissionError(
                "GPU lock must be a singly linked regular file owned by UID 1000"
            )
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise train.AdmissionError("shared GPU lock already owned") from exc
        yield {"path": path, "owner_uid": info.st_uid, "inode": info.st_ino}
    finally:
        os.close(fd)


def memory_projection(*, microbatch, length, vocab_size, total_bytes, free_bytes, measurements):
    reserve = max(HEADROOM_BYTES, math.ceil(total_bytes * HEADROOM_FRACTION))
    # Conservative room for logits, their FP32 loss view and shifted/loss buffers.
    floor = microbatch * length * vocab_size * 4 * 3
    measured = [row for row in measurements if row["status"] == "measured"]
    extrapolated = 0
    anchor = None
    if measured:
        anchor = min(
            measured,
            key=lambda row: (
                abs(math.log(length / row["sequence_length"])),
                abs(math.log(microbatch / row["microbatch"])),
            ),
        )
        ratio = microbatch * length / (anchor["microbatch"] * anchor["sequence_length"])
        extrapolated = math.ceil(anchor["peak_reserved_increment_bytes"] * ratio * 1.35)
    estimate = max(floor, extrapolated)
    return {
        "predicted_additional_bytes": estimate,
        "headroom_bytes": reserve,
        "observed_free_bytes": free_bytes,
        "logits_floor_bytes": floor,
        "measured_anchor": None
        if anchor is None
        else [anchor["microbatch"], anchor["sequence_length"]],
        "admit": estimate + reserve <= free_bytes,
        "heuristic_not_oom_guarantee": True,
    }


def measure_cell(model, row, *, tokenizer, torch, microbatch):
    model.zero_grad(set_to_none=True)
    gc.collect()
    torch.cuda.empty_cache()
    torch.cuda.synchronize()
    baseline_reserved = torch.cuda.memory_reserved()
    baseline_allocated = torch.cuda.memory_allocated()
    free_before, total = torch.cuda.mem_get_info()
    torch.cuda.reset_peak_memory_stats()
    batch = train.collate(
        [row] * microbatch, pad_token_id=tokenizer.pad_token_id, torch_module=torch, device="cuda:0"
    )
    durations, losses = [], []
    for iteration in range(WARMUP_ITERATIONS + MEASURED_ITERATIONS):
        model.zero_grad(set_to_none=True)
        torch.cuda.synchronize()
        started = time.perf_counter()
        with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
            loss = model(**batch).loss
        if not bool(torch.isfinite(loss)):
            raise RuntimeError("nonfinite synthetic diagnostic loss")
        loss.backward()
        torch.cuda.synchronize()
        elapsed = time.perf_counter() - started
        gradients = [p.grad for p in model.parameters() if p.requires_grad]
        if (
            not gradients
            or any(g is None or not bool(torch.isfinite(g).all()) for g in gradients)
            or not any(bool(g.ne(0).any()) for g in gradients)
        ):
            raise RuntimeError("missing, nonfinite or entirely zero diagnostic LoRA gradients")
        if iteration >= WARMUP_ITERATIONS:
            durations.append(elapsed)
            losses.append(float(loss.detach()))
        del loss, gradients
    peak_reserved = torch.cuda.max_memory_reserved()
    peak_allocated = torch.cuda.max_memory_allocated()
    incremental = max(0, peak_reserved - baseline_reserved)
    device_used_peak_estimate = total - free_before + incremental
    headroom = max(HEADROOM_BYTES, math.ceil(total * HEADROOM_FRACTION))
    result = {
        "status": "measured",
        "microbatch": microbatch,
        "sequence_length": row["sequence_tokens"],
        "active_sequence_tokens_per_row": row["active_sequence_tokens"],
        "padding_tokens_per_row": row["explicit_padding_tokens"],
        "trainable_tokens_per_row": row["trainable_tokens"],
        "warmup_iterations": WARMUP_ITERATIONS,
        "measured_iterations": MEASURED_ITERATIONS,
        "forward_backward_seconds": durations,
        "mean_forward_backward_seconds": sum(durations) / len(durations),
        "synthetic_losses_not_accuracy": losses,
        "sequence_tokens_per_second": microbatch
        * row["sequence_tokens"]
        * len(durations)
        / sum(durations),
        "supervised_tokens_per_second": microbatch
        * row["trainable_tokens"]
        * len(durations)
        / sum(durations),
        "baseline_allocated_bytes": baseline_allocated,
        "baseline_reserved_bytes": baseline_reserved,
        "peak_allocated_bytes": peak_allocated,
        "peak_reserved_bytes": peak_reserved,
        "peak_reserved_increment_bytes": incremental,
        "estimated_whole_device_peak_used_bytes": device_used_peak_estimate,
        "total_device_bytes": total,
        "recommendation_eligible": device_used_peak_estimate + headroom <= total,
    }
    model.zero_grad(set_to_none=True)
    del batch
    gc.collect()
    torch.cuda.empty_cache()
    return result


def recommendations(measurements):
    result = []
    for length in LENGTHS:
        passing = [
            row
            for row in measurements
            if row["status"] == "measured"
            and row["sequence_length"] == length
            and row["recommendation_eligible"]
        ]
        best = max(passing, key=lambda row: row["sequence_tokens_per_second"]) if passing else None
        result.append(
            {
                "sequence_length": length,
                "recommended_microbatch": None if best is None else best["microbatch"],
                "measured_sequence_tokens_per_second": None
                if best is None
                else best["sequence_tokens_per_second"],
                "basis": "fastest actually measured eligible backward-only synthetic cell; optimizer and real-data qualification still required",
            }
        )
    return result


def run(args):
    config_ref = train.verify_ref(
        {"path": str(Path(args.config).absolute()), "sha256": args.config_sha256}
    )
    config = train.read_json(args.config)
    validate_config(config)
    output = Path(config["output"])
    output.mkdir(parents=True, exist_ok=False)
    measurements = []
    current_cell = None
    try:
        tokenizer, cases, admission = prepare(config)
        train.write_new(
            output / "admission.json",
            {"config": config, "config_file": config_ref, **admission, "diagnostic_only": True},
        )
        with oracle_lock(config["gpu_lock"]) as lock:
            host = host_snapshot()
            train.write_new(output / "host-before.json", {"lock": lock, **host})
            import torch

            if (
                not torch.cuda.is_available()
                or torch.cuda.device_count() != 1
                or not torch.cuda.is_bf16_supported()
            ):
                raise train.AdmissionError("exactly one visible BF16-capable CUDA GPU required")
            torch.manual_seed(3407)
            torch.cuda.manual_seed_all(3407)
            torch.backends.cuda.matmul.allow_tf32 = False
            torch.backends.cudnn.allow_tf32 = False
            torch.backends.cudnn.benchmark = False
            model_config = {
                "initialization": config["initialization"],
                "training": {"gradient_checkpointing": True},
                "lora": {
                    "r": 16,
                    "alpha": 16,
                    "dropout": 0,
                    "target_modules": sorted(train.TARGETS),
                },
            }
            model, _parameters, initialized = train.initialize_model(model_config, torch=torch)
            model.train()
            initial_adapter = train._adapter_identity(model, torch)
            train.write_new(
                output / "initialized.json",
                {
                    "initialization": initialized,
                    "environment": train.environment_receipt(),
                    "cuda_version": torch.version.cuda,
                    "gpu_name": torch.cuda.get_device_name(0),
                    "synthetic_cases": {
                        str(k): {
                            name: value
                            for name, value in row.items()
                            if name
                            not in {"input_ids", "attention_mask", "labels", "assistant_spans"}
                        }
                        for k, row in cases.items()
                    },
                },
            )
            for length in LENGTHS:
                for microbatch in MICROBATCHES:
                    snapshot = host_snapshot(own_pid=os.getpid())
                    free, total = torch.cuda.mem_get_info()
                    projection = memory_projection(
                        microbatch=microbatch,
                        length=length,
                        vocab_size=model.config.vocab_size,
                        total_bytes=total,
                        free_bytes=free,
                        measurements=measurements,
                    )
                    current_cell = {
                        "microbatch": microbatch,
                        "sequence_length": length,
                        "memory_projection": projection,
                    }
                    train.append_log(
                        output / "events.jsonl", {"event": "cell_start", **current_cell}
                    )
                    if projection["admit"]:
                        result = measure_cell(
                            model,
                            cases[length],
                            tokenizer=tokenizer,
                            torch=torch,
                            microbatch=microbatch,
                        )
                    else:
                        result = {
                            "status": "skipped_anticipated_memory_limit",
                            "microbatch": microbatch,
                            "sequence_length": length,
                        }
                    result.update(memory_projection=projection, host_before_cell=snapshot)
                    measurements.append(result)
                    train.append_log(output / "measurements.jsonl", result)
            if train._adapter_identity(model, torch) != initial_adapter:
                raise RuntimeError("diagnostic unexpectedly changed adapter weights")
            for ref in config["initialization"]["base"], config["initialization"]["tokenizer"]:
                train.verify_ref(ref, tree=True)
            verify_sources(config["source_manifest"])
            if train.sha256_file(args.config) != config_ref["sha256"]:
                raise train.AdmissionError("config changed during diagnostic")
            train.write_new(output / "host-after.json", host_snapshot(own_pid=os.getpid()))
            result = {
                "schema_version": 1,
                "status": "complete",
                "diagnostic_only": True,
                "weights_unchanged": True,
                "no_optimizer_or_updates": True,
                "config_sha256": config_ref["sha256"],
                "recommendations": recommendations(measurements),
                "measured_cells": sum(row["status"] == "measured" for row in measurements),
                "skipped_cells": sum(row["status"] != "measured" for row in measurements),
                "limitations": "Synthetic repeated-text forward/backward only; no optimizer allocation, step, checkpoint, dataset accuracy, end-to-end ETA or target-CPU claim.",
                "run_inventory": train.tree_receipt(output),
            }
            train.write_new(output / "COMPLETED.json", result)
            return result
    except BaseException as exc:
        train.write_new(
            output / "FAILED.json",
            {
                "schema_version": 1,
                "status": "failed",
                "config_sha256": config_ref["sha256"],
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "current_cell": current_cell,
                "completed_cell_count": len(measurements),
                "automatic_retry": False,
                "time_unix": time.time(),
            },
        )
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--config-sha256", required=True)
    args = parser.parse_args()

    def stopped(signum, _frame):
        raise InterruptedError(f"received signal {signum}; no automatic retry")

    signal.signal(signal.SIGTERM, stopped)
    signal.signal(signal.SIGINT, stopped)
    print(json.dumps(run(args), ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
