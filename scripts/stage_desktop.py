#!/usr/bin/env python3
"""Stage the allow-listed desktop application resources and independent model pack.

The output deliberately has two roots. ``app`` is embedded in and signed with the desktop
application; ``model-pack`` stays beside the portable app or in the user's model store so a
GGUF can be updated without changing the application seal. No source tree is copied wholesale.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
from pathlib import Path, PurePosixPath
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CHUNK_SIZE = 8 * 1024 * 1024
FORBIDDEN_PARTS = {".git", "bench", "muta-iq", "model-development", "__pycache__"}
DEFAULT_MODEL_ID = "qwen2.5-1.5b-instruct-q4_k_m"
SECONDARY_CORE_MODEL_ID = "muta-tutor-qwen3.5-0.8b-q4_0"


class StageError(RuntimeError):
    """The requested release input is incomplete, unsafe or inconsistent."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(value: str) -> PurePosixPath:
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise StageError(f"unsafe staged path: {value!r}")
    return relative


def _assert_regular_source(path: Path) -> None:
    if path.is_symlink():
        raise StageError(f"symlinks are not allowed in desktop release inputs: {path}")
    if not path.is_file():
        raise StageError(f"required desktop release input is missing: {path}")


def _copy_file(source: Path, destination: Path, *, executable: bool = False) -> None:
    _assert_regular_source(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    if executable and os.name != "nt":
        destination.chmod(destination.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir() or source.is_symlink():
        raise StageError(f"required desktop release directory is missing or unsafe: {source}")
    for item in sorted(source.rglob("*")):
        relative = item.relative_to(source)
        if item.is_symlink():
            raise StageError(f"symlinks are not allowed in desktop release inputs: {item}")
        if item.is_dir():
            continue
        if any(part in FORBIDDEN_PARTS for part in relative.parts):
            raise StageError(f"forbidden release input below {source}: {relative}")
        _copy_file(item, destination / relative)


def _manifest_entries(root: Path, *, exclude: set[str] | None = None) -> list[dict[str, Any]]:
    excluded = exclude or set()
    entries = []
    for item in sorted(root.rglob("*")):
        if item.is_symlink():
            raise StageError(f"staged output contains a symlink: {item}")
        if not item.is_file():
            continue
        relative = item.relative_to(root).as_posix()
        if relative in excluded:
            continue
        entries.append(
            {"path": relative, "size_bytes": item.stat().st_size, "sha256": sha256_file(item)}
        )
    return entries


def _read_catalog(path: Path) -> dict[str, dict[str, Any]]:
    body = json.loads(path.read_text(encoding="utf-8"))
    if body.get("schema_version") != 1:
        raise StageError("unsupported source model catalog")
    return {str(item["id"]): item for item in body.get("models", [])}


def _model_spec(
    args: argparse.Namespace, model_id: str | None = None
) -> tuple[dict[str, Any], Path, Path | None]:
    selected_id = model_id or args.model_id
    catalog = _read_catalog(REPO_ROOT / "runtime" / "model-catalog.json")
    source_spec = catalog.get(selected_id, {})
    use_overrides = selected_id == args.model_id
    model_override = getattr(args, "model_file", None) if use_overrides else None
    projector_override = getattr(args, "mmproj_file", None) if use_overrides else None
    model_value = model_override or source_spec.get("path")
    if not model_value:
        raise StageError(f"unknown model id and no --model-file supplied: {selected_id}")
    model_source = Path(model_value)
    if not model_source.is_absolute():
        model_source = REPO_ROOT / model_source
    _assert_regular_source(model_source)
    actual_model_size = model_source.stat().st_size
    actual_model_hash = sha256_file(model_source)
    if source_spec.get("sha256") and actual_model_hash != source_spec["sha256"]:
        raise StageError(f"{selected_id} does not match the catalog SHA-256")
    if source_spec.get("size_bytes") and actual_model_size != source_spec["size_bytes"]:
        raise StageError(f"{selected_id} does not match the catalog byte size")

    projector_source: Path | None = None
    projector_value = projector_override or source_spec.get("mmproj_path")
    if projector_value:
        projector_source = Path(projector_value)
        if not projector_source.is_absolute():
            projector_source = REPO_ROOT / projector_source
        _assert_regular_source(projector_source)
        actual_projector_size = projector_source.stat().st_size
        actual_projector_hash = sha256_file(projector_source)
        if (
            source_spec.get("mmproj_sha256")
            and actual_projector_hash != source_spec["mmproj_sha256"]
        ):
            raise StageError(f"{selected_id} projector does not match the catalog SHA-256")
        if (
            source_spec.get("mmproj_size_bytes")
            and actual_projector_size != source_spec["mmproj_size_bytes"]
        ):
            raise StageError(f"{selected_id} projector does not match the catalog byte size")

    destination = f"models/core/{model_source.name}"
    spec: dict[str, Any] = {
        "id": selected_id,
        "label": source_spec.get("label") or selected_id,
        "kind": "local",
        "path": destination,
        "sha256": actual_model_hash,
        "size_bytes": actual_model_size,
        "description": source_spec.get("description") or "Packaged offline Muta model.",
        "recommended": bool(source_spec.get("recommended", selected_id == args.model_id)),
    }
    for key in ("arc_easy", "audit_proxy_tps"):
        if source_spec.get(key) is not None:
            spec[key] = source_spec[key]
    if projector_source is not None:
        spec.update(
            {
                "mmproj_path": f"models/core/{projector_source.name}",
                "mmproj_sha256": actual_projector_hash,
                "mmproj_size_bytes": actual_projector_size,
            }
        )
    return spec, model_source, projector_source


def _stage_engine(engine_dir: Path, app_root: Path, target_os: str) -> None:
    binary_name = "llama-server.exe" if target_os == "windows" else "llama-server"
    candidates = [engine_dir / binary_name, engine_dir / "bin" / binary_name]
    binary = next((candidate for candidate in candidates if candidate.is_file()), None)
    if binary is None:
        raise StageError(f"{binary_name} not found below engine directory {engine_dir}")
    _copy_file(binary, app_root / "bin" / binary_name, executable=True)
    # llama.cpp dynamically linked builds need their sibling shared libraries. Preserve only
    # native runtime files, never a compiler tree or arbitrary engine checkout.
    suffixes = {".dll", ".dylib", ".so"}
    for item in sorted(binary.parent.iterdir()):
        if item == binary or not item.is_file() or item.is_symlink():
            continue
        if item.suffix.lower() in suffixes or ".so." in item.name:
            _copy_file(item, app_root / "bin" / item.name, executable=True)
    versions = engine_dir / "VERSIONS.txt"
    if versions.is_file():
        _copy_file(versions, app_root / "bin" / "VERSIONS.txt")


def _stage_ffmpeg(ffmpeg_bin: Path | None, app_root: Path, target_os: str) -> None:
    if ffmpeg_bin is None:
        return
    executable_name = "ffmpeg.exe" if target_os == "windows" else "ffmpeg"
    source = ffmpeg_bin / executable_name if ffmpeg_bin.is_dir() else ffmpeg_bin
    _copy_file(source.resolve(), app_root / "bin" / executable_name, executable=True)


def stage(args: argparse.Namespace) -> None:
    app_root = args.app_output.resolve()
    model_root = args.model_output.resolve()
    for output in (app_root, model_root):
        if output.exists():
            shutil.rmtree(output)
        output.mkdir(parents=True)

    model_ids = (args.model_id, *args.bundled_model_id)
    if len(model_ids) != len(set(model_ids)):
        raise StageError("desktop core model ids must be unique")
    staged_models = [_model_spec(args, model_id) for model_id in model_ids]
    specs = [item[0] for item in staged_models]
    for spec, model_source, projector_source in staged_models:
        _copy_file(model_source, model_root / spec["path"])
        if projector_source is not None:
            _copy_file(projector_source, model_root / spec["mmproj_path"])
    spec = specs[0]

    custom_model_guide = model_root / "models" / "custom" / "ADD GGUF MODELS HERE.txt"
    custom_model_guide.parent.mkdir(parents=True, exist_ok=True)
    custom_model_guide.write_text(
        "Copy additional .gguf model files into this folder, then restart Muta.\n"
        "Muta validates each GGUF and shows models that fit this computer in the model menu.\n"
        "Keep the original model-pack files and model-pack.json unchanged.\n",
        encoding="utf-8",
    )

    if args.include_optional_models:
        for relative in ("models/asr", "models/tts", "models/embed", "models/ttft"):
            source = REPO_ROOT / relative
            if source.is_dir():
                _copy_tree(source, model_root / relative)
    # Ship only licences for product artifacts. The source directory also contains bake-off,
    # draft and training-candidate notices whose names would incorrectly imply those models
    # are part of the desktop release.
    license_names = {"core.Apache-2.0.txt"}
    if any(projector is not None for _, _, projector in staged_models):
        license_names.add("mmproj.Apache-2.0.txt")
    if args.include_optional_models:
        license_names.update({"asr.MIT.txt", "vad.MIT.txt", "tts.CC0-1.0.txt", "embed.MIT.txt"})
    for name in sorted(license_names):
        source = REPO_ROOT / "models" / "LICENSES" / name
        if source.is_file():
            _copy_file(source, model_root / "models" / "LICENSES" / name)

    _copy_tree(REPO_ROOT / "ui" / "dist", app_root / "ui" / "dist")
    _copy_tree(REPO_ROOT / "landing", app_root / "landing")
    index_source = REPO_ROOT / "index"
    if index_source.is_dir():
        _copy_tree(index_source, app_root / "index")
    _stage_engine(args.engine_dir.resolve(), app_root, args.target_os)
    _stage_ffmpeg(args.ffmpeg_bin, app_root, args.target_os)

    catalog = {"schema_version": 1, "models": specs}
    catalog_path = app_root / "runtime" / "model-catalog.json"
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")

    pack_manifest = {
        "schema": 1,
        "pack_id": args.model_pack_id,
        "active_model_id": args.model_id,
        "files": _manifest_entries(model_root, exclude={"model-pack.json"}),
    }
    (model_root / "model-pack.json").write_text(
        json.dumps(pack_manifest, indent=2) + "\n", encoding="utf-8"
    )

    product: dict[str, Any] = {
        "schema": 1,
        "version": args.version,
        "git_sha": args.git_sha,
        "target": {"os": args.target_os, "arch": args.target_arch},
        "model_pack_id": args.model_pack_id,
        "active_model": {
            key: spec[key]
            for key in (
                "id",
                "path",
                "sha256",
                "size_bytes",
                "mmproj_path",
                "mmproj_sha256",
                "mmproj_size_bytes",
            )
            if key in spec
        },
    }
    if args.heartbeat_url or args.heartbeat_ingest_key:
        if not args.heartbeat_url or not args.heartbeat_ingest_key:
            raise StageError("heartbeat URL and ingest key must be supplied together")
        product["heartbeat"] = {
            "url": args.heartbeat_url,
            "ingest_key": args.heartbeat_ingest_key,
        }
    (app_root / "desktop-product.json").write_text(
        json.dumps(product, indent=2) + "\n", encoding="utf-8"
    )
    release_manifest = {
        "schema": 1,
        "version": args.version,
        "git_sha": args.git_sha,
        "files": _manifest_entries(app_root, exclude={"desktop-manifest.json"}),
    }
    (app_root / "desktop-manifest.json").write_text(
        json.dumps(release_manifest, indent=2) + "\n", encoding="utf-8"
    )
    verify_root(app_root, "desktop-manifest.json")
    verify_root(model_root, "model-pack.json")


def verify_root(root: Path, manifest_name: str) -> None:
    path = root / manifest_name
    if not path.is_file():
        raise StageError(f"manifest is missing: {path}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    expected = {entry["path"]: entry for entry in manifest.get("files", [])}
    actual = {
        item.relative_to(root).as_posix()
        for item in root.rglob("*")
        if item.is_file() and item.name not in {manifest_name, f"{manifest_name}.sig"}
    }
    missing = sorted(set(expected) - actual)
    extra = sorted(actual - set(expected))
    if missing or extra:
        raise StageError(f"staged tree differs from manifest; missing={missing}, extra={extra}")
    for relative, entry in expected.items():
        _safe_relative(relative)
        item = root / relative
        if item.is_symlink():
            raise StageError(f"manifest member is a symlink: {relative}")
        if item.stat().st_size != int(entry["size_bytes"]):
            raise StageError(f"manifest byte size mismatch: {relative}")
        if sha256_file(item) != entry["sha256"]:
            raise StageError(f"manifest SHA-256 mismatch: {relative}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stage_desktop.py")
    subparsers = parser.add_subparsers(dest="command", required=True)
    stage_parser = subparsers.add_parser("stage")
    stage_parser.add_argument("--app-output", type=Path, required=True)
    stage_parser.add_argument("--model-output", type=Path, required=True)
    stage_parser.add_argument("--engine-dir", type=Path, required=True)
    stage_parser.add_argument("--ffmpeg-bin", type=Path)
    stage_parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    stage_parser.add_argument(
        "--bundled-model-id", action="append", default=[SECONDARY_CORE_MODEL_ID]
    )
    stage_parser.add_argument("--model-file")
    stage_parser.add_argument("--mmproj-file")
    stage_parser.add_argument("--model-pack-id", required=True)
    stage_parser.add_argument("--version", required=True)
    stage_parser.add_argument("--git-sha", required=True)
    stage_parser.add_argument("--target-os", choices=("windows", "macos", "linux"), required=True)
    stage_parser.add_argument("--target-arch", choices=("x86_64", "aarch64"), required=True)
    stage_parser.add_argument("--include-optional-models", action="store_true")
    stage_parser.add_argument(
        "--heartbeat-url", default=os.environ.get("MUTA_DESKTOP_HEARTBEAT_URL", "")
    )
    stage_parser.add_argument(
        "--heartbeat-ingest-key",
        default=os.environ.get("MUTA_DESKTOP_HEARTBEAT_INGEST_KEY", ""),
    )

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("root", type=Path)
    verify_parser.add_argument(
        "--manifest", choices=("desktop-manifest.json", "model-pack.json"), required=True
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "stage":
            stage(args)
        else:
            verify_root(args.root.resolve(), args.manifest)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, StageError) as exc:
        print(f"desktop staging failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
