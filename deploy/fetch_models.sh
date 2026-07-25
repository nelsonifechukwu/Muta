#!/usr/bin/env bash
# SUPERSEDED by scripts/fetch_models.sh — that is the T2 implementation (`make fetch-models`).
# It resolves every artifact against the live Hub API, pins commit SHAs in
# models/pins.lock.json, verifies sha256 twice, captures licences, and covers asr/vad/tts/
# embed as well as core. This script remains only for the `--fixture` dev path (Qwen3-0.6B)
# and the deploy/versions.lock convention; consolidate the two before the bundle freeze.
#
# Download every model file by EXACT revision, then write MANIFEST.json (TDD T2, §11.2).
#
#   deploy/fetch_models.sh [--dest dist/models] [--fixture]
#
# This is the only step in the whole system allowed to touch the network, and it runs on the
# build machine — never on the target (TDD §2 C-4). Revisions are commit hashes, not `main`:
# a moving tag means the bundle you tested is not the bundle you shipped.
#
# `--fixture` fetches the small dev model this repo runs against today (Qwen3-0.6B) instead
# of the competition core, which stays unpinned until the D1 bake-off closes.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK="$REPO_ROOT/deploy/versions.lock"
DEST="$REPO_ROOT/dist/models"
FIXTURE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --dest) DEST="$2"; shift 2 ;;
    --fixture) FIXTURE=1; shift ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

# shellcheck disable=SC1090
. "$LOCK"

fetch() {  # fetch <repo> <file> <revision> <subdir>
  local repo="$1" file="$2" rev="$3" subdir="$4"
  if [ -z "$repo" ] || [ -z "$file" ]; then
    echo "!! skipping $subdir: not pinned in versions.lock (see TDD §14 gates)" >&2
    return 0
  fi
  if [ -z "$rev" ]; then
    echo "FATAL: $repo/$file has no revision pin — refusing to download a moving target" >&2
    return 1
  fi
  mkdir -p "$DEST/$subdir"
  echo "==> $repo@${rev:0:12} :: $file"
  python3 - "$repo" "$file" "$rev" "$DEST/$subdir" <<'PY'
import shutil, sys
from pathlib import Path
from huggingface_hub import hf_hub_download

repo, filename, revision, dest = sys.argv[1:5]
src = hf_hub_download(repo_id=repo, filename=filename, revision=revision)
target = Path(dest) / Path(filename).name
if not target.exists() or target.stat().st_size != Path(src).stat().st_size:
    shutil.copyfile(src, target)
print(f"    -> {target} ({target.stat().st_size / 2**20:.0f} MiB)")
PY
}

if [ "$FIXTURE" = "1" ]; then
  fetch "$FIXTURE_MODEL_REPO" "$FIXTURE_MODEL_FILE" "${FIXTURE_MODEL_REVISION:-main}" core
else
  fetch "$CORE_MODEL_REPO"  "$CORE_MODEL_FILE"  "$CORE_MODEL_REVISION"  core
  fetch "$MMPROJ_REPO"      "$MMPROJ_FILE"      "$MMPROJ_REVISION"      core
  fetch "$DRAFT_MODEL_REPO" "$DRAFT_MODEL_FILE" "$DRAFT_MODEL_REVISION" draft
fi
fetch "$EMBED_MODEL_REPO" "$EMBED_MODEL_FILE" "${EMBED_MODEL_REVISION:-main}" embed

for url_var in ASR_MODEL_URL TTS_PIPER_VOICE_URL TTS_KOKORO_URL; do
  url="${!url_var:-}"
  [ -n "$url" ] || { echo "!! $url_var not pinned — skipping" >&2; continue; }
  case "$url_var" in
    ASR_MODEL_URL) sub=asr ;;
    *)             sub=tts ;;
  esac
  mkdir -p "$DEST/$sub"
  echo "==> $url"
  curl -fsSL "$url" -o "$DEST/$sub/$(basename "$url")"
done

echo "==> writing MANIFEST.json"
python3 -m bundle.manifest build --root "$(dirname "$DEST")" \
  --licenses "$REPO_ROOT/deploy/licenses.json"
python3 -m bundle.manifest verify --root "$(dirname "$DEST")"
echo "==> ok: models fetched and hashed (verified twice per TDD T2)"
