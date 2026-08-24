from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gcp_share_relay.sh"


def test_gcp_relay_dry_run_binds_operator_locally_and_learners_to_lan() -> None:
    env = {
        **os.environ,
        "MUTA_GCP_LAN_IP": "192.168.50.20",
        "MUTA_GCP_VM": "review-vm",
        "MUTA_GCP_ZONE": "us-west1-b",
        "MUTA_GCP_PROJECT": "review-project",
        "MUTA_GCP_OPERATOR_PORT": "18001",
        "MUTA_GCP_SHARE_PORT": "18443",
    }
    result = subprocess.run(
        [str(SCRIPT), "--dry-run"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "http://127.0.0.1:18001/chat/" in result.stdout
    assert "https://192.168.50.20:18443/chat/" in result.stdout
    assert "127.0.0.1:18001:127.0.0.1:8000" in result.stdout
    assert "192.168.50.20:18443:127.0.0.1:18443" in result.stdout
    assert "MUTA_SHARE_HOST=192.168.50.20" in result.stdout
    assert "MUTA_SHARE_PORT=18443" in result.stdout


def test_gcp_relay_rejects_loopback_as_a_learner_address() -> None:
    result = subprocess.run(
        [str(SCRIPT), "--dry-run"],
        cwd=ROOT,
        env={**os.environ, "MUTA_GCP_LAN_IP": "127.0.0.1"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "usable non-loopback IPv4" in result.stderr
