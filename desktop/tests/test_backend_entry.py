import hashlib
import json
from pathlib import Path

import pytest

from desktop import backend_entry


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bundle(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    resource = tmp_path / "resources"
    model_root = tmp_path / "model-pack"
    model = model_root / "models" / "core" / "core.gguf"
    projector = model_root / "models" / "core" / "mmproj.gguf"
    engine = (
        resource
        / "bin"
        / ("llama-server.exe" if __import__("sys").platform == "win32" else "llama-server")
    )
    for path in (model, projector, engine):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"test")
    (resource / "desktop-product.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "active_model": {
                    "path": "models/core/core.gguf",
                    "size_bytes": model.stat().st_size,
                    "sha256": _sha256(model),
                    "mmproj_path": "models/core/mmproj.gguf",
                    "mmproj_size_bytes": projector.stat().st_size,
                    "mmproj_sha256": _sha256(projector),
                },
            }
        )
    )
    return resource, model_root, model, engine


def test_configure_forces_offline_absolute_desktop_paths(tmp_path):
    resource, model_root, model, engine = _bundle(tmp_path)
    state = tmp_path / "state"
    args = backend_entry._parser().parse_args(
        [
            "--print-config",
            "--resource-root",
            str(resource),
            "--data-root",
            str(state),
            "--model-root",
            str(model_root),
            "--llama-server",
            str(engine),
            "--port",
            "19000",
            "--engine-port",
            "19080",
        ]
    )

    environment: dict[str, str] = {}
    values = backend_entry.configure(args, environment)

    assert values["MUTA_OFFLINE"] == "1"
    assert values["MUTA_ALLOW_MODEL_SWITCH"] == "1"
    assert values["MUTA_RT_AUTO_DOWNLOAD"] == "0"
    assert values["MUTA_RT_MODEL_DIR"] == str(model.parent)
    assert values["MUTA_MODEL_ROOT"] == str(model_root)
    assert values["MUTA_MODEL_SELECTION_PATH"] == str(state / "model-selection.json")
    assert values["MUTA_RT_DB_URL"].endswith("/state/muta.sqlite3")
    assert values["MUTA_LLAMA_SERVER_URL"] == "http://127.0.0.1:19080"
    assert environment == values
    assert (state / "logs").is_dir()
    assert not (resource / "data").exists()


def test_manifest_resource_escape_is_rejected(tmp_path):
    resource, model_root, _model, engine = _bundle(tmp_path)
    (resource / "desktop-product.json").write_text(
        json.dumps({"schema": 1, "active_model": {"path": "../outside.gguf"}})
    )
    args = backend_entry._parser().parse_args(
        [
            "--print-config",
            "--resource-root",
            str(resource),
            "--data-root",
            str(tmp_path / "state"),
            "--model-root",
            str(model_root),
            "--llama-server",
            str(engine),
        ]
    )

    with pytest.raises(ValueError, match="escapes"):
        backend_entry.configure(args)


def test_missing_product_manifest_fails_instead_of_guessing_a_model(tmp_path):
    resource = tmp_path / "resources"
    engine = resource / "bin" / "llama-server"
    engine.parent.mkdir(parents=True)
    engine.write_bytes(b"test")
    args = backend_entry._parser().parse_args(
        [
            "--print-config",
            "--resource-root",
            str(resource),
            "--data-root",
            str(tmp_path / "state"),
            "--llama-server",
            str(engine),
        ]
    )

    with pytest.raises(FileNotFoundError, match="product manifest"):
        backend_entry.configure(args)


def test_model_hash_mismatch_fails_closed(tmp_path):
    resource, model_root, model, engine = _bundle(tmp_path)
    model.write_bytes(b"tampered")
    args = backend_entry._parser().parse_args(
        [
            "--print-config",
            "--resource-root",
            str(resource),
            "--model-root",
            str(model_root),
            "--data-root",
            str(tmp_path / "state"),
            "--llama-server",
            str(engine),
        ]
    )

    with pytest.raises(ValueError, match="wrong byte size|SHA-256"):
        backend_entry.configure(args)


def test_inherited_engine_and_heartbeat_settings_are_not_used(tmp_path):
    resource, model_root, _model, engine = _bundle(tmp_path)
    args = backend_entry._parser().parse_args(
        [
            "--print-config",
            "--resource-root",
            str(resource),
            "--model-root",
            str(model_root),
            "--data-root",
            str(tmp_path / "state"),
            "--llama-server",
            str(engine),
        ]
    )
    environment = {
        "MUTA_RT_EXTRA_SERVER_ARGS": '["--dangerous"]',
        "MUTA_RT_MMPROJ_PATH": "/tmp/stale",
        "MUTA_FLEET_URL": "https://unexpected.example",
        "MUTA_FLEET_INGEST_KEY": "unexpected",
        "MUTA_CLOUD_URL": "https://unexpected.example",
        "MUTA_CLOUD_MODEL": "unexpected",
        "MUTA_CLOUD_API_KEY": "unexpected",
        "MUTA_SEARCH_URL": "https://unexpected.example",
        "MUTA_RT_HF_REPO": "unexpected/repo",
    }

    values = backend_entry.configure(args, environment)

    assert "MUTA_RT_EXTRA_SERVER_ARGS" not in environment
    assert "MUTA_FLEET_URL" not in environment
    assert "MUTA_CLOUD_URL" not in environment
    assert "MUTA_SEARCH_URL" not in environment
    assert "MUTA_RT_HF_REPO" not in environment
    assert values["MUTA_RT_MMPROJ_PATH"].endswith("mmproj.gguf")


def test_windows_uses_native_job_instead_of_posix_parent_watchdog():
    assert backend_entry._use_parent_watchdog(1234, "nt") is False
    assert backend_entry._use_parent_watchdog(1234, "posix") is True
    assert backend_entry._use_parent_watchdog(0, "posix") is False


def test_packaged_heartbeat_overrides_inherited_fleet_and_printing_redacts_key(
    tmp_path, monkeypatch, capsys
):
    # main() deliberately exports into the real process environment for the subsequently
    # imported gateway. Give it a per-test copy so those launcher variables cannot leak into
    # later lifespan/configuration tests in the same pytest process.
    monkeypatch.setattr(backend_entry.os, "environ", dict(backend_entry.os.environ))
    resource, model_root, _model, engine = _bundle(tmp_path)
    manifest_path = resource / "desktop-product.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["heartbeat"] = {
        "url": "https://fleet.example",
        "ingest_key": "write-only-secret",
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    argv = [
        "--print-config",
        "--resource-root",
        str(resource),
        "--model-root",
        str(model_root),
        "--data-root",
        str(tmp_path / "state"),
        "--llama-server",
        str(engine),
    ]

    assert backend_entry.main(argv) == 0
    printed = capsys.readouterr().out
    assert "https://fleet.example" in printed
    assert "write-only-secret" not in printed
    assert "<redacted>" in printed
