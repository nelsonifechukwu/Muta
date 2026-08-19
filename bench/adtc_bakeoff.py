"""D1 bake-off: score candidate GGUFs through the ADTC profiler's exact methodology.

Three measurements per candidate, mirroring how the official profiler
(bench/adtc-profiler @ 7adbe08) will see the file:

  throughput  llama-bench -m <gguf> -p 512 -n 128 -ngl 0 -o json
              (scored figure = tg row's avg_ts; NO -t flag — the binary's
              default thread count rules, exactly like the audit)
  memory      psutil RSS of the whole llama-bench process tree, 0.1 s sampling,
              peak = max observed (the profiler samples its own tree; ours
              excludes the ~60 MiB profiler-python overhead — add it mentally)
  accuracy    adtc_profiler.accuracy.run_benchmark() inside bench/.venv-profiler
              (lm-eval + llama-cpp-python, n_ctx=2048, no chat template) —
              the same code path the audit runs, one row per task

Rounds are interleaved across candidates (A/B/A/B, not A/A/B/B) so ambient
load on a dev host biases every candidate equally. Rows append to a JSONL;
nothing is overwritten. Hardware context is recorded per row; on this branch
every number is dev_host_provisional until it comes from the x86 target.

Usage (native, no docker — see RESULTS.md 2026-08-04 for the methodology's
first use):

  python3 -m bench.adtc_bakeoff \
      --models models/core/candidates/*.gguf \
      --bench b10035=runtime/build/bin/llama-bench \
      --bench b10175=bench/.artifacts/llama.cpp-b10175/build/bin/llama-bench \
      --rounds 3 \
      --out bench/.artifacts/bakeoff.jsonl

  python3 -m bench.adtc_bakeoff \
      --models models/core/candidates/*.gguf \
      --accuracy --tasks arc_easy:100,arc_challenge:100,sciq:100,gsm8k:40 \
      --out bench/.artifacts/bakeoff.jsonl
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import platform
import resource
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

REPO = Path(__file__).resolve().parent.parent
DEFAULT_VENV_PY = REPO / "bench" / ".venv-profiler" / "bin" / "python"

# One row per (model, task); limits sized so a 4-model battery finishes in a
# few hours on CPU. MCQ tasks are loglikelihood (cheap); gsm8k is generative
# (256 greedy tokens/doc — the expensive, and most quant-sensitive, probe).
DEFAULT_TASKS = "arc_easy:100,arc_challenge:100,sciq:100,gsm8k:40"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _append(out: Path, row: dict) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _binary_identity(path: Path) -> dict:
    proc = subprocess.run(
        [str(path), "--version"], capture_output=True, text=True, timeout=30, check=False
    )
    return {
        "path": str(path.resolve()),
        "sha256": _sha256(path),
        "version_output": (proc.stdout + proc.stderr).strip()[-2000:],
        "version_rc": proc.returncode,
    }


def _sample_tree(proc: psutil.Process, stats: dict, stop: threading.Event) -> None:
    peak = 0
    while not stop.is_set():
        try:
            family = [proc] + proc.children(recursive=True)
            rss = sum(p.memory_info().rss for p in family if p.is_running())
            peak = max(peak, rss)
        except psutil.NoSuchProcess:
            break
        stop.wait(0.1)
    stats["peak_rss_bytes"] = peak


def run_throughput(bench_bin: Path, model: Path, reps: int | None = None) -> dict:
    """Profiler-exact llama-bench invocation with tree-RSS sampling."""
    cmd = [str(bench_bin), "-m", str(model), "-p", "512", "-n", "128", "-o", "json", "-ngl", "0"]
    if reps is not None:
        cmd += ["-r", str(reps)]
    t0 = time.monotonic()
    ru_before = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    popen = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stats: dict = {}
    stop = threading.Event()
    sampler = threading.Thread(
        target=_sample_tree, args=(psutil.Process(popen.pid), stats, stop), daemon=True
    )
    sampler.start()
    stdout, stderr = popen.communicate()
    stop.set()
    sampler.join(timeout=2.0)
    wall = time.monotonic() - t0
    if popen.returncode != 0:
        return {
            "ok": False,
            "rc": popen.returncode,
            "command": cmd,
            "stdout_tail": stdout[-2000:],
            "stderr_tail": stderr[-4000:],
            "wall_s": round(wall, 1),
        }
    try:
        rows = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "rc": popen.returncode,
            "command": cmd,
            "stdout_tail": stdout[-4000:],
            "stderr_tail": stderr[-4000:],
            "parse_error": str(exc),
            "wall_s": round(wall, 1),
        }
    pp = next((r for r in rows if r.get("n_prompt") and not r.get("n_gen")), None)
    tg = next((r for r in rows if r.get("n_gen") and not r.get("n_prompt")), None)
    if pp is None or tg is None:
        return {
            "ok": False,
            "rc": popen.returncode,
            "command": cmd,
            "raw_bench_rows": rows,
            "stderr_tail": stderr[-4000:],
            "parse_error": "llama-bench JSON lacks a pp or tg row",
            "wall_s": round(wall, 1),
        }
    ru = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    # ru_maxrss: bytes on macOS, KiB on Linux. RUSAGE_CHILDREN is a high-water
    # mark across ALL children this process ever had — only trust it when it
    # moved during this run.
    scale = 1 if sys.platform == "darwin" else 1024
    # MiB, not decimal MB: the profiler's memory.py divides by 1024**2 while labelling the
    # field `_mb`. Parity with the number the audit will report matters more than SI
    # correctness — a 1e6 divisor reads ~4.9% high, which is real margin against the ±15%
    # reconciliation band and the 7 GB disqualification line.
    mib = 1024**2
    return {
        "ok": True,
        "command": cmd,
        "raw_bench_rows": rows,
        "stderr_tail": stderr[-4000:],
        "tg_avg_ts": tg.get("avg_ts") if tg else None,
        "tg_stddev_ts": tg.get("stddev_ts") if tg else None,
        "pp_avg_ts": pp.get("avg_ts") if pp else None,
        "n_threads": (tg or pp or {}).get("n_threads"),
        "peak_rss_tree_mb": round(stats.get("peak_rss_bytes", 0) / mib, 1),
        # The profiler samples ITS OWN tree, so its reading also carries the profiler
        # python process (~35-55 MiB). Add that when predicting an audit number.
        "profiler_python_overhead_mib_note": 45,
        "ru_maxrss_child_mb": round(ru * scale / mib, 1) if ru > ru_before else None,
        "wall_s": round(wall, 1),
    }


_ACCURACY_RUNNER = """
import json, sys
from pathlib import Path
from adtc_profiler import accuracy
import lm_eval

# The model-scoring path is the profiler's own LM adapter — unchanged. Only the metric
# EXTRACTION is done here explicitly: upstream `_extract_score` at 7adbe08 falls through
# to "any numeric metric" and, under lm-eval 0.4.12, picks gsm8k's `sample_len` (= the
# limit) as the score. Preference: acc_norm > acc > exact_match(strict) > exact_match.
model, task, limit = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
lm = accuracy._make_lm(model)
res = lm_eval.simple_evaluate(
    model=lm, tasks=[task], limit=limit,
    random_seed=42, numpy_random_seed=42, fewshot_random_seed=42,
)
tr = res["results"][task]
metrics = {
    k: float(v)
    for k, v in tr.items()
    if isinstance(v, (int, float))
    and not k.endswith("_stderr")
    and not k.startswith(("sample_len", "alias", "name"))
    and "_stderr," not in k
}
for pref in ("acc_norm,none", "acc,none", "exact_match,strict-match", "exact_match,flexible-extract"):
    if pref in metrics:
        score, metric = metrics[pref], pref.split(",")[0] + ("(strict)" if "strict" in pref else "")
        break
else:
    score, metric = (next(iter(metrics.items()))[1], next(iter(metrics))) if metrics else (None, None)
print(json.dumps({
    "benchmark": task, "samples": limit, "score": round(score, 4) if score is not None else None,
    "metric": metric, "all_metrics": metrics,
}))
"""


def run_accuracy(venv_py: Path, model: Path, task: str, limit: int, timeout_s: int = 14400) -> dict:
    """One lm-eval task through the official accuracy code path, subprocess-isolated.

    A timeout returns a failed ROW — it must never abort the whole battery (a 3-process
    pile-up on 2026-08-05 turned one slow task into three lost batteries).
    """
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            [str(venv_py), "-c", _ACCURACY_RUNNER, str(model), task, str(limit)],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "task": task,
            "stderr": f"timeout after {timeout_s}s",
            "wall_s": round(time.monotonic() - t0, 1),
        }
    wall = time.monotonic() - t0
    if proc.returncode != 0:
        return {"ok": False, "task": task, "stderr": proc.stderr[-2000:], "wall_s": round(wall, 1)}
    # lm-eval logs progress lines to stdout; the row is the last JSON line.
    line = next(
        (ln for ln in reversed(proc.stdout.strip().splitlines()) if ln.startswith("{")), None
    )
    if line is None:
        return {
            "ok": False,
            "task": task,
            "stderr": "no JSON row in stdout",
            "wall_s": round(wall, 1),
        }
    row = json.loads(line)
    row.update({"ok": True, "wall_s": round(wall, 1)})
    return row


def parse_tasks(spec: str) -> list[tuple[str, int]]:
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        name, _, lim = part.partition(":")
        out.append((name, int(lim) if lim else 50))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--models", nargs="+", required=True, help="candidate GGUF paths")
    ap.add_argument(
        "--bench",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="llama-bench binary to run, tagged (repeatable). Omit to skip throughput.",
    )
    ap.add_argument("--rounds", type=int, default=2, help="interleaved throughput rounds")
    ap.add_argument("--reps", type=int, default=None, help="override llama-bench -r")
    ap.add_argument("--accuracy", action="store_true", help="run the lm-eval battery")
    ap.add_argument("--tasks", default=DEFAULT_TASKS, help="task:limit list for --accuracy")
    ap.add_argument("--venv-python", type=Path, default=DEFAULT_VENV_PY)
    ap.add_argument("--out", type=Path, required=True, help="JSONL to append rows to")
    ap.add_argument(
        "--hardware-context",
        default="dev_host_provisional",
        help="explicit evidence class; e.g. x86_cloud_proxy_gcp_n2_2c4t",
    )
    args = ap.parse_args(argv)

    models = [Path(m) for m in args.models]
    missing = [m for m in models if not m.exists()]
    if missing:
        ap.error(f"missing model files: {missing}")
    benches: list[tuple[str, Path]] = []
    for spec in args.bench:
        name, _, path = spec.partition("=")
        if not path:
            ap.error(f"--bench wants NAME=PATH, got {spec!r}")
        if not Path(path).exists():
            ap.error(f"--bench binary not found: {path}")
        benches.append((name, Path(path)))

    model_sha = {model: _sha256(model) for model in models}
    bench_identity = {name: _binary_identity(path) for name, path in benches}
    base = {
        "harness": "bench/adtc_bakeoff.py",
        "host": platform.platform(),
        "machine": platform.machine(),
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cpus": psutil.cpu_count(logical=True),
        "host_ram_bytes": psutil.virtual_memory().total,
        "hardware_context": args.hardware_context,
    }

    for rnd in range(1, args.rounds + 1) if benches else []:
        for model in models:
            for bname, bbin in benches:
                print(f"[throughput] round {rnd} {model.name} via {bname}", flush=True)
                res = run_throughput(bbin, model, reps=args.reps)
                _append(
                    args.out,
                    {
                        **base,
                        "ts": _now(),
                        "kind": "throughput",
                        "round": rnd,
                        "model": model.name,
                        "model_path": str(model.resolve()),
                        "model_bytes": model.stat().st_size,
                        "model_sha256": model_sha[model],
                        "bench": bname,
                        "bench_identity": bench_identity[bname],
                        **res,
                    },
                )
                print(
                    f"  -> {res.get('tg_avg_ts')} tok/s, peak {res.get('peak_rss_tree_mb')} MB",
                    flush=True,
                )

    if args.accuracy:
        if not args.venv_python.exists():
            ap.error(
                f"venv python not found: {args.venv_python} (create bench/.venv-profiler first)"
            )
        for model in models:
            for task, limit in parse_tasks(args.tasks):
                print(f"[accuracy] {model.name} {task}:{limit}", flush=True)
                res = run_accuracy(args.venv_python, model, task, limit)
                _append(
                    args.out,
                    {
                        **base,
                        "ts": _now(),
                        "kind": "accuracy",
                        "model": model.name,
                        "model_path": str(model.resolve()),
                        "model_bytes": model.stat().st_size,
                        "model_sha256": model_sha[model],
                        "limit": limit,
                        **res,
                    },
                )
                print(
                    f"  -> {res.get('score')} ({res.get('metric')}) in {res.get('wall_s')}s",
                    flush=True,
                )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
