from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from scripts import desktop_cache_changes, desktop_cache_key
from scripts import verify_desktop_models as models
from scripts.freeze_desktop_gateway import FreezeError, validate_gateway


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(root: Path, relative: str, data: bytes) -> dict:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"path": relative, "bytes": len(data), "sha256": _sha(data)}


def test_model_cache_verifier_checks_product_and_optional_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(models, "REPO_ROOT", tmp_path)
    product = _write(tmp_path, "muta-iq/model/product.gguf", b"product")
    projector = _write(tmp_path, "models/mmproj/projector.gguf", b"projector")
    catalog = {
        "models": [
            {
                "id": models.PRODUCT_MODEL_ID,
                "path": product["path"],
                "size_bytes": product["bytes"],
                "sha256": product["sha256"],
                "mmproj_path": projector["path"],
                "mmproj_size_bytes": projector["bytes"],
                "mmproj_sha256": projector["sha256"],
            }
        ]
    }
    (tmp_path / "runtime").mkdir()
    (tmp_path / "runtime/model-catalog.json").write_text(json.dumps(catalog))

    artifacts = []
    for name in sorted(models.OPTIONAL_ARTIFACTS):
        entry = _write(tmp_path, f"models/{name}/{name}.bin", name.encode())
        artifacts.append({"name": name, "fetched": True, **entry})
    (tmp_path / "models/MANIFEST.json").write_text(json.dumps({"artifacts": artifacts}))
    for name in models.REQUIRED_LICENSES:
        _write(tmp_path, f"models/LICENSES/{name}", b"license")

    models.verify()
    (tmp_path / "models/embed/embed.bin").write_bytes(b"corrupt")
    with pytest.raises(models.VerificationError, match="wrong size"):
        models.verify()


def test_gateway_cache_key_changes_with_backend_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(desktop_cache_key, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(desktop_cache_key.importlib.metadata, "distributions", list)
    (tmp_path / "desktop").mkdir()
    source = tmp_path / "desktop/backend_entry.py"
    source.write_text("VALUE = 1\n")
    first = desktop_cache_key.gateway_key()
    source.write_text("VALUE = 2\n")
    assert desktop_cache_key.gateway_key() != first


def test_cache_change_classifier_keeps_layers_independent() -> None:
    ui = desktop_cache_changes.classify(["ui/styles.css"])
    assert ui == {"models": False, "ui": True, "native": False, "gateway": False}
    python = desktop_cache_changes.classify(["orchestrator/main.py"])
    assert python == {"models": False, "ui": False, "native": False, "gateway": True}
    catalog = desktop_cache_changes.classify(["runtime/model-catalog.json"])
    assert catalog == {"models": True, "ui": False, "native": False, "gateway": True}
    workflow = desktop_cache_changes.classify([".github/workflows/desktop-cache.yml"])
    assert all(workflow.values())


def test_macos_native_build_maps_aarch64_to_apple_arm64() -> None:
    script = (desktop_cache_key.REPO_ROOT / "scripts/build_desktop_native.sh").read_text()
    assert 'if [ "$(uname -s)" = "Darwin" ] && [ "$apple_arch" = "aarch64" ]' in script
    assert 'apple_arch="arm64"' in script
    assert '-DCMAKE_OSX_ARCHITECTURES="$apple_arch"' in script
    assert '--cc="clang -arch $apple_arch"' in script
    assert "ffmpeg_target_args" not in script
    assert "configure_ffmpeg()" in script
    assert 'macos_min="${MACOSX_DEPLOYMENT_TARGET:-$MUTA_MACOS_DEPLOYMENT_TARGET}"' in script
    assert '--extra-ldflags="-mmacosx-version-min=$macos_min"' in script


def test_macos_native_verifier_maps_aarch64_to_apple_arm64() -> None:
    script = (desktop_cache_key.REPO_ROOT / "scripts/verify_desktop_native.sh").read_text()
    assert 'if [ "$(uname -s)" = "Darwin" ] && [ "$file_arch" = "aarch64" ]' in script
    assert 'file_arch="arm64"' in script
    assert 'grep -Eq "Mach-O.*$file_arch|Mach-O universal"' in script


def test_frozen_gateway_requires_complete_onedir(tmp_path: Path) -> None:
    gateway = tmp_path / "gateway"
    gateway.mkdir()
    executable = gateway / ("muta-gateway.exe" if os.name == "nt" else "muta-gateway")
    executable.write_bytes(b"binary")
    with pytest.raises(FreezeError, match="incomplete"):
        validate_gateway(tmp_path)
    internal = gateway / "_internal"
    internal.mkdir()
    (internal / "runtime.dat").write_bytes(b"data")
    assert validate_gateway(tmp_path) == executable
