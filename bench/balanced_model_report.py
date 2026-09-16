"""Build the ranked CSV and Markdown report for the balanced-model campaign."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from bench.run_stem_prompt_suite import selected_option
from bench.score import score
from bench.stem_prompt_suite import prompts


def wilson95(rate: float, samples: int) -> tuple[float, float]:
    z = 1.959963984540054
    z2 = z * z
    denominator = 1 + z2 / samples
    centre = (rate + z2 / (2 * samples)) / denominator
    radius = z * math.sqrt(rate * (1 - rate) / samples + z2 / (4 * samples * samples)) / denominator
    return max(0.0, centre - radius), min(1.0, centre + radius)


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def load_artifacts(path: Path) -> tuple[dict[str, str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
        return {row["test_artifact"]: row["model"] for row in rows}, rows


def _throughput_by_model(rows: list[dict]) -> dict[str, dict]:
    return _unique_models(
        [row for row in rows if row.get("kind") == "throughput" and row.get("ok") is True]
    )


def _unique_models(rows: list[dict]) -> dict[str, dict]:
    result = {}
    for row in rows:
        if row["model"] in result:
            raise ValueError(f"duplicate measurement for {row['model']}")
        result[row["model"]] = row
    return result


def _require_matching_hashes(*rows: dict) -> None:
    hashes = [row.get("model_sha256") for row in rows]
    if not all(hashes) or len(set(hashes)) != 1:
        raise ValueError(f"missing or mismatched model hashes for {rows[0]['model']}")


def hardware_context(row: dict) -> str:
    context = row.get("hardware_context")
    return context if context and context != "unspecified" else "unspecified (legacy record)"


def _throughput_metrics(row: dict) -> tuple[float, float, float, float]:
    pp_row = next(
        item for item in row["raw_bench_rows"] if item.get("n_prompt") and not item.get("n_gen")
    )
    tg_row = next(
        item for item in row["raw_bench_rows"] if item.get("n_gen") and not item.get("n_prompt")
    )
    pp_samples = [float(value) for value in pp_row.get("samples_ts", [])]
    tg_samples = [float(value) for value in tg_row.get("samples_ts", [])]
    pp = statistics.mean(pp_samples) if pp_samples else float(row["pp_avg_ts"])
    tg = statistics.mean(tg_samples) if tg_samples else float(row["tg_avg_ts"])
    tg_sd = statistics.stdev(tg_samples) if len(tg_samples) > 1 else 0.0
    rss_mib = float(row["peak_rss_tree_mb"]) + float(
        row.get("profiler_python_overhead_mib_note", 0)
    )
    return pp, tg, tg_sd, rss_mib


def summarize(
    throughput_rows: list[dict],
    accuracy_rows: list[dict],
    names: dict[str, str],
    vector_rows: list[dict] | None = None,
    stem_rows: list[dict] | None = None,
) -> list[dict]:
    throughput_by_model = _throughput_by_model(throughput_rows)
    vector_by_model = _throughput_by_model(vector_rows or [])
    accuracy_by_model = _unique_models(
        [
            row
            for row in accuracy_rows
            if row.get("kind") == "accuracy"
            and row.get("benchmark") == "arc_easy"
            and row.get("ok") is True
            and int(row.get("samples", 0)) == 500
        ]
    )
    stem = stem_summary(stem_rows or [], names)
    results = []
    for filename, perf in throughput_by_model.items():
        accuracy = accuracy_by_model.get(filename)
        if accuracy is None:
            continue
        _require_matching_hashes(perf, accuracy)
        vector = vector_by_model.get(filename)
        if vector is not None:
            _require_matching_hashes(perf, vector)
        stem_result = stem.get(names.get(filename, filename))
        if stem_result:
            _require_matching_hashes(perf, stem_result)
        pp, tg, tg_sd, rss_mib = _throughput_metrics(perf)
        accuracy_rate = float(accuracy["score"])
        accuracy_pct = accuracy_rate * 100
        ci_low, ci_high = wilson95(accuracy_rate, int(accuracy["samples"]))
        scored = score(
            accuracy=accuracy_pct,
            tps_actual=tg,
            peak_rss_gb=rss_mib / 1024,
            tps_max=15,
            tps_max_provenance="profiler_reference",
            performance_formula="profiler_capped",
            max_temp_c=None,
            label=names.get(filename, filename),
        )
        result = {
            "model": names.get(filename, filename),
            "artifact": filename,
            "accuracy_percent": round(accuracy_pct, 4),
            "accuracy_samples": int(accuracy["samples"]),
            "accuracy_ci95_low_percent": round(ci_low * 100, 4),
            "accuracy_ci95_high_percent": round(ci_high * 100, 4),
            "scalar_pp512_tok_s": round(pp, 4),
            "scalar_tg128_tok_s": round(tg, 4),
            "scalar_tg128_sd": round(tg_sd, 4),
            "estimated_profiler_peak_rss_mib": round(rss_mib, 2),
            "s_acc": round(scored.s_acc or 0, 4),
            "s_perf": round(scored.s_perf or 0, 4),
            "s_eff": round(scored.s_eff or 0, 4),
            "s_total": round(scored.s_total or 0, 4),
            "thermal_status": "unavailable; no penalty applied",
            "model_sha256": perf["model_sha256"],
            "benchmark_binary_sha256": perf["bench_identity"]["sha256"],
            "scalar_hardware_context": hardware_context(perf),
            "accuracy_hardware_context": hardware_context(accuracy),
            "vector_hardware_context": hardware_context(vector) if vector else None,
            "stem_hardware_context": stem_result["hardware_context"] if stem_result else None,
            "stem_responses_completed": stem_result["responses"] if stem_result else 0,
            "stem_responses_expected": len(prompts()),
            "stem_status": stem_result["status"] if stem_result else "not_started",
            "selection_status": (
                "pending_manual_adjudication"
                if stem_result and stem_result["status"] == "complete"
                else "pending_stem_completion"
            ),
            "vector_pp512_tok_s": None,
            "vector_tg128_tok_s": None,
            "vector_tg128_sd": None,
            "decode_gain": None,
            "vector_estimated_profiler_peak_rss_mib": None,
            "vector_s_perf": None,
            "vector_s_eff": None,
            "vector_s_total": None,
            "vector_benchmark_binary_sha256": None,
        }
        if vector is not None:
            vector_pp, vector_tg, vector_tg_sd, vector_rss_mib = _throughput_metrics(vector)
            vector_scored = score(
                accuracy=accuracy_pct,
                tps_actual=vector_tg,
                peak_rss_gb=vector_rss_mib / 1024,
                tps_max=15,
                tps_max_provenance="profiler_reference",
                performance_formula="profiler_capped",
                max_temp_c=None,
                label=names.get(filename, filename),
            )
            result.update(
                {
                    "vector_pp512_tok_s": round(vector_pp, 4),
                    "vector_tg128_tok_s": round(vector_tg, 4),
                    "vector_tg128_sd": round(vector_tg_sd, 4),
                    "decode_gain": round(vector_tg / tg, 4),
                    "vector_estimated_profiler_peak_rss_mib": round(vector_rss_mib, 2),
                    "vector_s_perf": round(vector_scored.s_perf or 0, 4),
                    "vector_s_eff": round(vector_scored.s_eff or 0, 4),
                    "vector_s_total": round(vector_scored.s_total or 0, 4),
                    "vector_benchmark_binary_sha256": vector["bench_identity"]["sha256"],
                }
            )
        results.append(result)
    results.sort(key=lambda row: row["s_total"], reverse=True)
    for rank, row in enumerate(results, 1):
        row["rank"] = rank
    return results


def write_results(path: Path, results: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "rank",
        "model",
        "artifact",
        "accuracy_percent",
        "accuracy_samples",
        "accuracy_ci95_low_percent",
        "accuracy_ci95_high_percent",
        "scalar_pp512_tok_s",
        "scalar_tg128_tok_s",
        "scalar_tg128_sd",
        "estimated_profiler_peak_rss_mib",
        "s_acc",
        "s_perf",
        "s_eff",
        "s_total",
        "vector_pp512_tok_s",
        "vector_tg128_tok_s",
        "vector_tg128_sd",
        "decode_gain",
        "vector_estimated_profiler_peak_rss_mib",
        "vector_s_perf",
        "vector_s_eff",
        "vector_s_total",
        "thermal_status",
        "model_sha256",
        "benchmark_binary_sha256",
        "vector_benchmark_binary_sha256",
        "scalar_hardware_context",
        "accuracy_hardware_context",
        "vector_hardware_context",
        "stem_hardware_context",
        "stem_responses_completed",
        "stem_responses_expected",
        "stem_status",
        "selection_status",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)


def validated_stem_rows(rows: list[dict]) -> list[dict]:
    expected = {prompt.id: prompt for prompt in prompts()}
    seen = set()
    contexts = set()
    hashes = {}
    result = []
    for row in rows:
        key = (row["model"], row["id"])
        if key in seen:
            raise ValueError(f"duplicate STEM response: {key}")
        seen.add(key)
        contexts.add(hardware_context(row))
        if len(contexts) > 1:
            raise ValueError("mixed hardware contexts in STEM aggregate; report each separately")
        if row["id"] not in expected:
            raise ValueError(f"unknown STEM prompt: {row['id']}")
        prompt = expected[row["id"]]
        if row.get("format") != prompt.format or row.get("subject") != prompt.subject:
            raise ValueError(f"mismatched STEM prompt metadata: {key}")
        model_hash = row.get("model_sha256")
        if not model_hash or hashes.setdefault(row["model"], model_hash) != model_hash:
            raise ValueError(f"missing or mismatched model hashes for {row['model']}")
        copied = {**row, "expected": prompt.expected}
        if prompt.format == "multiple_choice":
            choice = selected_option(row.get("answer", ""))
            copied.update(selected=choice, correct=choice == prompt.expected)
        result.append(copied)
    return result


def stem_summary(rows: list[dict], names: dict[str, str]) -> dict[str, dict]:
    summary: dict[str, dict] = {}
    by_model: dict[str, list[dict]] = defaultdict(list)
    for row in validated_stem_rows(rows):
        by_model[names.get(row["model"], row["model"])].append(row)
    for model, model_rows in by_model.items():
        if len({row["model"] for row in model_rows}) != 1:
            raise ValueError(f"multiple artifacts share the display label {model}")
        mc = [row for row in model_rows if row["format"] == "multiple_choice"]
        counts = Counter(
            (row["subject"], bool(row.get("correct")))
            for row in mc
            if row.get("correct") is not None
        )
        summary[model] = {
            "math_mc": counts[("math", True)],
            "science_mc": counts[("science", True)],
            "overall_mc": sum(row.get("correct") is True for row in mc),
            "responses": len(model_rows),
            "expected_responses": len(prompts()),
            "status": "complete" if len(model_rows) == len(prompts()) else "incomplete",
            "hardware_context": hardware_context(model_rows[0]),
            "model_sha256": model_rows[0]["model_sha256"],
            "model": model_rows[0]["model"],
            "math_mc_completed": sum(row["subject"] == "math" for row in mc),
            "science_mc_completed": sum(row["subject"] == "science" for row in mc),
            "written_completed": sum(row["format"] == "written" for row in model_rows),
        }
    return summary


def compact(text: str, limit: int = 150) -> str:
    value = " ".join(text.split()).replace("|", "\\|")
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def write_report(
    path: Path,
    results: list[dict],
    stem_rows: list[dict],
    names: dict[str, str],
    artifact_rows: list[dict[str, str]],
) -> None:
    stem_rows = validated_stem_rows(stem_rows)
    stem = stem_summary(stem_rows, names)
    for row in results:
        stem_result = stem.get(row["model"])
        if stem_result:
            _require_matching_hashes({**row, "model": row["artifact"]}, stem_result)
    lines = [
        "# ADTC balanced-model scalar campaign",
        "",
        "## Provisional score ranking",
        "",
    ]
    if results:
        winner = results[0]
        lines.append(
            f"**{winner['model']}** ranks first under the executable profiler formula with "
            f"a scalar total of **{winner['s_total']:.4f}**. This is an ARC-Easy proxy, not "
            "the unavailable judging-panel score. It does not establish the final selection."
        )
        winner_stem = stem.get(winner["model"])
        completed = winner_stem["responses"] if winner_stem else 0
        lines.append(
            f"The score leader has {completed}/{len(prompts())} STEM responses recorded. "
            + (
                "STEM completion and manual adjudication are still required."
                if completed < len(prompts())
                else "Manual adjudication of the complete STEM and judge responses is required."
            )
        )
    else:
        lines.append("No model has completed both throughput and ARC-Easy-500.")
    lines.extend(
        [
            "",
            "## Scored results",
            "",
            "| Rank | Model | ARC-Easy-500 (95% CI) | Scalar → vector pp512 | Scalar → vector tg128 | Decode gain | Scalar → vector RSS | Scalar → vector total |",
            "|---:|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in results:
        vector_pp = row["vector_pp512_tok_s"]
        vector_tg = row["vector_tg128_tok_s"]
        vector_rss = row["vector_estimated_profiler_peak_rss_mib"]
        vector_total = row["vector_s_total"]
        pp_cell = (
            f"{row['scalar_pp512_tok_s']:.2f} → {vector_pp:.2f}"
            if vector_pp
            else f"{row['scalar_pp512_tok_s']:.2f} → pending"
        )
        tg_cell = (
            f"{row['scalar_tg128_tok_s']:.2f} → {vector_tg:.2f}"
            if vector_tg
            else f"{row['scalar_tg128_tok_s']:.2f} → pending"
        )
        gain_cell = f"{row['decode_gain']:.2f}×" if row["decode_gain"] else "pending"
        rss_cell = (
            f"{row['estimated_profiler_peak_rss_mib']:,.0f} → {vector_rss:,.0f} MiB"
            if vector_rss
            else f"{row['estimated_profiler_peak_rss_mib']:,.0f} → pending"
        )
        total_cell = (
            f"**{row['s_total']:.4f}** → {vector_total:.4f}"
            if vector_total
            else f"**{row['s_total']:.4f}** → pending"
        )
        lines.append(
            f"| {row['rank']} | {row['model']} | {row['accuracy_percent']:.1f}% "
            f"({row['accuracy_ci95_low_percent']:.1f}–"
            f"{row['accuracy_ci95_high_percent']:.1f}) | {pp_cell} | {tg_cell} | "
            f"{gain_cell} | {rss_cell} | {total_cell} |"
        )
    lines.extend(
        [
            "",
            (
                "The score is `0.50 × S_acc + 0.30 × S_perf + 0.20 × S_eff`. The "
                "executable profiler fixes the performance reference at 15 tok/s. RSS is "
                "the measured `llama-bench` process-tree peak plus the campaign's fixed "
                "45 MiB estimate for the profiler Python root. The scalar column determines "
                "rank because it matches the executable profiler build. The vector column is "
                "the separately measured portable AVX2/FMA/F16C proxy. Temperature is "
                "unavailable on GCP, so no thermal penalty is applied."
            ),
            "",
            "## Candidate set",
            "",
            "| Model | Role | Quantization | Test size | License | b10175 gate |",
            "|---|---|---|---:|---|---|",
        ]
    )
    for row in artifact_rows:
        source = f"https://huggingface.co/{row['source_repository']}/tree/{row['source_revision']}"
        lines.append(
            f"| [{row['model']}]({source}) | {row['role']} | {row['quantization']} | "
            f"{int(row['test_bytes']) / 1024**2:,.1f} MiB | {row['license']} | "
            f"{row['runtime_gate']} |"
        )
    lines.extend(
        [
            "",
            (
                "The candidate set comes from the repository-wide "
                "[Local AI Zone census](../../../muta-iq/opt/research/"
                "r8_local_ai_zone.md). Published MATH, AIME, GPQA, MMLU, and instruction "
                "scores were used only to decide what to test; they are not combined with "
                "the measurements below."
            ),
            "",
            "## Method",
            "",
            (
                "The scored throughput and ARC-Easy runs used the `n2-custom-4-8192` VM with two "
                "physical cores, four logical CPUs, 8 GB-class RAM, and no swap. The gateway "
                "and Google Ops Agent were stopped. An exclusive lock prevented overlapping "
                "campaign processes."
            ),
            "",
            (
                "Throughput uses llama.cpp b10175 with AVX, AVX2, FMA, and F16C disabled: "
                "`llama-bench -p 512 -n 128 -ngl 0 -r 5`. ARC-Easy uses the profiler's own "
                "`llama-cpp-python` and `lm-eval` path with 500 samples and seed 42. That "
                "accuracy path is vector-enabled by the official image design; scalar versus "
                "vector is a throughput distinction, not a separate accuracy treatment."
            ),
            "",
            (
                "MiniCPM5 was quantized from its official F16 GGUF with the b10360 "
                "quantizer's `--pure Q4_0` mode. Its tensor audit found 170 Q4_0 tensors and "
                "49 F32 scalar tensors; both token embeddings and output weights are Q4_0."
            ),
            "",
            (
                "Spark-X2.5-1.7B was tested only at the load gate. It fails under b10175 "
                "because that runtime predates Spark architecture support, so it is not "
                "ranked."
            ),
            "",
            (
                "This is a base-model selection screen. The incumbent has already been "
                "fine-tuned, while the challengers have not. A challenger that wins this "
                "table still requires a licence-clean adaptation, base-versus-final evidence, "
                "template validation, and a complete profiler rerun before it is a submission "
                "candidate."
            ),
            "",
            (
                "A high computed total is necessary but not sufficient. The competition "
                "also requires useful task capability and material adaptation from the base "
                "model. The STEM battery therefore remains a promotion gate, and the winning "
                "base cannot be submitted as though this screening result completed the "
                "fine-tuning and provenance requirements."
            ),
            "",
            (
                "The exact Gate 1 chat replay and its separate capability ranking are in "
                "[judges-report.md](judges-report.md). Those rubric scores are not inserted "
                "into the executable profiler formula."
            ),
            "",
            "## Common 100-prompt STEM battery",
            "",
            (
                "The battery contains 25 multiple-choice and 25 written prompts in each of "
                "mathematics and science. Every model receives identical raw prompts at "
                "context 2,048, temperature 0, and seed 42. Multiple-choice responses allow "
                "256 generated tokens; written responses allow 512."
            ),
            "",
        ]
    )
    if stem:
        lines.extend(
            [
                "| Model | Math MC | Science MC | MC total | Written captured | Responses captured | Status | Execution context |",
                "|---|---:|---:|---:|---:|---:|---|---|",
            ]
        )
        for model in [row["model"] for row in results]:
            row = stem.get(model)
            if row:
                lines.append(
                    f"| {model} | {row['math_mc']}/{row['math_mc_completed']} | "
                    f"{row['science_mc']}/{row['science_mc_completed']} | "
                    f"{row['overall_mc']}/{row['math_mc_completed'] + row['science_mc_completed']} | "
                    f"{row['written_completed']}/50 | {row['responses']}/100 | "
                    f"{row['status']} | {row['hardware_context']} |"
                )
            else:
                lines.append(
                    f"| {model} | 0/0 | 0/0 | 0/0 | 0/50 | 0/100 | not_started | unrecorded |"
                )
        lines.extend(
            [
                "",
                (
                    "Multiple-choice denominators count captured responses; the full suite has "
                    "25 per subject. Options are reparsed from saved answer text. This does not "
                    "check explanation correctness. All responses require independent adjudication "
                    "and are not mixed into the profiler score."
                ),
            ]
        )
    else:
        lines.append("The response phase has not completed.")

    if stem_rows:
        response_by_key = {
            (names.get(row["model"], row["model"]), row["id"]): row for row in stem_rows
        }
        ordered_models = [row["model"] for row in results]
        lines.extend(
            [
                "",
                "## Prompt outputs by model",
                "",
                (
                    "Each table contains the same 100 prompts. Multiple-choice rows show the "
                    "parsed final option; written rows remain ungraded. Responses are shortened "
                    "here for readability, while the full text remains in `raw/stem-responses.jsonl`."
                ),
                "",
            ]
        )
        for model in ordered_models:
            lines.extend(
                [
                    f"<details><summary>{model} · 100-prompt output table</summary>",
                    "",
                    "| ID | Subject | Format | Expected | Result | Response excerpt |",
                    "|---|---|---|---|---|---|",
                ]
            )
            for prompt in prompts():
                response = response_by_key.get((model, prompt.id))
                if response is None:
                    result = "not run"
                    excerpt = ""
                elif prompt.format == "multiple_choice":
                    marker = "✓" if response.get("correct") else "✗"
                    result = f"{marker} {response.get('selected') or 'no option'}"
                    excerpt = compact(response.get("answer", ""), 240)
                else:
                    result = "ungraded"
                    excerpt = compact(response.get("answer", ""), 240)
                lines.append(
                    f"| {prompt.id} | {prompt.subject} | {prompt.format.replace('_', ' ')} | "
                    f"{compact(prompt.expected, 120)} | {result} | {excerpt} |"
                )
            lines.extend(["", "</details>", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--throughput", type=Path, required=True)
    parser.add_argument("--vector-throughput", type=Path)
    parser.add_argument("--accuracy", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--stem", type=Path, required=True)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    names, artifact_rows = load_artifacts(args.artifacts)
    vector_rows = read_jsonl(args.vector_throughput) if args.vector_throughput else []
    stem_rows = read_jsonl(args.stem)
    results = summarize(
        read_jsonl(args.throughput), read_jsonl(args.accuracy), names, vector_rows, stem_rows
    )
    write_results(args.csv, results)
    write_report(args.report, results, stem_rows, names, artifact_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
