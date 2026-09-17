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
import json
from pathlib import Path


def parse_tasks(spec: str) -> list[tuple[str, int]]:
    out = []
    for item in spec.split(","):
        name, limit = item.split(":")
        out.append((name.strip(), int(limit)))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--tasks", default="arc_easy:500,arc_challenge:100,gsm8k:40")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from adtc_profiler import accuracy

    result: dict = {"model": str(args.model), "seed": args.seed}
    for task, limit in parse_tasks(args.tasks):
        row = accuracy.run_benchmark(args.model, task=task, limit=limit, seed=args.seed)
        result[task] = row
        print(json.dumps(row), flush=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
