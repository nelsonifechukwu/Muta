#!/usr/bin/env python
"""Assemble the requant results table from logs in results/requant/."""
import json, re, os, glob, ast
R = "/Users/timii/Developer/Muta/muta-iq/opt/results/requant"
MODELS = "/Users/timii/Developer/Muta/muta-iq/opt/models"
BASE = "/Users/timii/Developer/Muta/muta-iq/model/bitcpm4-8b-tq2_0.gguf"
variants = [
    ("base", "bitcpm4-8b-tq2_0 (competition file)", BASE, "base", "base"),
    ("V2", "bitcpm4-8b-tq2_0-oq5_k-eq4_k", None, "bitcpm4-8b-tq2_0-oq5_k-eq4_k", None),
    ("V3", "bitcpm4-8b-tq2_0-oq4_k-eq4_k", None, "bitcpm4-8b-tq2_0-oq4_k-eq4_k", "v3"),
    ("V4", "bitcpm4-8b-tq2_0-oiq4_xs-eq4_k", None, "bitcpm4-8b-tq2_0-oiq4_xs-eq4_k", None),
    ("V5", "bitcpm4-8b-tq2_0-oq5_0-eq4_k", None, "bitcpm4-8b-tq2_0-oq5_0-eq4_k", "v5"),
    ("V6", "bitcpm4-8b-tq2_0-oq4_k-eq3_k", None, "bitcpm4-8b-tq2_0-oq4_k-eq3_k", "v6"),
    ("V7", "bitcpm4-8b-tq2_0-oq4_k-eiq4_xs", None, "bitcpm4-8b-tq2_0-oq4_k-eiq4_xs", None),
    ("V8", "bitcpm4-8b-tq1_0-oq4_k-eq4_k", None, "bitcpm4-8b-tq1_0-oq4_k-eq4_k", "v8"),
    ("V9*", "bitcpm4-8b-tq2_0-oq4_k-eq2_k", None, "bitcpm4-8b-tq2_0-oq4_k-eq2_k", "v9"),
]
def ppl(tag):
    f = f"{R}/ppl_{tag}.log"
    if not os.path.exists(f): return None, None
    m = re.search(r"Final estimate: PPL = ([\d.]+) \+/- ([\d.]+)", open(f).read())
    return (float(m.group(1)), float(m.group(2))) if m else (None, None)
def bench(f):
    if not os.path.exists(f): return None, None
    try:
        for r in json.load(open(f)):
            if r.get("n_gen") == 128: return r["avg_ts"], r["stddev_ts"]
    except Exception: pass
    return None, None
def tensors(tag):
    f = f"{R}/tensors_{tag}.txt"
    if tag == "base":
        # compute on the fly
        import subprocess
        out = subprocess.run(["/Users/timii/miniforge3/envs/ai/bin/python", f"{R}/tensor_bytes.py", BASE], capture_output=True, text=True).stdout
    else:
        if not os.path.exists(f): return None
        out = open(f).read()
    m = re.search(r"file=(\d+) B .*?body\(blk\.\*\)=([\d.]+) MiB\s+output\[(\w+)\]=([\d.]+) MiB\s+embd\[(\w+)\]=([\d.]+) MiB", out, re.S)
    if not m: return None
    return dict(file=int(m.group(1)), body=float(m.group(2)), out_t=m.group(3), out=float(m.group(4)), emb_t=m.group(5), emb=float(m.group(6)))
def acc(tag):
    if not tag: return None
    f = f"{R}/acc_{tag}.log"
    if not os.path.exists(f): return None
    for line in open(f):
        if line.startswith("{'benchmark'"):
            d = ast.literal_eval(line.strip()); return f"{d['score']:.2f} ({d['metric']}, n={d['samples']})"
    return None
base_ppl = ppl("base")[0]
base_file = os.path.getsize(BASE)
rows = []
hdr = "| variant | file MiB (bytes) | Δ vs base MiB | body / out / embd MiB | PPL (±) | ΔPPL % | tg128 tok/s (±) | rebench tok/s | arc_easy (50) |"
sep = "|---|---|---|---|---|---|---|---|---|"
print(hdr); print(sep)
for vid, name, path, tag, acctag in variants:
    t = tensors(tag)
    p, pe = ppl(tag)
    b, be = bench(f"{R}/bench_{tag}.json")
    rb, rbe = bench(f"{R}/rebench_{acctag}.json") if acctag else (None, None)
    a = acc(acctag)
    if t is None:
        print(f"| {vid} {name} | (missing) | | | | | | | |"); continue
    dppl = f"{(p/base_ppl-1)*100:+.2f}" if p and base_ppl else "—"
    print(f"| {vid} `{name}` | {t['file']/2**20:.1f} ({t['file']}) | {(t['file']-base_file)/2**20:+.1f} | {t['body']:.1f} / {t['out']:.1f} {t['out_t']} / {t['emb']:.1f} {t['emb_t']} | {p:.4f} (±{pe:.3f}) | {dppl} | {b:.2f} (±{be:.2f}) | {f'{rb:.2f} (±{rbe:.2f})' if rb else '—'} | {a or '—'} |" if p and b else f"| {vid} `{name}` | {t['file']/2**20:.1f} | | | {p} | | {b} | | {a} |")
