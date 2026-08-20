from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts import export_native_linux as export


def test_sha256(tmp_path):
    payload = tmp_path / "payload"
    payload.write_bytes(b"muta")
    assert export._sha256(payload) == "75c6ac6edec202d9e959a464205a7cfd070ffd47e9225460c4a71691130b935c"


def test_verify_rejects_non_elf(tmp_path, monkeypatch):
    binary = tmp_path / "llama-server"
    binary.write_text("#!/bin/sh\necho 602f828\n")
    monkeypatch.setattr(
        export,
        "_run",
        lambda args, **kw: type("Result", (), {"stdout": "POSIX shell script", "stderr": ""})(),
    )
    with pytest.raises(export.ExportError, match="not a Linux x86-64 ELF"):
        export._verify_binary(binary)


def test_copy_cleanup_runs_after_failure(monkeypatch, tmp_path):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if args[:2] == ["docker", "create"]:
            return type("Result", (), {"stdout": "container-id\n", "stderr": ""})()
        if args[:2] == ["docker", "cp"]:
            raise export.ExportError("copy failed")
        return type("Result", (), {"stdout": "", "stderr": ""})()

    monkeypatch.setattr(export, "_run", fake_run)
    monkeypatch.setattr(export.subprocess, "run", fake_run)
    with pytest.raises(export.ExportError, match="copy failed"):
        export._copy_from_image("muta-backend:latest", "/app/runtime/build/bin", Path(tmp_path))
    assert ["docker", "rm", "-f", "container-id"] in calls


def test_verify_manifest_detects_binary_tampering(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "ROOT", tmp_path)
    output = tmp_path / "build"
    binary_dir = output / "bin"
    binary_dir.mkdir(parents=True)
    binaries = {}
    for name in export.BINARIES:
        path = binary_dir / name
        path.write_bytes(name.encode())
        binaries[name] = {"sha256": export._sha256(path)}
    ui_path = tmp_path / "ui" / "dist"
    ui_files = {}
    for relative in export.UI_REQUIRED:
        asset = ui_path / relative
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_text(relative)
        ui_files[relative] = {"sha256": export._sha256(asset)}
    (output / "native-linux-manifest.json").write_text(
        __import__("json").dumps(
            {
                "schema": 2,
                "verification": {"llama_cpp_pin": "b10035/602f828"},
                "binaries": binaries,
                "ui": {"path": "ui/dist", "files": ui_files},
            }
        )
    )
    assert export.verify_manifest(output).is_file()
    (binary_dir / "llama-server").write_bytes(b"tampered")
    with pytest.raises(export.ExportError, match="hash mismatch"):
        export.verify_manifest(output)


def test_llama_bench_identity_uses_zero_work_probe(monkeypatch, tmp_path):
    binary = tmp_path / "llama-bench"
    binary.touch()
    seen = []

    def fake_run(args, **kwargs):
        seen.append(args)
        return type("Result", (), {"stdout": "build: 602f828 (1)\n", "stderr": ""})()

    monkeypatch.setattr(export.subprocess, "run", fake_run)
    assert export._version(binary) == "build: 602f828 (1)"
    assert seen[0][1:] == ["-m", "/dev/null", "-p", "0", "-n", "0"]


def test_sync_source_ui_overlays_authored_assets_and_reseals_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "ROOT", tmp_path)
    output = tmp_path / "runtime" / "build"
    binary_dir = output / "bin"
    binary_dir.mkdir(parents=True)
    binaries = {}
    for name in export.BINARIES:
        path = binary_dir / name
        path.write_bytes(name.encode())
        binaries[name] = {"sha256": export._sha256(path)}

    ui_source = tmp_path / "ui"
    ui_dist = ui_source / "dist"
    ui_files = {}
    for relative in export.UI_REQUIRED:
        asset = ui_dist / relative
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_text(f"exported {relative}")
        ui_files[relative] = {"sha256": export._sha256(asset)}
    for relative in export.UI_SOURCE_FILES:
        source = ui_source / relative
        source.write_text(f"checkout {relative}")
        os.utime(source, (1, 1))

    manifest_path = output / "native-linux-manifest.json"
    manifest_path.write_text(
        __import__("json").dumps(
            {
                "schema": 2,
                "verification": {"llama_cpp_pin": "b10035/602f828"},
                "binaries": binaries,
                "ui": {"path": "ui/dist", "files": ui_files},
            }
        )
    )

    assert export.sync_source_ui(output) == manifest_path
    for relative in export.UI_SOURCE_FILES:
        assert (ui_dist / relative).read_text() == f"checkout {relative}"
        assert (ui_dist / relative).stat().st_mtime > 1
    resealed = __import__("json").loads(manifest_path.read_text())
    assert resealed["ui"]["source_overlay"]["files"] == list(export.UI_SOURCE_FILES)
    assert export.verify_manifest(output) == manifest_path


def test_ui_verifier_rejects_root_absolute_assets(tmp_path):
    for relative in export.UI_REQUIRED:
        asset = tmp_path / relative
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_text(relative)
    (tmp_path / "index.html").write_text('<script src="/app.js"></script>')
    with pytest.raises(export.ExportError, match="root-absolute"):
        export._verify_ui(tmp_path)
