"""Run bounded fresh/continuation training and real checkpoint-resume checks.

Runs only inside an explicitly supplied, previously nonexistent output root.
Never signals an existing job: interrupted processes are created by this wrapper
in a new process group. All source commands, logs and interruption evidence stay
beside the original training outputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import time
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def write(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def command(args, *, continuation: bool) -> list[str]:
    root = args.campaign_root
    run_name = "continuation-resume" if continuation else "clean-complete"
    lineage = "warm" if continuation else "clean"
    base = args.warm_base if continuation else root / "bases/upstream-qwen25"
    cmd = [
        str(args.python),
        str(args.repo / "model-development/finetune/train_lora_round2.py"),
        "--model",
        str(base),
        "--base-lineage",
        str(root / "provenance" / f"{lineage}-lineage.json"),
        "--tokenizer",
        str(root / "bases/upstream-qwen25"),
        "--tokenizer-lineage",
        str(root / "provenance/clean-lineage.json"),
        "--lineage",
        lineage,
        "--dataset-manifest",
        str(root / "data/muta-stem-v2-sft-300k-quality-first-20260917-v1/manifest.json"),
        "--validation-manifest",
        str(root / "data/round2-dev-5000/manifest.json"),
        "--output",
        str(args.output_root / run_name),
        "--run-name",
        f"full-stage-smoke-{run_name}",
        "--max-length",
        "512",
        "--epochs",
        "1",
        "--rank",
        "16",
        "--lora-alpha",
        "16",
        "--learning-rate",
        "5e-6" if continuation else "1e-5",
        "--batch-size",
        "64",
        "--eval-batch-size",
        "64",
        "--gradient-accumulation",
        "1",
        "--max-steps",
        "24",
        "--eval-steps",
        "25",
        "--save-steps",
        "25",
        "--milestone-steps",
        "6,12,24",
        "--logging-steps",
        "1",
        "--pilot-rows",
        "1536",
        "--validation-rows",
        "256",
        "--expected-train-rows",
        "1536",
        "--expected-validation-rows",
        "256",
        "--expected-planned-steps",
        "24",
        "--private-policy",
        "include",
        "--expected-dataset-fingerprint",
        "037edf28cccff62d90c23e2d6caf56b9998dea6928080f98af2a513f9f92910e",
        "--expected-validation-fingerprint",
        "c056e1744fe148f847354527aa7c7caf6b1fc24fec509f9834d700345e68cc8b",
        "--seed",
        "3407",
        "--dataloader-workers",
        "8",
    ]
    if continuation:
        cmd.extend(
            [
                "--initial-adapter",
                str(root / "runs/csd3-pilots/warm-r16-lr5e6/adapter"),
                "--expected-initial-adapter-tree-sha256",
                "4ec07d3668e9a772573c7f6553319760af00fb28cc1c8743a3c8fe5ce97a0aff",
            ]
        )
    return cmd


def execute(args, cmd: list[str], *, label: str, interrupt: bool = False) -> dict:
    output = Path(cmd[cmd.index("--output") + 1])
    output.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(CUDA_VISIBLE_DEVICES="0", PYTHONUNBUFFERED="1", TOKENIZERS_PARALLELISM="false")
    env.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    started = time.time()
    write(
        args.output_root / f"{label}.argv.json",
        {
            "argv": cmd,
            "cwd": str(args.repo),
            "started_unix": started,
            "trainer_sha256": digest(Path(cmd[1])),
        },
    )
    with (output / "stdout.log").open("a", encoding="utf-8") as log:
        process = subprocess.Popen(
            cmd,
            cwd=args.repo,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        checkpoint = output / "checkpoints/checkpoint-6"
        interrupted = False
        try:
            while process.poll() is None:
                state = checkpoint / "trainer_state.json"
                ready = all(
                    (checkpoint / name).is_file()
                    for name in (
                        "trainer_state.json",
                        "adapter_model.safetensors",
                        "optimizer.pt",
                        "scheduler.pt",
                        "rng_state.pth",
                    )
                )
                if interrupt and ready:
                    # Trainer writes state last. Confirm the parsed step before
                    # signalling only the fresh process group owned here.
                    try:
                        at_step = json.loads(state.read_text())["global_step"]
                    except (OSError, json.JSONDecodeError):
                        at_step = None
                    if at_step == 6:
                        pre = {
                            "schema_version": 1,
                            "signal": "SIGTERM",
                            "signal_number": 15,
                            "pid": process.pid,
                            "checkpoint_step": 6,
                            "checkpoint_path": str(checkpoint),
                            "checkpoint_trainer_state_sha256": digest(state),
                            "pre_resume_resolved_config_sha256": digest(
                                output / "resolved-config.json"
                            ),
                            "running_marker_sha256": digest(output / "RUNNING.json"),
                            "completed_marker_before_signal": (output / "COMPLETED.json").exists(),
                            "signalled_unix": time.time(),
                        }
                        os.killpg(process.pid, signal.SIGTERM)
                        try:
                            returncode = process.wait(timeout=30)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait(timeout=15)
                            raise RuntimeError("owned smoke process did not stop on SIGTERM")
                        pre.update(
                            returncode=returncode,
                            completed_marker_after_signal=(output / "COMPLETED.json").exists(),
                        )
                        if (output / "FAILED.json").exists():
                            pre["failed_marker_sha256"] = digest(output / "FAILED.json")
                        write(args.output_root / "interruption-receipt.json", pre)
                        if returncode != -signal.SIGTERM or pre["completed_marker_after_signal"]:
                            raise RuntimeError(
                                "interruption did not produce the expected incomplete run"
                            )
                        interrupted = True
                        break
                if time.time() - started > 1200:
                    raise TimeoutError("bounded smoke exceeded 20 minutes")
                time.sleep(0.2)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=15)
        if interrupt and not interrupted:
            raise RuntimeError(f"smoke exited before intended interruption: {process.returncode}")
        if not interrupt and (process.returncode != 0 or not (output / "COMPLETED.json").exists()):
            raise RuntimeError(f"smoke did not complete: {process.returncode}; see {output}")
    receipt = {
        "label": label,
        "returncode": process.returncode,
        "elapsed_seconds": round(time.time() - started, 3),
        "output": str(output),
        "stdout_sha256": digest(output / "stdout.log"),
    }
    write(args.output_root / f"{label}.process.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("campaign-root", "repo", "python", "output-root", "warm-base"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    args.output_root = args.output_root.resolve()
    args.output_root.mkdir(parents=True, exist_ok=False)
    try:
        first = execute(args, command(args, continuation=False), label="clean")
        continuing = command(args, continuation=True)
        interrupted = execute(args, continuing, label="continuation-interrupted", interrupt=True)
        resumed = execute(
            args,
            continuing
            + [
                "--resume-from-checkpoint",
                str(args.output_root / "continuation-resume/checkpoints/checkpoint-6"),
            ],
            label="continuation-resumed",
        )
        write(
            args.output_root / "COMPLETED.json",
            {
                "status": "complete",
                "checks": [first, interrupted, resumed],
                "interruption_receipt_sha256": digest(
                    args.output_root / "interruption-receipt.json"
                ),
                "wrapper_sha256": digest(Path(__file__)),
                "completed_unix": time.time(),
            },
        )
    except BaseException as exc:
        write(
            args.output_root / "FAILED.json",
            {
                "status": "failed",
                "exception": type(exc).__name__,
                "message": str(exc),
                "failed_unix": time.time(),
            },
        )
        raise


if __name__ == "__main__":
    main()
