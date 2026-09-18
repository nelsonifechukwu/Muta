#!/usr/bin/env python3
"""Run preregistered Oracle pilots sequentially with restart-safe receipts."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from campaign_io import sha256_file


def select_candidate_ids(
    config: dict[str, Any], *, host_filter: str, requested: list[str] | None
) -> list[str]:
    candidates = config["candidates"]
    ids = [row["id"] for row in candidates]
    if len(set(ids)) != len(ids):
        raise ValueError("candidate IDs must be unique")
    eligible = [row["id"] for row in candidates if row["preferred_host"] == host_filter]
    if not requested:
        return eligible
    unknown = sorted(set(requested) - set(ids))
    if unknown:
        raise ValueError(f"unknown candidate IDs: {', '.join(unknown)}")
    wrong_host = sorted(set(requested) - set(eligible))
    if wrong_host:
        raise ValueError(f"candidates do not belong to host {host_filter}: {', '.join(wrong_host)}")
    if len(set(requested)) != len(requested):
        raise ValueError("requested candidate IDs must be unique")
    return requested


def latest_checkpoint(run_dir: Path) -> Path | None:
    checkpoints: list[tuple[int, Path]] = []
    for path in run_dir.glob("checkpoints/checkpoint-*"):
        try:
            step = int(path.name.removeprefix("checkpoint-"))
        except ValueError:
            continue
        if (path / "trainer_state.json").is_file():
            checkpoints.append((step, path))
    return max(checkpoints, default=(0, None), key=lambda item: item[0])[1]


def running_process_alive(marker: Path) -> bool:
    if not marker.is_file():
        return False
    try:
        receipt = json.loads(marker.read_text(encoding="utf-8"))
        pid = int(receipt["pid"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False
    marker_host = receipt.get("hostname")
    if marker_host and marker_host != platform.node():
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def build_launcher_command(
    args: argparse.Namespace, candidate_id: str, checkpoint: Path | None
) -> list[str]:
    command = [
        str(args.python),
        str(Path(__file__).resolve().parent / "launch_round2.py"),
        "--config",
        str(args.config),
        "--candidate-id",
        candidate_id,
        "--host-filter",
        args.host_filter,
        "--python",
        str(args.python),
        "--clean-base",
        str(args.clean_base),
        "--warm-base",
        str(args.warm_base),
        "--clean-lineage",
        str(args.clean_lineage),
        "--warm-lineage",
        str(args.warm_lineage),
        "--dataset-manifest",
        str(args.dataset_manifest),
        "--validation-manifest",
        str(args.validation_manifest),
        "--output-root",
        str(args.output_root),
        "--dataloader-workers",
        str(args.dataloader_workers),
    ]
    if args.protocol_deviation is not None:
        command.extend(["--protocol-deviation", str(args.protocol_deviation)])
    for option, value in (
        ("--batch-size", args.batch_size),
        ("--eval-batch-size", args.eval_batch_size),
        ("--gradient-accumulation", args.gradient_accumulation),
    ):
        if value is not None:
            command.extend([option, str(value)])
    if checkpoint is not None:
        command.extend(["--resume-from-checkpoint", str(checkpoint)])
    return command


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _event(state: dict[str, Any], event: str, **details: Any) -> None:
    state["events"].append({"event": event, "unix": time.time(), **details})


def run_queue(args: argparse.Namespace) -> int:
    args.output_root.mkdir(parents=True, exist_ok=True)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    candidate_ids = select_candidate_ids(
        config,
        host_filter=args.host_filter,
        requested=args.candidate_id,
    )
    state_path = args.output_root / f"{args.host_filter}-queue-state.json"
    lock_path = args.output_root / f".{args.host_filter}-queue.lock"
    with lock_path.open("w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"another {args.host_filter} pilot queue is active") from exc
        prior_events: list[dict[str, Any]] = []
        original_started = time.time()
        if state_path.is_file():
            try:
                prior = json.loads(state_path.read_text(encoding="utf-8"))
                if prior.get("config_sha256") == sha256_file(args.config):
                    prior_events = prior.get("events", [])
                    original_started = prior.get("started_unix", original_started)
            except (OSError, TypeError, json.JSONDecodeError):
                pass
        state = {
            "schema_version": 1,
            "config": str(args.config.resolve()),
            "config_sha256": sha256_file(args.config),
            "host_filter": args.host_filter,
            "hostname": platform.node(),
            "pid": os.getpid(),
            "started_unix": original_started,
            "session_started_unix": time.time(),
            "candidate_ids": candidate_ids,
            "current": None,
            "events": prior_events,
        }
        _event(state, "queue_started", resumed=bool(prior_events))
        _write_json_atomic(state_path, state)
        failures = 0
        for candidate_id in candidate_ids:
            run_dir = args.output_root / candidate_id
            if (run_dir / "COMPLETED.json").is_file():
                _event(state, "candidate_skipped_completed", candidate_id=candidate_id)
                _write_json_atomic(state_path, state)
                continue
            if running_process_alive(run_dir / "RUNNING.json"):
                failures += 1
                _event(state, "candidate_skipped_active", candidate_id=candidate_id)
                _write_json_atomic(state_path, state)
                if args.stop_on_error:
                    break
                continue
            checkpoint = None if args.no_resume else latest_checkpoint(run_dir)
            command = build_launcher_command(args, candidate_id, checkpoint)
            state["current"] = candidate_id
            _event(
                state,
                "candidate_started",
                candidate_id=candidate_id,
                checkpoint=str(checkpoint) if checkpoint else None,
                argv=command,
            )
            _write_json_atomic(state_path, state)
            return_code = subprocess.run(command, check=False).returncode
            event = "candidate_completed" if return_code == 0 else "candidate_failed"
            _event(
                state,
                event,
                candidate_id=candidate_id,
                return_code=return_code,
            )
            state["current"] = None
            _write_json_atomic(state_path, state)
            if return_code:
                failures += 1
                if args.stop_on_error:
                    break
        state["finished_unix"] = time.time()
        state["status"] = "completed" if failures == 0 else "completed_with_failures"
        state["failure_count"] = failures
        _event(state, "queue_finished", failure_count=failures)
        _write_json_atomic(state_path, state)
        return 1 if failures else 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--candidate-id", action="append")
    parser.add_argument("--host-filter", default="oracle")
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--clean-base", type=Path, required=True)
    parser.add_argument("--warm-base", type=Path, required=True)
    parser.add_argument("--clean-lineage", type=Path, required=True)
    parser.add_argument("--warm-lineage", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--validation-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--eval-batch-size", type=int)
    parser.add_argument("--gradient-accumulation", type=int)
    parser.add_argument("--protocol-deviation", type=Path)
    parser.add_argument("--dataloader-workers", type=int, default=4)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--stop-on-error", action="store_true")
    return parser.parse_args(argv)


def main() -> None:
    raise SystemExit(run_queue(parse_args()))


if __name__ == "__main__":
    main()
