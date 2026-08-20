import json
from pathlib import Path

import pytest

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
        assert validated["scalar"]["accuracy_percent_500"] == 71.8
        assert validated["avx2"]["accuracy_percent_500"] == 71.8


def test_model_extension_is_fail_closed_and_identity_bound() -> None:
    result = build_summary(
        EVIDENCE / "screen-accuracy.jsonl",
        EVIDENCE / "screen-throughput.jsonl",
    )
    assert len(result["models"]) == 8
    assert result["schema_version"] == 3
    assert result["accuracy_shared_across_cpu_configurations"] is True
    assert result["accuracy_protocol"]["screen_samples"] == 50
    assert [item["rank"] for item in result["models"]] == list(range(1, 9))
    assert all(
        item["scalar"]["accuracy_percent"] == item["avx2"]["accuracy_percent"]
        and item["scalar"]["accuracy_samples"] == item["avx2"]["accuracy_samples"] == 50
        for item in result["models"]
    )
    assert all(len(item["model_sha256"]) == 64 for item in result["models"])
    assert result["benchmark_identity_sha256"].keys() == {"scalar", "avx2"}
    assert result["winner"] == {
        "model": "Qwen2.5-1.5B-Instruct-Q4_K_M.gguf",
        "s_total": 82.8697,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    (("kind", "throughput"), ("benchmark", "arc_challenge"), ("metric", "acc"), ("samples", 49)),
)
def test_accuracy_protocol_mismatch_fails_closed(tmp_path: Path, field: str, value: object) -> None:
    rows = [
        json.loads(line) for line in (EVIDENCE / "screen-accuracy.jsonl").read_text().splitlines()
    ]
    rows[0][field] = value
    path = tmp_path / "accuracy.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")

    with pytest.raises(ValueError, match="unexpected screen accuracy protocol"):
        build_summary(path, EVIDENCE / "screen-throughput.jsonl")


def test_duplicate_validation_row_fails_closed(tmp_path: Path) -> None:
    row = (EVIDENCE / "qwen25-15b-arc-easy-500.jsonl").read_text().strip()
    path = tmp_path / "validation.jsonl"
    path.write_text(f"{row}\n{row}\n")

    with pytest.raises(ValueError, match="duplicate model rows"):
        build_summary(
            EVIDENCE / "screen-accuracy.jsonl",
            EVIDENCE / "screen-throughput.jsonl",
            path,
        )
