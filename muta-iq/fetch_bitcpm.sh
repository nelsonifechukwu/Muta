#!/usr/bin/env bash
# Reproduce the optional BitCPM-CANN-8B UI model from the pinned official GGUF.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="$HERE/model/bitcpm4-8b-tq2_0.gguf"
FINAL="$HERE/model/bitcpm4-8b-tq2_0-envocab.gguf"
SOURCE_REV="78a2fa992bd0326b081abf3dc8ba97c33e6250f1"
SOURCE_SHA="b72d23bf549e90bdfb161a4ed217ba26b9eb3efd19363716e9bfcd265370ac91"
FINAL_SHA="069621f168502215839fb82db3afe35beb8e5350fb6cbf8523aa1eea6bee237d"
URL="https://huggingface.co/openbmb/BitCPM-CANN-8B-gguf/resolve/$SOURCE_REV/bitcpm4-8b-tq2_0.gguf"
PYTHON="${PY:-$HERE/../.venv/bin/python}"
LLAMA_DIR="$HERE/opt/llama.cpp"

sha() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  else shasum -a 256 "$1" | cut -d' ' -f1
  fi
}

mkdir -p "$HERE/model"
if [ -f "$FINAL" ] && [ "$(sha "$FINAL")" = "$FINAL_SHA" ]; then
  echo "BitCPM model already present and verified: $FINAL"
  exit 0
fi

if [ -f "$BASE" ]; then
  [ "$(sha "$BASE")" = "$SOURCE_SHA" ] \
    || { echo "source GGUF hash mismatch: $BASE" >&2; exit 1; }
else
  echo "downloading pinned OpenBMB BitCPM-CANN-8B source (2.37 GB)…"
  curl -fL --retry 5 --retry-delay 5 -C - -o "$BASE.partial" "$URL"
  [ "$(sha "$BASE.partial")" = "$SOURCE_SHA" ] \
    || { echo "downloaded source GGUF hash mismatch" >&2; exit 1; }
  mv "$BASE.partial" "$BASE"
fi

if [ ! -x "$PYTHON" ]; then
  PYTHON="$(command -v "$PYTHON" 2>/dev/null || true)"
fi
[ -n "$PYTHON" ] && [ -x "$PYTHON" ] \
  || { echo "Python environment missing — create .venv with 'make install'" >&2; exit 1; }
bash "$HERE/opt/scripts/ensure_llama_cpp.sh" "$LLAMA_DIR" >/dev/null

echo "pruning unused CJK vocabulary rows…"
"$PYTHON" "$HERE/opt/scripts/prune_vocab.py" "$BASE" "$FINAL.partial"
[ "$(sha "$FINAL.partial")" = "$FINAL_SHA" ] \
  || { echo "derived BitCPM GGUF hash mismatch" >&2; exit 1; }
mv "$FINAL.partial" "$FINAL"
echo "done: $FINAL (sha256 verified)"
