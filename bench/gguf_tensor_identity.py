"""Prove that two GGUF files contain identical tensor payloads.

Metadata-only submission changes should not silently alter weights.  This verifier compares
every tensor's name, quantization type, shape and raw bytes, then writes a compact artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--gguf-py", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    sys.path.insert(0, str(args.gguf_py.resolve()))
    from gguf import GGUFReader  # type: ignore[import-not-found]

    def tensor_rows(path: Path) -> list[dict]:
        rows = []
        for tensor in GGUFReader(str(path)).tensors:
            digest = hashlib.sha256(tensor.data.tobytes(order="C")).hexdigest()
            rows.append(
                {
                    "name": tensor.name,
                    "tensor_type": tensor.tensor_type.name,
                    "shape": [int(value) for value in tensor.shape],
                    "bytes": int(tensor.n_bytes),
                    "sha256": digest,
                }
            )
        return rows

    left = tensor_rows(args.left)
    right = tensor_rows(args.right)
    report = {
        "schema_version": 1,
        "left": str(args.left),
        "right": str(args.right),
        "tensor_count": len(left),
        "tensor_bytes": sum(row["bytes"] for row in left),
        "identical": left == right,
    }
    if left != right:
        left_by_name = {row["name"]: row for row in left}
        right_by_name = {row["name"]: row for row in right}
        report["differences"] = [
            name for name in sorted(left_by_name.keys() | right_by_name.keys())
            if left_by_name.get(name) != right_by_name.get(name)
        ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, sort_keys=True))
    return 0 if report["identical"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
