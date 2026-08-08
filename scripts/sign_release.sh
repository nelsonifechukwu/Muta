#!/usr/bin/env bash
# Muta — sign an offline update release (run on a TRUSTED build machine, offline is fine).
#
#   scripts/sign_release.sh [--key KEYFILE] [--tool auto|minisign|openssl] RELEASE_DIR
#
# A release is a directory holding the prebuilt image tarballs (`docker save`) plus the
# models manifest — everything a target laptop needs to update WITHOUT recompiling
# llama.cpp on-device (which the current `run.sh update` does; ~30 min per box — see
# docs/offline-updates.md for why that is wrong for a fleet).
#
# This produces, inside RELEASE_DIR:
#   SHA256SUMS         a sha256 line for every file in the release (the manifest).
#   SHA256SUMS.sig     a detached signature over that manifest (openssl Ed25519/RSA), OR
#   SHA256SUMS.minisig if minisign is used.
#
# Signing the manifest, and the manifest committing to every file's hash, is the same
# "verify twice" discipline the model provenance uses (models/pins.lock.json): one
# signature authenticates the list, the list authenticates the bytes.
#
# Keys: default keys/muta_release_ed25519.key (+ .pub), generated here if absent.
#   >>> The PRIVATE key must stay on the trusted machine and NEVER ride the flash drive. <<<
#   The PUBLIC key (.pub) is the trust anchor: install it once on every target, out of band
#   (like rootCA.pem). verify_release.sh takes it as an explicit argument.
#
# Exit: 0 signed · 2 usage · 3 tool/key error.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
info() { printf '\033[36m▸\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31m✗\033[0m %s\n' "$*" >&2; exit "${2:-1}"; }

usage() { sed -n '2,25p' "$0"; }

# sha256 helper: coreutils on the Linux target, shasum on a macOS build box. Both share
# the `<hash>  <path>` format and a `-c` check mode.
_sha256() {
    if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@"
    else shasum -a 256 "$@"; fi
}
# Print ED25519 or RSA for a private key (chooses the openssl signing path).
key_alg() {
    case "$(openssl pkey -in "$1" -noout -text 2>/dev/null | head -1)" in
        *ED25519*) echo ED25519 ;;
        *)         echo RSA ;;
    esac
}

KEY="$REPO_ROOT/keys/muta_release_ed25519.key"
TOOL="auto"
RELEASE=""
while [ $# -gt 0 ]; do
    case "$1" in
        --key)    [ $# -ge 2 ] || die "--key needs a path" 2; KEY="$2"; shift ;;
        --key=*)  KEY="${1#--key=}" ;;
        --tool)   [ $# -ge 2 ] || die "--tool needs a value" 2; TOOL="$2"; shift ;;
        --tool=*) TOOL="${1#--tool=}" ;;
        -h|--help) usage; exit 0 ;;
        -*)       die "unknown option: $1  (try --help)" 2 ;;
        *)        [ -z "$RELEASE" ] || die "only one RELEASE_DIR (got '$RELEASE' and '$1')" 2
                  RELEASE="$1" ;;
    esac
    shift
done

[ -n "$RELEASE" ] || die "no RELEASE_DIR given  (try --help)" 2
[ -d "$RELEASE" ] || die "not a directory: $RELEASE" 2
RELEASE="$(cd "$RELEASE" && pwd)"

# Refuse to sign an empty release — an empty manifest signs cleanly and means nothing.
if [ -z "$(find "$RELEASE" -type f \
        ! -name SHA256SUMS ! -name 'SHA256SUMS.sig' ! -name 'SHA256SUMS.minisig' -print -quit)" ]; then
    die "release directory is empty (no files to sign): $RELEASE" 2
fi

# --- pick the signing tool ------------------------------------------------------------
if [ "$TOOL" = auto ]; then
    if command -v minisign >/dev/null 2>&1; then TOOL=minisign; else TOOL=openssl; fi
fi
case "$TOOL" in
    minisign) command -v minisign >/dev/null 2>&1 || die "minisign requested but not installed" 3 ;;
    openssl)  command -v openssl  >/dev/null 2>&1 || die "openssl not found" 3 ;;
    *)        die "unknown --tool: $TOOL (minisign|openssl|auto)" 2 ;;
esac
info "signing tool: $TOOL"

# --- ensure a keypair exists ----------------------------------------------------------
PUB=""
if [ "$TOOL" = minisign ]; then
    # minisign default key names; generate if absent.
    [ "$KEY" = "$REPO_ROOT/keys/muta_release_ed25519.key" ] && KEY="$REPO_ROOT/keys/minisign.key"
    PUB="${KEY%.key}.pub"
    if [ ! -f "$KEY" ]; then
        mkdir -p "$(dirname "$KEY")"; chmod 700 "$(dirname "$KEY")"
        warn "no minisign key at $KEY — generating one (you will be asked for a password)."
        minisign -G -s "$KEY" -p "$PUB" || die "minisign key generation failed" 3
    fi
else
    PUB="${KEY%.key}.pub"
    if [ ! -f "$KEY" ]; then
        mkdir -p "$(dirname "$KEY")"; chmod 700 "$(dirname "$KEY")"
        info "no signing key at $KEY — generating an Ed25519 keypair."
        openssl genpkey -algorithm ED25519 -out "$KEY" >/dev/null 2>&1 || die "key generation failed" 3
        chmod 600 "$KEY"
        openssl pkey -in "$KEY" -pubout -out "$PUB" >/dev/null 2>&1 || die "public key export failed" 3
        warn "generated a NEW private key: $KEY"
        warn "  keep it on THIS machine only; it must never be on the flash drive."
    elif [ ! -f "$PUB" ]; then
        openssl pkey -in "$KEY" -pubout -out "$PUB" >/dev/null 2>&1 || die "public key export failed" 3
    fi
fi
# Keep private keys out of git regardless of the repo root .gitignore; allow the .pub.
KEYDIR="$(cd "$(dirname "$KEY")" && pwd)"
[ -f "$KEYDIR/.gitignore" ] || printf '*\n!.gitignore\n!*.pub\n' > "$KEYDIR/.gitignore"

# --- build the manifest (relative paths, deterministic order) -------------------------
info "hashing $(find "$RELEASE" -type f ! -name SHA256SUMS ! -name 'SHA256SUMS.sig' ! -name 'SHA256SUMS.minisig' | wc -l | tr -d ' ') file(s)"
MAN_TMP="$(mktemp)"
(
    cd "$RELEASE"
    find . -type f \
        ! -name SHA256SUMS ! -name 'SHA256SUMS.sig' ! -name 'SHA256SUMS.minisig' \
        -print0 | LC_ALL=C sort -z | while IFS= read -r -d '' f; do
        _sha256 "$f"
    done
) > "$MAN_TMP"
mv "$MAN_TMP" "$RELEASE/SHA256SUMS"

# --- sign the manifest ----------------------------------------------------------------
rm -f "$RELEASE/SHA256SUMS.sig" "$RELEASE/SHA256SUMS.minisig"
if [ "$TOOL" = minisign ]; then
    minisign -Sm "$RELEASE/SHA256SUMS" -s "$KEY" \
        -c "Muta offline release $(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        || die "minisign signing failed" 3
    SIG="$RELEASE/SHA256SUMS.minisig"
else
    ALG="$(key_alg "$KEY")"
    info "openssl signing algorithm: $ALG"
    if [ "$ALG" = ED25519 ]; then
        openssl pkeyutl -sign -inkey "$KEY" -rawin \
            -in "$RELEASE/SHA256SUMS" -out "$RELEASE/SHA256SUMS.sig" \
            || die "openssl Ed25519 signing failed" 3
    else
        openssl dgst -sha256 -sign "$KEY" \
            -out "$RELEASE/SHA256SUMS.sig" "$RELEASE/SHA256SUMS" \
            || die "openssl RSA signing failed" 3
    fi
    SIG="$RELEASE/SHA256SUMS.sig"
fi

PUBFPR="$(_sha256 "$PUB" | awk '{print $1}')"

echo
bold "Release signed."
info "  manifest:   $RELEASE/SHA256SUMS"
info "  signature:  $SIG"
info "  public key: $PUB"
info "  public key sha256: $PUBFPR"
echo
bold "Distribute to each target ONCE, out of band (not on the release flash drive):"
info "  $PUB"
info "Then on the target, before applying the update:"
info "  scripts/verify_release.sh --pubkey <that .pub> $RELEASE"
echo
warn "The PRIVATE key ($KEY) stays here. Never copy it to the flash drive or a target."
