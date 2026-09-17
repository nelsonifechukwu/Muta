from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

import pytest

compiler = importlib.import_module(
    "model-development.finetune.muta_dataset_v2.compile_external_review"
)
finalizer = importlib.import_module(
    "model-development.finetune.muta_dataset_v2.finalize_external_review"
)
selector = importlib.import_module("model-development.finetune.muta_dataset_v2.select_sft")


def _write_jsonl(path: Path, documents: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(document, separators=(",", ":")) + "\n" for document in documents),
        encoding="utf-8",
    )


def _wrapper(record_id: str, source_id: str, rank: str) -> dict:
    prompt = "What is 2 + 3?"
    completion = "2 + 3 = 5. Final answer: 5."
    cluster = f"row:{record_id}"
    source_task_hash = rank * 64
    record = {
        "id": record_id,
        "prompt": prompt,
        "completion": completion,
        "messages": [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": completion},
        ],
        "answer": "5",
        "split": "train",
        "provenance": {"source_id": source_id, "semantic_cluster_id": cluster},
        "verification": {
            "training_eligible": False,
            "expected": "5",
            "observed": "5",
        },
        "contamination": {
            "holdout_checked": True,
            "source_task_sha256": source_task_hash,
        },
        "tokenization": {
            "within_limit": True,
            "sequence_tokens": 20,
            "max_sequence_tokens": 1024,
        },
    }
    return {
        "schema_version": 1,
        "warehouse_dataset_fingerprint_sha256": "a" * 64,
        "source_id": source_id,
        "record_id": record_id,
        "record_content_sha256": selector.record_content_sha256(record),
        "selection_rank_sha256": rank * 64,
        "semantic_cluster_id": cluster,
        "source_task_sha256": source_task_hash,
        "record": record,
    }


def _decision(record_id: str, source_id: str, verdict: str) -> dict:
    return {
        "record_id": record_id,
        "source_id": source_id,
        "decision": verdict,
        "reason_codes": [] if verdict == "approved" else ["ambiguous"],
        "notes": "fixture",
        "checks": {"answer_correct": verdict == "approved"},
    }


def test_compile_external_review_binds_every_exact_row(tmp_path: Path) -> None:
    pack = tmp_path / "pack.jsonl"
    decisions = tmp_path / "decisions.jsonl"
    rubric = tmp_path / "rubric.md"
    output = tmp_path / "ledger"
    wrappers = [
        _wrapper("row-template", "template_gsm", "1"),
        _wrapper("row-qasc", "qasc", "2"),
        _wrapper("row-gsm", "gsm8k", "3"),
    ]
    _write_jsonl(pack, wrappers)
    _write_jsonl(
        decisions,
        [
            _decision("row-template", "template_gsm", "approved"),
            _decision("row-qasc", "qasc", "rejected"),
            _decision("row-gsm", "gsm8k", "approved"),
        ],
    )
    rubric.write_text("frozen fixture rubric\n", encoding="utf-8")

    manifest = compiler.compile_external_review(
        review_packs=[pack],
        decision_files=[decisions],
        rubric=rubric,
        reviewed_at="2026-09-17T00:00:00Z",
        output=output,
    )

    assert manifest["row_count"] == 3
    assert manifest["coverage"]["one_decision_per_row"] is True
    assert manifest["counts"] == {
        "gsm8k::approved": 1,
        "qasc::rejected": 1,
        "template_gsm::approved": 1,
    }
    receipts = [json.loads(line) for line in (output / "approval-receipts.jsonl").open()]
    assert {receipt["decision"] for receipt in receipts} == {"approved", "rejected"}
    assert all(
        receipt["receipt_id"] == selector.approval_receipt_id(receipt) for receipt in receipts
    )
    assert all("not independent human review" in receipt["reviewer"] for receipt in receipts)
    assert all(
        "exact review-pack ID/content-hash and decision-coverage validation"
        in receipt["review_method"]
        for receipt in receipts
    )
    assert all(
        "not an exhaustive independent human semantic review" in receipt["review_method"]
        for receipt in receipts
    )
    assert all(
        "exhaustive model-assisted row audit" not in receipt["review_method"]
        for receipt in receipts
    )
    for input_name, source in (
        ("compiler", Path(compiler.__file__)),
        ("approval_schema", selector.APPROVAL_SCHEMA_PATH),
        ("rubric", rubric),
    ):
        metadata = manifest["inputs"][input_name]
        archived = output / metadata["path"]
        assert archived.read_bytes() == source.read_bytes()
        assert archived.stat().st_size == metadata["bytes"]
        assert hashlib.sha256(archived.read_bytes()).hexdigest() == metadata["sha256"]
    references_metadata = manifest["inputs"]["input_references"]
    references_path = output / references_metadata["path"]
    references = json.loads(references_path.read_text(encoding="utf-8"))
    assert references["review_packs"] == manifest["inputs"]["review_packs"]
    assert references["source_decisions"] == manifest["inputs"]["source_decisions"]
    assert hashlib.sha256(references_path.read_bytes()).hexdigest() == references_metadata["sha256"]


def test_compile_external_review_fails_closed_on_missing_decision(tmp_path: Path) -> None:
    pack = tmp_path / "pack.jsonl"
    decisions = tmp_path / "decisions.jsonl"
    rubric = tmp_path / "rubric.md"
    _write_jsonl(pack, [_wrapper("row-template", "template_gsm", "1")])
    _write_jsonl(decisions, [_decision("different-row", "template_gsm", "approved")])
    rubric.write_text("frozen fixture rubric\n", encoding="utf-8")

    with pytest.raises(ValueError, match="decision coverage mismatch"):
        compiler.compile_external_review(
            review_packs=[pack],
            decision_files=[decisions],
            rubric=rubric,
            reviewed_at="2026-09-17T00:00:00Z",
            output=tmp_path / "ledger",
        )


def test_compile_external_review_rejects_decision_binding_mismatch(tmp_path: Path) -> None:
    pack = tmp_path / "pack.jsonl"
    decisions = tmp_path / "decisions.jsonl"
    rubric = tmp_path / "rubric.md"
    wrapper = _wrapper("row-template", "template_gsm", "1")
    decision = _decision("row-template", "template_gsm", "rejected")
    decision["record_content_sha256"] = "f" * 64
    _write_jsonl(pack, [wrapper])
    _write_jsonl(decisions, [decision])
    rubric.write_text("frozen fixture rubric\n", encoding="utf-8")

    with pytest.raises(ValueError, match="record_content_sha256 mismatch"):
        compiler.compile_external_review(
            review_packs=[pack],
            decision_files=[decisions],
            rubric=rubric,
            reviewed_at="2026-09-17T00:00:00Z",
            output=tmp_path / "ledger",
        )


def test_compile_external_review_requires_explicit_timezone(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="explicit UTC offset"):
        compiler.compile_external_review(
            review_packs=[tmp_path / "unused-pack.jsonl"],
            decision_files=[tmp_path / "unused-decisions.jsonl"],
            rubric=tmp_path / "unused-rubric.md",
            reviewed_at="2026-09-17T00:00:00",
            output=tmp_path / "ledger",
        )


def test_compile_external_review_detects_input_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pack = tmp_path / "pack.jsonl"
    decisions = tmp_path / "decisions.jsonl"
    rubric = tmp_path / "rubric.md"
    _write_jsonl(pack, [_wrapper("row-template", "template_gsm", "1")])
    _write_jsonl(
        decisions,
        [_decision("row-template", "template_gsm", "rejected")],
    )
    rubric.write_text("frozen fixture rubric\n", encoding="utf-8")
    original_write_jsonl = compiler._write_jsonl
    mutated = False

    def write_then_mutate(path: Path, documents: list[dict]) -> None:
        nonlocal mutated
        original_write_jsonl(path, documents)
        if not mutated:
            decisions.write_text(decisions.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            mutated = True

    monkeypatch.setattr(compiler, "_write_jsonl", write_then_mutate)

    with pytest.raises(RuntimeError, match="captured input changed"):
        compiler.compile_external_review(
            review_packs=[pack],
            decision_files=[decisions],
            rubric=rubric,
            reviewed_at="2026-09-17T00:00:00Z",
            output=tmp_path / "ledger",
        )


def test_snapshot_jsonl_parser_preserves_unicode_line_separator(tmp_path: Path) -> None:
    path = tmp_path / "unicode-lines.jsonl"
    document = {"text": "first\u2028second"}
    path.write_text(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    parsed = compiler._load_jsonl_snapshot(compiler._capture_input(path))

    assert parsed == [document]


def test_finalize_external_review_rejects_all_and_preserves_evidence(tmp_path: Path) -> None:
    pack = tmp_path / "pack.jsonl"
    decisions = tmp_path / "decisions.jsonl"
    output = tmp_path / "final"
    wrappers = [
        _wrapper("row-template", "template_gsm", "1"),
        _wrapper("row-qasc", "qasc", "2"),
        _wrapper("row-gsm", "gsm8k", "3"),
    ]
    source_decisions = [
        _decision("row-template", "template_gsm", "approved"),
        _decision("row-qasc", "qasc", "rejected"),
        _decision("row-gsm", "gsm8k", "approved"),
    ]
    source_decisions[0]["checks"]["semantic_story"] = "provisional-pass"
    source_decisions[1]["reason_codes"] = ["insufficient-review"]
    _write_jsonl(pack, wrappers)
    _write_jsonl(decisions, source_decisions)

    manifest = finalizer.finalize_external_review(
        review_packs=[pack],
        decision_files=[decisions],
        finalized_at="2026-09-17T13:00:00+01:00",
        output=output,
        expected_source_counts={"template_gsm": 1, "qasc": 1, "gsm8k": 1},
    )

    assert manifest["row_count"] == 3
    assert manifest["authorization"] == {
        "external_rows_approved": 0,
        "external_rows_rejected": 3,
        "all_external_rows_fail_closed": True,
        "ledger_authorizes_external_training_rows": False,
    }
    assert manifest["immutability"]["external_records_edited"] == 0
    assert manifest["trust_statement"].endswith("not independent human row-by-row attestation")
    finalizer_metadata = manifest["inputs"]["finalizer"]
    archived_finalizer = output / finalizer_metadata["path"]
    assert finalizer_metadata["path"] == "provenance/finalize_external_review.py"
    assert archived_finalizer.read_bytes() == Path(finalizer.__file__).read_bytes()
    assert archived_finalizer.stat().st_size == finalizer_metadata["bytes"]
    assert (
        hashlib.sha256(archived_finalizer.read_bytes()).hexdigest() == finalizer_metadata["sha256"]
    )
    documents = [json.loads(line) for line in (output / "final-decisions.jsonl").open()]
    assert len(documents) == 3
    assert {document["decision"] for document in documents} == {"rejected"}
    by_source = {document["source_id"]: document for document in documents}
    assert by_source["template_gsm"]["original_source_review"] == source_decisions[0]
    assert by_source["qasc"]["original_source_review"] == source_decisions[1]
    assert by_source["gsm8k"]["original_source_review"] == source_decisions[2]
    assert by_source["template_gsm"]["original_source_review"]["decision"] == "approved"
    assert "SOURCE_EXCLUDED_ADVERSARIAL_AUDIT_FAILED" in by_source["gsm8k"]["reason_codes"]
    assert "SOURCE_EXCLUDED_INSUFFICIENT_SEMANTIC_REVIEW" in by_source["qasc"]["reason_codes"]
    assert all(
        document["checks"]["immutable_external_row_edited"] is False
        and document["checks"]["external_row_authorized_for_training"] is False
        for document in documents
    )
    report = (output / "REPORT.md").read_text(encoding="utf-8")
    assert "All 20,000 frozen external rows are rejected" in report
    assert "not an independent human row-by-row attestation" in report


def test_finalize_external_review_is_byte_deterministic(tmp_path: Path) -> None:
    pack = tmp_path / "pack.jsonl"
    decisions = tmp_path / "decisions.jsonl"
    wrappers = [
        _wrapper("row-template", "template_gsm", "1"),
        _wrapper("row-qasc", "qasc", "2"),
        _wrapper("row-gsm", "gsm8k", "3"),
    ]
    source_decisions = [
        _decision("row-template", "template_gsm", "approved"),
        _decision("row-qasc", "qasc", "rejected"),
        _decision("row-gsm", "gsm8k", "approved"),
    ]
    _write_jsonl(pack, list(reversed(wrappers)))
    _write_jsonl(decisions, list(reversed(source_decisions)))
    kwargs = {
        "review_packs": [pack],
        "decision_files": [decisions],
        "finalized_at": "2026-09-17T13:00:00+01:00",
        "expected_source_counts": {"template_gsm": 1, "qasc": 1, "gsm8k": 1},
    }
    first = tmp_path / "first"
    second = tmp_path / "second"

    finalizer.finalize_external_review(output=first, **kwargs)
    finalizer.finalize_external_review(output=second, **kwargs)

    for filename in (
        "final-decisions.jsonl",
        "REPORT.md",
        "manifest.json",
        "provenance/finalize_external_review.py",
    ):
        assert (first / filename).read_bytes() == (second / filename).read_bytes()


def test_finalizer_input_paths_are_workspace_relative_when_possible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    input_path = nested / "input.jsonl"
    input_path.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(finalizer, "repository_root", lambda: tmp_path)

    metadata = finalizer._input_metadata(input_path)

    assert metadata["path"] == "nested/input.jsonl"
    assert metadata["bytes"] == 3
    assert metadata["sha256"] == hashlib.sha256(b"{}\n").hexdigest()


def test_finalize_external_review_detects_finalizer_source_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pack = tmp_path / "pack.jsonl"
    decisions = tmp_path / "decisions.jsonl"
    wrappers = [
        _wrapper("row-template", "template_gsm", "1"),
        _wrapper("row-qasc", "qasc", "2"),
        _wrapper("row-gsm", "gsm8k", "3"),
    ]
    source_decisions = [
        _decision("row-template", "template_gsm", "approved"),
        _decision("row-qasc", "qasc", "rejected"),
        _decision("row-gsm", "gsm8k", "approved"),
    ]
    _write_jsonl(pack, wrappers)
    _write_jsonl(decisions, source_decisions)
    fake_finalizer = tmp_path / "fake-finalizer.py"
    fake_finalizer.write_text("original source\n", encoding="utf-8")
    original_write_jsonl = finalizer._write_jsonl

    def write_then_mutate(path: Path, documents: list[dict]) -> None:
        original_write_jsonl(path, documents)
        fake_finalizer.write_text("changed source\n", encoding="utf-8")

    monkeypatch.setattr(finalizer, "FINALIZER_PATH", fake_finalizer)
    monkeypatch.setattr(finalizer, "_write_jsonl", write_then_mutate)

    with pytest.raises(RuntimeError, match="finalizer source changed"):
        finalizer.finalize_external_review(
            review_packs=[pack],
            decision_files=[decisions],
            finalized_at="2026-09-17T13:00:00+01:00",
            output=tmp_path / "final",
            expected_source_counts={"template_gsm": 1, "qasc": 1, "gsm8k": 1},
        )


def test_finalize_external_review_rejects_binding_mismatch(tmp_path: Path) -> None:
    pack = tmp_path / "pack.jsonl"
    decisions = tmp_path / "decisions.jsonl"
    wrappers = [
        _wrapper("row-template", "template_gsm", "1"),
        _wrapper("row-qasc", "qasc", "2"),
        _wrapper("row-gsm", "gsm8k", "3"),
    ]
    source_decisions = [
        _decision("row-template", "template_gsm", "approved"),
        _decision("row-qasc", "qasc", "rejected"),
        _decision("row-gsm", "gsm8k", "approved"),
    ]
    source_decisions[2]["record_content_sha256"] = "f" * 64
    _write_jsonl(pack, wrappers)
    _write_jsonl(decisions, source_decisions)

    with pytest.raises(ValueError, match="record_content_sha256 mismatch"):
        finalizer.finalize_external_review(
            review_packs=[pack],
            decision_files=[decisions],
            finalized_at="2026-09-17T13:00:00+01:00",
            output=tmp_path / "final",
            expected_source_counts={"template_gsm": 1, "qasc": 1, "gsm8k": 1},
        )


def test_finalize_external_review_requires_timezone_and_exact_coverage(tmp_path: Path) -> None:
    pack = tmp_path / "pack.jsonl"
    decisions = tmp_path / "decisions.jsonl"
    wrappers = [
        _wrapper("row-template", "template_gsm", "1"),
        _wrapper("row-qasc", "qasc", "2"),
        _wrapper("row-gsm", "gsm8k", "3"),
    ]
    _write_jsonl(pack, wrappers)
    _write_jsonl(
        decisions,
        [
            _decision("row-template", "template_gsm", "approved"),
            _decision("row-qasc", "qasc", "rejected"),
        ],
    )

    with pytest.raises(ValueError, match="explicit UTC offset"):
        finalizer.finalize_external_review(
            review_packs=[pack],
            decision_files=[decisions],
            finalized_at="2026-09-17T13:00:00",
            output=tmp_path / "no-timezone",
            expected_source_counts={"template_gsm": 1, "qasc": 1, "gsm8k": 1},
        )
    with pytest.raises(ValueError, match="decision coverage mismatch"):
        finalizer.finalize_external_review(
            review_packs=[pack],
            decision_files=[decisions],
            finalized_at="2026-09-17T13:00:00+01:00",
            output=tmp_path / "missing",
            expected_source_counts={"template_gsm": 1, "qasc": 1, "gsm8k": 1},
        )
