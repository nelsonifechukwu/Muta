#!/usr/bin/env bash
# Download the submission model: Muta Tutor — Qwen3-1.7B, pure Q4_0 (every matrix Q4_0, tied Q4_0
# embedding/LM head), with the tutoring persona and generation defaults baked into the GGUF metadata.
# Idempotent; public URL; verifies sha256. Output path matches `_runtime.model_path` in metadata.json.
#
# Provenance (see REPORT.md and opt/docs/): base = Qwen/Qwen3-1.7B (Apache-2.0) via bartowski's Q4_0 GGUF
# -> llama-quantize --pure Q4_0 (tied embedding Q4_0, no Q4_1/Q6_K tensors) -> duplicated `output.weight`
# dropped (llama.cpp uses the tied embedding) -> chat template replaced by ChatML + Muta persona (no-think),
# general.sampling.* defaults set. Scripts: opt/scripts/{bake_system_prompt.py,drop_tensor.py}.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_DIR="$HERE/model"
MODEL_FILE="$MODEL_DIR/muta-tutor-qwen3-1.7b-q4_0.gguf"
MODEL_SHA256="a98ce36e9ff97e5271d90cbc429c952f99a5a966bb0195ae74661b4c054fd63e"
MODEL_URL="${MODEL_URL:-https://huggingface.co/timiiowolabi/muta-tutor-qwen3-1.7b-q4_0/resolve/main/muta-tutor-qwen3-1.7b-q4_0.gguf}"

mkdir -p "$MODEL_DIR"

sha() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi; }
fetch() { # url dest
  if command -v curl >/dev/null 2>&1; then curl -L --fail --retry 5 --retry-delay 5 -C - --progress-bar -o "$2.partial" "$1"
  elif command -v wget >/dev/null 2>&1; then wget -c --show-progress -O "$2.partial" "$1"
  else echo "neither curl nor wget available" >&2; exit 1; fi
  mv "$2.partial" "$2"
}

if [[ -f "$MODEL_FILE" ]] && [[ "$(sha "$MODEL_FILE")" == "$MODEL_SHA256" ]]; then
  echo "model already present and verified at $MODEL_FILE — skipping download"; exit 0
fi

echo "downloading $MODEL_URL -> $MODEL_FILE (~975 MB)…"
fetch "$MODEL_URL" "$MODEL_FILE"
got="$(sha "$MODEL_FILE")"
if [[ "$got" != "$MODEL_SHA256" ]]; then
  echo "sha256 mismatch: got $got expected $MODEL_SHA256" >&2; exit 1
fi
echo "done: $MODEL_FILE (sha256 verified)"
