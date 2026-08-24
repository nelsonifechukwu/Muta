#!/usr/bin/env bash
# Sign every nested Mach-O before Tauri seals/signs/notarizes the outer application.
set -euo pipefail

identity="${APPLE_SIGNING_IDENTITY:?APPLE_SIGNING_IDENTITY is required}"
[ "$identity" != "-" ] || { echo "ad-hoc signing is forbidden for a release" >&2; exit 1; }
[ "$#" -gt 0 ] || { echo "usage: sign_macos_nested.sh ROOT..." >&2; exit 2; }

security find-identity -v -p codesigning | grep -F "$identity" >/dev/null \
  || { echo "code-signing identity is not installed: $identity" >&2; exit 1; }

for root in "$@"; do
  [ -d "$root" ] || { echo "nested signing root is missing: $root" >&2; exit 1; }
  while IFS= read -r -d '' candidate; do
    if file -b "$candidate" | grep -q 'Mach-O'; then
      codesign --force --options runtime --timestamp --sign "$identity" "$candidate"
      codesign --verify --strict --verbose=2 "$candidate"
    fi
  done < <(find "$root" -type f -print0)
done
