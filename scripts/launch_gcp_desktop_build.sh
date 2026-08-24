#!/usr/bin/env bash
# Launch a status-tracked GCP package build that survives the caller's SSH session.
set -euo pipefail

if [ "$#" -lt 4 ] || [ "$#" -gt 5 ]; then
  echo "usage: $0 COMMIT VERSION BUCKET ZONE [WINDOWS_INSTANCE]" >&2
  exit 2
fi

commit="$1"
version="$2"
bucket="$3"
zone="$4"
windows_instance="${5:-muta-package-windows}"
repo="${MUTA_PACKAGE_REPO:-$HOME/Muta}"
state_root="${MUTA_PACKAGE_STATE_ROOT:-$HOME/.local/state/muta-packages}/manual"
job="$commit-$version"
status="$state_root/$job.status"
log="$state_root/$job.log"
lock="$state_root/$job.lock"
mkdir -p "$state_root"

if [ "${MUTA_GCP_DETACHED_CHILD:-0}" = "1" ]; then
  printf 'running:%s\n' "$BASHPID" > "$status.tmp"
  mv "$status.tmp" "$status"
  set +e
  cd "$repo"
  python3 scripts/gcp_desktop_build.py \
    --commit "$commit" \
    --version "$version" \
    --bucket "$bucket" \
    --zone "$zone" \
    --windows-instance "$windows_instance"
  result=$?
  set -e
  if [ "$result" -eq 0 ]; then
    printf 'complete\n' > "$status.tmp"
  else
    printf 'failed:%s\n' "$result" > "$status.tmp"
  fi
  mv "$status.tmp" "$status"
  exit "$result"
fi

if [ -f "$status" ]; then
  current_status="$(cat "$status")"
  if [[ "$current_status" = running:* ]]; then
    running_pid="${current_status#running:}"
    if kill -0 "$running_pid" 2>/dev/null; then
      echo "GCP package job is already running: $job"
      echo "$status"
      exit 0
    fi
  fi
fi

exec 9>"$lock"
if ! flock -n 9; then
  echo "GCP package job is already running: $job"
  echo "$status"
  exit 0
fi

printf 'starting\n' > "$status.tmp"
mv "$status.tmp" "$status"
MUTA_GCP_DETACHED_CHILD=1 nohup "$0" "$@" > "$log" 2>&1 < /dev/null &
echo "launched GCP package job $job as PID $!"
echo "$status"
echo "$log"
