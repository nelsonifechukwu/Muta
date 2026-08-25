from __future__ import annotations

import argparse
import base64
import json
import stat
import tarfile
import zipfile
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
    with tarfile.open(archive, "r:gz") as package_archive:
        root = "Muta_1.2.3_linux-x86_64_offline"
        names = set(package_archive.getnames())
        assert f"{root}/{package.INSTALL_GUIDE}" in names
        launcher = package_archive.getmember(f"{root}/Muta.sh")
        assert launcher.mode & stat.S_IXUSR
        script = package_archive.extractfile(launcher)
        assert script is not None
        assert b'chmod +x "$app"' in script.read()


def test_unsigned_package_collector_adds_macos_private_test_launcher(tmp_path: Path):
    bundle = tmp_path / "bundle"
    app = bundle / "macos/Muta.app"
    app.mkdir(parents=True)
    (app / "placeholder").write_bytes(b"app")
    kit = tmp_path / "offline-kit"
    (kit / "model-pack").mkdir(parents=True)
    (kit / "model-pack/model-pack.json").write_text('{"schema": 1}', encoding="utf-8")
    args = argparse.Namespace(
        platform="darwin-aarch64",
        version="1.2.3",
        bundle_root=bundle,
        offline_kit=kit,
        output=tmp_path / "output",
    )

    archive = package.collect(args)

    with tarfile.open(archive, "r:gz") as package_archive:
        root = "Muta_1.2.3_darwin-aarch64_offline"
        names = set(package_archive.getnames())
        assert f"{root}/{package.INSTALL_GUIDE}" in names
        launcher = package_archive.getmember(f"{root}/Muta.command")
        assert launcher.mode & stat.S_IXUSR
        script = package_archive.extractfile(launcher)
        assert script is not None
        body = script.read()
        assert b'/usr/bin/xattr -c -r "$app"' in body
        assert b'/usr/bin/open "$app"' in body
        guide = package_archive.extractfile(f"{root}/{package.INSTALL_GUIDE}")
        assert guide is not None
        instructions = guide.read()
        assert b"/bin/zsh " in instructions
        assert b"Double-click Muta.command" not in instructions


def test_unsigned_package_collector_names_windows_install_guide(tmp_path: Path):
    bundle = tmp_path / "bundle"
    (bundle / "nsis").mkdir(parents=True)
    (bundle / "nsis/Muta-setup.exe").write_bytes(b"installer")
    kit = tmp_path / "offline-kit"
    (kit / "model-pack").mkdir(parents=True)
    (kit / "model-pack/model-pack.json").write_text('{"schema": 1}', encoding="utf-8")
    args = argparse.Namespace(
        platform="windows-x86_64",
        version="1.2.3",
        bundle_root=bundle,
        offline_kit=kit,
        output=tmp_path / "output",
    )

    archive = package.collect(args)

    with zipfile.ZipFile(archive) as package_archive:
        root = "Muta_1.2.3_windows-x86_64_offline"
        names = set(package_archive.namelist())
        assert f"{root}/{package.INSTALL_GUIDE}" in names
        assert f"{root}/Install-Muta.cmd" in names
        guide = package_archive.read(f"{root}/{package.INSTALL_GUIDE}")
        assert b"HOW TO INSTALL MUTA ON WINDOWS\r\n" in guide
        installer = package_archive.read(f"{root}/Install-Muta.cmd")
        assert b"\r\n" in installer
        assert b"\r\r\n" not in installer


def test_signed_macos_release_uses_notarized_install_guide(tmp_path: Path):
    bundle = tmp_path / "bundle"
    (bundle / "macos").mkdir(parents=True)
    update = bundle / "macos/Muta.app.tar.gz"
    update.write_bytes(b"signed update")
    Path(f"{update}.sig").write_text("signature", encoding="utf-8")
    kit = tmp_path / "offline-kit"
    (kit / "Muta.app").mkdir(parents=True)
    (kit / "model-pack").mkdir()
    (kit / "README.txt").write_text("old instructions", encoding="utf-8")
    args = argparse.Namespace(
        platform="darwin-aarch64",
        version="1.2.3",
        bundle_root=bundle,
        offline_kit=kit,
        output=tmp_path / "release",
    )

    collect.collect(args)

    archive = args.output / "Muta_1.2.3_darwin-aarch64_offline.tar.gz"
    with tarfile.open(archive, "r:gz") as package_archive:
        names = set(package_archive.getnames())
        assert "offline-kit/HOW TO INSTALL.txt" in names
        assert "offline-kit/README.txt" not in names
        assert "offline-kit/Muta.command" not in names
        guide = package_archive.extractfile("offline-kit/HOW TO INSTALL.txt")
        assert guide is not None
        assert b"Developer ID signed and notarized" in guide.read()


def test_signed_windows_release_uses_install_helper_and_guide(tmp_path: Path):
    bundle = tmp_path / "bundle"
    (bundle / "nsis").mkdir(parents=True)
    update = bundle / "nsis/Muta-setup.exe"
    update.write_bytes(b"signed installer")
    Path(f"{update}.sig").write_text("signature", encoding="utf-8")
    kit = tmp_path / "offline-kit"
    (kit / "model-pack").mkdir(parents=True)
    (kit / "README.txt").write_text("old instructions", encoding="utf-8")
    args = argparse.Namespace(
        platform="windows-x86_64",
        version="1.2.3",
        bundle_root=bundle,
        offline_kit=kit,
        output=tmp_path / "release",
    )

    collect.collect(args)

    archive = args.output / "Muta_1.2.3_windows-x86_64_offline.zip"
    with zipfile.ZipFile(archive) as package_archive:
        names = set(package_archive.namelist())
        assert "offline-kit/HOW TO INSTALL.txt" in names
        assert "offline-kit/README.txt" not in names
        assert "offline-kit/Install-Muta.cmd" in names
        assert b"\r\r\n" not in package_archive.read("offline-kit/Install-Muta.cmd")
