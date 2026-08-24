from __future__ import annotations

import subprocess

import pytest
import release_heartbeat as heartbeat


def test_existing_release_heartbeat_pair_does_not_call_gcloud(monkeypatch):
    monkeypatch.setattr(
        heartbeat.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("gcloud was called")),
    )

    result = heartbeat.release_heartbeat_environment(
        {
            "MUTA_DESKTOP_HEARTBEAT_URL": "https://fleet.example",
            "MUTA_DESKTOP_HEARTBEAT_INGEST_KEY": "write-only",
        }
    )

    assert result["MUTA_DESKTOP_HEARTBEAT_INGEST_KEY"] == "write-only"


def test_release_heartbeat_reads_secret_without_printing_it(monkeypatch):
    monkeypatch.setattr(
        heartbeat.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "secret-value\n", ""),
    )

    result = heartbeat.release_heartbeat_environment({"PATH": "/bin"})

    assert result["MUTA_DESKTOP_HEARTBEAT_URL"] == heartbeat.HEARTBEAT_URL
    assert result["MUTA_DESKTOP_HEARTBEAT_INGEST_KEY"] == "secret-value"


def test_release_heartbeat_rejects_half_configuration():
    with pytest.raises(heartbeat.HeartbeatConfigError, match="supplied together"):
        heartbeat.release_heartbeat_environment(
            {"MUTA_DESKTOP_HEARTBEAT_URL": "https://fleet.example"}
        )
