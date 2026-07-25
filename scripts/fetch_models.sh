#!/usr/bin/env bash
# Fetch, pin, verify and manifest every model artifact the offline tutor ships (TDD T2).
#
#   scripts/fetch_models.sh [--dry-run] [--only NAME] [--repin] [--force]
#                           [--mmproj-precision f16]
#                           [--with-multilingual-asr] [--with-kokoro] [--with-draft]
#                           [--quant-variants]
#
# Build machine only (TDD §2 C-4). Nothing this writes needs network access at run time.
#
#   --dry-run          print the resolution plan (repo, revision, license) and download
#                      nothing. Use this first — it is also the licence audit.
#   --only NAME        fetch a single artifact. Repeatable.
#   --repin            re-resolve every pin to the current repo HEAD. Changes what you
#                      ship; do it deliberately and commit models/pins.lock.json.
#   --force            redownload even when the on-disk hash already matches.
#   --quant-variants   also fetch the three D1 bake-off candidates side by side.
#
# Tier B artifacts are always *resolved* and recorded in MANIFEST.json as fetched:false,
# so the plan stays auditable, but they download only behind their flag.
#
# Exit: 0 clean · 1 size flags · 2 usage · 3 resolution/licence failure (never downgraded).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

case "${1:-}" in
  -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
esac

PY="${PYTHON:-python3}"
if ! "$PY" -c "import huggingface_hub" 2>/dev/null; then
  echo "FATAL: huggingface_hub not importable via '$PY'." >&2
  echo "       pip install huggingface_hub   (build-time dependency only)" >&2
  exit 2
fi

exec "$PY" "$REPO_ROOT/scripts/fetch_models.py" "$@"
