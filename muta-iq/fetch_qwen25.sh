#!/usr/bin/env bash
# Fetch the exact fine-tuned Qwen2.5 1.5B Q4_K_M artifact promoted by the campaign.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_DIR="$HERE/model"
FINAL="$MODEL_DIR/Muta-Tutor-Qwen2.5-1.5B-Finetuned-Q4_K_M.gguf"
FINAL_SHA="a750d00d458c6ab38925364ea1413db00648449180941e47025736d09922e1eb"
FINAL_BYTES=986048128
HF_REPO="timiiowolabi/Muta-Tutor-Qwen2.5-1.5B-ADTC-GGUF"
HF_FILE="Muta-Tutor-Qwen2.5-1.5B-Q4_K_M.gguf"

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
  [ -f "$1" ] && [ "$(bytes "$1")" = "$FINAL_BYTES" ] && [ "$(sha "$1")" = "$FINAL_SHA" ]
}

hf_cli() {
  if [ -n "${HF_CLI:-}" ] && [ -x "$HF_CLI" ]; then printf '%s\n' "$HF_CLI"
  elif command -v hf >/dev/null 2>&1; then command -v hf
  elif [ -x "$HOME/.local/bin/hf" ]; then printf '%s\n' "$HOME/.local/bin/hf"
  else return 1
  fi
}

mkdir -p "$MODEL_DIR"
if verify "$FINAL"; then
  echo "fine-tuned Qwen2.5 already present and verified: $FINAL"
  exit 0
fi

HF="$(hf_cli || true)"
[ -n "$HF" ] \
  || { echo "Hugging Face CLI missing — install it from https://hf.co/cli/install.sh" >&2; exit 1; }
"$HF" auth whoami --format quiet >/dev/null 2>&1 \
  || { echo "Hugging Face login required for the private model: run 'hf auth login'" >&2; exit 1; }

echo "downloading the promoted fine-tuned Qwen2.5 GGUF…"
"$HF" download "$HF_REPO" "$HF_FILE" --local-dir "$MODEL_DIR" >/dev/null
DOWNLOAD="$MODEL_DIR/$HF_FILE"
verify "$DOWNLOAD" \
  || { echo "downloaded fine-tuned Qwen2.5 GGUF failed integrity verification" >&2; exit 1; }
mv "$DOWNLOAD" "$FINAL"
echo "done: $FINAL (size and sha256 verified)"
