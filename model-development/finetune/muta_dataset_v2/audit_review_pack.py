"""Materialize the exact audit-gated external rows proposed for Muta SFT.

The output is a review artifact, never a training authorization.  Every row is
copied unchanged from a fully verified warehouse and is accompanied by the
content hash needed for a later approval or rejection receipt.  No decision is
created or inferred here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .core import load_source_registry, sha256_file
from .select_sft import (
    APPROVAL_SCHEMA_PATH,
    IMPORTED_APPROVAL_SCHEMA_SHA256,
    IMPORTED_SELECTOR_SHA256,
    TEMPLATE_SOURCE_ID,
    _canonical_json_bytes,
    _expanded_source_quotas,
    _load_selection_recipe,
    _rank,
    _safe_path,
    _verify_warehouse,
    record_content_sha256,
)

IMPORTED_MATERIALIZER_SHA256 = sha256_file(Path(__file__).resolve())
SELECTOR_PATH = Path(__file__).with_name("select_sft.py").resolve()
REVIEW_ROWS_NAME = "review-rows.jsonl"


def _audit_source_quotas(
    recipe: dict[str, Any], registry_path: Path
) -> tuple[dict[str, int], dict[str, dict[str, Any]]]:
    registry = load_source_registry(registry_path)
    quotas = _expanded_source_quotas(recipe)
    audit_quotas: dict[str, int] = {}
    audit_sources: dict[str, dict[str, Any]] = {}
    for source_id, quota in quotas.items():
        source = registry.get(source_id)
        if source is None:
            raise ValueError(f"recipe names an unknown source: {source_id}")
        if source.get("warehouse_training_eligible") is False:
            if not str(source.get("status", "")).startswith("enabled"):
                raise ValueError(f"audit source is not enabled: {source_id}")
            if source.get("sft_approval_scope") != "row_only":
                raise ValueError(f"audit source is not exact-row gated: {source_id}")
            audit_quotas[source_id] = quota
            audit_sources[source_id] = source
    if not audit_quotas:
        raise ValueError("recipe has no audit-gated external SFT allocation")
    return audit_quotas, audit_sources


def _create_candidate_table(database: sqlite3.Connection) -> None:
    database.executescript(
        """
        CREATE TABLE audit_candidates (
            record_id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            semantic_cluster_id TEXT NOT NULL,
            source_task_sha256 TEXT NOT NULL,
            rank_hex TEXT NOT NULL,
            shard_index INTEGER NOT NULL,
            line_index INTEGER NOT NULL,
            record_content_sha256 TEXT NOT NULL
        );
        CREATE INDEX audit_candidate_source_rank
            ON audit_candidates (source_id, rank_hex, record_id);
        CREATE INDEX audit_candidate_task_rank
            ON audit_candidates (source_task_sha256, rank_hex, record_id);
        """
    )


def _scan_candidates(
    *,
    verified: Any,
    source_quotas: dict[str, int],
    seed: int,
) -> dict[str, int]:
    database = verified.database
    _create_candidate_table(database)
    counts: Counter[str] = Counter()
    for shard_index, (shard_path, receipt) in enumerate(
        zip(verified.shard_paths, verified.shard_receipts, strict=True)
    ):
        digest = hashlib.sha256()
        byte_count = 0
        row_count = 0
        with shard_path.open("rb") as handle:
            for line_index, raw_line in enumerate(handle):
                digest.update(raw_line)
                byte_count += len(raw_line)
                row_count += 1
                record = json.loads(raw_line)
                source_id = record["provenance"]["source_id"]
                if source_id not in source_quotas:
                    continue
                counts[f"observed::{source_id}"] += 1
                if record["split"] != "train":
                    counts[f"excluded_non_train::{source_id}"] += 1
                    continue
                if record["verification"]["training_eligible"] is not False:
                    counts[f"excluded_not_audit_gated::{source_id}"] += 1
                    continue
                database.execute(
                    "INSERT INTO audit_candidates VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        record["id"],
                        source_id,
                        record["provenance"]["semantic_cluster_id"],
                        record["contamination"]["source_task_sha256"],
                        _rank(seed, record["id"]),
                        shard_index,
                        line_index,
                        record_content_sha256(record),
                    ),
                )
                counts[f"candidate::{source_id}"] += 1
        if digest.hexdigest() != receipt["sha256"]:
            raise RuntimeError(f"warehouse shard changed during audit scan: {shard_path}")
        if byte_count != receipt["bytes"] or row_count != receipt["rows"]:
            raise RuntimeError(f"warehouse shard shape changed during audit scan: {shard_path}")
    database.commit()
    return dict(sorted(counts.items()))


def _select_ids(
    *,
    database: sqlite3.Connection,
    source_quotas: dict[str, int],
    source_task_cap: int,
    template_cap: int,
    receipts: Sequence[dict[str, Any]],
) -> tuple[set[str], dict[str, int], dict[str, int], dict[str, Any]]:
    if source_task_cap <= 0 or template_cap <= 0:
        raise ValueError("review-pack caps must be positive")
    database.execute(
        """
        CREATE TABLE audit_decisions (
            record_id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            decision TEXT NOT NULL,
            receipt_id TEXT NOT NULL UNIQUE
        )
        """
    )
    decision_counts: Counter[str] = Counter()
    for receipt in receipts:
        if receipt["target_type"] != "record":
            raise ValueError("review-pack decisions must target exact records")
        source_id = receipt["source_id"]
        if source_id not in source_quotas:
            raise ValueError(f"decision receipt is outside the audit allocation: {source_id}")
        exists = database.execute(
            "SELECT 1 FROM audit_candidates WHERE record_id = ? AND source_id = ?",
            (receipt["record_id"], source_id),
        ).fetchone()
        if exists is None:
            raise ValueError(
                f"decision receipt does not bind an audit candidate: {receipt['receipt_id']}"
            )
        database.execute(
            "INSERT INTO audit_decisions VALUES (?, ?, ?, ?)",
            (
                receipt["record_id"],
                source_id,
                receipt["decision"],
                receipt["receipt_id"],
            ),
        )
        decision_counts[f"{receipt['decision']}::{source_id}"] += 1

    approved_counts = {
        source_id: database.execute(
            "SELECT COUNT(*) FROM audit_decisions WHERE source_id = ? AND decision = 'approved'",
            (source_id,),
        ).fetchone()[0]
        for source_id in source_quotas
    }
    for source_id, approved in approved_counts.items():
        if approved > source_quotas[source_id]:
            raise ValueError(
                f"approved decisions exceed the {source_id} quota: "
                f"{approved:,}/{source_quotas[source_id]:,}"
            )
    batch_quotas = {
        source_id: source_quotas[source_id] - approved_counts[source_id]
        for source_id in source_quotas
    }
    approved_task_overflow = database.execute(
        """
        SELECT c.source_task_sha256, COUNT(*)
        FROM audit_candidates c JOIN audit_decisions d USING (record_id)
        WHERE d.decision = 'approved'
        GROUP BY c.source_task_sha256 HAVING COUNT(*) > ? LIMIT 1
        """,
        (source_task_cap,),
    ).fetchone()
    if approved_task_overflow is not None:
        raise ValueError(
            "approved decision ledger exceeds the canonical source-task cap: "
            f"{approved_task_overflow[0]} ({approved_task_overflow[1]})"
        )
    approved_template_overflow = database.execute(
        """
        SELECT c.semantic_cluster_id, COUNT(*)
        FROM audit_candidates c JOIN audit_decisions d USING (record_id)
        WHERE d.decision = 'approved' AND c.source_id = ?
        GROUP BY c.semantic_cluster_id HAVING COUNT(*) > ? LIMIT 1
        """,
        (TEMPLATE_SOURCE_ID, template_cap),
    ).fetchone()
    if approved_template_overflow is not None:
        raise ValueError(
            "approved decision ledger exceeds the external-template cap: "
            f"{approved_template_overflow[0]} ({approved_template_overflow[1]})"
        )

    initial = database.execute("SELECT COUNT(*) FROM audit_candidates").fetchone()[0]
    decided = database.execute("SELECT COUNT(*) FROM audit_decisions").fetchone()[0]
    database.execute(
        """
        CREATE TABLE audit_task_capped AS
        WITH approved_tasks AS (
            SELECT c.source_task_sha256, COUNT(*) AS approved_count
            FROM audit_candidates c JOIN audit_decisions d USING (record_id)
            WHERE d.decision = 'approved'
            GROUP BY c.source_task_sha256
        ), ranked AS (
            SELECT c.*, COALESCE(a.approved_count, 0) AS approved_task_count,
                ROW_NUMBER() OVER (
                    PARTITION BY c.source_task_sha256 ORDER BY c.rank_hex, c.record_id
                ) AS task_position
            FROM audit_candidates c
            LEFT JOIN audit_decisions d USING (record_id)
            LEFT JOIN approved_tasks a USING (source_task_sha256)
            WHERE d.record_id IS NULL
        )
        SELECT * FROM ranked
        WHERE task_position <= ? - approved_task_count
        """,
        (source_task_cap,),
    )
    task_capped = database.execute("SELECT COUNT(*) FROM audit_task_capped").fetchone()[0]
    database.execute(
        """
        CREATE TABLE audit_capped AS
        WITH approved_clusters AS (
            SELECT c.source_id, c.semantic_cluster_id, COUNT(*) AS approved_count
            FROM audit_candidates c JOIN audit_decisions d USING (record_id)
            WHERE d.decision = 'approved'
            GROUP BY c.source_id, c.semantic_cluster_id
        ), ranked AS (
            SELECT c.*, COALESCE(a.approved_count, 0) AS approved_cluster_count,
                ROW_NUMBER() OVER (
                    PARTITION BY c.source_id, c.semantic_cluster_id
                    ORDER BY c.rank_hex, c.record_id
                ) AS cluster_position
            FROM audit_task_capped c
            LEFT JOIN approved_clusters a
              ON a.source_id = c.source_id
             AND a.semantic_cluster_id = c.semantic_cluster_id
        )
        SELECT * FROM ranked
        WHERE source_id != ? OR cluster_position <= ? - approved_cluster_count
        """,
        (TEMPLATE_SOURCE_ID, template_cap),
    )
    database.execute(
        "CREATE INDEX audit_capped_source_rank ON audit_capped (source_id, rank_hex, record_id)"
    )
    capped = database.execute("SELECT COUNT(*) FROM audit_capped").fetchone()[0]
    database.execute("CREATE TABLE audit_selected (record_id TEXT PRIMARY KEY) WITHOUT ROWID")
    for source_id, quota in sorted(batch_quotas.items()):
        rows = database.execute(
            """
            SELECT record_id FROM audit_capped
            WHERE source_id = ? ORDER BY rank_hex, record_id LIMIT ?
            """,
            (source_id, quota),
        ).fetchall()
        if len(rows) != quota:
            raise RuntimeError(
                f"audit review pack cannot fill {source_id}: {len(rows):,}/{quota:,}"
            )
        database.executemany("INSERT INTO audit_selected VALUES (?)", rows)
    database.commit()
    selected_ids = {row[0] for row in database.execute("SELECT record_id FROM audit_selected")}
    expected = sum(batch_quotas.values())
    if len(selected_ids) != expected:
        raise RuntimeError(f"audit selector chose {len(selected_ids):,}/{expected:,} rows")
    decision_summary = {
        "validated_receipts": len(receipts),
        "approved_by_source": dict(sorted(approved_counts.items())),
        "rejected_by_source": {
            source_id: decision_counts.get(f"rejected::{source_id}", 0)
            for source_id in sorted(source_quotas)
        },
        "decided_record_ids_sha256": hashlib.sha256(
            _canonical_json_bytes(sorted(receipt["record_id"] for receipt in receipts))
        ).hexdigest(),
        "decision_receipts_sha256": hashlib.sha256(
            _canonical_json_bytes(sorted(receipts, key=lambda receipt: receipt["receipt_id"]))
        ).hexdigest(),
    }
    return (
        selected_ids,
        batch_quotas,
        {
            "audit_candidates": initial,
            "excluded_by_decision_ledger": decided,
            "excluded_by_source_task_cap": initial - decided - task_capped,
            "excluded_by_external_template_cap": task_capped - capped,
            "capped_candidates": capped,
            "excluded_by_source_quota_rank": capped - expected,
        },
        decision_summary,
    )


def _write_review_rows(
    *,
    partial_output: Path,
    verified: Any,
    selected_ids: set[str],
    batch_quotas: dict[str, int],
    source_task_cap: int,
    template_cap: int,
) -> tuple[dict[str, Any], list[dict[str, str]], dict[str, Any]]:
    partial_path = partial_output / f"{REVIEW_ROWS_NAME}.partial"
    final_path = partial_output / REVIEW_ROWS_NAME
    output_digest = hashlib.sha256()
    counts: Counter[str] = Counter()
    task_counts: Counter[str] = Counter()
    template_counts: Counter[str] = Counter()
    bindings: list[dict[str, str]] = []
    seen: set[str] = set()
    byte_count = 0
    row_count = 0
    with partial_path.open("xb") as output_handle:
        for shard_path, receipt in zip(verified.shard_paths, verified.shard_receipts, strict=True):
            shard_digest = hashlib.sha256()
            shard_bytes = 0
            shard_rows = 0
            with shard_path.open("rb") as source_handle:
                for raw_line in source_handle:
                    shard_digest.update(raw_line)
                    shard_bytes += len(raw_line)
                    shard_rows += 1
                    record = json.loads(raw_line)
                    if record["id"] not in selected_ids:
                        continue
                    candidate = verified.database.execute(
                        """
                        SELECT source_id, rank_hex, record_content_sha256
                        FROM audit_capped WHERE record_id = ?
                        """,
                        (record["id"],),
                    ).fetchone()
                    if candidate is None:
                        raise RuntimeError(f"selected audit row vanished: {record['id']}")
                    source_id, rank_hex, expected_content_hash = candidate
                    observed_content_hash = record_content_sha256(record)
                    if observed_content_hash != expected_content_hash:
                        raise RuntimeError(f"selected audit row changed: {record['id']}")
                    if record["split"] != "train":
                        raise RuntimeError(f"review pack contains non-train row: {record['id']}")
                    if record["verification"]["training_eligible"] is not False:
                        raise RuntimeError(
                            f"review pack contains a natively eligible row: {record['id']}"
                        )
                    binding = {
                        "source_id": source_id,
                        "record_id": record["id"],
                        "record_content_sha256": observed_content_hash,
                    }
                    review_row = {
                        "schema_version": 1,
                        "warehouse_dataset_fingerprint_sha256": verified.manifest[
                            "dataset_fingerprint_sha256"
                        ],
                        **binding,
                        "selection_rank_sha256": rank_hex,
                        "semantic_cluster_id": record["provenance"]["semantic_cluster_id"],
                        "source_task_sha256": record["contamination"]["source_task_sha256"],
                        "record": record,
                    }
                    encoded = (
                        json.dumps(review_row, ensure_ascii=False, separators=(",", ":")) + "\n"
                    ).encode("utf-8")
                    output_handle.write(encoded)
                    output_digest.update(encoded)
                    byte_count += len(encoded)
                    row_count += 1
                    seen.add(record["id"])
                    bindings.append(binding)
                    counts[source_id] += 1
                    task_counts[record["contamination"]["source_task_sha256"]] += 1
                    if source_id == TEMPLATE_SOURCE_ID:
                        template_counts[record["provenance"]["semantic_cluster_id"]] += 1
            if shard_digest.hexdigest() != receipt["sha256"]:
                raise RuntimeError(
                    f"warehouse shard changed during review materialization: {shard_path}"
                )
            if shard_bytes != receipt["bytes"] or shard_rows != receipt["rows"]:
                raise RuntimeError(
                    f"warehouse shard shape changed during review materialization: {shard_path}"
                )
        output_handle.flush()
        os.fsync(output_handle.fileno())
    if seen != selected_ids:
        raise RuntimeError("not every selected audit row was materialized exactly once")
    observed_counts = {source_id: counts.get(source_id, 0) for source_id in sorted(batch_quotas)}
    if observed_counts != dict(sorted(batch_quotas.items())):
        raise RuntimeError("review-pack source counts differ from the refill batch quotas")
    observed_batch_task_cap = max(task_counts.values(), default=0)
    observed_batch_template_cap = max(template_counts.values(), default=0)
    observed_task_cap = verified.database.execute(
        """
        SELECT COALESCE(MAX(group_rows), 0) FROM (
            SELECT COUNT(*) AS group_rows
            FROM audit_candidates c
            LEFT JOIN audit_decisions d USING (record_id)
            LEFT JOIN audit_selected s USING (record_id)
            WHERE d.decision = 'approved' OR s.record_id IS NOT NULL
            GROUP BY c.source_task_sha256
        )
        """
    ).fetchone()[0]
    observed_template_cap = verified.database.execute(
        """
        SELECT COALESCE(MAX(group_rows), 0) FROM (
            SELECT COUNT(*) AS group_rows
            FROM audit_candidates c
            LEFT JOIN audit_decisions d USING (record_id)
            LEFT JOIN audit_selected s USING (record_id)
            WHERE c.source_id = ?
              AND (d.decision = 'approved' OR s.record_id IS NOT NULL)
            GROUP BY c.semantic_cluster_id
        )
        """,
        (TEMPLATE_SOURCE_ID,),
    ).fetchone()[0]
    if observed_task_cap > source_task_cap or observed_template_cap > template_cap:
        raise RuntimeError("materialized review rows exceed a selection cap")
    partial_path.replace(final_path)
    receipt = {
        "path": REVIEW_ROWS_NAME,
        "rows": row_count,
        "bytes": byte_count,
        "sha256": output_digest.hexdigest(),
    }
    if sha256_file(final_path) != receipt["sha256"]:
        raise RuntimeError("review JSONL changed after it was written")
    cap_report = {
        "max_rows_per_source_task": source_task_cap,
        "observed_batch_max_rows_per_source_task": observed_batch_task_cap,
        "observed_approved_plus_batch_max_rows_per_source_task": observed_task_cap,
        "template_source": TEMPLATE_SOURCE_ID,
        "max_rows_per_external_template": template_cap,
        "observed_batch_max_rows_per_external_template": observed_batch_template_cap,
        "observed_approved_plus_batch_max_rows_per_external_template": observed_template_cap,
    }
    return receipt, bindings, cap_report


def _archive_file(*, source: Path, output_root: Path, relative_path: str) -> dict[str, Any]:
    destination = _safe_path(output_root, relative_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    byte_count = 0
    with source.open("rb") as source_handle, destination.open("xb") as output_handle:
        for chunk in iter(lambda: source_handle.read(1024 * 1024), b""):
            output_handle.write(chunk)
            digest.update(chunk)
            byte_count += len(chunk)
        output_handle.flush()
        os.fsync(output_handle.fileno())
    return {
        "path": relative_path,
        "bytes": byte_count,
        "sha256": digest.hexdigest(),
    }


def _archive_decision_provenance(
    *,
    output_root: Path,
    decision_receipts: Sequence[Path],
    verified: Any,
) -> dict[str, Any]:
    receipt_inputs: list[dict[str, Any]] = []
    for source_receipt in sorted(verified.receipt_files, key=lambda item: item["sha256"]):
        source = Path(decision_receipts[source_receipt["input_index"]]).resolve()
        archived = _archive_file(
            source=source,
            output_root=output_root,
            relative_path=(
                f"provenance-decisions/receipt-inputs/{source_receipt['sha256']}.receipt-input"
            ),
        )
        if (
            archived["bytes"] != source_receipt["bytes"]
            or archived["sha256"] != source_receipt["sha256"]
        ):
            raise RuntimeError("decision receipt input changed after verification")
        receipt_inputs.append(
            {
                **archived,
                "input_index": source_receipt["input_index"],
                "original_name": source_receipt["name"],
                "receipts": source_receipt["receipts"],
            }
        )

    rubrics: list[dict[str, Any]] = []
    for rubric in sorted(verified.rubric_files, key=lambda item: item["sha256"]):
        archived = _archive_file(
            source=rubric["source_path"],
            output_root=output_root,
            relative_path=f"provenance-decisions/rubrics/{rubric['sha256']}.rubric",
        )
        if archived["bytes"] != rubric["bytes"] or archived["sha256"] != rubric["sha256"]:
            raise RuntimeError("decision rubric changed after verification")
        rubrics.append(
            {
                **archived,
                "input_index": rubric["input_index"],
                "original_name": rubric["name"],
            }
        )

    relative_ledger = "provenance-decisions/canonical-cumulative-ledger.jsonl"
    ledger_path = _safe_path(output_root, relative_ledger)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_digest = hashlib.sha256()
    ledger_bytes = 0
    with ledger_path.open("xb") as handle:
        for receipt in sorted(verified.receipts, key=lambda item: item["receipt_id"]):
            encoded = _canonical_json_bytes(receipt) + b"\n"
            handle.write(encoded)
            ledger_digest.update(encoded)
            ledger_bytes += len(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    canonical_ledger = {
        "path": relative_ledger,
        "rows": len(verified.receipts),
        "bytes": ledger_bytes,
        "sha256": ledger_digest.hexdigest(),
    }
    return {
        "canonical_ledger": canonical_ledger,
        "receipt_inputs": receipt_inputs,
        "rubrics": rubrics,
    }


def materialize_audit_review_pack(
    *,
    warehouse: Path,
    output: Path,
    decision_receipts: Sequence[Path] = (),
    rubric_files: Sequence[Path] = (),
    recipe_path: Path | None = None,
) -> dict[str, Any]:
    module_path = Path(__file__).resolve()
    if sha256_file(module_path) != IMPORTED_MATERIALIZER_SHA256:
        raise RuntimeError("loaded review-pack code differs from disk; restart the process")
    if sha256_file(SELECTOR_PATH) != IMPORTED_SELECTOR_SHA256:
        raise RuntimeError("loaded selector code differs from disk; restart the process")
    if sha256_file(APPROVAL_SCHEMA_PATH) != IMPORTED_APPROVAL_SCHEMA_SHA256:
        raise RuntimeError("loaded approval schema differs from disk; restart the process")
    warehouse = warehouse.resolve()
    output = output.resolve()
    partial_sentinel = output.with_name(output.name + ".partial")
    if output.exists() or partial_sentinel.exists():
        raise FileExistsError("refusing to overwrite a review pack or its partial directory")
    if output == warehouse or warehouse in output.parents or output in warehouse.parents:
        raise ValueError("warehouse and review-pack output directories must be disjoint")

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="muta-audit-review-", dir=output.parent) as state:
        partial_output = Path(state) / "review-pack.partial"
        verified = _verify_warehouse(
            warehouse=warehouse,
            receipt_paths=decision_receipts,
            rubric_paths=rubric_files,
            state_dir=Path(state),
        )
        try:
            archived_recipe_path = verified.archived_inputs["recipe"]
            registry_path = verified.archived_inputs["source_registry"]
            if (
                sha256_file(archived_recipe_path)
                != verified.manifest["inputs"]["recipe"]["sha256"]
            ):
                raise RuntimeError("archived warehouse recipe changed after verification")
            if (
                sha256_file(registry_path)
                != verified.manifest["inputs"]["source_registry"]["sha256"]
            ):
                raise RuntimeError("archived source registry changed after verification")
            recipe, selected_recipe_path, selection_recipe_binding = _load_selection_recipe(
                archived_recipe_path=archived_recipe_path,
                requested_recipe_path=recipe_path,
            )
            seed = int(recipe["seed"])
            if seed != verified.manifest["seed"]:
                raise ValueError("review seed differs from the warehouse seed")
            source_quotas, audit_sources = _audit_source_quotas(recipe, registry_path)
            source_task_cap = int(recipe["limits"]["max_rows_per_source_task_in_sft"])
            template_cap = int(recipe["limits"]["max_rows_per_external_template_in_sft"])
            scan_counts = _scan_candidates(
                verified=verified,
                source_quotas=source_quotas,
                seed=seed,
            )
            selected_ids, batch_quotas, exclusions, decision_summary = _select_ids(
                database=verified.database,
                source_quotas=source_quotas,
                source_task_cap=source_task_cap,
                template_cap=template_cap,
                receipts=verified.receipts,
            )

            partial_output.mkdir()
            review_rows, bindings, cap_report = _write_review_rows(
                partial_output=partial_output,
                verified=verified,
                selected_ids=selected_ids,
                batch_quotas=batch_quotas,
                source_task_cap=source_task_cap,
                template_cap=template_cap,
            )
            if sha256_file(module_path) != IMPORTED_MATERIALIZER_SHA256:
                raise RuntimeError("review-pack code changed during materialization")
            if sha256_file(SELECTOR_PATH) != IMPORTED_SELECTOR_SHA256:
                raise RuntimeError("selector code changed during materialization")
            if sha256_file(APPROVAL_SCHEMA_PATH) != IMPORTED_APPROVAL_SCHEMA_SHA256:
                raise RuntimeError("approval schema changed during materialization")
            archived_code = {
                "materializer": _archive_file(
                    source=module_path,
                    output_root=partial_output,
                    relative_path="provenance-code/audit_review_pack.py",
                ),
                "selector": _archive_file(
                    source=SELECTOR_PATH,
                    output_root=partial_output,
                    relative_path="provenance-code/select_sft.py",
                ),
                "approval_schema": _archive_file(
                    source=APPROVAL_SCHEMA_PATH,
                    output_root=partial_output,
                    relative_path="provenance-code/approval-receipt.schema.json",
                ),
                "warehouse_recipe": _archive_file(
                    source=archived_recipe_path,
                    output_root=partial_output,
                    relative_path="provenance-policy/warehouse-recipe.json",
                ),
                "selection_recipe": _archive_file(
                    source=selected_recipe_path,
                    output_root=partial_output,
                    relative_path="provenance-policy/selection-recipe.json",
                ),
            }
            if archived_code["materializer"]["sha256"] != IMPORTED_MATERIALIZER_SHA256:
                raise RuntimeError("archived review-pack code differs from loaded code")
            if archived_code["selector"]["sha256"] != IMPORTED_SELECTOR_SHA256:
                raise RuntimeError("archived selector code differs from loaded code")
            if archived_code["approval_schema"]["sha256"] != IMPORTED_APPROVAL_SCHEMA_SHA256:
                raise RuntimeError("archived approval schema differs from loaded schema")
            if archived_code["warehouse_recipe"]["sha256"] != selection_recipe_binding[
                "warehouse_recipe_sha256"
            ]:
                raise RuntimeError("archived warehouse recipe differs from the verified recipe")
            if archived_code["selection_recipe"]["sha256"] != selection_recipe_binding[
                "selection_recipe_sha256"
            ]:
                raise RuntimeError("archived selection recipe differs from the loaded recipe")
            archived_decisions = _archive_decision_provenance(
                output_root=partial_output,
                decision_receipts=decision_receipts,
                verified=verified,
            )
            binding_digest = hashlib.sha256(_canonical_json_bytes(bindings)).hexdigest()
            approval_schema = json.loads(APPROVAL_SCHEMA_PATH.read_text(encoding="utf-8"))
            ledger_binding = {
                "receipt_files": verified.receipt_files,
                "rubric_files": [
                    {
                        "input_index": rubric["input_index"],
                        "name": rubric["name"],
                        "bytes": rubric["bytes"],
                        "sha256": rubric["sha256"],
                    }
                    for rubric in verified.rubric_files
                ],
                **decision_summary,
            }
            batch_key_inputs = {
                "warehouse_dataset_fingerprint_sha256": verified.manifest[
                    "dataset_fingerprint_sha256"
                ],
                "seed": seed,
                "required_source_quotas": source_quotas,
                "batch_source_quotas": batch_quotas,
                "caps": {
                    "source_task": source_task_cap,
                    "template": template_cap,
                },
                "selection_recipe": selection_recipe_binding,
                "decision_ledger": {
                    "canonical_sha256": archived_decisions["canonical_ledger"]["sha256"],
                    "rubric_sha256": sorted(
                        rubric["sha256"] for rubric in archived_decisions["rubrics"]
                    ),
                },
                "materializer_sha256": IMPORTED_MATERIALIZER_SHA256,
                "selector_sha256": IMPORTED_SELECTOR_SHA256,
                "approval_schema_sha256": IMPORTED_APPROVAL_SCHEMA_SHA256,
            }
            batch_key = hashlib.sha256(_canonical_json_bytes(batch_key_inputs)).hexdigest()
            manifest = {
                "schema_version": 1,
                "artifact_name": "muta-stem-sft-v2-exact-row-audit-review-pack",
                "row_count": len(bindings),
                "seed": seed,
                "source_warehouse": {
                    "dataset_fingerprint_sha256": verified.manifest["dataset_fingerprint_sha256"],
                    "manifest_sha256": verified.manifest_sha256,
                    "row_count": verified.manifest["row_count"],
                    "shards_verified_twice": True,
                    "rows_revalidated_against_archived_schema_and_registry": True,
                },
                "selection": {
                    "rank": "lowest SHA-256(recipe_seed:record_id) within each source quota",
                    "split": "train only",
                    "eligibility": "verification.training_eligible=false only",
                    "source_quotas": dict(sorted(source_quotas.items())),
                    "recipe_binding": selection_recipe_binding,
                    "caps": cap_report,
                },
                "batch": {
                    "key_sha256": batch_key,
                    "key_inputs": batch_key_inputs,
                    "source_quotas": dict(sorted(batch_quotas.items())),
                    "row_count": sum(batch_quotas.values()),
                    "mode": "deterministic content-addressed decision-ledger refill",
                    "semantics": (
                        "approved rows count toward quotas and consume caps; rejected rows are "
                        "excluded before caps are reapplied; each batch contains the lowest-ranked "
                        "undecided rows that could still be approved; undecided rows repeat"
                    ),
                },
                "counts": {"source": dict(sorted(batch_quotas.items()))},
                "candidate_scan_counts": scan_counts,
                "candidate_exclusions": exclusions,
                "decision_ledger": {
                    **ledger_binding,
                    "archive": archived_decisions,
                    "rejections_authorize_training": False,
                    "scope": "caller-supplied cumulative ledger; completeness is not inferred",
                    "omitted_decisions_may_reemit_rows": True,
                },
                "review_state": {
                    "new_decisions_emitted": False,
                    "prior_validated_approvals": sum(
                        decision_summary["approved_by_source"].values()
                    ),
                    "prior_validated_rejections": sum(
                        decision_summary["rejected_by_source"].values()
                    ),
                    "authorizes_training": False,
                    "required_next_step": (
                        "issue separate schema-valid approval or rejection receipts for each "
                        "exact record after documented rubric-based review, accurately labeling "
                        "whether the method was human or model-assisted"
                    ),
                },
                "approval_receipt_schema": {
                    "id": approval_schema["$id"],
                    "sha256": IMPORTED_APPROVAL_SCHEMA_SHA256,
                },
                "inputs": {
                    "archived_recipe_sha256": verified.manifest["inputs"]["recipe"]["sha256"],
                    "archived_source_registry_sha256": verified.manifest["inputs"][
                        "source_registry"
                    ]["sha256"],
                    "materializer_sha256": IMPORTED_MATERIALIZER_SHA256,
                    "selector_sha256": IMPORTED_SELECTOR_SHA256,
                    "warehouse_recipe": archived_code["warehouse_recipe"],
                    "selection_recipe": archived_code["selection_recipe"],
                    "archived_executable_inputs": archived_code,
                    "audit_sources": {
                        source_id: {
                            "revision": source["revision"],
                            "license": source["license"],
                            "sft_approval_scope": source["sft_approval_scope"],
                        }
                        for source_id, source in sorted(audit_sources.items())
                    },
                },
                "review_rows": review_rows,
                "row_binding_inventory_sha256": binding_digest,
                "row_bindings": bindings,
            }
            manifest_partial = partial_output / "manifest.json.partial"
            with manifest_partial.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            manifest_partial.replace(partial_output / "manifest.json")
            directory_fd = os.open(partial_output, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            partial_output.replace(output)
            parent_fd = os.open(output.parent, os.O_RDONLY)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
            return manifest
        finally:
            verified.database.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warehouse", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--decision-receipt",
        action="append",
        default=[],
        type=Path,
        help="schema-valid JSON or JSONL approval/rejection ledger (repeatable)",
    )
    parser.add_argument(
        "--rubric",
        action="append",
        default=[],
        type=Path,
        help="rubric artifact bound by decision receipts (repeatable)",
    )
    parser.add_argument(
        "--recipe",
        type=Path,
        help=(
            "optional SFT allocation override; only documented recommended-allocation and "
            "training-note fields may differ from the warehouse recipe"
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = materialize_audit_review_pack(
        warehouse=args.warehouse,
        output=args.output,
        decision_receipts=args.decision_receipt,
        rubric_files=args.rubric,
        recipe_path=args.recipe,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
