"""Small process-tree and temperature probes shared by product and benchmarks.

This module deliberately lives in ``runtime``: the installed application needs live
telemetry, but the desktop product must not import or freeze the top-level ``bench`` tree.
The benchmark sampler reuses these functions so the scored and displayed measurements keep
the same process-family definition.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterable

import psutil

_CORE_HINTS = ("core", "cpu", "tdie", "tccd", "package")


def family(pids: int | Iterable[int]) -> dict[int, psutil.Process]:
    """Return ``[root] + children(recursive=True)`` for every measurable root PID."""
    root_pids = [pids] if isinstance(pids, int) else [pid for pid in pids if pid]
    processes: dict[int, psutil.Process] = {}
    for pid in root_pids:
        try:
            root = psutil.Process(pid)
        except psutil.NoSuchProcess:
            continue
        try:
            members = [root, *root.children(recursive=True)]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        for process in members:
            if process.is_running():
                processes[process.pid] = process
    return processes


def family_rss_bytes(pids: int | Iterable[int]) -> int:
    """Return whole-tree RSS now, or zero when nothing is measurable; never raise."""
    total = 0
    for process in family(pids).values():
        try:
            total += process.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return total


def read_temp_c() -> float | None:
    """Return CPU package/core temperature in °C, or ``None`` when unavailable."""
    if hasattr(psutil, "sensors_temperatures"):
        try:
            temperatures = psutil.sensors_temperatures() or {}
            fallback: float | None = None
            for entries in temperatures.values():
                for entry in entries:
                    if not entry.current or entry.current <= 0:
                        continue
                    label = (entry.label or "").lower()
                    if any(hint in label for hint in _CORE_HINTS):
                        return float(entry.current)
                    if fallback is None:
                        fallback = float(entry.current)
            if fallback is not None:
                return fallback
        except (AttributeError, OSError):
            pass

    if shutil.which("sensors"):
        try:
            output = subprocess.check_output(["sensors", "-u"], text=True, timeout=2)
        except (subprocess.SubprocessError, OSError):
            return None
        fallback_value: float | None = None
        block_is_core = False
        for line in output.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("+") and ":" not in stripped:
                block_is_core = any(hint in stripped.lower() for hint in _CORE_HINTS)
            if "_input:" not in line:
                continue
            try:
                value = float(line.split(":", 1)[1].strip())
            except ValueError:
                continue
            if value > 0:
                if block_is_core:
                    return value
                if fallback_value is None:
                    fallback_value = value
        return fallback_value
    return None
