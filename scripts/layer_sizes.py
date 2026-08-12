#!/usr/bin/env python3
"""Per-layer byte tables for GGUF model files (task A2 / S0.2).

Ground truth for the streaming residency manager's ledger: per-layer size,
tied-head detection, per-layer contiguity, layer-order monotonicity, and
token_embd's position in the file. Handles plain single-model GGUFs and the
prefixed multi-model bundle (`m0.`, `m1.` tensor-name prefixes).

Run with the repo venv so the local llama.cpp/gguf-py tree (not whatever
`gguf` package may be pip-installed) is used:

    .venv/bin/python scripts/layer_sizes.py [file ...]

With no arguments, analyzes the three pinned models plus the bundle.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The tree's own gguf-py must win over any pip-installed `gguf` package.
# Empirically (2026-08-12, this worktree): a stale `gguf==0.19.0` is
# pip-installed into .venv and a bare `import gguf` succeeds against IT, not
# against llama.cpp/gguf-py -- so "fall back to sys.path.insert only on
# ImportError" (the naive reading) would silently use the wrong, older gguf
# reader. Prepend the tree's copy unconditionally so it always wins.
sys.path.insert(0, str(REPO_ROOT / "llama.cpp" / "gguf-py"))
from gguf.gguf_reader import GGUFReader, ReaderTensor  # noqa: E402

MIB = 1024 * 1024

DEFAULT_FILES = [
    "models/SmolLM2-135M-Instruct-Q4_K_M.gguf",
    "models/Qwen3.5-0.8B-MTP-Q4_K_M.gguf",
    "models/Qwen3.5-4B-Q4_K_M.gguf",
    "bundle/muta-duo-q.gguf",
]

PREFIX_RE = re.compile(r"^(m\d+\.)")
LAYER_RE = re.compile(r"^blk\.(\d+)\.")

# Contiguity flag threshold from the brief: extent > 1.05x the byte-sum.
CONTIGUITY_SLOP = 1.05


def mib(n_bytes: int) -> float:
    return n_bytes / MIB


def group_by_prefix(tensors: list[ReaderTensor]) -> dict[str, list[ReaderTensor]]:
    """Group tensors by their `mN.` bundle prefix; "" for unprefixed files."""
    groups: dict[str, list[ReaderTensor]] = {}
    for t in tensors:
        m = PREFIX_RE.match(t.name)
        prefix = m.group(1) if m else ""
        groups.setdefault(prefix, []).append(t)
    return groups


class LayerInfo:
    __slots__ = ("idx", "tensors", "n_bytes", "min_off", "max_end")

    def __init__(self, idx: int):
        self.idx = idx
        self.tensors: list[tuple[str, ReaderTensor]] = []
        self.n_bytes = 0
        self.min_off = None
        self.max_end = None

    def add(self, name: str, t: ReaderTensor) -> None:
        self.tensors.append((name, t))
        self.n_bytes += t.n_bytes
        off = t.data_offset
        end = t.data_offset + t.n_bytes
        self.min_off = off if self.min_off is None else min(self.min_off, off)
        self.max_end = end if self.max_end is None else max(self.max_end, end)

    @property
    def extent(self) -> int:
        return self.max_end - self.min_off

    @property
    def flagged(self) -> bool:
        return self.extent > CONTIGUITY_SLOP * self.n_bytes


class ModelGeometry:
    """Parsed geometry for one model (a whole file, or one bundle prefix)."""

    def __init__(self, label: str, prefix: str, tensors: list[ReaderTensor]):
        self.label = label
        self.prefix = prefix
        self.layers: dict[int, LayerInfo] = {}
        self.token_embd: ReaderTensor | None = None
        self.output_weight: ReaderTensor | None = None
        self.output_norm: ReaderTensor | None = None
        self.misc: list[tuple[str, ReaderTensor]] = []
        self.all_tensors = tensors

        for t in tensors:
            name = t.name[len(prefix):] if prefix else t.name
            m = LAYER_RE.match(name)
            if m:
                idx = int(m.group(1))
                self.layers.setdefault(idx, LayerInfo(idx)).add(name, t)
            elif name == "token_embd.weight":
                self.token_embd = t
            elif name == "output.weight":
                self.output_weight = t
            elif name == "output_norm.weight":
                self.output_norm = t
            else:
                self.misc.append((name, t))

    @property
    def n_layers(self) -> int:
        return len(self.layers)

    @property
    def layer_idxs_sorted(self) -> list[int]:
        return sorted(self.layers)

    @property
    def blk_total_bytes(self) -> int:
        return sum(li.n_bytes for li in self.layers.values())

    @property
    def layer_bytes_list(self) -> list[int]:
        return [self.layers[i].n_bytes for i in self.layer_idxs_sorted]

    @property
    def payload_interval(self) -> tuple[int, int]:
        offs = [t.data_offset for t in self.all_tensors]
        ends = [t.data_offset + t.n_bytes for t in self.all_tensors]
        return min(offs), max(ends)

    def tied_head(self) -> bool:
        return self.output_weight is None

    def gaps(self) -> list[int]:
        idxs = self.layer_idxs_sorted
        if not idxs:
            return []
        full = set(range(idxs[0], idxs[-1] + 1))
        return sorted(full - set(idxs))

    def monotonicity(self) -> tuple[bool, list[str]]:
        idxs = self.layer_idxs_sorted
        exceptions = []
        prev_idx = None
        prev_off = None
        for idx in idxs:
            off = self.layers[idx].min_off
            if prev_off is not None and not (off > prev_off):
                exceptions.append(
                    f"layer {prev_idx} (off={prev_off}) -> layer {idx} (off={off}): "
                    f"not strictly increasing"
                )
            prev_idx, prev_off = idx, off
        return (len(exceptions) == 0), exceptions


def render_summary_row(geom: ModelGeometry, file_label: str, total_bytes: int) -> str:
    layer_bytes = geom.layer_bytes_list
    b_min = mib(min(layer_bytes)) if layer_bytes else 0.0
    b_avg = mib(sum(layer_bytes) / len(layer_bytes)) if layer_bytes else 0.0
    b_max = mib(max(layer_bytes)) if layer_bytes else 0.0
    embd_mib = mib(geom.token_embd.n_bytes) if geom.token_embd else 0.0
    embd_quant = geom.token_embd.tensor_type.name if geom.token_embd else "-"
    has_output = "yes" if geom.output_weight is not None else "no"
    tied = "TIED" if geom.tied_head() else "not tied"
    norm_bytes = geom.output_norm.n_bytes if geom.output_norm else 0
    return (
        f"| {file_label} | {total_bytes:,} | {geom.n_layers} | {mib(geom.blk_total_bytes):.1f} "
        f"| {b_min:.1f} | {b_avg:.1f} | {b_max:.1f} | {embd_mib:.1f} ({embd_quant}) "
        f"| {has_output} ({tied}) | {norm_bytes:,} |"
    )


def analyze_file(path: str) -> None:
    p = Path(path)
    if not p.is_absolute():
        p = (REPO_ROOT / p).resolve()
    if not p.exists():
        print(f"\n## {path} -- MISSING, skipped\n")
        return

    file_size = p.stat().st_size
    reader = GGUFReader(str(p))
    all_offs = [t.data_offset for t in reader.tensors]
    all_ends = [t.data_offset + t.n_bytes for t in reader.tensors]
    min_off, max_end = min(all_offs), max(all_ends)

    print(f"\n## {path}\n")
    print(f"- file size: {file_size:,} bytes")
    print(f"- header data section starts at reader.data_offset = {reader.data_offset:,}")
    print(
        f"- tensor offset bounds: min={min_off:,}, max(off+len)={max_end:,} "
        f"(min >= header: {min_off >= reader.data_offset}; "
        f"max <= file size: {max_end <= file_size}; "
        f"trailing slack: {file_size - max_end} bytes)"
    )

    groups = group_by_prefix(reader.tensors)
    multi = len(groups) > 1 or "" not in groups

    print("\n### (a) Summary\n")
    header = (
        "| model | total bytes | n_layers | blk total MiB | b_layer min MiB "
        "| b_layer avg MiB | b_layer max MiB | token_embd MiB (quant) "
        "| output.weight? (head) | output_norm bytes |"
    )
    sep = "|---|---|---|---|---|---|---|---|---|---|"
    print(header)
    print(sep)

    geoms: dict[str, ModelGeometry] = {}
    for prefix in sorted(groups):
        tensors = groups[prefix]
        geom = ModelGeometry(label=path, prefix=prefix, tensors=tensors)
        geoms[prefix] = geom
        file_label = f"{path} [{prefix.rstrip('.')}]" if prefix else path
        payload_bytes = sum(t.n_bytes for t in tensors)
        total_bytes = payload_bytes if multi else file_size
        print(render_summary_row(geom, file_label, total_bytes))

    if multi:
        print("\nPer-prefix payload interval [min data offset, max offset+len]:\n")
        for prefix in sorted(groups):
            geom = geoms[prefix]
            lo, hi = geom.payload_interval
            label = prefix.rstrip(".") if prefix else "(none)"
            print(f"- {label}: [{lo:,}, {hi:,}) -- {mib(hi - lo):.1f} MiB span")

    for prefix in sorted(groups):
        geom = geoms[prefix]
        label = f"{path} [{prefix.rstrip('.')}]" if prefix else path

        print(f"\n### (b) Per-layer table -- {label}\n")
        print("| layer | bytes | MiB | extent | sum(len) | extent/sum | contiguous? |")
        print("|---|---|---|---|---|---|---|")
        for idx in geom.layer_idxs_sorted:
            li = geom.layers[idx]
            ratio = li.extent / li.n_bytes if li.n_bytes else float("nan")
            flag = "FLAG" if li.flagged else "ok"
            print(
                f"| {idx} | {li.n_bytes:,} | {mib(li.n_bytes):.1f} | {li.extent:,} "
                f"| {li.n_bytes:,} | {ratio:.3f} | {flag} |"
            )
        gaps = geom.gaps()
        if gaps:
            print(f"\nLayer-index gaps detected: {gaps}")

        print(f"\n### (c) Layer-order monotonicity -- {label}\n")
        ok, exceptions = geom.monotonicity()
        print(f"Verdict: {'PASS' if ok else 'FAIL'}")
        for exc in exceptions:
            print(f"- exception: {exc}")

        print(f"\n### (d) token_embd position -- {label}\n")
        if geom.token_embd is None:
            print("token_embd.weight not found in this group.")
        else:
            embd_off = geom.token_embd.data_offset
            group_min_off = min(t.data_offset for t in geom.all_tensors)
            is_first = embd_off == group_min_off
            print(
                f"token_embd.weight offset = {embd_off:,}; "
                f"group's minimum tensor offset = {group_min_off:,}; "
                f"first tensor in file order? {'YES' if is_first else 'NO'}"
            )


def main(argv: list[str]) -> int:
    files = argv[1:] if len(argv) > 1 else DEFAULT_FILES
    for f in files:
        analyze_file(f)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
