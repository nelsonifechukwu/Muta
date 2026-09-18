from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

import bench.round2_candidate_eval as candidate_eval
from bench.judges_prompt_report import evaluate, load_names, read_jsonl
from bench.round2_candidate_eval import (
    EvaluationInputError,
    GenerationResult,
    file_identity,
    load_candidate_manifest,
    run_campaign,
    select_prompts,
    tree_identity,
    verify_candidate,
)


class FakeBackend:
    def __init__(self, candidate: dict, *_args, **_kwargs) -> None:
        self.candidate = candidate

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def generate(self, prompt, *, max_new_tokens):
        answer = f"{self.candidate['id']} exact answer for {prompt.id}"
        raw = f"RAW::{self.candidate['id']}::{prompt.id}::{answer}".encode()
        return GenerationResult(
            answer=answer,
            reasoning_content="",
            finish_reason="stop",
            generated_tokens=7,
            raw_bytes=raw,
            raw_media_type="application/octet-stream; source=test",
            backend_details={"generation": {"max_new_tokens": max_new_tokens}},
        )


class FirstCandidateFails(FakeBackend):
    def __enter__(self):
        if self.candidate["id"] == "candidate-0":
            raise RuntimeError("injected load failure")
        return self


class InvalidGenerationResult(FakeBackend):
    def generate(self, prompt, *, max_new_tokens):
        result = super().generate(prompt, max_new_tokens=max_new_tokens)
        return GenerationResult(
            answer=None,
            reasoning_content=result.reasoning_content,
            finish_reason=result.finish_reason,
            generated_tokens=result.generated_tokens,
            raw_bytes=result.raw_bytes,
            raw_media_type=result.raw_media_type,
            backend_details=result.backend_details,
        )


def _gguf_manifest(tmp_path: Path, *, count: int = 2) -> Path:
    server = tmp_path / "llama-server"
    server.write_bytes(b"exact-server")
    candidates = []
    for index in range(count):
        model = tmp_path / f"model-{index}.gguf"
        model.write_bytes(f"exact-model-{index}".encode())
        candidates.append(
            {
                "id": f"candidate-{index}",
                "label": f"Candidate {index}",
                "backend": "gguf",
                "model": model.name,
                "server": server.name,
                "expected": {
                    "model_sha256": file_identity(model)["sha256"],
                    "server_sha256": file_identity(server)["sha256"],
                },
            }
        )
    manifest = tmp_path / "candidates.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "campaign_id": "test-campaign",
                "candidates": candidates,
            }
        )
    )
    return manifest


def test_campaign_saves_exact_outputs_and_is_directly_consumable_by_judge_report(tmp_path):
    manifest = _gguf_manifest(tmp_path)
    output = tmp_path / "evaluation"
    summaries = run_campaign(
        manifest,
        output,
        suite="judges",
        prompt_ids=None,
        max_new_tokens=123,
        port=18180,
        gpu_layers=99,
        threads=2,
        context_size=4096,
        backend_factory=FakeBackend,
    )

    assert [row["status"] for row in summaries] == ["complete", "complete"]
    assert (output / "COMPLETED.json").is_file()
    assert (output / "candidate-manifest.json").read_bytes() == manifest.read_bytes()
    terminal = json.loads((output / "COMPLETED.json").read_text())
    assert len(terminal["artifact_inventory_sha256"]) == 64
    rows = read_jsonl(output / "responses.jsonl")
    assert len(rows) == 20
    assert len({row["prompt_set_sha256"] for row in rows}) == 1
    assert [row["id"] for row in rows[:10]] == [row.id for row in select_prompts("judges", None)]
    assert [row["text"] for row in rows[:10]] == [
        row.text for row in select_prompts("judges", None)
    ]
    first = rows[0]
    expected_model_hash = file_identity(tmp_path / "model-0.gguf")["sha256"]
    assert first["model_sha256"] == expected_model_hash
    assert first["model_identity_kind"] == "gguf_file_sha256"
    assert first["server_sha256"] == file_identity(tmp_path / "llama-server")["sha256"]
    raw_path = output / "candidates" / first["candidate_id"] / first["raw_output"]["path"]
    assert raw_path.read_bytes().startswith(b"RAW::candidate-0::automated_01")

    names = load_names(output / "artifacts.csv")
    gate1_summary, details = evaluate(rows, names)
    assert len(gate1_summary) == 2
    assert len(details) == 20
    assert all(row["status"] == "complete" for row in gate1_summary)
    with (output / "gate1-rubric.csv").open(newline="", encoding="utf-8") as handle:
        assert len(list(csv.DictReader(handle))) == 2


def test_existing_output_directory_is_never_appended_or_reused(tmp_path):
    manifest = _gguf_manifest(tmp_path, count=1)
    output = tmp_path / "evaluation"
    output.mkdir()
    sentinel = output / "sentinel"
    sentinel.write_text("unchanged")
    with pytest.raises(FileExistsError):
        run_campaign(
            manifest,
            output,
            suite="judges",
            prompt_ids=["automated_01", "automated_02"],
            max_new_tokens=16,
            port=18180,
            gpu_layers=0,
            threads=1,
            context_size=512,
            backend_factory=FakeBackend,
        )
    assert sentinel.read_text() == "unchanged"


def test_runtime_receipt_is_captured_before_output_tree_exists(tmp_path, monkeypatch):
    manifest = _gguf_manifest(tmp_path, count=1)
    output = tmp_path / "evaluation"

    def runtime_receipt():
        assert not output.exists()
        return {"git": {"available": True, "dirty": False}}

    monkeypatch.setattr(candidate_eval, "_runtime_receipt", runtime_receipt)
    run_campaign(
        manifest,
        output,
        suite="judges",
        prompt_ids=["automated_01", "automated_02"],
        max_new_tokens=16,
        port=18180,
        gpu_layers=0,
        threads=1,
        context_size=512,
        backend_factory=FakeBackend,
    )
    assert json.loads((output / "run.json").read_text())["runtime"]["git"]["dirty"] is False


def test_failure_is_receipted_and_does_not_hide_later_candidates(tmp_path):
    manifest = _gguf_manifest(tmp_path)
    output = tmp_path / "evaluation"
    summaries = run_campaign(
        manifest,
        output,
        suite="judges",
        prompt_ids=["automated_01", "automated_02"],
        max_new_tokens=16,
        port=18180,
        gpu_layers=0,
        threads=1,
        context_size=512,
        backend_factory=FirstCandidateFails,
    )
    by_id = {row["candidate_id"]: row for row in summaries}
    assert by_id["candidate-0"]["status"] == "failed"
    assert by_id["candidate-1"]["status"] == "complete"
    assert (output / "FAILED.json").is_file()
    assert (output / "candidates/candidate-0/error.json").is_file()
    assert len(read_jsonl(output / "candidates/candidate-1/responses.jsonl")) == 2


def test_invalid_backend_result_is_a_receipted_candidate_failure(tmp_path):
    manifest = _gguf_manifest(tmp_path, count=1)
    output = tmp_path / "evaluation"
    summaries = run_campaign(
        manifest,
        output,
        suite="judges",
        prompt_ids=["automated_01", "automated_02"],
        max_new_tokens=16,
        port=18180,
        gpu_layers=0,
        threads=1,
        context_size=512,
        backend_factory=InvalidGenerationResult,
    )
    assert summaries[0]["status"] == "failed"
    assert "answer is not text" in summaries[0]["error"]
    assert (output / "FAILED.json").is_file()


def test_requires_two_unique_known_prompts():
    with pytest.raises(EvaluationInputError, match="at least two"):
        select_prompts("judges", ["automated_01"])
    with pytest.raises(EvaluationInputError, match="duplicate"):
        select_prompts("judges", ["automated_01", "automated_01"])
    with pytest.raises(EvaluationInputError, match="unknown"):
        select_prompts("judges", ["automated_01", "not-a-prompt"])


def test_hash_mismatch_fails_before_output_directory_creation(tmp_path):
    manifest_path = _gguf_manifest(tmp_path, count=1)
    payload = json.loads(manifest_path.read_text())
    payload["candidates"][0]["expected"]["model_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(payload))
    output = tmp_path / "evaluation"
    with pytest.raises(EvaluationInputError, match="hash mismatch"):
        run_campaign(
            manifest_path,
            output,
            suite="judges",
            prompt_ids=["automated_01", "automated_02"],
            max_new_tokens=16,
            port=18180,
            gpu_layers=0,
            threads=1,
            context_size=512,
            backend_factory=FakeBackend,
        )
    assert not output.exists()


def test_duplicate_candidate_model_identity_fails_before_inference(tmp_path):
    manifest_path = _gguf_manifest(tmp_path)
    payload = json.loads(manifest_path.read_text())
    payload["candidates"][1]["model"] = payload["candidates"][0]["model"]
    payload["candidates"][1]["expected"]["model_sha256"] = payload["candidates"][0]["expected"][
        "model_sha256"
    ]
    manifest_path.write_text(json.dumps(payload))
    output = tmp_path / "evaluation"
    with pytest.raises(EvaluationInputError, match="duplicate candidate model identity"):
        run_campaign(
            manifest_path,
            output,
            suite="judges",
            prompt_ids=["automated_01", "automated_02"],
            max_new_tokens=16,
            port=18180,
            gpu_layers=0,
            threads=1,
            context_size=512,
            backend_factory=FakeBackend,
        )
    assert not output.exists()


def test_hf_and_peft_artifact_trees_are_verified(tmp_path):
    for directory, filename in [
        (tmp_path / "base", "model.safetensors"),
        (tmp_path / "adapter", "adapter_model.safetensors"),
        (tmp_path / "tokenizer", "tokenizer.json"),
    ]:
        directory.mkdir()
        (directory / filename).write_text(directory.name)
    (tmp_path / "adapter" / "adapter_config.json").write_text('{"r": 16}\n')
    base_hash = tree_identity(tmp_path / "base")["tree_sha256"]
    adapter_hash = tree_identity(tmp_path / "adapter")["tree_sha256"]
    tokenizer_hash = tree_identity(tmp_path / "tokenizer")["tree_sha256"]
    manifest_path = tmp_path / "mixed.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "candidates": [
                    {
                        "id": "upstream",
                        "backend": "hf",
                        "model": "base",
                        "tokenizer": "tokenizer",
                        "expected": {
                            "model_tree_sha256": base_hash,
                            "tokenizer_tree_sha256": tokenizer_hash,
                        },
                    },
                    {
                        "id": "new-lora",
                        "backend": "peft",
                        "base_model": "base",
                        "adapter": "adapter",
                        "tokenizer": "tokenizer",
                        "expected": {
                            "base_model_tree_sha256": base_hash,
                            "adapter_tree_sha256": adapter_hash,
                            "tokenizer_tree_sha256": tokenizer_hash,
                        },
                    },
                ],
            }
        )
    )
    manifest = load_candidate_manifest(manifest_path)
    cache = {}
    identities = [verify_candidate(candidate, cache) for candidate in manifest["candidates"]]
    assert [identity["backend"] for identity in identities] == ["hf", "peft"]
    assert identities[1]["observed"]["adapter"]["tree_sha256"] == adapter_hash


def test_peft_identity_requires_inference_relevant_adapter_config(tmp_path):
    for directory, filename in [
        (tmp_path / "base", "model.safetensors"),
        (tmp_path / "adapter", "adapter_model.safetensors"),
        (tmp_path / "tokenizer", "tokenizer.json"),
    ]:
        directory.mkdir()
        (directory / filename).write_text(directory.name)
    manifest_path = tmp_path / "peft.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "candidates": [
                    {
                        "id": "candidate",
                        "backend": "peft",
                        "base_model": "base",
                        "adapter": "adapter",
                        "tokenizer": "tokenizer",
                        "expected": {
                            "base_model_tree_sha256": tree_identity(tmp_path / "base")[
                                "tree_sha256"
                            ],
                            "adapter_tree_sha256": tree_identity(tmp_path / "adapter")[
                                "tree_sha256"
                            ],
                            "tokenizer_tree_sha256": tree_identity(tmp_path / "tokenizer")[
                                "tree_sha256"
                            ],
                        },
                    }
                ],
            }
        )
    )
    candidate = load_candidate_manifest(manifest_path)["candidates"][0]
    with pytest.raises(EvaluationInputError, match="adapter lacks"):
        verify_candidate(candidate, {})
