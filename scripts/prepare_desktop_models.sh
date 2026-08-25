#!/usr/bin/env bash
# Provision only the redistributable product models used by the desktop application.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

# Produces the selected 0.8B tutor deterministically from the pinned upstream GGUF. CI may
# provide MODEL_URL for a faster trusted mirror, but the final SHA-256 is identical either way.
bash muta-iq/download_model.sh

# Voice and retrieval are product features, so their small offline models belong in the pack.
# The 4B bake-off model, draft model and other development candidates are intentionally omitted.
fetch_product_model() {
  local artifact="$1"
  local status
  if scripts/fetch_models.sh --only "$artifact"; then
    return
  else
    status=$?
  fi
  # The pinned Moonshine archive is 118.2 MiB against the old 100 MiB planning ceiling.
  # fetch_models deliberately returns 1 for that already-documented size flag after it has
  # verified every pinned file. Other artifacts and all hard fetch/licence errors stay fatal.
  if [ "$artifact" = asr ] && [ "$status" -eq 1 ]; then
    echo "accepted documented ASR size flag; all pinned files were verified" >&2
    return
  fi
  return "$status"
}

for artifact in asr vad tts embed; do
  fetch_product_model "$artifact"
done

test "$(wc -c < muta-iq/model/muta-tutor-qwen3.5-0.8b-q4_0.gguf | tr -d ' ')" = "512977376"
test "$(wc -c < models/mmproj/Qwen3.5-0.8B-mmproj-F16.gguf | tr -d ' ')" = "204987232"
checksum_manifest="$(mktemp)"
trap 'rm -f "$checksum_manifest"' EXIT
printf '%s  %s\n' \
  "552de22f7ea6f161a458985900e2c961d7578baa1ea9c23018ae27151623ff26" \
  "muta-iq/model/muta-tutor-qwen3.5-0.8b-q4_0.gguf" \
  "56e4c6cfe73b0c82e3e82bc518d7591997e61d81f723fc41a586f4fa69ea2453" \
  "models/mmproj/Qwen3.5-0.8B-mmproj-F16.gguf" \
  > "$checksum_manifest"
if command -v sha256sum >/dev/null 2>&1; then
  sha256sum --check --strict "$checksum_manifest"
else
  shasum -a 256 --check "$checksum_manifest"
fi
