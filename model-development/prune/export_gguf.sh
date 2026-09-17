#!/usr/bin/env bash
# Export a merged BF16 HF checkpoint to Q4_K_M with pinned llama.cpp b10175 (audit parity).
# Usage: LLAMA_DIR=/path/to/llama.cpp-b10175 ./export_gguf.sh MERGED_DIR OUT_PREFIX [PYTHON]
set -euo pipefail
MERGED=$1; OUT=$2; PY=${3:-python3}
LLAMA_DIR=${LLAMA_DIR:?set LLAMA_DIR to a b10175 checkout with build/bin/llama-quantize}
TAG=$(git -C "$LLAMA_DIR" describe --tags --exact-match 2>/dev/null || git -C "$LLAMA_DIR" rev-parse --short HEAD)
[ "$TAG" = "b10175" ] || { echo "llama.cpp checkout is $TAG, not b10175" >&2; exit 1; }
[ -x "$LLAMA_DIR/build/bin/llama-quantize" ] || { echo "build llama-quantize first: cmake -B build -DGGML_NATIVE=OFF && cmake --build build --target llama-quantize -j" >&2; exit 1; }
"$PY" "$LLAMA_DIR/convert_hf_to_gguf.py" "$MERGED" --outtype f16 --outfile "$OUT-f16.gguf"
"$LLAMA_DIR/build/bin/llama-quantize" "$OUT-f16.gguf" "$OUT-Q4_K_M.gguf" Q4_K_M 8
rm -f "$OUT-f16.gguf"
"$PY" - "$OUT-Q4_K_M.gguf" "$LLAMA_DIR" "$MERGED" > "$OUT.export-manifest.json" <<'PY'
import hashlib, json, os, subprocess, sys
sys.path.insert(0, sys.argv[2] + "/gguf-py")
import numpy as np
from gguf import GGUFReader
path, llama_dir, merged = sys.argv[1:4]
reader = GGUFReader(path)
params = int(sum(int(np.prod(t.shape)) for t in reader.tensors))
digest = hashlib.sha256()
with open(path, "rb") as fh:
    for chunk in iter(lambda: fh.read(1 << 24), b""):
        digest.update(chunk)
commit = subprocess.check_output(["git", "-C", llama_dir, "rev-parse", "HEAD"], text=True).strip()
json.dump({"schema_version": 1, "source_dir": merged, "artifact": path, "params_count": params,
           "bytes": os.path.getsize(path), "sha256": digest.hexdigest(),
           "llama_cpp_commit": commit, "llama_cpp_tag": "b10175", "quantization": "Q4_K_M",
           "tensor_types": sorted({t.tensor_type.name for t in reader.tensors})},
          sys.stdout, indent=2)
sys.stdout.write("\n")
PY
cat "$OUT.export-manifest.json"
