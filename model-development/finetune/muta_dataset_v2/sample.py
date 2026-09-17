"""Create a small, deterministic, stratified review sample from built shards."""

from __future__ import annotations

import argparse
import hashlib
import heapq
import json
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .core import index_source_registry_document, normalize_text, sha256_file, validate_record

DEFAULT_STRATA = ("subject", "pedagogy")
STRATUM_ACCESSORS: dict[str, Callable[[dict[str, Any]], str]] = {
    "source": lambda record: record["provenance"]["source_id"],
    "semantic_cluster": lambda record: record["provenance"]["semantic_cluster_id"],
    "subject": lambda record: record["subject"],
    "topic": lambda record: record["topic"],
    "difficulty": lambda record: record["difficulty"],
    "pedagogy": lambda record: record["pedagogy"],
}


def _rank(seed: int, record_id: str) -> int:
    return int(hashlib.sha256(f"{seed}:{record_id}".encode()).hexdigest(), 16)


def _normalize_strata(strata: Sequence[str]) -> tuple[str, ...]:
    if isinstance(strata, str):
        raise TypeError("strata must be a sequence of field names, not one string")
    normalized = tuple(stratum.strip().lower() for stratum in strata)
    if not normalized:
        raise ValueError("at least one stratum is required")
    unknown = sorted(set(normalized).difference(STRATUM_ACCESSORS))
    if unknown:
        allowed = ", ".join(STRATUM_ACCESSORS)
        raise ValueError(f"unsupported strata {unknown!r}; allowed fields: {allowed}")
    if len(set(normalized)) != len(normalized):
        raise ValueError("strata must not contain duplicate fields")
    return normalized


def _cell_for(record: dict[str, Any], strata: tuple[str, ...]) -> tuple[str, ...]:
    values = tuple(STRATUM_ACCESSORS[stratum](record) for stratum in strata)
    if not all(isinstance(value, str) and value for value in values):
        raise ValueError(f"record {record.get('id', '<unknown>')} has an invalid stratum value")
    return values


def _cell_label(strata: tuple[str, ...], cell: tuple[str, ...]) -> str:
    return "::".join(f"{stratum}={value}" for stratum, value in zip(strata, cell))


def _resolve_shard_path(input_dir: Path, relative_path: str) -> Path:
    if not isinstance(relative_path, str) or not relative_path:
        raise ValueError("source manifest contains an invalid shard path")
    input_root = input_dir.resolve()
    shard_path = (input_dir / relative_path).resolve()
    if shard_path == input_root or input_root not in shard_path.parents:
        raise ValueError(f"source shard path escapes input directory: {relative_path}")
    return shard_path


def _assert_live_validator_matches_artifact(source_manifest: dict[str, Any]) -> None:
    """Fail closed instead of reinterpreting an old artifact with changed validators."""

    expected = {
        receipt.get("path"): receipt.get("sha256")
        for receipt in source_manifest.get("inputs", {}).get("code", ())
        if isinstance(receipt, dict)
    }
    for name in ("core.py", "generators.py", "tokenization.py"):
        expected_hash = expected.get(name)
        if not isinstance(expected_hash, str):
            raise TypeError(f"source manifest omits archived validator receipt for {name}")
        live_hash = sha256_file(Path(__file__).with_name(name))
        if live_hash != expected_hash:
            raise ValueError(
                f"live validator {name} differs from the source artifact; "
                "run the sampler from the artifact's archived code environment"
            )


def build_sample(
    *,
    input_dir: Path,
    output: Path,
    manifest_output: Path,
    rows_per_cell: int,
    seed: int,
    strata: Sequence[str] = DEFAULT_STRATA,
    revalidate_rows: bool = True,
    source_filter: Sequence[str] | None = None,
) -> dict[str, Any]:
    if rows_per_cell <= 0:
        raise ValueError("rows_per_cell must be positive")
    strata = _normalize_strata(strata)
    normalized_source_filter = None
    if source_filter is not None:
        if isinstance(source_filter, str):
            raise TypeError("source_filter must be a sequence of source IDs, not one string")
        normalized_source_filter = tuple(dict.fromkeys(value.strip() for value in source_filter))
        if not normalized_source_filter or not all(normalized_source_filter):
            raise ValueError("source_filter must contain at least one non-empty source ID")
    if output.resolve() == manifest_output.resolve():
        raise ValueError("sample and manifest outputs must be different files")
    if output.exists() or manifest_output.exists():
        raise FileExistsError("refusing to overwrite an existing sample or sample manifest")

    source_manifest_path = input_dir / "manifest.json"
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    schema_validator = None
    source_registry = None
    source_policy = None
    if revalidate_rows:
        _assert_live_validator_matches_artifact(source_manifest)
        schema_path = _resolve_shard_path(
            input_dir, source_manifest["inputs"]["schema"]["archive_path"]
        )
        registry_path = _resolve_shard_path(
            input_dir, source_manifest["inputs"]["source_registry"]["archive_path"]
        )
        schema_validator = Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8")))
        source_registry_document = json.loads(registry_path.read_text(encoding="utf-8"))
        source_registry = index_source_registry_document(source_registry_document)
        source_policy = source_registry_document["policy"]
    heaps: dict[tuple[str, ...], list[tuple[int, int, str, dict[str, Any]]]] = defaultdict(list)
    population_by_cell: Counter[tuple[str, ...]] = Counter()
    verified_shards: list[dict[str, Any]] = []
    sequence = 0
    seen_record_ids: set[str] = set()
    seen_rendered_prompts: set[str] = set()
    source_task_owner: dict[str, str] = {}
    encountered_sources: set[str] = set()

    manifest_shard_paths = [str(shard["path"]) for shard in source_manifest["shards"]]
    if len(manifest_shard_paths) != len(set(manifest_shard_paths)):
        raise ValueError("source manifest lists a shard more than once")
    discovered_shards = {
        path.resolve().relative_to(input_dir.resolve()).as_posix()
        for path in input_dir.rglob("part-*.jsonl")
        if path.is_file()
    }
    if discovered_shards != set(manifest_shard_paths):
        missing = sorted(set(manifest_shard_paths) - discovered_shards)
        unlisted = sorted(discovered_shards - set(manifest_shard_paths))
        raise ValueError(f"source shard coverage mismatch; missing={missing}, unlisted={unlisted}")
    partials = sorted(
        path.resolve().relative_to(input_dir.resolve()).as_posix()
        for path in input_dir.rglob("part-*.jsonl.partial")
        if path.is_file()
    )
    if partials:
        raise ValueError(f"source directory contains partial shards: {partials}")

    for shard in source_manifest["shards"]:
        shard_path = _resolve_shard_path(input_dir, shard["path"])
        actual_sha256 = sha256_file(shard_path)
        if actual_sha256 != shard["sha256"]:
            raise ValueError(f"source shard hash mismatch: {shard_path}")
        actual_bytes = shard_path.stat().st_size
        if actual_bytes != shard["bytes"]:
            raise ValueError(f"source shard byte count mismatch: {shard_path}")
        shard_row_count = 0
        with shard_path.open(encoding="utf-8") as handle:
            for line in handle:
                shard_row_count += 1
                record = json.loads(line)
                if revalidate_rows:
                    assert schema_validator is not None and source_registry is not None
                    validation_errors = validate_record(
                        record,
                        source_registry=source_registry,
                        source_policy=source_policy,
                    )
                    schema_errors = sorted(
                        schema_validator.iter_errors(record), key=lambda error: list(error.path)
                    )
                    if validation_errors or schema_errors:
                        details = validation_errors + [error.message for error in schema_errors]
                        raise ValueError(
                            f"source row {record.get('id')} failed revalidation: {details}"
                        )
                source_id = record["provenance"]["source_id"]
                encountered_sources.add(source_id)
                if revalidate_rows:
                    record_id = record["id"]
                    rendered_prompt = normalize_text(record["prompt"])
                    source_task_hash = record["contamination"]["source_task_sha256"]
                    if record_id in seen_record_ids:
                        raise ValueError(f"source dataset repeats record id {record_id}")
                    if rendered_prompt in seen_rendered_prompts:
                        raise ValueError(f"source dataset repeats rendered prompt at {record_id}")
                    prior_owner = source_task_owner.get(source_task_hash)
                    if prior_owner is not None and prior_owner != source_id:
                        raise ValueError(
                            f"source dataset repeats canonical task across {prior_owner} and {source_id}"
                        )
                    seen_record_ids.add(record_id)
                    seen_rendered_prompts.add(rendered_prompt)
                    source_task_owner.setdefault(source_task_hash, source_id)
                if (
                    normalized_source_filter is not None
                    and source_id not in normalized_source_filter
                ):
                    continue
                cell = _cell_for(record, strata)
                population_by_cell[cell] += 1
                rank = _rank(seed, record["id"])
                # The monotonically increasing sequence is a deterministic tie-breaker
                # and prevents Python from ever trying to compare record dictionaries.
                item = (-rank, -sequence, record["id"], record)
                sequence += 1
                heap = heaps[cell]
                if len(heap) < rows_per_cell:
                    heapq.heappush(heap, item)
                elif item > heap[0]:
                    heapq.heapreplace(heap, item)
        if shard_row_count != shard["rows"]:
            raise ValueError(f"source shard row count mismatch: {shard_path}")
        verified_shards.append(
            {
                "path": shard["path"],
                "rows": shard_row_count,
                "bytes": actual_bytes,
                "sha256": actual_sha256,
            }
        )

    verified_row_count = sum(shard["rows"] for shard in verified_shards)
    if verified_row_count != source_manifest["row_count"]:
        raise ValueError("source manifest total row count does not match its shards")
    verified_fingerprint = hashlib.sha256(
        "\n".join(shard["sha256"] for shard in verified_shards).encode("ascii")
    ).hexdigest()
    if verified_fingerprint != source_manifest["dataset_fingerprint_sha256"]:
        raise ValueError("source manifest aggregate dataset fingerprint mismatch")
    if normalized_source_filter is not None:
        missing_sources = sorted(set(normalized_source_filter) - encountered_sources)
        if missing_sources:
            raise ValueError(f"source filter IDs are absent from the dataset: {missing_sources}")

    selected = [(cell, item) for cell, heap in heaps.items() for item in heap]
    selected.sort(
        key=lambda selected_item: (selected_item[0], -selected_item[1][0], selected_item[1][1])
    )
    records = [item[3] for _, item in selected]
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")

    selected_by_cell = Counter(_cell_for(row, strata) for row in records)
    counts = {
        "source": dict(sorted(Counter(row["provenance"]["source_id"] for row in records).items())),
        "subject": dict(sorted(Counter(row["subject"] for row in records).items())),
        "pedagogy": dict(sorted(Counter(row["pedagogy"] for row in records).items())),
        "strata_cells": dict(
            sorted((_cell_label(strata, cell), count) for cell, count in selected_by_cell.items())
        ),
    }
    if strata == DEFAULT_STRATA:
        counts["subject_pedagogy"] = dict(
            sorted(Counter(f"{row['subject']}::{row['pedagogy']}" for row in records).items())
        )
    manifest = {
        "schema_version": 1,
        "sample_rows": len(records),
        "strata": list(strata),
        "stratum_cell_count": len(heaps),
        "complete_stratum_cell_count": sum(
            count >= rows_per_cell for count in population_by_cell.values()
        ),
        "underfilled_stratum_cell_count": sum(
            count < rows_per_cell for count in population_by_cell.values()
        ),
        "rows_per_cell": rows_per_cell,
        "seed": seed,
        "source_filter": list(normalized_source_filter) if normalized_source_filter else None,
        "selection": "lowest SHA-256(seed:record_id) rank per named stratum cell",
        "source_dataset_fingerprint_sha256": source_manifest["dataset_fingerprint_sha256"],
        "source_manifest_sha256": sha256_file(source_manifest_path),
        "source_shard_verification": {
            "algorithm": "sha256",
            "verified": True,
            "row_count": verified_row_count,
            "dataset_fingerprint_sha256": verified_fingerprint,
            "complete_part_file_coverage": True,
            "shard_count": len(verified_shards),
            "shards": verified_shards,
        },
        "source_row_revalidation": {
            "verified": revalidate_rows,
            "rows": verified_row_count if revalidate_rows else 0,
            "schema": revalidate_rows,
            "identity_and_provenance": revalidate_rows,
            "local_generator_regeneration": revalidate_rows,
            "duplicate_record_ids": 0,
            "duplicate_rendered_prompts": 0,
            "cross_source_canonical_task_duplicates": 0,
            "holdout_replay": (
                "stored normalized hashes and holdout_checked flags revalidated; the complete "
                "remote holdout corpus was not fetched again by the offline sampler"
            ),
            "token_recount": (
                "pinned tokenizer metadata and limits revalidated; exact tokenization was not "
                "recomputed by the sampler"
            ),
        },
        "output": {
            "path": output.name,
            "bytes": output.stat().st_size,
            "sha256": sha256_file(output),
        },
        "counts": counts,
    }
    if strata == DEFAULT_STRATA:
        manifest["rows_per_subject_pedagogy_cell"] = rows_per_cell
    with manifest_output.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest-output", required=True, type=Path)
    parser.add_argument("--rows-per-cell", type=int, default=5)
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument(
        "--source",
        action="append",
        dest="source_filter",
        help="sample only this source ID; repeat to include multiple sources",
    )
    parser.add_argument(
        "--strata",
        nargs="+",
        choices=tuple(STRATUM_ACCESSORS),
        default=list(DEFAULT_STRATA),
        help="allowlisted fields defining each sample cell (default: subject pedagogy)",
    )
    args = parser.parse_args(argv)
    if args.rows_per_cell <= 0:
        parser.error("--rows-per-cell must be positive")
    try:
        args.strata = _normalize_strata(args.strata)
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = build_sample(
        input_dir=args.input,
        output=args.output,
        manifest_output=args.manifest_output,
        rows_per_cell=args.rows_per_cell,
        seed=args.seed,
        strata=args.strata,
        source_filter=args.source_filter,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
