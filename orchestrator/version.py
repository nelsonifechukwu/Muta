"""Build identity, so a deployed box can say exactly what it is running.

A fleet of offline classroom laptops needs to correlate a field report, a perf number, or a
data-schema state with a commit. The image build stamps MUTA_VERSION and MUTA_GIT_SHA
(docker/backend.Dockerfile ARGs → ENV); outside the image we fall back to the package version
and, if available, the local git SHA — never crashing when neither exists.
"""

from __future__ import annotations

import os
import subprocess
from functools import cache


@cache
def version() -> str:
    return os.environ.get("MUTA_VERSION") or _pkg_version() or "0.0.0+unknown"


@cache
def git_sha() -> str:
    sha = os.environ.get("MUTA_GIT_SHA")
    if sha:
        return sha
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=2
        )
        return out.stdout.strip() or "unknown" if out.returncode == 0 else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _pkg_version() -> str | None:
    try:
        from importlib.metadata import PackageNotFoundError
        from importlib.metadata import version as _v

        try:
            return _v("muta")
        except PackageNotFoundError:
            return None
    except Exception:  # noqa: BLE001
        return None
