from pathlib import Path

from bench.live_prompt_battery import PROMPTS, sha256


def test_prompt_battery_covers_math_misconception_science_and_proof():
    assert [row["id"] for row in PROMPTS] == [
        "crate_profit",
        "fraction_misconception",
        "thermal_energy",
        "sqrt2_proof",
    ]


def test_sha256_streams_exact_file(tmp_path: Path):
    artifact = tmp_path / "artifact.gguf"
    artifact.write_bytes(b"exact-artifact")
    assert sha256(artifact) == "db87ed0995316ec06aed48290fc26603fe5f6c37a07df257848fe38ef8642cae"
