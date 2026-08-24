#!/usr/bin/env python3
"""Copy/hard-link verified desktop model inputs into an isolated source checkout."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

PRODUCT_MODEL_ID = "muta-tutor-qwen3.5-0.8b-q4_0"
MODEL_DIRECTORIES = ("models/asr", "models/tts", "models/embed", "models/LICENSES")
MODEL_FILES = ("models/MANIFEST.json", "models/pins.lock.json")


class SyncError(RuntimeError):
    pass


def copy_file(source: Path, destination: Path) -> None:
    if not source.is_file() or source.is_symlink():
        raise SyncError(f"unsafe or missing model input: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir() or source.is_symlink():
        raise SyncError(f"unsafe or missing model input directory: {source}")
    if destination.exists():
        shutil.rmtree(destination)
    for item in sorted(source.rglob("*")):
        if item.is_symlink():
            raise SyncError(f"model input contains a symlink: {item}")
        if item.is_file():
            copy_file(item, destination / item.relative_to(source))


def sync(source_root: Path, destination_root: Path) -> None:
    source_root = source_root.resolve()
    destination_root = destination_root.resolve()
    catalog_path = source_root / "runtime" / "model-catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    product = next(
        (entry for entry in catalog.get("models", []) if entry.get("id") == PRODUCT_MODEL_ID),
        None,
    )
    if product is None:
        raise SyncError(f"model catalog does not contain {PRODUCT_MODEL_ID}")
    for key in ("path", "mmproj_path"):
        relative = Path(product[key])
        if relative.is_absolute() or ".." in relative.parts:
            raise SyncError(f"unsafe catalog model path: {relative}")
        copy_file(source_root / relative, destination_root / relative)
    for relative in MODEL_DIRECTORIES:
        copy_tree(source_root / relative, destination_root / relative)
    for relative in MODEL_FILES:
        copy_file(source_root / relative, destination_root / relative)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        sync(args.source, args.destination)
    except (KeyError, OSError, ValueError, json.JSONDecodeError, SyncError) as error:
        print(f"desktop model input sync failed: {error}", file=sys.stderr)
        return 1
    print(args.destination.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
