"""Keep the reproducible GGUF recipes aligned with the exact runtime catalog artifacts."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_model_recipe_hashes_and_winner_metadata_match_catalog():
    catalog = json.loads((ROOT / "runtime" / "model-catalog.json").read_text())
    models = {model["id"]: model for model in catalog["models"]}
    winner_recipe = (ROOT / "muta-iq" / "download_model.sh").read_text()
    bitcpm_recipe = (ROOT / "muta-iq" / "fetch_bitcpm.sh").read_text()

    assert models["muta-tutor-qwen3-1.7b-q4_0"]["sha256"] in winner_recipe
    assert '--set-name "Muta Tutor (Qwen3-1.7B)"' in winner_recipe
    assert models["bitcpm4-8b-tq2_0-envocab"]["sha256"] in bitcpm_recipe
