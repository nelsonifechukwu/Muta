#!/usr/bin/env python3
"""Extract one sub-model from a GGUF bundle back into a standalone GGUF.

The inverse of pack_bundle.py for a single prefix: every KV `{prefix}k` -> `k`,
every tensor `{prefix}t` -> `t`, payload bytes copied raw in their original
quant type. The bundle's own manifest (`bundle.{i}.sha256`) records the source
file's hash, so a faithful extraction is verifiable: pass --verify to compare.

Mirrors pack_bundle.py's identity mode (version-matched reader->writer
pass-through; run with PYTHONPATH=<llama.cpp>/gguf-py to match the packer).

Usage:
  extract_bundle.py --bundle bundle/muta-trio.gguf --prefix m1. \
      --out models/Qwen3.5-0.8B-MTP-Q4_K_M.gguf --verify
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import gguf


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bundle", type=Path, required=True)
    ap.add_argument("--prefix", required=True, help="sub-model prefix, e.g. 'm1.'")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--verify", action="store_true",
                    help="compare the output sha256 against the bundle manifest's recorded source hash")
    args = ap.parse_args()

    reader = gguf.GGUFReader(args.bundle, "r")

    # locate the manifest entry for this prefix
    count_f = reader.get_field("bundle.count")
    if count_f is None:
        print("error: not a bundle (no bundle.count)", file=sys.stderr)
        return 1
    manifest_sha = None
    for i in range(count_f.contents()):
        if reader.get_field(f"bundle.{i}.prefix").contents() == args.prefix:
            manifest_sha = reader.get_field(f"bundle.{i}.sha256").contents()
            break
    if manifest_sha is None:
        print(f"error: prefix {args.prefix!r} not in bundle manifest", file=sys.stderr)
        return 1

    arch_key = args.prefix + gguf.Keys.General.ARCHITECTURE
    arch_f = reader.get_field(arch_key)
    if arch_f is None:
        print(f"error: {arch_key} missing", file=sys.stderr)
        return 1
    arch = arch_f.contents()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    writer = gguf.GGUFWriter(args.out, arch=arch, endianess=reader.endianess)

    align_f = reader.get_field(args.prefix + gguf.Keys.General.ALIGNMENT)
    if align_f is not None:
        writer.data_alignment = align_f.contents()

    n_kv = 0
    for field in reader.fields.values():
        if field.name.startswith("GGUF.") or not field.name.startswith(args.prefix):
            continue
        name = field.name[len(args.prefix):]
        if name == gguf.Keys.General.ARCHITECTURE:
            continue  # the writer already emitted it
        val_type = field.types[0]
        sub_type = field.types[-1] if val_type == gguf.GGUFValueType.ARRAY else None
        writer.add_key_value(name, field.contents(), val_type, sub_type=sub_type)
        n_kv += 1

    tensors = [t for t in reader.tensors if t.name.startswith(args.prefix)]
    for t in tensors:
        writer.add_tensor_info(t.name[len(args.prefix):], t.data.shape, t.data.dtype,
                               t.data.nbytes, t.tensor_type)

    writer.open_output_file()
    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_ti_data_to_file()
    for t in tensors:
        writer.write_tensor_data(t.data, tensor_endianess=reader.endianess)
    writer.close()

    print(f"* wrote {args.out} ({args.out.stat().st_size:,} B): arch={arch}, {n_kv+1} KVs, {len(tensors)} tensors")

    if args.verify:
        got = sha256_file(args.out)
        if got == manifest_sha:
            print(f"* sha256 VERIFIED against bundle manifest: {got}")
        else:
            print(f"* sha256 MISMATCH: extracted {got}\n"
                  f"                   manifest  {manifest_sha}\n"
                  "  (byte layout differs from the original packer's input; compare per-tensor hashes"
                  " with verify_bundle.py before trusting the file)", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
