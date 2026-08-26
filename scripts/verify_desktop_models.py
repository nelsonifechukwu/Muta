#!/usr/bin/env python3
"""Verify every platform-independent model input restored from the desktop cache."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCT_MODEL_IDS = (
    "qwen2.5-1.5b-instruct-q4_k_m",
    "muta-tutor-qwen3.5-0.8b-q4_0",
)
OPTIONAL_ARTIFACTS = {"asr", "vad", "tts", "embed"}
REQUIRED_LICENSES = {
    "core.Apache-2.0.txt",
    "mmproj.Apache-2.0.txt",
    "asr.MIT.txt",
    "vad.MIT.txt",
    "tts.CC0-1.0.txt",
    "embed.MIT.txt",
}


class VerificationError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file(relative: str, expected_size: int, expected_sha256: str) -> None:
    path = (REPO_ROOT / relative).resolve()
    try:
        path.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise VerificationError(f"unsafe model cache path: {relative}") from exc
    if not path.is_file():
        raise VerificationError(f"cached model input is missing: {relative}")
    if path.stat().st_size != expected_size:
        raise VerificationError(f"cached model input has the wrong size: {relative}")
    if sha256_file(path) != expected_sha256:
        raise VerificationError(f"cached model input has the wrong SHA-256: {relative}")


def verify() -> None:
    catalog = json.loads((REPO_ROOT / "runtime" / "model-catalog.json").read_text())
    catalog_by_id = {str(entry.get("id")): entry for entry in catalog["models"]}
    for model_id in PRODUCT_MODEL_IDS:
        product = catalog_by_id.get(model_id)
        if product is None:
            raise VerificationError(f"product model is absent from the catalog: {model_id}")
        verify_file(product["path"], product["size_bytes"], product["sha256"])
        if product.get("mmproj_path"):
            verify_file(
                product["mmproj_path"],
                product["mmproj_size_bytes"],
                product["mmproj_sha256"],
            )

    manifest = json.loads((REPO_ROOT / "models" / "MANIFEST.json").read_text())
    artifacts = {entry.get("name"): entry for entry in manifest.get("artifacts", [])}
    for name in sorted(OPTIONAL_ARTIFACTS):
        artifact = artifacts.get(name)
        if not artifact or not artifact.get("fetched"):
            raise VerificationError(f"desktop model artifact is not fetched: {name}")
        entries = artifact.get("files") or [artifact]
        if not entries:
            raise VerificationError(f"desktop model artifact has no files: {name}")
        for entry in entries:
            verify_file(entry["path"], int(entry["bytes"]), entry["sha256"])

    license_root = REPO_ROOT / "models" / "LICENSES"
    missing = sorted(name for name in REQUIRED_LICENSES if not (license_root / name).is_file())
    if missing:
        raise VerificationError(f"desktop model licences are missing: {', '.join(missing)}")


def main() -> int:
    try:
        verify()
    except (KeyError, OSError, ValueError, json.JSONDecodeError, VerificationError) as error:
        print(f"desktop model cache verification failed: {error}")
        return 1
    print("verified platform-independent desktop model inputs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
