#!/usr/bin/env bash
# Verify a built or restored desktop-native cache before it enters an application bundle.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$repo_root/scripts/desktop_native_pins.env"

output="${1:-$repo_root/desktop/build/native}"
target_arch="${MUTA_DESKTOP_TARGET_ARCH:-$(uname -m)}"
file_arch="$target_arch"
if [ "$(uname -s)" = "Darwin" ] && [ "$file_arch" = "aarch64" ]; then
  # Muta uses the cross-platform `aarch64` label; Apple's Mach-O tools report
  # the same architecture as `arm64`.
  file_arch="arm64"
fi
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) executable_suffix=.exe ;;
  *) executable_suffix= ;;
esac

llama="$output/llama-server$executable_suffix"
ffmpeg="$output/ffmpeg$executable_suffix"
versions="$output/VERSIONS.txt"
test -f "$llama"
test -f "$ffmpeg"
test -f "$versions"

expected_versions="$(mktemp)"
trap 'rm -f "$expected_versions"' EXIT
printf '%s\n' \
  "llama.cpp=$MUTA_LLAMA_LABEL/$MUTA_LLAMA_COMMIT" \
  "ffmpeg=$MUTA_FFMPEG_LABEL/$MUTA_FFMPEG_COMMIT" \
  > "$expected_versions"
diff -u "$expected_versions" "$versions"

assert_no_avx512() {
  local executable="$1"
  local disassembler=""
  if command -v llvm-objdump >/dev/null 2>&1; then
    disassembler="llvm-objdump"
  elif command -v objdump >/dev/null 2>&1; then
    disassembler="objdump"
  fi
  if [ -n "$disassembler" ] && "$disassembler" -d "$executable" 2>/dev/null \
      | grep -Eiq '(^|[^[:alnum:]_])(zmm[0-9]+|%k[1-7])([^[:alnum:]_]|$)'; then
    echo "AVX-512 instruction/register found in $executable" >&2
    exit 1
  fi
}

validate_native_binary() {
  local executable="$1"
  case "$(uname -s)" in
    Darwin)
      file "$executable" | grep -Eq "Mach-O.*$file_arch|Mach-O universal"
      otool -l "$executable" \
        | awk -v maximum="$MUTA_MACOS_DEPLOYMENT_TARGET" \
          '/minos/{ if ($2 + 0 > maximum + 0) { print "minimum macOS is too new: " $2 > "/dev/stderr"; exit 1 } }'
      if otool -L "$executable" | grep -Eq '/(opt/homebrew|usr/local)/'; then
        echo "non-system package-manager dependency found in $executable" >&2
        exit 1
      fi
      ;;
    Linux)
      file "$executable" | grep -q 'ELF 64-bit.*x86-64'
      assert_no_avx512 "$executable"
      ;;
    MINGW*|MSYS*|CYGWIN*)
      file "$executable" | grep -Eq 'PE32\+.*x86-64'
      assert_no_avx512 "$executable"
      if objdump -p "$executable" 2>/dev/null \
          | grep -Eiq 'DLL Name:.*(libgcc|libstdc\+\+|libwinpthread|msys-2)'; then
        echo "non-system MinGW/MSYS runtime dependency found in $executable" >&2
        exit 1
      fi
      ;;
    *)
      echo "unsupported native verification host: $(uname -s)" >&2
      exit 1
      ;;
  esac
}

validate_native_binary "$llama"
validate_native_binary "$ffmpeg"
echo "verified desktop-native cache: $output"
