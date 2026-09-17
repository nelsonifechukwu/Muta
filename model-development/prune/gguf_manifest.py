#!/usr/bin/env python3
"""Write the export manifest for a GGUF: parameter count, depth, sha256, tensor types.

Usage: gguf_manifest.py --gguf OUT-Q4_K_M.gguf --llama-dir ~/llama.cpp-b10175 \
           --source-dir merged_16bit --out OUT.export-manifest.json
Uses the gguf-py of the given llama.cpp checkout so the reader matches the writer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 24), b""):
            digest.update(chunk)
    return digest.hexdigest()


def describe(path: Path) -> dict:
    """Tensor-table parameter count, block_count and the set of tensor types."""
    import numpy as np
    from gguf import GGUFReader

    reader = GGUFReader(str(path))
    params = int(sum(int(np.prod(t.shape)) for t in reader.tensors))
    key = next(k for k in reader.fields if k.endswith(".block_count"))
    field = reader.fields[key]
    if hasattr(field, "contents"):
        block_count = int(field.contents())
    else:  # older gguf-py
        block_count = int(field.parts[-1][0])
    return {
        "params_count": params,
        "block_count": block_count,
        "tensor_types": sorted({t.tensor_type.name for t in reader.tensors}),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gguf", type=Path, required=True)
    parser.add_argument("--llama-dir", type=Path, required=True)
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--quantization", default="Q4_K_M")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.llama_dir / "gguf-py"))
    git = ["git", "-C", str(args.llama_dir)]
    commit = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
    tag = subprocess.run(
        [*git, "describe", "--tags", "--exact-match"], text=True, capture_output=True, check=False
    ).stdout.strip()
    manifest = {
        "schema_version": 1,
        "source_dir": args.source_dir,
        "artifact": str(args.gguf),
        **describe(args.gguf),
        "bytes": args.gguf.stat().st_size,
        "sha256": sha256_file(args.gguf),
        "llama_cpp_commit": commit,
        "llama_cpp_tag": tag or None,
        "quantization": args.quantization,
    }
    args.out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
