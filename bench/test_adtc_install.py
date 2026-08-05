"""Unit tests for the profiler venv bootstrap.

These never create a real venv and never touch the network — bootstrapping is covered by the
`integration`-marked test at the bottom, which is opt-in.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from bench.adtc import install


def test_sha_is_pinned_not_a_branch():
    # A moving pin makes every recorded benchmark unreproducible.
    # 7adbe08 = upstream HEAD 2026-07-30: two-sided fraud check, -ngl 0 pinned,
    # accuracy stack in the default install (see install.py comment).
    assert install.PROFILER_SHA == "7adbe08f157e9b96a670426339aca2a519706bdc"
    assert len(install.PROFILER_SHA) == 40


def test_venv_python_path_shape(tmp_path):
    assert install.venv_python(tmp_path) == tmp_path / "bin" / "python"


def test_profiler_bin_path_shape(tmp_path):
    assert install.profiler_bin(tmp_path) == tmp_path / "bin" / "adtc-profiler"


def test_is_installed_false_when_absent(tmp_path):
    assert install.is_installed(tmp_path) is False


def test_is_installed_false_when_binary_present_but_not_runnable(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    binary = bin_dir / "adtc-profiler"
    binary.write_text("#!/bin/sh\nexit 1\n")
    binary.chmod(0o755)

    def boom(*a, **k):
        raise subprocess.CalledProcessError(1, "adtc-profiler")

    monkeypatch.setattr(install.subprocess, "run", boom)
    assert install.is_installed(tmp_path) is False


def test_find_python311_rejects_too_old(monkeypatch):
    # A 3.10 interpreter must not be accepted: the profiler declares requires-python >=3.11.
    monkeypatch.setattr(install.shutil, "which", lambda name: "/usr/bin/python3")
    monkeypatch.setattr(install, "_interpreter_version", lambda p: (3, 10))
    with pytest.raises(install.ProfilerUnavailable) as exc:
        install.find_python311()
    assert "3.11" in str(exc.value)


def test_find_python311_accepts_new_enough(monkeypatch):
    monkeypatch.setattr(install.shutil, "which", lambda name: "/usr/bin/python3.12")
    monkeypatch.setattr(install, "_interpreter_version", lambda p: (3, 12))
    assert install.find_python311() == Path("/usr/bin/python3.12")


def test_run_python_raises_when_venv_missing(tmp_path):
    with pytest.raises(install.ProfilerUnavailable):
        install.run_python("print(1)", venv_dir=tmp_path)


@pytest.mark.integration
def test_ensure_profiler_bootstraps(tmp_path):
    """Opt-in: creates a real venv and downloads from GitHub. Run with `-m integration`."""
    binary = install.ensure_profiler(tmp_path)
    assert binary.exists()
    assert subprocess.run([str(binary), "--help"], capture_output=True).returncode == 0
    assert install.run_python("import adtc_profiler; print('ok')", venv_dir=tmp_path).strip() == "ok"
