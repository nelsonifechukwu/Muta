#!/usr/bin/env sh
# ADTC submission model fetch — idempotent, credential-free, resumable.
#
# Downloads the exact pinned GGUF this submission's metadata.json describes into
# model/ (the _runtime.model_path the profiler reads). The revision below MUST match
# models/pins.lock.json — the audit runs this script on a clean clone, so a drifted
# URL silently benchmarks a different file than the one we measured.
set -eu

REPO="unsloth/Qwen3.5-4B-GGUF"
REVISION="e87f176479d0855a907a41277aca2f8ee7a09523"
FILE="Qwen3.5-4B-Q4_K_M.gguf"
SHA256="00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4"

DIR="$(cd "$(dirname "$0")" && pwd)"
DEST_DIR="$DIR/model"
DEST="$DEST_DIR/model.gguf"
URL="https://huggingface.co/$REPO/resolve/$REVISION/$FILE"

mkdir -p "$DEST_DIR"

checksum() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | cut -d' ' -f1
    else
        shasum -a 256 "$1" | cut -d' ' -f1
    fi
}

if [ -f "$DEST" ] && [ "$(checksum "$DEST")" = "$SHA256" ]; then
    echo "model already present and verified: $DEST"
    exit 0
fi

echo "downloading $FILE @ $REVISION (~2.6 GB, resumable)"
if command -v curl >/dev/null 2>&1; then
    curl -fL --retry 5 -C - -o "$DEST.partial" "$URL"
else
    wget -c -O "$DEST.partial" "$URL"
fi

ACTUAL="$(checksum "$DEST.partial")"
if [ "$ACTUAL" != "$SHA256" ]; then
    echo "sha256 mismatch: expected $SHA256 got $ACTUAL" >&2
    exit 1
fi
mv "$DEST.partial" "$DEST"
echo "verified: $DEST"
