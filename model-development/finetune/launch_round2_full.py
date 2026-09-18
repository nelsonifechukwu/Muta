#!/usr/bin/env python3
"""Launch one frozen Muta round-two full-run promotion candidate."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from build_round2_promotions import validate_promotion_config
from campaign_io import sha256_file
from compile_round2_pilots import PilotResultError


def load_frozen_config(path: Path) -> tuple[dict[str, Any], str]:
    path = path.resolve()
    digest_path = path.with_suffix(path.suffix + ".sha256")
    try:
        parts = digest_path.read_text(encoding="ascii").strip().split()
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PilotResultError(f"cannot read frozen promotion config: {path}") from exc
    observed = sha256_file(path)
    if len(parts) != 2 or parts[0] != observed or parts[1] != path.name:
        raise PilotResultError("promotion config receipt mismatch")
    if not isinstance(payload, dict):
        raise PilotResultError("promotion config root is not an object")
    validate_promotion_config(payload)
    return payload, observed


def select_candidate(
    config: dict[str, Any], *, candidate_id: str | None, candidate_index: int | None
) -> dict[str, Any]:
    candidates = validate_promotion_config(config)
    if candidate_id is not None:
        matches = [candidate for candidate in candidates if candidate.get("id") == candidate_id]
        if len(matches) != 1:
            raise PilotResultError(f"candidate ID is missing or ambiguous: {candidate_id}")
        return matches[0]
    if candidate_index is None or not 0 <= candidate_index < len(candidates):
        raise PilotResultError(f"candidate index is outside 0..{len(candidates) - 1}")
    return candidates[candidate_index]


def build_command(
    args: argparse.Namespace,
    config: dict[str, Any],
    candidate: dict[str, Any],
    *,
    config_sha256: str,
) -> list[str]:
    shared = config["shared"]
    if args.eval_batch_size is not None and args.eval_batch_size != shared["batch_size"]:
        raise PilotResultError("eval batch override would change the frozen full-run config")
    lineage = candidate["lineage"]
    model = args.clean_base if lineage == "clean" else args.warm_base
    lineage_receipt = args.clean_lineage if lineage == "clean" else args.warm_lineage
    milestones = candidate.get("milestone_steps")
    if not isinstance(milestones, list) or not milestones:
        raise PilotResultError("promotion candidate has no checkpoint milestones")
    if milestones[-1] != candidate.get("planned_steps"):
        raise PilotResultError("final milestone does not match planned steps")
    command = [
        str(args.python),
        str(Path(__file__).resolve().parent / "train_lora_round2.py"),
        "--model",
        str(model),
        "--base-lineage",
        str(lineage_receipt),
        "--tokenizer",
        str(args.clean_base),
        "--tokenizer-lineage",
        str(args.clean_lineage),
        "--lineage",
        lineage,
        "--dataset-manifest",
        str(args.dataset_manifest),
        "--expected-dataset-fingerprint",
        str(config["dataset"]["fingerprint_sha256"]),
        "--validation-manifest",
        str(args.validation_manifest),
        "--expected-validation-fingerprint",
        str(config["validation"]["fingerprint_sha256"]),
        "--campaign-config",
        str(args.config.resolve()),
        "--expected-campaign-config-sha256",
        config_sha256,
        "--output",
        str(args.output_root / candidate["id"]),
        "--run-name",
        candidate["id"],
        "--max-length",
        str(shared["max_length"]),
        "--epochs",
        str(shared["epochs"]),
        "--learning-rate",
        str(candidate["learning_rate"]),
        "--rank",
        str(candidate["rank"]),
        "--lora-alpha",
        str(candidate["rank"]),
        "--batch-size",
        str(shared["batch_size"]),
        "--eval-batch-size",
        str(shared["batch_size"]),
        "--gradient-accumulation",
        str(shared["gradient_accumulation"]),
        "--warmup-ratio",
        str(shared["warmup_ratio"]),
        "--weight-decay",
        str(shared["weight_decay"]),
        "--logging-steps",
        str(shared["logging_steps"]),
        "--private-policy",
        candidate["private_policy"],
        "--seed",
        str(shared["seed"]),
        "--dataloader-workers",
        str(args.dataloader_workers),
        "--expected-train-rows",
        str(candidate["planned_rows"]),
        "--expected-validation-rows",
        str(config["validation"]["rows"]),
        "--expected-planned-steps",
        str(candidate["planned_steps"]),
        "--milestone-steps",
        ",".join(str(step) for step in milestones),
    ]
    if args.resume_from_checkpoint:
        command.extend(["--resume-from-checkpoint", str(args.resume_from_checkpoint)])
    return command


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--candidate-id")
    choice.add_argument("--candidate-index", type=int)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--clean-base", type=Path, required=True)
    parser.add_argument("--warm-base", type=Path, required=True)
    parser.add_argument("--clean-lineage", type=Path, required=True)
    parser.add_argument("--warm-lineage", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--validation-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--eval-batch-size", type=int)
    parser.add_argument("--dataloader-workers", type=int, default=8)
    parser.add_argument("--resume-from-checkpoint", type=Path)
    args = parser.parse_args(argv)
    if args.eval_batch_size is not None and args.eval_batch_size < 1:
        parser.error("--eval-batch-size must be positive")
    return args


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    config, config_sha256 = load_frozen_config(args.config)
    candidate = select_candidate(
        config,
        candidate_id=args.candidate_id,
        candidate_index=args.candidate_index,
    )
    command = build_command(args, config, candidate, config_sha256=config_sha256)
    output = (args.output_root / candidate["id"]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    launch_receipt = {
        "argv": command,
        "candidate": candidate,
        "config": str(args.config.resolve()),
        "config_bytes": args.config.stat().st_size,
        "config_sha256": config_sha256,
    }
    launch_receipts = output / "launch-receipts"
    launch_receipts.mkdir(exist_ok=True)
    launch_path = launch_receipts / f"launch-{time.time_ns()}-{os.getpid()}.json"
    with launch_path.open("x", encoding="utf-8") as handle:
        json.dump(launch_receipt, handle, indent=2, sort_keys=True)
        handle.write("\n")
    environment = os.environ.copy()
    environment.setdefault("TOKENIZERS_PARALLELISM", "false")
    environment.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    with (output / "stdout.log").open("a", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=environment,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            log.write(line)
            log.flush()
        return_code = process.wait()
    if return_code:
        raise SystemExit(return_code)


if __name__ == "__main__":
    main()
