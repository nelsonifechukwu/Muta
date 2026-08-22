from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts import export_native_linux as export


def test_sha256(tmp_path):
    payload = tmp_path / "payload"
    payload.write_bytes(b"muta")
    assert (
        export._sha256(payload)
        == "75c6ac6edec202d9e959a464205a7cfd070ffd47e9225460c4a71691130b935c"
    )


def test_ui_source_inventory_discovers_every_authored_browser_asset(tmp_path):
    for name in ("index.html", "styles.css", "app.js", "new-locale.js"):
        (tmp_path / name).write_text(name)
    (tmp_path / ".DS_Store").write_text("metadata")
    (tmp_path / "._app.js").write_text("metadata")
    (tmp_path / "browser.spec.js").write_text("test")
    (tmp_path / "browser.test.js").write_text("test")
    (tmp_path / "test_ui.py").write_text("test")
    (tmp_path / "dist").mkdir()

    assert export._discover_ui_source_files(tmp_path) == (
        "app.js",
        "index.html",
        "new-locale.js",
        "styles.css",
    )
    assert {
        "africa-languages.js",
        "locale-manifest.js",
        "locale-bootstrap.js",
        "i18n.js",
        "locale-fr.js",
        "locales.js",
    }.issubset(export.UI_SOURCE_FILES)


def test_ui_source_inventory_rejects_symlinks(tmp_path):
    (tmp_path / "app.js").write_text("app")
    (tmp_path / "linked.js").symlink_to(tmp_path / "app.js")

    with pytest.raises(export.ExportError, match="cannot be symlinks"):
        export._discover_ui_source_files(tmp_path)


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
    manifest = {
        "schema": 2,
        "verification": {"llama_cpp_pin": "b10035/602f828"},
        "binaries": binaries,
        "ui": {"path": "ui/dist", "files": ui_files},
    }
    manifest_path = output / "native-linux-manifest.json"
    manifest_path.write_text(__import__("json").dumps(manifest))
    assert export.verify_manifest(output).is_file()

    vendor_metadata = manifest["ui"]["files"].pop("vendor/marked.min.js")
    manifest_path.write_text(__import__("json").dumps(manifest))
    with pytest.raises(export.ExportError, match="missing UI hash metadata"):
        export.verify_manifest(output)
    manifest["ui"]["files"]["vendor/marked.min.js"] = vendor_metadata

    for unsafe_path in ("../outside", str(tmp_path / "absolute")):
        manifest["ui"]["path"] = unsafe_path
        manifest_path.write_text(__import__("json").dumps(manifest))
        with pytest.raises(export.ExportError, match="must be relative|escapes"):
            export.sync_source_ui(output)
    manifest["ui"]["path"] = "ui/dist"
    manifest_path.write_text(__import__("json").dumps(manifest))

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
    source_overlay_files = (*export.UI_SOURCE_FILES, *export.UI_REPOSITORY_ASSETS)
    for relative in source_overlay_files:
        source = ui_source / relative
        source.parent.mkdir(parents=True, exist_ok=True)
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
    for relative in source_overlay_files:
        assert (ui_dist / relative).read_text() == f"checkout {relative}"
        assert (ui_dist / relative).stat().st_mtime > 1
    resealed = __import__("json").loads(manifest_path.read_text())
    assert resealed["ui"]["source_overlay"]["files"] == list(source_overlay_files)
    assert export.verify_manifest(output) == manifest_path


def test_sync_source_ui_upgrades_a_legacy_export_without_new_authored_assets(tmp_path, monkeypatch):
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
    legacy_authored_assets = {
        "app.js",
        "audio.js",
        "index.html",
        "styles.css",
        "worklet.js",
    }
    new_overlay_assets = (set(export.UI_SOURCE_FILES) - legacy_authored_assets) | set(
        export.UI_REPOSITORY_ASSETS
    )
    assert new_overlay_assets
    legacy_required = [item for item in export.UI_REQUIRED if item not in new_overlay_assets]
    legacy_required.append("vendor/katex/contrib/auto-render.min.js")
    ui_files = {}
    for relative in legacy_required:
        asset = ui_dist / relative
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_text(f"legacy {relative}")
        ui_files[relative] = {"sha256": export._sha256(asset)}
    for relative in (*export.UI_SOURCE_FILES, *export.UI_REPOSITORY_ASSETS):
        source = ui_source / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(f"current {relative}")

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

    assert all(not (ui_dist / item).exists() for item in new_overlay_assets)
    assert export.sync_source_ui(output) == manifest_path
    assert all((ui_dist / item).read_text() == f"current {item}" for item in new_overlay_assets)
    assert export.verify_manifest(output) == manifest_path


def test_ui_verifier_rejects_root_absolute_assets(tmp_path):
    for relative in export.UI_REQUIRED:
        asset = tmp_path / relative
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_text(relative)
    (tmp_path / "index.html").write_text('<script src="/app.js"></script>')
    with pytest.raises(export.ExportError, match="root-absolute"):
        export._verify_ui(tmp_path)


@pytest.mark.parametrize(
    "reference",
    (
        '<script src="https://cdn.example/app.js"></script>',
        '<link rel="stylesheet" href="//cdn.example/styles.css">',
    ),
)
def test_ui_verifier_rejects_remote_assets(tmp_path, reference):
    for relative in export.UI_REQUIRED:
        asset = tmp_path / relative
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_text(relative)
    (tmp_path / "index.html").write_text(reference)

    with pytest.raises(export.ExportError, match="remote asset URLs"):
        export._verify_ui(tmp_path)


def test_ui_verifier_rejects_root_absolute_v1_assets(tmp_path):
    for relative in export.UI_REQUIRED:
        asset = tmp_path / relative
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_text(relative)
    (tmp_path / "index.html").write_text('<script src="/v1/missing.js"></script>')

    with pytest.raises(export.ExportError, match="root-absolute"):
        export._verify_ui(tmp_path)


def test_ui_verifier_allows_same_origin_navigation_links(tmp_path):
    for relative in export.UI_REQUIRED:
        asset = tmp_path / relative
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_text(relative)
    (tmp_path / "index.html").write_text(
        '<a href="/">Muta home</a>'
        '<a href="/chat/">Open Muta</a>'
        '<link rel="stylesheet" href="styles.css">'
        '<script src="app.js"></script>'
    )

    verified = export._verify_ui(tmp_path)

    assert "app.js" in verified["files"]


@pytest.mark.parametrize(
    "reference",
    (
        "<script src='missing-locale.js?v=new'></script>",
        "<SCRIPT SRC = 'missing-locale.js?v=new'></SCRIPT>",
        "<script src=missing-locale.js?v=new></script>",
    ),
)
def test_ui_verifier_rejects_an_index_that_references_a_missing_asset(tmp_path, reference):
    for relative in export.UI_REQUIRED:
        asset = tmp_path / relative
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_text(relative)
    (tmp_path / "index.html").write_text(
        "<!-- <script src='comment-only.js'></script> -->" + reference
    )

    with pytest.raises(export.ExportError, match="missing-locale.js") as error:
        export._verify_ui(tmp_path)
    assert "comment-only.js" not in str(error.value)


def test_ui_verifier_rejects_a_reference_that_escapes_the_bundle(tmp_path):
    for relative in export.UI_REQUIRED:
        asset = tmp_path / relative
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_text(relative)
    outside = tmp_path.parent / "outside.js"
    outside.write_text("outside")
    (tmp_path / "index.html").write_text("<script src='../outside.js'></script>")

    with pytest.raises(export.ExportError, match="escapes its allowed root"):
        export._verify_ui(tmp_path)
