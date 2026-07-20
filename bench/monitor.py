"""Live scored-metrics HUD — a separate process, attached by PID.

Deliberately external. A sampler running inside the gateway adds its own RSS to the tree it
reports, and to the tree the official profiler would measure. An observer outside the tree is
free, and the number stays honest.

The official profiler cannot do this at all: its `sample_during()` defaults to the profiler's
own PID and it emits one JSON at the end, so it can neither stream nor see llama-server. This
is our sampler, running the same math (bench/sampler.py) against the product tree.

    make monitor
    make monitor ARGS="--pid 4821 --interval 1.0"
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psutil

from bench.sampler import MemoryReport, ThermalReport, ThermalSampler, TreeSampler
from bench.score import PROVISIONAL_TPS_MAX, RAM_BUDGET_GB, score

PIDFILE = Path("data/muta.pid")
DEFAULT_PORT = 8000
DEFAULT_ENGINE_PORT = 8080


class MonitorError(RuntimeError):
    """The monitor could not attach to a running app."""


def _pid_listening_on(port: int) -> int | None:
    """PID of whatever is listening on `port`, or None.

    `psutil.net_connections()` raises AccessDenied on macOS unless run as root (verified
    2026-07-20), so it cannot be the only strategy — the dev host is exactly where the HUD
    gets used. `lsof` needs no privileges for your own processes and exists on both macOS and
    the Ubuntu target.
    """
    try:
        for conn in psutil.net_connections(kind="inet"):
            if (
                conn.laddr
                and conn.laddr.port == port
                and conn.status == psutil.CONN_LISTEN
                and conn.pid
            ):
                return conn.pid
        return None
    except (psutil.AccessDenied, OSError):
        pass

    lsof = shutil.which("lsof")
    if not lsof:
        return None
    try:
        out = subprocess.run(
            [lsof, "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    for line in out.stdout.split():
        try:
            return int(line)
        except ValueError:
            continue
    return None


def resolve_pid(explicit: int | None = None, *, port: int = DEFAULT_PORT) -> int:
    """--pid -> pidfile -> port probe -> an error that says what to do."""
    if explicit:
        return explicit

    if PIDFILE.is_file():
        try:
            candidate = int(PIDFILE.read_text().strip())
        except ValueError:
            candidate = 0
        if candidate and psutil.pid_exists(candidate):
            return candidate

    found = _pid_listening_on(port)
    if found:
        return found

    raise MonitorError(
        "could not find a running Muta gateway.\n"
        f"  tried:  --pid (not given), {PIDFILE} (absent or stale), "
        f"port {port} (nothing listening)\n"
        '  fix:    start the app with `make dev` or `./run.sh --serve`, '
        'or pass `make monitor ARGS="--pid <n>"`'
    )


def resolve_engine_pid(port: int = DEFAULT_ENGINE_PORT) -> int | None:
    """Find `llama-server`, which is a SIBLING of the gateway, not a child.

    Both the container entrypoint and the dev workflow start the engine independently, so it
    never appears in the gateway's process tree — and it is most of the scored RSS. Returns
    None when the engine is not up; the caller then reports the gateway alone and says so.
    """
    return _pid_listening_on(port)


def fetch_metrics(base_url: str) -> dict | None:
    """Recent generation rates from the app. None when unavailable — the HUD degrades."""
    try:
        r = httpx.get(f"{base_url}/internal/bench/metrics", timeout=1.0)
        return r.json() if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


def _fmt_elapsed(seconds: float) -> str:
    return f"{int(seconds) // 60:02d}:{int(seconds) % 60:02d}"


def render_lines(
    *,
    memory: MemoryReport,
    thermal: ThermalReport,
    metrics: dict | None,
    pid: int,
    names: list[str],
    elapsed_s: float,
) -> list[str]:
    """Build the panel. Pure, so it is testable without a process or a terminal."""
    last_tps = float(metrics["last_tps"]) if metrics else 0.0
    avg_tps = float(metrics["avg_tps"]) if metrics else 0.0
    count = int(metrics["count"]) if metrics else 0

    # Every displayed score term comes from score(), never from arithmetic done here.
    result = score(
        accuracy=0.0,
        tps_actual=last_tps,
        peak_rss_gb=memory.peak_rss_gb,
        max_temp_c=thermal.core_temp_c_peak,
        throttled=thermal.throttled,
        label="live",
    )

    unique = list(dict.fromkeys(names))
    tree_desc = ", ".join(unique[:3]) + (f", +{len(unique) - 3}" if len(unique) > 3 else "")

    temp = (
        f"{thermal.core_temp_c_peak:.1f} °C"
        if thermal.core_temp_c_peak is not None
        else f"—  unmeasurable on {sys.platform}"
    )
    penalty = "   −10 THERMAL" if result.p_thermal else ""
    budget = f"   OVER BUDGET (raw_eff={result.raw_s_eff:.1f})" if result.over_budget else ""

    if metrics is not None:
        tps_line = (
            f"TPS    {last_tps:6.1f} t/s last  {avg_tps:5.1f} avg/{count:<3d}"
            f"  tps_max {PROVISIONAL_TPS_MAX:.0f} prov   S_perf {result.s_perf:5.1f}"
        )
    else:
        tps_line = "TPS    —  no /internal/bench/metrics (RSS only; is the app on port 8000?)"

    return [
        f"muta ⏻ pid {pid}   tree: {tree_desc}    elapsed {_fmt_elapsed(elapsed_s)}",
        f"RSS    peak {memory.peak_rss_gb:5.2f} GB  steady {memory.steady_state_rss_gb:5.2f} GB"
        f"  budget {RAM_BUDGET_GB:.2f} GB   S_eff  {result.s_eff:5.1f}{budget}",
        tps_line,
        f"TEMP   {temp}   cpu p99 {thermal.cpu_percent_p99:.0f}%{penalty}",
    ]


def _run_loop(pids: list[int], base_url: str, interval: float) -> None:
    """Redraw until the gateway exits. rich when available, plain ANSI otherwise."""
    pid = pids[0]
    memory = TreeSampler()
    thermal = ThermalSampler()
    memory.start(pids)
    thermal.start()
    started = time.monotonic()

    def frame() -> list[str]:
        return render_lines(
            memory=memory.report(),
            thermal=thermal.report(),
            metrics=fetch_metrics(base_url),
            pid=pid,
            names=memory.process_names(),
            elapsed_s=time.monotonic() - started,
        )

    # rich.Live renders NOTHING when stdout is not a terminal, so piping the HUD to a file or
    # through `tee` would silently produce an empty log. Fall back to line output off-TTY.
    interactive = sys.stdout.isatty()
    try:
        from rich.console import Console
        from rich.live import Live
        from rich.panel import Panel

        has_rich = True
    except ImportError:
        has_rich = False  # rich is a dev extra; a bare install still gets a usable HUD

    try:
        if has_rich and interactive:
            with Live(console=Console(), refresh_per_second=4, screen=False) as live:
                while psutil.pid_exists(pid):
                    live.update(Panel("\n".join(frame()), title="muta bench", border_style="cyan"))
                    time.sleep(interval)
        else:
            while psutil.pid_exists(pid):
                # Clear only on a terminal; escape codes are noise in a captured log.
                prefix = "\033[2J\033[H" if interactive else ""
                print(prefix + "\n".join(frame()) + ("" if interactive else "\n"), flush=True)
                time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        memory.stop()
        thermal.stop()
        final = memory.report()
        print(
            f"\nfinal: peak {final.peak_rss_gb:.2f} GB  "
            f"steady {final.steady_state_rss_gb:.2f} GB",
            file=sys.stderr,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="muta-monitor", description=__doc__)
    parser.add_argument("--pid", type=int, default=None, help="attach to this PID directly")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="gateway port to probe")
    parser.add_argument(
        "--engine-port", type=int, default=DEFAULT_ENGINE_PORT, help="llama-server port to probe"
    )
    parser.add_argument("--interval", type=float, default=0.5, help="redraw interval, seconds")
    args = parser.parse_args(argv)

    try:
        pid = resolve_pid(args.pid, port=args.port)
    except MonitorError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    # The engine is a sibling process; without it the RSS number is missing most of its mass.
    engine_pid = resolve_engine_pid(args.engine_port)
    if engine_pid is None:
        print(
            f"warning: no llama-server on port {args.engine_port} — "
            "RSS covers the gateway only and understates the scored footprint",
            file=sys.stderr,
        )

    pids = [pid] + ([engine_pid] if engine_pid else [])
    _run_loop(pids, f"http://127.0.0.1:{args.port}", args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
