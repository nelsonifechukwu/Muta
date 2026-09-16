from __future__ import annotations

import csv

import pytest

from bench.balanced_model_report import stem_summary, summarize, write_report, write_results
from bench.stem_prompt_suite import prompts


def throughput(model: str, pp: float, tg: float, rss: float, binary: str) -> dict:
    return {
        "kind": "throughput",
        "ok": True,
        "model": model,
        "raw_bench_rows": [
            {"n_prompt": 512, "n_gen": 0, "samples_ts": [pp, pp]},
            {"n_prompt": 0, "n_gen": 128, "samples_ts": [tg, tg]},
        ],
        "peak_rss_tree_mb": rss,
        "profiler_python_overhead_mib_note": 45,
        "model_sha256": f"model-{model}",
        "bench_identity": {"sha256": binary},
    }


def accuracy(model: str, score: float) -> dict:
    return {
        "kind": "accuracy",
        "ok": True,
        "model": model,
        "model_sha256": f"model-{model}",
        "benchmark": "arc_easy",
        "samples": 500,
        "score": score,
    }


def test_summary_pairs_scalar_and_vector_by_exact_artifact(tmp_path):
    rows = summarize(
        [throughput("candidate.gguf", 10, 5, 1000, "scalar-bin")],
        [accuracy("candidate.gguf", 0.75)],
        {"candidate.gguf": "Candidate"},
        [throughput("candidate.gguf", 50, 15, 1200, "vector-bin")],
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["model"] == "Candidate"
    assert row["scalar_pp512_tok_s"] == 10
    assert row["scalar_tg128_tok_s"] == 5
    assert row["vector_pp512_tok_s"] == 50
    assert row["vector_tg128_tok_s"] == 15
    assert row["decode_gain"] == 3
    assert row["benchmark_binary_sha256"] == "scalar-bin"
    assert row["vector_benchmark_binary_sha256"] == "vector-bin"

    out = tmp_path / "results.csv"
    write_results(out, rows)
    written = next(csv.DictReader(out.open()))
    assert written["scalar_tg128_tok_s"] == "5.0"
    assert written["vector_tg128_tok_s"] == "15.0"
    assert written["decode_gain"] == "3.0"


def test_summary_keeps_scalar_only_rows_and_ranks_by_scalar_total():
    rows = summarize(
        [
            throughput("fast.gguf", 20, 15, 800, "scalar-bin"),
            throughput("slow.gguf", 10, 5, 800, "scalar-bin"),
        ],
        [accuracy("fast.gguf", 0.70), accuracy("slow.gguf", 0.70)],
        {"fast.gguf": "Fast", "slow.gguf": "Slow"},
    )

    assert [row["model"] for row in rows] == ["Fast", "Slow"]
    assert rows[0]["rank"] == 1
    assert rows[0]["vector_tg128_tok_s"] is None


@pytest.mark.parametrize("target", ["accuracy", "vector"])
def test_summary_rejects_mismatched_artifacts(target):
    perf = throughput("candidate.gguf", 10, 5, 1000, "scalar")
    acc = accuracy("candidate.gguf", 0.75)
    vector = throughput("candidate.gguf", 50, 15, 1200, "vector")
    (acc if target == "accuracy" else vector)["model_sha256"] = "different-artifact"
    with pytest.raises(ValueError, match="mismatched model hashes"):
        summarize([perf], [acc], {}, [vector])


def test_summary_rejects_an_unverifiable_accuracy_join():
    acc = accuracy("candidate.gguf", 0.75)
    del acc["model_sha256"]
    with pytest.raises(ValueError, match="missing or mismatched model hashes"):
        summarize([throughput("candidate.gguf", 10, 5, 1000, "scalar")], [acc], {})


def stem_row(prompt_id="M01", model="candidate.gguf", context="gcp_scalar", answer="C"):
    prompt = next(prompt for prompt in prompts() if prompt.id == prompt_id)
    return {
        **prompt.as_dict(),
        "model": model,
        "model_sha256": f"model-{model}",
        "hardware_context": context,
        "answer": answer,
        "selected": "A",
        "correct": False,
    }


def test_stem_summary_reparses_saved_text_without_mutating_evidence():
    source = stem_row()
    row = stem_summary([source], {})["candidate.gguf"]
    assert row["math_mc"] == 1
    assert row["math_mc_completed"] == 1
    assert row["science_mc_completed"] == 0
    assert row["responses"] == 1
    assert row["status"] == "incomplete"
    assert row["hardware_context"] == "gcp_scalar"
    assert source["correct"] is False


def test_stem_summary_rejects_duplicate_prompt_pairs():
    row = stem_row()
    with pytest.raises(ValueError, match="duplicate STEM response"):
        stem_summary([row, row], {})


def test_stem_summary_rejects_mixed_contexts_even_for_distinct_models():
    rows = [stem_row(), stem_row(model="other.gguf", context="mac_metal")]
    with pytest.raises(ValueError, match="mixed hardware contexts"):
        stem_summary(rows, {})


def test_stem_summary_distinguishes_unrecorded_hardware():
    row = stem_row()
    del row["hardware_context"]
    assert (
        stem_summary([row], {})["candidate.gguf"]["hardware_context"]
        == "unspecified (legacy record)"
    )


def test_stem_artifact_must_match_scored_artifact():
    stem = stem_row()
    stem["model_sha256"] = "different-artifact"
    with pytest.raises(ValueError, match="mismatched model hashes"):
        summarize(
            [throughput("candidate.gguf", 10, 5, 1000, "scalar")],
            [accuracy("candidate.gguf", 0.75)],
            {},
            stem_rows=[stem],
        )


def test_incomplete_stem_is_not_a_final_selection_and_report_reparses(tmp_path):
    stem = stem_row()
    rows = summarize(
        [throughput("candidate.gguf", 10, 5, 1000, "scalar")],
        [accuracy("candidate.gguf", 0.75)],
        {},
        stem_rows=[stem],
    )
    assert rows[0]["rank"] == 1  # Rank is the estimated profiler score, not promotion.
    assert rows[0]["stem_responses_completed"] == 1
    assert rows[0]["stem_responses_expected"] == 100
    assert rows[0]["selection_status"] == "pending_stem_completion"
    report = tmp_path / "report.md"
    write_report(report, rows, [stem], {}, [])
    text = report.read_text()
    assert "1/100 STEM responses" in text
    assert "does not establish the final selection" in text
    assert "✓ C" in text
    assert "gcp_scalar" in text


def test_complete_stem_still_requires_manual_adjudication():
    stem = [stem_row(prompt.id, answer=prompt.expected) for prompt in prompts()]
    rows = summarize(
        [throughput("candidate.gguf", 10, 5, 1000, "scalar")],
        [accuracy("candidate.gguf", 0.75)],
        {},
        stem_rows=stem,
    )
    assert rows[0]["stem_status"] == "complete"
    assert rows[0]["stem_responses_completed"] == 100
    assert rows[0]["selection_status"] == "pending_manual_adjudication"
