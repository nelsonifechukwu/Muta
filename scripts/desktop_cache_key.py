#!/usr/bin/env python3
"""Generate content-addressed keys for target-specific reusable desktop outputs."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import platform
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GATEWAY_INPUTS = (
    "pyproject.toml",
    "bench/sampler.py",
    "desktop/backend_entry.py",
    "desktop/pyinstaller",
    "orchestrator",
    "contracts",
    "runtime",
    "scripts/build_desktop.py",
    "scripts/freeze_desktop_gateway.py",
)
IGNORED_PARTS = {"__pycache__", ".pytest_cache", "tests"}
SOURCE_SUFFIXES = {".py", ".json", ".yaml", ".yml", ".txt", ".spec", ".toml"}


def input_files() -> list[Path]:
    files: set[Path] = set()
    for relative in GATEWAY_INPUTS:
        candidate = REPO_ROOT / relative
        if candidate.is_file():
            files.add(candidate)
            continue
        for path in candidate.rglob("*"):
            if (
                path.is_file()
                and path.suffix in SOURCE_SUFFIXES
                and not IGNORED_PARTS.intersection(path.relative_to(REPO_ROOT).parts)
            ):
                files.add(path)
    return sorted(files, key=lambda path: path.relative_to(REPO_ROOT).as_posix())


def gateway_key() -> str:
    digest = hashlib.sha256()
    identity = (
        f"python={platform.python_implementation()}-{platform.python_version()}\n"
        f"system={platform.system()}\narchitecture={platform.machine()}\n"
    )
    digest.update(identity.encode())
    distributions = sorted(
        (dist.metadata.get("Name", "").lower(), dist.version)
        for dist in importlib.metadata.distributions()
    )
    for name, version in distributions:
        digest.update(f"dependency={name}=={version}\n".encode())
    for path in input_files():
        relative = path.relative_to(REPO_ROOT).as_posix()
        digest.update(f"file={relative}\0".encode())
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("gateway",))
    args = parser.parse_args(argv)
    if args.kind == "gateway":
        print(gateway_key())
    return 0


if __name__ == "__main__":
    sys.exit(main())
