from __future__ import annotations

import hashlib
import json

import publish_desktop_model_addons as addons


def test_publishes_optional_models_but_not_the_base_archive_model(tmp_path, monkeypatch):
    root = tmp_path / "source"
    (root / "runtime").mkdir(parents=True)
    (root / "models").mkdir()
    base = root / "models/base.gguf"
    extra = root / "models/extra.gguf"
    base.write_bytes(b"base")
    extra.write_bytes(b"extra")
    digest = hashlib.sha256(extra.read_bytes()).hexdigest()
    (root / "runtime/model-catalog.json").write_text(
        json.dumps(
            {
                "models": [
                    {
                        "id": addons.BASE_MODEL_ID,
                        "kind": "local",
                        "path": "models/base.gguf",
                    },
                    {
                        "id": "extra",
                        "label": "Extra",
                        "kind": "local",
                        "path": "models/extra.gguf",
                        "size_bytes": 5,
                        "sha256": digest,
                        "description": "optional",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    commands = []
    monkeypatch.setattr(addons, "exists", lambda _uri: False)
    monkeypatch.setattr(addons, "run", lambda command, **_kwargs: commands.append(command))

    manifest = addons.publish(root, "bucket", "a" * 40)

    assert [item["id"] for item in manifest["models"]] == ["extra"]
    assert manifest["models"][0]["install_path"] == "model-pack/models/custom/extra.gguf"
    expected_object = f"gs://bucket/model-addons/v1/extra/{digest}/extra.gguf"
    assert manifest["models"][0]["gcs_uri"] == expected_object
    assert any(command[-1] == expected_object for command in commands)
