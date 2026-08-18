#!/usr/bin/env bash
# Fetch or validate the exact llama.cpp source tree used by the reproducible GGUF pipelines.
set -euo pipefail

LLAMA_DIR="${1:?usage: ensure_llama_cpp.sh CHECKOUT_DIR}"
LLAMA_COMMIT="48d22e295e2b86b47366c16390794f3e05ba970a" # b10360

if [ ! -d "$LLAMA_DIR/.git" ]; then
  [ ! -e "$LLAMA_DIR" ] \
    || { echo "$LLAMA_DIR exists but is not a git checkout" >&2; exit 1; }
  command -v git >/dev/null 2>&1 || { echo "git is required" >&2; exit 1; }
  echo "fetching pinned llama.cpp b10360 tooling…"
  git clone --filter=blob:none --no-checkout https://github.com/ggml-org/llama.cpp.git "$LLAMA_DIR"
  git -C "$LLAMA_DIR" checkout --detach "$LLAMA_COMMIT"
fi

[ "$(git -C "$LLAMA_DIR" rev-parse HEAD)" = "$LLAMA_COMMIT" ] \
  || { echo "llama.cpp checkout is not pinned b10360/$LLAMA_COMMIT" >&2; exit 1; }
git -C "$LLAMA_DIR" diff --quiet -- gguf-py \
  || { echo "llama.cpp gguf-py has local modifications" >&2; exit 1; }
printf '%s\n' "$LLAMA_COMMIT"
