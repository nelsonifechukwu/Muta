from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gcp_share_relay.sh"


def _laptop_product_file(tmp_path: Path) -> Path:
    product = tmp_path / "product-name"
    product.write_text("MacBookPro18,2\n")
    return product


def test_gcp_relay_dry_run_binds_operator_locally_and_learners_to_lan(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "MUTA_GCP_RELAY_PRODUCT_NAME_FILE": str(_laptop_product_file(tmp_path)),
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


def test_gcp_relay_rejects_loopback_as_a_learner_address(tmp_path: Path) -> None:
    result = subprocess.run(
        [str(SCRIPT), "--dry-run"],
        cwd=ROOT,
        env={
            **os.environ,
            "MUTA_GCP_RELAY_PRODUCT_NAME_FILE": str(_laptop_product_file(tmp_path)),
            "MUTA_GCP_LAN_IP": "127.0.0.1",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "usable non-loopback IPv4" in result.stderr


def test_gcp_relay_forwards_fleet_config_without_printing_the_key(tmp_path: Path) -> None:
    secret = "write-only-secret-that-must-not-be-printed"
    result = subprocess.run(
        [str(SCRIPT), "--dry-run"],
        cwd=ROOT,
        env={
            **os.environ,
            "MUTA_GCP_RELAY_PRODUCT_NAME_FILE": str(_laptop_product_file(tmp_path)),
            "MUTA_GCP_LAN_IP": "192.168.50.20",
            "MUTA_FLEET_URL": "https://fleet-ingest.example",
            "MUTA_FLEET_INGEST_KEY": secret,
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Fleet heartbeat: enabled" in result.stdout
    assert "MUTA_FLEET_URL=https://fleet-ingest.example" in result.stdout
    assert "MUTA_FLEET_INGEST_KEY" in result.stdout
    assert secret not in result.stdout
    assert secret not in result.stderr


def test_gcp_relay_requires_fleet_url_and_key_together(tmp_path: Path) -> None:
    result = subprocess.run(
        [str(SCRIPT), "--dry-run"],
        cwd=ROOT,
        env={
            **os.environ,
            "MUTA_GCP_RELAY_PRODUCT_NAME_FILE": str(_laptop_product_file(tmp_path)),
            "MUTA_GCP_LAN_IP": "192.168.50.20",
            "MUTA_FLEET_URL": "https://fleet-ingest.example",
            "MUTA_FLEET_INGEST_KEY": "",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "MUTA_FLEET_INGEST_KEY is required" in result.stderr


def test_gcp_relay_refuses_to_run_inside_the_vm(tmp_path: Path) -> None:
    product = tmp_path / "product-name"
    product.write_text("Google Compute Engine\n")
    result = subprocess.run(
        [str(SCRIPT), "--dry-run"],
        cwd=ROOT,
        env={
            **os.environ,
            "MUTA_GCP_RELAY_PRODUCT_NAME_FILE": str(product),
            "MUTA_GCP_LAN_IP": "10.138.0.2",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "must run on the operator laptop" in result.stderr
    assert "10.138.0.2" not in result.stdout
