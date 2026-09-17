#!/usr/bin/env python3
"""Run the profiler's own LM adapter through lm-eval on more tasks than the audit's ARC-Easy-50.

Runs INSIDE the reference image so lm-eval, llama-cpp-python and their versions are the
audit's. It evaluates exactly as `adtc_profiler.accuracy.run_benchmark` does (same
`_make_lm` adapter, same `simple_evaluate` seeds) but records every numeric metric of the
task and picks the accuracy metric explicitly: the profiler's `_extract_score` takes the
first numeric key for generative tasks, which for gsm8k in this image is `sample_len` (the
sample count), not `exact_match`. Usage (on muta-vm):
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

METRIC_PRIORITY = (
    "acc_norm,none",
    "acc,none",
    "exact_match,flexible-extract",
    "exact_match,strict-match",
    "exact_match,none",
)


def parse_tasks(spec: str) -> list[tuple[str, int]]:
    out = []
    for item in spec.split(","):
        name, limit = item.split(":")
        out.append((name.strip(), int(limit)))
    names = [name for name, _ in out]
    if len(set(names)) != len(names):
        raise ValueError(f"duplicate task names in {spec!r}; results are keyed by task")
    return out


def pick_metric(task_results: dict) -> tuple[float, str]:
    """The accuracy metric of an lm-eval task result, by explicit priority."""
    for key in METRIC_PRIORITY:
        value = task_results.get(key)
        if isinstance(value, (int, float)):
            return float(value), key
    raise ValueError(f"no accuracy metric among {sorted(task_results)}")


def numeric_metrics(task_results: dict) -> dict[str, float]:
    return {k: float(v) for k, v in task_results.items() if isinstance(v, (int, float))}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 24), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evaluate(model_path: Path, task: str, limit: int, seed: int) -> dict:
    """One task through the profiler's adapter; same call as accuracy.run_benchmark."""
    import lm_eval
    from adtc_profiler import accuracy

    lm = accuracy._make_lm(model_path)
    results = lm_eval.simple_evaluate(
        model=lm,
        tasks=[task],
        limit=limit,
        random_seed=seed,
        numpy_random_seed=seed,
        fewshot_random_seed=seed,
    )
    task_results = results["results"][task]
    n_samples = ((results.get("n-samples") or {}).get(task) or {}).get("effective")
    score, key = pick_metric(task_results)
    profiler = accuracy._extract_score(task_results)
    return {
        "benchmark": task,
        "dataset_version": "lm-eval-harness",
        "language": "en",
        "samples": int(n_samples) if isinstance(n_samples, int) else limit,
        "score": round(score, 4),
        "metric": key.split(",")[0],
        "metric_key": key,
        "metrics": numeric_metrics(task_results),
        "profiler_pick": {"score": profiler[0], "metric": profiler[1]} if profiler else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--tasks", default="arc_easy:500,arc_challenge:100,gsm8k:40")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

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
        row = evaluate(args.model, task, limit, args.seed)
        result[task] = row
        print(json.dumps(row), flush=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    result["complete"] = True
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
