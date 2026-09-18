#!/usr/bin/env python3
"""Launch one preregistered Muta pilot and preserve its complete stdout."""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from campaign_io import sha256_file
from compile_round2_pilots import (
    PilotResultError,
    _batch_settings,
    _verify_protocol_deviation,
    validate_pilot_config,
)


def select_candidate(
    config: dict[str, Any],
    *,
    candidate_id: str | None,
    candidate_index: int | None,
    host_filter: str | None,
) -> dict[str, Any]:
    candidates = config["candidates"]
    if host_filter:
        candidates = [row for row in candidates if row["preferred_host"] == host_filter]
    if candidate_id is not None:
        matches = [row for row in candidates if row["id"] == candidate_id]
        if len(matches) != 1:
            raise ValueError(f"candidate ID is missing or ambiguous: {candidate_id}")
        return matches[0]
    if candidate_index is None or not 0 <= candidate_index < len(candidates):
        raise ValueError(f"candidate index is outside 0..{len(candidates) - 1}")
    return candidates[candidate_index]


def build_command(
    args,
    config: dict[str, Any],
    candidate: dict[str, Any],
    *,
    config_sha256: str,
    protocol_deviation: dict[str, Any] | None,
) -> list[str]:
    shared = config["shared"]
    configured_batch = _batch_settings(config)
    actual_batch = {
        "batch_size": (
            configured_batch["batch_size"] if args.batch_size is None else args.batch_size
        ),
        "eval_batch_size": (
            configured_batch["eval_batch_size"]
            if args.eval_batch_size is None
            else args.eval_batch_size
        ),
        "gradient_accumulation": (
            configured_batch["gradient_accumulation"]
            if args.gradient_accumulation is None
            else args.gradient_accumulation
        ),
    }
    actual_batch["global_batch_per_gpu"] = (
        actual_batch["batch_size"] * actual_batch["gradient_accumulation"]
    )
    allowed_batch = protocol_deviation["actual"] if protocol_deviation else configured_batch
    if actual_batch != allowed_batch:
        raise PilotResultError(
            f"pilot batch treatment {actual_batch} is not frozen/approved {allowed_batch}"
        )
    model = args.clean_base if candidate["lineage"] == "clean" else args.warm_base
    lineage = args.clean_lineage if candidate["lineage"] == "clean" else args.warm_lineage
    output = args.output_root / candidate["id"]
    command = [
        str(args.python),
        str(Path(__file__).resolve().parent / "train_lora_round2.py"),
        "--model",
        str(model),
        "--base-lineage",
        str(lineage),
        "--tokenizer",
        str(args.clean_base),
        "--tokenizer-lineage",
        str(args.clean_lineage),
        "--lineage",
        candidate["lineage"],
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
        str(output),
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
        str(actual_batch["batch_size"]),
        "--eval-batch-size",
        str(actual_batch["eval_batch_size"]),
        "--gradient-accumulation",
        str(actual_batch["gradient_accumulation"]),
        "--warmup-ratio",
        str(shared["warmup_ratio"]),
        "--weight-decay",
        str(shared["weight_decay"]),
        "--eval-steps",
        str(shared["eval_steps"]),
        "--save-steps",
        str(shared["save_steps"]),
        "--logging-steps",
        str(shared["logging_steps"]),
        "--pilot-rows",
        str(config["dataset"]["pilot_rows"]),
        "--expected-train-rows",
        str(config["dataset"]["pilot_rows"]),
        "--expected-validation-rows",
        str(config["validation"]["rows"]),
        "--expected-planned-steps",
        str(
            math.ceil(
                math.ceil(config["dataset"]["pilot_rows"] / actual_batch["global_batch_per_gpu"])
                * float(shared["epochs"])
            )
        ),
        "--private-policy",
        config["dataset"]["private_policy"],
        "--seed",
        str(shared["seed"]),
        "--dataloader-workers",
        str(args.dataloader_workers),
    ]
    if args.resume_from_checkpoint:
        command.extend(["--resume-from-checkpoint", str(args.resume_from_checkpoint)])
    return command


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--candidate-id")
    choice.add_argument("--candidate-index", type=int)
    parser.add_argument("--host-filter")
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
    parser.add_argument("--resume-from-checkpoint", type=Path)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    validate_pilot_config(config)
    config_sha256 = sha256_file(args.config)
    protocol_deviation = _verify_protocol_deviation(
        args.protocol_deviation,
        config_path=args.config.resolve(),
        config=config,
    )
    candidate = select_candidate(
        config,
        candidate_id=args.candidate_id,
        candidate_index=args.candidate_index,
        host_filter=args.host_filter,
    )
    command = build_command(
        args,
        config,
        candidate,
        config_sha256=config_sha256,
        protocol_deviation=protocol_deviation,
    )
    output = args.output_root / candidate["id"]
    output.mkdir(parents=True, exist_ok=True)
    launch_receipts = output / "launch-receipts"
    launch_receipts.mkdir(exist_ok=True)
    launch_path = launch_receipts / f"launch-{time.time_ns()}-{os.getpid()}.json"
    with launch_path.open("x", encoding="utf-8") as handle:
        json.dump(
            {
                "argv": command,
                "candidate": candidate,
                "config": str(args.config.resolve()),
                "config_bytes": args.config.stat().st_size,
                "config_sha256": config_sha256,
                "protocol_deviation": protocol_deviation,
            },
            handle,
            indent=2,
            sort_keys=True,
        )
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
