from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

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


def _artifact(tmp_path: Path):
    rows = [b'{"id":"a"}\n', b'{"id":"b"}\n']
    shard = tmp_path / "part-00000.jsonl"
    shard.write_bytes(b"".join(rows))
    receipt = {
        "path": shard.name,
        "rows": 2,
        "bytes": shard.stat().st_size,
        "sha256": campaign_io.sha256_file(shard),
    }
    fingerprint = campaign_io.dataset_fingerprint([receipt])
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "row_count": 2,
                "dataset_fingerprint_sha256": fingerprint,
                "shards": [receipt],
            }
        )
    )
    return manifest, shard


def test_manifest_verification_binds_every_shard(tmp_path):
    manifest, shard = _artifact(tmp_path)
    verified = campaign_io.verify_dataset_manifest(manifest)
    assert verified.row_count == 2
    assert verified.shard_paths == (shard.resolve(),)
    assert verified.receipt()["manifest_sha256"] == campaign_io.sha256_file(manifest)


@pytest.mark.parametrize("mutation", ["bytes", "rows", "fingerprint"])
def test_manifest_verification_fails_closed(tmp_path, mutation):
    manifest, shard = _artifact(tmp_path)
    if mutation == "bytes":
        shard.write_bytes(shard.read_bytes() + b"x")
    else:
        payload = json.loads(manifest.read_text())
        if mutation == "rows":
            payload["shards"][0]["rows"] = 3
        else:
            payload["dataset_fingerprint_sha256"] = "0" * 64
        manifest.write_text(json.dumps(payload))
    with pytest.raises(campaign_io.CampaignInputError):
        campaign_io.verify_dataset_manifest(manifest)


def test_manifest_rejects_path_escape(tmp_path):
    manifest, _ = _artifact(tmp_path)
    payload = json.loads(manifest.read_text())
    payload["shards"][0]["path"] = "../escape.jsonl"
    manifest.write_text(json.dumps(payload))
    with pytest.raises(campaign_io.CampaignInputError, match="escapes"):
        campaign_io.verify_dataset_manifest(manifest)


def test_pilot_selection_is_order_independent_and_exact():
    ids = ["row-3", "row-1", "row-2", "row-4"]
    selected = campaign_io.select_pilot_indices(ids, rows=2, seed=3407)
    selected_ids = {ids[index] for index in selected}
    reversed_ids = list(reversed(ids))
    reversed_selected = campaign_io.select_pilot_indices(reversed_ids, rows=2, seed=3407)
    assert selected_ids == {reversed_ids[index] for index in reversed_selected}
    assert len(selected_ids) == 2


def test_tree_inventory_is_sorted_and_content_addressed(tmp_path):
    (tmp_path / "b").write_text("two")
    (tmp_path / "a").write_text("one")
    inventory = campaign_io.inventory_tree(tmp_path)
    assert [row["path"] for row in inventory["files"]] == ["a", "b"]
    expected = hashlib.sha256(
        "\n".join(f"{row['sha256']}  {row['path']}" for row in inventory["files"]).encode()
    ).hexdigest()
    assert inventory["tree_sha256"] == expected
