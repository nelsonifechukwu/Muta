from __future__ import annotations

import pytest
from inspect_desktop_artifact import verify_required_heartbeat


def test_release_heartbeat_requires_https_and_key() -> None:
    verify_required_heartbeat(
        {"heartbeat": {"url": "https://fleet.example.test", "ingest_key": "write-only"}}
    )
    with pytest.raises(RuntimeError, match="HTTPS"):
        verify_required_heartbeat(
            {"heartbeat": {"url": "http://fleet.example.test", "ingest_key": "write-only"}}
        )
    with pytest.raises(RuntimeError, match="key"):
        verify_required_heartbeat({"heartbeat": {"url": "https://fleet.example.test"}})
