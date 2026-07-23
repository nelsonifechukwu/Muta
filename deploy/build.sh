#!/usr/bin/env bash
# Build inference engine variant A from the pinned tree (TDD T1, §6.1).
#
#   deploy/build.sh [--src /path/to/llama.cpp] [--out dist/bin]
#
# Refuses to build anything but the pinned commit: an unpinned binary cannot be reproduced
# on 9 Aug, and the whole point of the lock is that "it worked on my machine" is not a
# defence when the machine is a judge's laptop.
#
# Two assertions run after the compile and both are hard failures, because an
# illegal-instruction fault on the target is a disqualification, not a slow score:
#   1. the binary is x86-64 ELF
#   2. the disassembly contains no AVX-512 mnemonics
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK="$REPO_ROOT/deploy/versions.lock"
SRC=""
OUT="$REPO_ROOT/dist/bin"
SKIP_ISA_CHECK="${SKIP_ISA_CHECK:-0}"

while [ $# -gt 0 ]; do
  case "$1" in
    --src) SRC="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --skip-isa-check) SKIP_ISA_CHECK=1; shift ;;
    -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

# shellcheck disable=SC1090
. "$LOCK"

: "${LLAMA_CPP_REF:?LLAMA_CPP_REF unset in versions.lock}"
SRC="${SRC:-$REPO_ROOT/.build/llama.cpp}"

if [ ! -d "$SRC/.git" ]; then
  echo "==> cloning ${LLAMA_CPP_REPO} @ ${LLAMA_CPP_REF}"
  git clone --depth 1 --branch "$LLAMA_CPP_REF" "$LLAMA_CPP_REPO" "$SRC"
fi

ACTUAL="$(git -C "$SRC" describe --tags --always)"
python3 -m bundle.versions check LLAMA_CPP_REF "$ACTUAL" --lock "$LOCK" \
  || { echo "FATAL: source tree is not the pinned commit" >&2; exit 1; }

echo "==> configuring (flags from versions.lock)"
# shellcheck disable=SC2086
cmake -S "$SRC" -B "$SRC/build" $LLAMA_BUILD_FLAGS

echo "==> building: $LLAMA_BUILD_TARGETS"
# shellcheck disable=SC2086
cmake --build "$SRC/build" -j "$(getconf _NPROCESSORS_ONLN)" \
  $(for t in $LLAMA_BUILD_TARGETS; do printf -- '--target %s ' "$t"; done)

mkdir -p "$OUT"
for t in $LLAMA_BUILD_TARGETS; do
  cp "$SRC/build/bin/$t" "$OUT/"
done
# The core binary ships under its own name so earlyoom's --avoid pattern can single it out
# without also protecting llama-bench (TDD §5.4).
cp "$OUT/llama-server" "$OUT/llama-server-core"

if [ "$SKIP_ISA_CHECK" = "1" ]; then
  echo "!! ISA assertions skipped (SKIP_ISA_CHECK=1) — never do this for a shipping bundle"
  exit 0
fi

echo "==> asserting ISA (DQ guard, TDD C-1)"
file "$OUT/llama-server" | grep -q 'ELF 64-bit LSB.*x86-64' \
  || { echo "FATAL: llama-server is not x86-64 ELF" >&2; exit 1; }
if objdump -d "$OUT/llama-server" | grep -qE '\s(vpxord|vpternlogd|kmovw|vpbroadcastmw2d)\s'; then
  echo "FATAL: AVX-512 instructions found in llama-server" >&2
  exit 1
fi

"$OUT/llama-server" --version 2>&1 | head -3
echo "==> ok: variant A built at $OUT (pin $LLAMA_CPP_REF)"
