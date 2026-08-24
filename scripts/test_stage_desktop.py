from __future__ import annotations

import json
from argparse import Namespace

import pytest

from scripts import stage_desktop


def test_verify_rejects_extra_and_tampered_files(tmp_path):
    root = tmp_path / "stage"
    root.mkdir()
    member = root / "file.bin"
    member.write_bytes(b"trusted")
    manifest = {
        "schema": 1,
        "files": [
            {
                "path": "file.bin",
                "size_bytes": member.stat().st_size,
                "sha256": stage_desktop.sha256_file(member),
            }
        ],
    }
    (root / "desktop-manifest.json").write_text(json.dumps(manifest))
    stage_desktop.verify_root(root, "desktop-manifest.json")

    (root / "unexpected").write_text("no")
    with pytest.raises(stage_desktop.StageError, match="extra"):
        stage_desktop.verify_root(root, "desktop-manifest.json")
    (root / "unexpected").unlink()
    member.write_bytes(b"changed")
    with pytest.raises(stage_desktop.StageError, match="SHA-256|byte size"):
        stage_desktop.verify_root(root, "desktop-manifest.json")


def test_model_spec_rewrites_a_source_path_into_product_model_pack(tmp_path, monkeypatch):
    model = tmp_path / "muta-iq" / "model" / "winner.gguf"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"GGUF")
    args = Namespace(model_id="custom", model_file=str(model), mmproj_file=None)

    spec, source, projector = stage_desktop._model_spec(args)

    assert source == model
    assert projector is None
    assert spec["path"] == "models/core/winner.gguf"
    assert "muta-iq" not in spec["path"]


def test_safe_relative_rejects_parent_escape():
    with pytest.raises(stage_desktop.StageError, match="unsafe"):
        stage_desktop._safe_relative("../model.gguf")
