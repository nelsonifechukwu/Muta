#!/usr/bin/env python3
"""Generate Tauri's signed static updater response from collected native assets."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from collect_desktop_release import UPDATE_PATTERNS


def updater_asset(root: Path, platform: str) -> Path:
    suffix = {
        "darwin-aarch64": ".app.tar.gz",
        "darwin-x86_64": ".app.tar.gz",
        "linux-x86_64": ".AppImage",
        "windows-x86_64": "-setup.exe",
    }[platform]
    candidates = sorted(
        path for path in root.iterdir() if path.is_file() and path.name.endswith(suffix)
    )
    if len(candidates) != 1:
        raise ValueError(f"expected one {platform} updater below {root}, found {candidates}")
    if not Path(f"{candidates[0]}.sig").is_file():
        raise ValueError(f"signature is missing for {candidates[0]}")
    return candidates[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--assets-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--notes", default="Muta desktop update")
    args = parser.parse_args()
    platforms = {}
    for platform in UPDATE_PATTERNS:
        asset = updater_asset(args.assets_root / platform, platform)
        signature = Path(f"{asset}.sig").read_text(encoding="utf-8").strip()
        if not signature:
            parser.error(f"empty updater signature: {asset}.sig")
        platforms[platform] = {
            "signature": signature,
            "url": (
                f"https://github.com/{args.repository}/releases/download/"
                f"{quote(args.tag, safe='')}/{quote(asset.name)}"
            ),
        }
    body = {
        "version": args.version.removeprefix("v"),
        "notes": args.notes,
        "pub_date": datetime.now(timezone.utc).isoformat(),
        "platforms": platforms,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
