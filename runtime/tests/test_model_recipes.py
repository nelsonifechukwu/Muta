"""Keep the reproducible GGUF recipes aligned with the exact runtime catalog artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_model_recipe_hashes_and_winner_metadata_match_catalog():
    catalog = json.loads((ROOT / "runtime" / "model-catalog.json").read_text())
    models = {model["id"]: model for model in catalog["models"]}
    winner_recipe = (ROOT / "muta-iq" / "download_model.sh").read_text()
    qwen25_recipe = (ROOT / "muta-iq" / "fetch_qwen25.sh").read_text()
    math_expert_recipe = (ROOT / "muta-iq" / "fetch_math_expert.sh").read_text()
    bitcpm_recipe = (ROOT / "muta-iq" / "fetch_bitcpm.sh").read_text()

    qwen35 = models["muta-tutor-qwen3.5-0.8b-q4_0"]
    qwen25 = models["qwen2.5-1.5b-instruct-q4_k_m"]
    artifacts = json.loads(
        (ROOT / "model-development" / "finetune" / "results" / "artifacts.json").read_text()
    )
    artifact_by_id = {item["id"]: item for item in artifacts["artifacts"]}
    summary = json.loads(
        (ROOT / "model-development" / "finetune" / "results" / "summary.json").read_text()
    )
    summary_by_id = {item["id"]: item for item in summary["models"]}

    assert qwen35["sha256"] in winner_recipe
    assert str(qwen35["size_bytes"]) in winner_recipe
    assert "timiiowolabi/Muta-Tutor-Qwen3.5-0.8B-ADTC-GGUF" in winner_recipe
    assert qwen35["sha256"] == artifact_by_id["qwen35-bf16-r16-mcq-lr2e5-400"]["sha256"]
    assert qwen35["arc_easy"] == pytest.approx(
        summary_by_id["qwen35"]["accuracy"]["candidate_percent"] / 100
    )
    assert qwen35["audit_proxy_tps"] == pytest.approx(
        summary_by_id["qwen35"]["scalar"]["candidate_tps"]
    )

    assert qwen25["sha256"] in qwen25_recipe
    assert str(qwen25["size_bytes"]) in qwen25_recipe
    assert "timiiowolabi/Muta-Tutor-Qwen2.5-1.5B-ADTC-GGUF" in qwen25_recipe
    assert qwen25["sha256"] == artifact_by_id[
        "qwen25-bf16-r16-licensed-mcq-lr2e5-500"
    ]["sha256"]
    assert qwen25["arc_easy"] == pytest.approx(
        summary_by_id["qwen25"]["accuracy"]["candidate_percent"] / 100
    )
    assert qwen25["audit_proxy_tps"] == pytest.approx(
        summary_by_id["qwen25"]["scalar"]["candidate_tps"]
    )
    assert models["qwen3-0.6b-math-expert-q4_k_m"]["sha256"] in math_expert_recipe
    assert str(models["qwen3-0.6b-math-expert-q4_k_m"]["size_bytes"]) in math_expert_recipe
    assert models["bitcpm4-8b-tq2_0-envocab"]["sha256"] in bitcpm_recipe
