#!/usr/bin/env bash
# Launch the llama.cpp inference server against the configured model (ROADMAP 15 Jul).
# Thin wrapper over the Python supervisor so the launch flags have a single source of
# truth (runtime/config.py). Override anything via MUTA_RT_* env vars.
#   ./runtime/run.sh              # resolve model (local, else HF) and serve
#   ./runtime/run.sh --print-cmd  # print the exact llama-server invocation and exit
set -euo pipefail
cd "$(dirname "$0")/.."
exec python -m runtime.server "$@"
