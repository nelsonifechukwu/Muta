#!/usr/bin/env bash
# Poll origin/main and launch the cached Linux/Windows build for each new pushed commit.
set -euo pipefail

repo="${MUTA_PACKAGE_REPO:-$HOME/Muta}"
state_root="${MUTA_PACKAGE_STATE_ROOT:-$HOME/.local/state/muta-packages}"
bucket="${MUTA_PACKAGE_BUCKET:-muta-adtc-desktop-packages}"
zone="${MUTA_PACKAGE_ZONE:-us-west1-b}"
mkdir -p "$state_root"
exec 9>"$state_root/watch.lock"
flock -n 9 || exit 0

cd "$repo"
git fetch origin main
commit="$(git rev-parse 'origin/main^{commit}')"
test "${#commit}" -eq 40
previous=""
test ! -f "$state_root/completed-main" || previous="$(cat "$state_root/completed-main")"
if [ "$commit" = "$previous" ]; then
  exit 0
fi

git merge --ff-only origin/main
version="0.1.$(git rev-list --count "$commit")"
python3 scripts/gcp_desktop_build.py \
  --commit "$commit" \
  --version "$version" \
  --bucket "$bucket" \
  --zone "$zone"
printf '%s\n' "$commit" > "$state_root/completed-main.tmp"
mv "$state_root/completed-main.tmp" "$state_root/completed-main"
