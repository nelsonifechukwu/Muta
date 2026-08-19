from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bench/build_gguf_candidates.sh"
MANIFEST = ROOT / "bench/measurements/campaign-20260819/manifest.json"


def test_candidate_recipe_and_manifest_share_all_input_pins():
    script = SCRIPT.read_text()
    manifest = json.loads(MANIFEST.read_text())

    assert manifest["source"]["sha256"] in script
    assert manifest["importance_matrix"]["sha256"] in script
    assert manifest["quantizer"]["llama_cpp_commit"] in script
    assert manifest["quantizer"]["binary_sha256"] in script
    assert 'sha256_file "$IMATRIX"' in script
