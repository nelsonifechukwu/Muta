#!/usr/bin/env bash
# Reproduce the Qwen3-1.7B quant/mixed-precision/pruning campaign from pinned BF16.
set -euo pipefail

if [ "$#" -ne 4 ]; then
  echo "usage: $0 SOURCE_BF16 IMATRIX LLAMA_QUANTIZE OUT_DIR" >&2
  exit 2
fi

SOURCE=$1
IMATRIX=$2
QUANTIZER=$3
OUT_DIR=$4
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DROP="$ROOT/muta-iq/opt/scripts/drop_tensor.py"
LLAMA_DIR=$(cd "$(dirname "$QUANTIZER")/../.." && pwd)
THREADS=${MUTA_QUANT_THREADS:-2}
GGUF_PYTHON=${MUTA_GGUF_PYTHON:-python3}
EXPECTED_SOURCE_SHA=199b4df12194e24ac097d4fcbd279ce62bd4959bed9f0d4719d05a6ab1501861
EXPECTED_IMATRIX_SHA=${MUTA_EXPECT_IMATRIX_SHA:-34b14260809a8d7b307637a37b2a4d576feaff626be5fba23a6d1df1b243a6f2}
EXPECTED_QUANTIZER_COMMIT=48d22e295e2b86b47366c16390794f3e05ba970a
EXPECTED_QUANTIZER_SHA=${MUTA_EXPECT_QUANTIZER_SHA:-dea1cace012c3e6ed7589fa2cab130497859156c7233c4958363c7d72d5a31d7}

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | cut -d ' ' -f 1
  else
    shasum -a 256 "$1" | cut -d ' ' -f 1
  fi
}

[ -f "$SOURCE" ] || { echo "missing BF16 source: $SOURCE" >&2; exit 1; }
[ -f "$IMATRIX" ] || { echo "missing importance matrix: $IMATRIX" >&2; exit 1; }
[ -x "$QUANTIZER" ] || { echo "missing llama-quantize: $QUANTIZER" >&2; exit 1; }
[ -f "$DROP" ] || { echo "missing tensor-drop tool: $DROP" >&2; exit 1; }
command -v "$GGUF_PYTHON" >/dev/null 2>&1 \
  || { echo "missing GGUF Python interpreter: $GGUF_PYTHON" >&2; exit 1; }
[ "$(sha256_file "$SOURCE")" = "$EXPECTED_SOURCE_SHA" ] \
  || { echo "BF16 source hash mismatch" >&2; exit 1; }
[ "$(sha256_file "$IMATRIX")" = "$EXPECTED_IMATRIX_SHA" ] \
  || { echo "importance matrix hash mismatch" >&2; exit 1; }
[ "$(git -C "$LLAMA_DIR" rev-parse HEAD)" = "$EXPECTED_QUANTIZER_COMMIT" ] \
  || { echo "llama.cpp checkout is not pinned b10360/$EXPECTED_QUANTIZER_COMMIT" >&2; exit 1; }
[ "$(sha256_file "$QUANTIZER")" = "$EXPECTED_QUANTIZER_SHA" ] \
  || { echo "llama-quantize binary hash mismatch" >&2; exit 1; }
mkdir -p "$OUT_DIR"

build_tied() {
  local name=$1
  local ftype=$2
  local head_type=$3
  shift 3
  local untied="$OUT_DIR/.${name}.untied.partial.gguf"
  local tied="$OUT_DIR/${name}-tied.gguf"
  if [ -f "$tied" ]; then
    if [ "${MUTA_REUSE_EXISTING:-0}" = "1" ]; then
      printf 'reusing %s  %s\n' "$(sha256_file "$tied")" "$tied"
      return
    fi
    echo "refusing to overwrite existing candidate: $tied" >&2
    exit 1
  fi
  if [ -e "$untied" ]; then
    [ "${MUTA_RESUME_PARTIAL:-0}" = "1" ] \
      || { echo "stale partial exists: $untied" >&2; exit 1; }
    echo "resuming completed quantization partial: $untied"
  else
    "$QUANTIZER" --pure --imatrix "$IMATRIX" \
      --output-tensor-type "$head_type" --token-embedding-type "$head_type" \
      "$@" "$SOURCE" "$untied" "$ftype" "$THREADS"
  fi
  "$GGUF_PYTHON" "$DROP" "$untied" "$tied.partial" output.weight
  mv "$tied.partial" "$tied"
  rm "$untied"
  printf '%s  %s\n' "$(sha256_file "$tied")" "$tied"
}

# Uniform quant ladder: direct from BF16, common imatrix, tied head.
build_tied Q3_K_M Q3_K_M Q3_K
build_tied IQ4_XS IQ4_XS IQ4_XS
build_tied Q4_K_S Q4_K_S Q4_K
build_tied Q4_K_M Q4_K_M Q4_K
build_tied Q5_0 Q5_0 Q5_0
build_tied Q5_K_M Q5_K_M Q5_K
build_tied Q6_K Q6_K Q6_K

# Mixed precision protects the shared token embedding / language-model head.
build_tied Q3_K_M-EQ6_K Q3_K_M Q6_K
build_tied IQ4_XS-EQ6_K IQ4_XS Q6_K

# Minimal structured-pruning probe: one middle transformer block only.
build_tied Q4_0-prune-L14 Q4_0 Q4_0 --prune-layers 14
