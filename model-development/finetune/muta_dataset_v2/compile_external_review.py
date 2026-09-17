"""Compile source-auditor decisions into immutable exact-row receipts.

This command does not decide whether a row is correct.  It validates that the
source-specific auditors covered every supplied review-pack row exactly once,
binds each decision to the frozen rubric and exact record content, and emits a
canonical cumulative receipt ledger for the refill materializer and selector.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .core import repository_root, sha256_file
from .select_sft import (
    APPROVAL_SCHEMA_PATH,
    _canonical_json_bytes,
    approval_receipt_id,
    record_content_sha256,
)

COMPILER_PATH = Path(__file__).resolve()
REVIEWER = "OpenAI Codex model-assisted audit (user-authorized; not independent human review)"
RUBRIC_VERSION = "muta-external-exact-row-audit-v1"
SOURCE_METHODS = {
    "template_gsm": (
        "exact review-pack ID/content-hash and decision-coverage validation; deterministic and "
        "model-assisted TemplateGSM arithmetic, story, entity, unit, operation, and language "
        "checks preserved from the source review; sampled adversarial review found source-level "
        "failures, so the final quality-first policy rejects the row fail-closed; not an "
        "exhaustive independent human semantic review"
    ),
    "qasc": (
        "exact review-pack ID/content-hash and decision-coverage validation; deterministic QASC "
        "binding, answer-key, duplication, placeholder, and grammar checks plus limited "
        "model-assisted semantic checks preserved from the source review; semantic coverage was "
        "insufficient, so the final quality-first policy rejects the row fail-closed; not an "
        "exhaustive independent human semantic review"
    ),
    "gsm8k": (
        "exact review-pack ID/content-hash and decision-coverage validation; deterministic and "
        "model-assisted GSM8K annotation, story-equation, quantity, unit, and semantic-"
        "plausibility checks preserved from the source review; sampled adversarial review found "
        "source-level failures, so the final quality-first policy rejects the row fail-closed; "
        "not an exhaustive independent human semantic review"
    ),
}


@dataclass(frozen=True)
class _CapturedInput:
    """One immutable byte snapshot used for parsing, hashing, and archiving."""

    source_path: Path
    display_path: str
    data: bytes
    size: int
    sha256: str
    identity: tuple[int, int, int, int, int]

    def metadata(self) -> dict[str, Any]:
        return {
            "path": self.display_path,
            "bytes": self.size,
            "sha256": self.sha256,
        }


def _display_path(path: Path) -> str:
    workspace = repository_root().resolve()
    try:
        return path.relative_to(workspace).as_posix()
    except ValueError:
        return str(path)


def _stat_identity(stat_result: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        stat_result.st_dev,
        stat_result.st_ino,
        stat_result.st_size,
        stat_result.st_mtime_ns,
        stat_result.st_ctime_ns,
    )


def _capture_input(path: Path) -> _CapturedInput:
    """Read a regular file once and prove its identity stayed stable during capture."""

    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise FileNotFoundError(f"input is not a regular file: {resolved}")
    before = resolved.stat()
    data = resolved.read_bytes()
    after = resolved.stat()
    if _stat_identity(before) != _stat_identity(after) or len(data) != after.st_size:
        raise RuntimeError(f"input changed while it was being captured: {resolved}")
    return _CapturedInput(
        source_path=resolved,
        display_path=_display_path(resolved),
        data=data,
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        identity=_stat_identity(after),
    )


def _assert_capture_unchanged(capture: _CapturedInput) -> None:
    """Detect input replacement or mutation after the byte snapshot was consumed."""

    try:
        current_path = capture.source_path.resolve(strict=True)
        current_stat = current_path.stat()
        current_data = current_path.read_bytes()
        final_stat = current_path.stat()
    except FileNotFoundError as error:
        raise RuntimeError(f"captured input disappeared: {capture.source_path}") from error
    if (
        current_path != capture.source_path
        or _stat_identity(current_stat) != _stat_identity(final_stat)
        or _stat_identity(final_stat) != capture.identity
        or len(current_data) != capture.size
        or hashlib.sha256(current_data).hexdigest() != capture.sha256
    ):
        raise RuntimeError(
            f"captured input changed while the ledger was compiled: {capture.source_path}"
        )


def _validate_reviewed_at(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("reviewed_at must be an ISO 8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("reviewed_at must include an explicit UTC offset")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise TypeError(f"{path}:{line_number} is not a JSON object")
            documents.append(value)
    if not documents:
        raise ValueError(f"input is empty: {path}")
    return documents


def _load_jsonl_snapshot(capture: _CapturedInput) -> list[dict[str, Any]]:
    try:
        text = capture.data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"input is not valid UTF-8: {capture.display_path}") from error
    documents: list[dict[str, Any]] = []
    # JSON strings may legally contain Unicode line/paragraph separators. JSONL is
    # delimited only by ASCII LF, so str.splitlines() would corrupt such records.
    for line_number, line in enumerate(text.split("\n"), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{capture.display_path}:{line_number} is not valid JSON") from error
        if not isinstance(value, dict):
            raise TypeError(f"{capture.display_path}:{line_number} is not a JSON object")
        documents.append(value)
    if not documents:
        raise ValueError(f"input is empty: {capture.display_path}")
    return documents


def _validate_universal_binding(wrapper: dict[str, Any], record: dict[str, Any]) -> None:
    record_id = record["id"]
    provenance = record.get("provenance") or {}
    verification = record.get("verification") or {}
    contamination = record.get("contamination") or {}
    tokenization = record.get("tokenization") or {}
    messages = record.get("messages")
    failures: list[str] = []
    if record.get("split") != "train":
        failures.append("not_train")
    if verification.get("training_eligible") is not False:
        failures.append("not_audit_gated")
    if contamination.get("holdout_checked") is not True:
        failures.append("holdout_not_checked")
    if messages != [
        {"role": "user", "content": record.get("prompt")},
        {"role": "assistant", "content": record.get("completion")},
    ]:
        failures.append("messages_do_not_mirror_prompt_completion")
    answer = str(record.get("answer", "")).strip()
    if str(verification.get("expected", "")).strip() != answer:
        failures.append("expected_answer_mismatch")
    if str(verification.get("observed", "")).strip() != answer:
        failures.append("observed_answer_mismatch")
    if tokenization.get("within_limit") is not True or not isinstance(
        tokenization.get("sequence_tokens"), int
    ):
        failures.append("invalid_token_limit_attestation")
    elif tokenization["sequence_tokens"] > tokenization.get("max_sequence_tokens", -1):
        failures.append("recorded_token_limit_exceeded")
    if wrapper.get("semantic_cluster_id") != provenance.get("semantic_cluster_id"):
        failures.append("semantic_cluster_mismatch")
    if wrapper.get("source_task_sha256") != contamination.get("source_task_sha256"):
        failures.append("source_task_hash_mismatch")
    if failures:
        raise ValueError(f"review wrapper fails universal binding for {record_id}: {failures}")


def _load_candidates(paths: Sequence[Path]) -> tuple[dict[str, dict[str, Any]], str]:
    candidates: dict[str, dict[str, Any]] = {}
    fingerprint: str | None = None
    for path in paths:
        for wrapper in _load_jsonl(path):
            record = wrapper.get("record")
            if not isinstance(record, dict):
                raise TypeError(f"review wrapper in {path} has no record object")
            record_id = record.get("id")
            source_id = (record.get("provenance") or {}).get("source_id")
            if not isinstance(record_id, str) or not record_id:
                raise ValueError(f"review wrapper in {path} has no stable record ID")
            if record_id in candidates:
                raise ValueError(f"record appears in more than one review pack: {record_id}")
            if source_id not in SOURCE_METHODS or wrapper.get("source_id") != source_id:
                raise ValueError(
                    f"review wrapper has unsupported or inconsistent source: {record_id}"
                )
            if wrapper.get("record_id") != record_id:
                raise ValueError(f"review wrapper record ID mismatch: {record_id}")
            content_hash = record_content_sha256(record)
            if wrapper.get("record_content_sha256") != content_hash:
                raise ValueError(f"review wrapper content hash mismatch: {record_id}")
            _validate_universal_binding(wrapper, record)
            row_fingerprint = wrapper.get("warehouse_dataset_fingerprint_sha256")
            if not isinstance(row_fingerprint, str) or len(row_fingerprint) != 64:
                raise ValueError(f"review wrapper has invalid warehouse fingerprint: {record_id}")
            if fingerprint is None:
                fingerprint = row_fingerprint
            elif row_fingerprint != fingerprint:
                raise ValueError("review packs bind different warehouse fingerprints")
            candidates[record_id] = wrapper
    assert fingerprint is not None
    return candidates, fingerprint


def _load_candidates_from_snapshots(
    captures: Sequence[_CapturedInput],
) -> tuple[dict[str, dict[str, Any]], str]:
    candidates: dict[str, dict[str, Any]] = {}
    fingerprint: str | None = None
    for capture in captures:
        for wrapper in _load_jsonl_snapshot(capture):
            record = wrapper.get("record")
            if not isinstance(record, dict):
                raise TypeError(f"review wrapper in {capture.display_path} has no record object")
            record_id = record.get("id")
            source_id = (record.get("provenance") or {}).get("source_id")
            if not isinstance(record_id, str) or not record_id:
                raise ValueError(
                    f"review wrapper in {capture.display_path} has no stable record ID"
                )
            if record_id in candidates:
                raise ValueError(f"record appears in more than one review pack: {record_id}")
            if source_id not in SOURCE_METHODS or wrapper.get("source_id") != source_id:
                raise ValueError(
                    f"review wrapper has unsupported or inconsistent source: {record_id}"
                )
            if wrapper.get("record_id") != record_id:
                raise ValueError(f"review wrapper record ID mismatch: {record_id}")
            content_hash = record_content_sha256(record)
            if wrapper.get("record_content_sha256") != content_hash:
                raise ValueError(f"review wrapper content hash mismatch: {record_id}")
            _validate_universal_binding(wrapper, record)
            row_fingerprint = wrapper.get("warehouse_dataset_fingerprint_sha256")
            if not isinstance(row_fingerprint, str) or len(row_fingerprint) != 64:
                raise ValueError(f"review wrapper has invalid warehouse fingerprint: {record_id}")
            if fingerprint is None:
                fingerprint = row_fingerprint
            elif row_fingerprint != fingerprint:
                raise ValueError("review packs bind different warehouse fingerprints")
            candidates[record_id] = wrapper
    if fingerprint is None:
        raise ValueError("review-pack snapshots are empty")
    return candidates, fingerprint


def _load_decisions(paths: Sequence[Path]) -> dict[str, dict[str, Any]]:
    decisions: dict[str, dict[str, Any]] = {}
    for path in paths:
        for decision in _load_jsonl(path):
            record_id = decision.get("record_id")
            source_id = decision.get("source_id")
            verdict = decision.get("decision")
            reasons = decision.get("reason_codes")
            if not isinstance(record_id, str) or not record_id:
                raise ValueError(f"decision in {path} has no record_id")
            if record_id in decisions:
                raise ValueError(f"row has multiple source-auditor decisions: {record_id}")
            if source_id not in SOURCE_METHODS:
                raise ValueError(f"decision has unsupported source: {record_id}")
            if verdict not in {"approved", "rejected"}:
                raise ValueError(f"decision has invalid verdict: {record_id}")
            if not isinstance(reasons, list) or any(
                not isinstance(reason, str) or not reason.strip() for reason in reasons
            ):
                raise ValueError(f"decision has invalid reason_codes: {record_id}")
            if verdict == "rejected" and not reasons:
                raise ValueError(f"rejection has no reason code: {record_id}")
            if not isinstance(decision.get("checks"), dict):
                raise TypeError(f"decision has no structured checks: {record_id}")
            notes = decision.get("notes")
            if notes is not None and not isinstance(notes, str):
                raise TypeError(f"decision notes must be text: {record_id}")
            decisions[record_id] = decision
    return decisions


def _load_decisions_from_snapshots(
    captures: Sequence[_CapturedInput],
) -> dict[str, dict[str, Any]]:
    decisions: dict[str, dict[str, Any]] = {}
    for capture in captures:
        for decision in _load_jsonl_snapshot(capture):
            record_id = decision.get("record_id")
            source_id = decision.get("source_id")
            verdict = decision.get("decision")
            reasons = decision.get("reason_codes")
            if not isinstance(record_id, str) or not record_id:
                raise ValueError(f"decision in {capture.display_path} has no record_id")
            if record_id in decisions:
                raise ValueError(f"row has multiple source-auditor decisions: {record_id}")
            if source_id not in SOURCE_METHODS:
                raise ValueError(f"decision has unsupported source: {record_id}")
            if verdict not in {"approved", "rejected"}:
                raise ValueError(f"decision has invalid verdict: {record_id}")
            if not isinstance(reasons, list) or any(
                not isinstance(reason, str) or not reason.strip() for reason in reasons
            ):
                raise ValueError(f"decision has invalid reason_codes: {record_id}")
            if verdict == "rejected" and not reasons:
                raise ValueError(f"rejection has no reason code: {record_id}")
            if not isinstance(decision.get("checks"), dict):
                raise TypeError(f"decision has no structured checks: {record_id}")
            notes = decision.get("notes")
            if notes is not None and not isinstance(notes, str):
                raise TypeError(f"decision notes must be text: {record_id}")
            decisions[record_id] = decision
    return decisions


def _validate_decision_binding(*, wrapper: dict[str, Any], decision: dict[str, Any]) -> None:
    record_id = wrapper["record_id"]
    if decision["source_id"] != wrapper["source_id"]:
        raise ValueError(f"decision source mismatch: {record_id}")
    optional_bindings = {
        "record_content_sha256": wrapper["record_content_sha256"],
        "warehouse_dataset_fingerprint_sha256": wrapper["warehouse_dataset_fingerprint_sha256"],
    }
    for field, expected in optional_bindings.items():
        observed = decision.get(field)
        if observed is not None and observed != expected:
            raise ValueError(f"decision {field} mismatch: {record_id}")
    binding = decision.get("binding")
    if binding is not None:
        if not isinstance(binding, dict):
            raise TypeError(f"decision binding must be an object: {record_id}")
        for field, expected in optional_bindings.items():
            observed = binding.get(field)
            if observed is not None and observed != expected:
                raise ValueError(f"decision binding {field} mismatch: {record_id}")


def _receipt(
    *,
    wrapper: dict[str, Any],
    decision: dict[str, Any],
    fingerprint: str,
    reviewed_at: str,
    rubric_hash: str,
) -> dict[str, Any]:
    receipt = {
        "schema_version": 1,
        "warehouse_dataset_fingerprint_sha256": fingerprint,
        "target_type": "record",
        "source_id": wrapper["source_id"],
        "record_id": wrapper["record_id"],
        "record_content_sha256": wrapper["record_content_sha256"],
        "decision": decision["decision"],
        "reviewer": REVIEWER,
        "review_method": SOURCE_METHODS[wrapper["source_id"]],
        "reviewed_at": reviewed_at,
        "rubric_version": RUBRIC_VERSION,
        "rubric_sha256": rubric_hash,
    }
    receipt["receipt_id"] = approval_receipt_id(receipt)
    return receipt


def _write_jsonl(path: Path, documents: Sequence[dict[str, Any]]) -> None:
    with path.open("wb") as handle:
        for document in documents:
            handle.write(_canonical_json_bytes(document))
            handle.write(b"\n")


def compile_external_review(
    *,
    review_packs: Sequence[Path],
    decision_files: Sequence[Path],
    rubric: Path,
    reviewed_at: str,
    output: Path,
) -> dict[str, Any]:
    _validate_reviewed_at(reviewed_at)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite review ledger: {output}")
    if not review_packs or not decision_files:
        raise ValueError("at least one review pack and one decision file are required")

    compiler_capture = _capture_input(COMPILER_PATH)
    schema_capture = _capture_input(APPROVAL_SCHEMA_PATH)
    rubric_capture = _capture_input(rubric)
    review_captures = [_capture_input(path) for path in review_packs]
    decision_captures = [_capture_input(path) for path in decision_files]
    all_captures = [
        compiler_capture,
        schema_capture,
        rubric_capture,
        *review_captures,
        *decision_captures,
    ]

    candidates, fingerprint = _load_candidates_from_snapshots(review_captures)
    decisions = _load_decisions_from_snapshots(decision_captures)
    missing = sorted(set(candidates).difference(decisions))
    extra = sorted(set(decisions).difference(candidates))
    if missing or extra:
        raise ValueError(
            f"decision coverage mismatch: missing={len(missing):,}, extra={len(extra):,}; "
            f"first_missing={missing[:3]}, first_extra={extra[:3]}"
        )
    for record_id, decision in decisions.items():
        _validate_decision_binding(wrapper=candidates[record_id], decision=decision)

    rubric_hash = rubric_capture.sha256
    try:
        receipt_schema = json.loads(schema_capture.data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("approval receipt schema is not valid UTF-8 JSON") from error
    validator = Draft202012Validator(receipt_schema, format_checker=FormatChecker())
    order = sorted(
        candidates,
        key=lambda record_id: (
            candidates[record_id]["source_id"],
            candidates[record_id]["selection_rank_sha256"],
            record_id,
        ),
    )
    receipts: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    for record_id in order:
        wrapper = candidates[record_id]
        decision = decisions[record_id]
        receipt = _receipt(
            wrapper=wrapper,
            decision=decision,
            fingerprint=fingerprint,
            reviewed_at=reviewed_at,
            rubric_hash=rubric_hash,
        )
        errors = sorted(validator.iter_errors(receipt), key=lambda error: list(error.path))
        if errors:
            detail = "; ".join(error.message for error in errors)
            raise ValueError(f"generated malformed receipt for {record_id}: {detail}")
        receipts.append(receipt)
        evidence.append(
            {
                "record_id": record_id,
                "source_id": wrapper["source_id"],
                "record_content_sha256": wrapper["record_content_sha256"],
                "selection_rank_sha256": wrapper["selection_rank_sha256"],
                "decision": decision["decision"],
                "reason_codes": sorted(set(decision["reason_codes"])),
                "notes": decision.get("notes", ""),
                "checks": decision["checks"],
                "receipt_id": receipt["receipt_id"],
            }
        )
        counts[f"{wrapper['source_id']}::{decision['decision']}"] += 1
        for reason in set(decision["reason_codes"]):
            reasons[f"{wrapper['source_id']}::{reason}"] += 1
    receipt_ids = [receipt["receipt_id"] for receipt in receipts]
    if len(receipt_ids) != len(set(receipt_ids)):
        raise RuntimeError("generated receipt IDs are not unique")

    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="muta-review-ledger-", dir=output.parent) as state:
        partial = Path(state) / "ledger"
        partial.mkdir()
        receipt_path = partial / "approval-receipts.jsonl"
        evidence_path = partial / "review-decisions.jsonl"
        _write_jsonl(receipt_path, receipts)
        _write_jsonl(evidence_path, evidence)

        provenance_directory = partial / "provenance"
        provenance_directory.mkdir()
        archived_compiler = provenance_directory / COMPILER_PATH.name
        archived_schema = provenance_directory / APPROVAL_SCHEMA_PATH.name
        archived_rubric = provenance_directory / rubric_capture.source_path.name
        archived_compiler.write_bytes(compiler_capture.data)
        archived_schema.write_bytes(schema_capture.data)
        archived_rubric.write_bytes(rubric_capture.data)

        for archived, capture in (
            (archived_compiler, compiler_capture),
            (archived_schema, schema_capture),
            (archived_rubric, rubric_capture),
        ):
            if archived.stat().st_size != capture.size or sha256_file(archived) != capture.sha256:
                raise RuntimeError(f"archived provenance does not match captured input: {archived}")

        review_metadata = [capture.metadata() for capture in review_captures]
        decision_metadata = [capture.metadata() for capture in decision_captures]
        input_references = {
            "schema_version": 1,
            "purpose": (
                "Compact content-addressed references to the exact review-pack and final-decision "
                "inputs consumed by the receipt compiler; row content is not duplicated here."
            ),
            "review_packs": review_metadata,
            "source_decisions": decision_metadata,
        }
        input_references_path = provenance_directory / "input-references.json"
        input_references_path.write_text(
            json.dumps(input_references, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        inputs = {
            "compiler": {
                "path": archived_compiler.relative_to(partial).as_posix(),
                "source_path": compiler_capture.display_path,
                "bytes": compiler_capture.size,
                "sha256": compiler_capture.sha256,
            },
            "approval_schema": {
                "path": archived_schema.relative_to(partial).as_posix(),
                "source_path": schema_capture.display_path,
                "bytes": schema_capture.size,
                "sha256": schema_capture.sha256,
            },
            "review_packs": review_metadata,
            "source_decisions": decision_metadata,
            "rubric": {
                "path": archived_rubric.relative_to(partial).as_posix(),
                "source_path": rubric_capture.display_path,
                "bytes": rubric_capture.size,
                "sha256": rubric_hash,
            },
            "input_references": {
                "path": input_references_path.relative_to(partial).as_posix(),
                "bytes": input_references_path.stat().st_size,
                "sha256": sha256_file(input_references_path),
            },
        }
        manifest = {
            "schema_version": 1,
            "artifact_name": "muta-external-exact-row-model-assisted-review-ledger",
            "warehouse_dataset_fingerprint_sha256": fingerprint,
            "trust_statement": (
                "user-authorized Codex model-assisted and deterministic review; not independent "
                "human row-by-row attestation"
            ),
            "reviewer": REVIEWER,
            "reviewed_at": reviewed_at,
            "rubric_version": RUBRIC_VERSION,
            "rubric_sha256": rubric_hash,
            "row_count": len(receipts),
            "counts": dict(sorted(counts.items())),
            "rejection_reasons": dict(sorted(reasons.items())),
            "coverage": {
                "candidate_rows": len(candidates),
                "decision_rows": len(decisions),
                "missing": 0,
                "extra": 0,
                "one_decision_per_row": True,
            },
            "outputs": {
                "approval_receipts": {
                    "path": receipt_path.name,
                    "bytes": receipt_path.stat().st_size,
                    "sha256": sha256_file(receipt_path),
                },
                "review_decisions": {
                    "path": evidence_path.name,
                    "bytes": evidence_path.stat().st_size,
                    "sha256": sha256_file(evidence_path),
                },
            },
            "inputs": inputs,
        }
        manifest_path = partial / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        for capture in all_captures:
            _assert_capture_unchanged(capture)
        partial.rename(output)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-pack", action="append", type=Path, required=True)
    parser.add_argument("--decision", action="append", type=Path, required=True)
    parser.add_argument("--rubric", type=Path, required=True)
    parser.add_argument("--reviewed-at", required=True, help="ISO 8601 timestamp with timezone")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = compile_external_review(
        review_packs=args.review_pack,
        decision_files=args.decision,
        rubric=args.rubric,
        reviewed_at=args.reviewed_at,
        output=args.output,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
