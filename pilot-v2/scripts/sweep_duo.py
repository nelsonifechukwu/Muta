#!/usr/bin/env python3
"""Extensive serialized benchmark sweep over llama-duo modes and settings.

Perf sweep: every config runs the 6-prompt perf set in one session; per-turn
tok/s parsed from [turn] traces, peak RSS from /usr/bin/time -l.
Accuracy suite: a subset of configs answers 14 checkable questions, one
process per question (no history contamination); scored by expected-answer
regex against stdout.

Outputs: bench/.runs/sweep.jsonl and bench/.runs/accuracy.jsonl (flushed per
run so partial results survive interruption).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DUO = ROOT / "llama.cpp/build/bin/llama-duo"
OUT = ROOT / "bench/.runs"
PERF_PROMPTS = ROOT / "bench/prompts/perf.txt"
ACC_TSV = ROOT / "bench/prompts/accuracy.tsv"

B1 = str(ROOT / "bundle/muta-duo.gguf")      # SmolLM2-135M front
B2 = str(ROOT / "bundle/muta-duo-q.gguf")    # Qwen3.5-0.8B front

# (name, bundle, extra flags, in accuracy subset)
def configs():
    out = []
    for tag, bundle in (("smol", B1), ("qwen", B2)):
        b = [("front-alone",   ["--mode", "router", "--route-threshold", "99"], True),
             ("router-t0",     ["--mode", "router"], True),
             ("router-t0-hardverify", ["--mode", "router", "--hard-mode", "verify"], False),
             ("router-t-0.5",  ["--mode", "router", "--route-threshold", "-0.5"], False),
             ("router-escalate", ["--mode", "router", "--conf-threshold", "-0.9", "--carry-draft"], False),
             ("codraft-f25",   ["--mode", "codraft", "--seg-min", "64", "--seg-max", "160", "--seg-min-expert", "16", "--seg-max-expert", "40"], False),
             ("codraft-f50",   ["--mode", "codraft"], True),
             ("codraft-f75",   ["--mode", "codraft", "--seg-min", "12", "--seg-max", "28", "--seg-min-expert", "72", "--seg-max-expert", "160"], False),
             ("random-p30",    ["--mode", "random", "--p-front", "0.3", "--seg-min", "8", "--seg-max", "24"], False),
             ("random-p50",    ["--mode", "random", "--p-front", "0.5", "--seg-min", "8", "--seg-max", "24"], True),
             ("random-p70",    ["--mode", "random", "--p-front", "0.7", "--seg-min", "8", "--seg-max", "24"], False),
             ("random-p50-long", ["--mode", "random", "--p-front", "0.5", "--seg-min", "16", "--seg-max", "48"], False),
             ("random-pessimum", ["--mode", "random", "--p-front", "0.3", "--seg-min", "1", "--seg-max", "2"], False),
             ("verify-t0",     ["--mode", "verify", "--temp-front", "0"], True),
             ("verify-t07",    ["--mode", "verify"], False),
             ("verify-t0-d24", ["--mode", "verify", "--temp-front", "0", "--draft", "24", "--draft-max", "32"], False),
             ("verify-t0-tau15", ["--mode", "verify", "--temp-front", "0", "--accept-threshold", "-1.5"], False),
             ("verify-t0-greedy", ["--mode", "verify", "--temp-front", "0", "--verify-rule", "greedy"], False),
             ("verify-t0-rep24", ["--mode", "verify", "--temp-front", "0", "--repair-min", "24"], False),
             ]
        for name, flags, acc in b:
            out.append((f"{tag}/{name}", bundle, flags, acc))
    # the expert path is the same 4B in both bundles; measure accuracy once
    out.append(("shared/expert-alone", B1, ["--mode", "router", "--route-threshold", "-99", "--hard-mode", "expert"], True))
    return out

TURN_RE = re.compile(r"^\[turn\].*?tokens=(\d+).*?ms=([0-9.]+)", re.M)
ACC_RE = re.compile(r"^\[turn\] mode=verify.*?acc=([0-9.]+)", re.M)
SHARE_RE = re.compile(r"expert_share=([0-9.]+)")
RSS_RE = re.compile(r"(\d+)\s+maximum resident set size")


def run(cmd, timeout=1800):
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return p, time.time() - t0


def perf_sweep(fh):
    for name, bundle, flags, _ in configs():
        cmd = ["/usr/bin/time", "-l", str(DUO), "--bundle", bundle, *flags,
               "--prompts-file", str(PERF_PROMPTS), "--quiet", "--no-stream",
               "-n", "512", "--seed", "42"]
        print(f"[perf] {name} ...", flush=True)
        try:
            p, wall = run(cmd)
        except subprocess.TimeoutExpired:
            fh.write(json.dumps({"config": name, "error": "timeout"}) + "\n"); fh.flush()
            continue
        turns = [(int(t), float(ms)) for t, ms in TURN_RE.findall(p.stderr)]
        rss = RSS_RE.search(p.stderr)
        toks = sum(t for t, _ in turns)
        ms = sum(m for _, m in turns)
        rec = {
            "config": name,
            "bundle": Path(bundle).name,
            "flags": " ".join(flags),
            "turns": len(turns),
            "tokens": toks,
            "gen_ms": ms,
            "avg_tok_s": round(toks * 1000.0 / ms, 2) if ms > 0 else None,
            "per_turn_tok_s": [round(t * 1000.0 / m, 1) for t, m in turns if m > 0],
            "max_tok_s": max((t * 1000.0 / m for t, m in turns if m > 0), default=None),
            "peak_rss_mib": int(rss.group(1)) // (1 << 20) if rss else None,
            "wall_s": round(wall, 1),
            "exit": p.returncode,
        }
        accs = [float(a) for a in ACC_RE.findall(p.stderr)]
        if accs:
            rec["verify_acceptance"] = round(sum(accs) / len(accs), 3)
        shares = [float(s) for s in SHARE_RE.findall(p.stderr)]
        if shares:
            rec["expert_share"] = round(sum(shares) / len(shares), 3)
        if rec["max_tok_s"]:
            rec["max_tok_s"] = round(rec["max_tok_s"], 1)
        fh.write(json.dumps(rec) + "\n"); fh.flush()
        print(f"       avg={rec['avg_tok_s']} max={rec['max_tok_s']} rss={rec['peak_rss_mib']}MiB wall={rec['wall_s']}s", flush=True)


def accuracy_suite(fh):
    qa = [l.split("\t") for l in ACC_TSV.read_text().strip().split("\n")]
    for name, bundle, flags, in_acc in configs():
        if not in_acc:
            continue
        correct = 0
        details = []
        print(f"[acc] {name} ...", flush=True)
        for q, pat in qa:
            cmd = [str(DUO), "--bundle", bundle, *flags, "-p", q,
                   "--quiet", "--no-trace", "--no-stream", "-n", "200", "--seed", "42"]
            try:
                p, _ = run(cmd, timeout=600)
                ok = re.search(pat.strip(), p.stdout) is not None
            except subprocess.TimeoutExpired:
                ok = False
            correct += ok
            details.append(ok)
        rec = {"config": name, "bundle": Path(bundle).name, "n": len(qa),
               "correct": correct, "accuracy": round(correct / len(qa), 3),
               "per_q": details}
        fh.write(json.dumps(rec) + "\n"); fh.flush()
        print(f"       accuracy={rec['accuracy']} ({correct}/{len(qa)})", flush=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("all", "perf"):
        with open(OUT / "sweep.jsonl", "w") as fh:
            perf_sweep(fh)
    if which in ("all", "acc"):
        with open(OUT / "accuracy.jsonl", "w") as fh:
            accuracy_suite(fh)
    print("SWEEP COMPLETE", flush=True)


if __name__ == "__main__":
    main()
