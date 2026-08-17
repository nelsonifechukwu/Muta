#!/usr/bin/env python3
"""Collect results/audit_proxy/*.json + *.err into a markdown table (stdout)."""
import json, os, re, sys
OUT = "/Users/timii/Developer/Muta/muta-iq/opt/results/audit_proxy"
# per-token weight bytes actually streamed for tg (total tensor bytes - token_embd; from gguf-py)
BYTES = {"tq2": 2202920704, "tq1": 1847453440}
ROWS = [
 ("tq2_neon_repack",        "TQ2_0", "NEON (native M1)", "default", 4),
 ("tq2_neon_norepack",      "TQ2_0", "NEON (native M1)", "off",     4),
 ("tq2_gen_repack",         "TQ2_0", "generic C",        "default", 4),
 ("tq2_gen_norepack",       "TQ2_0", "generic C",        "off",     4),
 ("tq1_neon_repack",        "TQ1_0", "NEON (native M1)", "default", 4),
 ("tq1_neon_norepack",      "TQ1_0", "NEON (native M1)", "off",     4),
 ("tq1_gen_repack",         "TQ1_0", "generic C",        "default", 4),
 ("tq1_gen_norepack",       "TQ1_0", "generic C",        "off",     4),
 ("tq2_gen_norepack_t1",    "TQ2_0", "generic C",        "off",     1),
 ("tq2_gen_norepack_pp512", "TQ2_0", "generic C",        "off",     4),
]
def bufs(tag):
    p = os.path.join(OUT, tag + ".err")
    if not os.path.exists(p): return "", "", ""
    txt = open(p, errors="replace").read()
    m1 = re.search(r"CPU_Mapped model buffer size\s*=\s*([\d.]+ MiB)", txt)
    m2 = re.search(r"CPU_REPACK model buffer size\s*=\s*([\d.]+ MiB)", txt)
    forced = "yes" if "MUTA_FORCE_GENERIC set" in txt else "no"
    return (m1.group(1) if m1 else "?"), (m2.group(1) if m2 else "none"), forced
print("| model | kernel path | repack | threads | test | tok/s ± stddev | implied GB/s (weights) | CPU_Mapped buf | CPU_REPACK buf | generic msg |")
print("|---|---|---|---|---|---|---|---|---|---|")
res = {}
for tag, model, kern, rep, thr in ROWS:
    p = os.path.join(OUT, tag + ".json")
    mapped, repack, forced = bufs(tag)
    if not os.path.exists(p) or os.path.getsize(p) == 0:
        print(f"| {model} | {kern} | {rep} | {thr} | — | (missing) | | {mapped} | {repack} | {forced} |"); continue
    try:
        data = json.load(open(p))
    except Exception as e:
        print(f"| {model} | {kern} | {rep} | {thr} | — | (bad json: {e}) | | {mapped} | {repack} | {forced} |"); continue
    for r in data:
        test = f"pp{r['n_prompt']}" if r["n_gen"] == 0 else f"tg{r['n_gen']}"
        ts, sd = r["avg_ts"], r["stddev_ts"]
        key = "tq2" if model == "TQ2_0" else "tq1"
        gbs = f"{ts * BYTES[key] / 1e9:.2f}" if r["n_gen"] > 0 else "n/a"
        res[tag] = ts
        print(f"| {model} | {kern} | {rep} | {r['n_threads']} | {test} | {ts:.2f} ± {sd:.2f} | {gbs} | {mapped} | {repack} | {forced} |")
json.dump(res, open(os.path.join(OUT, "summary.json"), "w"), indent=1)
