from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

import collect_desktop_package as package
import collect_desktop_release as collect
import generate_latest_json as latest
import prepare_tauri_release as prepare


def test_tauri_public_key_is_validated_and_normalized():
    raw = b"Ed" + bytes(range(40))
    document = (
        "untrusted comment: minisign public key\n"
        + base64.b64encode(raw).decode("ascii")
        + "\n"
    )
    wrapped = base64.b64encode(document.encode("utf-8")).decode("ascii")

    assert prepare.normalize_tauri_public_key(document) == wrapped
    assert prepare.normalize_tauri_public_key(wrapped) == wrapped


def test_collector_requires_a_signed_update(tmp_path: Path):
    bundle = tmp_path / "bundle"
    (bundle / "appimage").mkdir(parents=True)
    (bundle / "appimage/Muta.AppImage").write_bytes(b"app")
    kit = tmp_path / "offline-kit"
    kit.mkdir()
    (kit / "README.txt").write_text("offline", encoding="utf-8")
    args = argparse.Namespace(
        platform="linux-x86_64",
        version="1.2.3",
        bundle_root=bundle,
        offline_kit=kit,
        output=tmp_path / "release",
    )
    try:
        collect.collect(args)
    except collect.CollectError as error:
        assert "signature is missing" in str(error)
    else:
        raise AssertionError("unsigned updater was accepted")


def test_latest_manifest_contains_all_native_targets(tmp_path: Path, monkeypatch):
    suffixes = {
        "darwin-aarch64": ".app.tar.gz",
        "darwin-x86_64": ".app.tar.gz",
        "linux-x86_64": ".AppImage",
        "windows-x86_64": "-setup.exe",
    }
    for platform, suffix in suffixes.items():
        root = tmp_path / platform
        root.mkdir()
        artifact = root / f"Muta_1.2.3_{platform}{suffix}"
        artifact.write_bytes(b"update")
        Path(f"{artifact}.sig").write_text(f"signature-{platform}\n", encoding="utf-8")
    output = tmp_path / "latest.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "generate_latest_json.py",
            "--version",
            "1.2.3",
            "--tag",
            "v1.2.3",
            "--repository",
            "owner/repo",
            "--assets-root",
            str(tmp_path),
            "--output",
            str(output),
        ],
    )
    assert latest.main() == 0
    body = json.loads(output.read_text(encoding="utf-8"))
    assert set(body["platforms"]) == set(suffixes)
    assert body["version"] == "1.2.3"
    assert all(value["url"].startswith("https://") for value in body["platforms"].values())


def test_unsigned_package_collector_creates_linux_offline_archive(tmp_path: Path):
    bundle = tmp_path / "bundle"
    (bundle / "appimage").mkdir(parents=True)
    (bundle / "appimage/Muta.AppImage").write_bytes(b"appimage")
    kit = tmp_path / "offline-kit"
    (kit / "model-pack").mkdir(parents=True)
    (kit / "model-pack/model-pack.json").write_text('{"schema": 1}', encoding="utf-8")
    args = argparse.Namespace(
        platform="linux-x86_64",
        version="1.2.3",
        bundle_root=bundle,
        offline_kit=kit,
        output=tmp_path / "output",
    )

    archive = package.collect(args)

    assert archive.name == "Muta_1.2.3_linux-x86_64_offline.tar.gz"
    assert archive.is_file()
    assert Path(f"{archive}.sha256").is_file()
