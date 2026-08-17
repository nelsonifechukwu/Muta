#!/usr/bin/env python
"""Per-tensor-type byte totals for a GGUF, plus body/output/embd split. Usage: tensor_bytes.py file.gguf [file2.gguf ...]"""
import sys, os
from collections import defaultdict
from gguf import GGUFReader
for path in sys.argv[1:]:
    r = GGUFReader(path)
    by_type = defaultdict(lambda: [0, 0])
    body = out = emb = other = 0
    out_t = emb_t = None
    for t in r.tensors:
        n = t.n_bytes
        by_type[t.tensor_type.name][0] += n
        by_type[t.tensor_type.name][1] += 1
        if t.name == "output.weight":
            out += n; out_t = t.tensor_type.name
        elif t.name == "token_embd.weight":
            emb += n; emb_t = t.tensor_type.name
        elif t.name.startswith("blk."):
            body += n
        else:
            other += n
    total = sum(v[0] for v in by_type.values())
    print(f"== {os.path.basename(path)}  file={os.path.getsize(path)} B ({os.path.getsize(path)/2**20:.1f} MiB)  tensors={total/2**20:.1f} MiB")
    for k, (b, c) in sorted(by_type.items(), key=lambda kv: -kv[1][0]):
        print(f"   {k:8s} n={c:4d}  {b/2**20:9.1f} MiB")
    print(f"   body(blk.*)={body/2**20:.1f} MiB  output[{out_t}]={out/2**20:.1f} MiB  embd[{emb_t}]={emb/2**20:.1f} MiB  other={other/2**20:.1f} MiB")
    # per-blk-tensor type breakdown (short) for body
    bt = defaultdict(int)
    for t in r.tensors:
        if t.name.startswith("blk."):
            bt[t.tensor_type.name] += t.n_bytes
    print("   body by type:", {k: f"{v/2**20:.1f}" for k, v in bt.items()})
