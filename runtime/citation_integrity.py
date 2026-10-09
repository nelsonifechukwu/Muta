"""Keep persisted resource markers from silently changing meaning after a file is deleted."""

from __future__ import annotations

import re

_RESOURCE_MARKER = re.compile(r"[ \t]*\[\s*R[1-9]\d*\s*\]", re.IGNORECASE)


def without_resource_markers(text: str) -> str:
    """Remove inline R-markers when their complete ordered source set cannot be retained."""
    return _RESOURCE_MARKER.sub("", text)
