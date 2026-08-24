#!/usr/bin/env bash
# Idempotently provision Ubuntu 22.04 for cached Linux packaging and GCP coordination.
set -euo pipefail

builder_user="${MUTA_PACKAGE_BUILDER_USER:-$USER}"
builder_home="$(getent passwd "$builder_user" | cut -d: -f6)"
test -n "$builder_home"

sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  build-essential cmake ninja-build nasm pkg-config file git curl ca-certificates zstd \
  libwebkit2gtk-4.1-dev libayatana-appindicator3-dev librsvg2-dev \
  patchelf libssl-dev libasound2-dev libfuse2 python3-venv

node_version="22.22.0"
node_root="/opt/muta-package/node-v$node_version-linux-x64"
if [ ! -x "$node_root/bin/node" ]; then
  temporary="$(mktemp -d)"
  trap 'rm -rf "$temporary"' EXIT
  curl --fail --location --retry 3 \
    "https://nodejs.org/dist/v$node_version/node-v$node_version-linux-x64.tar.xz" \
    -o "$temporary/node.tar.xz"
  sudo mkdir -p /opt/muta-package
  sudo tar -xJf "$temporary/node.tar.xz" -C /opt/muta-package
fi
sudo ln -sfn "$node_root/bin/node" /usr/local/bin/node
sudo ln -sfn "$node_root/bin/npm" /usr/local/bin/npm
sudo ln -sfn "$node_root/bin/npx" /usr/local/bin/npx

sudo -u "$builder_user" env HOME="$builder_home" bash -lc '
  set -euo pipefail
  if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
  fi
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  uv python install 3.11
  if ! command -v rustup >/dev/null 2>&1; then
    curl --proto "=https" --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
  fi
  rustup toolchain install stable --profile minimal
  rustup default stable
'

echo "GCP Ubuntu package builder provisioned for $builder_user"
