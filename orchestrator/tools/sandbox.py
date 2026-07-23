"""Sandboxed subprocess execution for the deterministic tools (TDD §7.5).

Two execution shapes, same jail:

* `run_once` — one process per call. Simple, exact: every request gets its own
  `RLIMIT_CPU`, so "5 CPU-seconds" means what it says.
* `WorkerPool` — warm workers with imports already paid for. `import sympy` alone is
  ~400 ms, which on a tutoring turn is felt. Wall-clock timeouts are enforced by the parent
  here (the per-*process* CPU limit becomes a cumulative budget once a worker is reused, so
  it degrades to a backstop and the parent does the per-request killing).

The jail, and why each piece is there:

* `python -s -S` with a wholly replaced environment — no `site.py`, no `.pth` hooks, no user
  site-packages, nothing inherited from the gateway. The library path the worker *does* need
  is passed explicitly, so what the tool can import is a decision rather than an accident.
* `setrlimit(AS)` — a runaway allocation dies as a `MemoryError` in the child instead of as
  an OOM kill that earlyoom might resolve against the wrong process.
* `setrlimit(CPU)` — an infinite loop (`while True: x**2`) is a *compute* hang; a wall-clock
  timeout alone would leave the CPU burning until the parent noticed.
* `setrlimit(NOFILE)` — descriptor exhaustion is the cheapest way to take down the gateway
  from inside a child.
* `setsid` — the child gets its own process group, so a timeout kills the whole tree rather
  than orphaning a grandchild.
* network: `unshare -rn` when the kernel offers it (the real guarantee), plus the worker
  disabling `socket` in-process (the portable one — macOS dev boxes have no unshare).

Nothing here claims to be a security boundary against hostile *code*: the code that runs is
emitted by our own model under a grammar, and the threat model is a runaway loop or a
prompt-injected import, not an attacker with a shell. That distinction is why this is 200
lines and not a container per call.
"""

from __future__ import annotations

import json
import os
import resource
import shutil
import subprocess
import sys
import sysconfig
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

WORKER = Path(__file__).resolve().parent / "_worker.py"


@dataclass(frozen=True)
class Limits:
    """TDD §7.5: AS 256 MiB, CPU 5 s, NOFILE 32.

    `address_space_mib` is a per-tool knob because the numbers in the TDD were written for
    SymPy. NumPy + Matplotlib reserve far more *virtual* address space than they use, so the
    renderer gets a larger AS limit — a smaller one fails at `import`, not under load, which
    would make the diagram path permanently dead rather than bounded.
    [MEASURE: peak RSS of one render on the target box, T8.]
    """

    address_space_mib: int = 256
    cpu_seconds: int = 5
    open_files: int = 32
    wall_seconds: float = 5.0


VERIFIER_LIMITS = Limits()
RENDERER_LIMITS = Limits(address_space_mib=1024, cpu_seconds=10, wall_seconds=10.0)


@dataclass
class SandboxResult:
    ok: bool
    value: Any = None
    error: str = ""
    seconds: float = 0.0
    killed: bool = False  # hit a limit (wall clock, CPU, memory) rather than failing cleanly
    stderr: str = ""

    @property
    def failed_cleanly(self) -> bool:
        return not self.ok and not self.killed


def _library_path() -> str:
    """Import path handed to a `-S` worker: this repo plus the interpreter's site-packages.

    Explicit rather than inherited — `-I` throws `PYTHONPATH` away on purpose, and rebuilding
    it deliberately is what keeps "what can the tool import" a reviewable decision.
    """
    parts = [str(Path(__file__).resolve().parents[2])]
    for key in ("purelib", "platlib"):
        path = sysconfig.get_path(key)
        if path and path not in parts:
            parts.append(path)
    return os.pathsep.join(parts)


def sandbox_env() -> dict[str, str]:
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": "/nonexistent",
        "PYTHONPATH": _library_path(),
        "PYTHONHASHSEED": "0",  # deterministic tools should be deterministic end to end
        "PYTHONDONTWRITEBYTECODE": "1",
        "MPLBACKEND": "Agg",  # never try to reach a display
        "MPLCONFIGDIR": "/tmp/muta-mpl",
        "OMP_NUM_THREADS": "1",  # a tool must not steal the decode threads (§6.4)
        "OPENBLAS_NUM_THREADS": "1",
        "NO_PROXY": "*",
    }


def _preexec(limits: Limits):
    def apply() -> None:  # runs in the child between fork and exec
        os.setsid()
        as_bytes = limits.address_space_mib * 1024 * 1024
        for what, value in (
            (resource.RLIMIT_AS, as_bytes),
            (resource.RLIMIT_CPU, limits.cpu_seconds),
            (resource.RLIMIT_NOFILE, limits.open_files),
            (resource.RLIMIT_CORE, 0),  # no core dumps: a 256 MiB core on a full disk helps nobody
        ):
            try:
                soft, hard = resource.getrlimit(what)
                resource.setrlimit(what, (value, min(value, hard) if hard > 0 else value))
            except (ValueError, OSError):
                pass  # a limit the platform refuses is a weaker jail, not a failed tool call

    return apply


def _command(limits: Limits) -> list[str]:
    # `-s -S`, deliberately NOT `-I`: `-I` implies `-E`, which throws away the PYTHONPATH we
    # build in `sandbox_env()` — the worker then cannot import SymPy at all and every
    # verification degrades to a string comparison that looks like it worked. `-s` drops the
    # user site directory and `-S` drops site.py/.pth processing, which is the isolation that
    # was actually wanted; the environment is replaced wholesale anyway (`env=sandbox_env()`),
    # so there is nothing to inherit.
    base = [sys.executable, "-s", "-S", str(WORKER)]
    unshare = shutil.which("unshare")
    if unshare and sys.platform.startswith("linux"):
        # The real network guarantee where it exists: a new, empty network namespace.
        return [unshare, "-rn", "--"] + base
    return base


def run_once(op: str, payload: dict[str, Any], limits: Limits = VERIFIER_LIMITS) -> SandboxResult:
    """One request, one process. Exact limits; pays the import cost every time."""
    started = time.monotonic()
    request = json.dumps({"op": op, **payload})
    try:
        proc = subprocess.run(
            _command(limits),
            input=request + "\n",
            capture_output=True,
            text=True,
            timeout=limits.wall_seconds,
            env=sandbox_env(),
            preexec_fn=_preexec(limits),
        )
    except subprocess.TimeoutExpired:
        return SandboxResult(False, error=f"timeout after {limits.wall_seconds}s", killed=True,
                             seconds=time.monotonic() - started)
    return _parse(proc.stdout, proc.stderr, proc.returncode, time.monotonic() - started)


def _parse(stdout: str, stderr: str, returncode: int, seconds: float) -> SandboxResult:
    line = next((ln for ln in stdout.splitlines() if ln.startswith("{")), "")
    if not line:
        killed = returncode < 0 or "MemoryError" in stderr
        reason = f"worker produced no result (exit {returncode})"
        if returncode == -24 or "SIGXCPU" in stderr:
            reason = "CPU limit exceeded"
        elif "MemoryError" in stderr:
            reason = "memory limit exceeded"
        return SandboxResult(False, error=reason, killed=killed, seconds=seconds, stderr=stderr.strip()[:500])
    body = json.loads(line)
    return SandboxResult(
        ok=bool(body.get("ok")),
        value=body.get("value"),
        error=body.get("error", ""),
        seconds=seconds,
        stderr=stderr.strip()[:500],
    )


class WorkerPool:
    """A small pool of warm workers (TDD §7.5: 2 workers each, warm imports).

    Round-robin, restart-on-death. Not a queueing system: a busy worker is *not* handed a
    second request, because a tool call is short and the alternative — head-of-line blocking
    behind someone's pathological integral — is exactly what the timeouts exist to prevent.
    """

    def __init__(self, size: int = 2, limits: Limits = VERIFIER_LIMITS) -> None:
        self.size = size
        self.limits = limits
        self._workers: list[subprocess.Popen] = []
        self._next = 0

    def _spawn(self) -> subprocess.Popen:
        # CPU limit becomes a cumulative budget across a warm worker's lifetime, so give it
        # room and let the parent enforce per-request wall clock; the rlimit stays as the
        # backstop for a worker that gets stuck between requests.
        limits = Limits(
            address_space_mib=self.limits.address_space_mib,
            cpu_seconds=self.limits.cpu_seconds * 60,
            open_files=self.limits.open_files,
            wall_seconds=self.limits.wall_seconds,
        )
        return subprocess.Popen(
            _command(limits),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=sandbox_env(),
            preexec_fn=_preexec(limits),
        )

    def start(self) -> "WorkerPool":
        while len(self._workers) < self.size:
            self._workers.append(self._spawn())
        return self

    def _pick(self) -> subprocess.Popen:
        if not self._workers:
            self.start()
        idx = self._next % len(self._workers)
        self._next += 1
        worker = self._workers[idx]
        if worker.poll() is not None:  # died on a previous request; replace it silently
            worker = self._workers[idx] = self._spawn()
        return worker

    def submit(self, op: str, payload: dict[str, Any], *, timeout: float | None = None) -> SandboxResult:
        timeout = timeout or self.limits.wall_seconds
        worker = self._pick()
        started = time.monotonic()
        try:
            assert worker.stdin is not None and worker.stdout is not None
            worker.stdin.write(json.dumps({"op": op, **payload}) + "\n")
            worker.stdin.flush()
            line = _read_line(worker, timeout)
        except (BrokenPipeError, ValueError):
            self._kill(worker)
            return SandboxResult(False, error="worker died", killed=True, seconds=time.monotonic() - started)
        seconds = time.monotonic() - started
        if line is None:
            # Timed out: the worker is now untrustworthy (it may still be computing), so it
            # is killed rather than returned to the pool.
            self._kill(worker)
            return SandboxResult(False, error=f"timeout after {timeout}s", killed=True, seconds=seconds)
        return _parse(line, "", 0, seconds)

    def _kill(self, worker: subprocess.Popen) -> None:
        with_pid = worker.pid
        try:
            os.killpg(os.getpgid(with_pid), 9)  # setsid gave it its own group: kill the tree
        except (ProcessLookupError, PermissionError):
            worker.kill()
        try:
            worker.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        if worker in self._workers:
            self._workers[self._workers.index(worker)] = self._spawn()

    def close(self) -> None:
        for worker in self._workers:
            try:
                if worker.stdin:
                    worker.stdin.close()
                worker.wait(timeout=1)
            except (subprocess.TimeoutExpired, OSError):
                worker.kill()
        self._workers.clear()

    def __enter__(self) -> "WorkerPool":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.close()


def _read_line(worker: subprocess.Popen, timeout: float) -> str | None:
    """Read one response line, giving up after `timeout` seconds.

    `select` on the pipe rather than a reader thread: one fewer thread per in-flight tool
    call in a process whose RSS is capped at 600 MiB.
    """
    import select

    assert worker.stdout is not None
    deadline = time.monotonic() + timeout
    buf = ""
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        ready, _, _ = select.select([worker.stdout], [], [], remaining)
        if not ready:
            return None
        chunk = worker.stdout.readline()
        if chunk == "":
            return None if not buf else buf
        buf += chunk
        if buf.endswith("\n"):
            return buf


@dataclass
class ToolPools:
    """The pools the gateway owns (TDD §5.1 budgets 300 MiB peak for all of this)."""

    verifier: WorkerPool = field(default_factory=lambda: WorkerPool(2, VERIFIER_LIMITS))
    renderer: WorkerPool = field(default_factory=lambda: WorkerPool(2, RENDERER_LIMITS))

    def close(self) -> None:
        self.verifier.close()
        self.renderer.close()
