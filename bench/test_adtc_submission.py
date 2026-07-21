"""Tests for submission-directory synthesis.

Schema constraints these tests pin (adtc-profiler.schema.json, additionalProperties: false):
  - submission.test_prompts: exactly 2 items (minItems 2, maxItems 2)
  - submission.domain: must be one of the 7 enum values
  - submission.model.packaging: docker_image | docker_build_from_repo | binary_bundle
"""

from __future__ import annotations

import json

import pytest

from bench.adtc import submission


def _metadata() -> dict:
    return json.loads(submission.METADATA_PATH.read_text())


def test_checked_in_metadata_is_valid_json():
    assert isinstance(_metadata(), dict)


def test_domain_is_our_track():
    assert _metadata()["domain"] == "math_scientific_reasoning"


def test_exactly_two_test_prompts():
    # The schema is minItems 2 / maxItems 2 — three prompts is a Gate 1 validation failure.
    assert len(_metadata()["test_prompts"]) == 2


def test_metadata_has_every_schema_required_key():
    data = _metadata()
    for key in (
        "team_id",
        "domain",
        "language_scope",
        "african_alpha_claim",
        "budget_laptop_claim",
        "submitter",
        "cross_disciplinary_pairing",
        "test_prompts",
        "model",
    ):
        assert key in data, f"metadata.json is missing required key {key!r}"
    for key in ("name", "email", "github_handle"):
        assert key in data["submitter"]
    for key in ("discipline", "load_bearing", "description"):
        assert key in data["cross_disciplinary_pairing"]
    for key in ("name", "runtime", "quantization", "parameters_estimate", "packaging"):
        assert key in data["model"]
    assert data["model"]["packaging"] in {
        "docker_image",
        "docker_build_from_repo",
        "binary_bundle",
    }


@pytest.mark.parametrize(
    "count,expected",
    [
        (596_049_920, "597M"),
        (751_632_384, "752M"),
        (1_100_000_000, "1.1B"),
        (7_000_000_000, "7.0B"),
    ],
)
def test_parameter_estimate_rounds_up(count, expected):
    """Upstream fraud_check is one-sided: `actual <= claimed * 1.20`.

    Rounding UP guarantees claimed >= actual, so the check can never fail on our own
    derived string.
    """
    assert submission.format_parameter_estimate(count) == expected


def test_headerless_gguf_keeps_the_checked_in_claim():
    """Not every GGUF carries general.parameter_count — the Qwen3-0.6B build does not.

    A silent header must fall back to the real checked-in claim, not emit "unknown" into a
    competition artifact.
    """
    assert submission.format_parameter_estimate(None, fallback="0.6B") == "0.6B"
    assert submission.format_parameter_estimate(None) == "unknown"


def test_synthesize_keeps_the_claim_when_the_header_is_silent(tmp_path, monkeypatch):
    model = tmp_path / "fake.gguf"
    model.write_bytes(b"GGUF" + b"\x00" * 64)
    monkeypatch.setattr(submission, "read_gguf_metadata", lambda p: {"architecture": "qwen3"})
    dest = submission.synthesize(model, dest=tmp_path / "sub")
    written = json.loads((dest / "metadata.json").read_text())
    assert written["model"]["parameters_estimate"] == _metadata()["model"]["parameters_estimate"]


def test_parameter_estimate_never_understates():
    from_header = 596_049_920
    claimed = submission.format_parameter_estimate(from_header)
    parsed = float(claimed.rstrip("MB")) * (1e9 if claimed.endswith("B") else 1e6)
    assert parsed >= from_header


def test_synthesize_writes_runtime_block_and_links_model(tmp_path, monkeypatch):
    model = tmp_path / "fake.gguf"
    model.write_bytes(b"GGUF" + b"\x00" * 64)
    monkeypatch.setattr(submission, "read_gguf_metadata", lambda p: {"params_count": 596_049_920})

    dest = submission.synthesize(model, dest=tmp_path / "sub", docker_image="muta-dev:latest")

    written = json.loads((dest / "metadata.json").read_text())
    assert written["_runtime"]["model_path"] == "model.gguf"
    assert written["_runtime"]["docker_image"] == "muta-dev:latest"
    assert written["model"]["parameters_estimate"] == "597M"
    assert (dest / "model.gguf").read_bytes() == model.read_bytes()


def test_synthesize_is_idempotent(tmp_path, monkeypatch):
    model = tmp_path / "fake.gguf"
    model.write_bytes(b"GGUF" + b"\x00" * 64)
    monkeypatch.setattr(submission, "read_gguf_metadata", lambda p: {"params_count": 1})
    dest = tmp_path / "sub"
    submission.synthesize(model, dest=dest)
    submission.synthesize(model, dest=dest)  # must not raise on the existing model.gguf
    assert (dest / "model.gguf").exists()


def test_synthesize_rejects_a_missing_model(tmp_path):
    with pytest.raises(submission.SubmissionError):
        submission.synthesize(tmp_path / "nope.gguf", dest=tmp_path / "sub")


def test_test_prompts_helper_matches_the_file():
    assert submission.test_prompts() == _metadata()["test_prompts"]
