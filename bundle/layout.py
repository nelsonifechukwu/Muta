"""The bundle layout (TDD §10.1) as data, so scripts and tests agree on one description.

Paths are bundle-relative. At build time the bundle root is `dist/`; at runtime it is
`/opt/tutor`. Nothing else in the codebase may hardcode either.
"""

from __future__ import annotations

from pathlib import Path

INSTALL_ROOT = Path("/opt/tutor")
DIST_ROOT = Path("dist")

#: Directories created by `install.sh` / `package.sh`, in creation order.
BUNDLE_DIRS: tuple[str, ...] = (
    "bin",
    "models",
    "models/core",
    "models/adapters",
    "models/draft",
    "models/asr",
    "models/tts",
    "models/embed",
    "index",
    "gw",
    "gw/ui",
    "data",
    "data/twins",
    "data/kv-slots",
    "data/logs",
    "units",
)

#: Created with mode 0700 — they hold student data and the API key (TDD §10.1, §13).
PRIVATE_DIRS: tuple[str, ...] = ("data", "data/twins", "data/kv-slots", "data/logs")

MANIFEST_NAME = "models/MANIFEST.json"
VERSIONS_LOCK_NAME = "versions.lock"
API_KEY_NAME = "data/api.key"

#: Artifact roots the manifest covers. Everything under these is hashed; the gateway venv
#: and generated data are not (they are reproducible / mutable respectively).
MANIFEST_ROOTS: tuple[str, ...] = ("bin", "models", "index")


def resolve_root(explicit: str | Path | None = None) -> Path:
    """Bundle root: an explicit path, else the installed root if present, else `dist/`."""
    if explicit is not None:
        return Path(explicit)
    if INSTALL_ROOT.is_dir():
        return INSTALL_ROOT
    return DIST_ROOT
