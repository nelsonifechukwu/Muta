from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


campaign_io = _load("campaign_io")
builder = _load("build_round2_dev")


def _row(i: int, *, source="muta_verified_stem_v2", selected=False):
    return {
        "id": f"row-{i}",
        "prompt": f"p{i}",
        "completion": f"c{i}",
        "mode": "chat",
        "split": "train",
        "subject": "mathematics",
        "pedagogy": "worked_solution",
        "provenance": {"source_id": source},
        "verification": {"training_eligible": True},
        "contamination": {
            "source_task_sha256": f"task-{i if not selected else 0}",
            "normalized_prompt_sha256": f"prompt-{i}",
        },
    }


def _artifact(path: Path, rows: list[dict]):
    path.mkdir()
    shard = path / "part.jsonl"
    shard.write_text("".join(json.dumps(row) + "\n" for row in rows))
    receipt = {
        "path": shard.name,
        "rows": len(rows),
        "bytes": shard.stat().st_size,
        "sha256": campaign_io.sha256_file(shard),
    }
    manifest = {
        "row_count": len(rows),
        "dataset_fingerprint_sha256": campaign_io.dataset_fingerprint([receipt]),
        "shards": [receipt],
    }
    target = path / "manifest.json"
    target.write_text(json.dumps(manifest))
    return target


def test_build_is_deterministic_and_excludes_training_overlap(tmp_path):
    selected_rows = [_row(0), _row(100, source="deepmind_mathematics")]
    warehouse_rows = (
        selected_rows
        + [_row(i) for i in range(1, 8)]
        + [_row(i, source="deepmind_mathematics") for i in range(101, 108)]
    )
    selected = _artifact(tmp_path / "selected", selected_rows)
    warehouse = _artifact(tmp_path / "warehouse", warehouse_rows)
    first = builder.build(
        selected_manifest=selected,
        warehouse_manifest=warehouse,
        output=tmp_path / "dev-a",
        rows=4,
        seed=3407,
    )
    second = builder.build(
        selected_manifest=selected,
        warehouse_manifest=warehouse,
        output=tmp_path / "dev-b",
        rows=4,
        seed=3407,
    )
    assert first["shards"][0]["sha256"] == second["shards"][0]["sha256"]
    dev_rows = [
        json.loads(line) for line in (tmp_path / "dev-a" / "dev.jsonl").read_text().splitlines()
    ]
    assert len(dev_rows) == 4
    assert {row["id"] for row in dev_rows}.isdisjoint({"row-0", "row-100"})
    assert first["counts"]["source"] == {
        "deepmind_mathematics": 2,
        "muta_verified_stem_v2": 2,
    }
