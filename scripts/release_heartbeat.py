"""Resolve the production desktop heartbeat without exposing its write-only key in logs."""

from __future__ import annotations

import os
import subprocess

HEARTBEAT_URL = "https://muta-fleet-ingest-3lobbxiywa-uc.a.run.app"
GCP_PROJECT = "muta-adtc"
SECRET_NAME = "muta-fleet-ingest-key"


class HeartbeatConfigError(RuntimeError):
    pass


def release_heartbeat_environment(
    environment: dict[str, str] | None = None,
) -> dict[str, str]:
    env = dict(os.environ if environment is None else environment)
    url = env.get("MUTA_DESKTOP_HEARTBEAT_URL", "").strip()
    key = env.get("MUTA_DESKTOP_HEARTBEAT_INGEST_KEY", "").strip()
    if bool(url) != bool(key):
        raise HeartbeatConfigError("desktop heartbeat URL and ingest key must be supplied together")
    if not key:
        result = subprocess.run(
            [
                "gcloud",
                "secrets",
                "versions",
                "access",
                "latest",
                f"--project={GCP_PROJECT}",
                f"--secret={SECRET_NAME}",
            ],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        key = result.stdout.strip()
        if result.returncode or not key:
            raise HeartbeatConfigError(
                "the release builder could not read the fleet ingest key from Secret Manager"
            )
        url = HEARTBEAT_URL
    env["MUTA_DESKTOP_HEARTBEAT_URL"] = url
    env["MUTA_DESKTOP_HEARTBEAT_INGEST_KEY"] = key
    return env
