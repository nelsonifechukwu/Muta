"""Select a deterministic, quota-balanced SFT view from a verified warehouse.

The warehouse remains immutable.  Native training-eligible rows may enter the
view directly; every other row needs a content-addressed exact-record receipt
whose decision is approved for that warehouse fingerprint and row.  Rejected
receipts remain evidence and never authorize selection.  Optional cluster
receipts are attestations only and never blanket-authorize their member rows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .core import (
    load_source_registry,
    normalized_sha256,
    sha256_file,
    validate_record,
)

PACKAGE_DIR = Path(__file__).resolve().parent
APPROVAL_SCHEMA_PATH = PACKAGE_DIR / "approval-receipt.schema.json"
LOCAL_SOURCE_ID = "muta_verified_stem_v2"
TEMPLATE_SOURCE_ID = "template_gsm"
SELECTION_RECIPE_OVERRIDE_FIELDS = frozenset(
    {
        "recommended_sft_allocations",
        "recommended_sft_allocation_decision",
        "recommended_sft_local_cell_quotas",
        "training_note",
    }
)
IMPORTED_SELECTOR_SHA256 = sha256_file(Path(__file__).resolve())
IMPORTED_APPROVAL_SCHEMA_SHA256 = sha256_file(APPROVAL_SCHEMA_PATH)


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def record_content_sha256(record: dict[str, Any]) -> str:
    """Hash every serialized record field using one canonical representation."""

    return hashlib.sha256(_canonical_json_bytes(record)).hexdigest()


def _new_cluster_hasher(source_id: str, semantic_cluster_id: str) -> Any:
    digest = hashlib.sha256()
    digest.update(b"muta-semantic-cluster-content-v1\0")
    digest.update(source_id.encode("utf-8"))
    digest.update(b"\0")
    digest.update(semantic_cluster_id.encode("utf-8"))
    digest.update(b"\0")
    return digest


def _update_cluster_hasher(digest: Any, record: dict[str, Any], content_hash: str) -> None:
    digest.update(record["id"].encode("utf-8"))
    digest.update(b"\0")
    digest.update(bytes.fromhex(content_hash))
    digest.update(b"\n")


def semantic_cluster_content_sha256(
    records: Iterable[dict[str, Any]], *, source_id: str, semantic_cluster_id: str
) -> str:
    """Hash a cluster in warehouse order for a cluster-scoped approval receipt."""

    digest = _new_cluster_hasher(source_id, semantic_cluster_id)
    seen = 0
    for record in records:
        provenance = record.get("provenance") or {}
        if provenance.get("source_id") != source_id:
            raise ValueError("cluster digest received a row from a different source")
        if provenance.get("semantic_cluster_id") != semantic_cluster_id:
            raise ValueError("cluster digest received a row from a different semantic cluster")
        _update_cluster_hasher(digest, record, record_content_sha256(record))
        seen += 1
    if not seen:
        raise ValueError("cannot hash an empty semantic cluster")
    return digest.hexdigest()


def approval_receipt_id(receipt: dict[str, Any]) -> str:
    """Return the content-derived ID for a receipt (excluding its ID field)."""

    payload = {key: value for key, value in receipt.items() if key != "receipt_id"}
    return "muta_approval_v1_" + hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()[:24]


def _rank(seed: int, record_id: str) -> str:
    return hashlib.sha256(f"{seed}:{record_id}".encode()).hexdigest()


def _safe_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError("manifest contains an empty or non-string path")
    root = root.resolve()
    path = (root / relative).resolve()
    if path == root or root not in path.parents:
        raise ValueError(f"manifest path escapes the warehouse: {relative!r}")
    return path


def _verify_receipt_file(root: Path, receipt: dict[str, Any], *, path_key: str) -> Path:
    path = _safe_path(root, receipt[path_key])
    if not path.is_file():
        raise FileNotFoundError(f"receipted warehouse input is missing: {path}")
    if path.stat().st_size != receipt["bytes"]:
        raise ValueError(f"receipted warehouse input byte count mismatch: {path}")
    if sha256_file(path) != receipt["sha256"]:
        raise ValueError(f"receipted warehouse input hash mismatch: {path}")
    return path


def _verify_archived_inputs(warehouse: Path, manifest: dict[str, Any]) -> dict[str, Path]:
    inputs = manifest.get("inputs")
    if not isinstance(inputs, dict):
        raise TypeError("warehouse manifest has no provenance inputs")
    resolved: dict[str, Path] = {}
    for key in (
        "recipe",
        "schema",
        "source_registry",
        "requirements",
        "requirements_lock",
        "muta_license",
    ):
        receipt = inputs.get(key)
        if not isinstance(receipt, dict):
            raise TypeError(f"warehouse manifest omits the {key} receipt")
        resolved[key] = _verify_receipt_file(warehouse, receipt, path_key="archive_path")
    for receipt in inputs.get("code") or ():
        _verify_receipt_file(warehouse, receipt, path_key="archive_path")
    for archive_key in (
        "provenance_archive",
        "holdout_source_archive",
        "source_evidence_archive",
    ):
        archive = inputs.get(archive_key)
        if not isinstance(archive, dict):
            raise TypeError(f"warehouse manifest omits {archive_key}")
        receipt_path = _verify_receipt_file(warehouse, archive["receipts"], path_key="path")
        receipt_document = json.loads(receipt_path.read_text(encoding="utf-8"))
        archived_files = archive.get("files") or []
        if receipt_document.get("files") != archived_files:
            raise ValueError(f"{archive_key} receipt inventory does not match the manifest")
        for receipt in archived_files:
            _verify_receipt_file(warehouse, receipt, path_key="path")
    return resolved


_WAREHOUSE_PROVENANCE_ARCHIVES = {
    "provenance_archive": "provenance-code",
    "holdout_source_archive": "provenance-holdouts",
    "source_evidence_archive": "provenance-source-evidence",
}


def _copy_warehouse_provenance_archives(
    *, warehouse: Path, destination_root: Path, manifest: dict[str, Any]
) -> dict[str, Any]:
    """Copy the manifest's receipted provenance tree beside its copied manifest."""

    inputs = manifest["inputs"]
    copied_archives: dict[str, Any] = {}
    copied_warehouse_paths: set[str] = set()

    def copy_receipted_file(receipt: dict[str, Any]) -> dict[str, Any]:
        relative = receipt["path"]
        source = _verify_receipt_file(warehouse, receipt, path_key="path")
        before_size = source.stat().st_size
        before_hash = sha256_file(source)
        destination = _safe_path(destination_root, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise FileExistsError(f"duplicate copied warehouse provenance path: {relative}")
        shutil.copyfile(source, destination)
        if source.stat().st_size != before_size or sha256_file(source) != before_hash:
            raise RuntimeError(f"warehouse provenance input drifted while copied: {source}")
        if destination.stat().st_size != receipt["bytes"]:
            raise RuntimeError(f"copied warehouse provenance byte count mismatch: {destination}")
        if sha256_file(destination) != receipt["sha256"]:
            raise RuntimeError(f"copied warehouse provenance hash mismatch: {destination}")
        copied_warehouse_paths.add(relative)
        result = {
            "path": destination.relative_to(destination_root.parent).as_posix(),
            "warehouse_relative_path": relative,
            "bytes": receipt["bytes"],
            "sha256": receipt["sha256"],
        }
        for key in ("source_id", "revision", "locator", "sealed_evaluation_input"):
            if key in receipt:
                result[key] = receipt[key]
        return result

    for archive_key, expected_directory in _WAREHOUSE_PROVENANCE_ARCHIVES.items():
        archive = inputs.get(archive_key)
        if not isinstance(archive, dict):
            raise TypeError(f"warehouse manifest omits {archive_key}")
        if archive.get("directory") != expected_directory:
            raise ValueError(f"warehouse {archive_key} directory must be {expected_directory!r}")
        files = archive.get("files")
        if not isinstance(files, list):
            raise TypeError(f"warehouse {archive_key} has no file inventory")
        paths = [receipt.get("path") for receipt in files]
        receipts_receipt = archive.get("receipts")
        if not isinstance(receipts_receipt, dict):
            raise TypeError(f"warehouse {archive_key} has no receipts.json receipt")
        receipts_path = receipts_receipt.get("path")
        all_paths = [*paths, receipts_path]
        if any(
            not isinstance(path, str) or not path.startswith(expected_directory + "/")
            for path in all_paths
        ):
            raise ValueError(f"warehouse {archive_key} contains a path outside its directory")
        if len(all_paths) != len(set(all_paths)):
            raise ValueError(f"warehouse {archive_key} repeats a receipted path")

        source_receipts_path = _verify_receipt_file(warehouse, receipts_receipt, path_key="path")
        receipt_document = json.loads(source_receipts_path.read_text(encoding="utf-8"))
        if receipt_document.get("files") != files:
            raise ValueError(f"warehouse {archive_key} receipts.json inventory drifted")

        copied_files = [copy_receipted_file(receipt) for receipt in files]
        copied_receipts = copy_receipted_file(receipts_receipt)
        copied_directory = destination_root / expected_directory
        discovered = {
            path.relative_to(destination_root).as_posix()
            for path in copied_directory.rglob("*")
            if path.is_file()
        }
        if discovered != set(all_paths):
            raise RuntimeError(f"copied {archive_key} file coverage differs from its receipts")
        copied_archives[archive_key] = {
            "directory": copied_directory.relative_to(destination_root.parent).as_posix(),
            "warehouse_relative_directory": expected_directory,
            "file_count": len(copied_files),
            "files": copied_files,
            "receipts": copied_receipts,
        }

    required_paths = {
        inputs[key]["archive_path"]
        for key in (
            "recipe",
            "schema",
            "source_registry",
            "requirements",
            "requirements_lock",
            "muta_license",
        )
    }
    required_paths.update(receipt["archive_path"] for receipt in inputs.get("code") or ())
    missing = sorted(required_paths.difference(copied_warehouse_paths))
    if missing:
        raise ValueError(
            "copied warehouse provenance omits paths referenced by its manifest: "
            + ", ".join(missing)
        )
    inventory_hash = hashlib.sha256(_canonical_json_bytes(copied_archives)).hexdigest()
    return {
        "resolution_root": destination_root.relative_to(destination_root.parent).as_posix(),
        "copied_manifest_paths_resolve_from_this_root": True,
        "copy_policy": "only manifest-receipted files plus each receipts.json",
        "archive_count": len(copied_archives),
        "inventory_sha256": inventory_hash,
        "archives": copied_archives,
    }


def _assert_live_validators_match_warehouse(manifest: dict[str, Any]) -> None:
    """Refuse to reinterpret warehouse rows with different executable validators."""

    expected = {
        receipt.get("path"): receipt.get("sha256")
        for receipt in (manifest.get("inputs") or {}).get("code", ())
        if isinstance(receipt, dict)
    }
    for name in ("core.py", "generators.py", "tokenization.py"):
        expected_hash = expected.get(name)
        if not isinstance(expected_hash, str):
            raise TypeError(f"warehouse omits archived validator receipt for {name}")
        if sha256_file(PACKAGE_DIR / name) != expected_hash:
            raise ValueError(
                f"live validator {name} differs from the warehouse artifact; "
                "run selection from the artifact's archived code environment"
            )


def _load_receipt_documents(
    paths: Sequence[Path],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    schema = json.loads(APPROVAL_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    receipts: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    for input_index, path in enumerate(paths):
        resolved = path.resolve()
        raw = resolved.read_text(encoding="utf-8")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = [json.loads(line) for line in raw.splitlines() if line.strip()]
        documents = parsed if isinstance(parsed, list) else [parsed]
        if not documents:
            raise ValueError(f"approval receipt file is empty: {resolved}")
        for index, receipt in enumerate(documents):
            errors = sorted(validator.iter_errors(receipt), key=lambda error: list(error.path))
            if errors:
                detail = "; ".join(error.message for error in errors)
                raise ValueError(f"malformed approval receipt {resolved} item {index}: {detail}")
            if receipt["receipt_id"] != approval_receipt_id(receipt):
                raise ValueError(
                    f"approval receipt {receipt['receipt_id']} is not content-addressed correctly"
                )
            if (
                not receipt["reviewer"].strip()
                or not receipt["review_method"].strip()
                or not receipt["rubric_version"].strip()
            ):
                raise ValueError(
                    f"approval receipt {receipt['receipt_id']} has a blank reviewer, "
                    "review method, or rubric version"
                )
            receipts.append(receipt)
        files.append(
            {
                "input_index": input_index,
                "name": resolved.name,
                "bytes": resolved.stat().st_size,
                "sha256": sha256_file(resolved),
                "receipts": len(documents),
            }
        )
    receipt_ids = [receipt["receipt_id"] for receipt in receipts]
    if len(receipt_ids) != len(set(receipt_ids)):
        raise ValueError("approval receipt IDs must be unique")
    targets = [_receipt_target_key(receipt) for receipt in receipts]
    if len(targets) != len(set(targets)):
        raise ValueError("only one approval receipt may bind a row or semantic-cluster target")
    return receipts, files


def _receipt_target_key(receipt: dict[str, Any]) -> tuple[str, str, str]:
    if receipt["target_type"] == "record":
        return ("record", receipt["source_id"], receipt["record_id"])
    return ("semantic_cluster", receipt["source_id"], receipt["semantic_cluster_id"])


def _apportion(total: int, weights: dict[str, Any]) -> dict[str, int]:
    positive = {str(key): float(value) for key, value in weights.items() if float(value) > 0}
    if total < 0 or not positive:
        raise ValueError("quota total and target weights must be positive")
    scale = sum(positive.values())
    exact = {key: total * value / scale for key, value in positive.items()}
    quotas = {key: int(value) for key, value in exact.items()}
    remainder = total - sum(quotas.values())
    order = sorted(positive, key=lambda key: (-(exact[key] - quotas[key]), key))
    for key in order[:remainder]:
        quotas[key] += 1
    return quotas


def _expanded_source_quotas(recipe: dict[str, Any]) -> dict[str, int]:
    allocations = recipe.get("recommended_sft_allocations")
    target = recipe.get("recommended_sft_target_rows")
    if not isinstance(allocations, dict) or not isinstance(target, int) or target <= 0:
        raise ValueError("recipe has invalid recommended SFT allocations")
    supported = {
        LOCAL_SOURCE_ID,
        "deepmind_mathematics",
        TEMPLATE_SOURCE_ID,
        "qasc",
        "gsm8k",
        "licensed_anchors",
    }
    unknown = sorted(set(allocations).difference(supported))
    if unknown:
        raise ValueError(f"selector does not have a fail-closed expansion for {unknown!r}")
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value < 0
        for value in allocations.values()
    ):
        raise ValueError("recommended source allocations must be non-negative integers")
    if sum(allocations.values()) != target:
        raise ValueError("recommended source allocations do not sum to the SFT target")
    explicit_anchors = int(allocations.get("qasc", 0)) + int(allocations.get("gsm8k", 0))
    anchors = int(allocations.get("licensed_anchors", 0))
    if anchors and explicit_anchors:
        raise ValueError(
            "recommended allocations cannot mix licensed_anchors with explicit qasc/gsm8k"
        )
    quotas = {
        source: int(allocations.get(source, 0))
        for source in (
            LOCAL_SOURCE_ID,
            "deepmind_mathematics",
            TEMPLATE_SOURCE_ID,
            "qasc",
            "gsm8k",
        )
    }
    if anchors:
        quotas["qasc"] = anchors // 2 + anchors % 2
        quotas["gsm8k"] = anchors // 2
    return {source: quota for source, quota in quotas.items() if quota > 0}


def _load_selection_recipe(
    *, archived_recipe_path: Path, requested_recipe_path: Path | None
) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    """Load an SFT-only recipe override without reinterpreting warehouse construction.

    The warehouse rows do not depend on the recommended SFT allocation.  A later
    quality audit may therefore reduce or replace source allocations, but no seed,
    warehouse allocation, target margin, cap, or generation setting may drift.
    """

    archived_recipe_path = archived_recipe_path.resolve()
    selected_path = (requested_recipe_path or archived_recipe_path).resolve()
    archived_bytes = archived_recipe_path.read_bytes()
    selected_bytes = (
        archived_bytes if selected_path == archived_recipe_path else selected_path.read_bytes()
    )
    archived_hash = hashlib.sha256(archived_bytes).hexdigest()
    selected_hash = hashlib.sha256(selected_bytes).hexdigest()
    archived = json.loads(archived_bytes)
    selected = json.loads(selected_bytes)
    if selected_hash == archived_hash:
        mode = "warehouse_archived_recipe"
        changed_fields: list[str] = []
    else:
        archived_fixed = {
            key: value
            for key, value in archived.items()
            if key not in SELECTION_RECIPE_OVERRIDE_FIELDS
        }
        selected_fixed = {
            key: value
            for key, value in selected.items()
            if key not in SELECTION_RECIPE_OVERRIDE_FIELDS
        }
        if selected_fixed != archived_fixed:
            changed = sorted(
                key
                for key in set(archived_fixed) | set(selected_fixed)
                if archived_fixed.get(key) != selected_fixed.get(key)
            )
            raise ValueError(
                "selection recipe changes warehouse or target invariants: " + ", ".join(changed)
            )
        decision = selected.get("recommended_sft_allocation_decision")
        if not isinstance(decision, dict) or not str(decision.get("reason", "")).strip():
            raise ValueError("selection allocation override requires a documented decision reason")
        mode = "post_warehouse_quality_allocation_override"
        changed_fields = sorted(
            key
            for key in SELECTION_RECIPE_OVERRIDE_FIELDS
            if archived.get(key) != selected.get(key)
        )
    _expanded_source_quotas(selected)
    return selected, selected_path, {
        "mode": mode,
        "warehouse_recipe_sha256": archived_hash,
        "selection_recipe_sha256": selected_hash,
        "changed_fields": changed_fields,
        "warehouse_construction_reinterpreted": False,
        "subject_targets_changed": False,
        "pedagogy_targets_changed": False,
    }


class _Dinic:
    def __init__(self, size: int) -> None:
        self.graph: list[list[list[int]]] = [[] for _ in range(size)]

    def add(self, source: int, target: int, capacity: int) -> list[int]:
        forward = [target, len(self.graph[target]), capacity, capacity]
        reverse = [source, len(self.graph[source]), 0, 0]
        self.graph[source].append(forward)
        self.graph[target].append(reverse)
        return forward

    def _send(
        self,
        node: int,
        sink: int,
        amount: int,
        levels: list[int],
        positions: list[int],
    ) -> int:
        if node == sink:
            return amount
        while positions[node] < len(self.graph[node]):
            edge = self.graph[node][positions[node]]
            if edge[2] and levels[edge[0]] == levels[node] + 1:
                sent = self._send(edge[0], sink, min(amount, edge[2]), levels, positions)
                if sent:
                    edge[2] -= sent
                    self.graph[edge[0]][edge[1]][2] += sent
                    return sent
            positions[node] += 1
        return 0

    def flow(self, source: int, sink: int) -> int:
        total = 0
        while True:
            levels = [-1] * len(self.graph)
            levels[source] = 0
            queue = [source]
            for node in queue:
                for edge in self.graph[node]:
                    if edge[2] and levels[edge[0]] < 0:
                        levels[edge[0]] = levels[node] + 1
                        queue.append(edge[0])
            if levels[sink] < 0:
                return total
            positions = [0] * len(self.graph)
            while True:
                sent = self._send(source, sink, 10**18, levels, positions)
                if not sent:
                    break
                total += sent


def _local_transport(
    subject_quotas: dict[str, int],
    pedagogy_quotas: dict[str, int],
    availability: dict[tuple[str, str], int],
) -> dict[tuple[str, str], int]:
    if sum(subject_quotas.values()) != sum(pedagogy_quotas.values()):
        raise ValueError("residual local subject and pedagogy margins disagree")
    subjects = sorted(subject_quotas)
    pedagogies = sorted(pedagogy_quotas)
    source = 0
    subject_offset = 1
    pedagogy_offset = subject_offset + len(subjects)
    sink = pedagogy_offset + len(pedagogies)
    network = _Dinic(sink + 1)
    for index, subject in enumerate(subjects):
        network.add(source, subject_offset + index, subject_quotas[subject])
    tracked: dict[tuple[str, str], list[int]] = {}
    for subject_index, subject in enumerate(subjects):
        for pedagogy_index, pedagogy in enumerate(pedagogies):
            capacity = availability.get((subject, pedagogy), 0)
            if capacity:
                tracked[(subject, pedagogy)] = network.add(
                    subject_offset + subject_index,
                    pedagogy_offset + pedagogy_index,
                    capacity,
                )
    for index, pedagogy in enumerate(pedagogies):
        network.add(pedagogy_offset + index, sink, pedagogy_quotas[pedagogy])
    required = sum(subject_quotas.values())
    observed = network.flow(source, sink)
    if observed != required:
        raise RuntimeError(
            f"local rows cannot satisfy exact subject/pedagogy margins: {observed:,}/{required:,}"
        )
    return {key: edge[3] - edge[2] for key, edge in tracked.items() if edge[3] - edge[2] > 0}


def _formula_template_method_key(record: dict[str, Any]) -> str:
    verification = record.get("verification") or {}
    formula_id = str(verification.get("formula_id", "")).strip()
    if formula_id:
        return f"formula:{formula_id}"
    template_id = str(verification.get("template_id", "")).strip()
    if template_id:
        return f"template:{template_id}"
    method = str(verification.get("method", "")).strip() or "unspecified"
    if record.get("provenance", {}).get("source_id") == LOCAL_SOURCE_ID:
        return f"formula:{method}"
    return f"method:{method}"


def _token_bucket(count: int) -> str:
    if count <= 128:
        return "0001-0128"
    if count <= 256:
        return "0129-0256"
    if count <= 512:
        return "0257-0512"
    if count <= 768:
        return "0513-0768"
    return "0769-plus"


@dataclass
class _VerifiedWarehouse:
    manifest: dict[str, Any]
    manifest_path: Path
    manifest_sha256: str
    shard_paths: list[Path]
    shard_receipts: list[dict[str, Any]]
    archived_inputs: dict[str, Path]
    receipts: list[dict[str, Any]]
    receipt_files: list[dict[str, Any]]
    rubric_files: list[dict[str, Any]]
    database: sqlite3.Connection
    database_path: Path
    actual_counts: dict[str, Counter[str]]


def _check_manifest_counter(manifest: dict[str, Any], actual: Counter[str], key: str) -> None:
    expected = (manifest.get("counts") or {}).get(key)
    if expected is None:
        raise ValueError(f"warehouse manifest omits counts.{key}")
    if dict(sorted(actual.items())) != expected:
        raise ValueError(f"warehouse manifest counts.{key} does not match its rows")


def _verify_warehouse(
    *,
    warehouse: Path,
    receipt_paths: Sequence[Path],
    rubric_paths: Sequence[Path],
    state_dir: Path,
) -> _VerifiedWarehouse:
    warehouse = warehouse.resolve()
    if (warehouse / "FAILED.json").exists():
        raise ValueError("warehouse has a failure marker")
    partials = sorted(
        path.relative_to(warehouse).as_posix() for path in warehouse.rglob("*.partial")
    )
    if partials:
        raise ValueError(f"warehouse contains partial artifacts: {partials}")
    manifest_path = warehouse / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    manifest = json.loads(manifest_bytes)
    if manifest.get("profile") != "warehouse":
        raise ValueError("SFT selection requires a finalized warehouse-profile build")
    if (manifest.get("tokenization") or {}).get("status") != "exact":
        raise ValueError("SFT selection requires exact warehouse token accounting")
    archived_inputs = _verify_archived_inputs(warehouse, manifest)
    _assert_live_validators_match_warehouse(manifest)
    archived_recipe = json.loads(archived_inputs["recipe"].read_text(encoding="utf-8"))
    if manifest.get("seed") != archived_recipe.get("seed"):
        raise ValueError("warehouse seed does not match its archived recipe seed")
    receipts, receipt_files = _load_receipt_documents(receipt_paths)
    rubric_files: list[dict[str, Any]] = []
    rubric_hashes: set[str] = set()
    for input_index, rubric_path in enumerate(rubric_paths):
        resolved = rubric_path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"approval rubric artifact is missing: {resolved}")
        digest = sha256_file(resolved)
        if digest in rubric_hashes:
            raise ValueError("approval rubric artifacts must have unique content hashes")
        rubric_hashes.add(digest)
        rubric_files.append(
            {
                "input_index": input_index,
                "name": resolved.name,
                "source_path": resolved,
                "bytes": resolved.stat().st_size,
                "sha256": digest,
            }
        )
    referenced_rubrics = {receipt["rubric_sha256"] for receipt in receipts}
    missing_rubrics = sorted(referenced_rubrics.difference(rubric_hashes))
    if missing_rubrics:
        raise ValueError(
            "approval receipt references no supplied rubric artifact: " + ", ".join(missing_rubrics)
        )
    unused_rubrics = sorted(rubric_hashes.difference(referenced_rubrics))
    if unused_rubrics:
        raise ValueError("supplied approval rubric artifact is not referenced by any receipt")

    shard_receipts = manifest.get("shards")
    if not isinstance(shard_receipts, list) or not shard_receipts:
        raise ValueError("warehouse manifest has no shards")
    relative_paths = [receipt.get("path") for receipt in shard_receipts]
    if len(relative_paths) != len(set(relative_paths)):
        raise ValueError("warehouse manifest repeats a shard path")
    discovered = {
        path.relative_to(warehouse).as_posix()
        for path in warehouse.rglob("part-*.jsonl")
        if path.is_file()
    }
    if discovered != set(relative_paths):
        raise ValueError("warehouse part-file coverage differs from its manifest")

    schema = json.loads(archived_inputs["schema"].read_text(encoding="utf-8"))
    schema_validator = Draft202012Validator(schema)
    registry_document = json.loads(archived_inputs["source_registry"].read_text(encoding="utf-8"))
    registry = load_source_registry(archived_inputs["source_registry"])
    for receipt in receipts:
        source = registry.get(receipt["source_id"])
        if source is None:
            raise ValueError(f"approval receipt {receipt['receipt_id']} names an unknown source")
        if receipt["target_type"] == "semantic_cluster":
            scope = source.get("sft_approval_scope", "row_only")
            if scope != "cluster_attestation_with_row_receipts":
                raise ValueError(
                    f"source {receipt['source_id']} is row-only; a semantic-cluster receipt "
                    "cannot authorize its rows"
                )
    receipt_by_row = {
        (receipt["source_id"], receipt["record_id"]): receipt
        for receipt in receipts
        if receipt["target_type"] == "record"
    }
    receipt_by_cluster = {
        (receipt["source_id"], receipt["semantic_cluster_id"]): receipt
        for receipt in receipts
        if receipt["target_type"] == "semantic_cluster"
    }
    receipt_state: dict[str, dict[str, Any]] = {
        receipt["receipt_id"]: {
            "seen": 0,
            "train_ineligible": 0,
            "eligible": 0,
            "splits": set(),
            "observed_content_sha256": None,
        }
        for receipt in receipts
    }
    cluster_hashers = {key: _new_cluster_hasher(*key) for key in receipt_by_cluster}

    database_path = state_dir / "selector-state.sqlite3"
    database = sqlite3.connect(database_path)
    database.execute("PRAGMA journal_mode=OFF")
    database.execute("PRAGMA synchronous=OFF")
    database.execute("PRAGMA temp_store=FILE")
    database.executescript(
        """
        CREATE TABLE observed (
            record_id TEXT PRIMARY KEY,
            normalized_prompt_sha256 TEXT NOT NULL UNIQUE
        );
        CREATE TABLE task_owner (
            source_task_sha256 TEXT PRIMARY KEY,
            source_id TEXT NOT NULL
        );
        CREATE TABLE task_splits (
            source_task_sha256 TEXT NOT NULL,
            split TEXT NOT NULL,
            PRIMARY KEY (source_task_sha256, split)
        );
        CREATE TABLE candidates (
            record_id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            subject TEXT NOT NULL,
            pedagogy TEXT NOT NULL,
            semantic_cluster_id TEXT NOT NULL,
            source_task_sha256 TEXT NOT NULL,
            rank_hex TEXT NOT NULL,
            shard_index INTEGER NOT NULL,
            line_index INTEGER NOT NULL,
            authorization TEXT NOT NULL,
            approval_receipt_id TEXT
        );
        """
    )

    counters = {
        name: Counter()
        for name in (
            "source",
            "source_split",
            "subject",
            "topic",
            "difficulty",
            "pedagogy",
            "formula_template_method",
            "curriculum_alignment",
            "source_subject_pedagogy",
            "verification",
            "eligibility",
            "audit_eligibility",
            "split",
            "token_buckets",
        )
    }
    semantic_clusters: dict[str, set[str]] = defaultdict(set)
    semantic_cluster_splits: dict[tuple[str, str], set[str]] = defaultdict(set)
    token_total = 0
    token_minimum: int | None = None
    token_maximum: int | None = None
    verified_shards: list[dict[str, Any]] = []
    total_rows = 0
    seed = int(manifest.get("seed"))
    try:
        database.execute("BEGIN")
        for shard_index, shard_receipt in enumerate(shard_receipts):
            shard_path = _safe_path(warehouse, shard_receipt["path"])
            if not shard_path.is_file():
                raise FileNotFoundError(f"warehouse shard is missing: {shard_path}")
            if shard_path.stat().st_size != shard_receipt["bytes"]:
                raise ValueError(f"warehouse shard byte count mismatch: {shard_path}")
            if sha256_file(shard_path) != shard_receipt["sha256"]:
                raise ValueError(f"warehouse shard hash mismatch: {shard_path}")
            shard_rows = 0
            with shard_path.open(encoding="utf-8") as handle:
                for line_index, line in enumerate(handle):
                    shard_rows += 1
                    total_rows += 1
                    record = json.loads(line)
                    schema_errors = sorted(
                        schema_validator.iter_errors(record), key=lambda error: list(error.path)
                    )
                    validation_errors = validate_record(
                        record,
                        source_registry=registry,
                        source_policy=registry_document["policy"],
                    )
                    if schema_errors or validation_errors:
                        details = validation_errors + [error.message for error in schema_errors]
                        raise ValueError(
                            f"warehouse row {record.get('id')} failed revalidation: {details}"
                        )
                    if not isinstance(record.get("tokenization"), dict):
                        raise TypeError(f"warehouse row {record['id']} has no exact token metadata")
                    prompt_hash = normalized_sha256(record["prompt"])
                    try:
                        database.execute(
                            "INSERT INTO observed VALUES (?, ?)", (record["id"], prompt_hash)
                        )
                    except sqlite3.IntegrityError as exc:
                        raise ValueError(
                            f"warehouse repeats a record ID or normalized prompt at {record['id']}"
                        ) from exc
                    provenance = record["provenance"]
                    verification = record["verification"]
                    contamination = record["contamination"]
                    source_id = provenance["source_id"]
                    cluster_id = provenance["semantic_cluster_id"]
                    task_hash = contamination["source_task_sha256"]
                    database.execute(
                        "INSERT OR IGNORE INTO task_owner VALUES (?, ?)", (task_hash, source_id)
                    )
                    owner = database.execute(
                        "SELECT source_id FROM task_owner WHERE source_task_sha256 = ?",
                        (task_hash,),
                    ).fetchone()[0]
                    if owner != source_id:
                        raise ValueError(
                            f"canonical source task occurs across sources {owner} and {source_id}"
                        )
                    database.execute(
                        "INSERT OR IGNORE INTO task_splits VALUES (?, ?)",
                        (task_hash, record["split"]),
                    )
                    semantic_clusters[source_id].add(cluster_id)
                    semantic_cluster_splits[(source_id, cluster_id)].add(record["split"])

                    content_hash = record_content_sha256(record)
                    row_receipt = receipt_by_row.get((source_id, record["id"]))
                    cluster_receipt = receipt_by_cluster.get((source_id, cluster_id))
                    if row_receipt is not None:
                        state = receipt_state[row_receipt["receipt_id"]]
                        state["seen"] += 1
                        state["splits"].add(record["split"])
                        state["eligible"] += verification["training_eligible"] is True
                        state["train_ineligible"] += (
                            record["split"] == "train"
                            and verification["training_eligible"] is False
                        )
                        state["observed_content_sha256"] = content_hash
                    if cluster_receipt is not None:
                        state = receipt_state[cluster_receipt["receipt_id"]]
                        state["seen"] += 1
                        state["splits"].add(record["split"])
                        state["eligible"] += verification["training_eligible"] is True
                        state["train_ineligible"] += (
                            record["split"] == "train"
                            and verification["training_eligible"] is False
                        )
                        _update_cluster_hasher(
                            cluster_hashers[(source_id, cluster_id)], record, content_hash
                        )

                    authorization: str | None = None
                    receipt_id: str | None = None
                    if record["split"] == "train":
                        if verification["training_eligible"] is True:
                            authorization = "native_training_eligible"
                        elif row_receipt is not None and row_receipt["decision"] == "approved":
                            authorization = "approved_record_receipt"
                            receipt_id = row_receipt["receipt_id"]
                    if authorization is not None:
                        database.execute(
                            "INSERT INTO candidates VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                record["id"],
                                source_id,
                                record["subject"],
                                record["pedagogy"],
                                cluster_id,
                                task_hash,
                                _rank(seed, record["id"]),
                                shard_index,
                                line_index,
                                authorization,
                                receipt_id,
                            ),
                        )

                    counters["source"][source_id] += 1
                    counters["source_split"][f"{source_id} :: {provenance['source_split']}"] += 1
                    counters["subject"][record["subject"]] += 1
                    counters["topic"][record["topic"]] += 1
                    counters["difficulty"][record["difficulty"]] += 1
                    counters["pedagogy"][record["pedagogy"]] += 1
                    counters["formula_template_method"][_formula_template_method_key(record)] += 1
                    counters["curriculum_alignment"][record["curriculum"]["alignment"]] += 1
                    counters["source_subject_pedagogy"][
                        f"{source_id} :: {record['subject']} :: {record['pedagogy']}"
                    ] += 1
                    counters["verification"][verification["status"]] += 1
                    eligibility = (
                        "eligible"
                        if verification["training_eligible"] is True
                        else "audit_required"
                    )
                    counters["eligibility"][eligibility] += 1
                    counters["audit_eligibility"][
                        "training_eligible"
                        if verification["training_eligible"] is True
                        else "audit_required"
                    ] += 1
                    counters["split"][record["split"]] += 1
                    token_count = record["tokenization"]["sequence_tokens"]
                    counters["token_buckets"][_token_bucket(token_count)] += 1
                    token_total += token_count
                    token_minimum = (
                        token_count if token_minimum is None else min(token_minimum, token_count)
                    )
                    token_maximum = (
                        token_count if token_maximum is None else max(token_maximum, token_count)
                    )
            if shard_rows != shard_receipt["rows"]:
                raise ValueError(f"warehouse shard row count mismatch: {shard_path}")
            verified_shards.append(dict(shard_receipt))
        database.commit()
    except BaseException:
        database.close()
        raise

    if total_rows != manifest.get("row_count"):
        database.close()
        raise ValueError("warehouse row count does not equal its manifest")
    fingerprint = hashlib.sha256(
        "\n".join(shard["sha256"] for shard in verified_shards).encode("ascii")
    ).hexdigest()
    if fingerprint != manifest.get("dataset_fingerprint_sha256"):
        database.close()
        raise ValueError("warehouse aggregate dataset fingerprint mismatch")
    for receipt in receipts:
        if receipt["warehouse_dataset_fingerprint_sha256"] != fingerprint:
            database.close()
            raise ValueError(
                f"approval receipt {receipt['receipt_id']} binds a different warehouse"
            )
        state = receipt_state[receipt["receipt_id"]]
        if not state["seen"]:
            database.close()
            raise ValueError(f"approval receipt {receipt['receipt_id']} targets no warehouse rows")
        if state["eligible"]:
            database.close()
            raise ValueError(
                f"approval receipt {receipt['receipt_id']} unnecessarily targets eligible rows"
            )
        if not state["train_ineligible"] or state["splits"] != {"train"}:
            database.close()
            raise ValueError(
                f"approval receipt {receipt['receipt_id']} does not exclusively target ineligible train rows"
            )
        observed_hash = (
            state["observed_content_sha256"]
            if receipt["target_type"] == "record"
            else cluster_hashers[(receipt["source_id"], receipt["semantic_cluster_id"])].hexdigest()
        )
        if observed_hash != receipt["record_content_sha256"]:
            database.close()
            raise ValueError(f"approval receipt {receipt['receipt_id']} has a stale content hash")

    cross_split = database.execute(
        """
        SELECT source_task_sha256, GROUP_CONCAT(split)
        FROM task_splits
        GROUP BY source_task_sha256
        HAVING COUNT(*) > 1
        LIMIT 1
        """
    ).fetchone()
    if cross_split is not None:
        database.close()
        raise ValueError(
            f"canonical source task crosses dataset splits: {cross_split[0]} ({cross_split[1]})"
        )
    cluster_overlap = [
        (key, splits) for key, splits in semantic_cluster_splits.items() if len(splits) > 1
    ]
    if cluster_overlap:
        database.close()
        raise ValueError(f"semantic cluster crosses dataset splits: {cluster_overlap[0]}")
    expected_cluster_counts = {
        source: len(clusters) for source, clusters in sorted(semantic_clusters.items())
    }
    if expected_cluster_counts != (manifest.get("counts") or {}).get(
        "semantic_cluster_count_by_source"
    ):
        database.close()
        raise ValueError("warehouse semantic-cluster counts do not match its manifest")
    if (manifest.get("counts") or {}).get("semantic_cluster_split_overlap_count") != 0:
        database.close()
        raise ValueError("warehouse manifest reports semantic-cluster split overlap")
    if not isinstance(
        (manifest.get("counts") or {}).get("cross_source_task_collision_pairs"), dict
    ):
        database.close()
        raise TypeError("warehouse manifest omits cross-source collision rejection accounting")
    for key in (
        "source",
        "source_split",
        "subject",
        "topic",
        "difficulty",
        "pedagogy",
        "formula_template_method",
        "curriculum_alignment",
        "source_subject_pedagogy",
        "verification",
        "eligibility",
        "audit_eligibility",
        "split",
    ):
        _check_manifest_counter(manifest, counters[key], key)
    tokenization = manifest["tokenization"]
    if tokenization.get("minimum_sequence_tokens") != token_minimum:
        database.close()
        raise ValueError("warehouse minimum token count does not match its rows")
    if tokenization.get("maximum_sequence_tokens") != token_maximum:
        database.close()
        raise ValueError("warehouse maximum token count does not match its rows")
    observed_mean = round(token_total / total_rows, 6)
    if tokenization.get("mean_sequence_tokens") != observed_mean:
        database.close()
        raise ValueError("warehouse mean token count does not match its rows")
    if tokenization.get("buckets") != dict(sorted(counters["token_buckets"].items())):
        database.close()
        raise ValueError("warehouse token buckets do not match its rows")
    source_receipts = {row["id"]: row["rows"] for row in manifest.get("sources") or ()}
    if source_receipts != dict(counters["source"]):
        database.close()
        raise ValueError("warehouse source receipts do not match its rows")
    for source_id, requested in (manifest.get("requested_counts") or {}).items():
        if counters["source"].get(source_id) != requested:
            database.close()
            raise ValueError(f"warehouse requested count for {source_id} is not satisfied")

    return _VerifiedWarehouse(
        manifest=manifest,
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha256,
        shard_paths=[_safe_path(warehouse, receipt["path"]) for receipt in verified_shards],
        shard_receipts=verified_shards,
        archived_inputs=archived_inputs,
        receipts=receipts,
        receipt_files=receipt_files,
        rubric_files=rubric_files,
        database=database,
        database_path=database_path,
        actual_counts=counters,
    )


def _materialize_caps(
    database: sqlite3.Connection, *, template_cap: int, source_task_cap: int
) -> tuple[dict[tuple[str, str, str], int], dict[str, int]]:
    if template_cap <= 0:
        raise ValueError("external template cap must be positive")
    if source_task_cap <= 0:
        raise ValueError("canonical source-task cap must be positive")
    candidate_rows = database.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
    task_survivors = database.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN task_rows < ? THEN task_rows ELSE ? END), 0)
        FROM (
            SELECT COUNT(*) AS task_rows FROM candidates GROUP BY source_task_sha256
        )
        """,
        (source_task_cap, source_task_cap),
    ).fetchone()[0]
    database.execute(
        """
        CREATE TABLE capped_candidates AS
        WITH task_ranked AS (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY source_task_sha256 ORDER BY rank_hex, record_id
            ) AS task_position
            FROM candidates
        ), cluster_ranked AS (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY source_id, semantic_cluster_id ORDER BY rank_hex, record_id
            ) AS cluster_position
            FROM task_ranked
            WHERE task_position <= ?
        )
        SELECT * FROM cluster_ranked
        WHERE source_id != ? OR cluster_position <= ?
        """,
        (source_task_cap, TEMPLATE_SOURCE_ID, template_cap),
    )
    database.execute(
        "CREATE INDEX capped_cell_rank ON capped_candidates "
        "(source_id, subject, pedagogy, rank_hex, record_id)"
    )
    database.execute("CREATE INDEX capped_record ON capped_candidates (record_id)")
    capped_rows = database.execute("SELECT COUNT(*) FROM capped_candidates").fetchone()[0]
    availability = {
        (source, subject, pedagogy): count
        for source, subject, pedagogy, count in database.execute(
            """
            SELECT source_id, subject, pedagogy, COUNT(*)
            FROM capped_candidates
            GROUP BY source_id, subject, pedagogy
            """
        )
    }
    return availability, {
        "authorized_train_candidates": candidate_rows,
        "excluded_by_source_task_cap": candidate_rows - task_survivors,
        "excluded_by_external_template_cap": task_survivors - capped_rows,
        "capped_candidates": capped_rows,
    }


def _solve_cell_quotas(
    *, recipe: dict[str, Any], availability: dict[tuple[str, str, str], int]
) -> tuple[dict[tuple[str, str, str], int], dict[str, int], dict[str, int], dict[str, int]]:
    target = int(recipe["recommended_sft_target_rows"])
    source_quotas = _expanded_source_quotas(recipe)
    subject_quotas = _apportion(target, recipe["recommended_sft_subject_targets"])
    pedagogy_quotas = _apportion(target, recipe["recommended_sft_pedagogy_targets"])
    if sum(source_quotas.values()) != target:
        raise ValueError("expanded recommended source quotas do not sum to the SFT target")
    unknown_sources = sorted({source for source, _, _ in availability}.difference(source_quotas))
    if unknown_sources:
        raise RuntimeError(
            f"authorized train candidates include sources absent from the recipe: {unknown_sources}"
        )
    cells: dict[tuple[str, str, str], int] = {}
    residual_subject = dict(subject_quotas)
    residual_pedagogy = dict(pedagogy_quotas)
    for source_id, quota in sorted(source_quotas.items()):
        if source_id == LOCAL_SOURCE_ID:
            continue
        source_cells = {
            (subject, pedagogy): count
            for (source, subject, pedagogy), count in availability.items()
            if source == source_id and count > 0
        }
        if len(source_cells) != 1:
            raise RuntimeError(
                f"external source {source_id} must have one audited subject/pedagogy cell; "
                f"found {sorted(source_cells)}"
            )
        (subject, pedagogy), available = next(iter(source_cells.items()))
        if available < quota:
            raise RuntimeError(
                f"source {source_id} has {available:,} authorized capped rows; needs {quota:,}"
            )
        if residual_subject.get(subject, 0) < quota or residual_pedagogy.get(pedagogy, 0) < quota:
            raise RuntimeError(
                f"source {source_id} allocation exceeds the global {subject}/{pedagogy} margin"
            )
        cells[(source_id, subject, pedagogy)] = quota
        residual_subject[subject] -= quota
        residual_pedagogy[pedagogy] -= quota
    residual_subject = {key: value for key, value in residual_subject.items() if value > 0}
    residual_pedagogy = {key: value for key, value in residual_pedagogy.items() if value > 0}
    local_quota = source_quotas.get(LOCAL_SOURCE_ID, 0)
    if (
        sum(residual_subject.values()) != local_quota
        or sum(residual_pedagogy.values()) != local_quota
    ):
        raise RuntimeError("external allocations leave inconsistent local target margins")
    local_availability = {
        (subject, pedagogy): count
        for (source, subject, pedagogy), count in availability.items()
        if source == LOCAL_SOURCE_ID
    }
    declared_local_cells = recipe.get("recommended_sft_local_cell_quotas")
    if declared_local_cells is None:
        local_cells = _local_transport(
            residual_subject, residual_pedagogy, local_availability
        )
    else:
        if not isinstance(declared_local_cells, dict):
            raise TypeError("recommended local cell quotas must be an object")
        local_cells: dict[tuple[str, str], int] = {}
        for label, quota in declared_local_cells.items():
            if not isinstance(label, str) or label.count(" :: ") != 1:
                raise ValueError(f"invalid recommended local cell label: {label!r}")
            subject, pedagogy = label.split(" :: ")
            if subject not in residual_subject or pedagogy not in residual_pedagogy:
                raise ValueError(f"recommended local cell is outside the residual margins: {label}")
            if not isinstance(quota, int) or isinstance(quota, bool) or quota < 0:
                raise ValueError(f"recommended local cell quota must be non-negative: {label}")
            if quota:
                local_cells[(subject, pedagogy)] = quota
        declared_subjects: Counter[str] = Counter()
        declared_pedagogies: Counter[str] = Counter()
        for (subject, pedagogy), quota in local_cells.items():
            declared_subjects[subject] += quota
            declared_pedagogies[pedagogy] += quota
            if local_availability.get((subject, pedagogy), 0) < quota:
                raise RuntimeError(
                    f"recommended local cell {subject}/{pedagogy} has "
                    f"{local_availability.get((subject, pedagogy), 0):,} candidates; "
                    f"needs {quota:,}"
                )
        if dict(declared_subjects) != residual_subject:
            raise ValueError("recommended local cells do not match the residual subject margins")
        if dict(declared_pedagogies) != residual_pedagogy:
            raise ValueError("recommended local cells do not match the residual pedagogy margins")
    for (subject, pedagogy), quota in local_cells.items():
        cells[(LOCAL_SOURCE_ID, subject, pedagogy)] = quota
    if sum(cells.values()) != target:
        raise RuntimeError("cell quota solver did not allocate the complete SFT target")
    return cells, source_quotas, subject_quotas, pedagogy_quotas


class _AtomicShardWriter:
    def __init__(self, directory: Path, shard_rows: int) -> None:
        self.directory = directory
        self.shard_rows = shard_rows
        self.shards: list[dict[str, Any]] = []
        self.total_rows = 0
        self._rows = 0
        self._handle: Any | None = None
        self._partial: Path | None = None

    def write(self, record: dict[str, Any]) -> None:
        if self._handle is None:
            self._partial = self.directory / f"part-{len(self.shards):05d}.jsonl.partial"
            self._handle = self._partial.open("x", encoding="utf-8", newline="\n")
            self._rows = 0
        self._handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        self._rows += 1
        self.total_rows += 1
        if self._rows == self.shard_rows:
            self.close_shard()

    def close_shard(self) -> None:
        if self._handle is None or self._partial is None:
            return
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._handle.close()
        final = self._partial.with_suffix("")
        self._partial.replace(final)
        self.shards.append(
            {
                "path": final.name,
                "rows": self._rows,
                "bytes": final.stat().st_size,
                "sha256": sha256_file(final),
            }
        )
        self._handle = None
        self._partial = None
        self._rows = 0

    def close(self) -> None:
        self.close_shard()


def _write_provenance(
    *,
    partial_output: Path,
    verified: _VerifiedWarehouse,
    recipe_path: Path,
    selection_recipe_sha256: str,
) -> dict[str, Any]:
    directory = partial_output / "selector-provenance"
    directory.mkdir()
    sources = {
        "warehouse_manifest": verified.manifest_path,
        "warehouse_recipe": verified.archived_inputs["recipe"],
        "selection_recipe": recipe_path,
        "approval_schema": APPROVAL_SCHEMA_PATH,
        "selector": Path(__file__).resolve(),
    }
    receipts: dict[str, dict[str, Any]] = {}
    for name, source in sources.items():
        before = sha256_file(source)
        expected = {
            "warehouse_manifest": verified.manifest_sha256,
            "warehouse_recipe": verified.manifest["inputs"]["recipe"]["sha256"],
            "selection_recipe": selection_recipe_sha256,
            "approval_schema": IMPORTED_APPROVAL_SCHEMA_SHA256,
            "selector": IMPORTED_SELECTOR_SHA256,
        }[name]
        if before != expected:
            raise RuntimeError(f"selector provenance input drifted after it was loaded: {source}")
        destination = directory / f"{name}-{source.name}"
        shutil.copyfile(source, destination)
        if sha256_file(source) != before or sha256_file(destination) != before:
            raise RuntimeError(f"selector provenance input changed while copied: {source}")
        receipts[name] = {
            "path": destination.relative_to(partial_output).as_posix(),
            "bytes": destination.stat().st_size,
            "sha256": before,
        }
    canonical_receipts = directory / "approval-receipts.jsonl"
    with canonical_receipts.open("x", encoding="utf-8", newline="\n") as handle:
        for receipt in sorted(verified.receipts, key=lambda item: item["receipt_id"]):
            handle.write(json.dumps(receipt, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    receipts["approval_receipts"] = {
        "path": canonical_receipts.relative_to(partial_output).as_posix(),
        "bytes": canonical_receipts.stat().st_size,
        "sha256": sha256_file(canonical_receipts),
        "count": len(verified.receipts),
        "input_files": verified.receipt_files,
    }
    rubric_receipts = []
    rubric_directory = directory / "rubrics"
    if verified.rubric_files:
        rubric_directory.mkdir()
    for rubric in verified.rubric_files:
        source = rubric["source_path"]
        destination = rubric_directory / f"{rubric['sha256']}-{rubric['name']}"
        shutil.copyfile(source, destination)
        if sha256_file(source) != rubric["sha256"] or sha256_file(destination) != rubric["sha256"]:
            raise RuntimeError(f"approval rubric changed while copied: {source}")
        rubric_receipts.append(
            {
                "path": destination.relative_to(partial_output).as_posix(),
                "bytes": destination.stat().st_size,
                "sha256": rubric["sha256"],
            }
        )
    receipts["approval_rubrics"] = {
        "count": len(rubric_receipts),
        "files": rubric_receipts,
    }
    receipts["warehouse_provenance_archives"] = _copy_warehouse_provenance_archives(
        warehouse=verified.manifest_path.parent,
        destination_root=directory,
        manifest=verified.manifest,
    )
    return receipts


def _creator_from_registry(source: dict[str, Any]) -> tuple[str, str]:
    explicit = str(source.get("creator", "")).strip()
    if explicit:
        return explicit, "archived source registry creator field"
    if source["id"] == LOCAL_SOURCE_ID:
        return "Muta project", "archived source registry source identity"
    repository_id = str(source.get("repository_id", "")).strip()
    if "/" in repository_id:
        return repository_id.split("/", 1)[0], "archived repository_id namespace"
    return "not stated", "archived source registry contains no creator field"


def _selected_source_attribution_inventory(
    *,
    verified: _VerifiedWarehouse,
    provenance: dict[str, Any],
    source_states: dict[str, dict[str, Any]],
    selected_source_counts: Counter[str],
) -> dict[str, Any]:
    registry_document = json.loads(
        verified.archived_inputs["source_registry"].read_text(encoding="utf-8")
    )
    registry = {source["id"]: source for source in registry_document["sources"]}
    if set(source_states) != set(selected_source_counts):
        raise RuntimeError("selected source attribution state does not cover selected sources")

    copied_archives = provenance["warehouse_provenance_archives"]["archives"]
    source_evidence = copied_archives["source_evidence_archive"]["files"]
    provenance_code = copied_archives["provenance_archive"]["files"]
    local_license_path = verified.manifest["inputs"]["muta_license"]["archive_path"]
    sources: list[dict[str, Any]] = []
    for source_id in sorted(selected_source_counts):
        source = registry.get(source_id)
        if source is None:
            raise RuntimeError(f"selected source is absent from archived registry: {source_id}")
        state = source_states[source_id]
        selected_count = int(selected_source_counts[source_id])
        if sum(state["authorization"].values()) != selected_count:
            raise RuntimeError(f"source attribution count mismatch for {source_id}")
        row_licenses = set(state["license"])
        if row_licenses != {source["license"]}:
            raise RuntimeError(f"selected row licenses disagree with registry for {source_id}")
        row_synthetic = set(state["synthetic"])
        registry_synthetic = source.get("synthetic")
        if not isinstance(registry_synthetic, bool) or row_synthetic != {registry_synthetic}:
            raise RuntimeError(f"selected synthetic flags disagree with registry for {source_id}")
        revisions = sorted(state["revision"])
        source_splits = sorted(state["source_split"])
        if not revisions or not source_splits:
            raise RuntimeError(f"selected source lacks revision or split evidence: {source_id}")

        evidence = [
            {
                key: item[key]
                for key in ("path", "bytes", "sha256", "revision", "locator")
                if key in item
            }
            for item in source_evidence
            if item.get("source_id") == source_id
        ]
        if source_id == LOCAL_SOURCE_ID:
            evidence.extend(
                {key: item[key] for key in ("path", "bytes", "sha256") if key in item}
                for item in provenance_code
                if item["warehouse_relative_path"] == local_license_path
            )
        creator, creator_basis = _creator_from_registry(source)
        authorization_counts = dict(sorted(state["authorization"].items()))
        if set(authorization_counts) == {"native_training_eligible"}:
            audit_result = "native training eligibility revalidated from the warehouse row"
        elif set(authorization_counts) == {"approved_record_receipt"}:
            audit_result = "exact-record approved receipts revalidated and archived"
        else:
            audit_result = "mixed native eligibility and exact-record approvals revalidated"
        sources.append(
            {
                "source_id": source_id,
                "creator": creator,
                "creator_evidence": creator_basis,
                "title": source["name"],
                "name": source["name"],
                "source_url": source["url"],
                "selected_count": selected_count,
                "immutable_revision_config_split_evidence": {
                    "registry_revision": source["revision"],
                    "selected_row_revisions": revisions,
                    "repository_id": source.get("repository_id"),
                    "repository_type": source.get("repository_type"),
                    "registry_configuration": source.get("configuration"),
                    "registry_allowed_splits": list(source.get("allowed_splits") or ()),
                    "selected_source_splits": source_splits,
                },
                "license": {
                    "name": source["license"],
                    "url": source["license_url"],
                    "archived_evidence": sorted(evidence, key=lambda item: item["path"]),
                },
                "transform_change_notice": {
                    "summary": (
                        "Selected rows retain their exact per-row transform/change notices; "
                        "the frequency of each notice is recorded here."
                    ),
                    "selected_transform_counts": dict(sorted(state["transform"].items())),
                },
                "synthetic": registry_synthetic,
                "verification_audit_result": {
                    "result": audit_result,
                    "registry_verification": source["verification"],
                    "selected_verification_status_counts": dict(
                        sorted(state["verification_status"].items())
                    ),
                    "selected_verification_method_counts": dict(
                        sorted(state["verification_method"].items())
                    ),
                    "authorization_counts": authorization_counts,
                    "approved_receipt_ids_used": sorted(state["approval_receipt_id"]),
                },
            }
        )

    if sum(source["selected_count"] for source in sources) != sum(selected_source_counts.values()):
        raise RuntimeError("source attribution inventory row total is inconsistent")
    return {
        "schema_version": 1,
        "artifact_role": "mixed-source attribution inventory for selected SFT rows",
        "licensing_scope": "per-source; this mixed artifact has no blanket MIT declaration",
        "blanket_license": None,
        "archived_source_registry_sha256": verified.manifest["inputs"]["source_registry"]["sha256"],
        "selected_row_count": sum(selected_source_counts.values()),
        "source_count": len(sources),
        "sources": sources,
    }


def _write_selected_source_attribution(
    *, partial_output: Path, inventory: dict[str, Any]
) -> dict[str, Any]:
    path = partial_output / "selector-provenance" / "selected-source-attribution.json"
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return {
        "path": path.relative_to(partial_output).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "source_count": inventory["source_count"],
        "selected_row_count": inventory["selected_row_count"],
    }


def select_sft(
    *,
    warehouse: Path,
    output: Path,
    approval_receipts: Sequence[Path] = (),
    rubric_files: Sequence[Path] = (),
    recipe_path: Path | None = None,
    shard_rows: int | None = None,
) -> dict[str, Any]:
    if sha256_file(Path(__file__).resolve()) != IMPORTED_SELECTOR_SHA256:
        raise RuntimeError("loaded selector code differs from disk; restart in a fresh process")
    if sha256_file(APPROVAL_SCHEMA_PATH) != IMPORTED_APPROVAL_SCHEMA_SHA256:
        raise RuntimeError("loaded approval schema differs from disk; restart in a fresh process")
    warehouse = warehouse.resolve()
    output = output.resolve()
    partial_output = output.with_name(output.name + ".partial")
    if output.exists() or partial_output.exists():
        raise FileExistsError("refusing to overwrite an SFT output or its partial directory")
    if output == warehouse or warehouse in output.parents or output in warehouse.parents:
        raise ValueError("warehouse and SFT output directories must be disjoint")

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="muta-sft-selector-", dir=output.parent) as temporary:
        verified = _verify_warehouse(
            warehouse=warehouse,
            receipt_paths=approval_receipts,
            rubric_paths=rubric_files,
            state_dir=Path(temporary),
        )
        try:
            archived_recipe = verified.archived_inputs["recipe"]
            recipe, selected_recipe_path, selection_recipe_binding = _load_selection_recipe(
                archived_recipe_path=archived_recipe,
                requested_recipe_path=recipe_path,
            )
            template_cap = int(recipe["limits"]["max_rows_per_external_template_in_sft"])
            source_task_cap = int(recipe["limits"]["max_rows_per_source_task_in_sft"])
            output_shard_rows = int(shard_rows or recipe["limits"]["shard_rows"])
            if output_shard_rows <= 0:
                raise ValueError("SFT shard row count must be positive")
            availability, exclusions = _materialize_caps(
                verified.database,
                template_cap=template_cap,
                source_task_cap=source_task_cap,
            )
            cell_quotas, source_quotas, subject_quotas, pedagogy_quotas = _solve_cell_quotas(
                recipe=recipe, availability=availability
            )
            verified.database.execute(
                "CREATE TABLE selected (record_id TEXT PRIMARY KEY) WITHOUT ROWID"
            )
            for (source_id, subject, pedagogy), quota in sorted(cell_quotas.items()):
                rows = verified.database.execute(
                    """
                    SELECT record_id FROM capped_candidates
                    WHERE source_id = ? AND subject = ? AND pedagogy = ?
                    ORDER BY rank_hex, record_id
                    LIMIT ?
                    """,
                    (source_id, subject, pedagogy, quota),
                ).fetchall()
                if len(rows) != quota:
                    raise RuntimeError(
                        f"selector could not fill {source_id}/{subject}/{pedagogy}: "
                        f"{len(rows):,}/{quota:,}"
                    )
                verified.database.executemany("INSERT INTO selected VALUES (?)", rows)
            verified.database.commit()
            selected_ids = {
                row[0] for row in verified.database.execute("SELECT record_id FROM selected")
            }
            target = int(recipe["recommended_sft_target_rows"])
            if len(selected_ids) != target:
                raise RuntimeError(
                    f"selector chose {len(selected_ids):,} rows; expected {target:,}"
                )

            partial_output.mkdir()
            provenance = _write_provenance(
                partial_output=partial_output,
                verified=verified,
                recipe_path=selected_recipe_path,
                selection_recipe_sha256=selection_recipe_binding[
                    "selection_recipe_sha256"
                ],
            )
            writer = _AtomicShardWriter(partial_output, output_shard_rows)
            counts = {
                name: Counter() for name in ("source", "subject", "pedagogy", "authorization")
            }
            task_counts: Counter[str] = Counter()
            template_counts: Counter[str] = Counter()
            receipt_usage: Counter[str] = Counter()
            source_attribution_states: dict[str, dict[str, Any]] = {}
            observed_selected: set[str] = set()
            for shard_index, (source_path, source_receipt) in enumerate(
                zip(verified.shard_paths, verified.shard_receipts)
            ):
                digest = hashlib.sha256()
                byte_count = 0
                row_count = 0
                with source_path.open("rb") as handle:
                    for raw_line in handle:
                        digest.update(raw_line)
                        byte_count += len(raw_line)
                        row_count += 1
                        record = json.loads(raw_line)
                        if record["id"] not in selected_ids:
                            continue
                        candidate = verified.database.execute(
                            """
                            SELECT authorization, approval_receipt_id
                            FROM capped_candidates WHERE record_id = ?
                            """,
                            (record["id"],),
                        ).fetchone()
                        if candidate is None:
                            raise RuntimeError(
                                f"selected row vanished from candidate state: {record['id']}"
                            )
                        if record["split"] != "train":
                            raise RuntimeError(
                                f"selector attempted to emit non-train row {record['id']}"
                            )
                        if (
                            record["verification"]["training_eligible"] is not True
                            and not candidate[1]
                        ):
                            raise RuntimeError(
                                f"ineligible row lacks an approval receipt: {record['id']}"
                            )
                        writer.write(record)
                        observed_selected.add(record["id"])
                        source_id = record["provenance"]["source_id"]
                        counts["source"][source_id] += 1
                        counts["subject"][record["subject"]] += 1
                        counts["pedagogy"][record["pedagogy"]] += 1
                        counts["authorization"][candidate[0]] += 1
                        task_counts[record["contamination"]["source_task_sha256"]] += 1
                        if source_id == TEMPLATE_SOURCE_ID:
                            template_counts[record["provenance"]["semantic_cluster_id"]] += 1
                        if candidate[1]:
                            receipt_usage[candidate[1]] += 1
                        source_state = source_attribution_states.setdefault(
                            source_id,
                            {
                                "revision": set(),
                                "source_split": set(),
                                "license": set(),
                                "synthetic": set(),
                                "transform": Counter(),
                                "verification_status": Counter(),
                                "verification_method": Counter(),
                                "authorization": Counter(),
                                "approval_receipt_id": set(),
                            },
                        )
                        provenance_record = record["provenance"]
                        verification_record = record["verification"]
                        source_state["revision"].add(provenance_record["source_revision"])
                        source_state["source_split"].add(provenance_record["source_split"])
                        source_state["license"].add(provenance_record["license"])
                        source_state["synthetic"].add(provenance_record["synthetic"])
                        source_state["transform"][provenance_record["transform"]] += 1
                        source_state["verification_status"][verification_record["status"]] += 1
                        source_state["verification_method"][verification_record["method"]] += 1
                        source_state["authorization"][candidate[0]] += 1
                        if candidate[1]:
                            source_state["approval_receipt_id"].add(candidate[1])
                if digest.hexdigest() != source_receipt["sha256"]:
                    raise RuntimeError(f"warehouse shard changed during selection: {source_path}")
                if byte_count != source_receipt["bytes"] or row_count != source_receipt["rows"]:
                    raise RuntimeError(
                        f"warehouse shard shape changed during selection: {source_path}"
                    )
            writer.close()
            if observed_selected != selected_ids or writer.total_rows != target:
                raise RuntimeError("not every selected warehouse row was materialized exactly once")
            if dict(counts["source"]) != source_quotas:
                raise RuntimeError("materialized source allocation differs from the solved quota")
            if dict(counts["subject"]) != subject_quotas:
                raise RuntimeError("materialized subject margin differs from the recipe")
            if dict(counts["pedagogy"]) != pedagogy_quotas:
                raise RuntimeError("materialized pedagogy margin differs from the recipe")
            max_task_rows = max(task_counts.values(), default=0)
            if max_task_rows > source_task_cap:
                raise RuntimeError("materialized data exceeds the canonical source-task cap")
            max_template_rows = max(template_counts.values(), default=0)
            if max_template_rows > template_cap:
                raise RuntimeError("materialized data exceeds the external-template cap")

            source_attribution_inventory = _selected_source_attribution_inventory(
                verified=verified,
                provenance=provenance,
                source_states=source_attribution_states,
                selected_source_counts=counts["source"],
            )
            source_attribution_receipt = _write_selected_source_attribution(
                partial_output=partial_output,
                inventory=source_attribution_inventory,
            )
            provenance["selected_source_attribution"] = source_attribution_receipt

            fingerprint = hashlib.sha256(
                "\n".join(shard["sha256"] for shard in writer.shards).encode("ascii")
            ).hexdigest()
            exclusions["excluded_by_quota_rank"] = exclusions["capped_candidates"] - target
            receipts_by_decision = {
                decision: sorted(
                    (receipt for receipt in verified.receipts if receipt["decision"] == decision),
                    key=lambda item: item["receipt_id"],
                )
                for decision in ("approved", "rejected")
            }
            selected_usage_by_decision = {
                decision: {
                    receipt["receipt_id"]: receipt_usage.get(receipt["receipt_id"], 0)
                    for receipt in receipts_by_decision[decision]
                }
                for decision in ("approved", "rejected")
            }
            manifest = {
                "schema_version": 1,
                "dataset_name": "muta-stem-sft-v2-selected",
                "row_count": target,
                "dataset_fingerprint_sha256": fingerprint,
                "seed": int(recipe["seed"]),
                "source_warehouse": {
                    "dataset_fingerprint_sha256": verified.manifest["dataset_fingerprint_sha256"],
                    "manifest_sha256": verified.manifest_sha256,
                    "row_count": verified.manifest["row_count"],
                    "shards_verified_twice": True,
                    "row_schema_and_provenance_revalidated": True,
                    "count_margins_recomputed": True,
                },
                "selection": {
                    "rank": "lowest SHA-256(recipe_seed:record_id) in each solved quota cell",
                    "recipe_binding": selection_recipe_binding,
                    "split": "train only",
                    "native_eligibility": "verification.training_eligible=true",
                    "audit_gate": (
                        "otherwise require a schema-valid content-addressed receipt with an "
                        "approved decision for this exact warehouse fingerprint, exact record, "
                        "and record content"
                    ),
                    "max_rows_per_source_task_sha256": source_task_cap,
                    "max_selected_weight_per_source_task": round(max_task_rows / target, 12),
                    "source_task_split_overlap_count": 0,
                    "external_template_source": TEMPLATE_SOURCE_ID,
                    "max_rows_per_external_template": template_cap,
                    "observed_max_rows_per_external_template": max_template_rows,
                    "cell_quotas": {
                        " :: ".join(cell): quota for cell, quota in sorted(cell_quotas.items())
                    },
                    "capped_availability": {
                        " :: ".join(cell): count
                        for cell, count in sorted(availability.items())
                    },
                },
                "counts": {
                    "source": dict(sorted(counts["source"].items())),
                    "subject": dict(sorted(counts["subject"].items())),
                    "pedagogy": dict(sorted(counts["pedagogy"].items())),
                    "authorization": dict(sorted(counts["authorization"].items())),
                },
                "required_margins": {
                    "source": dict(sorted(source_quotas.items())),
                    "subject": dict(sorted(subject_quotas.items())),
                    "pedagogy": dict(sorted(pedagogy_quotas.items())),
                },
                "candidate_exclusions": exclusions,
                "approval_receipts": {
                    "validated": len(verified.receipts),
                    "validated_by_decision": {
                        decision: len(receipts_by_decision[decision])
                        for decision in ("approved", "rejected")
                    },
                    "trust_model": (
                        "content-addressed decision attestations with self-asserted reviewer and "
                        "review-method fields; receipts are not cryptographic signatures, and "
                        "their text must distinguish human from model-assisted review"
                    ),
                    "authorization_scope": (
                        "approved exact-record receipts only; rejected receipts and "
                        "semantic-cluster attestations never authorize rows"
                    ),
                    "rubric_artifacts_verified_and_archived": True,
                    "selected_row_usage": {
                        receipt["receipt_id"]: receipt_usage.get(receipt["receipt_id"], 0)
                        for receipt in sorted(
                            verified.receipts, key=lambda item: item["receipt_id"]
                        )
                    },
                    "selected_row_usage_by_decision": selected_usage_by_decision,
                    "rejected_receipts_never_authorize_selection": True,
                },
                "source_attribution": {
                    "licensing_scope": (
                        "per-source licensing; no blanket MIT declaration applies to this "
                        "mixed-source selected artifact"
                    ),
                    "blanket_license": None,
                    "inventory": source_attribution_receipt,
                    "selected_count_by_source": dict(sorted(counts["source"].items())),
                    "license_by_source": {
                        source["source_id"]: source["license"]
                        for source in source_attribution_inventory["sources"]
                    },
                },
                "inputs": provenance,
                "shards": writer.shards,
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
        "--approval-receipt",
        action="append",
        default=[],
        type=Path,
        help="JSON/JSONL receipt file; repeat for multiple files",
    )
    parser.add_argument(
        "--rubric",
        action="append",
        default=[],
        type=Path,
        help="rubric artifact whose SHA-256 is referenced by a receipt; repeat as needed",
    )
    parser.add_argument(
        "--recipe",
        type=Path,
        help=(
            "optional SFT allocation override; only documented recommended-allocation and "
            "training-note fields may differ from the warehouse recipe"
        ),
    )
    parser.add_argument("--shard-rows", type=int)
    args = parser.parse_args(argv)
    if args.shard_rows is not None and args.shard_rows <= 0:
        parser.error("--shard-rows must be positive")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = select_sft(
        warehouse=args.warehouse,
        output=args.output,
        approval_receipts=args.approval_receipt,
        rubric_files=args.rubric,
        recipe_path=args.recipe,
        shard_rows=args.shard_rows,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
