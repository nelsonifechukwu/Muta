#!/usr/bin/env bash
# Acceptance checks for the fetched model bundle (TDD T2).
#
#   scripts/verify_models.sh [--strict]
#
# Verifies: every fetched artifact's sha256 still matches MANIFEST.json · resident tier
# <= 3.3 GiB · licences all permissive · core GGUF loads under llama-cli · embed GGUF
# returns a correctly-sized vector · sherpa-onnx can instantiate the ASR, VAD and TTS
# engines · KV metadata (block_count / head_count_kv / key_length) written to
# bench/kv_metadata.json for the TDD §5.2 slot table.
#
# Checks whose tooling is absent report SKIP; --strict turns those into failures and is
# what the build machine and CI should use.
#
# Exit: 0 all good · 1 a check failed · 2 no manifest (run fetch_models.sh first).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

case "${1:-}" in
  -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
esac

exec "${PYTHON:-python3}" "$REPO_ROOT/scripts/verify_models.py" "$@"
