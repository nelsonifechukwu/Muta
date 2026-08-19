"""Aggregate one-host GGUF campaign evidence without mixing incompatible runs.

The raw JSONL written by :mod:`bench.adtc_bakeoff` is append-only. This module refuses to
pool different hardware contexts or benchmark binary hashes, computes means and sample
standard deviations for repeated throughput rows, and scores the measured accuracy proxy
through the official profiler's capped 15 tok/s formula.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

from bench.score import score


def _read_rows(path: Path) -> list[dict]:
    rows = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{number}: invalid JSON: {exc}") from exc
    return rows


def _mean_sd(values: list[float]) -> tuple[float, float]:
    return statistics.mean(values), statistics.stdev(values) if len(values) > 1 else 0.0


def _wilson95(success_rate: float, samples: int) -> tuple[float, float]:
    """95% Wilson interval for a binomial accuracy proportion."""
    if samples <= 0:
        return 0.0, 1.0
    z = 1.959963984540054
    z2 = z * z
    denominator = 1.0 + z2 / samples
    centre = (success_rate + z2 / (2.0 * samples)) / denominator
    radius = (
        z
        * math.sqrt(success_rate * (1.0 - success_rate) / samples + z2 / (4.0 * samples * samples))
        / denominator
    )
    return max(0.0, centre - radius), min(1.0, centre + radius)


def summarize(
    rows: list[dict],
    *,
    tps_maxes: list[float],
    accuracy_task: str,
    performance_formula: str = "profiler_capped",
) -> dict:
    if performance_formula == "profiler_capped" and tps_maxes != [15.0]:
        raise ValueError("profiler_capped requires exactly one TPS reference: 15")
    failed = [row for row in rows if row.get("ok") is not True]
    if failed:
        labels = sorted(
            {str(row.get("model") or row.get("model_path") or "unknown-model") for row in failed}
        )
        raise ValueError(
            f"refusing to rank evidence containing {len(failed)} failed row(s): {labels}"
        )
    good = [row for row in rows if row.get("ok")]
    throughput_rows = [row for row in good if row.get("kind") == "throughput"]
    contexts = {row.get("hardware_context") for row in throughput_rows}
    if len(contexts) != 1 or None in contexts:
        raise ValueError(f"refusing to pool hardware contexts: {sorted(map(str, contexts))}")
    identities = {row.get("bench_identity", {}).get("sha256") for row in throughput_rows}
    if len(identities) != 1 or None in identities:
        raise ValueError(f"refusing to pool benchmark binaries: {sorted(map(str, identities))}")
    profiler_root_estimates = {
        row.get("profiler_python_overhead_mib_note") for row in throughput_rows
    }
    if len(profiler_root_estimates) != 1 or None in profiler_root_estimates:
        raise ValueError(
            "refusing to rank throughput without one consistent profiler-root RSS estimate: "
            f"{sorted(map(str, profiler_root_estimates))}"
        )
    profiler_root_estimate = float(next(iter(profiler_root_estimates)))

    by_model: dict[str, list[dict]] = defaultdict(list)
    for row in good:
        by_model[row["model"]].append(row)

    models = []
    for model_name, model_rows in sorted(by_model.items()):
        model_hashes = {row.get("model_sha256") for row in model_rows}
        if len(model_hashes) != 1 or None in model_hashes:
            raise ValueError(
                f"refusing to pool different artifacts named {model_name}: "
                f"{sorted(map(str, model_hashes))}"
            )
        perf = [row for row in model_rows if row.get("kind") == "throughput"]
        accuracy_rows = [
            row
            for row in model_rows
            if row.get("kind") == "accuracy" and row.get("benchmark") == accuracy_task
        ]
        accuracy_by_task: dict[str, dict] = {}
        for task in sorted(
            {row.get("benchmark") for row in model_rows if row.get("kind") == "accuracy"} - {None}
        ):
            task_rows = [
                row
                for row in model_rows
                if row.get("kind") == "accuracy" and row.get("benchmark") == task
            ]
            task_score = statistics.mean(float(row["score"]) for row in task_rows)
            task_samples = sum(int(row["samples"]) for row in task_rows)
            ci_low, ci_high = _wilson95(task_score, task_samples)
            accuracy_by_task[str(task)] = {
                "score_percent": round(task_score * 100.0, 4),
                "samples": task_samples,
                "metric": task_rows[0].get("metric"),
                "ci95_percent": [round(ci_low * 100.0, 2), round(ci_high * 100.0, 2)],
            }
        if not perf:
            continue
        tps = []
        for row in perf:
            tg_raw = next(
                (
                    item
                    for item in row.get("raw_bench_rows", [])
                    if item.get("n_gen") and not item.get("n_prompt")
                ),
                None,
            )
            samples = (tg_raw or {}).get("samples_ts") or []
            tps.extend(float(value) for value in samples)
            if not samples:
                tps.append(float(row["tg_avg_ts"]))
        rss = [
            float(row["peak_rss_tree_mb"])
            + float(row.get("profiler_python_overhead_mib_note") or 0.0)
            for row in perf
        ]
        tps_mean, tps_sd = _mean_sd(tps)
        rss_mean, rss_sd = _mean_sd(rss)
        accuracy = None
        accuracy_samples = None
        if accuracy_rows:
            accuracy = statistics.mean(float(row["score"]) for row in accuracy_rows) * 100.0
            accuracy_samples = sum(int(row["samples"]) for row in accuracy_rows)

        scores = {}
        if accuracy is not None:
            for denominator in tps_maxes:
                effective_denominator = (
                    max(denominator, tps_mean)
                    if performance_formula == "website_relative"
                    else denominator
                )
                result = score(
                    accuracy=accuracy,
                    tps_actual=tps_mean,
                    peak_rss_gb=rss_mean / 1024.0,
                    tps_max=effective_denominator,
                    tps_max_provenance=(
                        "profiler_reference"
                        if performance_formula == "profiler_capped"
                        else "cohort_observed"
                    ),
                    performance_formula=performance_formula,
                    max_temp_c=None,
                    label=model_name,
                )
                scores[str(denominator)] = {
                    "s_total": round(result.s_total, 4),
                    "s_acc": round(result.s_acc, 4),
                    "s_perf": round(result.s_perf, 4),
                    "s_eff": round(result.s_eff, 4),
                    "effective_tps_max": round(effective_denominator, 4),
                }

        first = perf[0]
        commands = sorted({tuple(str(part) for part in row.get("command", [])) for row in perf})
        repetition_modes = {
            "single_repeat_screen"
            if "-r" in command and command[command.index("-r") + 1] == "1"
            else "profiler_default_repetitions"
            for command in commands
        }
        models.append(
            {
                "model": model_name,
                "model_sha256": first.get("model_sha256"),
                "model_bytes": first.get("model_bytes"),
                "throughput_rounds": len(perf),
                "throughput_repetitions": len(tps),
                "measurement_tier": (
                    next(iter(repetition_modes)) if len(repetition_modes) == 1 else "mixed"
                ),
                "commands": [list(command) for command in commands],
                "tg_tps_mean": round(tps_mean, 4),
                "tg_tps_sd": round(tps_sd, 4),
                "peak_rss_mib_mean": round(rss_mean, 2),
                "peak_rss_mib_sd": round(rss_sd, 2),
                "rss_accounting": (
                    "measured llama-bench child-tree peak plus the raw row's "
                    f"{profiler_root_estimate:g} MiB official-profiler-root estimate"
                ),
                "rss_estimated": True,
                "accuracy_proxy_task": accuracy_task,
                "accuracy_proxy": round(accuracy, 4) if accuracy is not None else None,
                "accuracy_samples": accuracy_samples,
                "accuracy_tasks": accuracy_by_task,
                "scores": scores,
            }
        )

    winners = {}
    for denominator in tps_maxes:
        key = str(denominator)
        ranked = [model for model in models if key in model["scores"]]
        if ranked:
            winner = max(ranked, key=lambda model: model["scores"][key]["s_total"])
            winners[key] = {
                "model": winner["model"],
                "model_sha256": winner["model_sha256"],
                "s_total": winner["scores"][key]["s_total"],
            }

    return {
        "schema_version": 1,
        "hardware_context": next(iter(contexts), None),
        "accuracy_hardware_contexts": sorted(
            {str(row.get("hardware_context")) for row in good if row.get("kind") == "accuracy"}
        ),
        "benchmark_binary_sha256": next(iter(identities), None),
        "performance_formula": (
            "S_perf = min(TPS / 15, 1) * 100 (official profiler)"
            if performance_formula == "profiler_capped"
            else (
                "S_perf = 100 * TPS / max(cohort_floor, candidate_TPS) "
                "(public challenge webpage alternative)"
            )
        ),
        "tps_max_scenario_notice": (
            "website scenarios are pre-entry cohort floors; each candidate raises TPS_max "
            "to at least its own measured TPS"
            if performance_formula == "website_relative"
            else "the executable profiler fixes TPS_REFERENCE at 15"
        ),
        "accuracy_notice": (
            f"S_acc is a measured {accuracy_task} proxy, not the unavailable judging-panel score"
        ),
        "thermal_notice": "temperature unavailable on GCP; no penalty applied",
        "rss_notice": (
            "peak RSS adds a 45 MiB estimate for the official profiler Python root to the "
            "measured llama-bench child-tree peak"
        ),
        "tps_max_sensitivity": tps_maxes,
        "winners": winners,
        "models": models,
    }


def write_tsv(summary: dict, path: Path) -> None:
    denominators = [str(value) for value in summary["tps_max_sensitivity"]]
    fields = [
        "model",
        "model_sha256",
        "model_bytes",
        "throughput_rounds",
        "throughput_repetitions",
        "tg_tps_mean",
        "tg_tps_sd",
        "peak_rss_mib_mean",
        "peak_rss_mib_sd",
        "accuracy_proxy_task",
        "accuracy_proxy",
        "accuracy_samples",
    ] + [f"score_tpsmax_{value}" for value in denominators]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for model in summary["models"]:
            row = {key: model.get(key) for key in fields}
            for value in denominators:
                row[f"score_tpsmax_{value}"] = (
                    model.get("scores", {}).get(value, {}).get("s_total", "NA")
                )
            writer.writerow(row)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        nargs="+",
        required=True,
        help="one or more append-only JSONL files; throughput identity checks remain strict",
    )
    parser.add_argument(
        "--accuracy-input",
        type=Path,
        nargs="*",
        default=(),
        help=(
            "optional JSONL evidence from another labelled execution context; only "
            "successful accuracy rows are imported"
        ),
    )
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--tsv", type=Path, required=True)
    parser.add_argument("--accuracy-task", default="arc_easy")
    parser.add_argument(
        "--tps-max",
        default="15",
        help="comma-separated references; default matches the official profiler's fixed 15",
    )
    parser.add_argument(
        "--performance-formula",
        choices=("profiler_capped", "website_relative"),
        default="profiler_capped",
    )
    args = parser.parse_args(argv)
    tps_maxes = [float(item) for item in args.tps_max.split(",") if item.strip()]
    rows = [row for path in args.input for row in _read_rows(path)]
    rows.extend(
        row
        for path in args.accuracy_input
        for row in _read_rows(path)
        if row.get("kind") == "accuracy"
    )
    result = summarize(
        rows,
        tps_maxes=tps_maxes,
        accuracy_task=args.accuracy_task,
        performance_formula=args.performance_formula,
    )
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    write_tsv(result, args.tsv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
