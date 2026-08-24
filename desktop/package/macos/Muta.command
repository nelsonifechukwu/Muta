#!/bin/zsh
set -eu

package_dir="${0:A:h}"
app="$package_dir/Muta.app"

if [[ ! -d "$app" ]]; then
  echo "Muta.app must remain beside Muta.command."
  echo "Press Return to close this window."
  read -r
  exit 1
fi

# Unsigned private-test archives acquire quarantine when downloaded. Use Apple's system tool and
# touch only the sibling Muta application selected above. The fallback supports xattr variants
# that do not accept recursive mode.
if ! /usr/bin/xattr -c -r "$app"; then
  /usr/bin/find "$app" -exec /usr/bin/xattr -c {} +
fi
/usr/bin/open "$app"
