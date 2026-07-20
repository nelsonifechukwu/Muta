"""Bootstrap and reach the pinned ADTC profiler.

Pinned to a commit SHA, not a branch: `docs/rules-digest.md` cites this SHA, and a moving pin
would make every recorded benchmark silently unreproducible.

Network is needed on first bootstrap only. That is acceptable because profiling is dev-time
work — nothing here ships to the offline flash drive.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

PROFILER_REPO = "https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler.git"
PROFILER_SHA = "cf3432cf54216617429cf3f9d3d7150fb891fdd1"

# bench/adtc/install.py -> parents[1] is bench/
VENV_DIR = Path(__file__).resolve().parents[1] / ".venv-profiler"

_MIN_PYTHON = (3, 11)
_CANDIDATES = ("python3.13", "python3.12", "python3.11", "python3")


class ProfilerUnavailable(RuntimeError):
    """The profiler could not be located, bootstrapped, or run."""


def venv_python(venv_dir: Path = VENV_DIR) -> Path:
    return venv_dir / "bin" / "python"


def profiler_bin(venv_dir: Path = VENV_DIR) -> Path:
    return venv_dir / "bin" / "adtc-profiler"


def _interpreter_version(path: Path) -> tuple[int, int]:
    out = subprocess.run(
        [str(path), "-c", "import sys; print(sys.version_info[0], sys.version_info[1])"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    major, minor = out.stdout.split()
    return int(major), int(minor)


def find_python311() -> Path:
    """Locate an interpreter new enough for the profiler."""
    tried: list[str] = []
    for name in _CANDIDATES:
        found = shutil.which(name)
        if not found:
            continue
        try:
            version = _interpreter_version(Path(found))
        except (subprocess.SubprocessError, ValueError, OSError):
            continue
        if version >= _MIN_PYTHON:
            return Path(found)
        tried.append(f"{found} ({version[0]}.{version[1]})")
    raise ProfilerUnavailable(
        "the ADTC profiler requires Python >=3.11 and none was found on PATH.\n"
        f"  tried: {', '.join(tried) or 'nothing on PATH'}\n"
        "  fix:   uv python install 3.11   (or: pyenv install 3.11 && pyenv local 3.11)\n"
        f"  note:  Muta itself stays on {sys.version_info[0]}.{sys.version_info[1]}; "
        "the profiler is isolated in its own venv."
    )


def is_installed(venv_dir: Path = VENV_DIR) -> bool:
    """True when the venv exists and its adtc-profiler actually runs."""
    binary = profiler_bin(venv_dir)
    if not binary.exists():
        return False
    try:
        subprocess.run([str(binary), "--help"], capture_output=True, check=True, timeout=60)
    except (subprocess.SubprocessError, OSError):
        return False
    return True


def ensure_profiler(venv_dir: Path = VENV_DIR) -> Path:
    """Return a working `adtc-profiler` binary, bootstrapping the venv if needed."""
    if is_installed(venv_dir):
        return profiler_bin(venv_dir)

    interpreter = find_python311()
    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [str(interpreter), "-m", "venv", str(venv_dir)],
            capture_output=True,
            text=True,
            check=True,
            timeout=300,
        )
        subprocess.run(
            [
                str(venv_python(venv_dir)),
                "-m",
                "pip",
                "install",
                "--quiet",
                f"git+{PROFILER_REPO}@{PROFILER_SHA}",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=1800,
        )
    except subprocess.CalledProcessError as e:
        raise ProfilerUnavailable(
            f"failed to bootstrap the profiler venv at {venv_dir}.\n"
            f"  pinned: {PROFILER_SHA}\n"
            "  this step needs network access; it is required once only.\n"
            f"  stderr:\n{(e.stderr or '')[:2000]}"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise ProfilerUnavailable(f"profiler bootstrap timed out: {e}") from e

    if not is_installed(venv_dir):
        raise ProfilerUnavailable(f"bootstrap completed but {profiler_bin(venv_dir)} does not run")
    return profiler_bin(venv_dir)


def run_python(code: str, *, venv_dir: Path = VENV_DIR, timeout: float = 60.0) -> str:
    """Run `code` inside the profiler venv; return stdout.

    The escape hatch that lets us reuse upstream's own GGUF parser and memory math without
    importing GPL code into this process — and it guarantees agreement with the exact
    implementation the audit will run.
    """
    python = venv_python(venv_dir)
    if not python.exists():
        raise ProfilerUnavailable(
            f"profiler venv not bootstrapped at {venv_dir}; call ensure_profiler() first"
        )
    try:
        out = subprocess.run(
            [str(python), "-c", code],
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as e:
        raise ProfilerUnavailable(
            f"code failed inside the profiler venv:\n{(e.stderr or '')[:2000]}"
        ) from e
    return out.stdout
