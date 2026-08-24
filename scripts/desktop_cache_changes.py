#!/usr/bin/env python3
"""Classify a trusted main-branch diff into independently warmable desktop caches."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable

CACHE_WORKFLOWS = {
    ".github/workflows/desktop-cache.yml",
    ".github/workflows/desktop-packages.yml",
    ".github/workflows/desktop-release.yml",
    "scripts/desktop_cache_changes.py",
}
NATIVE_INPUTS = {
    "scripts/build_desktop_native.sh",
    "scripts/verify_desktop_native.sh",
    "scripts/desktop_native_pins.env",
}
MODEL_INPUTS = {
    "scripts/prepare_desktop_models.sh",
    "scripts/verify_desktop_models.py",
    "scripts/fetch_models.py",
    "scripts/fetch_models.sh",
    "scripts/model_specs.py",
    "models/pins.lock.json",
    "runtime/model-catalog.json",
    "muta-iq/download_model.sh",
}
UI_INPUTS = {"scripts/build_ui_dist.py", "ui/VISUALIZATION-LICENSES.txt"}
GATEWAY_INPUTS = {
    "pyproject.toml",
    "bench/sampler.py",
    "desktop/backend_entry.py",
    "scripts/build_desktop.py",
    "scripts/freeze_desktop_gateway.py",
    "scripts/desktop_cache_key.py",
}


def classify(paths: Iterable[str], *, force_all: bool = False) -> dict[str, bool]:
    result = {"models": force_all, "ui": force_all, "native": force_all, "gateway": force_all}
    for raw in paths:
        path = raw.strip().replace("\\", "/")
        if not path:
            continue
        if path in CACHE_WORKFLOWS:
            return {name: True for name in result}
        if path in NATIVE_INPUTS:
            result["native"] = True
        if path in MODEL_INPUTS or path.startswith(("muta-iq/opt/scripts/", "muta-iq/opt/eval/")):
            result["models"] = True
        if (
            path in UI_INPUTS
            or (path.startswith("ui/") and path.rsplit(".", 1)[-1] in {"html", "css", "js"})
            or path.startswith("ui/vendor/viz/")
        ):
            result["ui"] = True
        if path in GATEWAY_INPUTS or path.startswith(
            ("contracts/", "desktop/pyinstaller/", "orchestrator/", "runtime/")
        ):
            result["gateway"] = True
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)
    for name, changed in classify(sys.stdin, force_all=args.all).items():
        print(f"{name}={'true' if changed else 'false'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
