#!/usr/bin/env bash
# Muta — verify an offline update release BEFORE applying it (run this on the target box).
#
#   scripts/verify_release.sh --pubkey PUBKEY [--tool auto|minisign|openssl] RELEASE_DIR
#
# This is the gate a classroom laptop runs before loading any images or swapping any tag.
# NEVER apply an update that this does not pass. It checks two independent things
# ("verify twice", like the model-provenance sha256 discipline):
#
#   1. the detached signature over SHA256SUMS is valid for the PRE-SHARED public key, and
#   2. every sha256 in SHA256SUMS matches the file on disk, with no extra/missing files.
#
# The public key MUST be the one you installed on this device out of band (like rootCA.pem)
# — NOT a copy pulled from the release itself. A release carries its signature; it cannot
# carry its own trust anchor. That is why --pubkey is a required, explicit argument.
#
# Exit: 0 all good (safe to apply) · 1 bad signature · 2 hash/manifest mismatch
#       · 3 tool/setup error · 4 usage.
set -euo pipefail

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
info() { printf '\033[36m▸\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31m✗\033[0m %s\n' "$*" >&2; exit "${2:-1}"; }

usage() { sed -n '2,18p' "$0"; }

_sha256() {
    if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@"
    else shasum -a 256 "$@"; fi
}
pub_alg() {
    case "$(openssl pkey -pubin -in "$1" -noout -text 2>/dev/null | head -1)" in
        *ED25519*) echo ED25519 ;;
        *)         echo RSA ;;
    esac
}

PUB=""
TOOL="auto"
RELEASE=""
while [ $# -gt 0 ]; do
    case "$1" in
        --pubkey)   [ $# -ge 2 ] || die "--pubkey needs a path" 4; PUB="$2"; shift ;;
        --pubkey=*) PUB="${1#--pubkey=}" ;;
        --tool)     [ $# -ge 2 ] || die "--tool needs a value" 4; TOOL="$2"; shift ;;
        --tool=*)   TOOL="${1#--tool=}" ;;
        -h|--help)  usage; exit 0 ;;
        -*)         die "unknown option: $1  (try --help)" 4 ;;
        *)          [ -z "$RELEASE" ] || die "only one RELEASE_DIR (got '$RELEASE' and '$1')" 4
                    RELEASE="$1" ;;
    esac
    shift
done

[ -n "$RELEASE" ] || die "no RELEASE_DIR given  (try --help)" 4
[ -d "$RELEASE" ] || die "not a directory: $RELEASE" 4
[ -n "$PUB" ]     || die "no --pubkey given — the pre-shared trust anchor is required" 4
[ -f "$PUB" ]     || die "public key not found: $PUB" 4
RELEASE="$(cd "$RELEASE" && pwd)"

MAN="$RELEASE/SHA256SUMS"
[ -f "$MAN" ] || die "no SHA256SUMS manifest in $RELEASE — is this a signed release?" 2

# --- locate the signature and pick the verify tool ------------------------------------
if [ "$TOOL" = auto ]; then
    if   [ -f "$RELEASE/SHA256SUMS.minisig" ]; then TOOL=minisign
    elif [ -f "$RELEASE/SHA256SUMS.sig" ];     then TOOL=openssl
    else die "no signature file (SHA256SUMS.sig or SHA256SUMS.minisig) in $RELEASE" 1
    fi
fi
case "$TOOL" in
    minisign) SIG="$RELEASE/SHA256SUMS.minisig"
              command -v minisign >/dev/null 2>&1 || die "signature is minisign but minisign is not installed" 3 ;;
    openssl)  SIG="$RELEASE/SHA256SUMS.sig"
              command -v openssl  >/dev/null 2>&1 || die "openssl not found" 3 ;;
    *)        die "unknown --tool: $TOOL" 4 ;;
esac
[ -f "$SIG" ] || die "expected signature not found: $SIG" 1
info "release:    $RELEASE"
info "public key: $PUB"
info "signature:  $SIG ($TOOL)"

# --- check 1: signature over the manifest ---------------------------------------------
info "check 1/2: signature over SHA256SUMS"
sig_ok=0
if [ "$TOOL" = minisign ]; then
    if minisign -Vm "$MAN" -p "$PUB" -x "$SIG" >/dev/null 2>&1; then sig_ok=1; fi
else
    ALG="$(pub_alg "$PUB")"
    if [ "$ALG" = ED25519 ]; then
        if openssl pkeyutl -verify -pubin -inkey "$PUB" -rawin \
                -in "$MAN" -sigfile "$SIG" >/dev/null 2>&1; then sig_ok=1; fi
    else
        if openssl dgst -sha256 -verify "$PUB" -signature "$SIG" "$MAN" >/dev/null 2>&1; then sig_ok=1; fi
    fi
fi
if [ "$sig_ok" != 1 ]; then
    die "SIGNATURE INVALID — the manifest is not signed by this key. DO NOT APPLY THIS UPDATE." 1
fi
info "  signature OK — manifest is authentic"

# --- check 2: every hash matches, and no unexpected files -----------------------------
info "check 2/2: file hashes match the manifest"
check_out="$(cd "$RELEASE" && _sha256 -c SHA256SUMS 2>&1)" && hashes_ok=1 || hashes_ok=0
if [ "$hashes_ok" != 1 ]; then
    warn "hash check FAILED for:"
    printf '%s\n' "$check_out" | grep -v ': OK$' >&2 || true
    die "FILE HASH MISMATCH — the release has been altered. DO NOT APPLY THIS UPDATE." 2
fi

# Catch files that were ADDED after signing (not covered by -c, which only checks the list).
listed="$(sed -E 's/^[0-9a-fA-F]{64} [ *]//' "$MAN" | LC_ALL=C sort)"
present="$(cd "$RELEASE" && find . -type f \
    ! -name SHA256SUMS ! -name 'SHA256SUMS.sig' ! -name 'SHA256SUMS.minisig' | LC_ALL=C sort)"
if [ "$listed" != "$present" ]; then
    warn "the set of files on disk does not match the signed manifest:"
    printf '%s\n' "$(comm -3 <(printf '%s\n' "$listed") <(printf '%s\n' "$present"))" >&2
    die "UNEXPECTED OR MISSING FILES — the release does not match its manifest. DO NOT APPLY." 2
fi
info "  all hashes match; no extra or missing files"

echo
bold "✓ RELEASE VERIFIED — signature valid and every file matches. Safe to apply."
exit 0
