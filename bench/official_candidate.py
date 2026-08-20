"""Run one exact GGUF through the bundled ADTC participant profiler.

This is the slow confirmation path for campaign finalists. It synthesizes the submission
directory from the checked-in claims, replaces only the candidate-specific model fields, and
lets the profiler perform throughput, whole-tree RSS, ARC-Easy and schema validation.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from bench.adtc.submission import synthesize


def _candidate_metadata(
    submission_dir: Path, *, name: str, quantization: str, packaging: str
) -> None:
    path = submission_dir / "metadata.json"
    data = json.loads(path.read_text())
    model = data.setdefault("model", {})
    model["name"] = name
    model["quantization"] = quantization
    model["packaging"] = packaging
    path.write_text(json.dumps(data, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--quantization", required=True)
    parser.add_argument("--submission-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profiler", type=Path, required=True)
    parser.add_argument("--llama-bench-dir", type=Path, required=True)
    parser.add_argument("--packaging", default="exact_gguf_campaign_artifact")
    parser.add_argument("--skip-accuracy", action="store_true")
    args = parser.parse_args(argv)

    if not args.model.is_file():
        parser.error(f"model does not exist: {args.model}")
    if not args.profiler.is_file():
        parser.error(f"profiler does not exist: {args.profiler}")
    if not (args.llama_bench_dir / "llama-bench").is_file():
        parser.error(f"llama-bench does not exist in: {args.llama_bench_dir}")

    submission_dir = synthesize(args.model.resolve(), dest=args.submission_dir.resolve())
    _candidate_metadata(
        submission_dir,
        name=args.name,
        quantization=args.quantization,
        packaging=args.packaging,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(args.profiler.resolve()),
        "run",
        "--submission",
        str(submission_dir),
        "--mode",
        "participant",
        "--output",
        str(args.output.resolve()),
    ]
    if args.skip_accuracy:
        command.append("--skip-accuracy")
    env = dict(os.environ)
    env["PATH"] = f"{args.llama_bench_dir.resolve()}{os.pathsep}{env.get('PATH', '')}"
    print("running:", " ".join(command), flush=True)
    completed = subprocess.run(command, env=env, timeout=6 * 3600, check=False)
    if completed.returncode:
        return completed.returncode
    report = json.loads(args.output.read_text())
    throughput = report.get("throughput") or {}
    memory = report.get("memory") or {}
    accuracy = next(
        (row for row in report.get("accuracy", []) if row.get("benchmark") == "arc_easy"),
        {},
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "generation_tps": throughput.get("tokens_per_second_generation"),
                "peak_rss_mb": memory.get("peak_rss_mb"),
                "arc_easy": accuracy.get("score"),
                "samples": accuracy.get("samples"),
                "params_match": (report.get("model_info") or {}).get("params_match"),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
