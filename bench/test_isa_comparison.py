import copy
import json
from pathlib import Path

import pytest

from bench.isa_comparison import AVX2_BINARY_SHA256, ROSTER, compare, read_jsonl

ROOT = Path(__file__).resolve().parent.parent
CAMPAIGN = ROOT / "bench" / "measurements" / "campaign-20260819"


def _existing_avx2_roster() -> list[dict]:
    selected = {}
    for row in read_jsonl(CAMPAIGN / "avx2.jsonl"):
        model = row.get("model")
        if (
            model in ROSTER
            and model not in selected
            and row.get("kind") == "throughput"
            and row.get("ok") is True
            and row.get("bench_identity", {}).get("sha256") == AVX2_BINARY_SHA256
        ):
            selected[model] = row
    return list(selected.values())


def test_existing_evidence_produces_separate_scalar_and_avx2_winners():
    summary = compare(
        read_jsonl(CAMPAIGN / "scalar15.jsonl"),
        _existing_avx2_roster(),
        json.loads((CAMPAIGN / "summary.json").read_text()),
    )

    assert summary["winners"]["scalar"]["model"] == "muta-tutor-qwen3-1.7b-q4_0.gguf"
    assert summary["winners"]["avx2"]["model"] == "Q4_K_M-tied.gguf"
    bitcpm = next(item for item in summary["models"] if item["model"].startswith("bitcpm"))
    assert bitcpm["delta"]["decode_speedup"] > 9


def test_wrong_avx2_binary_fails_closed():
    rows = _existing_avx2_roster()
    broken = copy.deepcopy(rows)
    broken[0]["bench_identity"]["sha256"] = "0" * 64

    with pytest.raises(ValueError, match="benchmark binary hash mismatch"):
        compare(
            read_jsonl(CAMPAIGN / "scalar15.jsonl"),
            broken,
            json.loads((CAMPAIGN / "summary.json").read_text()),
        )
