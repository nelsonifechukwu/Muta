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
        capture_output=True, text=True, env=env, cwd=REPO, timeout=30,
    )
    assert out.returncode == 0, out.stderr
    return out.stdout


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
