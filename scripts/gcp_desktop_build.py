#!/usr/bin/env python3
"""Build/cache Linux and Windows packages from the GCP coordinator."""

from __future__ import annotations

import argparse
import base64
import contextlib
import fcntl
import hashlib
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$")


class GcpBuildError(RuntimeError):
    pass


def run(
    command: list[str],
    *,
    cwd: Path = REPO_ROOT,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    print("+", shlex.join(command), flush=True)
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=capture,
        text=True,
        check=False,
    )
    if check and result.returncode:
        detail = result.stderr.strip() if capture else ""
        raise GcpBuildError(
            f"command exited {result.returncode}: {shlex.join(command)}"
            + (f"\n{detail}" if detail else "")
        )
    return result


def output_exists(uri: str) -> bool:
    return run(["gcloud", "storage", "ls", uri], capture=True, check=False).returncode == 0


def exact_worktree(commit: str, cache_root: Path) -> Path:
    run(["git", "fetch", "origin", "main"])
    if run(["git", "merge-base", "--is-ancestor", commit, "origin/main"], check=False).returncode:
        raise GcpBuildError(f"commit is not reachable from origin/main: {commit}")
    worktree = cache_root / "worktrees" / "linux-x86_64" / commit
    if worktree.exists():
        identity = run(["git", "-C", str(worktree), "rev-parse", "HEAD"], capture=True, check=False)
        if identity.returncode or identity.stdout.strip() != commit:
            raise GcpBuildError(f"unexpected cached worktree: {worktree}")
        return worktree
    run(["git", "worktree", "add", "--detach", str(worktree), commit])
    return worktree


def sync_models(worktree: Path) -> None:
    run(
        [
            sys.executable,
            "scripts/sync_desktop_model_inputs.py",
            "--source",
            str(REPO_ROOT),
            "--destination",
            str(worktree),
        ]
    )


def python_environment(worktree: Path, cache_root: Path) -> Path:
    venv = cache_root / "venvs" / "linux-x86_64"
    python = venv / "bin" / "python"
    if not python.is_file():
        uv = shutil.which("uv")
        if not uv:
            raise GcpBuildError("uv is missing; run provision_gcp_package_builder.sh")
        environment = {
            **os.environ,
            "UV_PYTHON_INSTALL_DIR": str(cache_root / "python"),
        }
        print("+", shlex.join([uv, "python", "install", "3.11"]), flush=True)
        installed = subprocess.run(
            [uv, "python", "install", "3.11"], env=environment, text=True, check=False
        )
        if installed.returncode:
            raise GcpBuildError("uv could not install Python 3.11")
        located = subprocess.run(
            [uv, "python", "find", "3.11"],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if located.returncode:
            raise GcpBuildError("uv could not locate Python 3.11")
        run([located.stdout.strip(), "-m", "venv", str(venv)])
    run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-e",
            f"{worktree}[desktop]",
        ]
    )
    return python


def archive_name(version: str, platform_name: str) -> str:
    suffix = ".zip" if platform_name == "windows-x86_64" else ".tar.gz"
    return f"Muta_{version}_{platform_name}_offline{suffix}"


def build_linux(
    worktree: Path,
    python: Path,
    cache_root: Path,
    output: Path,
    commit: str,
    version: str,
) -> None:
    run(
        [
            str(python),
            "scripts/manual_desktop_worker.py",
            "--platform",
            "linux-x86_64",
            "--version",
            version,
            "--commit",
            commit,
            "--cache-root",
            str(cache_root / "layers"),
            "--output",
            str(output),
        ],
        cwd=worktree,
    )


def model_key(worktree: Path) -> str:
    digest = hashlib.sha256(b"windows-model-input-v1\n")
    for relative in (
        "runtime/model-catalog.json",
        "models/MANIFEST.json",
        "models/pins.lock.json",
    ):
        path = worktree / relative
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def make_archives(worktree: Path, cache_root: Path, commit: str) -> tuple[Path, Path, str]:
    transfer = cache_root / "transfer"
    transfer.mkdir(parents=True, exist_ok=True)
    source_archive = transfer / f"source-{commit}.tar.gz"
    if not source_archive.is_file():
        run(
            [
                "git",
                "-C",
                str(worktree),
                "archive",
                "--format=tar.gz",
                "--output",
                str(source_archive),
                commit,
            ]
        )
    key = model_key(worktree)
    model_archive = transfer / f"model-inputs-{key}.tar.gz"
    if not model_archive.is_file():
        temporary = model_archive.with_suffix(".tmp")
        temporary.unlink(missing_ok=True)
        model_paths = [
            "muta-iq/model/muta-tutor-qwen3.5-0.8b-q4_0.gguf",
            "models/mmproj",
            "models/asr",
            "models/tts",
            "models/embed",
            "models/LICENSES",
            "models/MANIFEST.json",
            "models/pins.lock.json",
        ]
        with tarfile.open(temporary, "w:gz") as archive:
            for relative in model_paths:
                archive.add(worktree / relative, arcname=relative, recursive=True)
        temporary.replace(model_archive)
    return source_archive, model_archive, key


def ssh_base(key: Path, address: str) -> list[str]:
    return [
        "ssh",
        "-i",
        str(key),
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=10",
        f"muta-builder@{address}",
    ]


def powershell_command(script: str) -> list[str]:
    """Encode PowerShell so OpenSSH cannot reinterpret spaces or operators."""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-EncodedCommand",
        encoded,
    ]


@contextlib.contextmanager
def coordinator_lock(cache_root: Path):
    """Serialize timer and manual builds while allowing the caller to wait safely."""
    lock_path = cache_root / "locks" / "gcp-coordinator.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        print(f"waiting for GCP package coordinator lock: {lock_path}", flush=True)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def wait_for_windows(key: Path, address: str) -> None:
    deadline = time.monotonic() + 15 * 60
    while time.monotonic() < deadline:
        probe = run(
            [*ssh_base(key, address), *powershell_command("exit 0")],
            check=False,
        )
        if probe.returncode == 0:
            return
        time.sleep(10)
    raise GcpBuildError("Windows builder did not expose SSH within 15 minutes")


def remote_has_model(key_file: Path, address: str, key: str) -> bool:
    marker = f"C:/MutaPackageCache/models/{key}/.complete"
    result = run(
        [
            *ssh_base(key_file, address),
            *powershell_command(
                f"if (Test-Path -LiteralPath '{marker}') {{ exit 0 }} else {{ exit 1 }}"
            ),
        ],
        check=False,
    )
    return result.returncode == 0


def scp_to_windows(key: Path, address: str, source: Path, name: str) -> None:
    run(
        [
            "scp",
            "-i",
            str(key),
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            str(source),
            f"muta-builder@{address}:/C:/MutaIncoming/{name}",
        ]
    )


def build_windows(
    worktree: Path,
    cache_root: Path,
    output: Path,
    commit: str,
    version: str,
    zone: str,
    instance: str,
) -> None:
    key_file = Path(
        os.environ.get("MUTA_WINDOWS_SSH_KEY", str(Path.home() / ".ssh/muta-package-windows"))
    )
    if not key_file.is_file():
        raise GcpBuildError(f"Windows builder SSH key is missing: {key_file}")
    source_archive, model_archive, models = make_archives(worktree, cache_root, commit)
    run(["gcloud", "compute", "instances", "start", instance, "--zone", zone])
    try:
        address_result = run(
            [
                "gcloud",
                "compute",
                "instances",
                "describe",
                instance,
                "--zone",
                zone,
                "--format=value(networkInterfaces[0].networkIP)",
            ],
            capture=True,
        )
        address = address_result.stdout.strip()
        if not address:
            raise GcpBuildError("Windows builder has no internal address")
        wait_for_windows(key_file, address)
        run(
            [
                *ssh_base(key_file, address),
                *powershell_command(
                    "New-Item -Force -ItemType Directory -Path 'C:/MutaIncoming' | Out-Null"
                ),
            ]
        )
        scp_to_windows(key_file, address, source_archive, source_archive.name)
        scp_to_windows(
            key_file,
            address,
            worktree / "scripts/windows_manual_desktop_build.ps1",
            "windows_manual_desktop_build.ps1",
        )
        has_models = remote_has_model(key_file, address, models)
        if not has_models:
            scp_to_windows(key_file, address, model_archive, model_archive.name)
        remote_model = f"C:/MutaIncoming/{model_archive.name}" if not has_models else ""
        command = (
            "& C:/MutaIncoming/windows_manual_desktop_build.ps1 "
            f"-SourceArchive C:/MutaIncoming/{source_archive.name} "
            f"-ModelArchive '{remote_model}' -ModelKey {models} "
            f"-Commit {commit} -Version {version}"
        )
        run(
            [
                *ssh_base(key_file, address),
                *powershell_command(command),
            ]
        )
        name = archive_name(version, "windows-x86_64")
        for suffix in ("", ".sha256"):
            run(
                [
                    "scp",
                    "-i",
                    str(key_file),
                    "-o",
                    "IdentitiesOnly=yes",
                    "-o",
                    "StrictHostKeyChecking=accept-new",
                    f"muta-builder@{address}:/C:/MutaPackageOutput/{commit}/{version}/{name}{suffix}",
                    str(output),
                ]
            )
        cleanup = (
            f"Remove-Item -Recurse -Force C:/MutaPackageOutput/{commit}/{version}; "
            f"Remove-Item -Recurse -Force C:/MutaPackageCache/source/{commit}; "
            f"Remove-Item -Force C:/MutaIncoming/{source_archive.name}"
        )
        run(
            [
                *ssh_base(key_file, address),
                *powershell_command(cleanup),
            ],
            check=False,
        )
    finally:
        run(
            ["gcloud", "compute", "instances", "stop", instance, "--zone", zone],
            check=False,
        )


def upload(output: Path, version: str, platform_name: str, prefix: str) -> None:
    name = archive_name(version, platform_name)
    for suffix in ("", ".sha256"):
        source = output / f"{name}{suffix}"
        if not source.is_file():
            raise GcpBuildError(f"expected build output is missing: {source}")
        run(["gcloud", "storage", "cp", str(source), f"{prefix}/"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--bucket", default="muta-adtc-desktop-packages")
    parser.add_argument("--zone", default="us-west1-b")
    parser.add_argument("--windows-instance", default="muta-package-windows")
    parser.add_argument("--cache-root", type=Path, default=Path.home() / ".cache/muta-packages")
    args = parser.parse_args(argv)
    try:
        user_tools = (Path.home() / ".local/bin", Path.home() / ".cargo/bin")
        os.environ["PATH"] = os.pathsep.join(
            [*(str(path) for path in user_tools), os.environ.get("PATH", "")]
        )
        if not SHA_RE.fullmatch(args.commit):
            raise GcpBuildError("--commit must be a full lowercase Git SHA")
        if not SEMVER_RE.fullmatch(args.version):
            raise GcpBuildError("--version must be SemVer")
        cache_root = args.cache_root.expanduser().resolve()
        with coordinator_lock(cache_root):
            output = cache_root / "outputs" / args.commit / args.version
            output.mkdir(parents=True, exist_ok=True)
            prefix = f"gs://{args.bucket}/builds/{args.commit}/{args.version}"
            worktree = exact_worktree(args.commit, cache_root)
            sync_models(worktree)
            python = python_environment(worktree, cache_root)
            for target in ("linux-x86_64", "windows-x86_64"):
                name = archive_name(args.version, target)
                if output_exists(f"{prefix}/{name}") and output_exists(
                    f"{prefix}/{name}.sha256"
                ):
                    print(f"final cache hit: {target}")
                    continue
                if target == "linux-x86_64":
                    build_linux(
                        worktree,
                        python,
                        cache_root,
                        output,
                        args.commit,
                        args.version,
                    )
                else:
                    build_windows(
                        worktree,
                        cache_root,
                        output,
                        args.commit,
                        args.version,
                        args.zone,
                        args.windows_instance,
                    )
                upload(output, args.version, target, prefix)
                for suffix in ("", ".sha256"):
                    (output / f"{name}{suffix}").unlink(missing_ok=True)
            print(prefix)
    except (GcpBuildError, OSError, subprocess.SubprocessError) as error:
        print(f"GCP desktop build failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
