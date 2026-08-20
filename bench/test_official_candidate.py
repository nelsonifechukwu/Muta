import json
from pathlib import Path

from bench.official_candidate import _candidate_metadata


def test_candidate_metadata_changes_only_candidate_fields(tmp_path: Path) -> None:
    path = tmp_path / "metadata.json"
    original = {
        "team_id": "muta",
        "test_prompts": [{"prompt_id": "a"}, {"prompt_id": "b"}],
        "model": {
            "name": "old",
            "quantization": "old-quant",
            "parameters_estimate": "753M",
            "runtime": "llama.cpp",
            "packaging": "old-package",
        },
    }
    path.write_text(json.dumps(original))

    _candidate_metadata(tmp_path, name="new", quantization="Q4_0", packaging="campaign")

    updated = json.loads(path.read_text())
    assert updated["model"] == {
        "name": "new",
        "quantization": "Q4_0",
        "parameters_estimate": "753M",
        "runtime": "llama.cpp",
        "packaging": "campaign",
    }
    assert updated["team_id"] == original["team_id"]
    assert updated["test_prompts"] == original["test_prompts"]
