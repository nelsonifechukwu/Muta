#!/usr/bin/env python3
"""Generate the release-only Tauri overlay from CI-provided public update configuration."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
from pathlib import Path

SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:[-+][0-9A-Za-z.-]+)?$")


def normalize_tauri_public_key(value: str) -> str:
    """Return Tauri's outer-base64 public-key representation after strict validation."""
    supplied = value.strip()
    if supplied.startswith("untrusted comment:"):
        document = supplied + "\n"
    else:
        try:
            document = base64.b64decode(supplied, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as error:
            raise ValueError("public key is not valid Tauri base64") from error
    lines = document.splitlines()
    if len(lines) != 2 or not lines[0].startswith("untrusted comment:"):
        raise ValueError("public key must decode to a two-line minisign document")
    try:
        raw_key = base64.b64decode(lines[1], validate=True)
    except binascii.Error as error:
        raise ValueError("minisign public-key payload is malformed") from error
    if len(raw_key) != 42 or raw_key[:2] not in {b"Ed", b"ED"}:
        raise ValueError("minisign public-key payload is invalid")
    return base64.b64encode(document.encode("utf-8")).decode("ascii")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--pubkey", default=os.environ.get("MUTA_UPDATER_PUBLIC_KEY", ""))
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    version = args.version.removeprefix("v")
    if not SEMVER.fullmatch(version):
        parser.error("--version must be SemVer")
    try:
        public_key = normalize_tauri_public_key(args.pubkey)
    except ValueError as error:
        parser.error(f"--pubkey {error}")
    if not args.endpoint.startswith("https://"):
        parser.error("--endpoint must use HTTPS")
    overlay = {
        "version": version,
        "bundle": {"createUpdaterArtifacts": True},
        "plugins": {
            "updater": {
                "pubkey": public_key,
                "endpoints": [args.endpoint],
                "windows": {"installMode": "passive"},
            }
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(overlay, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
