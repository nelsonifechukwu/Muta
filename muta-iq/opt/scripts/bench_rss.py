#!/usr/bin/env python3
"""Run a command exactly like adtc-profiler does and sample the child tree's RSS at 10 Hz.

Mirrors adtc_profiler.memory.MemorySampler (root = this process + all descendants,
psutil memory_info().rss, 0.1 s interval; peak = max, steady = mean of last 60 s or
last half). Prints a JSON summary line prefixed with '@@RESULT ' so callers can grep it.

Usage: bench_rss.py [--tag TAG] [--out FILE] -- <cmd...>
"""
import argparse, json, subprocess, sys, threading, time, os
import psutil

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--interval", type=float, default=0.1)
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    cmd = a.cmd[1:] if a.cmd and a.cmd[0] == "--" else a.cmd
    if not cmd:
        sys.exit("no command")
    root = psutil.Process()
    samples = []
    stop = threading.Event()
    def poll():
        t0 = time.monotonic()
        while not stop.is_set():
            try:
                fam = [root] + root.children(recursive=True)
                rss = sum(p.memory_info().rss for p in fam if p.is_running())
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                stop.wait(a.interval); continue
            samples.append((time.monotonic() - t0, rss / 2**20))
            stop.wait(a.interval)
    th = threading.Thread(target=poll, daemon=True); th.start()
    t_start = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    wall = time.time() - t_start
    stop.set(); th.join(2)
    self_rss = root.memory_info().rss / 2**20
    rss = [s[1] for s in samples]
    dur = samples[-1][0] - samples[0][0] if samples else 0
    cutoff = (samples[-1][0] - min(60.0, dur / 2)) if samples else 0
    tail = [s[1] for s in samples if s[0] >= cutoff]
    res = {
        "tag": a.tag, "cmd": cmd, "returncode": proc.returncode, "wall_s": round(wall, 1),
        "peak_rss_mb": round(max(rss), 1) if rss else None,
        "steady_rss_mb": round(sum(tail) / len(tail), 1) if tail else None,
        "sampler_self_rss_mb": round(self_rss, 1),
        "n_samples": len(samples),
    }
    # try to parse llama-bench json output
    try:
        rows = json.loads(proc.stdout)
        res["bench"] = [{k: r.get(k) for k in ("n_prompt", "n_gen", "avg_ts", "stddev_ts", "n_threads", "model_type", "model_size", "avg_ns")} for r in rows]
    except Exception:
        res["stdout_head"] = proc.stdout[:400]
    res["stderr_tail"] = proc.stderr[-1500:]
    line = "@@RESULT " + json.dumps(res)
    print(line)
    if a.out:
        with open(a.out, "a") as f:
            f.write(json.dumps({**res, "samples": samples}) + "\n")
    return proc.returncode

if __name__ == "__main__":
    sys.exit(main())
