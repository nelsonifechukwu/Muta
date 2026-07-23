#!/usr/bin/env bash
# USB → local disk, hashed on both sides (TDD §10.3). Thin wrapper; logic is in bundle/stage.py
# so it is unit-tested rather than discovered broken in a classroom.
#
#   deploy/stage.sh --src /media/usb/tutor [--dst /opt/tutor] [--no-warm]
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
exec python3 -m bundle.stage "$@"
