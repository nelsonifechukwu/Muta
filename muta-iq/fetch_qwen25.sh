#!/usr/bin/env bash
# Fetch the exact Qwen2.5 1.5B Instruct Q4_K_M artifact used by the GCP campaign.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_DIR="$HERE/model"
FINAL="$MODEL_DIR/qwen2.5-1.5b-instruct-q4_k_m.gguf"
FINAL_SHA="6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e"
FINAL_BYTES=1117320736
SOURCE_REV="91cad51170dc346986eccefdc2dd33a9da36ead9"
SOURCE_URL="https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/$SOURCE_REV/qwen2.5-1.5b-instruct-q4_k_m.gguf"

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
  [ "$(bytes "$1")" = "$FINAL_BYTES" ] && [ "$(sha "$1")" = "$FINAL_SHA" ]
}

mkdir -p "$MODEL_DIR"
if [ -f "$FINAL" ] && verify "$FINAL"; then
  echo "Qwen2.5 already present and verified: $FINAL"
  exit 0
fi

rm -f "$FINAL.partial"
if command -v curl >/dev/null 2>&1; then
  curl -fL --retry 5 --retry-delay 5 --progress-bar -o "$FINAL.partial" "$SOURCE_URL"
elif command -v wget >/dev/null 2>&1; then
  wget --show-progress -O "$FINAL.partial" "$SOURCE_URL"
else
  echo "neither curl nor wget is available" >&2
  exit 1
fi

verify "$FINAL.partial" \
  || { echo "downloaded Qwen2.5 GGUF failed byte-size or SHA-256 verification" >&2; exit 1; }
mv "$FINAL.partial" "$FINAL"
echo "done: $FINAL (size and sha256 verified)"
