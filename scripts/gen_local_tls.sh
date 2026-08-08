#!/usr/bin/env bash
# Muta — generate a LOCAL certificate authority + a LAN server cert, fully offline.
#
#   scripts/gen_local_tls.sh [--out DIR] [--force] [HOST ...]
#
# Why this exists: the mic (getUserMedia) and the voice WebSocket need a SECURE CONTEXT.
# Browsers treat http://localhost as secure but NOT http://<lan-ip>, so on the classroom
# LAN the flagship voice loop is dead on plain :80 for every device that is not the host.
# A locally-trusted TLS cert fixes it with NO public CA and NO network (docs/tls-lan.md).
#
# What it produces (into ./certs, or --out DIR):
#   rootCA.pem   — the local CA certificate. INSTALL THIS on every student device (once).
#   rootCA.key   — the CA private key. Signs new server certs. Keep it safe; do NOT ship it.
#   fullchain.pem + privkey.pem — the server cert + key. Mount into the frontend container
#                  at /etc/nginx/certs/ (matches docker/nginx.conf.template's 443 block).
#
# SANs always include localhost, 127.0.0.1 and ::1. Pass the classroom laptop's LAN IP and
# any hostnames as arguments — modern browsers validate the SAN, never the CN:
#   scripts/gen_local_tls.sh 192.168.1.50 tutor.local
#
# Idempotent-ish: an existing CA is REUSED to re-issue the server cert (so you can add a new
# laptop IP without re-trusting the CA on every device). --force recreates the CA from
# scratch — which invalidates trust on every device that already installed the old one.
#
# Exit: 0 ok · 1 openssl/verify failure · 2 usage.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
info() { printf '\033[36m▸\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31m✗\033[0m %s\n' "$*" >&2; exit "${2:-1}"; }

usage() { sed -n '2,25p' "$0"; }

# --- args -----------------------------------------------------------------------------
FORCE=0
CERT_DIR="$REPO_ROOT/certs"
HOSTS=""
while [ $# -gt 0 ]; do
    case "$1" in
        --force)   FORCE=1 ;;
        --out)     [ $# -ge 2 ] || die "--out needs a directory" 2; CERT_DIR="$2"; shift ;;
        --out=*)   CERT_DIR="${1#--out=}" ;;
        -h|--help) usage; exit 0 ;;
        -*)        die "unknown option: $1  (try --help)" 2 ;;
        *)         HOSTS="$HOSTS $1" ;;
    esac
    shift
done

command -v openssl >/dev/null 2>&1 || die "openssl not found — install it (Ubuntu: apt-get install openssl)"

# mkcert is an even simpler local-CA tool. If it is here, point at it — but this script
# stays on openssl because the classroom needs an EXPLICIT, portable rootCA.pem to hand to
# every device, which openssl emits directly (mkcert hides its CA under `mkcert -CAROOT`).
if command -v mkcert >/dev/null 2>&1; then
    info "mkcert detected. It auto-trusts on THIS machine, but student devices still need the CA installed by hand."
    info "  mkcert equivalent:  mkcert -install && mkcert -cert-file certs/fullchain.pem -key-file certs/privkey.pem localhost 127.0.0.1$HOSTS"
    info "  proceeding with openssl so you get a portable certs/rootCA.pem for the fleet."
fi

# --- classify the requested names into DNS vs IP SANs (bash 3.2-safe, no arrays) -------
is_ip() {
    case "$1" in
        *:*) return 0 ;;                                   # IPv6
    esac
    case "$1" in
        *[!0-9.]*) return 1 ;;                             # has a non-IPv4 char → hostname
    esac
    # four dotted octets
    printf '%s' "$1" | grep -Eq '^[0-9]{1,3}(\.[0-9]{1,3}){3}$'
}
contains() { local n="$1"; shift; local x; for x in "$@"; do [ "$x" = "$n" ] && return 0; done; return 1; }

DNS_SANS="localhost"
IP_SANS="127.0.0.1 ::1"
for a in $HOSTS; do
    if is_ip "$a"; then
        contains "$a" $IP_SANS  || IP_SANS="$IP_SANS $a"
    else
        contains "$a" $DNS_SANS || DNS_SANS="$DNS_SANS $a"
    fi
done
# CN is cosmetic (browsers ignore it) but set it to the first requested name for readability.
set -- $HOSTS
CN="${1:-localhost}"

mkdir -p "$CERT_DIR"
# Nothing under certs/ should ever be committed (private keys live here). A self-contained
# .gitignore keeps rootCA.key / privkey.pem out of git without touching the repo root file.
[ -f "$CERT_DIR/.gitignore" ] || printf '*\n!.gitignore\n' > "$CERT_DIR/.gitignore"

# --- decide whether to (re)create the CA ----------------------------------------------
CA_PEM="$CERT_DIR/rootCA.pem"
CA_KEY="$CERT_DIR/rootCA.key"
gen_ca=1
if [ -f "$CA_PEM" ] && [ -f "$CA_KEY" ]; then
    if [ "$FORCE" = 1 ]; then
        warn "--force: recreating the CA. Every device that trusts the OLD rootCA.pem must install the new one."
    else
        info "existing CA found in $CERT_DIR — reusing it; re-issuing only the server cert."
        gen_ca=0
    fi
elif { [ -f "$CA_PEM" ] || [ -f "$CA_KEY" ]; } && [ "$FORCE" != 1 ]; then
    die "incomplete CA in $CERT_DIR (need BOTH rootCA.pem and rootCA.key to re-issue). Pass --force to recreate."
fi

EXT="$(mktemp)"; CSR="$(mktemp)"
trap 'rm -f "$EXT" "$CSR"' EXIT

if [ "$gen_ca" = 1 ]; then
    info "generating local root CA (RSA-4096, 10-year) → rootCA.pem"
    # Self-signed CA. pathlen:0 => it can sign leaf certs but no sub-CAs.
    openssl req -x509 -newkey rsa:4096 -sha256 -days 3650 -nodes \
        -keyout "$CA_KEY" -out "$CA_PEM" \
        -subj "/O=Muta Local CA/CN=Muta Local Root CA" \
        -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
        -addext "keyUsage=critical,keyCertSign,cRLSign" \
        -addext "subjectKeyIdentifier=hash" \
        >/dev/null 2>&1 || die "CA generation failed"
    chmod 600 "$CA_KEY"
fi

# --- the SAN / usage extension file (heredoc, inline) ---------------------------------
{
    echo "basicConstraints = critical, CA:FALSE"
    echo "keyUsage = critical, digitalSignature, keyEncipherment"
    echo "extendedKeyUsage = serverAuth"
    echo "subjectKeyIdentifier = hash"
    echo "authorityKeyIdentifier = keyid:always"
    echo "subjectAltName = @alt_names"
    echo "[alt_names]"
    n=1; for d in $DNS_SANS; do echo "DNS.$n = $d"; n=$((n+1)); done
    n=1; for p in $IP_SANS;  do echo "IP.$n = $p";  n=$((n+1)); done
} > "$EXT"

info "issuing server cert (RSA-2048, 825-day) for: $DNS_SANS $IP_SANS"
# 825 days: Apple/Safari reject TLS *leaf* certs valid longer than this, even from a
# locally-trusted CA. The CA itself may be long-lived (10y above); the server cert may not.
openssl req -newkey rsa:2048 -sha256 -nodes \
    -keyout "$CERT_DIR/privkey.pem" -out "$CSR" \
    -subj "/O=Muta Local/CN=$CN" >/dev/null 2>&1 || die "server key/CSR generation failed"
chmod 600 "$CERT_DIR/privkey.pem"

openssl x509 -req -in "$CSR" \
    -CA "$CA_PEM" -CAkey "$CA_KEY" -CAcreateserial \
    -days 825 -sha256 -extfile "$EXT" \
    -out "$CERT_DIR/fullchain.pem" >/dev/null 2>&1 || die "signing the server cert failed"

# Verify the chain we just built before we tell anyone it works ("verify twice" discipline).
openssl verify -CAfile "$CA_PEM" "$CERT_DIR/fullchain.pem" >/dev/null 2>&1 \
    || die "the issued cert does not verify against its own CA — refusing to claim success"

FPR="$(openssl x509 -in "$CA_PEM" -noout -fingerprint -sha256 | sed 's/^.*=//')"

echo
bold "TLS material written to $CERT_DIR/"
info "  rootCA.pem     install on every student device (trust anchor)"
info "  fullchain.pem  server certificate  → /etc/nginx/certs/fullchain.pem"
info "  privkey.pem    server private key  → /etc/nginx/certs/privkey.pem  (mode 600)"
info "  rootCA.key     CA private key — keep OFF the flash drive; needed only to issue more certs"
echo
bold "Root CA SHA-256 fingerprint (compare this on each device after install):"
echo "  $FPR"
echo
bold "Next steps:"
echo "  1. Mount the certs into the frontend container. In docker-compose.yml, under the"
echo "     'frontend' service, add:"
echo "         volumes:"
echo "           - ./certs:/etc/nginx/certs:ro"
echo "  2. Enable TLS in nginx: uncomment the 'listen 443 ssl' block in"
echo "     docker/nginx.conf.template and redeploy (full steps in docs/tls-lan.md)."
echo "  3. Install certs/rootCA.pem on each classroom device ONCE — the per-OS/browser"
echo "     steps are in docs/tls-lan.md. Then https://<lan-ip>:3000 is a secure context"
echo "     and the mic + voice loop work over the LAN."
echo
warn "Never distribute rootCA.key or privkey.pem to devices — only rootCA.pem is installed."
