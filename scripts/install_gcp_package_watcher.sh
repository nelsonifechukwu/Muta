#!/usr/bin/env bash
# Install the origin/main package watcher on the Ubuntu GCP coordinator.
set -euo pipefail

builder_user="${MUTA_PACKAGE_BUILDER_USER:-$USER}"
builder_home="$(getent passwd "$builder_user" | cut -d: -f6)"
gcloud_dir="$(dirname "$(command -v gcloud)")"
repo="${MUTA_PACKAGE_REPO:-$HOME/Muta}"
state_root="${MUTA_PACKAGE_STATE_ROOT:-$HOME/.local/state/muta-packages}"
test -n "$builder_home"
test -x "$gcloud_dir/gcloud"
test -x "$repo/scripts/gcp_package_watch.sh"
mkdir -p "$state_root"

if [ "${1:-}" = "--initialize" ]; then
  git -C "$repo" fetch origin main
  git -C "$repo" rev-parse 'origin/main^{commit}' > "$state_root/completed-main"
fi

sudo tee /etc/systemd/system/muta-package-watch.service >/dev/null <<EOF
[Unit]
Description=Muta desktop package commit watcher
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$builder_user
Environment=MUTA_PACKAGE_REPO=$repo
Environment=MUTA_PACKAGE_STATE_ROOT=$state_root
Environment=PATH=$builder_home/.local/bin:$builder_home/.cargo/bin:$gcloud_dir:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=$repo/scripts/gcp_package_watch.sh
EOF

sudo tee /etc/systemd/system/muta-package-watch.timer >/dev/null <<'EOF'
[Unit]
Description=Poll GitHub for new Muta package commits

[Timer]
OnBootSec=5min
OnUnitActiveSec=5min
RandomizedDelaySec=30s
Persistent=true

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now muta-package-watch.timer
systemctl list-timers muta-package-watch.timer --no-pager
