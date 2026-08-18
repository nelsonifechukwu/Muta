#!/usr/bin/env python3
"""Content identity for a native Muta source tree, including uncommitted files.

Git SHA alone is insufficient during VM bring-up because the native packaging work may be
deployed before it is committed.  This hashes every runtime-relevant source/config/UI file while
excluding generated caches, benchmark results and extracted binaries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = ("Makefile", "pyproject.toml", "run.sh", "docker-compose.yml")
ROOT_DIRS = ("bench", "contracts", "docker", "orchestrator", "runtime", "scripts", "ui")
EXCLUDED_PARTS = {".artifacts", "__pycache__", "build", "dist", "node_modules"}
INCLUDED_SUFFIXES = {
    ".css", ".html", ".js", ".json", ".md", ".py", ".sh", ".toml", ".yaml", ".yml"
}


def _git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _source_files() -> list[Path]:
    files = [ROOT / name for name in ROOT_FILES if (ROOT / name).is_file()]
    for dirname in ROOT_DIRS:
        base = ROOT / dirname
        if not base.is_dir():
            continue
        files.extend(
            path
            for path in base.rglob("*")
            if path.is_file()
            and path.suffix in INCLUDED_SUFFIXES
            and not EXCLUDED_PARTS.intersection(path.relative_to(ROOT).parts)
        )
    return sorted(set(files), key=lambda path: path.relative_to(ROOT).as_posix())


def source_identity() -> dict:
    digest = hashlib.sha256()
    files = _source_files()
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(content_hash.encode())
        digest.update(b"\0")
    tree_sha256 = digest.hexdigest()
    head = _git("rev-parse", "HEAD") or "unknown"
    status = _git(
        "status",
        "--short",
        "--untracked-files=all",
        "--",
        *ROOT_FILES,
        *ROOT_DIRS,
    )
    return {
        "identifier": f"{head[:12]}+tree.{tree_sha256[:12]}",
        "git_head": head,
        "source_tree_sha256": tree_sha256,
        "source_file_count": len(files),
        "git_status": status.splitlines() if status else [],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", action="store_true", help="print only the compact identifier")
    args = parser.parse_args(argv)
    identity = source_identity()
    print(identity["identifier"] if args.id else json.dumps(identity, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
