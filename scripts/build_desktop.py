#!/usr/bin/env python3
"""Build Muta's frozen backend, Tauri shell and portable offline kit on this native runner."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from freeze_desktop_gateway import FreezeError, freeze_gateway, validate_gateway

REPO_ROOT = Path(__file__).resolve().parents[1]
DESKTOP = REPO_ROOT / "desktop"
BUILD = DESKTOP / "build"


class BuildError(RuntimeError):
    pass


def run(command: list[str], *, cwd: Path = REPO_ROOT, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(command), flush=True)
    result = subprocess.run(command, cwd=cwd, env=env, check=False)
    if result.returncode:
        raise BuildError(f"command exited {result.returncode}: {' '.join(command)}")


def target() -> tuple[str, str]:
    system = platform.system()
    target_os = {"Darwin": "macos", "Windows": "windows", "Linux": "linux"}.get(system)
    if target_os is None:
        raise BuildError(f"unsupported desktop build OS: {system}")
    machine = platform.machine().lower()
    target_arch = os.environ.get("MUTA_DESKTOP_TARGET_ARCH") or (
        "aarch64" if machine in {"arm64", "aarch64"} else "x86_64"
    )
    if target_arch not in {"aarch64", "x86_64"}:
        raise BuildError(f"unsupported desktop target architecture: {target_arch}")
    if target_os != "macos" and target_arch != (
        "aarch64" if machine in {"arm64", "aarch64"} else "x86_64"
    ):
        raise BuildError("architecture override is supported only for macOS cross-builds")
    return target_os, target_arch


def build(args: argparse.Namespace) -> None:
    target_os, target_arch = target()
    npm = "npm.cmd" if target_os == "windows" else "npm"
    engine_dir = args.engine_dir.resolve()
    engine_name = "llama-server.exe" if target_os == "windows" else "llama-server"
    if not (engine_dir / engine_name).is_file():
        raise BuildError(f"native engine is missing: {engine_dir / engine_name}")
    ffmpeg = (
        args.ffmpeg_bin.resolve()
        if args.ffmpeg_bin
        else engine_dir / ("ffmpeg.exe" if target_os == "windows" else "ffmpeg")
    )
    if args.release and not ffmpeg.is_file():
        raise BuildError("a release build requires the pinned native FFmpeg binary")

    stage_command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "stage_desktop.py"),
        "stage",
        "--app-output",
        str(BUILD / "app-resources"),
        "--model-output",
        str(BUILD / "model-pack"),
        "--engine-dir",
        str(engine_dir),
        "--model-id",
        args.model_id,
        "--model-pack-id",
        args.model_pack_id,
        "--version",
        args.version,
        "--git-sha",
        args.git_sha,
        "--target-os",
        target_os,
        "--target-arch",
        target_arch,
    ]
    if args.model_file:
        stage_command += ["--model-file", args.model_file]
    if args.mmproj_file:
        stage_command += ["--mmproj-file", args.mmproj_file]
    if args.include_optional_models:
        stage_command.append("--include-optional-models")
    if ffmpeg.is_file():
        stage_command += ["--ffmpeg-bin", str(ffmpeg)]
    heartbeat_url = os.environ.get("MUTA_DESKTOP_HEARTBEAT_URL", "")
    heartbeat_key = os.environ.get("MUTA_DESKTOP_HEARTBEAT_INGEST_KEY", "")
    if heartbeat_url or heartbeat_key:
        stage_command += [
            "--heartbeat-url",
            heartbeat_url,
            "--heartbeat-ingest-key",
            heartbeat_key,
        ]
    run(stage_command)

    if not args.no_tauri:
        run([npm, "ci"], cwd=DESKTOP)
    if args.release:
        if not os.environ.get("TAURI_SIGNING_PRIVATE_KEY"):
            raise BuildError("release build requires TAURI_SIGNING_PRIVATE_KEY")
        if not os.environ.get("TAURI_SIGNING_PRIVATE_KEY_PASSWORD"):
            raise BuildError("release build requires TAURI_SIGNING_PRIVATE_KEY_PASSWORD")
        if not os.environ.get("MUTA_MODEL_PACK_PUBLIC_KEY"):
            raise BuildError("release build requires MUTA_MODEL_PACK_PUBLIC_KEY")
        run(
            [
                npm,
                "run",
                "tauri",
                "--",
                "signer",
                "sign",
                str(BUILD / "model-pack" / "model-pack.json"),
            ],
            cwd=DESKTOP,
        )

    try:
        if not args.reuse_frozen_gateway:
            freeze_gateway(BUILD)
        executable = validate_gateway(BUILD)
    except FreezeError as error:
        source = "cached" if args.reuse_frozen_gateway else "built"
        raise BuildError(f"{source} {error}") from error
    run(
        [
            str(executable),
            "--print-config",
            "--resource-root",
            str(BUILD / "app-resources"),
            "--model-root",
            str(BUILD / "model-pack"),
            "--data-root",
            str(BUILD / "freeze-smoke-state"),
            "--llama-server",
            str(BUILD / "app-resources" / "bin" / engine_name),
        ]
    )
    if args.no_tauri:
        return

    if args.release and target_os == "macos":
        if not os.environ.get("APPLE_SIGNING_IDENTITY"):
            raise BuildError("macOS release requires APPLE_SIGNING_IDENTITY")
        run(
            [
                "bash",
                str(REPO_ROOT / "scripts" / "sign_macos_nested.sh"),
                str(BUILD / "gateway"),
                str(BUILD / "app-resources"),
            ]
        )
    if args.release and target_os == "windows":
        if not os.environ.get("WINDOWS_CERTIFICATE_BASE64") or not os.environ.get(
            "WINDOWS_CERTIFICATE_PASSWORD"
        ):
            raise BuildError("Windows release requires its code-signing certificate")
        run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(REPO_ROOT / "scripts" / "sign_windows.ps1"),
                "-Root",
                str(BUILD),
                "-NestedOnly",
            ]
        )

    tauri_command = [npm, "run", "tauri", "--", "build"]
    target_triple = os.environ.get("MUTA_DESKTOP_TARGET_TRIPLE", "")
    if target_triple:
        if target_os != "macos" or target_triple not in {
            "aarch64-apple-darwin",
            "x86_64-apple-darwin",
        }:
            raise BuildError(f"unsupported Tauri target override: {target_triple}")
        tauri_command += ["--target", target_triple]
    if args.tauri_config:
        tauri_command += ["--config", str(args.tauri_config.resolve())]
    tauri_env = {**os.environ, "MACOSX_DEPLOYMENT_TARGET": "12.0"}
    if target_os == "linux":
        # linuxdeploy scans the complete PyInstaller onedir closure. NumPy wheels keep their
        # hashed Fortran dependencies below numpy.libs, so expose that private directory to
        # the bundler's resolver without flattening or rewriting PyInstaller's sibling tree.
        numpy_libs = executable.parent / "_internal" / "numpy.libs"
        if numpy_libs.is_dir():
            existing = tauri_env.get("LD_LIBRARY_PATH", "")
            tauri_env["LD_LIBRARY_PATH"] = os.pathsep.join(
                item for item in (str(numpy_libs), existing) if item
            )
    run(tauri_command, cwd=DESKTOP, env=tauri_env)
    if args.release and target_os == "windows":
        run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(REPO_ROOT / "scripts" / "sign_windows.ps1"),
                "-Root",
                str(DESKTOP / "src-tauri" / "target" / "release"),
            ]
        )
    target_root = Path(
        os.environ.get("CARGO_TARGET_DIR", str(DESKTOP / "src-tauri" / "target"))
    ).resolve()
    target_release = (
        target_root / target_triple / "release" if target_triple else target_root / "release"
    )
    assemble_portable_kit(target_os, target_release)


def assemble_portable_kit(target_os: str, target_release: Path) -> None:
    kit = BUILD / "offline-kit"
    shutil.rmtree(kit, ignore_errors=True)
    kit.mkdir(parents=True)
    if target_os == "macos":
        app = target_release / "bundle" / "macos" / "Muta.app"
        if not app.is_dir():
            raise BuildError(f"Tauri application bundle is missing: {app}")
        shutil.copytree(app, kit / app.name)
    else:
        executable_name = "Muta.exe" if target_os == "windows" else "Muta"
        executable = target_release / executable_name
        if not executable.is_file():
            raise BuildError(f"Tauri executable is missing: {executable}")
        shutil.copy2(executable, kit / executable_name)
        shutil.copytree(BUILD / "gateway", kit / "gateway")
        shutil.copytree(BUILD / "app-resources", kit / "resources")
    shutil.copytree(BUILD / "model-pack", kit / "model-pack")
    (kit / "README.txt").write_text(
        "Muta runs offline. Keep model-pack beside the app/executable. "
        "Application updates replace code; model packs are versioned independently.\n",
        encoding="utf-8",
    )


def parser() -> argparse.ArgumentParser:
    default_sha = os.environ.get("MUTA_BUILD_GIT_SHA", "")
    if not default_sha:
        identity = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        default_sha = identity.stdout.strip() if identity.returncode == 0 else "unknown"
    result = argparse.ArgumentParser(prog="build_desktop.py")
    result.add_argument("--engine-dir", type=Path, default=BUILD / "native")
    result.add_argument("--ffmpeg-bin", type=Path)
    result.add_argument("--model-id", default="muta-tutor-qwen3.5-0.8b-q4_0")
    result.add_argument("--model-file")
    result.add_argument("--mmproj-file")
    result.add_argument("--model-pack-id", default="muta-models-2026.08")
    result.add_argument("--include-optional-models", action="store_true")
    result.add_argument("--version", default="0.1.0-dev")
    result.add_argument("--git-sha", default=default_sha)
    result.add_argument("--tauri-config", type=Path)
    result.add_argument("--no-tauri", action="store_true")
    result.add_argument("--release", action="store_true")
    result.add_argument(
        "--reuse-frozen-gateway",
        action="store_true",
        help="reuse a cache-restored PyInstaller onedir after running its normal smoke test",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        build(args)
    except (BuildError, OSError, subprocess.SubprocessError) as error:
        print(f"desktop build failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
