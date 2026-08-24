#!/usr/bin/env python3
"""Fail-closed inspection of staged/frozen desktop release inputs."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from stage_desktop import StageError, verify_root

FORBIDDEN = {"bench", "muta-iq", "model-development", ".git", "tests", "__pycache__"}


def fail(message: str) -> None:
    raise RuntimeError(message)


def command(*args: str) -> str:
    result = subprocess.run(args, check=False, text=True, capture_output=True)
    if result.returncode:
        fail(f"{' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def inspect(args: argparse.Namespace) -> None:
    app = args.app_resources.resolve()
    gateway = args.gateway.resolve()
    models = args.model_pack.resolve()
    verify_root(app, "desktop-manifest.json")
    verify_root(models, "model-pack.json")

    for root in (app, gateway):
        for item in root.rglob("*"):
            relative = item.relative_to(root)
            if set(relative.parts) & FORBIDDEN:
                fail(f"forbidden development path in product: {root.name}/{relative}")
            if item.is_symlink():
                # PyInstaller uses relative aliases for versioned shared libraries. They are
                # safe only while their final target is a regular file inside the frozen tree.
                try:
                    target = item.resolve(strict=True)
                except OSError as error:
                    fail(f"broken symlink in inspected product tree: {item}: {error}")
                if root != target and root not in target.parents:
                    fail(f"symlink escapes inspected product tree: {item} -> {target}")
                if not target.is_file():
                    fail(f"symlink does not resolve to a regular file: {item} -> {target}")

    gateway_name = "muta-gateway.exe" if args.target_os == "windows" else "muta-gateway"
    engine_name = "llama-server.exe" if args.target_os == "windows" else "llama-server"
    if not (gateway / gateway_name).is_file() or not (gateway / "_internal").is_dir():
        fail("frozen PyInstaller onedir is incomplete")
    engine = app / "bin" / engine_name
    if not engine.is_file():
        fail("native llama-server is absent")
    versions = (app / "bin" / "VERSIONS.txt").read_text(encoding="utf-8")
    if "602f828b4d93a2fefdd546145d9e761825f3bd11" not in versions:
        fail("llama.cpp provenance pin is absent")

    product = json.loads((app / "desktop-product.json").read_text(encoding="utf-8"))
    pack = json.loads((models / "model-pack.json").read_text(encoding="utf-8"))
    if product["target"] != {"os": args.target_os, "arch": args.target_arch}:
        fail("product target does not match the requested inspector target")
    if product["model_pack_id"] != pack["pack_id"]:
        fail("application and model-pack identities differ")
    if args.release and not (models / "model-pack.json.sig").is_file():
        fail("release model pack has no trusted signature")

    native_binaries = [engine]
    ffmpeg_name = "ffmpeg.exe" if args.target_os == "windows" else "ffmpeg"
    ffmpeg = app / "bin" / ffmpeg_name
    if ffmpeg.is_file():
        native_binaries.append(ffmpeg)
    if sys.platform != "win32":
        expected = {
            ("linux", "x86_64"): "x86-64",
            ("macos", "aarch64"): "arm64",
            ("macos", "x86_64"): "x86_64",
        }.get((args.target_os, args.target_arch))
        for executable in native_binaries:
            description = command("file", str(executable))
            if expected and expected not in description:
                fail(f"wrong native binary architecture: {description.strip()}")
    if args.target_os == "linux":
        for executable in native_binaries:
            dependencies = command("ldd", str(executable))
            if "not found" in dependencies:
                fail(f"native dependency is missing:\n{dependencies}")
    if args.target_os == "macos":
        for executable in native_binaries:
            dependencies = command("otool", "-L", str(executable))
            # otool prints the inspected executable itself on line one; only linked-library
            # rows may be evaluated as leaked build-machine dependencies.
            linked_libraries = "\n".join(dependencies.splitlines()[1:])
            if any(
                marker in linked_libraries
                for marker in ("desktop/build", "native-work", "/opt/homebrew", "/usr/local")
            ):
                fail(f"build-machine dependency leaked into native binary:\n{dependencies}")
            load_commands = command("otool", "-l", str(executable))
            for line in load_commands.splitlines():
                fields = line.split()
                if len(fields) == 2 and fields[0] == "minos" and float(fields[1]) > 12.0:
                    fail(f"native binary requires macOS {fields[1]}: {executable}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-resources", type=Path, required=True)
    parser.add_argument("--gateway", type=Path, required=True)
    parser.add_argument("--model-pack", type=Path, required=True)
    parser.add_argument("--target-os", choices=("linux", "windows", "macos"), required=True)
    parser.add_argument("--target-arch", choices=("x86_64", "aarch64"), required=True)
    parser.add_argument("--release", action="store_true")
    args = parser.parse_args()
    try:
        inspect(args)
    except (OSError, KeyError, ValueError, StageError, RuntimeError) as error:
        print(f"desktop artifact inspection failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
