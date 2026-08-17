#!/usr/bin/env python
"""Compare raw bytes of blk.* tensors between two GGUFs. Usage: verify_body.py a.gguf b.gguf [max_tensors]"""
import sys, numpy as np
from gguf import GGUFReader
a, b = GGUFReader(sys.argv[1]), GGUFReader(sys.argv[2])
maxn = int(sys.argv[3]) if len(sys.argv) > 3 else 10**9
bt = {t.name: t for t in b.tensors}
same = diff = 0
checked = []
for i, ta in enumerate(a.tensors):
    if not ta.name.startswith("blk."):
        continue
    tb = bt[ta.name]
    da = np.asarray(ta.data).view(np.uint8).ravel()
    db = np.asarray(tb.data).view(np.uint8).ravel()
    ok = ta.tensor_type == tb.tensor_type and da.shape == db.shape and np.array_equal(da, db)
    if ok: same += 1
    else:
        diff += 1
        print(f"DIFF {ta.name}: {ta.tensor_type.name}/{da.shape} vs {tb.tensor_type.name}/{db.shape}")
    checked.append(ta.name)
    if len(checked) >= maxn: break
print(f"checked={len(checked)} identical={same} different={diff}")
for n in ["output.weight", "token_embd.weight"]:
    ta = {t.name: t for t in a.tensors}[n]; tb = bt[n]
    print(f"{n}: {ta.tensor_type.name} {ta.n_bytes} -> {tb.tensor_type.name} {tb.n_bytes}")
