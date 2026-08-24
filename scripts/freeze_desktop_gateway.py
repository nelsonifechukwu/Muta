#!/usr/bin/env python3
"""Build and structurally verify the reusable PyInstaller desktop gateway layer."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DESKTOP = REPO_ROOT / "desktop"


class FreezeError(RuntimeError):
    pass


def executable_for(build_root: Path) -> Path:
    return build_root / "gateway" / ("muta-gateway.exe" if os.name == "nt" else "muta-gateway")


def validate_gateway(build_root: Path) -> Path:
    executable = executable_for(build_root)
    internal = executable.parent / "_internal"
    if not executable.is_file() or not internal.is_dir():
        raise FreezeError(f"PyInstaller onedir output is incomplete below {executable.parent}")
    if not any(internal.iterdir()):
        raise FreezeError(f"PyInstaller internal dependency tree is empty: {internal}")
    return executable


def freeze_gateway(build_root: Path) -> Path:
    build_root = build_root.resolve()
    shutil.rmtree(build_root / "gateway", ignore_errors=True)
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "--distpath",
        str(build_root),
        "--workpath",
        str(build_root / "pyinstaller-work"),
        str(DESKTOP / "pyinstaller" / "muta_gateway.spec"),
    ]
    print("+", " ".join(command), flush=True)
    result = subprocess.run(command, cwd=REPO_ROOT, check=False)
    if result.returncode:
        raise FreezeError(f"PyInstaller exited {result.returncode}")
    return validate_gateway(build_root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-root", type=Path, default=DESKTOP / "build")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        executable = (
            validate_gateway(args.build_root)
            if args.verify_only
            else freeze_gateway(args.build_root)
        )
    except (FreezeError, OSError) as error:
        print(f"desktop gateway freeze failed: {error}", file=sys.stderr)
        return 1
    print(executable)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
