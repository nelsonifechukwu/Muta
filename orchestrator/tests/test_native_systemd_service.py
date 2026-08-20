from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "deploy" / "systemd" / "muta-gateway.service"


def test_native_systemd_service_owns_and_restarts_the_whole_stack() -> None:
    text = SERVICE.read_text()

    assert "WorkingDirectory=%h/Muta" in text
    assert (
        "ExecStart=/usr/bin/env MUTA_NATIVE_HOST=127.0.0.1 "
        "MUTA_RT_SERVER_HOST=127.0.0.1 MUTA_RT_EXTRA_SERVER_ARGS=[] "
        "%h/Muta/run.sh --native-linux"
    ) in text
    assert "Restart=always" in text
    assert "KillMode=mixed" in text
    assert "WantedBy=default.target" in text
    assert "--host 0.0.0.0" not in text
    assert "docker" not in text.lower()


def test_native_systemd_service_pins_both_listeners_in_exec_command() -> None:
    exec_start = next(
        line for line in SERVICE.read_text().splitlines() if line.startswith("ExecStart=")
    )

    assert exec_start.startswith("ExecStart=/usr/bin/env ")
    assert "MUTA_NATIVE_HOST=127.0.0.1" in exec_start
    assert "MUTA_RT_SERVER_HOST=127.0.0.1" in exec_start
    assert "MUTA_RT_EXTRA_SERVER_ARGS=[]" in exec_start
