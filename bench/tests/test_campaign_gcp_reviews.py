"""Evidence validation does not supply semantic grades."""

import copy
import hashlib
import json

import pytest

from bench.campaign_gcp_reviews import GCP_BINARY, GCP_CONTEXT, GCP_SETTINGS, manual_gcp_judges
from bench.judges_prompt_report import grade as rubric_definition
from bench.judges_prompt_suite import prompts


def sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture(params=["items", "criteria"])
def review_fixture(tmp_path, request):
    campaign = tmp_path / "bench/measurements/campaign"
    raw = campaign / "raw/judges-responses.jsonl"
    raw.parent.mkdir(parents=True)
    manifest = campaign / "artifacts.csv"
    manifest.write_text("model,test_artifact,test_sha256\nTest,model.gguf," + "a" * 64 + "\n")
    rows, entries = [], []
    for i, prompt in enumerate(prompts(), 1):
        record = {
            "model": "model.gguf",
            "model_sha256": "a" * 64,
            **prompt.as_dict(),
            "hardware_context": GCP_CONTEXT,
            "server_sha256": GCP_BINARY,
            "settings": copy.deepcopy(GCP_SETTINGS),
            "answer": "Delivered answer.",
            "reasoning_content": "Private reasoning.",
            "finish_reason": "stop",
        }
        # One partial literal-think response and one reasoning-only response.
        if i == 9:
            record.update(answer="<think>Draft.</think>Partial final.", finish_reason="length")
        if i == 10:
            record.update(answer="", finish_reason="length")
        rows.append(record)
        criteria = [
            {
                "criterion": c["criterion"],
                "weight": c["weight"],
                "passed": False,
                "points" if request.param == "items" else "points_awarded": 0,
            }
            for c in rubric_definition(prompt.id, "")["items"]
        ]
        entry = {
            "id": prompt.id,
            "source": prompt.source,
            "source_line": i,
            "finish_reason": record["finish_reason"],
            "score": 0,
            "max_score": 10,
            request.param: criteria,
        }
        if request.param == "items":
            entry["final_status"] = (
                "finished" if i < 9 else "truncated_final_fragment" if i == 9 else "reasoning_only"
            )
        else:
            final = record["answer"].split("</think>")[-1].strip()
            entry["final_sha256"] = sha(final.encode())
            entry["final_output_status"] = (
                "finished" if i < 9 else "partial_final" if i == 9 else "absent"
            )
        entries.append(entry)
    payload = {
        "official_judge_score": False,
        "shared_execution": {
            "hardware_context": GCP_CONTEXT,
            "server_sha256": GCP_BINARY,
            "settings": copy.deepcopy(GCP_SETTINGS),
        },
        "source_snapshot": {"path": str(raw), "bytes": 0, "lines": 10, "sha256": ""},
        "models": [
            {
                "model": "model.gguf",
                "model_sha256": "a" * 64,
                "source_path": str(raw),
                "response_count": 10,
                "score": 0,
                "max_score": 100,
                "automated_score": 0,
                "human_score": 0,
                "finished_final_count": 8,
                "partial_final_count": 1,
                "any_final_text_count": 9,
                "truncated_response_count": 2,
                "reasoning_only_count": 1,
                "prompts": entries,
            }
        ],
    }
    review = campaign / "manual-judges-gcp/review.json"
    review.parent.mkdir()

    def save(rebind=False):
        if rebind:
            lines = [json.dumps(r).encode() for r in rows]
            blob = b"\n".join(lines) + b"\n"
            raw.write_bytes(blob)
            payload["source_snapshot"].update(bytes=len(blob), lines=len(rows), sha256=sha(blob))
            payload["models"][0]["source_sha256"] = sha(blob)
            for entry, record, line in zip(entries, rows, lines):
                entry.update(
                    record_sha256=sha(line),
                    answer_sha256=sha(record["answer"].encode()),
                    reasoning_sha256=sha(record["reasoning_content"].encode()),
                    prompt_sha256=sha(record["text"].encode()),
                )
        review.write_text(json.dumps(payload))

    save(rebind=True)
    return campaign, raw, review, payload, rows, save


def test_both_review_schemas_validate_without_regrading(review_fixture):
    campaign, _, review, _, _, _ = review_fixture
    result = manual_gcp_judges(campaign)["model.gguf"]
    assert (result["score"], result["finished"], result["truncated"]) == (0, 8, 2)
    assert result["source"] == review
    assert result["model_sha256"] == "a" * 64 and len(result["records"]) == 10


def test_prefix_append_is_accepted(review_fixture):
    campaign, raw, _, _, _, _ = review_fixture
    with raw.open("ab") as handle:
        handle.write(b'{"later": "unreviewed record"}\n')
    assert manual_gcp_judges(campaign)["model.gguf"]["score"] == 0


def test_changed_prefix_is_rejected(review_fixture):
    campaign, raw, _, _, _, _ = review_fixture
    raw.write_bytes(raw.read_bytes().replace(b"Delivered answer.", b"Altered answer!!", 1))
    with pytest.raises(ValueError, match="prefix changed"):
        manual_gcp_judges(campaign)


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_id",
        "duplicate_model",
        "wrong_sum",
        "decision",
        "weight",
        "label",
        "points",
        "line",
        "line_hash",
        "answer_hash",
        "prompt_hash",
        "model_hash",
        "finished",
        "truncated",
        "status",
        "source",
        "partial_count",
        "snapshot_lines",
    ],
)
def test_bad_reviews_fail_closed(review_fixture, mutation):
    campaign, _, _, payload, _, save = review_fixture
    model = payload["models"][0]
    entry = model["prompts"][0]
    criterion = entry.get("items", entry.get("criteria"))[0]
    if mutation == "duplicate_id":
        model["prompts"][1] = copy.deepcopy(entry)
    elif mutation == "duplicate_model":
        payload["models"].append(copy.deepcopy(model))
    elif mutation == "wrong_sum":
        model["score"] = 1
    elif mutation == "decision":
        criterion["passed"] = 0
    elif mutation in {"weight", "label"}:
        criterion["weight" if mutation == "weight" else "criterion"] = 100
    elif mutation == "points":
        criterion["points" if "points" in criterion else "points_awarded"] = 1
    elif mutation == "line":
        entry["source_line"] = 2
    elif mutation in {"line_hash", "answer_hash", "prompt_hash"}:
        entry[
            {
                "line_hash": "record_sha256",
                "answer_hash": "answer_sha256",
                "prompt_hash": "prompt_sha256",
            }[mutation]
        ] = "bad"
    elif mutation == "model_hash":
        model["model_sha256"] = "b" * 64
    elif mutation in {"finished", "truncated"}:
        model["finished_final_count" if mutation == "finished" else "truncated_response_count"] = 0
    elif mutation == "status":
        entry["final_status" if "final_status" in entry else "final_output_status"] = "absent"
    elif mutation == "source":
        payload["source_snapshot"]["path"] = str(campaign / "mac-accuracy/responses.jsonl")
    elif mutation == "partial_count":
        model["partial_final_count"] = 0
    elif mutation == "snapshot_lines":
        payload["source_snapshot"]["lines"] = 9
    save()
    with pytest.raises(ValueError):
        manual_gcp_judges(campaign)


@pytest.mark.parametrize(
    "field,value",
    [
        ("hardware_context", "apple_m4_pro_24gib_macos_metal_b10175"),
        ("server_sha256", "b" * 64),
        ("model_sha256", "b" * 64),
        ("settings", {**GCP_SETTINGS, "gpu_layers": 99}),
        ("text", "Changed prompt"),
        ("model", "other.gguf"),
        ("id", "automated_01"),
    ],
)
def test_rebound_wrong_raw_provenance_is_rejected(review_fixture, field, value):
    campaign, _, _, _, rows, save = review_fixture
    rows[1][field] = value
    save(rebind=True)
    with pytest.raises(ValueError):
        manual_gcp_judges(campaign)


def test_reasoning_cannot_receive_final_answer_points(review_fixture):
    campaign, _, _, payload, _, save = review_fixture
    model = payload["models"][0]
    entry = model["prompts"][-1]
    criterion = entry.get("items", entry.get("criteria"))[0]
    criterion["passed"] = True
    criterion["points" if "points" in criterion else "points_awarded"] = criterion["weight"]
    entry["score"] = model["score"] = model["human_score"] = criterion["weight"]
    save()
    with pytest.raises(ValueError, match="reasoning-only"):
        manual_gcp_judges(campaign)


def test_no_manual_reviews_returns_empty(tmp_path):
    assert manual_gcp_judges(tmp_path) == {}


def test_scalar_transcript_preserves_snapshot_and_does_not_edit_source(review_fixture):
    from bench.campaign_transcripts import scalar_transcript

    campaign, raw, _, _, _, _ = review_fixture
    review = manual_gcp_judges(campaign)["model.gguf"]
    original = raw.read_bytes()
    output = campaign / "transcripts/model.md"
    artifact = {
        "model": "Test",
        "test_artifact": "model.gguf",
        "test_sha256": "a" * 64,
        "quantization": "Q4_0",
    }
    manifest = scalar_transcript(output, artifact, review)
    written = output.read_text()
    assert raw.read_bytes() == original
    assert written.count("### Prompt") == 10
    assert written.count("### Local assessment") == 10
    assert "GCP scalar" in written and "not official panel" in written
    assert manifest["source_prefix_sha256"] == sha(original)
    for record in review["raw_records"].values():
        for field in ("text", "answer", "reasoning_content"):
            assert record[field] in written


@pytest.mark.parametrize("mutation", ["model", "context", "answer", "reasoning", "coverage", "sum"])
def test_scalar_transcript_rejects_mismatched_review_snapshots(review_fixture, mutation):
    from bench.campaign_transcripts import scalar_transcript

    campaign, _, _, _, _, _ = review_fixture
    review = manual_gcp_judges(campaign)["model.gguf"]
    artifact = {
        "model": "Test",
        "test_artifact": "model.gguf",
        "test_sha256": "a" * 64,
        "quantization": "Q4_0",
    }
    first = review["raw_records"][prompts()[0].id]
    if mutation == "model":
        artifact["test_sha256"] = "b" * 64
    elif mutation == "context":
        first["hardware_context"] = "Mac"
    elif mutation == "answer":
        first["answer"] = "Edited answer"
    elif mutation == "reasoning":
        first["reasoning_content"] = "Edited reasoning"
    elif mutation == "coverage":
        review["raw_records"].pop(prompts()[0].id)
    elif mutation == "sum":
        review["score"] += 1
    with pytest.raises(ValueError):
        scalar_transcript(campaign / "out.md", artifact, review)
