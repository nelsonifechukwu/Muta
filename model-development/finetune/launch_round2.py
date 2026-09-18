#!/usr/bin/env python3
"""Launch one preregistered Muta pilot and preserve its complete stdout."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


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


def build_command(args, config: dict[str, Any], candidate: dict[str, Any]) -> list[str]:
    shared = config["shared"]
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
        "--validation-manifest",
        str(args.validation_manifest),
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
        str(args.batch_size or shared["batch_size"]),
        "--eval-batch-size",
        str(args.eval_batch_size or args.batch_size or shared["batch_size"]),
        "--gradient-accumulation",
        str(args.gradient_accumulation or shared["gradient_accumulation"]),
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
    parser.add_argument("--dataloader-workers", type=int, default=4)
    parser.add_argument("--resume-from-checkpoint", type=Path)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    candidate = select_candidate(
        config,
        candidate_id=args.candidate_id,
        candidate_index=args.candidate_index,
        host_filter=args.host_filter,
    )
    command = build_command(args, config, candidate)
    output = args.output_root / candidate["id"]
    output.mkdir(parents=True, exist_ok=True)
    (output / "launch-command.json").write_text(
        json.dumps(
            {
                "argv": command,
                "candidate": candidate,
                "config": str(args.config.resolve()),
                "config_bytes": args.config.stat().st_size,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
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
