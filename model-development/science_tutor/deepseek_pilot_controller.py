"""Hash-bound DeepSeek native pilot controller for the Oracle A100.

This controller performs the same disposable real-data optimizer qualification
as the matched Qwen pilot, then launches the native wrapper exactly once.  A
failure is sealed and never retried automatically.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

try:
    from . import calibrate, deepseek_train, train
except ImportError:  # direct invocation on a training host
    import calibrate
    import deepseek_train
    import train


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def file_receipt(path):
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"path": str(path.resolve()), "sha256": digest, "bytes": path.stat().st_size}


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        handle.write("\n")


def source_hashes():
    return {name: file_receipt(Path(deepseek_train.__file__).with_name(name))["sha256"] for name in (
        "train.py",
        "tokenization.py",
        "deepseek_train.py",
        "deepseek_tokenization.py",
    )}


def qualification(config, prepared, control):
    import torch

    if not torch.cuda.is_available() or torch.cuda.device_count() != 1 or not torch.cuda.is_bf16_supported():
        raise train.AdmissionError("exactly one visible BF16-capable CUDA GPU is required")
    tokenizer, data, _schedule, _receipt = prepared
    torch.manual_seed(config["training"]["seed"])
    torch.cuda.manual_seed_all(config["training"]["seed"])
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.benchmark = False
    before = calibrate.host_snapshot()
    model, parameters, initialized = train.initialize_model(config, torch=torch)
    try:
        model.train()
        initial_identity = train._adapter_identity(model, torch)
        own = calibrate.host_snapshot(own_pid=os.getpid())
        if not any(row["pid"] == os.getpid() for row in own["compute_processes"]):
            raise train.AdmissionError("CUDA model did not appear on the owned Oracle GPU")
        optimizer = torch.optim.AdamW(
            parameters,
            lr=config["training"]["learning_rate"],
            weight_decay=config["training"]["weight_decay"],
            betas=(0.9, 0.999),
            eps=1e-8,
        )
        indices = sorted(
            range(len(data["train"])),
            key=lambda i: (-data["train"][i]["sequence_tokens"], i),
        )[:64]
        items = [data["train"][index] for index in indices]
        token_count = sum(row["trainable_tokens"] for row in items)
        microbatch = config["training"]["micro_batch_size"]
        free, total = torch.cuda.mem_get_info()
        projection = calibrate.memory_projection(
            microbatch=microbatch,
            length=items[0]["sequence_tokens"],
            vocab_size=model.config.vocab_size,
            total_bytes=total,
            free_bytes=free,
            measurements=[],
        )
        if not projection["admit"]:
            raise train.AdmissionError("real-data qualification would breach memory projection")
        torch.cuda.reset_peak_memory_stats()
        optimizer.zero_grad(set_to_none=True)
        torch.cuda.synchronize()
        started = time.perf_counter()
        weighted_loss = 0.0
        for offset in range(0, len(items), microbatch):
            chunk = items[offset : offset + microbatch]
            targets = sum(row["trainable_tokens"] for row in chunk)
            batch = train.collate(
                chunk,
                pad_token_id=tokenizer.pad_token_id,
                torch_module=torch,
                device="cuda:0",
            )
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                loss = model(**batch).loss
            if not bool(torch.isfinite(loss)):
                raise RuntimeError("nonfinite DeepSeek qualification loss")
            (loss * (targets / token_count)).backward()
            weighted_loss += float(loss.detach()) * targets / token_count
            del loss, batch
        grad_norm = torch.nn.utils.clip_grad_norm_(parameters, 1.0, error_if_nonfinite=True)
        optimizer.step()
        torch.cuda.synchronize()
        elapsed = time.perf_counter() - started
        changed = train._adapter_identity(model, torch) != initial_identity
        state_bytes = sum(
            value.numel() * value.element_size()
            for item in optimizer.state.values()
            for value in item.values()
            if torch.is_tensor(value)
        )
        peak_reserved = torch.cuda.max_memory_reserved()
        estimated_used = total - free + max(0, peak_reserved)
        if not changed or not state_bytes:
            raise RuntimeError("qualification did not make a finite real adapter update")
        if estimated_used + max(calibrate.HEADROOM_BYTES, math.ceil(total * calibrate.HEADROOM_FRACTION)) > total:
            raise RuntimeError("qualification exceeded conservative memory headroom")
        result = {
            "status": "qualified",
            "config_sha256": file_receipt(config["_config_path"])["sha256"],
            "source_sha256": source_hashes(),
            "dataset_sha256": {name: config["data"][name]["sha256"] for name in ("train", "dev", "admission")},
            "gpu": before["gpu"],
            "host_before": before,
            "host_after_model": own,
            "environment": train.environment_receipt(),
            "initialization": initialized,
            "effective_rows": 64,
            "microbatch": microbatch,
            "indices_sha256": train.digest(indices),
            "row_token_hashes_sha256": train.digest([row["input_ids_sha256"] for row in items]),
            "longest_sequence_tokens": items[0]["sequence_tokens"],
            "supervised_tokens": token_count,
            "weighted_loss_not_accuracy": weighted_loss,
            "grad_norm": float(grad_norm),
            "optimizer": "torch.optim.AdamW",
            "optimizer_state_bytes": state_bytes,
            "optimizer_step_executed": True,
            "diagnostic_adapter_changed": changed,
            "weights_saved": False,
            "candidate_state_reused": False,
            "effective_batch_step_seconds": elapsed,
            "conservative_training_seconds": elapsed * config["training"]["max_steps"] * 1.5 + 600,
            "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
            "peak_reserved_bytes": peak_reserved,
            "estimated_whole_device_peak_used_bytes": estimated_used,
            "memory_headroom_passed": True,
        }
        write_new(Path(control) / "qualification" / "COMPLETED.json", result)
        return result
    finally:
        try:
            del optimizer
        except UnboundLocalError:
            pass
        del model, parameters
        gc.collect()
        torch.cuda.empty_cache()


def main(argv=None):
    deepseek_train.configure()
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--control", type=Path, required=True)
    args = parser.parse_args(argv)
    config = train.read_json(args.config)
    config["_config_path"] = str(args.config)
    try:
        if file_receipt(args.config)["sha256"] != args.config_sha256:
            raise train.AdmissionError("config hash mismatch")
        config_for_train = dict(config)
        config_for_train.pop("_config_path")
        train.validate_config(config_for_train)
        prepared = train.prepare(config_for_train)
        args.control.mkdir(parents=True, exist_ok=False)
        write_new(args.control / "REQUEST.json", {"config_sha256": args.config_sha256, "source_sha256": source_hashes(), "pid": os.getpid(), "time_unix": time.time()})
        with calibrate.oracle_lock(config_for_train["gpu_lock"]):
            qualification_result = qualification(config, prepared, args.control)
        write_new(args.control / "training-admission.json", {"qualification": file_receipt(args.control / "qualification" / "COMPLETED.json"), "config_sha256": args.config_sha256, "source_sha256": source_hashes()})
        command = [
            sys.executable,
            str(Path(deepseek_train.__file__).resolve()),
            "--config",
            str(args.config),
            "--config-sha256",
            args.config_sha256,
        ]
        with (args.control / "training.stdout.log").open("x") as log:
            process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
        if process.returncode != 0:
            raise RuntimeError(f"DeepSeek trainer exited {process.returncode}")
        completed = train.read_json(Path(config_for_train["output"]) / "COMPLETED.json")
        expected_sources = source_hashes()
        if completed.get("status") != "complete" or completed.get("config_sha256") != args.config_sha256 or completed.get("completed_steps") != config_for_train["training"]["max_steps"] or completed.get("consumed_trainable_tokens") != config_for_train["training"]["expected_trainable_tokens"] or completed.get("source_sha256") != expected_sources:
            raise train.AdmissionError("DeepSeek trainer terminal evidence mismatch")
        write_new(args.control / "COMPLETED.json", {"status": "complete", "qualification": file_receipt(args.control / "qualification" / "COMPLETED.json"), "trainer_completion": file_receipt(Path(config_for_train["output"]) / "COMPLETED.json"), "config_sha256": args.config_sha256, "source_sha256": expected_sources, "ended_unix": time.time()})
    except BaseException as exc:
        try:
            write_new(args.control / "FAILED.json", {"status": "failed", "error": str(exc), "traceback": traceback.format_exc(), "automatic_retry": False, "config_sha256": args.config_sha256, "time_unix": time.time()})
        except FileExistsError:
            pass
        raise


if __name__ == "__main__":
    main()
