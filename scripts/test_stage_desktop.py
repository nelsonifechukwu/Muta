from __future__ import annotations

import hashlib
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


def test_desktop_defaults_name_both_core_models_and_select_qwen25():
    args = stage_desktop._parser().parse_args(
        [
            "stage",
            "--app-output",
            "/tmp/app",
            "--model-output",
            "/tmp/models",
            "--engine-dir",
            "/tmp/engine",
            "--model-pack-id",
            "test-pack",
            "--version",
            "0.1.449",
            "--git-sha",
            "a" * 40,
            "--target-os",
            "macos",
            "--target-arch",
            "aarch64",
        ]
    )

    assert args.model_id == "qwen2.5-1.5b-instruct-q4_k_m"
    assert args.bundled_model_id == ["muta-tutor-qwen3.5-0.8b-q4_0"]


def test_stage_writes_both_core_models_and_qwen25_clean_start(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    qwen25 = root / "models-src/Muta-Tutor-Qwen2.5-1.5B-Finetuned-Q4_K_M.gguf"
    qwen35 = root / "models-src/muta-tutor-qwen3.5-0.8b-q4_0.gguf"
    projector = root / "models-src/Qwen3.5-0.8B-mmproj-F16.gguf"
    for path, body in ((qwen25, b"qwen25"), (qwen35, b"qwen35"), (projector, b"projector")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    catalog = {
        "schema_version": 1,
        "models": [
            {
                "id": stage_desktop.DEFAULT_MODEL_ID,
                "label": "Qwen2.5",
                "kind": "local",
                "path": qwen25.relative_to(root).as_posix(),
                "size_bytes": qwen25.stat().st_size,
                "sha256": hashlib.sha256(qwen25.read_bytes()).hexdigest(),
                "recommended": True,
            },
            {
                "id": stage_desktop.SECONDARY_CORE_MODEL_ID,
                "label": "Qwen3.5",
                "kind": "local",
                "path": qwen35.relative_to(root).as_posix(),
                "size_bytes": qwen35.stat().st_size,
                "sha256": hashlib.sha256(qwen35.read_bytes()).hexdigest(),
                "recommended": False,
                "mmproj_path": projector.relative_to(root).as_posix(),
                "mmproj_size_bytes": projector.stat().st_size,
                "mmproj_sha256": hashlib.sha256(projector.read_bytes()).hexdigest(),
            },
        ],
    }
    (root / "runtime").mkdir()
    (root / "runtime/model-catalog.json").write_text(json.dumps(catalog))
    for relative in ("ui/dist/index.html", "landing/index.html"):
        path = root / relative
        path.parent.mkdir(parents=True)
        path.write_text(relative)
    engine = root / "engine/llama-server"
    engine.parent.mkdir()
    engine.write_bytes(b"engine")
    app_output = tmp_path / "app"
    model_output = tmp_path / "model-pack"
    args = Namespace(
        app_output=app_output,
        model_output=model_output,
        engine_dir=engine.parent,
        ffmpeg_bin=None,
        model_id=stage_desktop.DEFAULT_MODEL_ID,
        bundled_model_id=[stage_desktop.SECONDARY_CORE_MODEL_ID],
        model_file=None,
        mmproj_file=None,
        model_pack_id="test-pack",
        version="0.1.449",
        git_sha="a" * 40,
        target_os="macos",
        target_arch="aarch64",
        include_optional_models=False,
        heartbeat_url="",
        heartbeat_ingest_key="",
    )
    monkeypatch.setattr(stage_desktop, "REPO_ROOT", root)

    stage_desktop.stage(args)

    product = json.loads((app_output / "desktop-product.json").read_text())
    staged_catalog = json.loads((app_output / "runtime/model-catalog.json").read_text())
    pack = json.loads((model_output / "model-pack.json").read_text())
    assert product["active_model"]["id"] == stage_desktop.DEFAULT_MODEL_ID
    assert pack["active_model_id"] == stage_desktop.DEFAULT_MODEL_ID
    assert [model["id"] for model in staged_catalog["models"]] == [
        stage_desktop.DEFAULT_MODEL_ID,
        stage_desktop.SECONDARY_CORE_MODEL_ID,
    ]
    assert {entry["path"] for entry in pack["files"]} >= {
        "models/core/Muta-Tutor-Qwen2.5-1.5B-Finetuned-Q4_K_M.gguf",
        "models/core/muta-tutor-qwen3.5-0.8b-q4_0.gguf",
    }


def test_safe_relative_rejects_parent_escape():
    with pytest.raises(stage_desktop.StageError, match="unsafe"):
        stage_desktop._safe_relative("../model.gguf")
