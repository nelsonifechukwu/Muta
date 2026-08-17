#!/usr/bin/env python3
"""Copy a GGUF without the named tensors (e.g. drop a duplicated `output.weight` so llama.cpp
uses the tied `token_embd.weight` as the LM head). Metadata copied verbatim.
Usage: drop_tensor.py in.gguf out.gguf output.weight [more...]"""
import sys
sys.path.insert(0, "/Users/timii/Developer/Muta/muta-iq/opt/llama.cpp/gguf-py")
import gguf
from gguf import GGUFReader, GGUFWriter, GGUFValueType

inp, out, *drop = sys.argv[1:]
r = GGUFReader(inp)
f = r.fields
arch = bytes(f["general.architecture"].parts[f["general.architecture"].data[0]]).decode()
w = GGUFWriter(out, arch)
for fld in f.values():
    if fld.name == gguf.Keys.General.ARCHITECTURE or fld.name.startswith("GGUF."):
        continue
    vt = fld.types[0]; st = fld.types[-1] if vt == GGUFValueType.ARRAY else None
    w.add_key_value(fld.name, fld.contents(), vt, sub_type=st)
kept = [t for t in r.tensors if t.name not in drop]
dropped = [t for t in r.tensors if t.name in drop]
for t in kept:
    w.add_tensor_info(t.name, t.data.shape, t.data.dtype, t.data.nbytes, t.tensor_type)
w.write_header_to_file(); w.write_kv_data_to_file(); w.write_ti_data_to_file()
for t in kept:
    w.write_tensor_data(t.data, tensor_endianess=r.endianess)
w.close()
print(f"dropped {[(t.name, round(t.n_bytes/1e6)) for t in dropped]} MB; kept {len(kept)} tensors -> {out}")
