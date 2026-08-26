#!/usr/bin/env bash
# Run on the operator laptop. The phone reaches this laptop's Wi-Fi address; SSH carries the
# encrypted bytes to Muta's dedicated learner listener on GCP. No GCP firewall port is opened.

# A caller may invoke this with ``bash -x``. Disable tracing before reading the secret env value.
set +x
set -euo pipefail

VM="${MUTA_GCP_VM:-muta-vm}"
ZONE="${MUTA_GCP_ZONE:-us-west1-b}"
PROJECT="${MUTA_GCP_PROJECT:-}"
OPERATOR_PORT="${MUTA_GCP_OPERATOR_PORT:-18001}"
SHARE_PORT="${MUTA_GCP_SHARE_PORT:-8443}"
LAN_IP="${MUTA_GCP_LAN_IP:-}"
FLEET_URL="${MUTA_FLEET_URL:-}"
FLEET_INGEST_KEY="${MUTA_FLEET_INGEST_KEY:-}"
# Do not let the inherited secret remain in gcloud's environment. When enabled it is delivered
# to the remote launcher over SSH stdin, never as a process argument or dry-run output.
unset MUTA_FLEET_INGEST_KEY
DRY_RUN=0

usage() {
    cat <<'EOF'
Usage: ./scripts/gcp_share_relay.sh [--dry-run]

Run this on the laptop that shares Wi-Fi with the learner phones. It launches native Muta on
GCP and creates two SSH forwards:

  operator:  127.0.0.1:18001       -> GCP 127.0.0.1:8000
  learners:  <laptop LAN IP>:8443  -> GCP 127.0.0.1:8443

Environment overrides:
  MUTA_GCP_LAN_IP, MUTA_GCP_VM, MUTA_GCP_ZONE, MUTA_GCP_PROJECT,
  MUTA_GCP_OPERATOR_PORT, MUTA_GCP_SHARE_PORT

Optional fleet heartbeat (both values are required together):
  MUTA_FLEET_URL, MUTA_FLEET_INGEST_KEY

Stop an older GCP Muta SSH launch first. Ctrl-C stops this launch and both forwards.
EOF
}

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'unknown argument: %s\n' "$arg" >&2; usage >&2; exit 2 ;;
    esac
done

# This launcher is the bridge between a learner LAN and GCP. Running it inside the VM would
# advertise Google's private VPC address and then ask gcloud to SSH from the VM back into itself.
product_name_file="${MUTA_GCP_RELAY_PRODUCT_NAME_FILE:-/sys/class/dmi/id/product_name}"
if [ -r "$product_name_file" ] && grep -qi 'Google Compute Engine' "$product_name_file"; then
    printf '%s\n' \
        'gcp_share_relay.sh must run on the operator laptop, not inside muta-vm.' \
        'Exit this SSH session, open a terminal on the laptop, and run it from the Muta folder.' >&2
    exit 1
fi

detect_lan_ip() {
    if [ "$(uname -s)" = "Darwin" ]; then
        interface=$(route -n get default 2>/dev/null | awk '/interface:/ {print $2; exit}')
        [ -n "$interface" ] && ipconfig getifaddr "$interface" 2>/dev/null || true
        return
    fi
    if command -v ip >/dev/null 2>&1; then
        ip route get 192.0.2.1 2>/dev/null \
            | awk '{for (i=1; i<=NF; i++) if ($i == "src") {print $(i+1); exit}}'
    fi
}

[ -n "$LAN_IP" ] || LAN_IP=$(detect_lan_ip)
[ -n "$LAN_IP" ] || {
    printf 'could not detect the laptop LAN IPv4; set MUTA_GCP_LAN_IP explicitly\n' >&2
    exit 1
}

if [ -n "$FLEET_URL" ] && [ -z "$FLEET_INGEST_KEY" ]; then
    printf 'MUTA_FLEET_INGEST_KEY is required when MUTA_FLEET_URL is set\n' >&2
    exit 1
fi
if [ -n "$FLEET_INGEST_KEY" ] && [ -z "$FLEET_URL" ]; then
    printf 'MUTA_FLEET_URL is required when MUTA_FLEET_INGEST_KEY is set\n' >&2
    exit 1
fi

python3 - "$LAN_IP" "$OPERATOR_PORT" "$SHARE_PORT" "$FLEET_URL" <<'PY'
import ipaddress
import sys
from urllib.parse import urlsplit

address = ipaddress.ip_address(sys.argv[1])
if address.version != 4 or address.is_loopback or address.is_link_local or address.is_unspecified:
    raise SystemExit("MUTA_GCP_LAN_IP must be a usable non-loopback IPv4 address")
for raw in sys.argv[2:4]:
    port = int(raw)
    if not 1024 <= port <= 65535:
        raise SystemExit("relay ports must be between 1024 and 65535")

fleet_url = sys.argv[4]
if fleet_url:
    parsed = urlsplit(fleet_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise SystemExit("MUTA_FLEET_URL must be an HTTPS origin without embedded credentials")
PY

operator_forward="127.0.0.1:${OPERATOR_PORT}:127.0.0.1:8000"
learner_forward="${LAN_IP}:${SHARE_PORT}:127.0.0.1:${SHARE_PORT}"
remote_command="cd ~/Muta && exec env MUTA_SHARE_HOST=${LAN_IP} MUTA_SHARE_PORT=${SHARE_PORT} ./run.sh --native-linux"
fleet_enabled=0
if [ -n "$FLEET_URL" ]; then
    fleet_enabled=1
    printf -v fleet_url_quoted '%q' "$FLEET_URL"
    remote_command="cd ~/Muta && IFS= read -r fleet_ingest_key && exec env MUTA_SHARE_HOST=${LAN_IP} MUTA_SHARE_PORT=${SHARE_PORT} MUTA_FLEET_URL=${fleet_url_quoted} MUTA_FLEET_INGEST_KEY=\"\$fleet_ingest_key\" ./run.sh --native-linux"
fi
command=(gcloud compute ssh "$VM" "--zone=$ZONE")
[ -z "$PROJECT" ] || command+=("--project=$PROJECT")
command+=(-- -T -o BatchMode=yes -o ExitOnForwardFailure=yes -L "$operator_forward" -L "$learner_forward" -- "$remote_command")

printf 'Muta operator: http://127.0.0.1:%s/chat/\n' "$OPERATOR_PORT"
printf 'Learner relay: https://%s:%s/chat/\n' "$LAN_IP" "$SHARE_PORT"
printf 'GCP ports remain private; learner traffic crosses the authenticated SSH tunnel.\n'
if [ "$fleet_enabled" -eq 1 ]; then
    printf 'Fleet heartbeat: enabled; the operator consent choice still controls delivery.\n'
fi

if [ "$DRY_RUN" -eq 1 ]; then
    printf 'Command:'
    printf ' %q' "${command[@]}"
    printf '\n'
    exit 0
fi

command -v gcloud >/dev/null 2>&1 || {
    printf 'gcloud is required; install the Google Cloud CLI first\n' >&2
    exit 1
}

# Fail before SSH prints an opaque forwarding error. Binding the LAN address—not 0.0.0.0—keeps
# the learner relay off unrelated VPN/virtual interfaces.
python3 - "$LAN_IP" "$OPERATOR_PORT" "$SHARE_PORT" <<'PY'
import socket
import sys

targets = (("127.0.0.1", int(sys.argv[2]), "operator"), (sys.argv[1], int(sys.argv[3]), "learner"))
for host, port, label in targets:
    sock = socket.socket()
    # A just-closed SSH tunnel can leave accepted connections in TIME_WAIT. That does not mean
    # another process owns the listener; SO_REUSEADDR matches OpenSSH's safe restart behaviour.
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
    except OSError as exc:
        raise SystemExit(
            f"{label} relay {host}:{port} is already occupied; stop the old GCP launch first: {exc}"
        ) from exc
    finally:
        sock.close()
PY

if [ "$fleet_enabled" -eq 1 ]; then
    # Establish gcloud/SSH credentials before the key ever reaches stdin. ``--quiet`` and
    # BatchMode make a first-run prompt fail safely instead of consuming the heartbeat key.
    preflight=(gcloud compute ssh "$VM" "--zone=$ZONE" --quiet --command=true)
    [ -z "$PROJECT" ] || preflight+=("--project=$PROJECT")
    preflight+=(-- -o BatchMode=yes)
    "${preflight[@]}" </dev/null >/dev/null
    exec "${command[@]}" <<<"$FLEET_INGEST_KEY"
fi
exec "${command[@]}"
