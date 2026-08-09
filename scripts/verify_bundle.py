#!/usr/bin/env python3
"""Byte-level verification of a DUO bundle against its source GGUFs (gate G2a).

Asserts, for every source model:
  (a) every source KV appears in the bundle under its prefix with equal typed value
  (b) every source tensor appears under its prefix with equal quant type, shape,
      and byte-identical payload (sha256)
  (c) the bundle manifest (bundle.count / prefix / role / arch / source / sha256)
      matches the sources.

Usage: verify_bundle.py BUNDLE SOURCE [SOURCE ...]
Sources are matched to manifest entries by file basename.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import gguf


def sha256_bytes(data) -> str:
    return hashlib.sha256(data.tobytes()).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def contents(field):
    return field.contents()


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2

    bundle_path = Path(sys.argv[1])
    source_paths = [Path(p) for p in sys.argv[2:]]

    print(f"* Opening bundle {bundle_path}")
    bundle = gguf.GGUFReader(bundle_path, "r")
    results: list[tuple[str, str, str]] = []  # (model, check, PASS/FAIL detail)
    failed = False

    def check(model: str, name: str, ok: bool, detail: str = ""):
        nonlocal failed
        results.append((model, name, ("PASS" if ok else "FAIL") + (f" {detail}" if detail else "")))
        failed |= not ok

    arch = bundle.get_field(gguf.Keys.General.ARCHITECTURE).contents()
    check("bundle", "general.architecture == 'bundle'", arch == "bundle", repr(arch))

    count_f = bundle.get_field("bundle.count")
    count = count_f.contents() if count_f else 0
    check("bundle", f"bundle.count == {len(source_paths)}", count == len(source_paths), str(count))

    # map manifest entries by source basename
    manifest: dict[str, dict] = {}
    for i in range(count):
        entry = {k: bundle.get_field(f"bundle.{i}.{k}").contents()
                 for k in ("prefix", "role", "arch", "source", "sha256")}
        manifest[entry["source"]] = entry

    for src_path in source_paths:
        name = src_path.name
        entry = manifest.get(name)
        check(name, "manifest entry exists", entry is not None)
        if entry is None:
            continue
        prefix = entry["prefix"]

        print(f"* Verifying {name} (prefix={prefix!r})")
        src = gguf.GGUFReader(src_path, "r")

        src_arch = src.get_field(gguf.Keys.General.ARCHITECTURE).contents()
        check(name, "manifest arch matches", entry["arch"] == src_arch, f"{entry['arch']} vs {src_arch}")
        check(name, "manifest sha256 matches file", entry["sha256"] == sha256_file(src_path))

        # (a) every KV prefixed and equal
        n_kv_bad = 0
        n_kv = 0
        for field in src.fields.values():
            if field.name.startswith("GGUF."):
                continue
            n_kv += 1
            bf = bundle.get_field(prefix + field.name)
            if bf is None or bf.types != field.types or contents(bf) != contents(field):
                n_kv_bad += 1
                print(f"    KV MISMATCH: {field.name}")
        check(name, f"KVs equal under prefix ({n_kv})", n_kv_bad == 0, f"{n_kv_bad} bad")

        # (b) every tensor prefixed, same type/shape, byte-identical payload
        bundle_tensors = {t.name: t for t in bundle.tensors}
        n_t_bad = 0
        n_t = 0
        for t in src.tensors:
            n_t += 1
            bt = bundle_tensors.get(prefix + t.name)
            if bt is None:
                n_t_bad += 1
                print(f"    TENSOR MISSING: {t.name}")
                continue
            if bt.tensor_type != t.tensor_type or list(bt.shape) != list(t.shape) \
                    or bt.n_bytes != t.n_bytes or sha256_bytes(bt.data) != sha256_bytes(t.data):
                n_t_bad += 1
                print(f"    TENSOR MISMATCH: {t.name}")
        check(name, f"tensors byte-identical under prefix ({n_t})", n_t_bad == 0, f"{n_t_bad} bad")

    print()
    w = max(len(m) for m, _, _ in results)
    for model, check_name, status in results:
        print(f"  {model:<{w}}  {check_name:<44} {status}")
    print()
    print("G2a: " + ("FAIL" if failed else "PASS"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
