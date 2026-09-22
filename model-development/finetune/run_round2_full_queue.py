"""One-GPU Oracle queue: fresh clean, then selected-pilot continuation.

Fresh runs only. No automatic retries, checkpoint resumes, GPU sharing, or process
termination. If this controller times out or is interrupted, its already-created
child is left untouched and its PID/output receipts prevent accidental relaunch.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from campaign_io import sha256_file
from launch_round2_full import load_frozen_config, select_candidate

CANDIDATES = (
    "full-best-clean-private-enriched",
    "full-best-warm-pilot-continuation",
)


def write_json(path: Path, data: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def status(root: Path, data: dict[str, Any]) -> None:
    temporary = root / f".status-{os.getpid()}-{time.time_ns()}.json"
    write_json(temporary, {"updated_unix": time.time(), **data})
    os.replace(temporary, root / "status.json")


def gpu_lock_path(gpu: int) -> Path:
    return Path("/tmp") / f"muta-round2-full-uid-{os.getuid()}-gpu-{gpu}.lock"


def acquire_gpu_lock(gpu: int) -> int:
    """One advisory lock across our queues, even with different output roots."""
    descriptor = os.open(gpu_lock_path(gpu), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(descriptor)
        if info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode):
            raise RuntimeError("GPU lock is not a regular file owned by this user")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(
                "Another queue or preserved child owns the GPU lock; no work disturbed"
            ) from exc
        os.ftruncate(descriptor, 0)
        os.write(
            descriptor,
            json.dumps({"pid": os.getpid(), "gpu": gpu, "acquired_unix": time.time()}).encode(),
        )
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def check_gpu_idle(gpu: int) -> dict[str, Any]:
    process = subprocess.run(
        [
            "nvidia-smi",
            f"--id={gpu}",
            "--query-compute-apps=pid,process_name",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    receipt = {
        "gpu": gpu,
        "checked_unix": time.time(),
        "returncode": process.returncode,
        "stdout": process.stdout,
        "stderr": process.stderr,
    }
    if process.returncode != 0:
        raise RuntimeError(f"Cannot verify GPU {gpu} is idle: {process.stderr.strip()}")
    if process.stdout.strip():
        raise RuntimeError(
            f"GPU {gpu} has active compute processes; preserved without interference"
        )
    return receipt


def launch_command(args: argparse.Namespace, candidate_id: str) -> list[str]:
    if candidate_id not in CANDIDATES:
        raise ValueError("Oracle queue only accepts the clean and continuation treatments")
    command = [
        str(args.python),
        str(Path(__file__).parent / "launch_round2_full.py"),
        "--config",
        str(args.config),
        "--expected-config-sha256",
        args.expected_config_sha256,
        "--candidate-id",
        candidate_id,
        "--python",
        str(args.python),
    ]
    for name in (
        "clean_base",
        "warm_base",
        "clean_lineage",
        "warm_lineage",
        "dataset_manifest",
        "validation_manifest",
        "output_root",
    ):
        command.extend(["--" + name.replace("_", "-"), str(getattr(args, name))])
    command.extend(["--dataloader-workers", str(args.dataloader_workers)])
    if candidate_id == CANDIDATES[1]:
        command.extend(["--initial-adapter", str(args.initial_adapter)])
    return command


def completed_stage(output: Path, candidate: dict, config_sha: str, config: dict) -> dict[str, Any]:
    if any((output / name).exists() for name in ("RUNNING.json", "FAILED.json")):
        raise RuntimeError("Stage has a conflicting live/failed marker; do not start the next run")
    terminal_path = output / "COMPLETED.json"
    manifest_path = output / "training-manifest.json"
    if terminal_path.is_symlink() or manifest_path.is_symlink():
        raise RuntimeError("Stage completion evidence cannot be a symlink")
    terminal = json.loads(terminal_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    expected_base = config["runtime_input_authority"]["lineages"][candidate["lineage"]][
        "base_tree_sha256"
    ]
    if (
        terminal.get("run_name") != candidate["id"]
        or terminal.get("training_manifest_sha256") != sha256_file(manifest_path)
        or manifest.get("run_name") != candidate["id"]
        or manifest.get("trainer_global_step") != candidate["planned_steps"]
        or manifest.get("planned_steps") != candidate["planned_steps"]
        or manifest.get("pilot_rows") is not None
        or manifest.get("tokenization", {}).get("train", {}).get("rows")
        != candidate["planned_rows"]
        or manifest.get("private_policy") != "include"
        or manifest.get("campaign_config", {}).get("sha256") != config_sha
        or manifest.get("lineage") != candidate["lineage"]
        or manifest.get("rank") != candidate["rank"]
        or manifest.get("learning_rate") != candidate["learning_rate"]
        or manifest.get("base_lineage", {}).get("observed", {}).get("tree_sha256") != expected_base
        or manifest.get("scripts", {}).get("train_lora_round2.py")
        != config["source_code"]["trainer_sha256"]
        or manifest.get("resume", {}).get("requested") is not False
    ):
        raise RuntimeError("Stage terminal/manifest does not prove the frozen full-data run")
    expected_initial = candidate.get("initial_adapter_tree_sha256")
    receipt, loaded = manifest.get("initial_adapter_receipt"), manifest.get("initial_adapter_load")
    if expected_initial is None:
        if receipt is not None or loaded is not None:
            raise RuntimeError("Fresh clean stage must not contain an initializer")
    elif (
        not isinstance(receipt, dict)
        or not isinstance(loaded, dict)
        or receipt.get("inventory", {}).get("tree_sha256") != expected_initial
        or receipt.get("training_base_tree_sha256") != expected_base
        or receipt.get("training_manifest_sha256")
        != candidate["source_pilot_training_manifest_sha256"]
        or loaded.get("operation") != "copy_exact_adapter_tensors_once_no_merge"
        or loaded.get("exact_source_values_loaded") is not True
        or not re.fullmatch(r"[0-9a-f]{64}", str(loaded.get("source_tensor_sha256", "")))
        or loaded.get("source_tensor_sha256") != loaded.get("loaded_tensor_sha256")
        or loaded.get("source_tree_sha256_before") != expected_initial
        or loaded.get("source_tree_sha256_after") != expected_initial
    ):
        raise RuntimeError(
            "Continuation completion does not prove the exact pilot initializer was loaded once"
        )
    return {
        "completed_sha256": sha256_file(terminal_path),
        "training_manifest_sha256": sha256_file(manifest_path),
        "completed_steps": manifest["trainer_global_step"],
        "training_rows": manifest["tokenization"]["train"]["rows"],
    }


def run_queue(args: argparse.Namespace) -> dict[str, Any]:
    # This atomic mkdir is the queue's lock. Never reuse it, even after failure.
    args.queue_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    started = {
        "schema_version": 1,
        "queue_pid": os.getpid(),
        "started_unix": time.time(),
        "queue_script_sha256": sha256_file(Path(__file__)),
        "config": str(args.config),
        "expected_config_sha256": args.expected_config_sha256,
        "candidate_order": list(CANDIDATES),
        "gpu": args.gpu,
        "max_stage_seconds": args.max_stage_seconds,
        "policy": "fresh_only_sequential_no_retry_preserve_existing_processes",
    }
    write_json(args.queue_dir / "queue-start.json", started)
    status(args.queue_dir, {"state": "preflight", "queue_pid": os.getpid()})
    stages: list[dict[str, Any]] = []
    active_pid: int | None = None
    active_id: str | None = None
    lock_fd: int | None = None
    try:
        config, config_sha = load_frozen_config(
            args.config, expected_sha256=args.expected_config_sha256
        )
        if config.get("schema_version") != 3:
            raise ValueError("Oracle queue requires the current three-treatment schema v3")
        candidates = [
            select_candidate(config, candidate_id=value, candidate_index=None)
            for value in CANDIDATES
        ]
        for candidate in candidates:
            output = args.output_root / candidate["id"]
            if output.exists() or output.is_symlink():
                raise FileExistsError(
                    f"Existing candidate output is preserved; refusing restart: {output}"
                )
        lock_fd = acquire_gpu_lock(args.gpu)
        write_json(
            args.queue_dir / "gpu-lock.json",
            {
                "path": str(gpu_lock_path(args.gpu)),
                "queue_pid": os.getpid(),
                "inherited_by_stage_controllers": True,
            },
        )
        for index, candidate in enumerate(candidates, 1):
            active_id = candidate["id"]
            idle = check_gpu_idle(args.gpu)
            write_json(args.queue_dir / f"stage-{index}-gpu-preflight.json", idle)
            # Exclusive claim also closes the race with another queue for this run.
            output = args.output_root / active_id
            output.mkdir(parents=True, exist_ok=False)
            command = launch_command(args, active_id)
            write_json(args.queue_dir / f"stage-{index}-argv.json", {"argv": command})
            environment = os.environ.copy()
            environment.update(CUDA_VISIBLE_DEVICES=str(args.gpu), PYTHONUNBUFFERED="1")
            with (args.queue_dir / f"stage-{index}-controller.log").open(
                "x", encoding="utf-8"
            ) as log:
                process = subprocess.Popen(
                    command,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    env=environment,
                    start_new_session=True,
                    pass_fds=(lock_fd,),
                )
                active_pid = process.pid
                write_json(
                    args.queue_dir / f"stage-{index}-started.json",
                    {
                        "candidate_id": active_id,
                        "pid": active_pid,
                        "started_unix": time.time(),
                        "output": str(output),
                        "argv_sha256": sha256_file(args.queue_dir / f"stage-{index}-argv.json"),
                    },
                )
                status(
                    args.queue_dir,
                    {
                        "state": "running",
                        "queue_pid": os.getpid(),
                        "candidate_id": active_id,
                        "child_pid": active_pid,
                    },
                )
                try:
                    returncode = process.wait(timeout=args.max_stage_seconds)
                except BaseException:
                    # Never kill a healthy existing process or silently retry it.
                    # Retain the actual liveness in the failure receipt instead.
                    if process.poll() is not None:
                        active_pid = None
                    raise
            active_pid = None
            exit_record = {
                "candidate_id": active_id,
                "pid": process.pid,
                "returncode": returncode,
                "finished_unix": time.time(),
                "output": str(output),
            }
            write_json(args.queue_dir / f"stage-{index}-exit.json", exit_record)
            if returncode != 0:
                raise RuntimeError(
                    f"{active_id} failed with exit {returncode}; queue stopped without retry"
                )
            proof = completed_stage(output, candidate, config_sha, config)
            stage = {**exit_record, **proof}
            write_json(args.queue_dir / f"stage-{index}-completed.json", stage)
            stages.append(stage)
        result = {
            "state": "complete",
            "queue_pid": os.getpid(),
            "completed_unix": time.time(),
            "config_sha256": config_sha,
            "stages": stages,
        }
        write_json(args.queue_dir / "COMPLETED.json", result)
        status(args.queue_dir, result)
        return result
    except BaseException as exc:
        failed = {
            "state": "stopped",
            "queue_pid": os.getpid(),
            "stopped_unix": time.time(),
            "exception": type(exc).__name__,
            "message": str(exc),
            "candidate_id": active_id,
            "child_pid_preserved": active_pid,
            "completed_stages": stages,
            "automatic_retry": False,
        }
        write_json(args.queue_dir / "FAILED.json", failed)
        status(args.queue_dir, failed)
        raise
    finally:
        if lock_fd is not None:
            # Do not LOCK_UN: the same open-file description may still be held
            # by our preserved launcher child. Closing only our copy lets that
            # child retain exclusivity through its own exit.
            os.close(lock_fd)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "config",
        "queue-dir",
        "output-root",
        "clean-base",
        "warm-base",
        "clean-lineage",
        "warm-lineage",
        "dataset-manifest",
        "validation-manifest",
        "initial-adapter",
    ):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--expected-config-sha256", required=True)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--gpu", type=int, default=0)
    parser.add_argument("--dataloader-workers", type=int, default=8)
    parser.add_argument("--max-stage-seconds", type=int, default=21600)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{64}", args.expected_config_sha256):
        parser.error("--expected-config-sha256 must be a lowercase SHA256")
    if args.gpu < 0 or args.dataloader_workers < 0 or args.max_stage_seconds < 1:
        parser.error("GPU/workers must be nonnegative and the stage timeout positive")
    for name, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, name, value.absolute())
    if args.queue_dir == args.output_root or args.output_root in args.queue_dir.parents:
        parser.error("queue receipts must be outside the full-run output tree")
    return args


def main(argv: list[str] | None = None) -> None:
    def interrupted(signum, _frame):
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, interrupted)
    run_queue(parse_args(argv))


if __name__ == "__main__":
    main()
