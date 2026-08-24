#!/usr/bin/env python3
"""Publish catalog GGUFs as independent GCS add-ons, never inside application archives."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

BASE_MODEL_ID = "muta-tutor-qwen3.5-0.8b-q4_0"


class AddonError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, capture_output=capture, text=True, check=False)
    if result.returncode:
        detail = result.stderr.strip() if capture else ""
        raise AddonError(f"command failed: {' '.join(command)}{': ' + detail if detail else ''}")
    return result


def exists(uri: str) -> bool:
    return (
        subprocess.run(
            ["gcloud", "storage", "ls", uri],
            capture_output=True,
            text=True,
            check=False,
        ).returncode
        == 0
    )


def publish(
    source_root: Path,
    bucket: str,
    commit: str,
    *,
    catalog_root: Path | None = None,
) -> dict:
    source_root = source_root.resolve()
    catalog_root = (catalog_root or source_root).resolve()
    catalog = json.loads((catalog_root / "runtime/model-catalog.json").read_text(encoding="utf-8"))
    published = []
    for entry in catalog.get("models", []):
        if entry.get("kind") != "local" or entry.get("id") == BASE_MODEL_ID:
            continue
        relative = Path(str(entry.get("path", "")))
        if not relative.parts or relative.is_absolute() or ".." in relative.parts:
            raise AddonError(f"unsafe catalog path for {entry.get('id')}")
        source = source_root / relative
        if not source.is_file() or source.is_symlink():
            raise AddonError(f"catalog add-on is missing: {source}")
        actual = sha256(source)
        if actual != entry.get("sha256") or source.stat().st_size != entry.get("size_bytes"):
            raise AddonError(f"catalog add-on failed integrity verification: {entry.get('id')}")
        # Content-addressed objects are immutable. A future catalog update may retain an ID and
        # filename, but it must never let an old GCS cache masquerade as the new checksum.
        object_root = f"gs://{bucket}/model-addons/v1/{entry['id']}/{actual}"
        object_uri = f"{object_root}/{source.name}"
        if not exists(object_uri):
            size_gb = source.stat().st_size / 1024**3
            print(f"publishing optional model {entry['id']} ({size_gb:.2f} GB)")
            run(["gcloud", "storage", "cp", str(source), object_uri])
        checksum_uri = f"{object_uri}.sha256"
        if not exists(checksum_uri):
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
                handle.write(f"{actual}  {source.name}\n")
                checksum = Path(handle.name)
            try:
                run(["gcloud", "storage", "cp", str(checksum), checksum_uri])
            finally:
                checksum.unlink(missing_ok=True)
        published.append(
            {
                "id": entry["id"],
                "label": entry["label"],
                "description": entry["description"],
                "file": source.name,
                "bytes": source.stat().st_size,
                "sha256": actual,
                "gcs_uri": object_uri,
                "install_path": f"model-pack/models/custom/{source.name}",
            }
        )
    manifest = {
        "schema": 1,
        "git_commit": commit,
        "base_model_excluded": BASE_MODEL_ID,
        "models": published,
    }
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
        path = Path(handle.name)
    try:
        run(
            [
                "gcloud",
                "storage",
                "cp",
                str(path),
                f"gs://{bucket}/model-addons/v1/manifest.json",
            ]
        )
    finally:
        path.unlink(missing_ok=True)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--catalog-root", type=Path)
    parser.add_argument("--bucket", default="muta-adtc-desktop-packages")
    parser.add_argument("--commit", required=True)
    args = parser.parse_args(argv)
    try:
        manifest = publish(
            args.source_root,
            args.bucket,
            args.commit,
            catalog_root=args.catalog_root,
        )
    except (AddonError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"model add-on publishing failed: {error}")
        return 1
    print(f"published {len(manifest['models'])} optional model add-ons")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
