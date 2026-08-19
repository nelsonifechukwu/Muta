from __future__ import annotations

import json

import pytest

from bench.campaign_summary import main, summarize


def row(
    model: str, *, context: str = "gcp", binary: str = "abc", tps: float = 20, rss: float = 1024
):
    return {
        "ok": True,
        "kind": "throughput",
        "model": model,
        "model_sha256": model * 3,
        "model_bytes": 123,
        "hardware_context": context,
        "bench_identity": {"sha256": binary},
        "tg_avg_ts": tps,
        "peak_rss_tree_mb": rss,
        "profiler_python_overhead_mib_note": 45,
    }


def test_summary_uses_profiler_cap_and_keeps_repetitions():
    rows = [row("a", tps=20), row("a", tps=22)]
    rows.append(
        {
            "ok": True,
            "kind": "accuracy",
            "model": "a",
            "model_sha256": "aaa",
            "hardware_context": "gcp",
            "benchmark": "arc_easy",
            "score": 0.7,
            "samples": 100,
        }
    )
    result = summarize(rows, tps_maxes=[15], accuracy_task="arc_easy")
    model = result["models"][0]
    assert model["throughput_rounds"] == 2
    assert model["throughput_repetitions"] == 2
    assert model["tg_tps_mean"] == 21
    assert model["scores"]["15"]["s_perf"] == 100
    assert result["winners"]["15"]["model"] == "a"
    assert model["accuracy_tasks"]["arc_easy"] == {
        "score_percent": 70.0,
        "samples": 100,
        "metric": None,
        "ci95_percent": [60.42, 78.11],
    }


def test_summary_webpage_relative_raises_denominator_to_candidate_speed():
    measured = row("a", tps=20)
    accuracy = {
        "ok": True,
        "kind": "accuracy",
        "model": "a",
        "model_sha256": "aaa",
        "hardware_context": "gcp",
        "benchmark": "arc_easy",
        "score": 0.7,
        "samples": 50,
    }
    result = summarize(
        [measured, accuracy],
        tps_maxes=[10],
        accuracy_task="arc_easy",
        performance_formula="website_relative",
    )
    score = result["models"][0]["scores"]["10"]
    assert score["s_perf"] == 100
    assert score["effective_tps_max"] == 20
    assert "webpage alternative" in result["performance_formula"]


def test_summary_refuses_mixed_hosts():
    with pytest.raises(ValueError, match="hardware contexts"):
        summarize([row("a"), row("a", context="mac")], tps_maxes=[15], accuracy_task="arc_easy")


def test_summary_allows_separately_labelled_accuracy_context():
    accuracy = {
        "ok": True,
        "kind": "accuracy",
        "model": "a",
        "model_sha256": "aaa",
        "hardware_context": "official_profiler_accuracy_wheel",
        "benchmark": "arc_easy",
        "score": 0.7,
        "samples": 50,
    }
    result = summarize([row("a"), accuracy], tps_maxes=[15], accuracy_task="arc_easy")
    assert result["accuracy_hardware_contexts"] == ["official_profiler_accuracy_wheel"]
    assert result["models"][0]["accuracy_proxy"] == 70.0


def test_summary_refuses_mixed_binaries():
    with pytest.raises(ValueError, match="benchmark binaries"):
        summarize(
            [row("a"), row("a", binary="different")], tps_maxes=[15], accuracy_task="arc_easy"
        )


@pytest.mark.parametrize("missing", ["hardware_context", "bench_identity"])
def test_summary_refuses_missing_throughput_provenance(missing):
    measured = row("a")
    measured.pop(missing)
    expected = "hardware contexts" if missing == "hardware_context" else "benchmark binaries"
    with pytest.raises(ValueError, match=expected):
        summarize([measured], tps_maxes=[15], accuracy_task="arc_easy")


def test_summary_refuses_missing_profiler_root_estimate():
    measured = row("a")
    measured.pop("profiler_python_overhead_mib_note")
    with pytest.raises(ValueError, match="profiler-root RSS estimate"):
        summarize([measured], tps_maxes=[15], accuracy_task="arc_easy")


def test_summary_refuses_same_filename_with_different_hashes():
    rows = [row("a"), row("a")]
    rows[1]["model_sha256"] = "different"
    with pytest.raises(ValueError, match="different artifacts"):
        summarize(rows, tps_maxes=[15], accuracy_task="arc_easy")


def test_summary_refuses_any_failed_evidence_row():
    failed = row("crashed")
    failed.update({"ok": False, "error": "illegal instruction"})
    with pytest.raises(ValueError, match="failed row"):
        summarize([row("winner"), failed], tps_maxes=[15], accuracy_task="arc_easy")


def test_profiler_formula_rejects_non_15_reference_even_without_accuracy():
    with pytest.raises(ValueError, match="exactly one TPS reference: 15"):
        summarize([row("a")], tps_maxes=[30], accuracy_task="arc_easy")


def test_summary_uses_llama_bench_internal_samples_when_present():
    measured = row("a", tps=999)
    measured["raw_bench_rows"] = [{"n_prompt": 0, "n_gen": 128, "samples_ts": [10.0, 12.0, 14.0]}]
    result = summarize([measured], tps_maxes=[15], accuracy_task="arc_easy")
    model = result["models"][0]
    assert model["throughput_rounds"] == 1
    assert model["throughput_repetitions"] == 3
    assert model["tg_tps_mean"] == 12.0


def test_summary_labels_single_repeat_screening_without_hiding_command():
    measured = row("a")
    measured["command"] = ["llama-bench", "-m", "a.gguf", "-r", "1"]
    result = summarize([measured], tps_maxes=[15], accuracy_task="arc_easy")
    model = result["models"][0]
    assert model["measurement_tier"] == "single_repeat_screen"
    assert model["commands"] == [["llama-bench", "-m", "a.gguf", "-r", "1"]]


def test_summary_adds_recorded_profiler_root_process_rss():
    measured = row("a", rss=1024)
    measured["profiler_python_overhead_mib_note"] = 45
    result = summarize([measured], tps_maxes=[15], accuracy_task="arc_easy")
    assert result["models"][0]["peak_rss_mib_mean"] == 1069.0
    assert result["models"][0]["rss_accounting"] == (
        "measured llama-bench child-tree peak plus the raw row's 45 MiB "
        "official-profiler-root estimate"
    )
    assert result["models"][0]["rss_estimated"] is True


def test_cli_imports_only_accuracy_rows_from_separate_evidence(tmp_path):
    throughput_path = tmp_path / "throughput.jsonl"
    accuracy_path = tmp_path / "accuracy.jsonl"
    output_json = tmp_path / "summary.json"
    output_tsv = tmp_path / "summary.tsv"
    throughput_path.write_text(json.dumps(row("a")) + "\n")
    accuracy_path.write_text(
        "\n".join(
            [
                json.dumps(row("a", context="incompatible-throughput-host")),
                json.dumps(
                    {
                        "ok": True,
                        "kind": "accuracy",
                        "model": "a",
                        "model_sha256": "aaa",
                        "hardware_context": "profiler-accuracy-wheel",
                        "benchmark": "arc_easy",
                        "score": 0.7,
                        "samples": 50,
                    }
                ),
            ]
        )
        + "\n"
    )

    assert (
        main(
            [
                "--input",
                str(throughput_path),
                "--accuracy-input",
                str(accuracy_path),
                "--json",
                str(output_json),
                "--tsv",
                str(output_tsv),
            ]
        )
        == 0
    )
    result = json.loads(output_json.read_text())
    assert result["hardware_context"] == "gcp"
    assert result["accuracy_hardware_contexts"] == ["profiler-accuracy-wheel"]
    assert result["models"][0]["accuracy_proxy"] == 70.0
