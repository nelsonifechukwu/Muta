import json
from pathlib import Path

from bench.model_extension_summary import build_summary

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "bench/measurements/model-extension"


def test_committed_summary_reproduces_from_raw_evidence() -> None:
    validation = EVIDENCE / "qwen25-15b-arc-easy-500.jsonl"
    result = build_summary(
        EVIDENCE / "screen-accuracy.jsonl",
        EVIDENCE / "screen-throughput.jsonl",
        validation if validation.exists() else None,
    )
    assert result == json.loads((EVIDENCE / "summary.json").read_text())
    if validation.exists():
        validated = result["models"][0]
        assert validated["accuracy_validation"]["accuracy_percent"] == 71.8
        assert validated["scalar"]["s_total_accuracy_500"] == 63.8176
        assert validated["avx2"]["s_total_accuracy_500"] == 80.7697


def test_model_extension_is_fail_closed_and_identity_bound() -> None:
    result = build_summary(
        EVIDENCE / "screen-accuracy.jsonl",
        EVIDENCE / "screen-throughput.jsonl",
    )
    assert len(result["models"]) == 8
    assert all(len(item["model_sha256"]) == 64 for item in result["models"])
    assert result["benchmark_identity_sha256"].keys() == {"scalar", "avx2"}
    assert result["winner"] == {
        "model": "Qwen2.5-1.5B-Instruct-Q4_K_M.gguf",
        "s_total": 82.8697,
    }
