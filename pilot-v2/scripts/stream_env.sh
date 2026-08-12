#!/usr/bin/env bash
# scripts/stream_env.sh — container env for the weight-streaming gates
# (pilot/v2, STREAMING_IMPL_PLAN.md task A1 / S0.1).
#
# Subcommands:
#   image                    build the muta-stream image from scripts/Dockerfile.streaming
#   build                    configure + build the streaming-gate llama.cpp targets
#                             into the muta-build volume, from a ro bind-mount of
#                             the repo's llama.cpp/ tree. Idempotent/re-runnable:
#                             later phases rebuild after code changes.
#   models                   copy the mid-tier model (+ bundle/muta-trio.gguf, once
#                             it exists) into the muta-models volume. Never touches
#                             models/ itself (read-only mount).
#   cgrun CAP CMD...         run CMD in a fresh, capped, gate-grade container;
#                             prints memory.peak + memory.stat(anon,file) + OOMKilled
#                             on exit.
#   drop_caches              drop the Docker Desktop VM's page cache (privileged).
#
# Env overrides: IMAGE (default muta-stream), BUILD_VOLUME (muta-build),
# MODELS_VOLUME (muta-models).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${IMAGE:-muta-stream}"
BUILD_VOLUME="${BUILD_VOLUME:-muta-build}"
MODELS_VOLUME="${MODELS_VOLUME:-muta-models}"
DOCKERFILE="${REPO_ROOT}/scripts/Dockerfile.streaming"

# Targets built for the streaming gates. llama-speculative-simple lives under
# examples/ (not tools/), so LLAMA_BUILD_EXAMPLES=ON is required to reach it.
BUILD_TARGETS=(llama-completion llama-duo llama-bench llama-speculative-simple)

usage() {
    cat <<'EOF'
usage: scripts/stream_env.sh <subcommand> [args...]

subcommands:
  image                  build the muta-stream image
  build                  configure+build llama.cpp streaming-gate targets into muta-build
  models                 copy the mid-tier model (+ trio bundle if present) into muta-models
  cgrun CAP CMD...        run CMD capped at CAP (e.g. 2048m) in a fresh gate container
  drop_caches             drop the Docker Desktop VM page cache (privileged)
EOF
}

cmd_image() {
    docker build -t "$IMAGE" -f "$DOCKERFILE" "$REPO_ROOT"
}

cmd_build() {
    docker volume create "$BUILD_VOLUME" >/dev/null

    local target_flags=()
    local t
    for t in "${BUILD_TARGETS[@]}"; do
        target_flags+=(--target "$t")
    done

    # -S/-B against an already-configured /build is a no-op reconfigure (cmake
    # detects the existing cache); this is what makes `build` safe to re-run
    # after llama.cpp source changes in later phases.
    #
    # `-- -k` passes GNU make's keep-going flag through, so one broken target
    # (see docs/DISCOVERY.md S0 re: llama-duo / GCC) does not block the rest.
    set +e
    docker run --rm \
        -v "${REPO_ROOT}/llama.cpp:/src/llama.cpp:ro" \
        -v "${BUILD_VOLUME}:/build" \
        "$IMAGE" \
        bash -c '
            set -euo pipefail
            cmake -S /src/llama.cpp -B /build \
                -DCMAKE_BUILD_TYPE=Release \
                -DLLAMA_CURL=OFF \
                -DGGML_BLAS=OFF \
                -DGGML_NATIVE=OFF \
                -DGGML_CPU_ARM_ARCH=armv8.5-a+dotprod+i8mm+fp16 \
                -DLLAMA_BUILD_EXAMPLES=ON
            cmake --build /build -j8 "$@" -- -k
        ' bash "${target_flags[@]}"
    local status=$?
    set -e

    echo "--- build: binaries present in ${BUILD_VOLUME}:/build/bin ---"
    docker run --rm -v "${BUILD_VOLUME}:/build:ro" "$IMAGE" \
        bash -c 'ls -la /build/bin 2>/dev/null || echo "(no /build/bin)"'

    if [[ "$status" -ne 0 ]]; then
        echo "stream_env.sh: build: cmake --build exited $status (keep-going was set; check which targets are missing from /build/bin above)" >&2
    fi
    return "$status"
}

cmd_models() {
    docker volume create "$MODELS_VOLUME" >/dev/null

    local mid="${REPO_ROOT}/models/Qwen3.5-4B-Q4_K_M.gguf"
    if [[ ! -f "$mid" ]]; then
        echo "stream_env.sh: models: missing $mid" >&2
        exit 1
    fi

    docker run --rm \
        -v "${REPO_ROOT}/models:/src-models:ro" \
        -v "${REPO_ROOT}/bundle:/src-bundle:ro" \
        -v "${MODELS_VOLUME}:/models" \
        "$IMAGE" \
        bash -c '
            set -euo pipefail
            cp -v /src-models/Qwen3.5-4B-Q4_K_M.gguf /models/
            if [[ -f /src-bundle/muta-trio.gguf ]]; then
                cp -v /src-bundle/muta-trio.gguf /models/
            else
                echo "stream_env.sh: models: bundle/muta-trio.gguf not present yet, skipping (created in task A4)"
            fi
        '
}

cmd_cgrun() {
    if [[ $# -lt 2 ]]; then
        echo "usage: scripts/stream_env.sh cgrun CAP CMD..." >&2
        exit 1
    fi
    local cap="$1"; shift

    local name="muta-stream-cgrun-$$-${RANDOM}"

    set +e
    docker run --name "$name" \
        --memory="$cap" --memory-swap="$cap" --cpus=6 --cgroupns=private \
        -v "${BUILD_VOLUME}:/build:ro" \
        -v "${MODELS_VOLUME}:/models:ro" \
        -v "${REPO_ROOT}:/work:ro" \
        "$IMAGE" \
        bash -c '
            "$@"
            status=$?
            echo "--- memory.peak ---"
            cat /sys/fs/cgroup/memory.peak 2>/dev/null || echo "memory.peak: unavailable"
            echo "--- memory.stat (anon, file) ---"
            grep -E "^(anon|file) " /sys/fs/cgroup/memory.stat 2>/dev/null || echo "memory.stat: unavailable"
            exit "$status"
        ' bash "$@"
    local status=$?
    set -e

    local oomkilled
    oomkilled="$(docker inspect -f '{{.State.OOMKilled}}' "$name" 2>/dev/null || echo unknown)"
    echo "--- cgrun: container=$name cap=$cap exit_status=$status OOMKilled=$oomkilled ---"

    docker rm "$name" >/dev/null 2>&1 || true

    return "$status"
}

cmd_drop_caches() {
    docker run --rm --privileged "$IMAGE" \
        bash -c 'sync; echo 3 > /proc/sys/vm/drop_caches && echo "drop_caches: done"'
}

main() {
    if [[ $# -lt 1 ]]; then
        usage >&2
        exit 1
    fi
    local sub="$1"; shift
    case "$sub" in
        image) cmd_image "$@" ;;
        build) cmd_build "$@" ;;
        models) cmd_models "$@" ;;
        cgrun) cmd_cgrun "$@" ;;
        drop_caches) cmd_drop_caches "$@" ;;
        -h|--help) usage ;;
        *)
            echo "stream_env.sh: unknown subcommand: $sub" >&2
            usage >&2
            exit 1
            ;;
    esac
}

main "$@"
