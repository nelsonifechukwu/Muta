"""Build a fail-closed scalar-versus-AVX2 score-of-record comparison.

The two raw JSONL files remain the evidence. This module validates the fixed five-model
roster, hashes, benchmark geometry, binary identities, CPU/thread context, and repetition
policy before it emits a comparison. Accuracy is reused by artifact hash from the existing
campaign summary because changing the inference ISA cannot change the GGUF weights.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from bench.score import score

SCALAR_BINARY_SHA256 = "7f01dc0465d64f726b2b66139859a8ff1ca204f4901e18b71ddfa678dea19370"
AVX2_BINARY_SHA256 = "4abfa11a3f86b8c5e4d508cce10daf8f381c968585a3e5961fea3d5cbe312fd8"
SCALAR_HARDWARE_CONTEXT = "adtc_profiler_reference_cloud_vm_proxy_no_avx_2c4t"
AVX2_HARDWARE_CONTEXT = "x86_cloud_proxy_gcp_n2_custom_4_8192_2c4t"
PROFILER_TPS_REFERENCE = 15.0

ROSTER = {
    "muta-tutor-qwen3-1.7b-q4_0.gguf": "a98ce36e9ff97e5271d90cbc429c952f99a5a966bb0195ae74661b4c054fd63e",
    "Q4_K_M-tied.gguf": "e8a4133261be39c07f73c8d40e1c8334aae90ece9cae9f1cce75a8347f64c315",
    "Q5_K_M-tied.gguf": "17ddf7b5b135bc9fe0ce5449b8f506f91586447f73bf145f14b52b5b4bbe0647",
    "IQ4_XS-tied.gguf": "aea3cb60c57cc93f74f45c36c85c80ae34d65396ec563cfba4742f89b10b6fa3",
    "bitcpm4-8b-tq2_0-envocab.gguf": "069621f168502215839fb82db3afe35beb8e5350fb6cbf8523aa1eea6bee237d",
}


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{number}: invalid JSON: {exc}") from exc
    return rows


def _flag_value(command: list[str], flag: str) -> str | None:
    try:
        return command[command.index(flag) + 1]
    except (ValueError, IndexError):
        return None


def _bench_metric(row: dict, *, prompt: bool) -> dict:
    matches = [
        item
        for item in row.get("raw_bench_rows", [])
        if bool(item.get("n_prompt")) is prompt and bool(item.get("n_gen")) is not prompt
    ]
    if len(matches) != 1:
        kind = "pp512" if prompt else "tg128"
        raise ValueError(f"{row.get('model')}: expected one {kind} raw row, got {len(matches)}")
    return matches[0]


def _validate_row(
    row: dict, *, binary_sha256: str, hardware_context: str, require_five_reps: bool
) -> None:
    model = row.get("model")
    if model not in ROSTER:
        raise ValueError(f"unexpected model in ISA comparison: {model!r}")
    if row.get("ok") is not True:
        raise ValueError(f"{model}: benchmark row is not successful")
    if row.get("model_sha256") != ROSTER[model]:
        raise ValueError(f"{model}: artifact hash mismatch")
    if row.get("hardware_context") != hardware_context:
        raise ValueError(f"{model}: wrong hardware context {row.get('hardware_context')!r}")
    if row.get("bench_identity", {}).get("sha256") != binary_sha256:
        raise ValueError(f"{model}: benchmark binary hash mismatch")
    if row.get("physical_cores") != 2 or row.get("logical_cpus") != 4:
        raise ValueError(f"{model}: expected the GCP 2C/4T topology")
    if row.get("n_threads") != 2:
        raise ValueError(f"{model}: expected llama-bench to select two physical-core threads")

    command = row.get("command") or []
    expected = {"-p": "512", "-n": "128", "-ngl": "0"}
    for flag, value in expected.items():
        if _flag_value(command, flag) != value:
            raise ValueError(f"{model}: expected {flag} {value} in {command}")
    if "-t" in command or "--threads" in command:
        raise ValueError(f"{model}: thread override breaks profiler parity")
    if require_five_reps and _flag_value(command, "-r") not in (None, "5"):
        raise ValueError(f"{model}: AVX2 score-of-record requires the default five reps or -r 5")

    for prompt in (True, False):
        metric = _bench_metric(row, prompt=prompt)
        samples = metric.get("samples_ts") or []
        if require_five_reps and len(samples) != 5:
            raise ValueError(f"{model}: AVX2 metric does not contain five internal samples")


def _measurement(row: dict) -> dict:
    pp = _bench_metric(row, prompt=True)
    tg = _bench_metric(row, prompt=False)
    overhead = row.get("profiler_python_overhead_mib_note")
    if overhead is None:
        raise ValueError(f"{row.get('model')}: profiler-root RSS estimate is missing")
    tree_rss = float(row["peak_rss_tree_mb"])
    return {
        "pp512_tps": round(float(pp["avg_ts"]), 6),
        "pp512_sd": round(float(pp.get("stddev_ts") or 0.0), 6),
        "tg128_tps": round(float(tg["avg_ts"]), 6),
        "tg128_sd": round(float(tg.get("stddev_ts") or 0.0), 6),
        "tree_rss_mib": round(tree_rss, 1),
        "estimated_profiler_rss_mib": round(tree_rss + float(overhead), 1),
        "wall_s": float(row["wall_s"]),
        "internal_repetitions": len(tg.get("samples_ts") or []) or 1,
    }


def compare(scalar_rows: list[dict], avx2_rows: list[dict], accuracy_summary: dict) -> dict:
    scalar = {row.get("model"): row for row in scalar_rows if row.get("kind") == "throughput"}
    avx2 = {row.get("model"): row for row in avx2_rows if row.get("kind") == "throughput"}
    if set(scalar) != set(ROSTER) or set(avx2) != set(ROSTER):
        raise ValueError(
            f"roster mismatch: scalar={sorted(scalar)}, avx2={sorted(avx2)}, "
            f"expected={sorted(ROSTER)}"
        )
    if len(scalar_rows) != len(ROSTER) or len(avx2_rows) != len(ROSTER):
        raise ValueError("ISA evidence must contain exactly one throughput row per model")

    accuracy_by_hash = {
        model["model_sha256"]: float(model["accuracy_proxy"])
        for model in accuracy_summary.get("models", [])
        if model.get("accuracy_proxy") is not None
    }
    models = []
    for name, artifact_hash in ROSTER.items():
        scalar_row, avx2_row = scalar[name], avx2[name]
        _validate_row(
            scalar_row,
            binary_sha256=SCALAR_BINARY_SHA256,
            hardware_context=SCALAR_HARDWARE_CONTEXT,
            require_five_reps=False,
        )
        _validate_row(
            avx2_row,
            binary_sha256=AVX2_BINARY_SHA256,
            hardware_context=AVX2_HARDWARE_CONTEXT,
            require_five_reps=True,
        )
        if artifact_hash not in accuracy_by_hash:
            raise ValueError(f"{name}: no accuracy proxy for artifact hash")
        accuracy = accuracy_by_hash[artifact_hash]
        scalar_measurement = _measurement(scalar_row)
        avx2_measurement = _measurement(avx2_row)

        for measurement in (scalar_measurement, avx2_measurement):
            scored = score(
                accuracy=accuracy,
                tps_actual=measurement["tg128_tps"],
                peak_rss_gb=measurement["estimated_profiler_rss_mib"] / 1024.0,
                max_temp_c=None,
                label=name,
            )
            measurement["score"] = {
                "s_total": round(scored.s_total, 4),
                "s_acc": round(scored.s_acc, 4),
                "s_perf": round(scored.s_perf, 4),
                "s_eff": round(scored.s_eff, 4),
                "thermal_penalty": scored.p_thermal,
                "thermal_unknown": scored.thermal_unknown,
            }

        scalar_tps = scalar_measurement["tg128_tps"]
        avx2_tps = avx2_measurement["tg128_tps"]
        models.append(
            {
                "model": name,
                "model_sha256": artifact_hash,
                "accuracy_proxy": accuracy,
                "accuracy_proxy_task": "arc_easy",
                "scalar": scalar_measurement,
                "avx2": avx2_measurement,
                "delta": {
                    "decode_tps": round(avx2_tps - scalar_tps, 6),
                    "decode_speedup": round(avx2_tps / scalar_tps, 6),
                    "estimated_profiler_rss_mib": round(
                        avx2_measurement["estimated_profiler_rss_mib"]
                        - scalar_measurement["estimated_profiler_rss_mib"],
                        1,
                    ),
                    "s_total": round(
                        avx2_measurement["score"]["s_total"]
                        - scalar_measurement["score"]["s_total"],
                        4,
                    ),
                },
            }
        )

    scalar_winner = max(models, key=lambda item: item["scalar"]["score"]["s_total"])
    avx2_winner = max(models, key=lambda item: item["avx2"]["score"]["s_total"])
    return {
        "schema_version": 1,
        "hardware_contexts": {
            "scalar": SCALAR_HARDWARE_CONTEXT,
            "avx2": AVX2_HARDWARE_CONTEXT,
        },
        "performance_formula": "100 * min(TPS / 15, 1)",
        "tps_reference": PROFILER_TPS_REFERENCE,
        "rss_accounting": "llama-bench child-tree peak plus the raw row's 45 MiB profiler-root estimate",
        "thermal_notice": "GCP exposes no package-temperature sensor; no penalty applied, thermal unknown",
        "scalar_binary_sha256": SCALAR_BINARY_SHA256,
        "avx2_binary_sha256": AVX2_BINARY_SHA256,
        "models": models,
        "winners": {
            "scalar": {
                "model": scalar_winner["model"],
                "s_total": scalar_winner["scalar"]["score"]["s_total"],
            },
            "avx2": {
                "model": avx2_winner["model"],
                "s_total": avx2_winner["avx2"]["score"]["s_total"],
            },
        },
    }


def write_tsv(path: Path, summary: dict) -> None:
    fields = [
        "model",
        "accuracy_proxy",
        "scalar_pp512_tps",
        "avx2_pp512_tps",
        "scalar_tg128_tps",
        "avx2_tg128_tps",
        "decode_delta_tps",
        "decode_speedup",
        "scalar_rss_mib",
        "avx2_rss_mib",
        "rss_delta_mib",
        "scalar_s_total",
        "avx2_s_total",
        "s_total_delta",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for item in summary["models"]:
            writer.writerow(
                {
                    "model": item["model"],
                    "accuracy_proxy": item["accuracy_proxy"],
                    "scalar_pp512_tps": item["scalar"]["pp512_tps"],
                    "avx2_pp512_tps": item["avx2"]["pp512_tps"],
                    "scalar_tg128_tps": item["scalar"]["tg128_tps"],
                    "avx2_tg128_tps": item["avx2"]["tg128_tps"],
                    "decode_delta_tps": item["delta"]["decode_tps"],
                    "decode_speedup": item["delta"]["decode_speedup"],
                    "scalar_rss_mib": item["scalar"]["estimated_profiler_rss_mib"],
                    "avx2_rss_mib": item["avx2"]["estimated_profiler_rss_mib"],
                    "rss_delta_mib": item["delta"]["estimated_profiler_rss_mib"],
                    "scalar_s_total": item["scalar"]["score"]["s_total"],
                    "avx2_s_total": item["avx2"]["score"]["s_total"],
                    "s_total_delta": item["delta"]["s_total"],
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scalar-jsonl", type=Path, required=True)
    parser.add_argument("--avx2-jsonl", type=Path, required=True)
    parser.add_argument("--accuracy-summary", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-tsv", type=Path, required=True)
    args = parser.parse_args()

    summary = compare(
        read_jsonl(args.scalar_jsonl),
        read_jsonl(args.avx2_jsonl),
        json.loads(args.accuracy_summary.read_text()),
    )
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    write_tsv(args.out_tsv, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
