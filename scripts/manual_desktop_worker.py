#!/usr/bin/env python3
"""Build one fresh offline desktop package while reusing verified content-addressed layers."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DESKTOP = REPO_ROOT / "desktop"
SUPPORTED = {
    "linux-x86_64": ("Linux", "linux", "x86_64"),
    "windows-x86_64": ("Windows", "windows", "x86_64"),
    "darwin-aarch64": ("Darwin", "macos", "aarch64"),
    "darwin-x86_64": ("Darwin", "macos", "x86_64"),
}
UI_INPUTS = (
    "scripts/build_ui_dist.py",
    "ui/VISUALIZATION-LICENSES.txt",
    "ui/*.html",
    "ui/*.css",
    "ui/*.js",
    "ui/vendor/viz/*",
)
NATIVE_INPUTS = (
    "scripts/build_desktop_native.sh",
    "scripts/verify_desktop_native.sh",
    "scripts/desktop_native_pins.env",
)


class WorkerError(RuntimeError):
    pass


def run(
    command: list[str],
    *,
    cwd: Path = REPO_ROOT,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(command), flush=True)
    result = subprocess.run(command, cwd=cwd, env=env, text=True, check=False)
    if check and result.returncode:
        raise WorkerError(f"command exited {result.returncode}: {' '.join(command)}")
    return result


def content_key(platform_name: str, patterns: tuple[str, ...]) -> str:
    digest = hashlib.sha256(f"schema=1\nplatform={platform_name}\n".encode())
    files: set[Path] = set()
    for pattern in patterns:
        files.update(path for path in REPO_ROOT.glob(pattern) if path.is_file())
    if not files:
        raise WorkerError(f"cache key has no inputs: {patterns}")
    for path in sorted(files, key=lambda item: item.relative_to(REPO_ROOT).as_posix()):
        relative = path.relative_to(REPO_ROOT).as_posix()
        digest.update(f"{relative}\0".encode())
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def replace_tree(source: Path, destination: Path) -> None:
    temporary = destination.with_name(f".{destination.name}.tmp-{os.getpid()}")
    shutil.rmtree(temporary, ignore_errors=True)
    temporary.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, temporary)
    if destination.exists():
        shutil.rmtree(destination)
    temporary.replace(destination)


def msys_path(path: Path) -> str:
    if os.name != "nt":
        return str(path)
    result = subprocess.run(
        ["cygpath", "-u", str(path)], capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise WorkerError(f"cygpath could not translate {path}")
    return result.stdout.strip()


def bash_script(script: Path, *arguments: Path, env: dict[str, str]) -> None:
    command = ["bash", msys_path(script), *(msys_path(path) for path in arguments)]
    run(command, env=env)


@contextlib.contextmanager
def platform_lock(cache_root: Path, platform_name: str):
    lock = cache_root / "locks" / f"{platform_name}.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock.mkdir()
    except FileExistsError as exc:
        owner_path = lock / "owner.json"
        stale = False
        try:
            owner = json.loads(owner_path.read_text(encoding="utf-8"))
            owner_pid = int(owner["pid"])
            owner_host = str(owner["host"])
            if owner_host == platform.node():
                try:
                    os.kill(owner_pid, 0)
                except ProcessLookupError:
                    stale = True
                except PermissionError:
                    pass
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            try:
                stale = time.time() - lock.stat().st_mtime > 300
            except OSError:
                pass
        if not stale:
            raise WorkerError(f"another {platform_name} package build is active: {lock}") from exc
        shutil.rmtree(lock)
        lock.mkdir()
    try:
        (lock / "owner.json").write_text(
            json.dumps({"pid": os.getpid(), "host": platform.node(), "started": time.time()})
            + "\n",
            encoding="utf-8",
        )
        yield
    finally:
        shutil.rmtree(lock, ignore_errors=True)


def target_environment(platform_name: str, cache_root: Path) -> dict[str, str]:
    _, _, target_arch = SUPPORTED[platform_name]
    env = {**os.environ}
    env["MUTA_DESKTOP_TARGET_ARCH"] = target_arch
    env["MUTA_NATIVE_WORK"] = str(cache_root / "native-work" / platform_name)
    env["CARGO_TARGET_DIR"] = str(cache_root / "cargo-target" / platform_name)
    if platform_name == "linux-x86_64":
        # The GCP coordinator deliberately matches the 8 GB competition laptop. Two native
        # compiler jobs avoid four simultaneous llama.cpp translation units forcing swap thrash.
        env.setdefault("CMAKE_BUILD_PARALLEL_LEVEL", "2")
        env.setdefault("NUMBER_OF_PROCESSORS", "2")
        env.setdefault("MUTA_NATIVE_JOBS", "2")
    if platform_name == "darwin-x86_64":
        env["MUTA_DESKTOP_TARGET_TRIPLE"] = "x86_64-apple-darwin"
    elif platform_name == "darwin-aarch64":
        env["MUTA_DESKTOP_TARGET_TRIPLE"] = "aarch64-apple-darwin"
    return env


def verify_host(platform_name: str) -> None:
    expected_system, _, target_arch = SUPPORTED[platform_name]
    if platform.system() != expected_system:
        raise WorkerError(
            f"{platform_name} must build on {expected_system}, got {platform.system()}"
        )
    machine = platform.machine().lower()
    if expected_system != "Darwin" and machine not in {target_arch, "amd64"}:
        raise WorkerError(f"{platform_name} cannot build on architecture {machine}")
    if platform_name == "darwin-x86_64" and machine not in {"x86_64", "amd64"}:
        raise WorkerError("Intel macOS gateway freezing must run under an x86-64 Python")


def prepare_ui(cache_root: Path) -> None:
    key = content_key("platform-independent", UI_INPUTS)
    cached = cache_root / "ui" / key
    output = REPO_ROOT / "ui" / "dist"
    if cached.is_dir():
        replace_tree(cached, output)
        run([sys.executable, "scripts/build_ui_dist.py", "--verify-only"])
        print(f"UI cache hit: {key[:12]}")
        return
    run([sys.executable, "scripts/build_ui_dist.py"])
    replace_tree(output, cached)
    print(f"UI cache stored: {key[:12]}")


def prepare_native(platform_name: str, cache_root: Path, env: dict[str, str]) -> Path:
    key = content_key(platform_name, NATIVE_INPUTS)
    cached = cache_root / "native" / platform_name / key
    verifier = REPO_ROOT / "scripts" / "verify_desktop_native.sh"
    if cached.is_dir():
        bash_script(verifier, cached, env=env)
        print(f"native cache hit: {key[:12]}")
        return cached
    temporary = cached.with_name(f".{key}.tmp-{os.getpid()}")
    shutil.rmtree(temporary, ignore_errors=True)
    temporary.parent.mkdir(parents=True, exist_ok=True)
    bash_script(REPO_ROOT / "scripts" / "build_desktop_native.sh", temporary, env=env)
    if cached.exists():
        shutil.rmtree(temporary)
    else:
        temporary.replace(cached)
    bash_script(verifier, cached, env=env)
    print(f"native cache stored: {key[:12]}")
    return cached


def gateway_cache(platform_name: str, cache_root: Path) -> tuple[Path, bool]:
    key_result = subprocess.run(
        [sys.executable, "scripts/desktop_cache_key.py", "gateway"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if key_result.returncode:
        raise WorkerError("could not compute the frozen gateway cache key")
    key = key_result.stdout.strip()
    cached = cache_root / "gateway" / platform_name / key
    output = DESKTOP / "build" / "gateway"
    if not cached.is_dir():
        return cached, False
    replace_tree(cached, output)
    run([sys.executable, "scripts/freeze_desktop_gateway.py", "--verify-only"])
    print(f"gateway cache hit: {key[:12]}")
    return cached, True


def bundle_root(env: dict[str, str]) -> Path:
    target = Path(env["CARGO_TARGET_DIR"])
    triple = env.get("MUTA_DESKTOP_TARGET_TRIPLE")
    return target / triple / "release" / "bundle" if triple else target / "release" / "bundle"


def build(args: argparse.Namespace) -> Path:
    verify_host(args.platform)
    cache_root = args.cache_root.expanduser().resolve()
    output = args.output.expanduser().resolve()
    cache_root.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    env = target_environment(args.platform, cache_root)

    with platform_lock(cache_root, args.platform):
        model_check = run([sys.executable, "scripts/verify_desktop_models.py"], check=False)
        if model_check.returncode:
            run(["bash", "scripts/prepare_desktop_models.sh"])
            run([sys.executable, "scripts/verify_desktop_models.py"])
        prepare_ui(cache_root)
        native = prepare_native(args.platform, cache_root, env)
        cached_gateway, reuse_gateway = gateway_cache(args.platform, cache_root)

        target_bundle = bundle_root(env)
        shutil.rmtree(target_bundle, ignore_errors=True)
        command = [
            sys.executable,
            "scripts/build_desktop.py",
            "--engine-dir",
            str(native),
            "--include-optional-models",
            "--version",
            args.version,
            "--git-sha",
            args.commit,
            "--model-pack-id",
            args.model_pack_id,
        ]
        if reuse_gateway:
            command.append("--reuse-frozen-gateway")
        run(command, env=env)
        if not reuse_gateway:
            replace_tree(DESKTOP / "build" / "gateway", cached_gateway)
            run([sys.executable, "scripts/freeze_desktop_gateway.py", "--verify-only"])

        _, target_os, target_arch = SUPPORTED[args.platform]
        run(
            [
                sys.executable,
                "scripts/inspect_desktop_artifact.py",
                "--app-resources",
                "desktop/build/app-resources",
                "--gateway",
                "desktop/build/gateway",
                "--model-pack",
                "desktop/build/model-pack",
                "--target-os",
                target_os,
                "--target-arch",
                target_arch,
                "--require-heartbeat",
            ]
        )
        run(
            [
                sys.executable,
                "scripts/collect_desktop_package.py",
                "--platform",
                args.platform,
                "--version",
                args.version,
                "--bundle-root",
                str(target_bundle),
                "--offline-kit",
                "desktop/build/offline-kit",
                "--output",
                str(output),
            ]
        )
    suffix = ".zip" if args.platform == "windows-x86_64" else ".tar.gz"
    archive = output / f"Muta_{args.version}_{args.platform}_offline{suffix}"
    if not archive.is_file() or not archive.with_name(f"{archive.name}.sha256").is_file():
        raise WorkerError(f"final package or checksum is missing: {archive}")
    return archive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", required=True, choices=tuple(SUPPORTED))
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-pack-id", default="muta-models-2026.08")
    args = parser.parse_args(argv)
    try:
        archive = build(args)
    except (OSError, WorkerError, subprocess.SubprocessError) as error:
        print(f"manual desktop worker failed: {error}", file=sys.stderr)
        return 1
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
