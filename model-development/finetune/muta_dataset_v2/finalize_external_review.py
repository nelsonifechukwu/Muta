"""Finalize the exact external-row review as a fail-closed rejection ledger.

The source-specific review ledgers are evidence, not final authorization.  This
utility validates their exact coverage of the frozen review pack, preserves
each source decision verbatim, and applies the post-adversarial policy: none of
the 20,000 external rows is authorized for training.  The immutable warehouse
rows are not edited; their planned slots are replaced by native verified rows
when the SFT view is materialized.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from .compile_external_review import (
    _load_candidates,
    _load_decisions,
    _write_jsonl,
)
from .core import repository_root, sha256_file
from .select_sft import _canonical_json_bytes

FINALIZER_PATH = Path(__file__).resolve()
POLICY_VERSION = "muta-external-quality-first-finalization-v1"
FINALIZER = (
    "OpenAI Codex model-assisted audit finalization "
    "(user-authorized; not independent human review)"
)

SOURCE_ORDER = ("template_gsm", "qasc", "gsm8k")
EXPECTED_SOURCE_COUNTS = {
    "template_gsm": 10_000,
    "qasc": 5_000,
    "gsm8k": 5_000,
}
REPLACEMENT_MARGIN_ROWS = {
    "subject :: mathematics": 15_000,
    "subject :: integrated_science": 5_000,
    "pedagogy :: worked_solution": 15_000,
    "pedagogy :: concise_answer": 5_000,
}
REPLACEMENT_JOINT_CELL_DELTAS = {
    "muta_verified_stem_v2 :: mathematics :: worked_solution": 14_757,
    "muta_verified_stem_v2 :: mathematics :: concise_answer": 243,
    "muta_verified_stem_v2 :: integrated_science :: worked_solution": 243,
    "muta_verified_stem_v2 :: integrated_science :: concise_answer": 4_757,
}
SOURCE_POLICY: dict[str, dict[str, Any]] = {
    "template_gsm": {
        "final_reason_code": "SOURCE_EXCLUDED_ADVERSARIAL_AUDIT_FAILED",
        "basis": (
            "Independent adversarial review found systematic semantic, language, "
            "plausibility, and arithmetic false approvals."
        ),
        "replacement_margin": {
            "row_count": 10_000,
            "source_class": "native_verified",
            "subject_margin": "mathematics",
            "pedagogy_margin": "worked_solution",
        },
    },
    "qasc": {
        "final_reason_code": "SOURCE_EXCLUDED_INSUFFICIENT_SEMANTIC_REVIEW",
        "basis": (
            "The source audit could not establish exhaustive semantic correctness "
            "and the available reserve was insufficient for a safe refill."
        ),
        "replacement_margin": {
            "row_count": 5_000,
            "source_class": "native_verified",
            "subject_margin": "integrated_science",
            "pedagogy_margin": "concise_answer",
        },
    },
    "gsm8k": {
        "final_reason_code": "SOURCE_EXCLUDED_ADVERSARIAL_AUDIT_FAILED",
        "basis": (
            "Independent adversarial review found story-equation, quantity, unit, "
            "and underdetermination false approvals, including reserve rows."
        ),
        "replacement_margin": {
            "row_count": 5_000,
            "source_class": "native_verified",
            "subject_margin": "mathematics",
            "pedagogy_margin": "worked_solution",
        },
    },
}


def _validate_finalized_at(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("finalized_at must be an ISO 8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("finalized_at must include an explicit UTC offset")


def _input_metadata(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    workspace = repository_root().resolve()
    try:
        display_path = resolved.relative_to(workspace).as_posix()
    except ValueError:
        display_path = str(resolved)
    return {
        "path": display_path,
        "bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def _stable_input_metadata(paths: Sequence[Path]) -> list[dict[str, Any]]:
    return [_input_metadata(path) for path in paths]


def _assert_inputs_unchanged(
    before: Sequence[dict[str, Any]],
    paths: Sequence[Path],
) -> list[dict[str, Any]]:
    after = _stable_input_metadata(paths)
    if list(before) != after:
        raise RuntimeError("an input changed while the final ledger was being compiled")
    return after


def _validate_expected_counts(
    candidates: Mapping[str, dict[str, Any]],
    expected_source_counts: Mapping[str, int],
) -> dict[str, int]:
    expected = dict(expected_source_counts)
    if set(expected) != set(SOURCE_POLICY):
        raise ValueError(
            "expected_source_counts must specify exactly template_gsm, qasc, and gsm8k"
        )
    if any(
        not isinstance(count, int) or isinstance(count, bool) or count < 0
        for count in expected.values()
    ):
        raise ValueError("expected source counts must be non-negative integers")
    observed = Counter(wrapper["source_id"] for wrapper in candidates.values())
    observed_dict = {source: observed[source] for source in SOURCE_ORDER}
    if observed_dict != expected:
        raise ValueError(
            f"review-pack source counts do not match the frozen expectation: "
            f"observed={observed_dict}, expected={expected}"
        )
    return observed_dict


def _validate_decision_binding(
    *,
    wrapper: dict[str, Any],
    decision: dict[str, Any],
) -> None:
    record_id = wrapper["record_id"]
    if decision["source_id"] != wrapper["source_id"]:
        raise ValueError(f"decision source mismatch: {record_id}")
    optional_bindings = {
        "record_content_sha256": wrapper["record_content_sha256"],
        "warehouse_dataset_fingerprint_sha256": wrapper[
            "warehouse_dataset_fingerprint_sha256"
        ],
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


def _original_decision_hash(decision: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json_bytes(decision)).hexdigest()


def _final_decision(
    *,
    wrapper: dict[str, Any],
    source_decision: dict[str, Any],
    finalized_at: str,
) -> dict[str, Any]:
    source_id = wrapper["source_id"]
    policy = SOURCE_POLICY[source_id]
    final_reason = policy["final_reason_code"]
    original_reason_codes = source_decision["reason_codes"]
    reason_codes = sorted(set(original_reason_codes) | {final_reason})
    replacement_margin = policy["replacement_margin"]
    return {
        "schema_version": 1,
        "warehouse_dataset_fingerprint_sha256": wrapper[
            "warehouse_dataset_fingerprint_sha256"
        ],
        "record_id": wrapper["record_id"],
        "source_id": source_id,
        "record_content_sha256": wrapper["record_content_sha256"],
        "selection_rank_sha256": wrapper["selection_rank_sha256"],
        "decision": "rejected",
        "reason_codes": reason_codes,
        "notes": (
            f"Fail-closed final policy: {policy['basis']} The immutable external row was "
            "not edited and is not authorized for training; its allocation is replaced "
            "within the documented balanced native allocation while preserving the removed "
            "source allocation's subject and pedagogy margins."
        ),
        "checks": {
            "exact_review_pack_binding_validated": True,
            "exact_source_decision_coverage_validated": True,
            "original_source_review_preserved": True,
            "immutable_external_row_edited": False,
            "external_row_authorized_for_training": False,
            "native_verified_replacement_required": True,
            "source_level_final_reason_code": final_reason,
        },
        "finalization": {
            "policy_version": POLICY_VERSION,
            "finalizer": FINALIZER,
            "finalized_at": finalized_at,
            "source_level_basis": policy["basis"],
            "replacement_margin": replacement_margin,
        },
        "original_source_review_sha256": _original_decision_hash(source_decision),
        "original_source_review": source_decision,
    }


def _render_report(manifest_basis: dict[str, Any], decisions_hash: str) -> str:
    lines = [
        "# Final external 20,000-row audit disposition",
        "",
        "## Outcome",
        "",
        (
            "All 20,000 frozen external rows are rejected by the final fail-closed policy. "
            "No row in this ledger authorizes training use. The review was model-assisted "
            "and deterministic; it is not an independent human row-by-row attestation."
        ),
        "",
        (
            "The source rows remain immutable and were not corrected in place. Their 20,000 "
            "planned slots are replaced by native verified rows while preserving the same "
            "aggregate subject and pedagogy margins when the SFT selection is materialized."
        ),
        "",
        "## Exact disposition",
        "",
        "| Source | Source-review approved | Source-review rejected | Final rejected | Replacement |",
        "|---|---:|---:|---:|---|",
    ]
    original_counts = manifest_basis["original_review_counts"]
    final_counts = manifest_basis["final_counts"]
    for source in SOURCE_ORDER:
        replacement = SOURCE_POLICY[source]["replacement_margin"]
        lines.append(
            "| "
            f"{source} | {original_counts.get(f'{source}::approved', 0):,} | "
            f"{original_counts.get(f'{source}::rejected', 0):,} | "
            f"{final_counts[f'{source}::rejected']:,} | "
            f"{replacement['row_count']:,} native verified "
            f"{replacement['subject_margin']} subject + "
            f"{replacement['pedagogy_margin']} pedagogy margins |"
        )
    lines.extend(
        [
            "",
            "## Capacity-safe joint-cell deltas",
            "",
            (
                "The one-row-per-canonical-task cap permits only 4,892 native "
                "integrated-science/concise rows. The balanced 260K native baseline is therefore "
                "expanded by these exact joint-cell deltas without weakening deduplication:"
            ),
            "",
            *[
                f"- `{cell}`: +{rows:,}"
                for cell, rows in REPLACEMENT_JOINT_CELL_DELTAS.items()
            ],
        ]
    )
    lines.extend(
        [
            "",
            "## Source-level basis",
            "",
        ]
    )
    for source in SOURCE_ORDER:
        policy = SOURCE_POLICY[source]
        lines.append(
            f"- `{source}` — `{policy['final_reason_code']}`: {policy['basis']}"
        )
    lines.extend(
        [
            "",
            "## Integrity",
            "",
            f"- Warehouse fingerprint: `{manifest_basis['warehouse_dataset_fingerprint_sha256']}`",
            f"- Final decisions SHA-256: `{decisions_hash}`",
            "- Exact review-pack coverage: 20,000 of 20,000 rows; no missing or extra IDs.",
            "- Every original source decision, check object, reason list, and note is embedded losslessly as a JSON object.",
            "- Every embedded original decision has its own canonical SHA-256 binding.",
            "- External record content is referenced by hash only and is never rewritten here.",
            "",
        ]
    )
    return "\n".join(lines)


def finalize_external_review(
    *,
    review_packs: Sequence[Path],
    decision_files: Sequence[Path],
    finalized_at: str,
    output: Path,
    expected_source_counts: Mapping[str, int] = EXPECTED_SOURCE_COUNTS,
) -> dict[str, Any]:
    """Create an atomic, deterministic, all-rejected final disposition ledger."""

    _validate_finalized_at(finalized_at)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite final review ledger: {output}")
    if not review_packs or not decision_files:
        raise ValueError("at least one review pack and one decision file are required")

    finalizer_source_metadata = _input_metadata(FINALIZER_PATH)
    finalizer_source_bytes = FINALIZER_PATH.read_bytes()
    if (
        len(finalizer_source_bytes) != finalizer_source_metadata["bytes"]
        or hashlib.sha256(finalizer_source_bytes).hexdigest()
        != finalizer_source_metadata["sha256"]
    ):
        raise RuntimeError("the finalizer source changed while it was being captured")

    input_paths = [*review_packs, *decision_files]
    before = _stable_input_metadata(input_paths)
    candidates, fingerprint = _load_candidates(review_packs)
    source_decisions = _load_decisions(decision_files)
    _assert_inputs_unchanged(before, input_paths)

    observed_source_counts = _validate_expected_counts(candidates, expected_source_counts)
    missing = sorted(set(candidates).difference(source_decisions))
    extra = sorted(set(source_decisions).difference(candidates))
    if missing or extra:
        raise ValueError(
            f"decision coverage mismatch: missing={len(missing):,}, extra={len(extra):,}; "
            f"first_missing={missing[:3]}, first_extra={extra[:3]}"
        )

    order = sorted(
        candidates,
        key=lambda record_id: (
            SOURCE_ORDER.index(candidates[record_id]["source_id"]),
            candidates[record_id]["selection_rank_sha256"],
            record_id,
        ),
    )
    final_decisions: list[dict[str, Any]] = []
    original_counts: Counter[str] = Counter()
    final_counts: Counter[str] = Counter()
    final_reason_counts: Counter[str] = Counter()
    for record_id in order:
        wrapper = candidates[record_id]
        source_decision = source_decisions[record_id]
        _validate_decision_binding(wrapper=wrapper, decision=source_decision)
        document = _final_decision(
            wrapper=wrapper,
            source_decision=source_decision,
            finalized_at=finalized_at,
        )
        final_decisions.append(document)
        source_id = wrapper["source_id"]
        original_counts[f"{source_id}::{source_decision['decision']}"] += 1
        final_counts[f"{source_id}::rejected"] += 1
        final_reason_counts[f"{source_id}::{SOURCE_POLICY[source_id]['final_reason_code']}"] += 1

    row_count = len(final_decisions)
    manifest_basis: dict[str, Any] = {
        "schema_version": 1,
        "artifact_name": "muta-external-20k-fail-closed-final-disposition",
        "policy_version": POLICY_VERSION,
        "warehouse_dataset_fingerprint_sha256": fingerprint,
        "trust_statement": (
            "user-authorized Codex model-assisted and deterministic audit finalization; "
            "not independent human row-by-row attestation"
        ),
        "finalizer": FINALIZER,
        "finalized_at": finalized_at,
        "row_count": row_count,
        "source_counts": observed_source_counts,
        "original_review_counts": dict(sorted(original_counts.items())),
        "final_counts": dict(sorted(final_counts.items())),
        "final_reason_counts": dict(sorted(final_reason_counts.items())),
        "coverage": {
            "review_pack_rows": len(candidates),
            "source_decision_rows": len(source_decisions),
            "final_decision_rows": row_count,
            "missing": 0,
            "extra": 0,
            "one_source_decision_per_row": True,
            "one_final_decision_per_row": True,
        },
        "authorization": {
            "external_rows_approved": 0,
            "external_rows_rejected": row_count,
            "all_external_rows_fail_closed": True,
            "ledger_authorizes_external_training_rows": False,
        },
        "immutability": {
            "external_records_edited": 0,
            "record_content_referenced_by_sha256": True,
            "original_source_review_embedded_without_field_mutation": True,
        },
        "replacement_margin_allocations": {
            source: SOURCE_POLICY[source]["replacement_margin"] for source in SOURCE_ORDER
        },
        "replacement_margin_rows": REPLACEMENT_MARGIN_ROWS,
        "replacement_joint_cell_deltas_from_balanced_260k_native_baseline": (
            REPLACEMENT_JOINT_CELL_DELTAS
        ),
        "source_policy": SOURCE_POLICY,
    }

    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="muta-final-review-", dir=output.parent) as state:
        partial = Path(state) / "ledger"
        partial.mkdir()
        decisions_path = partial / "final-decisions.jsonl"
        _write_jsonl(decisions_path, final_decisions)
        decisions_hash = sha256_file(decisions_path)
        report_path = partial / "REPORT.md"
        report_path.write_text(
            _render_report(manifest_basis, decisions_hash),
            encoding="utf-8",
        )

        provenance_directory = partial / "provenance"
        provenance_directory.mkdir()
        archived_finalizer_path = provenance_directory / FINALIZER_PATH.name
        archived_finalizer_path.write_bytes(finalizer_source_bytes)
        archived_finalizer_hash = sha256_file(archived_finalizer_path)
        if (
            archived_finalizer_path.stat().st_size != finalizer_source_metadata["bytes"]
            or archived_finalizer_hash != finalizer_source_metadata["sha256"]
        ):
            raise RuntimeError("the archived finalizer does not match the captured source")
        if _input_metadata(FINALIZER_PATH) != finalizer_source_metadata:
            raise RuntimeError("the finalizer source changed while the ledger was being compiled")

        review_count = len(review_packs)
        review_metadata = before[:review_count]
        decision_metadata = before[review_count:]
        manifest = {
            **manifest_basis,
            "inputs": {
                "finalizer": {
                    "path": archived_finalizer_path.relative_to(partial).as_posix(),
                    "source_path": finalizer_source_metadata["path"],
                    "bytes": finalizer_source_metadata["bytes"],
                    "sha256": finalizer_source_metadata["sha256"],
                },
                "review_packs": review_metadata,
                "source_decisions": decision_metadata,
            },
            "outputs": {
                "final_decisions": {
                    "path": decisions_path.name,
                    "bytes": decisions_path.stat().st_size,
                    "sha256": decisions_hash,
                },
                "report": {
                    "path": report_path.name,
                    "bytes": report_path.stat().st_size,
                    "sha256": sha256_file(report_path),
                },
            },
        }
        manifest_path = partial / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        partial.rename(output)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-pack", action="append", type=Path, required=True)
    parser.add_argument("--decision", action="append", type=Path, required=True)
    parser.add_argument("--finalized-at", required=True, help="ISO 8601 timestamp with timezone")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = finalize_external_review(
        review_packs=args.review_pack,
        decision_files=args.decision,
        finalized_at=args.finalized_at,
        output=args.output,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
