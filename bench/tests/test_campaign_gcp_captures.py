"""Ungraded scalar captures must not invent completion, provenance or grades."""

import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from bench.campaign_gcp_captures import load_gcp_captures, render_gcp_capture
from bench.campaign_gcp_reviews import GCP_BINARY, GCP_CONTEXT, GCP_SETTINGS
from bench.campaign_transcripts import build_gcp
from bench.judges_prompt_report import grade as rubric_definition
from bench.judges_prompt_suite import prompts


@pytest.fixture
def fixture(tmp_path):
    campaign = tmp_path / "campaign"
    raw = campaign / "raw"
    raw.mkdir(parents=True)
    (campaign / "artifacts.csv").write_text(
        "model,test_artifact,test_sha256\nTest,model.gguf,"
        + "a" * 64
        + "\nWaiting,waiting.gguf,"
        + "b" * 64
        + "\n"
    )
    identity = {
        "model": "model.gguf",
        "model_sha256": "a" * 64,
        "hardware_context": GCP_CONTEXT,
        "server_sha256": GCP_BINARY,
        "settings": copy.deepcopy(GCP_SETTINGS),
    }
    rows = [
        {
            **copy.deepcopy(identity),
            **p.as_dict(),
            "ts": f"2026-09-14T18:00:{i:02d}+00:00",
            "answer": "Final answer.",
            "reasoning_content": "Separate reasoning.",
            "finish_reason": "stop",
            "usage": {"completion_tokens": 10, "prompt_tokens": 20, "total_tokens": 30},
            "wall_s": 1.5,
        }
        for i, p in enumerate(prompts(), 1)
    ]
    events = [{**identity, "event": "model_start", "ts": "2026-09-14T18:00:00+00:00"}]
    events[0]["command"] = [
        "/remote/bin/llama-server",
        "--model",
        "/remote/models/model.gguf",
        "--host",
        "127.0.0.1",
        "--port",
        "18081",
        "--ctx-size",
        "4096",
        "--threads",
        "2",
        "--n-gpu-layers",
        "0",
        "--cache-ram",
        "256",
        "--jinja",
    ]
    response_path = raw / "judges-responses.jsonl"
    event_path = raw / "judges-events.jsonl"

    def save(count=3):
        response_path.write_bytes(b"".join(json.dumps(r).encode() + b"\n" for r in rows[:count]))
        event_path.write_bytes(b"".join(json.dumps(e).encode() + b"\n" for e in events))

    save()
    return campaign, rows, events, save, response_path, event_path


def stop_event():
    return {
        "model": "model.gguf",
        "hardware_context": GCP_CONTEXT,
        "event": "model_stop",
        "ts": "2026-09-14T18:00:11+00:00",
    }


def test_partial_and_not_started_have_all_prompts_without_grades(fixture):
    campaign, _, _, _, _, _ = fixture
    batch = load_gcp_captures(campaign)
    capture = batch.by_model["model.gguf"]
    assert capture.summary["status"] == "partial"
    assert capture.summary["response_count"] == 3
    assert len(capture.summary["missing_ids"]) == 7
    assert batch.by_model["waiting.gguf"].summary["status"] == "not_started"
    text = render_gcp_capture(capture)
    assert sum(f"## {p.id}:" in text for p in prompts()) == 10
    assert text.count("**Missing response:**") == 7
    assert "no score, rank or correctness assessment" in text
    assert "Local rubric:" not in text and "/100" not in text
    assert all("score" not in key and "rank" not in key for key in capture.summary)


def test_complete_unreviewed_requires_stop_event(fixture):
    campaign, rows, events, save, _, _ = fixture
    rows[-1].update(answer="", finish_reason="length")
    rows[-1]["usage"].update(completion_tokens=1024, total_tokens=1044)
    save(10)
    assert (
        load_gcp_captures(campaign).by_model["model.gguf"].summary["status"]
        == "awaiting_stop_event"
    )
    events.append(stop_event())
    save(10)
    capture = load_gcp_captures(campaign).by_model["model.gguf"]
    assert capture.summary["status"] == "complete_unreviewed"
    assert capture.summary["response_count"] == 10
    assert capture.summary["finished_final_count"] == 9
    assert capture.summary["truncated_response_count"] == 1
    text = render_gcp_capture(capture)
    assert "Final-text delivery: absent" in text and "**Missing response:**" not in text


def test_literal_think_and_substantive_partial_are_preserved(fixture):
    campaign, rows, _, save, _, _ = fixture
    rows[0].update(answer="<think>Draft only", finish_reason="length")
    rows[1].update(answer="<think>Draft.</think>Partial result.", finish_reason="length")
    save()
    text = render_gcp_capture(load_gcp_captures(campaign).by_model["model.gguf"])
    assert "<think>Draft only" in text and "<think>Draft.</think>Partial result." in text
    assert "Final-text delivery: absent" in text and "Final-text delivery: partial" in text
    assert "Local assessment" not in text


def test_scalar_failure_verbatim_not_inferred_from_other_host(fixture):
    campaign, _, events, save, _, event_path = fixture
    error = "HTTP 500\n```\n<script>alert('x')</script>\n# invented rank"
    events.append({**stop_event(), "event": "model_failure", "error": error})
    events.append(stop_event())
    save()
    batch = load_gcp_captures(campaign)
    capture = batch.by_model["model.gguf"]
    assert capture.summary["status"] == "failed" and capture.summary["response_count"] == 3
    text = render_gcp_capture(capture)
    raw_failure = event_path.read_bytes().splitlines()[1].decode()
    assert raw_failure in text
    # A Mac failure file must not affect the waiting scalar model.
    (campaign / "mac-failure.json").write_text(
        json.dumps({"model": "waiting.gguf", "error": error})
    )
    assert load_gcp_captures(campaign).by_model["waiting.gguf"].summary["status"] == "not_started"


def test_stop_without_all_responses_is_explicit(fixture):
    campaign, _, events, save, _, _ = fixture
    events.append(stop_event())
    save(2)
    summary = load_gcp_captures(campaign).by_model["model.gguf"].summary
    assert summary["status"] == "stopped_incomplete"
    assert not summary["failure_recorded"]


def test_missing_files_and_event_lag_do_not_claim_complete(fixture):
    campaign, _, _, save, response_path, event_path = fixture
    response_path.unlink()
    event_path.unlink()
    batch = load_gcp_captures(campaign)
    assert all(c.summary["status"] == "not_started" for c in batch.models)
    assert not batch.responses.metadata["exists"]
    save(10)
    event_path.unlink()
    assert (
        load_gcp_captures(campaign).by_model["model.gguf"].summary["status"]
        == "awaiting_start_event"
    )
    save(0)
    assert (
        load_gcp_captures(campaign).by_model["model.gguf"].summary["status"]
        == "started_no_responses"
    )


def test_uncommitted_tail_is_reported_not_parsed(fixture):
    campaign, _, _, _, response_path, event_path = fixture
    with response_path.open("ab") as f:
        f.write(b'{"model": "unfinished')
    with event_path.open("ab") as f:
        f.write(b'{"event":')
    batch = load_gcp_captures(campaign)
    assert batch.by_model["model.gguf"].summary["response_count"] == 3
    assert batch.responses.metadata["uncommitted_tail_bytes"] > 0
    assert batch.events.metadata["uncommitted_tail_bytes"] > 0
    with response_path.open("ab") as f:
        f.write(b"\n")
    with pytest.raises(ValueError):
        load_gcp_captures(campaign)


@pytest.mark.parametrize(
    "mutation",
    [
        "context",
        "server",
        "model_hash",
        "settings",
        "boolean_setting",
        "duplicate_id",
        "unknown_id",
        "prompt",
        "source",
        "title",
        "answer",
        "reasoning",
        "finish",
        "usage",
        "negative_time",
        "timestamp",
        "unknown_model",
        "token_total",
        "token_cap",
        "duplicate_start",
        "stop_without_start",
        "failure_without_start",
        "failure_after_stop",
        "event_context",
        "start_hash",
        "start_settings",
        "start_server",
        "event_type",
        "response_after_stop",
        "response_before_start",
        "failure_error",
        "missing_command",
        "wrong_command",
        "wrong_command_model",
    ],
)
def test_invalid_records_and_lifecycles_fail_closed(fixture, mutation):
    campaign, rows, events, save, _, _ = fixture
    row = rows[0]
    if mutation == "context":
        row["hardware_context"] = "Mac"
    elif mutation == "server":
        row["server_sha256"] = "f" * 64
    elif mutation == "model_hash":
        row["model_sha256"] = "f" * 64
    elif mutation == "settings":
        row["settings"]["gpu_layers"] = 99
    elif mutation == "boolean_setting":
        row["settings"]["embedded_chat_template"] = 1
    elif mutation == "duplicate_id":
        rows[1] = copy.deepcopy(row)
    elif mutation == "unknown_id":
        row["id"] = "unknown"
    elif mutation == "prompt":
        row["text"] += "Changed"
    elif mutation in {"source", "title"}:
        row[mutation] = "Changed"
    elif mutation in {"answer", "reasoning"}:
        row["reasoning_content" if mutation == "reasoning" else "answer"] = None
    elif mutation == "finish":
        row["finish_reason"] = "error"
    elif mutation == "usage":
        row["usage"]["completion_tokens"] = True
    elif mutation == "negative_time":
        row["wall_s"] = -1
    elif mutation == "timestamp":
        row["ts"] = "2026-09-14T18:00:01"
    elif mutation == "unknown_model":
        row["model"] = "not-in-manifest.gguf"
    elif mutation == "token_total":
        row["usage"]["total_tokens"] = 99
    elif mutation == "token_cap":
        row["usage"].update(completion_tokens=2048, total_tokens=2068)
    elif mutation == "duplicate_start":
        events.append(copy.deepcopy(events[0]))
    elif mutation == "stop_without_start":
        events[:] = [stop_event()]
    elif mutation == "failure_without_start":
        events[:] = [{**stop_event(), "event": "model_failure", "error": "Failure"}]
    elif mutation == "failure_after_stop":
        events += [stop_event(), {**stop_event(), "event": "model_failure", "error": "Failure"}]
    elif mutation == "event_context":
        events[0]["hardware_context"] = "Mac"
    elif mutation == "start_hash":
        events[0]["model_sha256"] = "f" * 64
    elif mutation == "start_settings":
        events[0]["settings"]["threads"] = 4
    elif mutation == "start_server":
        events[0]["server_sha256"] = "f" * 64
    elif mutation == "event_type":
        events.append({**stop_event(), "event": "success"})
    elif mutation == "response_after_stop":
        events.append({**stop_event(), "ts": rows[0]["ts"]})
    elif mutation == "response_before_start":
        events[0]["ts"] = rows[1]["ts"]
    elif mutation == "failure_error":
        events.append({**stop_event(), "event": "model_failure", "error": None})
    elif mutation == "missing_command":
        del events[0]["command"]
    elif mutation == "wrong_command":
        events[0]["command"][10] = "4"
    elif mutation == "wrong_command_model":
        events[0]["command"][2] = "/remote/models/waiting.gguf"
    save()
    with pytest.raises((ValueError, TypeError)):
        load_gcp_captures(campaign)


def test_manifest_duplicates_and_traversal_fail(fixture):
    campaign, _, _, _, _, _ = fixture
    path = campaign / "artifacts.csv"
    original = path.read_text()
    path.write_text(original + "Duplicate,model.gguf," + "a" * 64 + "\n")
    with pytest.raises(ValueError, match="duplicate capture artifact"):
        load_gcp_captures(campaign)
    path.write_text(original.replace("waiting.gguf", "../escape.gguf"))
    with pytest.raises(ValueError, match="filename"):
        load_gcp_captures(campaign)
    path.write_text(original.replace("waiting.gguf", ".."))
    with pytest.raises(ValueError, match="filename"):
        load_gcp_captures(campaign)


def test_overlapping_model_events_are_rejected(fixture):
    campaign, _, events, save, _, _ = fixture
    second = copy.deepcopy(events[0])
    second.update(model="waiting.gguf", model_sha256="b" * 64)
    second["command"][2] = "/remote/models/waiting.gguf"
    events.append(second)
    save()
    with pytest.raises(ValueError, match="overlapping"):
        load_gcp_captures(campaign)


def test_single_reads_immutable_snapshot_and_inert_markdown(fixture, monkeypatch):
    campaign, rows, _, save, response_path, event_path = fixture
    injection = "```\n# forged score\n<script>evil()</script>\n``````\n[link](bad)\n"
    rows[0].update(answer=injection, reasoning_content=injection + "reasoning")
    save()
    original_read = Path.read_bytes
    calls = []

    def read(path):
        calls.append(path)
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", read)
    batch = load_gcp_captures(campaign)
    assert calls.count(response_path.resolve()) == calls.count(event_path.resolve()) == 1
    capture = batch.by_model["model.gguf"]
    original_hash = hashlib.sha256(response_path.read_bytes()).hexdigest()
    response_path.write_text("changed after snapshot\n")
    monkeypatch.setattr(Path, "read_bytes", lambda _: pytest.fail("renderer reread the filesystem"))
    text = render_gcp_capture(capture)
    assert "```````text\n" + injection + "\n```````" in text
    assert batch.responses.metadata["snapshot_sha256"] == original_hash
    assert "changed after snapshot" not in text
    # A caller cannot omit a captured response or alter its bytes before rendering.
    with pytest.raises(ValueError, match="selected records"):
        render_gcp_capture(replace(capture, responses=capture.responses[1:]))
    altered = replace(
        capture.responses[0], raw=capture.responses[0].raw.replace(b"forged", b"altered")
    )
    with pytest.raises(ValueError, match="selected records"):
        render_gcp_capture(replace(capture, responses=(altered, *capture.responses[1:])))


@pytest.fixture
def archive_fixture(fixture):
    campaign, *_ = fixture
    (campaign / "artifacts.csv").write_text(
        "model,quantization,runtime_gate,test_artifact,test_sha256\n"
        + "Test,Q4_0,pass,model.gguf,"
        + "a" * 64
        + "\n"
        + "Waiting,Q4_K_M,pass,waiting.gguf,"
        + "b" * 64
        + "\n"
        + "Spark,Q4_0,fail,spark.gguf,"
        + "c" * 64
        + "\n"
    )
    return fixture


def write_zero_review(campaign, response_path):
    """Supply genuine source-bound manual input; the archive must not grade it."""
    blob = response_path.read_bytes()
    entries = []
    for number, line in enumerate(blob.splitlines(), 1):
        row = json.loads(line)
        entries.append(
            {
                "id": row["id"],
                "source_line": number,
                "record_sha256": hashlib.sha256(line).hexdigest(),
                "answer_sha256": hashlib.sha256(row["answer"].encode()).hexdigest(),
                "reasoning_sha256": hashlib.sha256(row["reasoning_content"].encode()).hexdigest(),
                "prompt_sha256": hashlib.sha256(row["text"].encode()).hexdigest(),
                "finish_reason": row["finish_reason"],
                "score": 0,
                "max_score": 10,
                "items": [
                    {"criterion": item["criterion"], "weight": item["weight"], "passed": False}
                    for item in rubric_definition(row["id"], "")["items"]
                ],
            }
        )
    review = {
        "official_judge_score": False,
        "source_snapshot": {
            "path": str(response_path),
            "sha256": hashlib.sha256(blob).hexdigest(),
            "bytes": len(blob),
            "lines": len(entries),
        },
        "models": [
            {
                "model": "model.gguf",
                "model_sha256": "a" * 64,
                "response_count": 10,
                "finished_final_count": 10,
                "truncated_response_count": 0,
                "any_final_text_count": 10,
                "reasoning_only_count": 0,
                "automated_score": 0,
                "human_score": 0,
                "score": 0,
                "max_score": 100,
                "prompts": entries,
            }
        ],
    }
    path = campaign / "manual-judges-gcp/review.json"
    path.parent.mkdir()
    path.write_text(json.dumps(review))


@pytest.mark.parametrize("state", ["partial", "failed", "not_started", "complete_unreviewed"])
def test_build_gcp_capture_pages_never_become_grades(archive_fixture, state):
    campaign, rows, events, save, response_path, event_path = archive_fixture
    count = 3
    rows[0]["answer"] = "```\n# Fabricated rank 1\n<script>bad()</script>\n```"
    if state == "failed":
        events += [{**stop_event(), "event": "model_failure", "error": "HTTP 500"}, stop_event()]
    elif state == "not_started":
        count = 0
        events.clear()
    elif state == "complete_unreviewed":
        count = 10
        events.append(stop_event())
    save(count)
    source_before = (response_path.read_bytes(), event_path.read_bytes())
    result = build_gcp(campaign)
    assert source_before == (response_path.read_bytes(), event_path.read_bytes())
    entries = {entry["model"]: entry for entry in result["files"]}
    assert set(entries) == {"model.gguf", "waiting.gguf"}
    assert entries["model.gguf"]["status"] == state
    assert entries["model.gguf"]["response_count"] == count
    assert entries["waiting.gguf"]["status"] == "not_started"
    for name, captured in [("model.gguf", count), ("waiting.gguf", 0)]:
        entry = entries[name]
        assert entry["score"] is entry["rank"] is entry["review"] is None
        output = Path(entry["output"])
        text = output.read_text()
        assert text.count("### Prompt") == 10
        assert text.count("**Missing response:**") == 10 - captured
        assert "Local assessment:" not in text and "Local rubric:" not in text
        assert hashlib.sha256(output.read_bytes()).hexdigest() == entry["output_sha256"]
    if count:
        assert (
            "````text\n" + rows[0]["answer"] + "\n````"
            in Path(entries["model.gguf"]["output"]).read_text()
        )
    if state == "failed":
        assert (
            event_path.read_bytes().splitlines()[1].decode()
            in Path(entries["model.gguf"]["output"]).read_text()
        )
    index = Path(result["index"]).read_text()
    assert "0 models have complete, source-checked local assessments" in index
    assert "Spark" not in index
    assert not (campaign / "transcripts/gcp-scalar/spark.gguf").exists()
    assert "| 1 |" not in index
    assert json.loads((campaign / "gcp-transcript-manifest.json").read_text()) == result


def test_build_gcp_keeps_real_review_separate_from_missing_score(archive_fixture):
    campaign, _, events, save, response_path, _ = archive_fixture
    events.append(stop_event())
    save(10)
    write_zero_review(campaign, response_path)
    result = build_gcp(campaign)
    entries = {entry["model"]: entry for entry in result["files"]}
    assert entries["model.gguf"]["review"] is not None
    assert entries["waiting.gguf"]["score"] is entries["waiting.gguf"]["rank"] is None
    graded_text = Path(entries["model.gguf"]["output"]).read_text()
    assert graded_text.count("### Local assessment: 0/10") == 10
    index = Path(result["index"]).read_text()
    assert "1 models have complete, source-checked local assessments" in index
    assert "| 1 | Test · Q4_0 | 0 | 10/10 |" in index
    assert "| Waiting · Q4_K_M | not started | 0/10 |" in index
    assert "Spark" not in index


def test_build_gcp_rejects_changed_prefix_between_review_and_capture(archive_fixture, monkeypatch):
    campaign, rows, events, save, response_path, _ = archive_fixture
    events.append(stop_event())
    save(10)
    write_zero_review(campaign, response_path)

    def changed_snapshot(path):
        rows[0]["answer"] = "Changed after the manual loader read its prefix."
        save(10)
        return load_gcp_captures(path)

    monkeypatch.setattr("bench.campaign_transcripts.load_gcp_captures", changed_snapshot)
    with pytest.raises(ValueError, match="source snapshots differ"):
        build_gcp(campaign)
    assert not (campaign / "gcp-judges-responses.md").exists()


def test_build_gcp_review_requires_complete_captured_lifecycle(archive_fixture):
    campaign, _, _, save, response_path, _ = archive_fixture
    save(10)
    write_zero_review(campaign, response_path)
    with pytest.raises(ValueError, match="complete captured lifecycle"):
        build_gcp(campaign)


def test_build_gcp_rejects_unknown_raw_model_before_publishing(archive_fixture):
    campaign, rows, _, save, _, _ = archive_fixture
    rows[0]["model"] = "unknown.gguf"
    save()
    with pytest.raises(ValueError, match="manifest"):
        build_gcp(campaign)
    assert not (campaign / "gcp-judges-responses.md").exists()
