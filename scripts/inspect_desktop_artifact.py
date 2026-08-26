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
DEFAULT_MODEL_ID = "qwen2.5-1.5b-instruct-q4_k_m"
CORE_MODELS = {
    DEFAULT_MODEL_ID: {
        "path": "models/core/Muta-Tutor-Qwen2.5-1.5B-Finetuned-Q4_K_M.gguf",
        "size_bytes": 986_048_128,
        "sha256": "a750d00d458c6ab38925364ea1413db00648449180941e47025736d09922e1eb",
    },
    "muta-tutor-qwen3.5-0.8b-q4_0": {
        "path": "models/core/muta-tutor-qwen3.5-0.8b-q4_0.gguf",
        "size_bytes": 512_977_376,
        "sha256": "552de22f7ea6f161a458985900e2c961d7578baa1ea9c23018ae27151623ff26",
        "mmproj_path": "models/core/Qwen3.5-0.8B-mmproj-F16.gguf",
        "mmproj_size_bytes": 204_987_232,
        "mmproj_sha256": "56e4c6cfe73b0c82e3e82bc518d7591997e61d81f723fc41a586f4fa69ea2453",
    },
}


def fail(message: str) -> None:
    raise RuntimeError(message)


def command(*args: str) -> str:
    result = subprocess.run(args, check=False, text=True, capture_output=True)
    if result.returncode:
        fail(f"{' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def verify_required_heartbeat(product: dict) -> None:
    heartbeat = product.get("heartbeat") or {}
    if not str(heartbeat.get("url", "")).startswith("https://"):
        fail("release heartbeat URL is missing or is not HTTPS")
    if not str(heartbeat.get("ingest_key", "")).strip():
        fail("release heartbeat ingest key is missing")


def verify_core_models(product: dict, catalog: dict, pack: dict) -> None:
    active = product.get("active_model") or {}
    if active.get("id") != DEFAULT_MODEL_ID or pack.get("active_model_id") != DEFAULT_MODEL_ID:
        fail("Qwen2.5 is not the packaged clean-start model")
    expected_active = {"id": DEFAULT_MODEL_ID, **CORE_MODELS[DEFAULT_MODEL_ID]}
    if active != expected_active:
        fail("packaged Qwen2.5 active-model metadata is not the pinned release artifact")
    catalog_by_id = {str(item.get("id")): item for item in catalog.get("models", [])}
    files_by_path = {str(item.get("path")): item for item in pack.get("files", [])}
    for model_id, expected in CORE_MODELS.items():
        expected_path = expected["path"]
        model = catalog_by_id.get(model_id)
        if model is None or model.get("kind") != "local":
            fail(f"required core model is absent from the packaged catalog: {model_id}")
        if model.get("path") != expected_path:
            fail(f"required core model has the wrong packaged path: {model_id}")
        entry = files_by_path.get(expected_path)
        if entry is None:
            fail(f"required core GGUF is absent from the model-pack manifest: {expected_path}")
        for key in ("size_bytes", "sha256"):
            if entry.get(key) != expected[key] or model.get(key) != expected[key]:
                fail(f"core model {key} is not the pinned release artifact: {model_id}")
        expected_projector = expected.get("mmproj_path")
        if expected_projector is None:
            if any(
                model.get(key) is not None
                for key in ("mmproj_path", "mmproj_size_bytes", "mmproj_sha256")
            ):
                fail(f"text-only core model unexpectedly declares a projector: {model_id}")
            continue
        projector_entry = files_by_path.get(expected_projector)
        if projector_entry is None:
            fail(f"required image projector is absent: {model_id}")
        for key in ("mmproj_path", "mmproj_size_bytes", "mmproj_sha256"):
            if model.get(key) != expected[key]:
                fail(f"core projector {key} is not the pinned release artifact: {model_id}")
        if projector_entry.get("size_bytes") != expected["mmproj_size_bytes"]:
            fail(f"core projector size is not the pinned release artifact: {model_id}")
        if projector_entry.get("sha256") != expected["mmproj_sha256"]:
            fail(f"core projector hash is not the pinned release artifact: {model_id}")
    recommended = [
        item.get("id") for item in catalog.get("models", []) if item.get("recommended") is True
    ]
    if recommended != [DEFAULT_MODEL_ID]:
        fail("the packaged catalog must recommend only the Qwen2.5 clean-start model")


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
    catalog = json.loads((app / "runtime" / "model-catalog.json").read_text(encoding="utf-8"))
    pack = json.loads((models / "model-pack.json").read_text(encoding="utf-8"))
    if product["target"] != {"os": args.target_os, "arch": args.target_arch}:
        fail("product target does not match the requested inspector target")
    if product["model_pack_id"] != pack["pack_id"]:
        fail("application and model-pack identities differ")
    verify_core_models(product, catalog, pack)
    if args.require_heartbeat:
        verify_required_heartbeat(product)
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
    parser.add_argument("--require-heartbeat", action="store_true")
    args = parser.parse_args()
    try:
        inspect(args)
    except (OSError, KeyError, ValueError, StageError, RuntimeError) as error:
        print(f"desktop artifact inspection failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
