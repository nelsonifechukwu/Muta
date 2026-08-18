#!/usr/bin/env python3
"""Prune CJK-script tokens from a llama/SPM-tokenizer GGUF (English-scoped deployment).

Removes every vocabulary piece containing CJK / fullwidth characters (never produced when
tokenizing English/math text), renumbers the remaining ids, rewrites the tokenizer arrays and
*_token_id keys, and slices the matching rows out of token_embd.weight / output.weight at the
raw quantized-block level (rows are independent for Q4_K/Q6_K/etc — no requantization, kept
rows are byte-identical). All other tensors and metadata are copied verbatim.

Usage: prune_vocab.py in.gguf out.gguf [--dry-run] [--extra-drop-regex REGEX]
"""
import argparse, re, sys, time
from pathlib import Path

# Resolve the pinned workspace clone on macOS, Linux and a relocated checkout. The old
# developer-absolute path made the recorded "reproduce the submission model" command fail
# everywhere except its author's laptop.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "llama.cpp" / "gguf-py"))
import numpy as np
import gguf
from gguf import GGUFReader, GGUFWriter, GGUFValueType

CJK = re.compile(
    "[　-〿"    # CJK symbols & punctuation
    "぀-ヿ"    # hiragana, katakana
    "㄀-ㄯ"    # bopomofo
    "㄰-㆏"    # hangul compat jamo
    "㆐-㏿"    # kanbun, CJK strokes, katakana ext, enclosed CJK, CJK compat
    "㐀-䶿"    # CJK ext A
    "一-鿿"    # CJK unified
    "가-힯"    # hangul syllables
    "豈-﫿"    # CJK compat ideographs
    "︰-﹏"    # CJK compat forms
    "＀-￯"    # halfwidth/fullwidth forms
    "⺀-⿟"    # CJK radicals
    "\U00020000-\U0003ffff]"  # CJK ext B..H
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--extra-drop-regex", default=None)
    ap.add_argument("--pad-to", type=int, default=64, help="keep the vocab size a multiple of this (un-drops the lowest-id dropped pieces); 0 = off")
    a = ap.parse_args()

    r = GGUFReader(str(a.inp))
    f = r.fields
    tok_f, sc_f, ty_f = f["tokenizer.ggml.tokens"], f["tokenizer.ggml.scores"], f["tokenizer.ggml.token_type"]
    tokens = [bytes(tok_f.parts[i]) for i in tok_f.data]
    scores = [float(sc_f.parts[i][0]) for i in sc_f.data]
    types = [int(ty_f.parts[i][0]) for i in ty_f.data]
    n = len(tokens)
    extra = re.compile(a.extra_drop_regex) if a.extra_drop_regex else None

    keep = []
    for i, (t, ty) in enumerate(zip(tokens, types)):
        s = t.decode("utf-8", "replace")
        if ty in (3, 6):          # control / byte tokens: always keep
            keep.append(i); continue
        if CJK.search(s):
            continue
        if extra and extra.search(s):
            continue
        keep.append(i)
    if a.pad_to and len(keep) % a.pad_to:
        dropped = sorted(set(range(n)) - set(keep))
        need = a.pad_to - len(keep) % a.pad_to
        keep = sorted(keep + dropped[:need])
        print(f"  padded vocab by {need} un-dropped pieces to a multiple of {a.pad_to} (keeps CPU repack/alignment paths for output.weight)")
    keep = np.array(keep, dtype=np.int64)
    new_id = {int(o): k for k, o in enumerate(keep)}
    print(f"vocab {n} -> {len(keep)} (dropped {n-len(keep)}, {100*(n-len(keep))/n:.1f}%)")

    # remap special ids
    id_keys = {}
    for k, fld in f.items():
        if k.startswith("tokenizer.ggml.") and k.endswith("_token_id"):
            old = int(fld.parts[fld.data[0]][0])
            if old not in new_id:
                sys.exit(f"special token {k}={old} ({tokens[old]!r}) would be dropped — refusing")
            id_keys[k] = new_id[old]
            print(f"  {k}: {old} -> {new_id[old]}  {tokens[old]!r}")

    arch = bytes(f["general.architecture"].parts[f["general.architecture"].data[0]]).decode()
    if a.dry_run:
        for tname in ("token_embd.weight", "output.weight"):
            t = next(x for x in r.tensors if x.name == tname)
            rb = t.data.shape[1]
            print(f"  {tname}: {t.tensor_type.name} rows {t.data.shape[0]} x {rb} B -> {len(keep)} rows: {t.data.shape[0]*rb/1e6:.1f} MB -> {len(keep)*rb/1e6:.1f} MB")
        return

    w = GGUFWriter(str(a.out), arch)
    for fld in r.fields.values():
        name = fld.name
        if name == gguf.Keys.General.ARCHITECTURE or name.startswith("GGUF."):
            continue
        vt = fld.types[0]
        st = fld.types[-1] if vt == GGUFValueType.ARRAY else None
        if name == "tokenizer.ggml.tokens":
            w.add_token_list([tokens[i] for i in keep]); continue
        if name == "tokenizer.ggml.scores":
            w.add_token_scores([scores[i] for i in keep]); continue
        if name == "tokenizer.ggml.token_type":
            w.add_token_types([types[i] for i in keep]); continue
        if name in id_keys:
            w.add_key_value(name, id_keys[name], vt); continue
        if name.endswith(".vocab_size"):
            w.add_key_value(name, len(keep), vt); print(f"  {name}: {fld.contents()} -> {len(keep)}"); continue
        w.add_key_value(name, fld.contents(), vt, sub_type=st)
    w.add_string("muta.vocab_prune", f"dropped {n-len(keep)} CJK-script pieces of {n} (English-scoped); kept ids remapped; embd/output rows sliced byte-exact")

    total = 0
    sliced = {}
    for t in r.tensors:
        if t.name in ("token_embd.weight", "output.weight"):
            assert t.data.shape[0] == n, (t.name, t.data.shape)
            data = np.ascontiguousarray(t.data[keep])
            sliced[t.name] = data
            w.add_tensor_info(t.name, data.shape, data.dtype, data.nbytes, t.tensor_type)
            total += data.nbytes
        else:
            w.add_tensor_info(t.name, t.data.shape, t.data.dtype, t.data.nbytes, t.tensor_type)
            total += t.data.nbytes
    w.write_header_to_file(); w.write_kv_data_to_file(); w.write_ti_data_to_file()
    t0 = time.time(); done = 0
    for t in r.tensors:
        data = sliced.get(t.name, t.data)
        w.write_tensor_data(data, tensor_endianess=r.endianess)
        done += data.nbytes
    w.close()
    print(f"wrote {a.out} ({total/1e6:.1f} MB) in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
