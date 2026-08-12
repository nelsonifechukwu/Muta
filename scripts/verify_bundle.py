#!/usr/bin/env python3
"""Byte-level verification of a bundle against its source GGUFs (gate G2a),
plus two whole-bundle streaming-design gates (task A4 / S0.4).

Asserts, for every source model:
  (a) every source KV appears in the bundle under its prefix with equal typed value
  (b) every source tensor appears under its prefix with equal quant type, shape,
      and byte-identical payload (sha256)
  (c) the bundle manifest (bundle.count / prefix / role / arch / source / sha256)
      matches the sources.

Additionally, over the whole bundle manifest (independent of which SOURCEs this
invocation was given, so these run the same way for a 2-model or N-model bundle):
  (d) contiguity: each prefix's tensor payloads form a single gap-free-mod-
      alignment interval (no gaps beyond writer padding, no overlaps), AND
      those per-prefix intervals themselves appear in manifest order
      (bundle.0, bundle.1, ...) with physically increasing file offsets --
      catches a scrambled-but-internally-contiguous bundle.
  (e) vocab-identity: tokens/merges/pre/special-ids compared for every prefix
      pair; the front!=mid / easy==mid expectation is additionally asserted
      when those three roles are present (the trio bundle).

Usage: verify_bundle.py BUNDLE SOURCE [SOURCE ...]
Sources are matched to manifest entries by file basename.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The tree's own gguf-py must win over any pip-installed `gguf` package.
# Empirically (2026-08-12, this worktree): a stale `gguf==0.19.0` is
# pip-installed into .venv (its "editable" source dir points at an orphaned
# ../Muta_v2/llama.cpp/gguf-py that no longer exists on disk) and a bare
# `import gguf` succeeds against IT, not against llama.cpp/gguf-py -- so
# "fall back to sys.path.insert only on ImportError" (the naive reading)
# would silently use the wrong, older gguf reader. Prepend the tree's copy
# unconditionally so it always wins (same pattern as scripts/layer_sizes.py).
sys.path.insert(0, str(REPO_ROOT / "llama.cpp" / "gguf-py"))
import gguf  # noqa: E402


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


def align_up(n: int, alignment: int) -> int:
    """Match gguf_writer.py's GGUFWriter.ggml_pad exactly: round n up to the
    next multiple of alignment (the padding the writer inserts between
    consecutive tensor payloads)."""
    return ((n + alignment - 1) // alignment) * alignment


def tokenizer_signature(reader: gguf.GGUFReader, prefix: str) -> dict:
    """tokens/merges/pre + special-ids (bos/eos/pad), read under a bundle
    prefix. Missing keys read as None on both sides of a comparison, which
    is also correct for "differs" when only one side has the key."""
    def val(key: str):
        f = reader.get_field(prefix + key)
        return f.contents() if f else None

    return {
        "tokens": val(gguf.Keys.Tokenizer.LIST),
        "merges": val(gguf.Keys.Tokenizer.MERGES),
        "pre": val(gguf.Keys.Tokenizer.PRE),
        "bos": val(gguf.Keys.Tokenizer.BOS_ID),
        "eos": val(gguf.Keys.Tokenizer.EOS_ID),
        "pad": val(gguf.Keys.Tokenizer.PAD_ID),
    }


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

    # map manifest entries by source basename; also keep index (manifest)
    # order for the whole-bundle gates below, which operate on every prefix
    # in the bundle regardless of which SOURCEs this invocation was given.
    manifest: dict[str, dict] = {}
    manifest_entries: list[dict] = []
    for i in range(count):
        entry = {k: bundle.get_field(f"bundle.{i}.{k}").contents()
                 for k in ("prefix", "role", "arch", "source", "sha256")}
        manifest[entry["source"]] = entry
        manifest_entries.append(entry)

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

    # (d) per-prefix payload-interval contiguity: within each model's
    # prefix group, tensor payloads must form one gap-free-mod-alignment
    # interval -- no gaps beyond writer padding, no overlaps. Checked and
    # printed in manifest order (bundle.0, bundle.1, ...).
    print()
    print(f"* Contiguity check (alignment={bundle.alignment})")
    intervals: list[tuple[str, str, int | None, int | None]] = []  # (source, prefix, lo, hi)
    for entry in manifest_entries:
        prefix = entry["prefix"]
        tensors = sorted((t for t in bundle.tensors if t.name.startswith(prefix)),
                          key=lambda t: t.data_offset)
        if not tensors:
            check(entry["source"], f"payload interval contiguous under prefix {prefix!r}",
                  False, "no tensors found under prefix")
            intervals.append((entry["source"], prefix, None, None))
            continue
        ok = True
        for a, b in zip(tensors, tensors[1:]):
            a_end = a.data_offset + a.n_bytes
            expected = align_up(a_end, bundle.alignment)
            if b.data_offset < a_end or b.data_offset > expected:
                ok = False
                print(f"    GAP/OVERLAP in {prefix}: {a.name} ends {a_end:,} -> "
                      f"{b.name} starts {b.data_offset:,} (expected <= {expected:,})")
        lo = tensors[0].data_offset
        hi = max(t.data_offset + t.n_bytes for t in tensors)
        print(f"  {prefix} [{lo}, {hi - lo}]")
        check(entry["source"], f"payload interval contiguous under prefix {prefix!r}", ok)
        intervals.append((entry["source"], prefix, lo, hi))

    # (d2) manifest order matches physical file-offset order: a bundle
    # where every prefix is internally contiguous but the prefixes
    # themselves are scrambled relative to bundle.{i} order would still
    # pass (d) alone -- so additionally require each successive manifest
    # prefix's interval to start at or after the previous prefix's
    # interval end, with a gap no larger than one alignment-padding step.
    valid_intervals = [iv for iv in intervals if iv[2] is not None]
    order_ok = True
    for (prev_src, prev_prefix, _, prev_hi), (cur_src, cur_prefix, cur_lo, _) in \
            zip(valid_intervals, valid_intervals[1:]):
        expected = align_up(prev_hi, bundle.alignment)
        if not (prev_hi <= cur_lo <= expected):
            order_ok = False
            print(f"    MANIFEST-ORDER BREAK: {prev_prefix} ends {prev_hi:,} -> "
                  f"{cur_prefix} starts {cur_lo:,} (expected in [{prev_hi:,}, {expected:,}])")
    print(f"  manifest-order contiguity: {'PASS' if order_ok else 'FAIL'}")
    check("bundle", "manifest prefix order matches physical file-offset order", order_ok)

    # (e) vocab-identity gate: tokens/merges/pre/special-ids compared for
    # every prefix pair in the bundle (generic, works for any N). The
    # trio-specific front!=mid / easy==mid expectation is additionally
    # asserted when those three roles are present in this bundle.
    print()
    print("* Vocab-identity gate")
    sigs = {e["prefix"]: tokenizer_signature(bundle, e["prefix"]) for e in manifest_entries}
    role_of = {e["prefix"]: e["role"] for e in manifest_entries}
    prefixes = [e["prefix"] for e in manifest_entries]

    pair_equal: dict[tuple[str, str], bool] = {}
    for i, p1 in enumerate(prefixes):
        for p2 in prefixes[i + 1:]:
            eq = sigs[p1] == sigs[p2]
            pair_equal[(p1, p2)] = eq
            pair_equal[(p2, p1)] = eq
            print(f"  {p1} ({role_of[p1]}) vs {p2} ({role_of[p2]}): "
                  f"{'EQUAL' if eq else 'DIFFERS'}")

    prefix_of_role = {role: prefix for prefix, role in role_of.items()}
    if {"front", "easy", "mid"} <= prefix_of_role.keys():
        front, easy, mid = prefix_of_role["front"], prefix_of_role["easy"], prefix_of_role["mid"]
        easy_mid_ok = pair_equal[(easy, mid)]
        front_mid_ok = not pair_equal[(front, mid)]
        print(f"vocab_gate: easy==mid {'OK' if easy_mid_ok else 'FAIL'}, "
              f"front!=mid {'OK' if front_mid_ok else 'FAIL'}")
        check("bundle", "vocab_gate: easy==mid", easy_mid_ok)
        check("bundle", "vocab_gate: front!=mid", front_mid_ok)

    print()
    w = max(len(m) for m, _, _ in results)
    for model, check_name, status in results:
        print(f"  {model:<{w}}  {check_name:<44} {status}")
    print()
    print("G2a: " + ("FAIL" if failed else "PASS"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())


