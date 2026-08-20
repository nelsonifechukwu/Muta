"""Build the 20 August overnight-campaign summary from retained raw evidence."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from bench.campaign_summary import _wilson95
from bench.score import score


ROOT_NAME = "campaign-20260820-overnight"
PROFILER_REPORTS = {
    "qwen3-0.6b-math-expert-q4_k_m": {
        "report": "official-clean-qwen3-0.6b-math-expert-q4_k_m.json",
        "model": "Qwen3-0.6B-Math-Expert.Q4_K_M.gguf",
        "manifest_id": "qwen3-0.6b-math-expert-q4_k_m",
        "accuracy_model": "Qwen3-0.6B-Math-Expert.Q4_K_M.gguf",
        "screen_model": "Qwen3-0.6B-Math-Expert.Q4_K_M.gguf",
    },
    "muta-tutor-qwen3.5-0.8b-q4_0-final": {
        "report": "official-final-muta-tutor-qwen3.5-0.8b-q4_0.json",
        "model": "Muta-Tutor-Qwen3.5-0.8B-Q4_0-final.gguf",
        "manifest_id": "muta-tutor-qwen3.5-0.8b-q4_0-final",
        "accuracy_model": "Qwen3.5-0.8B-Q4_0.gguf",
        "screen_model": "Qwen3.5-0.8B-Q4_0.gguf",
    },
}
RAW_FILES = (
    "qwen08-quant-screen.jsonl",
    "candidate-screen.jsonl",
    "candidate-screen-2.jsonl",
    "candidate-accuracy.jsonl",
    "candidate-accuracy-2.jsonl",
    "finalist-broad-accuracy.jsonl",
    "math-expert-quant-screen.jsonl",
    "math-expert-quant-accuracy.jsonl",
    "math-expert-hybrid-screen.jsonl",
    "math-expert-last4-screen.jsonl",
    "finalist-arc-easy-200.jsonl",
    "finalist-arc-easy-500.jsonl",
)


def _rows(path: Path) -> list[dict]:
    if not path.is_file():
        raise ValueError(f"missing campaign evidence: {path.name}")
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not rows or any(row.get("ok") is not True for row in rows):
        raise ValueError(f"campaign evidence is empty or contains a failed row: {path.name}")
    return rows


def _manifest_candidate(manifest: dict, candidate_id: str) -> dict:
    matches = [
        row
        for row in manifest["candidates"] + manifest["derived_candidates"]
        if row["id"] == candidate_id
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one manifest row for {candidate_id}")
    return matches[0]


def _ci(score_fraction: float, samples: int) -> list[float]:
    low, high = _wilson95(score_fraction, samples)
    return [round(low * 100, 2), round(high * 100, 2)]


def _profiler_row(root: Path, manifest: dict, candidate_id: str) -> dict:
    spec = PROFILER_REPORTS[candidate_id]
    report_name = spec["report"]
    model_file = spec["model"]
    report = json.loads((root / report_name).read_text())
    candidate = _manifest_candidate(manifest, spec["manifest_id"])
    accuracy = next(row for row in report["accuracy"] if row["benchmark"] == "arc_easy")
    tps = report["throughput"]["tokens_per_second_generation"]
    rss = report["memory"]["peak_rss_mb"]
    result = score(
        accuracy=accuracy["score"] * 100,
        tps_actual=tps,
        peak_rss_gb=rss / 1024,
        label=model_file,
    )
    return {
        "id": candidate_id,
        "model": model_file,
        "sha256": candidate["sha256"],
        "bytes": candidate.get("bytes", next(
            (row["model_bytes"] for row in _rows(root / "qwen08-quant-screen.jsonl")
             if row["model_sha256"] == candidate["sha256"]),
            396706176,
        )),
        "accuracy_model": spec["accuracy_model"],
        "screen_model": spec["screen_model"],
        "report": report_name,
        "tps": tps,
        "first_token_ms": report["throughput"]["first_token_latency_ms"],
        "peak_rss_mib": rss,
        "arc_easy_50": accuracy["score"] * 100,
        "arc_easy_50_ci95": _ci(accuracy["score"], accuracy["samples"]),
        "s_acc": result.s_acc,
        "s_perf": result.s_perf,
        "s_eff": result.s_eff,
        "s_total": result.s_total,
        "params_match": report["model_info"]["params_match"],
        "temperature_c": report["cpu_thermal"]["core_temp_c_peak"],
        "throttled": report["cpu_thermal"]["throttled"],
    }


def summarize(root: Path) -> dict:
    if root.name != ROOT_NAME:
        raise ValueError(f"expected campaign directory {ROOT_NAME}")
    manifest = json.loads((root / "manifest.json").read_text())
    raw = {name: _rows(root / name) for name in RAW_FILES}

    official = [_profiler_row(root, manifest, candidate_id) for candidate_id in PROFILER_REPORTS]
    official.sort(key=lambda row: row["s_total"], reverse=True)

    broad = defaultdict(dict)
    for name in ("finalist-broad-accuracy.jsonl", "finalist-arc-easy-200.jsonl", "finalist-arc-easy-500.jsonl"):
        for row in raw[name]:
            broad[row["model"]][f'{row["benchmark"]}_{row["limit"]}'] = {
                "score_percent": row["score"] * 100,
                "samples": row["limit"],
                "metric": row["metric"],
                "ci95_percent": _ci(row["score"], row["limit"]),
            }

    throughput = defaultdict(dict)
    for name in ("qwen08-quant-screen.jsonl", "candidate-screen.jsonl", "candidate-screen-2.jsonl"):
        for row in raw[name]:
            if row["kind"] == "throughput":
                throughput[row["model"]][row["bench"]] = {
                    "tg128_tps": row["tg_avg_ts"],
                    "pp512_tps": row["pp_avg_ts"],
                    "child_tree_rss_mib": row["peak_rss_tree_mb"],
                }

    accuracy = defaultdict(dict)
    for name in ("candidate-accuracy.jsonl", "candidate-accuracy-2.jsonl"):
        for row in raw[name]:
            accuracy[row["model"]][row["benchmark"]] = row["score"] * 100

    screened = []
    for model, benches in throughput.items():
        screened.append({
            "model": model,
            "scalar": benches.get("scalar"),
            "avx2": benches.get("avx2"),
            "accuracy": accuracy.get(model, {}),
        })

    quant_throughput = defaultdict(dict)
    quant_accuracy = defaultdict(dict)
    for name in ("math-expert-quant-screen.jsonl", "math-expert-hybrid-screen.jsonl", "math-expert-last4-screen.jsonl"):
        for row in raw[name]:
            if row["kind"] == "throughput":
                quant_throughput[row["model"]][row["bench"]] = {
                    "tg128_tps": row["tg_avg_ts"],
                    "pp512_tps": row["pp_avg_ts"],
                    "child_tree_rss_mib": row["peak_rss_tree_mb"],
                }
            else:
                quant_accuracy[row["model"]][row["benchmark"]] = row["score"] * 100
    for row in raw["math-expert-quant-accuracy.jsonl"]:
        quant_accuracy[row["model"]][row["benchmark"]] = row["score"] * 100
    # The promoted Q4_K_M accuracy was measured by the direct profiler.
    quant_accuracy["Qwen3-0.6B-Math-Expert.Q4_K_M.gguf"]["arc_easy"] = 68.0
    quant_sweep = [
        {"model": model, "scalar": benches.get("scalar"), "avx2": benches.get("avx2"),
         "accuracy": quant_accuracy.get(model, {})}
        for model, benches in quant_throughput.items()
    ]

    finalists = {
        row["model"]: {
            "official": row,
            "accuracy": broad[row["accuracy_model"]],
        }
        for row in official
    }
    for entry in finalists.values():
        official_row = entry["official"]
        accuracy_500 = entry["accuracy"]["arc_easy_500"]["score_percent"]
        diagnostic = score(
            accuracy=accuracy_500,
            tps_actual=official_row["tps"],
            peak_rss_gb=official_row["peak_rss_mib"] / 1024,
            label=official_row["model"],
        )
        entry["diagnostic_total_with_arc_easy_500"] = diagnostic.s_total
    recommendation = max(
        finalists,
        key=lambda model: finalists[model]["accuracy"]["arc_easy_500"]["score_percent"],
    )

    floors = [15, 30, 45, 60, 100, 150]
    website_relative = {}
    screen_by_model = {row["model"]: row for row in screened}
    for model, entry in finalists.items():
        avx2 = screen_by_model[entry["official"]["screen_model"]]["avx2"]
        accuracy_500 = entry["accuracy"]["arc_easy_500"]["score_percent"]
        scores = {}
        for floor in floors:
            denominator = max(float(floor), avx2["tg128_tps"])
            result = score(
                accuracy=accuracy_500,
                tps_actual=avx2["tg128_tps"],
                peak_rss_gb=(avx2["child_tree_rss_mib"] + 45) / 1024,
                tps_max=denominator,
                tps_max_provenance="cohort_observed",
                performance_formula="website_relative",
                label=model,
            )
            scores[str(floor)] = {
                "effective_tps_max": denominator,
                "s_total": result.s_total,
                "s_perf": result.s_perf,
            }
        website_relative[model] = {"avx2": avx2, "scores": scores}

    return {
        "schema_version": 1,
        "campaign": manifest["campaign"],
        "status": manifest["status"],
        "hardware_context": manifest["hardware_context"],
        "rules": manifest["rules"],
        "baseline": manifest["baseline"],
        "official_profiler": official,
        "official_profiler_winner": official[0]["model"],
        "risk_adjusted_recommendation": recommendation,
        "finalists": finalists,
        "screened_candidates": sorted(screened, key=lambda row: row["model"]),
        "quantization_sweep": sorted(quant_sweep, key=lambda row: row["model"]),
        "website_relative_floors": floors,
        "website_relative": website_relative,
        "notices": {
            "accuracy": "ARC and SciQ are diagnostic proxies; the judging-panel tutoring score is unknown.",
            "thermal": "The GCP host exposed no package-temperature sensor.",
            "hardware": "GCP n2-custom-4-8192 is a 2-core/4-thread cloud proxy, not the physical target laptop.",
            "rss": "Direct reports use profiler root-plus-child RSS; screening rows use child-tree RSS.",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    summary = summarize(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
