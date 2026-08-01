"""Target-box benchmark — the engine inside a container shaped like the deployment box.

The competition deploy target is a consumer desktop: i5 10th–12th gen / Ryzen 5
3000–5000 (6C/12T), 8 GB DDR4, integrated graphics only, 256 GB SSD, Ubuntu 22.04 — no
GPU. `scripts/bench_target_box.sh` builds that shape out of the backend image (Ubuntu
22.04 userland, the pinned AVX2-only b10035 engine) plus cgroup caps — 8 GiB hard with
swap denied, a 6-core+SMT cpuset when the host can grant one — and runs THIS module
inside. Fidelity boundaries and interpretation live in docs/benchmarking-target-box.md.

What cgroups cannot fake — DDR4 memory bandwidth, clock speed, SMT topology on the
quota fallback — is *measured and recorded* instead, so every number ships with the
context needed to map it onto a real box. Stages (each degrades to a recorded absence,
never a crash — a missing model still yields a fingerprint and a bandwidth figure):

  fingerprint   CPU model/ISA flags/affinity, cgroup caps, OS, engine + model provenance
  bandwidth     numpy memcpy GiB/s → first-order decode ceiling for the Q4_K_M weights
  llama-bench   pp512/tg128 across thread counts, tree RSS sampled (bench.sampler)
  sweep         optional: named bench.native_sweep configs over /v1/chat/completions —
                engine-reported decode, the RESULTS.md metric of record

    python -m bench.target_box                    # fingerprint + bandwidth + llama-bench
    python -m bench.target_box --sweep WINNER     # add the server-level probe
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from bench.native_sweep import BIN as SERVER_BIN
from bench.native_sweep import MODEL
from bench.sampler import sample_tree

ROOT = Path(__file__).resolve().parents[1]
BENCH_BIN = SERVER_BIN.with_name("llama-bench")
PINS = ROOT / "models" / "pins.lock.json"
ARTIFACTS = Path(__file__).resolve().parent / ".artifacts" / "target-box"

_ISA_FLAGS = ("avx2", "avx512f", "f16c", "fma", "sse4_2")


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def _cgroup_bytes(*paths: str) -> int | None:
    """First readable cgroup limit, None when unlimited/unreadable (v2 'max', v1 ~2^63)."""
    for p in paths:
        raw = _read(p)
        if raw is None or raw == "max":
            continue
        val = int(raw)
        if val < 2**60:
            return val
    return None


def _cpu_quota() -> float | None:
    """Fractional CPUs allowed by cfs quota (the cpuset-unavailable fallback), else None."""
    v2 = _read("/sys/fs/cgroup/cpu.max")
    if v2 and not v2.startswith("max"):
        quota, period = v2.split()
        return round(int(quota) / int(period), 2)
    quota, period = (
        _read("/sys/fs/cgroup/cpu/cpu.cfs_quota_us"),
        _read("/sys/fs/cgroup/cpu/cpu.cfs_period_us"),
    )
    if quota and period and int(quota) > 0:
        return round(int(quota) / int(period), 2)
    return None


def _swap_limit_bytes(mem_limit: int | None) -> int | None:
    """Net swap allowed on top of the memory cap; 0 = denied, None = unlimited/unknown.

    v1 and v2 disagree on semantics — v2 `memory.swap.max` is swap alone, v1
    `memsw.limit_in_bytes` is memory+swap combined — so normalize to "swap alone"
    here rather than letting the artifact carry an ambiguous raw number.
    """
    v2 = _read("/sys/fs/cgroup/memory.swap.max")
    if v2 is not None:
        return None if v2 == "max" else int(v2)
    v1 = _cgroup_bytes("/sys/fs/cgroup/memory/memory.memsw.limit_in_bytes")
    if v1 is not None and mem_limit:
        return v1 - mem_limit
    return None


def _pinned_core_bytes() -> int | None:
    try:
        core = json.loads(PINS.read_text())["artifacts"]["core"]["files"]
        return next(iter(core.values()))["bytes"]
    except (OSError, KeyError, StopIteration, json.JSONDecodeError):
        return None


def fingerprint(hash_model: bool = False) -> dict:
    cpuinfo = _read("/proc/cpuinfo") or ""
    flags = set()
    m = re.search(r"^flags\s*:\s*(.+)$", cpuinfo, re.MULTILINE)
    if m:
        flags = set(m.group(1).split())
    model_name = None
    m = re.search(r"^model name\s*:\s*(.+)$", cpuinfo, re.MULTILINE)
    if m:
        model_name = m.group(1)

    os_release = _read("/etc/os-release") or ""
    pretty = re.search(r'PRETTY_NAME="([^"]+)"', os_release)

    engine = None
    try:
        out = subprocess.run(
            [str(SERVER_BIN), "--version"], capture_output=True, text=True, timeout=20, check=False
        )
        engine = (out.stdout + out.stderr).strip().splitlines()[0][:200] or None
    except (OSError, subprocess.SubprocessError, IndexError):
        pass

    model: dict = {"path": str(MODEL), "present": MODEL.exists()}
    if MODEL.exists():
        model["bytes"] = MODEL.stat().st_size
        if hash_model:
            h = hashlib.sha256()
            with open(MODEL, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            model["sha256"] = h.hexdigest()
    else:
        model["pinned_bytes"] = _pinned_core_bytes()

    # cgroup limits are the truth in a container; /proc/meminfo shows the host.
    mem_limit = _cgroup_bytes(
        "/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"
    )
    return {
        "cpu_model": model_name,
        "isa": {f: (f in flags) for f in _ISA_FLAGS},
        "cpus_allowed": len(os.sched_getaffinity(0)),
        "cpu_quota": _cpu_quota(),
        "mem_limit_bytes": mem_limit,
        "swap_limit_bytes": _swap_limit_bytes(mem_limit),
        "kernel": platform.release(),
        "os": pretty.group(1) if pretty else None,
        "engine": engine,
        "model": model,
    }


def bandwidth_probe(mib: int = 512, reps: int = 5) -> dict:
    """memcpy GiB/s and the first-order decode ceiling it implies for the pinned weights.

    Decode on CPU is bandwidth-bound: every generated token streams the full weight
    file through the memory bus once. memcpy moves 2 bytes of traffic per byte copied
    (read+write), and a pure weight-stream is reads, so `2 × memcpy` approximates the
    achievable read stream — an upper bound, not a prediction (KV/activation traffic
    and sampling overhead all subtract from it).
    """
    try:
        import numpy as np

        src = np.empty(mib << 20, dtype=np.uint8)
        dst = np.empty_like(src)
        src[:] = 1
        dst[:] = 2  # fault every page in before timing
        best = 0.0
        for _ in range(reps):
            t0 = time.perf_counter()
            np.copyto(dst, src)
            best = max(best, (mib / 1024) / (time.perf_counter() - t0))
    except (MemoryError, ImportError) as e:
        return {"error": f"{type(e).__name__}: {e}"}

    result = {"buffer_mib": mib, "memcpy_gibps": round(best, 2), "stream_gibps": round(best * 2, 2)}
    weights = MODEL.stat().st_size if MODEL.exists() else _pinned_core_bytes()
    if weights:
        result["est_decode_ceiling_tps"] = round(best * 2 / (weights / 2**30), 1)
    return result


def run_llama_bench(threads: list[int], pp: int, tg: int, reps: int) -> dict:
    if not MODEL.exists():
        return {"skipped": f"model not present: {MODEL}"}
    cmd = [
        str(BENCH_BIN),
        "-m",
        str(MODEL),
        "-p",
        str(pp),
        "-n",
        str(tg),
        "-r",
        str(reps),
        "-t",
        ",".join(map(str, threads)),
        "-o",
        "json",
    ]
    print(f"▸ llama-bench: {' '.join(cmd)}", flush=True)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    with sample_tree(proc.pid) as sampler:
        out, err = proc.communicate()
    mem = sampler.report()
    result: dict = {
        "cmd": cmd,
        "rc": proc.returncode,
        "rss_peak_mib": round(mem.peak_rss_mb),
        "rss_steady_mib": round(mem.steady_state_rss_mb),
    }
    try:
        rows = json.loads(out)
        result["rows"] = [
            {k: r.get(k) for k in ("n_threads", "n_prompt", "n_gen", "avg_ts", "stddev_ts")}
            for r in rows
        ]
        result["raw_rows"] = rows
    except json.JSONDecodeError:
        result["stdout_tail"] = out[-2000:]
    if proc.returncode != 0:
        result["stderr_tail"] = err[-2000:]
    return result


def run_sweeps(names: list[str]) -> dict:
    if not MODEL.exists():
        return {"skipped": f"model not present: {MODEL}"}
    from bench.native_sweep import CONFIGS, run_config

    out = {}
    for name in names:
        if name not in CONFIGS:
            out[name] = {"error": "unknown config (see native_sweep --list)"}
            continue
        extra, suite = CONFIGS[name]
        out[name] = run_config(name, extra, suite=suite)
    return out


def _default_threads() -> list[int]:
    # Physical-core threads for decode, all-logical for comparison — mirrors the
    # RESULTS.md finding that decode wants physical cores while prefill can use SMT.
    # Under a quota fallback SMT topology is invisible; allowed-count and its half
    # are still the two interesting points.
    n = len(os.sched_getaffinity(0))
    return sorted({max(1, n // 2), n})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="target-box", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--threads", help="comma list for llama-bench (default: half and all of the allowed CPUs)"
    )
    parser.add_argument("--pp", type=int, default=512, help="prompt tokens (default 512)")
    parser.add_argument("--tg", type=int, default=128, help="generated tokens (default 128)")
    parser.add_argument("--reps", type=int, default=3, help="llama-bench repetitions")
    parser.add_argument("--no-bench", action="store_true", help="skip llama-bench")
    parser.add_argument(
        "--hash", action="store_true", help="sha256 the model into the fingerprint (~2.7 GB read)"
    )
    parser.add_argument(
        "--sweep",
        nargs="*",
        default=[],
        metavar="CONFIG",
        help="bench.native_sweep config names to run server-level",
    )
    parser.add_argument("--label", default="target-box", help="artifact filename prefix")
    args = parser.parse_args(argv)

    started = datetime.now(timezone.utc)
    report: dict = {
        "started_utc": started.isoformat(timespec="seconds"),
        "argv": argv if argv is not None else None,
    }
    report["fingerprint"] = fingerprint(hash_model=args.hash)
    report["bandwidth"] = bandwidth_probe()
    if not args.no_bench:
        threads = (
            sorted({int(t) for t in args.threads.split(",")})
            if args.threads
            else _default_threads()
        )
        report["llama_bench"] = run_llama_bench(threads, args.pp, args.tg, args.reps)
    if args.sweep:
        report["sweeps"] = run_sweeps(args.sweep)

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    out_path = ARTIFACTS / f"{args.label}-{started.strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(report, indent=1) + "\n")

    fp, bw = report["fingerprint"], report["bandwidth"]
    mem = fp["mem_limit_bytes"]
    print("\n=== target-box summary ===")
    print(
        f"cpu:        {fp['cpu_model']}  ({fp['cpus_allowed']} allowed"
        + (f", quota {fp['cpu_quota']}" if fp["cpu_quota"] else "")
        + ")"
    )
    print(
        f"isa:        avx2={fp['isa']['avx2']} avx512f={fp['isa']['avx512f']}"
        f" (engine is AVX2-only by build)"
    )
    swap = fp["swap_limit_bytes"]
    swap_txt = (
        "unlimited/unknown"
        if swap is None
        else ("denied" if swap == 0 else f"{round(swap / 2**30, 1)} GiB")
    )
    print(f"mem cap:    {round(mem / 2**30, 1) if mem else 'unlimited'} GiB (swap: {swap_txt})")
    print(f"os/engine:  {fp['os']} / {fp['engine']}")
    print(f"model:      {'present' if fp['model']['present'] else 'ABSENT'}")
    if "memcpy_gibps" in bw:
        print(
            f"bandwidth:  memcpy {bw['memcpy_gibps']} GiB/s → est decode ceiling"
            f" ≈ {bw.get('est_decode_ceiling_tps', '?')} tok/s (upper bound)"
        )
    for row in report.get("llama_bench", {}).get("rows", []):
        if row.get("avg_ts") is None:  # unexpected row shape: it is in the artifact, not lost
            continue
        kind = "pp" if row.get("n_prompt") else "tg"
        n = row.get("n_prompt") or row.get("n_gen")
        print(
            f"llama-bench {kind}{n} t={row['n_threads']}: "
            f"{row['avg_ts']:.2f} ± {row['stddev_ts'] or 0:.2f} tok/s"
        )
    print(f"artifact:   {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
