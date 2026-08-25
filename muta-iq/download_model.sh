#!/usr/bin/env bash
# Fetch the exact fine-tuned Qwen3.5 0.8B Q4_0 artifact promoted by the campaign.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_DIR="$HERE/model"
FINAL="$MODEL_DIR/muta-tutor-qwen3.5-0.8b-q4_0.gguf"
FINAL_SHA="552de22f7ea6f161a458985900e2c961d7578baa1ea9c23018ae27151623ff26"
FINAL_BYTES=512977376
HF_REPO="timiiowolabi/Muta-Tutor-Qwen3.5-0.8B-ADTC-GGUF"
HF_FILE="Muta-Tutor-Qwen3.5-0.8B-Q4_0.gguf"

MMPROJ_DIR="$HERE/../models/mmproj"
MMPROJ="$MMPROJ_DIR/Qwen3.5-0.8B-mmproj-F16.gguf"
MMPROJ_SHA="56e4c6cfe73b0c82e3e82bc518d7591997e61d81f723fc41a586f4fa69ea2453"
MMPROJ_SIZE=204987232
MMPROJ_REV="6ab461498e2023f6e3c1baea90a8f0fe38ab64d0"
MMPROJ_URL="${MMPROJ_URL:-https://huggingface.co/unsloth/Qwen3.5-0.8B-GGUF/resolve/$MMPROJ_REV/mmproj-F16.gguf}"

sha() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  else shasum -a 256 "$1" | cut -d' ' -f1
  fi
}

bytes() {
  if stat -c '%s' "$1" >/dev/null 2>&1; then stat -c '%s' "$1"
  else stat -f '%z' "$1"
  fi
}

verify() {
  [ -f "$1" ] && [ "$(bytes "$1")" = "$2" ] && [ "$(sha "$1")" = "$3" ]
}

hf_cli() {
  if [ -n "${HF_CLI:-}" ] && [ -x "$HF_CLI" ]; then printf '%s\n' "$HF_CLI"
  elif command -v hf >/dev/null 2>&1; then command -v hf
  elif [ -x "$HOME/.local/bin/hf" ]; then printf '%s\n' "$HOME/.local/bin/hf"
  else return 1
  fi
}

fetch_public() {
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

mkdir -p "$MODEL_DIR" "$MMPROJ_DIR"

if verify "$MMPROJ" "$MMPROJ_SIZE" "$MMPROJ_SHA"; then
  :
elif [ -f "$MMPROJ" ]; then
  echo "Qwen3.5-0.8B projector verification failed: $MMPROJ" >&2
  exit 1
else
  echo "downloading pinned Qwen3.5-0.8B image projector…"
  fetch_public "$MMPROJ_URL" "$MMPROJ"
  verify "$MMPROJ" "$MMPROJ_SIZE" "$MMPROJ_SHA" \
    || { echo "downloaded Qwen3.5-0.8B projector verification failed" >&2; exit 1; }
fi

if verify "$FINAL" "$FINAL_BYTES" "$FINAL_SHA"; then
  echo "fine-tuned Muta Tutor and image projector already present and verified: $FINAL"
  exit 0
fi

HF="$(hf_cli || true)"
[ -n "$HF" ] \
  || { echo "Hugging Face CLI missing — install it from https://hf.co/cli/install.sh" >&2; exit 1; }
"$HF" auth whoami --format quiet >/dev/null 2>&1 \
  || { echo "Hugging Face login required for the private model: run 'hf auth login'" >&2; exit 1; }

echo "downloading the promoted fine-tuned Qwen3.5 GGUF…"
"$HF" download "$HF_REPO" "$HF_FILE" --local-dir "$MODEL_DIR" >/dev/null
DOWNLOAD="$MODEL_DIR/$HF_FILE"
verify "$DOWNLOAD" "$FINAL_BYTES" "$FINAL_SHA" \
  || { echo "downloaded fine-tuned Qwen3.5 GGUF failed integrity verification" >&2; exit 1; }
mv "$DOWNLOAD" "$FINAL"
echo "done: $FINAL (size and sha256 verified)"
