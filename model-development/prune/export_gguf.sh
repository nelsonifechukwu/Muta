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
"$PY" "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/gguf_manifest.py" --gguf "$OUT-Q4_K_M.gguf" \
  --llama-dir "$LLAMA_DIR" --source-dir "$MERGED" --out "$OUT.export-manifest.json" > /dev/null
cat "$OUT.export-manifest.json"
