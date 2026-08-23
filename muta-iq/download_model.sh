#!/usr/bin/env bash
# Reproduce Muta Tutor — Qwen3.5-0.8B Q4_0 with baked tutor metadata.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_DIR="$HERE/model"
CANDIDATES="$HERE/opt/candidates"
FINAL="$MODEL_DIR/muta-tutor-qwen3.5-0.8b-q4_0.gguf"
FINAL_SHA="c96df4ef6d9416bea6a35866751cb6cf02e20ec6ce28b20980d66c90604d5d7b"
SOURCE="$CANDIDATES/Qwen3.5-0.8B-Q4_0.gguf"
SOURCE_SHA="444406ddd926550c724ec18d5120a9d40ded44908a063b0e66e9a7e5464c652c"
SOURCE_REV="6ab461498e2023f6e3c1baea90a8f0fe38ab64d0"
SOURCE_URL="https://huggingface.co/unsloth/Qwen3.5-0.8B-GGUF/resolve/$SOURCE_REV/Qwen3.5-0.8B-Q4_0.gguf"
MMPROJ_DIR="$HERE/../models/mmproj"
MMPROJ="$MMPROJ_DIR/Qwen3.5-0.8B-mmproj-F16.gguf"
MMPROJ_SHA="56e4c6cfe73b0c82e3e82bc518d7591997e61d81f723fc41a586f4fa69ea2453"
MMPROJ_SIZE="204987232"
MMPROJ_URL="${MMPROJ_URL:-https://huggingface.co/unsloth/Qwen3.5-0.8B-GGUF/resolve/$SOURCE_REV/mmproj-F16.gguf}"
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

mkdir -p "$MODEL_DIR" "$CANDIDATES" "$MMPROJ_DIR"
if [ -f "$MMPROJ" ]; then
  [ "$(wc -c < "$MMPROJ" | tr -d ' ')" = "$MMPROJ_SIZE" ] \
    && [ "$(sha "$MMPROJ")" = "$MMPROJ_SHA" ] \
    || { echo "Qwen3.5-0.8B projector verification failed: $MMPROJ" >&2; exit 1; }
else
  echo "downloading pinned Qwen3.5-0.8B image projector…"
  fetch "$MMPROJ_URL" "$MMPROJ"
  [ "$(wc -c < "$MMPROJ" | tr -d ' ')" = "$MMPROJ_SIZE" ] \
    && [ "$(sha "$MMPROJ")" = "$MMPROJ_SHA" ] \
    || { echo "downloaded Qwen3.5-0.8B projector verification failed" >&2; exit 1; }
fi

if [ -f "$FINAL" ] && [ "$(sha "$FINAL")" = "$FINAL_SHA" ]; then
  echo "Muta Tutor and image projector already present and verified: $FINAL"
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
  echo "downloading pinned Qwen3.5-0.8B Q4_0 source…"
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

echo "baking the Muta tutor template and sampling defaults…"
"$PYTHON" "$HERE/opt/scripts/bake_system_prompt.py" "$SOURCE" "$FINAL.partial" \
  --system "$HERE/opt/eval/system_prompt.txt" --replace-chatml off \
  --set-name "Muta Tutor (Qwen3.5-0.8B)" --set-languages en \
  --sampling "temp=0.4,top_p=0.9,min_p=0.05,penalty_repeat=1.05"

[ "$(sha "$FINAL.partial")" = "$FINAL_SHA" ] \
  || { echo "derived Muta Tutor GGUF hash mismatch" >&2; exit 1; }
mv "$FINAL.partial" "$FINAL"
echo "done: $FINAL (sha256 verified)"
