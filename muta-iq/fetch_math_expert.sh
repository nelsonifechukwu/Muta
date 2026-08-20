#!/usr/bin/env bash
# Fetch the exact Qwen3 0.6B Math-Expert Q4_K_M finalist used by the GCP campaign.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_DIR="$HERE/model"
FINAL="$MODEL_DIR/Qwen3-0.6B-Math-Expert.Q4_K_M.gguf"
FINAL_SHA="7f64c2e3bbd5c6fa570f49631cad5527ebd4acd7fcaf014963152027b2dae9a1"
FINAL_BYTES=396706176
SOURCE_REV="aa95cecf66c2cdd4bac11c70999dab8cefa42d08"
SOURCE_URL="https://huggingface.co/mradermacher/Qwen3-0.6B-Math-Expert-GGUF/resolve/$SOURCE_REV/Qwen3-0.6B-Math-Expert.Q4_K_M.gguf"

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
  echo "Math-Expert already present and verified: $FINAL"
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
  || { echo "downloaded Math-Expert GGUF failed byte-size or SHA-256 verification" >&2; exit 1; }
mv "$FINAL.partial" "$FINAL"
echo "done: $FINAL (size and sha256 verified)"
