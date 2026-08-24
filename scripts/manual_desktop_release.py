#!/usr/bin/env python3
"""Coordinate one exact pushed commit into all four offline desktop archives."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

from release_heartbeat import HeartbeatConfigError, release_heartbeat_environment

REPO_ROOT = Path(__file__).resolve().parents[1]
PLATFORMS = (
    "darwin-aarch64",
    "darwin-x86_64",
    "linux-x86_64",
    "windows-x86_64",
)
MAC_PLATFORMS = PLATFORMS[:2]
GCP_PLATFORMS = PLATFORMS[2:]
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SEMVER_RE = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
INTEL_MAC_CRYPTOGRAPHY = "cryptography==46.0.3"


class ReleaseError(RuntimeError):
    pass


def run(
    command: list[str],
    *,
    cwd: Path = REPO_ROOT,
    env: dict[str, str] | None = None,
    capture: bool = False,
    dry_run: bool = False,
) -> subprocess.CompletedProcess[str]:
    print("+", shlex.join(command), flush=True)
    if dry_run:
        return subprocess.CompletedProcess(command, 0, "", "")
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=capture,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip() if capture else ""
        raise ReleaseError(
            f"command exited {result.returncode}: {shlex.join(command)}"
            + (f"\n{detail}" if detail else "")
        )
    return result


def git_output(*arguments: str) -> str:
    result = run(["git", *arguments], capture=True)
    return result.stdout.strip()


def resolve_commit(requested: str, *, fetch: bool) -> str:
    if fetch:
        run(["git", "fetch", "origin", "main"])
    commit = git_output("rev-parse", f"{requested}^{{commit}}")
    if not SHA_RE.fullmatch(commit):
        raise ReleaseError(f"Git did not resolve a full commit SHA: {commit!r}")
    reachable = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "origin/main"],
        cwd=REPO_ROOT,
        check=False,
    )
    if reachable.returncode != 0:
        raise ReleaseError(
            f"{commit} is not on origin/main; commit and push the update before packaging"
        )
    return commit


def release_version(commit: str, requested: str | None) -> str:
    if requested:
        version = requested
    else:
        exact_tag = subprocess.run(
            ["git", "describe", "--tags", "--exact-match", "--match", "v[0-9]*", commit],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if exact_tag.returncode == 0 and exact_tag.stdout.strip().startswith("v"):
            version = exact_tag.stdout.strip()[1:]
        else:
            count = git_output("rev-list", "--count", commit)
            version = f"0.1.{count}"
    if not SEMVER_RE.fullmatch(version):
        raise ReleaseError(f"package version is not SemVer: {version!r}")
    return version


def archive_name(version: str, target: str) -> str:
    suffix = ".zip" if target == "windows-x86_64" else ".tar.gz"
    return f"Muta_{version}_{target}_offline{suffix}"


def ensure_worktree(commit: str, target: str, cache_root: Path, *, dry_run: bool) -> Path:
    worktree = cache_root / "worktrees" / target / commit
    if worktree.exists():
        identity = subprocess.run(
            ["git", "-C", str(worktree), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if identity.returncode or identity.stdout.strip() != commit:
            raise ReleaseError(f"refusing an unexpected existing worktree: {worktree}")
        return worktree
    run(["git", "worktree", "add", "--detach", str(worktree), commit], dry_run=dry_run)
    return worktree


def uv_python(target: str, cache_root: Path, *, dry_run: bool) -> Path:
    architecture = "aarch64" if target == "darwin-aarch64" else "x86_64"
    override = os.environ.get(f"MUTA_MACOS_{architecture.upper()}_PYTHON")
    if override:
        return Path(override).expanduser().resolve()
    selector = f"cpython-3.11.15-macos-{architecture}-none"
    uv = shutil.which("uv")
    if not uv:
        raise ReleaseError("uv is required to provision the two macOS Python architectures")
    environment = {
        **os.environ,
        "UV_PYTHON_INSTALL_DIR": str(cache_root / "python"),
    }
    found = subprocess.run(
        [uv, "python", "find", selector],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if found.returncode:
        run([uv, "python", "install", selector], env=environment, dry_run=dry_run)
        found = run(
            [uv, "python", "find", selector],
            env=environment,
            capture=True,
            dry_run=dry_run,
        )
    if dry_run and not found.stdout.strip():
        return cache_root / "python" / selector / "bin" / "python3.11"
    return Path(found.stdout.strip()).resolve()


def mac_python(target: str, worktree: Path, cache_root: Path, *, dry_run: bool) -> Path:
    base_python = uv_python(target, cache_root, dry_run=dry_run)
    venv = cache_root / "venvs" / target
    python = venv / "bin" / "python"
    if not python.is_file():
        run([str(base_python), "-m", "venv", str(venv)], dry_run=dry_run)
    if target == "darwin-x86_64":
        # cryptography 47+ stopped publishing an Intel macOS wheel. Without this
        # compatible universal2 pin, pip tries to cross-compile OpenSSL from an
        # Apple Silicon host and the offline Intel package cannot be produced.
        run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--only-binary=:all:",
                INTEL_MAC_CRYPTOGRAPHY,
            ],
            dry_run=dry_run,
        )
    run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-e",
            f"{worktree}[desktop]",
        ],
        dry_run=dry_run,
    )
    return python


def sync_models(source: Path, worktree: Path, *, dry_run: bool) -> None:
    run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "sync_desktop_model_inputs.py"),
            "--source",
            str(source),
            "--destination",
            str(worktree),
        ],
        dry_run=dry_run,
    )


def build_mac(
    target: str,
    commit: str,
    version: str,
    cache_root: Path,
    output: Path,
    *,
    dry_run: bool,
    env: dict[str, str] | None = None,
) -> None:
    if platform.system() != "Darwin":
        raise ReleaseError("macOS packages must be coordinated from the development Mac")
    worktree = ensure_worktree(commit, target, cache_root, dry_run=dry_run)
    sync_models(REPO_ROOT, worktree, dry_run=dry_run)
    triple = "aarch64-apple-darwin" if target == "darwin-aarch64" else "x86_64-apple-darwin"
    run(["rustup", "target", "add", triple], dry_run=dry_run)
    python = mac_python(target, worktree, cache_root, dry_run=dry_run)
    run(
        [
            str(python),
            "scripts/manual_desktop_worker.py",
            "--platform",
            target,
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
        env=env,
        dry_run=dry_run,
    )


def gcs_prefix(bucket: str, commit: str, version: str) -> str:
    return f"gs://{bucket}/builds/{commit}/{version}"


def gcp_output_set_exists(commit: str, version: str, bucket: str) -> bool:
    prefix = gcs_prefix(bucket, commit, version)
    for target in GCP_PLATFORMS:
        name = archive_name(version, target)
        for suffix in ("", ".sha256"):
            result = subprocess.run(
                ["gcloud", "storage", "ls", f"{prefix}/{name}{suffix}"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode:
                return False
    return True


def gcp_addon_manifest_is_current(commit: str, bucket: str) -> bool:
    result = subprocess.run(
        ["gcloud", "storage", "cat", f"gs://{bucket}/model-addons/v1/manifest.json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        return False
    try:
        return json.loads(result.stdout).get("git_commit") == commit
    except (AttributeError, json.JSONDecodeError):
        return False


def gcp_ssh_capture(instance: str, zone: str, command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "gcloud",
            "compute",
            "ssh",
            instance,
            "--zone",
            zone,
            "--command",
            command,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def build_gcp(
    commit: str,
    version: str,
    bucket: str,
    instance: str,
    zone: str,
    *,
    dry_run: bool,
) -> None:
    if (
        not dry_run
        and gcp_output_set_exists(commit, version, bucket)
        and gcp_addon_manifest_is_current(commit, bucket)
    ):
        print("final cache hit: linux-x86_64")
        print("final cache hit: windows-x86_64")
        return

    remote = shlex.join(
        [
            "scripts/launch_gcp_desktop_build.sh",
            commit,
            version,
            bucket,
            zone,
        ]
    )
    command = "set -e; cd ~/Muta; git fetch origin main; git merge --ff-only origin/main; " + remote
    run(
        [
            "gcloud",
            "compute",
            "ssh",
            instance,
            "--zone",
            zone,
            "--command",
            command,
        ],
        dry_run=dry_run,
    )
    if dry_run:
        return

    job = f"{commit}-{version}"
    status_path = f".local/state/muta-packages/manual/{job}.status"
    log_path = f".local/state/muta-packages/manual/{job}.log"
    deadline = time.monotonic() + 6 * 60 * 60
    next_update = time.monotonic()
    while time.monotonic() < deadline:
        status_result = gcp_ssh_capture(
            instance,
            zone,
            f"cat \"$HOME/{status_path}\" 2>/dev/null || printf 'missing\\n'",
        )
        status = status_result.stdout.strip() if status_result.returncode == 0 else "unreachable"
        if status == "complete":
            if not gcp_output_set_exists(commit, version, bucket):
                raise ReleaseError("GCP job completed without the four expected cloud objects")
            if not gcp_addon_manifest_is_current(commit, bucket):
                raise ReleaseError("GCP job completed without the current model add-on manifest")
            return
        if status.startswith("failed:"):
            log_result = gcp_ssh_capture(
                instance,
                zone,
                f'tail -n 120 "$HOME/{log_path}" 2>/dev/null || true',
            )
            detail = log_result.stdout.strip()
            raise ReleaseError(
                f"GCP package job {status}"
                + (f"\nLast remote log lines:\n{detail}" if detail else "")
            )
        now = time.monotonic()
        if now >= next_update:
            print(f"GCP package job status: {status}; waiting...", flush=True)
            next_update = now + 120
        time.sleep(20)
    raise ReleaseError(
        f"GCP package job exceeded six hours; inspect $HOME/{log_path} on {instance}"
    )


def copy_gcp_outputs(
    commit: str,
    version: str,
    bucket: str,
    output: Path,
    *,
    dry_run: bool,
) -> None:
    prefix = gcs_prefix(bucket, commit, version)
    for target in GCP_PLATFORMS:
        name = archive_name(version, target)
        for suffix in ("", ".sha256"):
            run(
                ["gcloud", "storage", "cp", f"{prefix}/{name}{suffix}", str(output)],
                dry_run=dry_run,
            )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(commit: str, version: str, output: Path, *, dry_run: bool) -> Path:
    manifest_path = output / f"Muta_{version}_final-packages.json"
    if dry_run:
        print(f"would write {manifest_path}")
        return manifest_path
    files = []
    for target in PLATFORMS:
        archive = output / archive_name(version, target)
        checksum = Path(f"{archive}.sha256")
        if not archive.is_file() or not checksum.is_file():
            raise ReleaseError(f"final output is incomplete: {archive}")
        expected = checksum.read_text(encoding="utf-8").split()[0]
        actual = sha256(archive)
        if actual != expected:
            raise ReleaseError(f"checksum mismatch: {archive}")
        files.append(
            {
                "platform": target,
                "file": archive.name,
                "bytes": archive.stat().st_size,
                "sha256": actual,
            }
        )
    document = {"schema": 1, "version": version, "git_commit": commit, "files": files}
    manifest_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", default="HEAD")
    parser.add_argument("--version")
    parser.add_argument("--bucket", default="muta-adtc-desktop-packages")
    parser.add_argument("--gcp-instance", default="muta-vm")
    parser.add_argument("--gcp-zone", default="us-west1-b")
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=Path.home() / "Library/Caches/MutaPackages",
    )
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "desktop/build/final-packages")
    parser.add_argument("--gcp-only", action="store_true")
    parser.add_argument("--mac-only", action="store_true")
    parser.add_argument("--no-fetch", action="store_true")
    parser.add_argument("--skip-upload", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.gcp_only and args.mac_only:
            raise ReleaseError("--gcp-only and --mac-only are mutually exclusive")
        commit = resolve_commit(args.commit, fetch=not args.no_fetch)
        version = release_version(commit, args.version)
        output = args.output.expanduser().resolve()
        cache_root = args.cache_root.expanduser().resolve()
        if not args.dry_run:
            output.mkdir(parents=True, exist_ok=True)
        print(f"Packaging Muta {version} from {commit}")
        release_env = (
            None if args.dry_run or args.gcp_only else release_heartbeat_environment()
        )
        if not args.mac_only:
            build_gcp(
                commit,
                version,
                args.bucket,
                args.gcp_instance,
                args.gcp_zone,
                dry_run=args.dry_run,
            )
            copy_gcp_outputs(commit, version, args.bucket, output, dry_run=args.dry_run)
        if not args.gcp_only:
            for target in MAC_PLATFORMS:
                build_mac(
                    target,
                    commit,
                    version,
                    cache_root,
                    output,
                    dry_run=args.dry_run,
                    env=release_env,
                )
            if not args.skip_upload:
                prefix = gcs_prefix(args.bucket, commit, version)
                for target in MAC_PLATFORMS:
                    name = archive_name(version, target)
                    for suffix in ("", ".sha256"):
                        run(
                            [
                                "gcloud",
                                "storage",
                                "cp",
                                str(output / f"{name}{suffix}"),
                                f"{prefix}/",
                            ],
                            dry_run=args.dry_run,
                        )
        if args.gcp_only or args.mac_only:
            print("Partial platform run completed; no four-platform manifest was written.")
            return 0
        manifest = write_manifest(commit, version, output, dry_run=args.dry_run)
        if not args.skip_upload:
            run(
                [
                    "gcloud",
                    "storage",
                    "cp",
                    str(manifest),
                    f"{gcs_prefix(args.bucket, commit, version)}/",
                ],
                dry_run=args.dry_run,
            )
        print(f"Four-platform package set: {manifest}")
    except (HeartbeatConfigError, OSError, ReleaseError, subprocess.SubprocessError) as error:
        print(f"final package build failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
