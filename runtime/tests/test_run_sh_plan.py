"""`./run.sh plan` — hardware detection is testable without touching docker.

The subcommand prints `key=value` lines and exits before any docker/model logic, so these
tests shim `uname` (and optionally `nvidia-smi`) on PATH and read the decisions directly.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent


def run_plan(tmp_path, uname_s: str, uname_m: str, *args: str, nvidia: bool = False) -> str:
    shim = tmp_path / "bin"
    shim.mkdir(exist_ok=True)
    uname = shim / "uname"
    uname.write_text(
        "#!/bin/sh\n"
        f'case "$1" in -m) echo {uname_m};; *) echo {uname_s};; esac\n'
    )
    uname.chmod(uname.stat().st_mode | stat.S_IEXEC)
    if nvidia:
        smi = shim / "nvidia-smi"
        smi.write_text("#!/bin/sh\nexit 0\n")
        smi.chmod(smi.stat().st_mode | stat.S_IEXEC)
    env = {**os.environ, "PATH": f"{shim}:{os.environ['PATH']}"}
    out = subprocess.run(
        ["bash", str(REPO / "run.sh"), "plan", *args],
        capture_output=True, text=True, env=env, cwd=REPO, timeout=30, check=False,
    )
    assert out.returncode == 0, out.stderr
    return out.stdout


def _shim_curl(tmp_path, exit_code: int) -> None:
    shim = tmp_path / "bin"
    shim.mkdir(exist_ok=True)
    curl = shim / "curl"
    curl.write_text(f"#!/bin/sh\nexit {exit_code}\n")
    curl.chmod(curl.stat().st_mode | stat.S_IEXEC)


def test_plan_reports_online_when_curl_succeeds(tmp_path):
    _shim_curl(tmp_path, 0)
    out = run_plan(tmp_path, "Darwin", "arm64")
    assert "net=online" in out


def test_plan_reports_offline_when_curl_fails(tmp_path):
    _shim_curl(tmp_path, 6)  # curl exit 6: could not resolve host
    out = run_plan(tmp_path, "Darwin", "arm64")
    assert "net=offline" in out


def test_plan_on_apple_silicon_offers_metal(tmp_path):
    out = run_plan(tmp_path, "Darwin", "arm64")
    assert "host=Darwin/arm64" in out
    assert "gpu=metal-native" in out


def test_plan_with_cpu_flag_forces_cpu(tmp_path):
    out = run_plan(tmp_path, "Darwin", "arm64", "--cpu")
    assert "gpu=none" in out


def test_plan_on_linux_with_nvidia_points_at_cuda(tmp_path):
    out = run_plan(tmp_path, "Linux", "x86_64", nvidia=True)
    assert "gpu=cuda-available" in out


def test_plan_on_plain_linux_is_cpu(tmp_path):
    out = run_plan(tmp_path, "Linux", "x86_64")
    assert "gpu=none" in out


def test_native_port_probe_allows_immediate_restart_after_time_wait():
    source = (REPO / "run.sh").read_text()
    assert "setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)" in source


def test_native_launchers_reserve_a_12288_token_context():
    source = (REPO / "run.sh").read_text()
    assert "export MUTA_RT_N_CTX=12288" in source
    assert 'export MUTA_RT_N_CTX="${MUTA_RT_N_CTX:-12288}"' in source
    assert "MUTA_RT_N_CTX=2048" not in source


def test_native_preflight_imports_the_assembled_gateway():
    source = (REPO / "run.sh").read_text()
    assert source.count('import orchestrator.main, uvicorn') == 2
    assert 'import orchestrator, uvicorn' not in source
