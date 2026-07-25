"""The one place RSS and thermal measurement math lives.

A faithful port of adtc_profiler.memory and adtc_profiler.thermal @ cf3432cf, with the tree
root parameterised so it can point at OUR process tree instead of the sampler's own. Upstream
`sample_during()` defaults to the profiler's own PID, which is why the official tool can never
measure our product.

`summarize()` is kept pure and separate precisely so `test_sampler.py` can feed the same
series through upstream's implementation and assert equality. A port that is never
cross-checked is a port that has already drifted.

Deliberate omission: upstream's macOS `ismc` temperature branch is not ported. Darwin runs are
stamped `dev_host_provisional` and never produce report-grade numbers (CLAUDE.md), so the
branch would add code that can only ever feed a provisional figure.
"""

from __future__ import annotations

import contextlib
import shutil
import subprocess
import threading
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

import psutil

_MB = 1024**2

# Upstream constants — changing these desynchronises us from the scored methodology.
POLL_INTERVAL_S = 0.1
THERMAL_INTERVAL_S = 0.5
STEADY_STATE_WINDOW_S = 60.0

_CORE_HINTS = ("core", "cpu", "tdie", "tccd", "package")


@dataclass(frozen=True)
class Sample:
    t: float
    rss_mb: float
    vms_mb: float


@dataclass(frozen=True)
class MemoryReport:
    peak_rss_mb: float
    steady_state_rss_mb: float
    peak_vms_mb: float

    @property
    def peak_rss_gb(self) -> float:
        return self.peak_rss_mb / 1024.0

    @property
    def steady_state_rss_gb(self) -> float:
        return self.steady_state_rss_mb / 1024.0


@dataclass(frozen=True)
class ThermalReport:
    cpu_percent_p99: float
    core_temp_c_peak: float | None
    throttled: bool


def family(pids: int | Iterable[int]) -> dict[int, psutil.Process]:
    """`[root] + children(recursive=True)` per root, de-duplicated by PID.

    Shared by TreeSampler (bench runs) and orchestrator/telemetry.py (the live hub) so the
    tree-walk definition — the thing the score depends on — exists exactly once."""
    root_pids = [pids] if isinstance(pids, int) else [p for p in pids if p]
    out: dict[int, psutil.Process] = {}
    for pid in root_pids:
        try:
            root = psutil.Process(pid)
        except psutil.NoSuchProcess:
            continue
        try:
            procs = [root] + root.children(recursive=True)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        for proc in procs:
            if proc.is_running():
                out[proc.pid] = proc
    return out


def family_rss_bytes(pids: int | Iterable[int]) -> int:
    """Whole-tree RSS right now; 0 when nothing is measurable. Never raises."""
    total = 0
    for proc in family(pids).values():
        try:
            total += proc.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return total


def read_temp_c() -> float | None:
    """CPU package/core temperature in °C, or None when unmeasurable (e.g. Docker on macOS:
    no hwmon in the VM). psutil first, `sensors -u` as fallback — same hint matching as the
    upstream profiler."""
    if hasattr(psutil, "sensors_temperatures"):
        try:
            temps = psutil.sensors_temperatures() or {}
            fallback: float | None = None
            for entries in temps.values():
                for entry in entries:
                    if not entry.current or entry.current <= 0:
                        continue
                    label = (entry.label or "").lower()
                    if any(h in label for h in _CORE_HINTS):
                        return float(entry.current)
                    if fallback is None:
                        fallback = float(entry.current)
            if fallback is not None:
                return fallback
        except (AttributeError, OSError):
            pass
    if shutil.which("sensors"):
        try:
            out = subprocess.check_output(["sensors", "-u"], text=True, timeout=2)
        except (subprocess.SubprocessError, OSError):
            return None
        fallback_value: float | None = None
        block_is_core = False
        for line in out.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("+") and ":" not in stripped:
                block_is_core = any(h in stripped.lower() for h in _CORE_HINTS)
            if "_input:" in line:
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


def summarize(samples: list[Sample]) -> MemoryReport:
    """Port of upstream MemorySampler.report(). Cross-checked in test_sampler.py."""
    if not samples:
        return MemoryReport(0.0, 0.0, 0.0)
    rss = [s.rss_mb for s in samples]
    vms = [s.vms_mb for s in samples]
    duration = samples[-1].t - samples[0].t
    cutoff = samples[-1].t - min(STEADY_STATE_WINDOW_S, duration / 2)
    tail = [s.rss_mb for s in samples if s.t >= cutoff]
    steady = sum(tail) / len(tail) if tail else sum(rss) / len(rss)
    return MemoryReport(
        peak_rss_mb=round(max(rss), 2),
        steady_state_rss_mb=round(steady, 2),
        peak_vms_mb=round(max(vms), 2),
    )


class TreeSampler:
    """Poll RSS/VMS across every root's `[root] + children(recursive=True)`, every 0.1 s.

    Multiple roots are supported because **our deploy topology is not one tree.**
    `llama-server` and the gateway are *siblings*, not parent and child — `docker/entrypoint.sh`
    starts them side by side, and in dev they are launched independently. A sampler rooted at
    the gateway alone sees ~60 MB of Python and misses the ~500 MB engine, which is most of
    the scored footprint. Verified 2026-07-20: gateway-only sampling reported 0.06 GB while the
    engine alone was 0.55 GB.

    Processes are de-duplicated by PID, so overlapping roots cannot double-count.
    """

    def __init__(self, interval_s: float = POLL_INTERVAL_S) -> None:
        self.interval_s = interval_s
        self._samples: list[Sample] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._root_pids: list[int] = []
        self._names: list[str] = []
        self._lock = threading.Lock()

    def _poll(self) -> None:
        roots: list[psutil.Process] = []
        for pid in self._root_pids:
            try:
                roots.append(psutil.Process(pid))
            except psutil.NoSuchProcess:
                continue
        if not roots:
            return

        t0 = time.monotonic()
        while not self._stop.is_set():
            try:
                family: dict[int, psutil.Process] = {}
                for root in roots:
                    for proc in [root] + root.children(recursive=True):
                        if proc.is_running():
                            family[proc.pid] = proc
                rss = sum(p.memory_info().rss for p in family.values())
                vms = sum(p.memory_info().vms for p in family.values())
                names = [p.name() for p in family.values()]
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                # Upstream `continue`s here, which spins. Wait first so a dead target does not
                # burn a core — the sample series is unaffected either way.
                self._stop.wait(self.interval_s)
                continue
            with self._lock:
                self._samples.append(Sample(time.monotonic() - t0, rss / _MB, vms / _MB))
                self._names = names
            self._stop.wait(self.interval_s)

    def start(self, pids: int | Iterable[int]) -> None:
        self._root_pids = [pids] if isinstance(pids, int) else [p for p in pids if p]
        self._stop.clear()
        with self._lock:
            self._samples.clear()
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def report(self) -> MemoryReport:
        with self._lock:
            return summarize(list(self._samples))

    def latest_rss_mb(self) -> float:
        with self._lock:
            return self._samples[-1].rss_mb if self._samples else 0.0

    def process_names(self) -> list[str]:
        with self._lock:
            return list(self._names)


@contextlib.contextmanager
def sample_tree(pids: int | Iterable[int]) -> Iterator[TreeSampler]:
    s = TreeSampler()
    s.start(pids)
    try:
        yield s
    finally:
        s.stop()


class ThermalSampler:
    """Port of upstream ThermalSampler: 0.5 s poll, core-hint label matching, max()."""

    def __init__(self, interval_s: float = THERMAL_INTERVAL_S) -> None:
        self.interval_s = interval_s
        self._cpu_samples: list[float] = []
        self._temp_samples: list[float] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _read_temp(self) -> float | None:
        return read_temp_c()

    def _poll(self) -> None:
        psutil.cpu_percent(interval=None)  # prime; the first call returns a meaningless 0.0
        while not self._stop.is_set():
            self._cpu_samples.append(psutil.cpu_percent(interval=self.interval_s))
            temp = self._read_temp()
            if temp is not None:
                self._temp_samples.append(temp)

    def start(self) -> None:
        self._stop.clear()
        self._cpu_samples.clear()
        self._temp_samples.clear()
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)

    def report(self) -> ThermalReport:
        if not self._cpu_samples:
            return ThermalReport(0.0, None, False)
        ordered = sorted(self._cpu_samples)
        idx = max(0, int(len(ordered) * 0.99) - 1)
        peak_temp = max(self._temp_samples) if self._temp_samples else None
        # Upstream's own flag trips only at >=95 C. It is reported as-is; the 85 C rule is
        # applied by score() from `core_temp_c_peak`. Never treat this flag as the sole signal.
        return ThermalReport(
            cpu_percent_p99=round(min(100.0, ordered[idx]), 1),
            core_temp_c_peak=round(peak_temp, 1) if peak_temp is not None else None,
            throttled=bool(peak_temp and peak_temp >= 95.0),
        )
