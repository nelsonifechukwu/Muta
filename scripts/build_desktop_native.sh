#!/usr/bin/env bash
# Build release-native llama.cpp and a self-contained FFmpeg command on the current runner.
# Called from the per-OS CI matrix. macOS may additionally target Intel from Apple Silicon;
# other operating systems still build on their destination OS.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
output="${1:-$repo_root/desktop/build/native}"
work="${MUTA_NATIVE_WORK:-$repo_root/desktop/build/native-work}"
llama_commit="602f828b4d93a2fefdd546145d9e761825f3bd11"
ffmpeg_commit="db69d06eeeab4f46da15030a80d539efb4503ca8"
target_arch="${MUTA_DESKTOP_TARGET_ARCH:-$(uname -m)}"

mkdir -p "$output" "$work"

llama_src="$work/llama.cpp"
if [ ! -d "$llama_src/.git" ]; then
  git clone --filter=blob:none https://github.com/ggml-org/llama.cpp.git "$llama_src"
fi
git -C "$llama_src" fetch --depth 1 origin "$llama_commit"
git -C "$llama_src" checkout --detach FETCH_HEAD
test "$(git -C "$llama_src" rev-parse HEAD)" = "$llama_commit"

rm -rf "$work/llama-build"

cmake_args=(
  -S "$llama_src" -B "$work/llama-build"
  -DCMAKE_BUILD_TYPE=Release
  -DGGML_NATIVE=OFF
  -DGGML_AVX512=OFF
  # llama.cpp's own thread pool is sufficient and avoids a libgomp/libomp runtime that may
  # not exist on a clean target machine.
  -DGGML_OPENMP=OFF
  -DLLAMA_CURL=OFF
  -DLLAMA_BUILD_TESTS=OFF
  -DLLAMA_BUILD_EXAMPLES=OFF
  -DLLAMA_BUILD_APP=OFF
  -DLLAMA_BUILD_SERVER=ON
  -DLLAMA_BUILD_UI=OFF
  -DLLAMA_USE_PREBUILT_UI=OFF
  -DLLAMA_OPENSSL=OFF
  -DBUILD_SHARED_LIBS=OFF
)
case "$(uname -s)" in
  Darwin)
    cmake_args+=(
      -DCMAKE_OSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-12.0}"
      -DCMAKE_OSX_ARCHITECTURES="$target_arch"
      -DGGML_METAL=ON
      # Current Accelerate headers route cblas_sgemm through a macOS 13.3 symbol even when
      # the deployment target is 12. Keep the documented macOS 12 baseline and use ggml's
      # native CPU/Metal kernels instead of shipping a binary that can fail on 12.x.
      -DGGML_BLAS=OFF
    )
    if [ "$target_arch" = "x86_64" ]; then
      cmake_args+=(
        -DGGML_AVX2=ON
        -DGGML_F16C=ON
        -DGGML_FMA=ON
      )
    fi
    ;;
  Linux)
    cmake_args+=(
      -DGGML_AVX2=ON
      -DGGML_F16C=ON
      -DGGML_FMA=ON
      -DGGML_CUDA=OFF
    )
    ;;
  MINGW*|MSYS*|CYGWIN*)
    cmake_args+=(
      -G Ninja
      -DGGML_AVX2=ON
      -DGGML_F16C=ON
      -DGGML_FMA=ON
      -DGGML_CUDA=OFF
      -DCMAKE_EXE_LINKER_FLAGS=-static
    )
    ;;
  *) echo "unsupported native build host: $(uname -s)" >&2; exit 1 ;;
esac
cmake "${cmake_args[@]}"
cmake --build "$work/llama-build" --config Release --parallel --target llama-server

llama_binary="$(find "$work/llama-build/bin" -type f \( -name llama-server -o -name llama-server.exe \) -print -quit)"
test -n "$llama_binary"
cp "$llama_binary" "$output/"

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
      file "$executable" | grep -Eq "Mach-O.*$target_arch|Mach-O universal"
      # A developer download built for a future macOS must never slip into a release.
      otool -l "$executable" \
        | awk '/minos/{ if ($2 + 0 > 12.0) { print "minimum macOS is too new: " $2 > "/dev/stderr"; exit 1 } }'
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
  esac
}

validate_native_binary "$output/$(basename "$llama_binary")"

ffmpeg_src="$work/ffmpeg"
if [ ! -d "$ffmpeg_src/.git" ]; then
  git clone --filter=blob:none https://git.ffmpeg.org/ffmpeg.git "$ffmpeg_src"
fi
git -C "$ffmpeg_src" fetch --depth 1 origin "$ffmpeg_commit"
git -C "$ffmpeg_src" checkout --detach FETCH_HEAD
test "$(git -C "$ffmpeg_src" rev-parse HEAD)" = "$ffmpeg_commit"

ffmpeg_prefix="$work/ffmpeg-install"
rm -rf "$work/ffmpeg-build" "$ffmpeg_prefix"
mkdir -p "$work/ffmpeg-build" "$ffmpeg_prefix"
ffmpeg_target_args=()
if [ "$(uname -s)" = "Darwin" ] && [ "$target_arch" != "$(uname -m)" ]; then
  ffmpeg_target_args=(
    --arch="$target_arch"
    --cc="clang -arch $target_arch"
    --extra-cflags="-mmacosx-version-min=${MACOSX_DEPLOYMENT_TARGET:-12.0}"
    --extra-ldflags="-mmacosx-version-min=${MACOSX_DEPLOYMENT_TARGET:-12.0}"
  )
fi
(
  cd "$work/ffmpeg-build"
  "$ffmpeg_src/configure" \
    --prefix="$ffmpeg_prefix" \
    --disable-doc \
    --disable-debug \
    --disable-network \
    --disable-avx512 \
    --disable-avx512icl \
    --disable-shared \
    --enable-static \
    --disable-autodetect \
    --disable-ffplay \
    --disable-ffprobe \
    --enable-ffmpeg \
    --enable-small \
    "${ffmpeg_target_args[@]}"
  make -j "${NUMBER_OF_PROCESSORS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || sysctl -n hw.ncpu)}"
  make install
)
ffmpeg_binary="$(find "$ffmpeg_prefix/bin" -maxdepth 1 -type f \( -name ffmpeg -o -name ffmpeg.exe \) -print -quit)"
test -n "$ffmpeg_binary"
cp "$ffmpeg_binary" "$output/"
validate_native_binary "$output/$(basename "$ffmpeg_binary")"

printf '%s\n' "llama.cpp=b10035/$llama_commit" "ffmpeg=n7.1.1/$ffmpeg_commit" > "$output/VERSIONS.txt"
