#!/usr/bin/env python3
r"""Per-domain spec-decode acceptance harness (S4.2).

One duo process per prompt line, per prompts file. The command template must
route duo's --json-trace stream back through the process's combined output
(when running through `stream_env.sh cgrun`, write the trace to an in-container
temp file and `cat` it after a marker -- see the example below). The harness
parses the trace's `spec` events (amortizer rounds) and `turn` events, then
emits one TSV row per prompt plus a mean/min/max summary row per domain
(= prompts-file stem) to --out.

Example (streamed, gate-grade, in-container):
  BUILD_VOLUME=muta-build-r python3 scripts/spec_accept.py \
    --template 'bash scripts/stream_env.sh cgrun 2048m bash -c \
      "/build/bin/llama-duo --bundle /models/muta-trio.gguf --no-repack \
       --stream-weights --max-ram-mib 2048 --disk-gbps 2.977 \
       --ctx-expert 2048 --tier-ctx easy=2048 --ctx-front 2048 -ub 32 \
       --draft-tier easy --draft-k {k} -t 6 -n 128 \
       --json-trace /tmp/j.json -p \"\$0\"; s=\$?; \
       echo JSONTRACE-BEGIN; cat /tmp/j.json; exit \$s" {prompt}' \
    --k 8 --prompts bench/prompts/perf.txt --out bench/.runs/stream/acceptance.tsv

Serialized by construction (one subprocess at a time); nothing else heavy may
run on the host during a gate-grade sweep.
"""
from __future__ import annotations

import argparse
import json
import statistics
import shlex
import subprocess
import sys
from pathlib import Path


def parse_trace(output: str) -> list[dict]:
    lines = output.splitlines()
    marker = None
    for i, l in enumerate(lines):
        if l.strip() == "JSONTRACE-BEGIN":
            marker = i  # keep the LAST marker (one per process)
    events = []
    for l in lines[marker + 1:] if marker is not None else lines:
        l = l.strip()
        if not l.startswith('{"type"'):
            continue
        try:
            events.append(json.loads(l))
        except json.JSONDecodeError:
            pass
    return events


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--template", required=True,
                    help="shell command with {prompt} (shell-quoted by the harness) and optional {k}")
    ap.add_argument("--prompts", nargs="+", required=True, type=Path)
    ap.add_argument("--k", type=int, default=8, help="substituted for {k} and recorded per row")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--label", default="", help="free-form config label recorded per row")
    ap.add_argument("--timeout", type=int, default=900, help="per-prompt timeout, seconds")
    args = ap.parse_args()

    rows = []
    for pf in args.prompts:
        domain = pf.stem
        prompts = [l.strip() for l in pf.read_text().splitlines() if l.strip()]
        accs, toks_s = [], []
        for i, prompt in enumerate(prompts):
            cmd = args.template.replace("{k}", str(args.k)).replace("{prompt}", shlex.quote(prompt))
            print(f"[{domain} {i+1}/{len(prompts)}] {prompt[:60]}", flush=True)
            try:
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=args.timeout)
            except subprocess.TimeoutExpired:
                rows.append((domain, i, args.k, "TIMEOUT", "", "", "", "", args.label))
                continue
            ev = parse_trace(r.stdout + "\n" + r.stderr)
            spec = [e for e in ev if e.get("type") == "spec"]
            turn = [e for e in ev if e.get("type") == "turn"]
            drafted  = sum(e.get("drafted", 0) for e in spec)
            accepted = sum(e.get("accepted", 0) for e in spec)
            acc = accepted / drafted if drafted else None
            tokens = sum(e.get("tokens", 0) for e in turn)
            ms     = sum(e.get("ms", 0.0) for e in turn)
            ts = tokens * 1e3 / ms if ms > 0 else None
            if acc is not None:
                accs.append(acc)
            if ts is not None:
                toks_s.append(ts)
            rows.append((domain, i, args.k,
                         f"{acc:.3f}" if acc is not None else "n/a",
                         drafted, accepted, tokens,
                         f"{ts:.2f}" if ts is not None else "n/a",
                         args.label))
        if accs:
            rows.append((domain, "summary", args.k,
                         f"mean={statistics.mean(accs):.3f} min={min(accs):.3f} max={max(accs):.3f}",
                         "", "", "",
                         f"tok/s mean={statistics.mean(toks_s):.2f}" if toks_s else "",
                         args.label))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "a") as f:
        if f.tell() == 0:
            f.write("domain\tprompt_idx\tk\tacc\tdrafted\taccepted\ttokens\ttok_s\tlabel\n")
        for r in rows:
            f.write("\t".join(str(x) for x in r) + "\n")
    print(f"wrote {len(rows)} rows -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
