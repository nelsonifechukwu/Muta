#!/usr/bin/env python3
"""Collect one native Tauri build into uniquely named release assets."""

from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path


class CollectError(RuntimeError):
    pass


UPDATE_PATTERNS = {
    "darwin-aarch64": "macos/*.app.tar.gz",
    "darwin-x86_64": "macos/*.app.tar.gz",
    "linux-x86_64": "appimage/*.AppImage",
    "windows-x86_64": "nsis/*-setup.exe",
}


def extension(path: Path) -> str:
    for suffix in (".app.tar.gz", ".AppImage", "-setup.exe", ".dmg", ".msi", ".deb", ".rpm"):
        if path.name.endswith(suffix):
            return suffix
    return "".join(path.suffixes)


def copy_named(source: Path, output: Path, version: str, platform: str) -> Path:
    suffix = extension(source)
    destination = output / f"Muta_{version}_{platform}{suffix}"
    shutil.copy2(source, destination)
    return destination


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect(args: argparse.Namespace) -> None:
    if args.platform not in UPDATE_PATTERNS:
        raise CollectError(f"unsupported release platform: {args.platform}")
    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    bundle = args.bundle_root.resolve()
    kit = args.offline_kit.resolve()
    if not kit.is_dir():
        raise CollectError(f"offline kit is missing: {kit}")

    update_candidates = sorted(bundle.glob(UPDATE_PATTERNS[args.platform]))
    if len(update_candidates) != 1:
        raise CollectError(
            f"expected one update artifact for {args.platform}, found {update_candidates}"
        )
    update_source = update_candidates[0]
    signature_source = Path(f"{update_source}.sig")
    if not signature_source.is_file():
        raise CollectError(f"update signature is missing: {signature_source}")
    update = copy_named(update_source, output, args.version, args.platform)
    shutil.copy2(signature_source, Path(f"{update}.sig"))

    if args.platform == "linux-x86_64":
        for obsolete in (kit / "Muta", kit / "gateway", kit / "resources"):
            if obsolete.is_dir():
                shutil.rmtree(obsolete)
            elif obsolete.exists():
                obsolete.unlink()
        portable = kit / "Muta.AppImage"
        shutil.copy2(update_source, portable)
        portable.chmod(portable.stat().st_mode | 0o111)
        (kit / "README.txt").write_text(
            "Run ./Muta.AppImage. The first launch verifies and installs model-pack locally; "
            "no internet or system installation is required.\n",
            encoding="utf-8",
        )
    elif args.platform == "windows-x86_64":
        for obsolete in (kit / "Muta.exe", kit / "gateway", kit / "resources"):
            if obsolete.is_dir():
                shutil.rmtree(obsolete)
            elif obsolete.exists():
                obsolete.unlink()
        shutil.copy2(update_source, kit / "Muta-Setup.exe")
        (kit / "Install-Muta.cmd").write_text(
            "@echo off\r\n"
            "start /wait \"\" \"%~dp0Muta-Setup.exe\" /S\r\n"
            "if not exist \"%LOCALAPPDATA%\\Muta\\Muta.exe\" (\r\n"
            "  echo Muta installation was not found. 1>&2\r\n"
            "  exit /b 1\r\n"
            ")\r\n"
            "\"%LOCALAPPDATA%\\Muta\\Muta.exe\" --install-model-pack \"%~dp0model-pack\"\r\n",
            encoding="utf-8",
        )
        (kit / "README.txt").write_text(
            "Double-click Install-Muta.cmd. It installs the bundled WebView runtime, verifies "
            "the offline model pack and then opens Muta. No internet is required.\r\n",
            encoding="utf-8",
        )

    archive_format = "zip" if args.platform.startswith("windows-") else "gztar"
    archive = Path(
        shutil.make_archive(
            str(output / f"Muta_{args.version}_{args.platform}_offline"),
            archive_format,
            root_dir=kit.parent,
            base_dir=kit.name,
        )
    )

    installer_patterns = {
        "darwin-aarch64": ("dmg/*.dmg",),
        "darwin-x86_64": ("dmg/*.dmg",),
        "linux-x86_64": ("deb/*.deb", "rpm/*.rpm"),
        "windows-x86_64": ("msi/*.msi",),
    }[args.platform]
    for pattern in installer_patterns:
        for installer in sorted(bundle.glob(pattern)):
            copy_named(installer, output, args.version, args.platform)

    assets = sorted(path for path in output.iterdir() if path.is_file() and path.suffix != ".sig")
    if archive not in assets:
        raise CollectError("offline archive was not collected")
    lines = []
    for asset in assets:
        lines.append(f"{sha256(asset)}  {asset.name}")
    (output / f"SHA256SUMS_{args.platform}.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--offline-kit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        collect(args)
    except (OSError, CollectError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
