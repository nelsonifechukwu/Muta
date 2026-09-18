"""Fail-closed input and artifact receipts for Muta fine-tuning campaigns."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class CampaignInputError(ValueError):
    """Raised when a campaign input no longer matches its frozen receipt."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_jsonl_rows(path: Path) -> int:
    with path.open("rb") as handle:
        return sum(1 for line in handle if line.strip())


def dataset_fingerprint(shards: Iterable[dict[str, Any]]) -> str:
    payload = "\n".join(str(shard["sha256"]) for shard in shards).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _safe_child(root: Path, relative: str) -> Path:
    if not relative or Path(relative).is_absolute():
        raise CampaignInputError(f"unsafe shard path: {relative!r}")
    root = root.resolve()
    path = (root / relative).resolve()
    if path != root and root not in path.parents:
        raise CampaignInputError(f"shard path escapes dataset root: {relative!r}")
    return path


@dataclass(frozen=True)
class VerifiedDataset:
    manifest_path: Path
    manifest_sha256: str
    fingerprint: str
    row_count: int
    shard_paths: tuple[Path, ...]
    shard_receipts: tuple[dict[str, Any], ...]
    manifest: dict[str, Any]

    def receipt(self) -> dict[str, Any]:
        return {
            "manifest_path": str(self.manifest_path),
            "manifest_sha256": self.manifest_sha256,
            "dataset_fingerprint_sha256": self.fingerprint,
            "row_count": self.row_count,
            "shards": list(self.shard_receipts),
        }


def verify_dataset_manifest(manifest_path: Path) -> VerifiedDataset:
    """Verify every shard before returning any path to the trainer."""
    manifest_path = manifest_path.resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CampaignInputError(f"cannot read dataset manifest: {manifest_path}") from exc

    shards = manifest.get("shards")
    if not isinstance(shards, list) or not shards:
        raise CampaignInputError("dataset manifest has no shard receipts")

    verified: list[dict[str, Any]] = []
    shard_paths: list[Path] = []
    total_rows = 0
    for index, raw in enumerate(shards):
        if not isinstance(raw, dict):
            raise CampaignInputError(f"shard receipt {index} is not an object")
        try:
            relative = str(raw["path"])
            expected_rows = int(raw["rows"])
            expected_bytes = int(raw["bytes"])
            expected_sha = str(raw["sha256"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CampaignInputError(f"invalid shard receipt {index}") from exc
        if len(expected_sha) != 64:
            raise CampaignInputError(f"invalid shard SHA-256: {relative}")
        path = _safe_child(manifest_path.parent, relative)
        if not path.is_file():
            raise CampaignInputError(f"missing dataset shard: {path}")
        actual_bytes = path.stat().st_size
        if actual_bytes != expected_bytes:
            raise CampaignInputError(
                f"shard byte mismatch for {relative}: {actual_bytes} != {expected_bytes}"
            )
        actual_sha = sha256_file(path)
        if actual_sha != expected_sha:
            raise CampaignInputError(f"shard SHA-256 mismatch: {relative}")
        actual_rows = count_jsonl_rows(path)
        if actual_rows != expected_rows:
            raise CampaignInputError(
                f"shard row mismatch for {relative}: {actual_rows} != {expected_rows}"
            )
        receipt = {
            "path": relative,
            "rows": actual_rows,
            "bytes": actual_bytes,
            "sha256": actual_sha,
        }
        verified.append(receipt)
        shard_paths.append(path)
        total_rows += actual_rows

    expected_rows = manifest.get("row_count")
    if total_rows != expected_rows:
        raise CampaignInputError(f"dataset row mismatch: {total_rows} != manifest {expected_rows}")
    fingerprint = dataset_fingerprint(verified)
    if fingerprint != manifest.get("dataset_fingerprint_sha256"):
        raise CampaignInputError("aggregate dataset fingerprint mismatch")
    return VerifiedDataset(
        manifest_path=manifest_path,
        manifest_sha256=sha256_file(manifest_path),
        fingerprint=fingerprint,
        row_count=total_rows,
        shard_paths=tuple(shard_paths),
        shard_receipts=tuple(verified),
        manifest=manifest,
    )


def stable_row_key(record_id: str, *, seed: int, namespace: str) -> str:
    return hashlib.sha256(f"{seed}:{namespace}:{record_id}".encode()).hexdigest()


def select_lowest_hash_indices(
    ids: Iterable[str], *, rows: int, seed: int, namespace: str
) -> list[int]:
    """Return the same lowest-hash subset independent of shard order."""
    if rows < 1:
        raise CampaignInputError("selected rows must be positive")
    ranked = sorted(
        enumerate(ids),
        key=lambda item: (
            stable_row_key(item[1], seed=seed, namespace=namespace),
            item[1],
        ),
    )
    if rows > len(ranked):
        raise CampaignInputError(f"selected rows {rows} exceed available rows {len(ranked)}")
    return [index for index, _ in ranked[:rows]]


def select_pilot_indices(ids: Iterable[str], *, rows: int, seed: int) -> list[int]:
    return select_lowest_hash_indices(ids, rows=rows, seed=seed, namespace="pilot")


def inventory_tree(root: Path) -> dict[str, Any]:
    """Content-address a file tree without following symlinks."""
    root = root.resolve()
    if not root.is_dir():
        raise CampaignInputError(f"inventory root is not a directory: {root}")
    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise CampaignInputError(f"inventory refuses symlink: {path}")
        if not path.is_file():
            continue
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    tree_digest = hashlib.sha256(
        "\n".join(f"{row['sha256']}  {row['path']}" for row in files).encode()
    ).hexdigest()
    return {
        "root": str(root),
        "file_count": len(files),
        "bytes": sum(row["bytes"] for row in files),
        "tree_sha256": tree_digest,
        "files": files,
    }
