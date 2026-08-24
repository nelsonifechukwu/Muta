#!/usr/bin/env bash
# Build release-native llama.cpp and a self-contained FFmpeg command on the current runner.
# Called from the per-OS CI matrix. macOS may additionally target Intel from Apple Silicon;
# other operating systems still build on their destination OS.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$repo_root/scripts/desktop_native_pins.env"
output="${1:-$repo_root/desktop/build/native}"
work="${MUTA_NATIVE_WORK:-$repo_root/desktop/build/native-work}"
llama_commit="$MUTA_LLAMA_COMMIT"
ffmpeg_commit="$MUTA_FFMPEG_COMMIT"
target_arch="${MUTA_DESKTOP_TARGET_ARCH:-$(uname -m)}"
native_jobs="${MUTA_NATIVE_JOBS:-${NUMBER_OF_PROCESSORS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || sysctl -n hw.ncpu)}}"
apple_arch="$target_arch"
if [ "$(uname -s)" = "Darwin" ] && [ "$apple_arch" = "aarch64" ]; then
  # Muta's cross-platform label is aarch64; Apple Clang, CMake and FFmpeg call
  # the same architecture arm64 and reject `-arch aarch64`.
  apple_arch="arm64"
fi

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
      -DCMAKE_OSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-$MUTA_MACOS_DEPLOYMENT_TARGET}"
      -DCMAKE_OSX_ARCHITECTURES="$apple_arch"
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
      # cpp-httplib requires CreateFile2 and deliberately rejects the older implicit
      # MinGW API baseline. Muta supports Windows 10/11, so declare that contract.
      -DCMAKE_C_FLAGS=-D_WIN32_WINNT=0x0A00
      -DCMAKE_CXX_FLAGS=-D_WIN32_WINNT=0x0A00
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
cmake --build "$work/llama-build" --config Release --parallel "$native_jobs" --target llama-server

llama_binary="$(find "$work/llama-build/bin" -type f \( -name llama-server -o -name llama-server.exe \) -print -quit)"
test -n "$llama_binary"
cp "$llama_binary" "$output/"

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
(
  cd "$work/ffmpeg-build"
  configure_ffmpeg() {
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
      "$@"
  }
  if [ "$(uname -s)" = "Darwin" ]; then
    macos_min="${MACOSX_DEPLOYMENT_TARGET:-$MUTA_MACOS_DEPLOYMENT_TARGET}"
    if [ "$apple_arch" != "$(uname -m)" ]; then
      configure_ffmpeg \
        --arch="$apple_arch" \
        --cc="clang -arch $apple_arch" \
        --extra-cflags="-mmacosx-version-min=$macos_min" \
        --extra-ldflags="-mmacosx-version-min=$macos_min"
    else
      configure_ffmpeg \
        --extra-cflags="-mmacosx-version-min=$macos_min" \
        --extra-ldflags="-mmacosx-version-min=$macos_min"
    fi
  elif [[ "$(uname -s)" = MINGW* || "$(uname -s)" = MSYS* || "$(uname -s)" = CYGWIN* ]]; then
    # FFmpeg otherwise leaves libwinpthread-1.dll as an undeclared target dependency even
    # when its own libraries are static. The offline kit must use only Windows system DLLs.
    configure_ffmpeg --extra-ldflags=-static
  else
    configure_ffmpeg
  fi
  make -j "$native_jobs"
  make install
)
ffmpeg_binary="$(find "$ffmpeg_prefix/bin" -maxdepth 1 -type f \( -name ffmpeg -o -name ffmpeg.exe \) -print -quit)"
test -n "$ffmpeg_binary"
cp "$ffmpeg_binary" "$output/"
printf '%s\n' \
  "llama.cpp=$MUTA_LLAMA_LABEL/$llama_commit" \
  "ffmpeg=$MUTA_FFMPEG_LABEL/$ffmpeg_commit" \
  > "$output/VERSIONS.txt"
bash "$repo_root/scripts/verify_desktop_native.sh" "$output"
