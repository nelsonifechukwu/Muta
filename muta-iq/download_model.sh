#!/usr/bin/env bash
# Reproduce Muta Tutor — Qwen3-1.7B pure Q4_0 with tied head and baked tutor metadata.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_DIR="$HERE/model"
CANDIDATES="$HERE/opt/candidates"
FINAL="$MODEL_DIR/muta-tutor-qwen3-1.7b-q4_0.gguf"
FINAL_SHA="a98ce36e9ff97e5271d90cbc429c952f99a5a966bb0195ae74661b4c054fd63e"
SOURCE="$CANDIDATES/Qwen_Qwen3-1.7B-Q4_0.gguf"
SOURCE_SHA="c470091d31c4ada174ee5c2547daa020e930593cbca5ca8ca385ce8ff59a2fdf"
SOURCE_REV="dcb19155b962dbb6389f4691a982043a8e651022"
SOURCE_URL="https://huggingface.co/bartowski/Qwen_Qwen3-1.7B-GGUF/resolve/$SOURCE_REV/Qwen_Qwen3-1.7B-Q4_0.gguf"
PURE="$CANDIDATES/Qwen3-1.7B-Q4_0-pure.gguf"
TIED="$CANDIDATES/Qwen3-1.7B-Q4_0-pure-tied.gguf"
LLAMA_DIR="$HERE/opt/llama.cpp"
PYTHON="${PY:-$HERE/../.venv/bin/python}"

sha() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  else shasum -a 256 "$1" | cut -d' ' -f1
  fi
}

fetch() {
  if command -v curl >/dev/null 2>&1; then
    curl -fL --retry 5 --retry-delay 5 -C - --progress-bar -o "$2.partial" "$1"
  elif command -v wget >/dev/null 2>&1; then
    wget -c --show-progress -O "$2.partial" "$1"
  else
    echo "neither curl nor wget is available" >&2
    exit 1
  fi
  mv "$2.partial" "$2"
}

mkdir -p "$MODEL_DIR" "$CANDIDATES"
if [ -f "$FINAL" ] && [ "$(sha "$FINAL")" = "$FINAL_SHA" ]; then
  echo "Muta Tutor already present and verified: $FINAL"
  exit 0
fi

# An operator may provide a trusted mirror of the already-derived final artifact. The normal
# path below no longer depends on the unavailable historical Hugging Face repo.
if [ -n "${MODEL_URL:-}" ]; then
  fetch "$MODEL_URL" "$FINAL"
  [ "$(sha "$FINAL")" = "$FINAL_SHA" ] \
    || { echo "mirrored final GGUF hash mismatch" >&2; exit 1; }
  echo "done: $FINAL (sha256 verified)"
  exit 0
fi

if [ -f "$SOURCE" ]; then
  [ "$(sha "$SOURCE")" = "$SOURCE_SHA" ] \
    || { echo "source GGUF hash mismatch: $SOURCE" >&2; exit 1; }
else
  echo "downloading pinned bartowski Qwen3-1.7B Q4_0 source…"
  fetch "$SOURCE_URL" "$SOURCE"
  [ "$(sha "$SOURCE")" = "$SOURCE_SHA" ] \
    || { echo "downloaded source GGUF hash mismatch" >&2; exit 1; }
fi

if [ ! -x "$PYTHON" ]; then
  PYTHON="$(command -v "$PYTHON" 2>/dev/null || true)"
fi
[ -n "$PYTHON" ] && [ -x "$PYTHON" ] \
  || { echo "Python environment missing — create .venv with 'make install'" >&2; exit 1; }
bash "$HERE/opt/scripts/ensure_llama_cpp.sh" "$LLAMA_DIR" >/dev/null

QUANTIZE="$LLAMA_DIR/build-cpu/bin/llama-quantize"
if [ ! -x "$QUANTIZE" ]; then
  command -v cmake >/dev/null 2>&1 || { echo "cmake is required to build llama-quantize" >&2; exit 1; }
  echo "building pinned CPU-only llama-quantize…"
  cmake -S "$LLAMA_DIR" -B "$LLAMA_DIR/build-cpu" \
    -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF \
    -DGGML_NATIVE=OFF -DGGML_AVX2=ON -DGGML_AVX512=OFF \
    -DGGML_OPENMP=OFF -DLLAMA_CURL=OFF
  cmake --build "$LLAMA_DIR/build-cpu" --target llama-quantize \
    -j "$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)"
fi

echo "requantizing every matrix to pure Q4_0…"
"$QUANTIZE" --allow-requantize --pure --output-tensor-type q4_0 \
  --token-embedding-type q4_0 "$SOURCE" "$PURE.partial" Q4_0
mv "$PURE.partial" "$PURE"

echo "dropping the duplicated output head…"
"$PYTHON" "$HERE/opt/scripts/drop_tensor.py" "$PURE" "$TIED.partial" output.weight
mv "$TIED.partial" "$TIED"

echo "baking the Muta tutor template and sampling defaults…"
"$PYTHON" "$HERE/opt/scripts/bake_system_prompt.py" "$TIED" "$FINAL.partial" \
  --system "$HERE/opt/eval/system_prompt.txt" --replace-chatml off \
  --set-name "Muta Tutor (Qwen3-1.7B)" --set-languages en \
  --sampling "temp=0.4,top_p=0.9,min_p=0.05,penalty_repeat=1.05"

[ "$(sha "$FINAL.partial")" = "$FINAL_SHA" ] \
  || { echo "derived Muta Tutor GGUF hash mismatch" >&2; exit 1; }
mv "$FINAL.partial" "$FINAL"
echo "done: $FINAL (sha256 verified)"
