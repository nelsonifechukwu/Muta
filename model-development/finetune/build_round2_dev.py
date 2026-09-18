#!/usr/bin/env python3
"""Build a deterministic, non-overlapping development set for Muta round two."""

from __future__ import annotations

import argparse
import hashlib
import heapq
import json
from collections import Counter
from pathlib import Path
from typing import Any

from campaign_io import dataset_fingerprint, sha256_file, verify_dataset_manifest

OPEN_SOURCES = frozenset({"muta_verified_stem_v2", "deepmind_mathematics"})


def _iter_rows(paths: tuple[Path, ...]):
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid JSON at {path}:{line_number}") from exc


def _cell(row: dict) -> tuple[str, str, str]:
    return (
        str(row["provenance"]["source_id"]),
        str(row["subject"]),
        str(row["pedagogy"]),
    )


def _largest_remainder(counts: Counter, total: int) -> dict[tuple[str, str, str], int]:
    denominator = sum(counts.values())
    if denominator < 1 or total < 1:
        raise ValueError("cannot allocate an empty development set")
    exact = {cell: total * count / denominator for cell, count in counts.items()}
    quotas = {cell: int(value) for cell, value in exact.items()}
    remaining = total - sum(quotas.values())
    order = sorted(counts, key=lambda cell: (-(exact[cell] - quotas[cell]), cell))
    for cell in order[:remaining]:
        quotas[cell] += 1
    return {cell: quota for cell, quota in quotas.items() if quota}


def _rank(seed: int, record_id: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}:round2-dev:{record_id}".encode()).digest(), "big")


def build(
    *,
    selected_manifest: Path,
    warehouse_manifest: Path,
    output: Path,
    rows: int,
    seed: int,
) -> dict[str, Any]:
    selected = verify_dataset_manifest(selected_manifest)
    warehouse = verify_dataset_manifest(warehouse_manifest)
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    data_path = output / "dev.jsonl"
    manifest_path = output / "manifest.json"
    if data_path.exists() or manifest_path.exists():
        raise FileExistsError(f"development artifact already exists: {output}")

    selected_ids: set[str] = set()
    selected_tasks: set[str] = set()
    selected_prompts: set[str] = set()
    selected_cell_counts: Counter = Counter()
    for record in _iter_rows(selected.shard_paths):
        record_id = str(record["id"])
        task_hash = str(record["contamination"]["source_task_sha256"])
        prompt_hash = str(record["contamination"]["normalized_prompt_sha256"])
        if record_id in selected_ids:
            raise ValueError(f"duplicate selected record ID: {record_id}")
        selected_ids.add(record_id)
        selected_tasks.add(task_hash)
        selected_prompts.add(prompt_hash)
        if record["provenance"]["source_id"] in OPEN_SOURCES:
            selected_cell_counts[_cell(record)] += 1
    quotas = _largest_remainder(selected_cell_counts, rows)

    heaps: dict[tuple[str, str, str], list[tuple[int, str, dict]]] = {cell: [] for cell in quotas}
    exclusions = Counter()
    candidate_counts = Counter()
    for record in _iter_rows(warehouse.shard_paths):
        source = record.get("provenance", {}).get("source_id")
        if source not in OPEN_SOURCES:
            exclusions["non_open_source"] += 1
            continue
        if record.get("split") != "train":
            exclusions["non_train_split"] += 1
            continue
        if record.get("verification", {}).get("training_eligible") is not True:
            exclusions["not_training_eligible"] += 1
            continue
        record_id = str(record["id"])
        contamination = record.get("contamination", {})
        task_hash = str(contamination.get("source_task_sha256"))
        prompt_hash = str(contamination.get("normalized_prompt_sha256"))
        if record_id in selected_ids:
            exclusions["selected_record_id"] += 1
            continue
        if task_hash in selected_tasks:
            exclusions["selected_source_task"] += 1
            continue
        if prompt_hash in selected_prompts:
            exclusions["selected_normalized_prompt"] += 1
            continue
        cell = _cell(record)
        quota = quotas.get(cell)
        if not quota:
            exclusions["unallocated_cell"] += 1
            continue
        candidate_counts[cell] += 1
        rank = _rank(seed, record_id)
        item = (-rank, record_id, record)
        heap = heaps[cell]
        if len(heap) < quota:
            heapq.heappush(heap, item)
        elif item > heap[0]:
            heapq.heapreplace(heap, item)

    shortfalls = {
        " :: ".join(cell): quotas[cell] - len(heaps[cell])
        for cell in quotas
        if len(heaps[cell]) != quotas[cell]
    }
    if shortfalls:
        raise ValueError(f"development quota shortfalls: {shortfalls}")

    chosen = [item for heap in heaps.values() for item in heap]
    chosen.sort(key=lambda item: (-item[0], item[1]))
    records = [item[2] for item in chosen]
    if len(records) != rows:
        raise ValueError(f"selected {len(records)} development rows, expected {rows}")
    ids = [str(record["id"]) for record in records]
    tasks = [record["contamination"]["source_task_sha256"] for record in records]
    prompts = [record["contamination"]["normalized_prompt_sha256"] for record in records]
    if len(ids) != len(set(ids)) or set(tasks) & selected_tasks or set(prompts) & selected_prompts:
        raise ValueError("development overlap invariant failed")

    with data_path.open("x", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    shard = {
        "path": data_path.name,
        "rows": rows,
        "bytes": data_path.stat().st_size,
        "sha256": sha256_file(data_path),
    }
    output_counts = {
        "source": dict(sorted(Counter(row["provenance"]["source_id"] for row in records).items())),
        "subject": dict(sorted(Counter(row["subject"] for row in records).items())),
        "pedagogy": dict(sorted(Counter(row["pedagogy"] for row in records).items())),
        "cell": {
            " :: ".join(cell): count
            for cell, count in sorted(Counter(_cell(row) for row in records).items())
        },
    }
    manifest = {
        "schema_version": 1,
        "artifact": "muta-round2-representative-development",
        "seed": seed,
        "row_count": rows,
        "dataset_fingerprint_sha256": dataset_fingerprint([shard]),
        "shards": [shard],
        "selection": {
            "method": "lowest SHA-256(seed:round2-dev:record_id) per proportional source-subject-pedagogy cell",
            "open_sources": sorted(OPEN_SOURCES),
            "selected_record_overlap": 0,
            "selected_source_task_overlap": 0,
            "selected_normalized_prompt_overlap": 0,
            "quotas": {" :: ".join(cell): value for cell, value in sorted(quotas.items())},
            "candidate_counts": {
                " :: ".join(cell): value for cell, value in sorted(candidate_counts.items())
            },
            "exclusions": dict(sorted(exclusions.items())),
        },
        "counts": output_counts,
        "inputs": {
            "selected": selected.receipt(),
            "warehouse": warehouse.receipt(),
            "script_sha256": sha256_file(Path(__file__)),
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selected-manifest", type=Path, required=True)
    parser.add_argument("--warehouse-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rows", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=3407)
    args = parser.parse_args()
    print(json.dumps(build(**vars(args)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
