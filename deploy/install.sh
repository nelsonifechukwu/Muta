#!/usr/bin/env bash
# Install a staged bundle as running services (TDD T3, §10.4).
#
#   sudo deploy/install.sh [--root /opt/tutor] [--profile classroom|solo-demo] [--no-systemd]
#
# Idempotent: safe to re-run after a re-stage. Creates the private data dirs 0700, mints an
# API key if absent (the loopback engines are key-protected so a curious student on the LAN
# cannot drive the model directly), installs the units, and enables them.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT=/opt/tutor
PROFILE=classroom
USE_SYSTEMD=1

while [ $# -gt 0 ]; do
  case "$1" in
    --root) ROOT="$2"; shift 2 ;;
    --profile) PROFILE="$2"; shift 2 ;;
    --no-systemd) USE_SYSTEMD=0; shift ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

echo "==> creating layout under $ROOT"
python3 - "$ROOT" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, ".")
from bundle.layout import BUNDLE_DIRS, PRIVATE_DIRS

root = Path(sys.argv[1])
for d in BUNDLE_DIRS:
    (root / d).mkdir(parents=True, exist_ok=True)
for d in PRIVATE_DIRS:
    (root / d).chmod(0o700)
print(f"    {len(BUNDLE_DIRS)} directories ready")
PY

if [ ! -f "$ROOT/data/api.key" ]; then
  echo "==> minting API key"
  ( umask 077; head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n' > "$ROOT/data/api.key" )
fi
chmod 600 "$ROOT/data/api.key"

echo "==> installing profile: $PROFILE"
install -m 644 "$REPO_ROOT/deploy/etc/profile.env" "$ROOT/etc-profile.env.default" 2>/dev/null || true
mkdir -p "$ROOT/etc"
sed "s/^PROFILE=.*/PROFILE=$PROFILE/" "$REPO_ROOT/deploy/etc/profile.env" > "$ROOT/etc/profile.env"

echo "==> verifying bundle integrity before enabling anything"
python3 -m bundle.manifest verify --root "$ROOT" || {
  echo "FATAL: refusing to install a bundle that does not match its manifest" >&2
  exit 1
}

if [ "$USE_SYSTEMD" = "0" ] || ! command -v systemctl >/dev/null 2>&1; then
  echo "==> systemd not used; start manually:  $ROOT/gw/run.sh"
  exit 0
fi

echo "==> installing systemd units"
# Audio gets the last physical core to itself — an audio dropout is more judge-visible than
# 5% off the decode rate (TDD §6.4).
AUDIO_CPU="$(( $(getconf _NPROCESSORS_ONLN) - 1 ))"
for unit in "$REPO_ROOT"/deploy/units/*.service "$REPO_ROOT"/deploy/units/*.slice; do
  [ -e "$unit" ] || continue
  sed -e "s#@ROOT@#$ROOT#g" -e "s#@AUDIO_CPU@#$AUDIO_CPU#g" "$unit" \
    > "/etc/systemd/system/$(basename "$unit")"
done
install -m 644 "$REPO_ROOT/deploy/units/earlyoom.conf" /etc/default/earlyoom 2>/dev/null || true
install -m 644 "$REPO_ROOT/deploy/units/zram-generator.conf" /etc/systemd/zram-generator.conf 2>/dev/null || true

systemctl daemon-reload
systemctl enable --now tutor-core.service tutor-embed.service tutor-gw.service
systemctl enable --now tutor-audio.service || echo "!! audio service not enabled (sherpa binaries absent)"

echo "==> installed. health:  curl -s http://127.0.0.1:8080/v1/health"
