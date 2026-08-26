from __future__ import annotations

import pytest
from inspect_desktop_artifact import (
    CORE_MODELS,
    DEFAULT_MODEL_ID,
    verify_core_models,
    verify_required_heartbeat,
)


def test_release_heartbeat_requires_https_and_key() -> None:
    verify_required_heartbeat(
        {"heartbeat": {"url": "https://fleet.example.test", "ingest_key": "write-only"}}
    )
    with pytest.raises(RuntimeError, match="HTTPS"):
        verify_required_heartbeat(
            {"heartbeat": {"url": "http://fleet.example.test", "ingest_key": "write-only"}}
        )
    with pytest.raises(RuntimeError, match="key"):
        verify_required_heartbeat({"heartbeat": {"url": "https://fleet.example.test"}})


def test_core_model_inspection_binds_default_catalog_and_pack_hashes() -> None:
    models = []
    files = []
    for model_id, expected in CORE_MODELS.items():
        models.append(
            {
                "id": model_id,
                "kind": "local",
                **expected,
                "recommended": model_id == DEFAULT_MODEL_ID,
            }
        )
        files.append(
            {
                "path": expected["path"],
                "size_bytes": expected["size_bytes"],
                "sha256": expected["sha256"],
            }
        )
        if "mmproj_path" in expected:
            files.append(
                {
                    "path": expected["mmproj_path"],
                    "size_bytes": expected["mmproj_size_bytes"],
                    "sha256": expected["mmproj_sha256"],
                }
            )
    product = {"active_model": {"id": DEFAULT_MODEL_ID, **CORE_MODELS[DEFAULT_MODEL_ID]}}
    pack = {"active_model_id": DEFAULT_MODEL_ID, "files": files}

    verify_core_models(product, {"models": models}, pack)
    product["active_model"]["size_bytes"] += 1
    with pytest.raises(RuntimeError, match="active-model metadata"):
        verify_core_models(product, {"models": models}, pack)
    product["active_model"]["size_bytes"] = CORE_MODELS[DEFAULT_MODEL_ID]["size_bytes"]
    models[0]["sha256"] = "0" * 64
    with pytest.raises(RuntimeError, match="pinned release artifact"):
        verify_core_models(product, {"models": models}, pack)
    models[0]["sha256"] = CORE_MODELS[DEFAULT_MODEL_ID]["sha256"]
    pack["files"] = [
        item for item in files if item["path"] != CORE_MODELS["muta-tutor-qwen3.5-0.8b-q4_0"]["mmproj_path"]
    ]
    with pytest.raises(RuntimeError, match="projector is absent"):
        verify_core_models(product, {"models": models}, pack)
    pack["files"] = files
    pack["active_model_id"] = "muta-tutor-qwen3.5-0.8b-q4_0"
    with pytest.raises(RuntimeError, match="clean-start"):
        verify_core_models(product, {"models": models}, pack)
