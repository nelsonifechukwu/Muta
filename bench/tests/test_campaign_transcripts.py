import copy

import pytest

from bench.campaign_transcripts import (
    MAC_BINARY,
    MAC_CONTEXT,
    expected_settings,
    literal,
    manual_stem,
    read_snapshot,
    transcript,
    validate_records,
)
from bench.judges_prompt_suite import prompts as judge_prompts
from bench.stem_prompt_suite import prompts as stem_prompts

ARTIFACT = {
    "test_artifact": "model.gguf",
    "test_sha256": "a" * 64,
    "model": "Test model",
    "quantization": "Q4_0",
}


def row(prompt):
    return {
        "model": "model.gguf",
        "model_sha256": "a" * 64,
        "id": prompt.id,
        "text": prompt.text,
        "hardware_context": MAC_CONTEXT,
        "server_sha256": MAC_BINARY,
        "settings": expected_settings("judges"),
        "answer": "",
        "finish_reason": "length",
    }


def config(stage):
    return {
        "model": "model.gguf",
        "model_sha256": "a" * 64,
        "hardware_context": MAC_CONTEXT,
        "server_sha256": MAC_BINARY,
        "settings": expected_settings(stage),
    }


def test_empty_capture_is_not_a_zero_grade():
    assert validate_records([], ARTIFACT, "stem", config("stem")) == {}


def test_exact_prompt_hash_and_context():
    sample = row(stem_prompts()[0])
    assert validate_records([sample], ARTIFACT, "stem", config("stem"))[sample["id"]] == sample
    for field, value in [
        ("model_sha256", "wrong"),
        ("model", "other.gguf"),
        ("text", "different prompt"),
        ("hardware_context", None),
        ("answer", None),
    ]:
        altered = {**sample, field: value}
        with pytest.raises((ValueError, TypeError)):
            validate_records([altered], ARTIFACT, "stem", config("stem"))


def test_duplicate_and_mixed_execution_are_rejected():
    first, second = map(row, judge_prompts()[:2])
    with pytest.raises(ValueError, match="duplicate"):
        validate_records([first, first], ARTIFACT, "judges", config("judges"))
    for field, value in [
        ("hardware_context", "gcp"),
        ("server_sha256", "c" * 64),
        ("settings", {"seed": 1}),
    ]:
        with pytest.raises(ValueError):
            validate_records(
                [first, {**second, field: value}], ARTIFACT, "judges", config("judges")
            )


def test_literal_preserves_nested_fences_without_active_html():
    value = "```\n<script>alert(1)</script>\n````"
    output = literal(value)
    assert output == "`````text\n" + value + "\n`````"


def test_transcript_preserves_answer_reasoning_and_missing_prompts(tmp_path):
    sample = row(judge_prompts()[0])
    sample.update(answer="```\noriginal answer\n```", reasoning_content="unfinished thought")
    source = tmp_path / "responses.jsonl"
    source.write_text("raw immutable source\n")
    output = tmp_path / "judges.md"
    entry = transcript(
        output, source, ARTIFACT, "judges", [sample], [], config("judges"), "snapshot"
    )
    text = output.read_text()
    assert sample["answer"] in text and sample["reasoning_content"] in text
    assert entry["captured"] == 1 and entry["expected"] == 10
    assert text.count("No response captured.") == 9
    assert text.count("### Prompt") == 10
    assert "Provisional assessment" not in text


def test_grade_must_match_model(tmp_path):
    grade = {"model_sha256": "wrong"}
    with pytest.raises(ValueError, match="grade/model"):
        transcript(
            tmp_path / "output.md",
            tmp_path / "raw.jsonl",
            ARTIFACT,
            "judges",
            [],
            [],
            config("judges"),
            None,
            grade,
        )


def test_validation_does_not_mutate_records():
    samples = [row(p) for p in judge_prompts()]
    original = copy.deepcopy(samples)
    validate_records(samples, ARTIFACT, "judges", config("judges"))
    assert samples == original


def test_gcp_in_mac_directory_is_rejected_even_with_consistent_rows():
    sample = row(stem_prompts()[0])
    with pytest.raises(ValueError, match="pinned Mac"):
        validate_records(
            [{**sample, "hardware_context": "gcp"}],
            ARTIFACT,
            "stem",
            {**config("stem"), "hardware_context": "gcp"},
        )


def test_changed_context_size_or_cache_fails():
    for key, value in [("context_size", 8192), ("cache_ram_mib", 8192)]:
        cfg = config("stem")
        cfg["settings"][key] = value
        with pytest.raises(ValueError, match="settings"):
            validate_records([], ARTIFACT, "stem", cfg)


def test_stale_grade_or_partial_source_is_rejected(tmp_path):
    for samples, source_digest in [
        ([row(p) for p in judge_prompts()], "changed"),
        ([row(judge_prompts()[0])], "same"),
    ]:
        grade = {"model_sha256": "a" * 64, "response_sha256": "same"}
        with pytest.raises(ValueError, match="grade/source"):
            transcript(
                tmp_path / "out.md",
                tmp_path / "raw.jsonl",
                ARTIFACT,
                "judges",
                samples,
                [],
                config("judges"),
                source_digest,
                grade,
            )


def test_snapshot_hash_corresponds_to_parsed_bytes(tmp_path):
    import hashlib
    import json

    path = tmp_path / "raw.jsonl"
    data = (json.dumps(row(stem_prompts()[0])) + "\n").encode()
    path.write_bytes(data)
    rows, fingerprint = read_snapshot(path)
    assert rows == [row(stem_prompts()[0])]
    assert fingerprint == hashlib.sha256(data).hexdigest()


@pytest.fixture
def stem_review_fixture(tmp_path, monkeypatch):
    import hashlib
    import json

    campaign = tmp_path / "campaign"
    directory = campaign / "mac-accuracy/model.gguf/stem"
    directory.mkdir(parents=True)
    samples = []
    entries = []
    totals = {}
    for i, prompt in enumerate(stem_prompts(), 1):
        sample = row(prompt)
        sample.update(
            subject=prompt.subject,
            format=prompt.format,
            expected=prompt.expected,
            generated_tokens=1,
            finish_reason="eos",
        )
        samples.append(sample)
        entries.append(
            {
                "id": prompt.id,
                "subject": prompt.subject,
                "format": prompt.format,
                "expected": prompt.expected,
                "generated_tokens": 1,
                "finish_reason": "eos",
                "source_line": i,
                "response_sha256": hashlib.sha256(b"").hexdigest(),
                "strict_pass": False,
                "core_answer_correct": False,
                "reason": "Empty answer.",
            }
        )
        key = f"{prompt.subject}_{prompt.format}"
        subtotal = totals.setdefault(key, {"strict_pass": 0, "core_correct": 0, "total": 0})
        subtotal["total"] += 1
    totals["overall"] = {"strict_pass": 0, "core_correct": 0, "total": 100}
    source = directory / "responses.jsonl"
    source.write_text("\n".join(json.dumps(s) for s in samples) + "\n")
    (directory / "config.json").write_text(json.dumps(config("stem")))
    payload = {
        "model": "model.gguf",
        "model_sha256": "a" * 64,
        "source": {"path": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest()},
        "results": entries,
        "totals": totals,
    }
    review = campaign / "manual-stem-mac/review.json"
    review.parent.mkdir()
    review.write_text(json.dumps(payload))
    monkeypatch.setattr("bench.campaign_transcripts.load_artifacts", lambda _: ({}, [ARTIFACT]))
    return campaign, review, payload


def test_manual_stem_complete_source_bound_grades(stem_review_fixture):
    campaign, _, _ = stem_review_fixture
    checked = manual_stem(campaign)["model.gguf"]
    assert checked["totals"]["overall"] == {"strict_pass": 0, "core_correct": 0, "total": 100}
    assert len(checked["records"]) == 100


@pytest.mark.parametrize(
    "mutation", ["source", "hash", "decision", "sum", "duplicate", "answer", "line"]
)
def test_manual_stem_rejects_misattribution_and_bad_decisions(stem_review_fixture, mutation):
    import json

    campaign, review, payload = stem_review_fixture
    if mutation == "source":
        payload["source"]["path"] = str(campaign / "raw/gcp.jsonl")
    elif mutation == "hash":
        payload["source"]["sha256"] = "changed"
    elif mutation == "decision":
        payload["results"][0]["strict_pass"] = 0
    elif mutation == "sum":
        payload["totals"]["overall"]["strict_pass"] = 1
    elif mutation == "duplicate":
        payload["results"][1] = payload["results"][0]
    elif mutation == "answer":
        payload["results"][0]["response_sha256"] = "changed"
    elif mutation == "line":
        payload["results"][0]["source_line"] = 2
    review.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        manual_stem(campaign)
