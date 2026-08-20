#!/usr/bin/env bash
set -euo pipefail

readonly UNIT="muta-gateway.service"
readonly -a PORTS=(8000 8080)

# Stop the persistent owner first so systemd cannot restart the processes while
# orphaned listeners are being cleared.
systemctl --user stop "$UNIT" 2>/dev/null || true

listener_pids() {
  local port="$1"
  ss -H -ltnp "sport = :${port}" 2>/dev/null \
    | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' \
    | sort -u
}

terminate_listener() {
  local pid="$1"
  local attempt

  kill -TERM "$pid" 2>/dev/null || true
  for attempt in {1..20}; do
    kill -0 "$pid" 2>/dev/null || return 0
    sleep 0.1
  done

  kill -KILL "$pid" 2>/dev/null || true
}

for port in "${PORTS[@]}"; do
  while IFS= read -r pid; do
    [[ -n "$pid" ]] && terminate_listener "$pid"
  done < <(listener_pids "$port")
done

for port in "${PORTS[@]}"; do
  if [[ -n "$(listener_pids "$port")" ]]; then
    echo "Could not clear port ${port}; inspect it with: ss -ltnp 'sport = :${port}'" >&2
    exit 1
  fi
done

echo "Muta gateway and llama-server stopped; ports 8000 and 8080 are free."
