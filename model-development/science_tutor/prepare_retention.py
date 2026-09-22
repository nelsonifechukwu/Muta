"""Select a small, recomputed quantitative rehearsal set from the existing artifact.

No fresh-test claim: these rows have already been exposed to previous pilots/full
runs. They may only enter training, never this campaign's development or holdout.
"""
from __future__ import annotations

import argparse
import heapq
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from build_dataset import canonical, digest, file_hash, write_json, write_rows

REPO = Path(__file__).resolve().parents[2]
MANIFEST_SHA = "93b7dbcbad72350e099d8951effcbc9a253693dc364b25ffc165102a6e844f4e"
EXCLUDE = {"profit", "average_speed", "inheritance", "population_density", "magnification"}


def build(args):
    sys.path.insert(0, str(REPO / "model-development/finetune"))
    from muta_dataset_v2.generators import verify_local_record
    if file_hash(args.manifest) != MANIFEST_SHA:
        raise ValueError("retention manifest differs from completed campaign")
    manifest = json.loads(args.manifest.read_text())
    candidates = defaultdict(list)
    source_receipts = []
    for shard in manifest["shards"]:
        path = args.manifest.parent / shard["path"]
        if file_hash(path) != shard["sha256"]:
            raise ValueError("retention shard hash mismatch")
        source_receipts.append(shard)
        with path.open() as handle:
            for line, value in enumerate(handle, 1):
                row = json.loads(value)
                p, v = row["provenance"], row["verification"]
                if p["source_id"] != "muta_verified_stem_v2" or row["subject"] not in {"mathematics", "physics", "chemistry"}:
                    continue
                if v.get("generator_name") in EXCLUDE or row["pedagogy"] != "worked_solution":
                    continue
                group = v.get("generator_name", "unknown")
                key = -int(digest(row["id"]), 16)
                entry = (key, row["id"], row, shard["path"], line, digest(value))
                heap = candidates[group]
                if len(heap) < args.per_family:
                    heapq.heappush(heap, entry)
                elif key > heap[0][0]:
                    heapq.heapreplace(heap, entry)
    output, rejected = [], []
    for family, entries in sorted(candidates.items()):
        for _, _, row, shard, line, line_sha in sorted(entries, reverse=True):
            if not verify_local_record(row):
                rejected.append({"id": row["id"], "reason": "programmatic_recomputation_failed"})
                continue
            output.append({
                "id": f'retention:{row["id"]}', "group_id": f'retention-task:{row["contamination"]["source_task_sha256"]}',
                "source": "muta_retention", "source_id": row["id"], "source_revision": MANIFEST_SHA,
                "license": "MIT", "subject": row["subject"], "source_split": "train",
                "capabilities": ["quantitative_reasoning", "worked_solution"],
                "quality": {"tier": "existing_programmatic_recomputed", "independent_verification": False,
                            "checks": ["existing_generator_verifier_reexecuted"],
                            "limits": ["Not a new independent verifier or universal semantic certification."]},
                "messages": row["messages"], "question": row["prompt"], "answer": row["answer"],
                "known_prior_training_exposure": True, "family": family,
                "original_verification": row["verification"],
                "original_row_location": {"shard": shard, "line": line, "raw_line_sha256": line_sha}})
    args.output.mkdir(parents=True, exist_ok=False)
    artifact = write_rows(args.output / "normalized.jsonl", output)
    write_json(args.output / "manifest.json", {"status": "candidate_train_only", "source_manifest_sha256": MANIFEST_SHA,
               "source_shards": source_receipts, "per_family_cap": args.per_family, "excluded_families": sorted(EXCLUDE),
               "artifact": artifact, "families": dict(Counter(r["family"] for r in output)), "rejected": rejected,
               "code_sha256": file_hash(Path(__file__)), "generator_code_sha256": file_hash(REPO / "model-development/finetune/muta_dataset_v2/generators.py")})
    print(json.dumps({"rows": len(output), "families": len(candidates), "rejected": len(rejected)}))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, default=REPO / "data/muta-stem-v2-sft-300k-quality-first-20260917-v1/manifest.json")
    p.add_argument("--output", type=Path, default=REPO / "data/muta-science-tutor-20260919/sources/muta_retention")
    p.add_argument("--per-family", type=int, default=40)
    build(p.parse_args())
