#!/usr/bin/env bash
# Rebuild the muta residency-window engine from scratch: llama.cpp b10360 + opt/patches/0001.
# Usage: opt/build_engine.sh [jobs]   (needs cmake ≥3.14; on this Mac: ~/miniforge3/envs/ai/bin/cmake)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CMAKE="${CMAKE:-$(command -v cmake || echo "$HOME/miniforge3/envs/ai/bin/cmake")}"
J="${1:-8}"
if [[ ! -d "$HERE/llama.cpp" ]]; then
  git clone --depth 1 --branch b10360 https://github.com/ggml-org/llama.cpp.git "$HERE/llama.cpp"
  git -C "$HERE/llama.cpp" apply "$HERE/patches/0001-muta-residency-window-b10360.patch"
fi
"$CMAKE" -S "$HERE/llama.cpp" -B "$HERE/llama.cpp/build-cpu" -DCMAKE_BUILD_TYPE=Release \
  -DGGML_METAL=OFF -DGGML_BLAS=OFF -DLLAMA_CURL=OFF -DGGML_NATIVE=ON \
  -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_SERVER=OFF -DLLAMA_OPENSSL=OFF
"$CMAKE" --build "$HERE/llama.cpp/build-cpu" -j "$J" --target llama-bench llama-completion llama-perplexity llama-quantize
echo "built: $HERE/llama.cpp/build-cpu/bin/{llama-bench,llama-completion,llama-perplexity,llama-quantize}"
