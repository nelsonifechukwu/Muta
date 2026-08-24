#!/usr/bin/env python3
"""Create one copyable offline-kit archive from a native unsigned desktop build."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import stat
from pathlib import Path


class PackageError(RuntimeError):
    pass


INSTALL_GUIDE = "HOW TO INSTALL.txt"
PACKAGE_ASSETS = Path(__file__).resolve().parents[1] / "desktop" / "package"


def _copy_executable(source: Path, destination: Path) -> None:
    shutil.copy2(source, destination)
    destination.chmod(destination.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _one(root: Path, pattern: str, label: str) -> Path:
    matches = sorted(root.glob(pattern))
    if len(matches) != 1:
        raise PackageError(f"expected one {label}, found {matches}")
    return matches[0]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect(args: argparse.Namespace) -> Path:
    bundle = args.bundle_root.resolve()
    source_kit = args.offline_kit.resolve()
    if not (source_kit / "model-pack" / "model-pack.json").is_file():
        raise PackageError(f"offline model pack is missing below {source_kit}")

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    name = f"Muta_{args.version}_{args.platform}_offline"
    staging = output / name
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    shutil.copytree(source_kit / "model-pack", staging / "model-pack")

    if args.platform in {"darwin-aarch64", "darwin-x86_64"}:
        app = _one(bundle, "macos/*.app", "macOS application")
        shutil.copytree(app, staging / "Muta.app", symlinks=True)
        _copy_executable(PACKAGE_ASSETS / "macos/Muta.command", staging / "Muta.command")
        shutil.copy2(PACKAGE_ASSETS / f"macos/{INSTALL_GUIDE}", staging / INSTALL_GUIDE)
        archive = Path(
            shutil.make_archive(str(output / name), "gztar", root_dir=output, base_dir=name)
        )
    elif args.platform == "linux-x86_64":
        appimage = _one(bundle, "appimage/*.AppImage", "Linux AppImage")
        destination = staging / "Muta.AppImage"
        shutil.copy2(appimage, destination)
        destination.chmod(destination.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        _copy_executable(PACKAGE_ASSETS / "linux/Muta.sh", staging / "Muta.sh")
        shutil.copy2(PACKAGE_ASSETS / f"linux/{INSTALL_GUIDE}", staging / INSTALL_GUIDE)
        archive = Path(
            shutil.make_archive(str(output / name), "gztar", root_dir=output, base_dir=name)
        )
    elif args.platform == "windows-x86_64":
        installer = _one(bundle, "nsis/*-setup.exe", "Windows NSIS installer")
        shutil.copy2(installer, staging / "Muta-Setup.exe")
        (staging / "Install-Muta.cmd").write_text(
            (PACKAGE_ASSETS / "windows/Install-Muta.cmd").read_text(encoding="utf-8"),
            encoding="utf-8",
            newline="\r\n",
        )
        (staging / INSTALL_GUIDE).write_text(
            (PACKAGE_ASSETS / f"windows/{INSTALL_GUIDE}").read_text(encoding="utf-8"),
            encoding="utf-8",
            newline="\r\n",
        )
        archive = Path(
            shutil.make_archive(str(output / name), "zip", root_dir=output, base_dir=name)
        )
    else:
        raise PackageError(f"unsupported package platform: {args.platform}")

    shutil.rmtree(staging)
    checksum = output / f"{archive.name}.sha256"
    checksum.write_text(
        f"{_sha256(archive)}  {archive.name}\n", encoding="utf-8", newline="\n"
    )
    return archive


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--platform",
        required=True,
        choices=("darwin-aarch64", "darwin-x86_64", "linux-x86_64", "windows-x86_64"),
    )
    parser.add_argument("--version", required=True)
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--offline-kit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        archive = collect(args)
    except (OSError, PackageError) as error:
        parser.error(str(error))
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
