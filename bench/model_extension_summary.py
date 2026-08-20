"""Build the eight-model scalar/vector report summary from retained JSONL evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bench.campaign_summary import _wilson95
from bench.score import score

MODEL_LABELS = {
    "qwen2.5-1.5b-instruct-Q4_K_M.gguf": ("Qwen2.5-1.5B-Instruct-Q4_K_M.gguf", "Qwen2.5 1.5B"),
    "qwen2-1.5b-instruct-Q4_K_M.gguf": ("Qwen2-1.5B-Instruct-Q4_K_M.gguf", "Qwen2 1.5B"),
    "llama-3.2-1b-instruct-Q4_K_M.gguf": ("Llama-3.2-1B-Instruct-Q4_K_M.gguf", "Llama 3.2 1B"),
    "qwen2.5-3b-instruct-Q4_K_M.gguf": ("Qwen2.5-3B-Instruct-Q4_K_M.gguf", "Qwen2.5 3B"),
    "llama-3.2-3b-instruct-Q4_K_M.gguf": ("Llama-3.2-3B-Instruct-Q4_K_M.gguf", "Llama 3.2 3B"),
    "gemma-2-2b-it-Q8_0.gguf": ("gemma-2-2b-it-Q8_0.gguf", "Gemma 2 2B Q8_0"),
    "phi-4-mini-instruct-Q4_K_M.gguf": ("Phi-4-mini-instruct-Q4_K_M.gguf", "Phi-4 Mini 3.8B"),
    "orca-mini-3b-Q4_K_M.gguf": ("orca-mini-3b-Q4_K_M.gguf", "Orca Mini 3B"),
}


def _read_jsonl(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    failed = [row for row in rows if row.get("ok") is not True]
    if failed:
        raise ValueError(f"{path} contains {len(failed)} failed row(s)")
    return rows


def _one(rows: list[dict], *, label: str) -> dict:
    if len(rows) != 1:
        raise ValueError(f"expected one {label} row, found {len(rows)}")
    return rows[0]


def _score(accuracy_percent: float, throughput: dict, rss_mib: float) -> float:
    result = score(
        accuracy=accuracy_percent,
        tps_actual=float(throughput["tg_avg_ts"]),
        peak_rss_gb=rss_mib / 1024.0,
        label=str(throughput["model"]),
    )
    if result.s_total is None:
        raise ValueError(f"unexpected disqualification for {throughput['model']}")
    return round(result.s_total, 4)


def build_summary(
    accuracy_path: Path,
    throughput_path: Path,
    validation_path: Path | None = None,
) -> dict:
    accuracy_rows = _read_jsonl(accuracy_path)
    throughput_rows = _read_jsonl(throughput_path)
    validation_rows = _read_jsonl(validation_path) if validation_path else []

    if len(accuracy_rows) != len(MODEL_LABELS):
        raise ValueError("the architecture screen must contain eight accuracy rows")
    if len(throughput_rows) != 2 * len(MODEL_LABELS):
        raise ValueError(
            "the architecture screen must contain one scalar and one vector row per model"
        )

    contexts = {row.get("hardware_context") for row in throughput_rows}
    if len(contexts) != 1 or None in contexts:
        raise ValueError(f"mixed or missing hardware contexts: {contexts}")
    physical_cores = {row.get("physical_cores") for row in throughput_rows}
    logical_cpus = {row.get("logical_cpus") for row in throughput_rows}
    if physical_cores != {2} or logical_cpus != {4}:
        raise ValueError("expected the GCP 2C/4T proxy")

    lane_identity: dict[str, str] = {}
    for lane in ("scalar", "avx2"):
        hashes = {
            row.get("bench_identity", {}).get("sha256")
            for row in throughput_rows
            if row.get("bench") == lane
        }
        if len(hashes) != 1 or None in hashes:
            raise ValueError(f"mixed or missing {lane} benchmark identity: {hashes}")
        lane_identity[lane] = hashes.pop()

    validation_by_model = {row["model"]: row for row in validation_rows}
    models = []
    for raw_name, (canonical_name, display_label) in MODEL_LABELS.items():
        accuracy = _one(
            [row for row in accuracy_rows if row.get("model") == raw_name],
            label=f"accuracy for {raw_name}",
        )
        scalar = _one(
            [
                row
                for row in throughput_rows
                if row.get("model") == raw_name and row.get("bench") == "scalar"
            ],
            label=f"scalar throughput for {raw_name}",
        )
        vector = _one(
            [
                row
                for row in throughput_rows
                if row.get("model") == raw_name and row.get("bench") == "avx2"
            ],
            label=f"vector throughput for {raw_name}",
        )
        identities = {accuracy["model_sha256"], scalar["model_sha256"], vector["model_sha256"]}
        sizes = {accuracy["model_bytes"], scalar["model_bytes"], vector["model_bytes"]}
        if len(identities) != 1 or len(sizes) != 1:
            raise ValueError(f"model identity mismatch for {raw_name}")

        accuracy_percent = round(float(accuracy["score"]) * 100.0, 6)
        ci_low, ci_high = _wilson95(float(accuracy["score"]), int(accuracy["samples"]))
        root_estimate = float(scalar["profiler_python_overhead_mib_note"])
        scalar_rss = float(scalar["peak_rss_tree_mb"]) + root_estimate
        vector_rss = float(vector["peak_rss_tree_mb"]) + float(
            vector["profiler_python_overhead_mib_note"]
        )
        item = {
            "model": canonical_name,
            "label": display_label,
            "bytes": sizes.pop(),
            "model_sha256": identities.pop(),
            "accuracy_percent": accuracy_percent,
            "accuracy_samples": int(accuracy["samples"]),
            "accuracy_ci95_percent": [round(ci_low * 100.0, 2), round(ci_high * 100.0, 2)],
            "scalar": {
                "pp512_tps": round(float(scalar["pp_avg_ts"]), 6),
                "tg128_tps": round(float(scalar["tg_avg_ts"]), 6),
                "estimated_profiler_rss_mib": round(scalar_rss, 1),
                "s_total": _score(accuracy_percent, scalar, scalar_rss),
            },
            "avx2": {
                "pp512_tps": round(float(vector["pp_avg_ts"]), 6),
                "tg128_tps": round(float(vector["tg_avg_ts"]), 6),
                "estimated_profiler_rss_mib": round(vector_rss, 1),
                "s_total": _score(accuracy_percent, vector, vector_rss),
            },
            "decode_speedup": round(float(vector["tg_avg_ts"]) / float(scalar["tg_avg_ts"]), 3),
        }
        validation = validation_by_model.get(raw_name)
        if validation:
            if validation["model_sha256"] != item["model_sha256"]:
                raise ValueError(f"validation identity mismatch for {raw_name}")
            validation_percent = round(float(validation["score"]) * 100.0, 6)
            v_low, v_high = _wilson95(float(validation["score"]), int(validation["samples"]))
            item["accuracy_validation"] = {
                "benchmark": validation["benchmark"],
                "metric": validation["metric"],
                "samples": int(validation["samples"]),
                "accuracy_percent": validation_percent,
                "ci95_percent": [round(v_low * 100.0, 2), round(v_high * 100.0, 2)],
            }
            item["scalar"]["s_total_accuracy_500"] = _score(validation_percent, scalar, scalar_rss)
            item["avx2"]["s_total_accuracy_500"] = _score(validation_percent, vector, vector_rss)
        models.append(item)

    unmatched_validation = set(validation_by_model) - set(MODEL_LABELS)
    if unmatched_validation:
        raise ValueError(f"validation rows do not match the screen: {sorted(unmatched_validation)}")
    models.sort(key=lambda item: item["avx2"]["s_total"], reverse=True)
    winner = models[0]
    return {
        "schema_version": 2,
        "evidence_tier": "controlled_scalar_and_vector_proxy",
        "hardware_context": contexts.pop(),
        "hardware": {"physical_cores": 2, "logical_cpus": 4},
        "workload": {"prompt_tokens": 512, "generated_tokens": 128, "samples_per_lane": 5},
        "performance_reference_tps": 15,
        "profiler_root_rss_estimate_mib": 45,
        "temperature": "unavailable",
        "benchmark_identity_sha256": lane_identity,
        "source_evidence": {
            "accuracy": accuracy_path.name,
            "throughput": throughput_path.name,
            "accuracy_validation": validation_path.name if validation_path else None,
        },
        "models": models,
        "winner": {"model": winner["model"], "s_total": winner["avx2"]["s_total"]},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--accuracy", type=Path, required=True)
    parser.add_argument("--throughput", type=Path, required=True)
    parser.add_argument("--validation", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = build_summary(args.accuracy, args.throughput, args.validation)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
