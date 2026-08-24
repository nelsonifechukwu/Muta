#!/bin/sh
set -eu

package_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
app="$package_dir/Muta.AppImage"

if [ ! -f "$app" ]; then
  echo "Muta.AppImage must remain beside Muta.sh." >&2
  exit 1
fi

chmod +x "$app"
exec "$app" --install-model-pack "$package_dir/model-pack"
