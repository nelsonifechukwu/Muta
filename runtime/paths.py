"""One authority for installed resources and mutable Muta state.

The source checkout and the historical portable Linux layout use ``TUTOR_ROOT`` with mutable
state below ``TUTOR_ROOT/data``. Signed desktop applications cannot write into their resource
directory and model packs must be replaceable without invalidating an application signature,
so packaged launchers pass separate absolute resource, model and data roots. Keeping the
compatibility fallback here avoids platform conditionals being copied throughout the product.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parent.parent


def resource_root() -> Path:
    """Read-only signed application resources: UI, index and native binaries."""
    explicit = os.environ.get("MUTA_RESOURCE_ROOT") or os.environ.get("TUTOR_ROOT")
    if explicit:
        return Path(explicit).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return (Path(sys.executable).resolve().parent / "resources").resolve()
    return _SOURCE_ROOT


def model_root() -> Path:
    """Root of the active, independently versioned model pack (contains ``models/``)."""
    explicit = os.environ.get("MUTA_MODEL_ROOT")
    if explicit:
        return Path(explicit).expanduser().resolve()
    # Source checkouts and the historical portable Linux bundle keep models below the root.
    return resource_root()


def data_root() -> Path:
    """Writable durable state, without a trailing historical ``data`` component."""
    explicit = os.environ.get("MUTA_DATA_ROOT")
    if explicit:
        return Path(explicit).expanduser().resolve()
    legacy = os.environ.get("TUTOR_ROOT")
    if legacy:
        return (Path(legacy).expanduser() / "data").resolve()
    return (_SOURCE_ROOT / "data").resolve()


def cache_root() -> Path:
    explicit = os.environ.get("MUTA_CACHE_ROOT")
    if explicit:
        return Path(explicit).expanduser().resolve()
    return data_root() / "cache"


def default_desktop_data_root(platform_name: str | None = None) -> Path:
    """Return the native per-user data directory without creating it.

    ``platform_name`` is injectable so packaging tests can cover every target on one host.
    The desktop entrypoint exports the resolved result through ``MUTA_DATA_ROOT`` before any
    product module is imported.
    """
    platform_name = platform_name or sys.platform
    if platform_name == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        return (Path(base) if base else Path.home() / "AppData" / "Local") / "Muta"
    if platform_name == "darwin":
        return Path.home() / "Library" / "Application Support" / "Muta"
    base = os.environ.get("XDG_DATA_HOME")
    return (Path(base).expanduser() if base else Path.home() / ".local" / "share") / "muta"


def prepare_mutable_roots() -> None:
    """Create the small durable/cache directory skeleton used before FastAPI starts."""
    for path in (
        data_root(),
        data_root() / "logs",
        data_root() / "kv-slots",
        data_root() / "twins",
        cache_root(),
    ):
        path.mkdir(parents=True, exist_ok=True)
