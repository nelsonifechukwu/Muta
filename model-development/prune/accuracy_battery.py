#!/usr/bin/env python3
"""Run the profiler's own accuracy function on more tasks than the audit's ARC-Easy-50.

Runs INSIDE the reference image so lm-eval, llama-cpp-python and their versions are the
audit's. Usage (on muta-vm):
  sudo docker run --rm -v ~/adtc-prune:/w -v ~/adtc-prune/hfcache:/root/.cache/huggingface \
    --entrypoint python adtc-profiler:latest /w/accuracy_battery.py \
    --model /w/subs/heal-21L-contiguous-lr5e5-1000/model/heal-21L-contiguous-lr5e5-1000-Q4_K_M.gguf \
    --tasks arc_easy:500,arc_challenge:100,gsm8k:40 \
    --output /w/artifacts/battery-heal-21L-contiguous-lr5e5-1000.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def parse_tasks(spec: str) -> list[tuple[str, int]]:
    out = []
    for item in spec.split(","):
        name, limit = item.split(":")
        out.append((name.strip(), int(limit)))
    names = [name for name, _ in out]
    if len(set(names)) != len(names):
        raise ValueError(f"duplicate task names in {spec!r}; results are keyed by task")
    return out


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 24), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--tasks", default="arc_easy:500,arc_challenge:100,gsm8k:40")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from adtc_profiler import accuracy

    tasks = parse_tasks(args.tasks)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result: dict = {
        "model": str(args.model),
        "model_sha256": sha256_file(args.model),
        "seed": args.seed,
        "tasks_requested": [f"{task}:{limit}" for task, limit in tasks],
        "complete": False,
    }
    for task, limit in tasks:
        row = accuracy.run_benchmark(args.model, task=task, limit=limit, seed=args.seed)
        result[task] = row
        print(json.dumps(row), flush=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    result["complete"] = True
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
