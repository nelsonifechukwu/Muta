from __future__ import annotations

import os
import socket
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gcp_share_relay.sh"
START_SCRIPT = ROOT / "scripts" / "gcp_share_start.sh"


def _laptop_product_file(tmp_path: Path) -> Path:
    product = tmp_path / "product-name"
    product.write_text("MacBookPro18,2\n")
    return product


def _executable(path: Path, body: str) -> Path:
    path.write_text(body)
    path.chmod(0o755)
    return path


def _bindable_non_loopback_ip() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect(("192.0.2.1", 9))
        return probe.getsockname()[0]


def _free_port(host: str = "127.0.0.1") -> int:
    with socket.socket() as listener:
        listener.bind((host, 0))
        return listener.getsockname()[1]


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
    assert " -T " in result.stdout
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


def test_gcp_relay_preflights_before_supplying_secret_to_real_transport(
    tmp_path: Path,
) -> None:
    secret = "stdin-only-secret"
    capture = tmp_path / "gcloud-calls.txt"
    lan_ip = _bindable_non_loopback_ip()
    _executable(
        tmp_path / "gcloud",
        "#!/bin/sh\n"
        "{ printf 'CALL'; for arg in \"$@\"; do printf '|%s' \"$arg\"; done; "
        "printf '\\nSTDIN:'; cat; printf '\\n'; } >> \"$CAPTURE_GCLOUD\"\n",
    )
    result = subprocess.run(
        [str(SCRIPT)],
        cwd=ROOT,
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "CAPTURE_GCLOUD": str(capture),
            "MUTA_GCP_RELAY_PRODUCT_NAME_FILE": str(_laptop_product_file(tmp_path)),
            "MUTA_GCP_LAN_IP": lan_ip,
            "MUTA_GCP_OPERATOR_PORT": str(_free_port()),
            "MUTA_GCP_SHARE_PORT": str(_free_port(lan_ip)),
            "MUTA_GCP_PROJECT": "review-project",
            "MUTA_FLEET_URL": "https://fleet-ingest.example",
            "MUTA_FLEET_INGEST_KEY": secret,
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    calls = capture.read_text()
    assert calls.count("CALL|") == 2
    assert "--quiet|--command=true|--project=review-project" in calls
    assert "STDIN:\nCALL|" in calls
    assert calls.endswith(f"STDIN:{secret}\n\n")
    assert calls.count(secret) == 1


def test_gcp_relay_xtrace_cannot_print_fleet_secret(tmp_path: Path) -> None:
    secret = "xtrace-secret-that-must-not-appear"
    result = subprocess.run(
        ["bash", "-x", str(SCRIPT), "--dry-run"],
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


def test_gcp_share_start_fetches_secret_and_invokes_relay_without_printing_it(
    tmp_path: Path,
) -> None:
    gcloud_capture = tmp_path / "gcloud.txt"
    relay_capture = tmp_path / "relay.txt"
    gcloud = _executable(
        tmp_path / "gcloud",
        "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$CAPTURE_GCLOUD\"\nprintf 'wrapper-secret'\n",
    )
    relay = _executable(
        tmp_path / "relay",
        "#!/bin/sh\n"
        "{ printf '%s\\n' \"$MUTA_GCP_PROJECT\" \"$MUTA_FLEET_URL\" "
        "\"$MUTA_FLEET_INGEST_KEY\"; "
        "printf '%s\\n' \"$@\"; } > \"$CAPTURE_RELAY\"\n",
    )
    result = subprocess.run(
        [str(START_SCRIPT), "--dry-run"],
        cwd=ROOT,
        env={
            **os.environ,
            "MUTA_GCP_RELAY_PRODUCT_NAME_FILE": str(_laptop_product_file(tmp_path)),
            "MUTA_GCLOUD_BIN": str(gcloud),
            "MUTA_GCP_RELAY_SCRIPT": str(relay),
            "CAPTURE_GCLOUD": str(gcloud_capture),
            "CAPTURE_RELAY": str(relay_capture),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert gcloud_capture.read_text().splitlines() == [
        "secrets",
        "versions",
        "access",
        "latest",
        "--project=muta-adtc",
        "--secret=muta-fleet-ingest-key",
    ]
    assert relay_capture.read_text().splitlines() == [
        "muta-adtc",
        "https://muta-fleet-ingest-3lobbxiywa-uc.a.run.app",
        "wrapper-secret",
        "--dry-run",
    ]
    assert "wrapper-secret" not in result.stdout
    assert "wrapper-secret" not in result.stderr


def test_gcp_share_start_xtrace_cannot_print_retrieved_secret(tmp_path: Path) -> None:
    secret = "retrieved-secret-that-must-not-appear"
    gcloud = _executable(tmp_path / "gcloud", f"#!/bin/sh\nprintf '{secret}'\n")
    relay = _executable(tmp_path / "relay", "#!/bin/sh\nexit 0\n")
    result = subprocess.run(
        ["bash", "-x", str(START_SCRIPT), "--dry-run"],
        cwd=ROOT,
        env={
            **os.environ,
            "MUTA_GCP_RELAY_PRODUCT_NAME_FILE": str(_laptop_product_file(tmp_path)),
            "MUTA_GCLOUD_BIN": str(gcloud),
            "MUTA_GCP_RELAY_SCRIPT": str(relay),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert secret not in result.stdout
    assert secret not in result.stderr


def test_gcp_share_start_refuses_vm_before_reading_secret(tmp_path: Path) -> None:
    product = tmp_path / "product-name"
    product.write_text("Google Compute Engine\n")
    gcloud_capture = tmp_path / "gcloud-called"
    gcloud = _executable(
        tmp_path / "gcloud",
        "#!/bin/sh\ntouch \"$CAPTURE_GCLOUD\"\nprintf 'must-not-be-read'\n",
    )
    result = subprocess.run(
        [str(START_SCRIPT)],
        cwd=ROOT,
        env={
            **os.environ,
            "MUTA_GCP_RELAY_PRODUCT_NAME_FILE": str(product),
            "MUTA_GCLOUD_BIN": str(gcloud),
            "CAPTURE_GCLOUD": str(gcloud_capture),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "must run on the operator laptop" in result.stderr
    assert not gcloud_capture.exists()
