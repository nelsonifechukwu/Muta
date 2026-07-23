#!/usr/bin/env bash
# Assemble dist/ in the §10.1 shape and rehearse it in a clean room (TDD T16, §11.4).
#
#   deploy/package.sh [--dist dist] [--skip-selftest]
#
# The bundle is the deliverable: a judge plugs in a flash drive and the thing works with no
# install, no network, no Docker. So packaging ends with the same bundle running inside
# `--network none` with an 8 GiB cap — the closest rehearsal available before hardware day.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="$REPO_ROOT/dist"
SKIP_SELFTEST=0

while [ $# -gt 0 ]; do
  case "$1" in
    --dist) DIST="$2"; shift 2 ;;
    --skip-selftest) SKIP_SELFTEST=1; shift ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

cd "$REPO_ROOT"
# shellcheck disable=SC1091
. deploy/versions.lock

echo "==> layout"
python3 - "$DIST" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, ".")
from bundle.layout import BUNDLE_DIRS
root = Path(sys.argv[1])
for d in BUNDLE_DIRS:
    (root / d).mkdir(parents=True, exist_ok=True)
print(f"    {root} ready")
PY

echo "==> gateway app"
rsync -a --delete \
  --exclude '__pycache__' --exclude '*.pyc' --exclude 'tests' \
  bundle contracts orchestrator runtime "$DIST/gw/"
cp pyproject.toml "$DIST/gw/"
[ -d ui/dist ] && rsync -a ui/dist/ "$DIST/gw/ui/"

echo "==> scripts, units, profile"
cp deploy/versions.lock deploy/selftest.sh "$DIST/"
cp deploy/install.sh deploy/stage.sh "$DIST/"
mkdir -p "$DIST/units" "$DIST/etc"
cp deploy/units/* "$DIST/units/"
cp deploy/etc/profile.env "$DIST/etc/"
chmod +x "$DIST"/*.sh

echo "==> binaries"
if [ -d "$REPO_ROOT/.build/llama.cpp/build/bin" ]; then
  cp "$REPO_ROOT/.build/llama.cpp/build/bin/llama-server" "$DIST/bin/" 2>/dev/null || true
  cp "$REPO_ROOT/.build/llama.cpp/build/bin/llama-bench"  "$DIST/bin/" 2>/dev/null || true
  cp "$DIST/bin/llama-server" "$DIST/bin/llama-server-core" 2>/dev/null || true
else
  echo "!! no built engine found — run deploy/build.sh first (bundle will be incomplete)"
fi

echo "==> manifest (hashes every binary, model and index file)"
python3 -m bundle.manifest build --root "$DIST" --licenses deploy/licenses.json
python3 -m bundle.manifest verify --root "$DIST"

SIZE="$(du -sh "$DIST" | cut -f1)"
echo "==> dist assembled: $SIZE"

if [ "$SKIP_SELFTEST" = "1" ]; then
  echo "==> selftest skipped"
  exit 0
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "!! docker absent — cannot run the clean-room rehearsal here (TDD T16 stays open)"
  exit 0
fi

echo "==> clean-room selftest (${TARGET_OS_IMAGE}, --network none, 8 GiB)"
docker run --rm --platform=linux/amd64 --network none --memory 8g \
  -v "$DIST:/opt/tutor:ro" -w /opt/tutor \
  "${TARGET_OS_IMAGE}" /opt/tutor/selftest.sh --root /opt/tutor --offline-only
