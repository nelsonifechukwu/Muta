#!/usr/bin/env python3
"""Copy a GGUF without the given decoder layers: tensors byte-identical, blocks renumbered,
`<arch>.block_count` rewritten. Mirrors muta-iq/opt/scripts/drop_tensor.py's copy pattern.

Usage: prune_gguf_layers.py IN.gguf OUT.gguf --drop 8,9,10,11,12,13,14
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import layer_selection

_BLK = re.compile(r"^blk\.(\d+)\.(.+)$")


def plan_tensor_names(names: list[str], n_layers: int, drop: list[int]) -> list[tuple[str, str]]:
    """(old_name, new_name) for every kept tensor, in the original order."""
    mapping = layer_selection.renumber_plan(n_layers, drop)
    plan: list[tuple[str, str]] = []
    for name in names:
        match = _BLK.match(name)
        if match is None:
            plan.append((name, name))
            continue
        old = int(match.group(1))
        if old in mapping:
            plan.append((name, f"blk.{mapping[old]}.{match.group(2)}"))
    return plan


def params_from_shapes(shapes: list[tuple[int, ...]]) -> int:
    return int(sum(int(np.prod(shape)) for shape in shapes))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prune(src: Path, dst: Path, drop: list[int]) -> dict:
    import gguf
    from gguf import GGUFReader, GGUFValueType, GGUFWriter

    reader = GGUFReader(str(src))
    fields = reader.fields
    arch_field = fields["general.architecture"]
    arch = bytes(arch_field.parts[arch_field.data[0]]).decode()
    count_field = fields[f"{arch}.block_count"]
    n_layers = int(count_field.parts[count_field.data[0]][0])
    kept = layer_selection.kept_layer_indices(n_layers, drop)

    writer = GGUFWriter(str(dst), arch)
    for field in fields.values():
        if field.name == gguf.Keys.General.ARCHITECTURE or field.name.startswith("GGUF."):
            continue
        if field.name == f"{arch}.block_count":
            writer.add_uint32(field.name, len(kept))
            continue
        value_type = field.types[0]
        sub_type = field.types[-1] if value_type == GGUFValueType.ARRAY else None
        writer.add_key_value(field.name, field.contents(), value_type, sub_type=sub_type)

    by_name = {t.name: t for t in reader.tensors}
    plan = plan_tensor_names([t.name for t in reader.tensors], n_layers, drop)
    for old, new in plan:
        t = by_name[old]
        writer.add_tensor_info(new, t.data.shape, t.data.dtype, t.data.nbytes, t.tensor_type)
    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_ti_data_to_file()
    for old, _new in plan:
        t = by_name[old]
        writer.write_tensor_data(t.data, tensor_endianess=reader.endianess)
    writer.close()

    manifest = {
        "schema_version": 1,
        "source": {"path": str(src), "sha256": _sha256(src), "block_count": n_layers},
        "drop": sorted(drop),
        "kept_layers": kept,
        "block_count": len(kept),
        "tensors": len(plan),
        "params_count": params_from_shapes(
            [tuple(int(d) for d in by_name[o].shape) for o, _ in plan]
        ),
        "bytes": dst.stat().st_size,
        "sha256": _sha256(dst),
    }
    dst.with_suffix(".prune-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("src", type=Path)
    parser.add_argument("dst", type=Path)
    parser.add_argument("--drop", required=True, help="comma-separated layer indices")
    args = parser.parse_args()
    drop = sorted({int(x) for x in args.drop.split(",")})
    print(json.dumps(prune(args.src, args.dst, drop), indent=2))


if __name__ == "__main__":
    main()
