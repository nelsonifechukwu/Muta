from __future__ import annotations

import hashlib
import json

import pytest

from bench.official_profiler_summary import summarize


def _report() -> dict:
    return {
        "profiler_version": "adtc-profiler 0.1.0",
        "environment": {"measured_on": "participant_laptop", "cpu_model": "test"},
        "reproducibility": {"random_seed": 42},
        "model_info": {"params_match": True, "params_count": 100},
        "throughput": {
            "tokens_per_second_generation": 10.0,
            "first_token_latency_ms": 20.0,
            "prompt_tokens": 512,
            "generated_tokens": 128,
        },
        "memory": {"peak_rss_mb": 1024.0},
        "cpu_thermal": {"core_temp_c_peak": None, "throttled": False},
        "accuracy": [
            {
                "benchmark": "arc_easy",
                "samples": 50,
                "score": 0.7,
                "metric": "acc_norm",
            }
        ],
    }


def _manifest(report_sha: str) -> dict:
    return {
        "schema_version": 1,
        "run_mode": "participant",
        "hardware_context": "test_host",
        "profiler_source_commit": "profiler-sha",
        "benchmark_binary": {
            "sha256": "binary-sha",
            "llama_cpp_commit": "llama-sha",
            "build": "no avx",
        },
        "accuracy_stack": {
            "llama_cpp_python": "0.3.35",
            "libllama_sha256": "libllama-sha",
            "lm_eval": "0.4.12",
        },
        "models": [
            {
                "model": "candidate.gguf",
                "model_sha256": "model-sha",
                "model_bytes": 123,
                "report": "candidate.json",
                "report_sha256": report_sha,
            }
        ],
    }


def test_summarizes_direct_profiler_measurements(tmp_path):
    report_path = tmp_path / "candidate.json"
    report_path.write_text(json.dumps(_report()))
    report_sha = hashlib.sha256(report_path.read_bytes()).hexdigest()
    result = summarize(_manifest(report_sha), tmp_path)
    model = result["models"][0]
    assert model["peak_rss_mib_mean"] == 1024.0
    assert model["rss_estimated"] is False
    assert model["accuracy_proxy"] == 70.0
    assert model["scores"]["15.0"]["s_total"] == pytest.approx(72.1429)
    assert result["winners"]["15.0"]["model"] == "candidate.gguf"


def test_rejects_report_hash_mismatch(tmp_path):
    (tmp_path / "candidate.json").write_text(json.dumps(_report()))
    with pytest.raises(ValueError, match="report hash mismatch"):
        summarize(_manifest("wrong"), tmp_path)


def test_rejects_empty_manifest(tmp_path):
    manifest = _manifest("unused")
    manifest["models"] = []
    with pytest.raises(ValueError, match="at least one model"):
        summarize(manifest, tmp_path)


def test_rejects_incomplete_model_identity(tmp_path):
    manifest = _manifest("unused")
    del manifest["models"][0]["model_sha256"]
    with pytest.raises(ValueError, match="missing model_sha256"):
        summarize(manifest, tmp_path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("model_info", {"params_match": False}, "parameter check"),
        ("accuracy", [], "exactly one arc_easy"),
        ("throughput", {}, "invalid profiler throughput"),
    ],
)
def test_rejects_incomplete_profiler_evidence(tmp_path, field, value, message):
    report = _report()
    report[field] = value
    report_path = tmp_path / "candidate.json"
    report_path.write_text(json.dumps(report))
    report_sha = hashlib.sha256(report_path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match=message):
        summarize(_manifest(report_sha), tmp_path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("reproducibility", {"random_seed": 7}, "seed is not 42"),
        (
            "throughput",
            {
                "tokens_per_second_generation": 10.0,
                "prompt_tokens": 256,
                "generated_tokens": 128,
            },
            "p512/tg128",
        ),
        (
            "accuracy",
            [{"benchmark": "arc_easy", "samples": 10, "score": 0.7, "metric": "acc_norm"}],
            "ARC-Easy-50",
        ),
    ],
)
def test_rejects_wrong_profiler_workload(tmp_path, field, value, message):
    report = _report()
    report[field] = value
    report_path = tmp_path / "candidate.json"
    report_path.write_text(json.dumps(report))
    report_sha = hashlib.sha256(report_path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match=message):
        summarize(_manifest(report_sha), tmp_path)
