"""Aggregate full reports emitted by the official ADTC profiler.

Unlike :mod:`bench.campaign_summary`, this path does not reconstruct profiler memory
accounting. Each input is the profiler's own schema-valid JSON report, so peak RSS already
contains the Python root process and its llama-bench child tree.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from bench.campaign_summary import _wilson95
from bench.score import score


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def summarize(manifest: dict, root: Path) -> dict:
    if manifest.get("schema_version") != 1:
        raise ValueError("official-profiler manifest schema_version must be 1")
    if manifest.get("run_mode") != "participant":
        raise ValueError("official-profiler manifest run_mode must be participant")
    binary = manifest.get("benchmark_binary") or {}
    binary_sha = binary.get("sha256")
    if not binary_sha:
        raise ValueError("benchmark binary SHA-256 is required")
    accuracy_stack = manifest.get("accuracy_stack") or {}
    if not accuracy_stack.get("libllama_sha256") or not accuracy_stack.get("lm_eval"):
        raise ValueError("accuracy stack versions and libllama SHA-256 are required")

    model_specs = manifest.get("models") or []
    if not model_specs:
        raise ValueError("official-profiler manifest must contain at least one model")

    models = []
    environments = set()
    profiler_versions = set()
    for spec in model_specs:
        for required in ("model", "model_sha256", "model_bytes", "report", "report_sha256"):
            if not spec.get(required):
                raise ValueError(f"model entry is missing {required}")
        report_path = root / spec["report"]
        if not report_path.is_file():
            raise ValueError(f"missing official profiler report: {report_path}")
        actual_report_sha = _sha256(report_path)
        if actual_report_sha != spec.get("report_sha256"):
            raise ValueError(
                f"report hash mismatch for {report_path.name}: "
                f"{actual_report_sha} != {spec.get('report_sha256')}"
            )
        report = json.loads(report_path.read_text())
        profiler_versions.add(report.get("profiler_version"))
        environment = report.get("environment") or {}
        if environment.get("measured_on") != "participant_laptop":
            raise ValueError(f"report is not participant-mode evidence: {spec['model']}")
        environments.add(json.dumps(environment, sort_keys=True))

        reproducibility = report.get("reproducibility") or {}
        if reproducibility.get("random_seed") != 42:
            raise ValueError(f"report seed is not 42: {spec['model']}")

        model_info = report.get("model_info") or {}
        if model_info.get("params_match") is not True:
            raise ValueError(f"profiler fraud/parameter check did not pass: {spec['model']}")
        throughput = report.get("throughput") or {}
        memory = report.get("memory") or {}
        thermal = report.get("cpu_thermal") or {}
        tps = throughput.get("tokens_per_second_generation")
        peak_rss = memory.get("peak_rss_mb")
        if not isinstance(tps, (int, float)) or tps <= 0:
            raise ValueError(f"invalid profiler throughput: {spec['model']}")
        if throughput.get("prompt_tokens") != 512 or throughput.get("generated_tokens") != 128:
            raise ValueError(f"report is not the p512/tg128 workload: {spec['model']}")
        if not isinstance(peak_rss, (int, float)) or peak_rss <= 0:
            raise ValueError(f"invalid profiler peak RSS: {spec['model']}")

        accuracy_rows = report.get("accuracy") or []
        matching_accuracy = [row for row in accuracy_rows if row.get("benchmark") == "arc_easy"]
        if len(matching_accuracy) != 1:
            raise ValueError(f"expected exactly one arc_easy result: {spec['model']}")
        accuracy = matching_accuracy[0]
        samples = accuracy.get("samples")
        raw_score = accuracy.get("score")
        if not isinstance(samples, int) or samples <= 0:
            raise ValueError(f"invalid accuracy sample count: {spec['model']}")
        if samples != 50 or accuracy.get("metric") != "acc_norm":
            raise ValueError(f"report is not ARC-Easy-50 acc_norm evidence: {spec['model']}")
        if not isinstance(raw_score, (int, float)) or not 0 <= raw_score <= 1:
            raise ValueError(f"invalid accuracy score: {spec['model']}")

        result = score(
            accuracy=raw_score * 100.0,
            tps_actual=tps,
            peak_rss_gb=peak_rss / 1024.0,
            tps_max=15.0,
            tps_max_provenance="profiler_reference",
            performance_formula="profiler_capped",
            max_temp_c=thermal.get("core_temp_c_peak"),
            throttled=bool(thermal.get("throttled")),
            label=spec["model"],
        )
        ci_low, ci_high = _wilson95(raw_score, samples)
        scores = {
            "15.0": {
                "s_total": round(result.s_total, 4) if result.s_total is not None else None,
                "s_acc": round(result.s_acc, 4) if result.s_acc is not None else None,
                "s_perf": round(result.s_perf, 4) if result.s_perf is not None else None,
                "s_eff": round(result.s_eff, 4) if result.s_eff is not None else None,
                "thermal_penalty": result.p_thermal,
                "disqualified": result.disqualified,
            }
        }
        models.append(
            {
                "model": spec["model"],
                "model_sha256": spec["model_sha256"],
                "model_bytes": spec["model_bytes"],
                "report": spec["report"],
                "report_sha256": spec["report_sha256"],
                "throughput_rounds": 1,
                "throughput_repetitions": 5,
                "measurement_tier": "official_profiler_full_run",
                "tg_tps_mean": tps,
                "tg_tps_sd": None,
                "first_token_latency_ms": throughput.get("first_token_latency_ms"),
                "peak_rss_mib_mean": peak_rss,
                "peak_rss_mib_sd": None,
                "rss_accounting": "measured by official profiler over root plus child tree",
                "rss_estimated": False,
                "accuracy_proxy_task": "arc_easy",
                "accuracy_proxy": round(raw_score * 100.0, 4),
                "accuracy_samples": samples,
                "accuracy_tasks": {
                    "arc_easy": {
                        "score_percent": round(raw_score * 100.0, 4),
                        "samples": samples,
                        "metric": accuracy.get("metric"),
                        "ci95_percent": [round(ci_low * 100.0, 2), round(ci_high * 100.0, 2)],
                    }
                },
                "thermal": thermal,
                "model_info": model_info,
                "scores": scores,
            }
        )

    if len(environments) != 1 or len(profiler_versions) != 1 or None in profiler_versions:
        raise ValueError("official reports do not share one environment and profiler version")
    ranked = [model for model in models if model["scores"]["15.0"]["s_total"] is not None]
    winner = max(ranked, key=lambda model: model["scores"]["15.0"]["s_total"])
    return {
        "schema_version": 1,
        "evidence_tier": "official_profiler_full_run",
        "hardware_context": manifest["hardware_context"],
        "environment": json.loads(next(iter(environments))),
        "profiler_version": next(iter(profiler_versions)),
        "profiler_source_commit": manifest["profiler_source_commit"],
        "benchmark_binary_sha256": binary_sha,
        "benchmark_binary_commit": binary["llama_cpp_commit"],
        "benchmark_build": binary["build"],
        "accuracy_stack": accuracy_stack,
        "performance_formula": "S_perf = min(TPS / 15, 1) * 100 (official profiler)",
        "tps_max_scenario_notice": "the executable profiler fixes TPS_REFERENCE at 15",
        "accuracy_notice": "S_acc is the profiler's arc_easy result, not the judging-panel score",
        "thermal_notice": "temperature unavailable on GCP; profiler reported no throttling",
        "rss_notice": "peak RSS is directly measured by the profiler over its root and child tree",
        "tps_max_sensitivity": [15.0],
        "winners": {
            "15.0": {
                "model": winner["model"],
                "model_sha256": winner["model_sha256"],
                "s_total": winner["scores"]["15.0"]["s_total"],
            }
        },
        "models": models,
    }


def write_tsv(summary: dict, path: Path) -> None:
    fields = [
        "model",
        "model_sha256",
        "model_bytes",
        "tg_tps_mean",
        "first_token_latency_ms",
        "peak_rss_mib_mean",
        "accuracy_proxy",
        "accuracy_samples",
        "s_total",
        "report",
        "report_sha256",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for model in summary["models"]:
            writer.writerow(
                {
                    **{field: model.get(field) for field in fields},
                    "s_total": model["scores"]["15.0"]["s_total"],
                }
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--tsv", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text())
    summary = summarize(manifest, args.manifest.parent)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    write_tsv(summary, args.tsv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
