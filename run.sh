#!/usr/bin/env bash
# Muta — one command to a running stack.
#
#   ./run.sh            build (cached), provision models, start db + backend + frontend,
#                       print the UI URL
#   ./run.sh --native   dev mode: gateway + llama-server run on this host (arm64), db +
#                       frontend stay in docker — skips the amd64 emulation tax
#   ./run.sh down       stop the stack (data survives in the muta-pgdata volume)
#   ./run.sh logs       follow logs
#   ./run.sh --build    force a clean image rebuild first
#
# Three containers, all linux/amd64: db (Postgres), backend (llama-server + FastAPI
# gateway), frontend (nginx serving the chat UI, proxying /v1). Weights live in ./models
# on the host and are volume-mounted — never baked into an image.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
info() { printf '\033[36m▸\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'EOF'
Usage: ./run.sh [--native] [--gpu|--cpu] [--build] [--model PATH] | plan | down | logs

  (no args)   docker mode (default): bring up db + backend + frontend, print the UI URL
  --native    dev mode: db + frontend stay in docker; the gateway and an arm64
              llama-server run on THIS host in the foreground (Ctrl-C stops them;
              './run.sh down' stops the containers). No slow amd64 emulation.
              Native CPU is the ~10x-over-emulation path of record; --gpu adds Metal
              offload, which measured NEUTRAL for Qwen3.5-4B (docs/gpu.md).
  --gpu       native mode: export MUTA_RT_N_GPU_LAYERS=all (Metal). Experimental —
              measured no faster than native CPU for the default model at this pin.
  --cpu       force CPU everywhere (suppresses GPU detection and suggestions)
  --build     force a clean (no-cache) image rebuild first (docker images only)
  --model P   core GGUF to serve (default models/core/Qwen3.5-4B-IQ4_XS.gguf). A
              non-default model must already exist (fetch/quantize it first — e.g.
              scripts/fetch_models.py --quant-variants for the D1 candidates) and, in
              docker mode, live under ./models (the only dir mounted into the
              container). Vision (mmproj) pairs with the Qwen3.5-4B family, and the
              docker default keeps draft speculation active — a vocab-incompatible
              core fails the engine boot (set MUTA_RT_SPEC_TYPE=none first).
  plan        print the hardware decisions (host, mode, gpu) and exit — no side effects
  down        docker compose down (conversations survive: the muta-pgdata volume stays)
  logs        docker compose logs -f

The first docker run compiles llama.cpp (slow) and downloads ~4 GB of models into
./models (kept for every later run). Later runs start in seconds. Native mode needs
'make install' (an importable venv) and downloads the pinned llama.cpp arm64 release
into runtime/build/bin on first use.
EOF
}

# Pinned in runtime/VERSIONS.md — must match the container build so native-mode numbers
# are comparable. VERSIONS.md documents this exact practice for macOS dev.
ENGINE_TAG=b10035

fetch_native_engine() {
    # find_binary order (runtime/server.py): env override, runtime/build/bin, PATH.
    [ -n "${MUTA_RT_LLAMA_SERVER_BIN:-}" ] && [ -x "$MUTA_RT_LLAMA_SERVER_BIN" ] && return 0
    [ -x runtime/build/bin/llama-server ] && return 0
    command -v llama-server >/dev/null 2>&1 && {
        warn "using llama-server from PATH — NOT the pinned ${ENGINE_TAG}; numbers are not comparable"
        return 0
    }
    [ "$(uname -s)/$(uname -m)" = "Darwin/arm64" ] \
        || die "no llama-server found — install one on PATH or set MUTA_RT_LLAMA_SERVER_BIN"
    info "fetching pinned llama.cpp ${ENGINE_TAG} (macos-arm64 release) into runtime/build/bin"
    tmp=$(mktemp -d)
    url="https://github.com/ggml-org/llama.cpp/releases/download/${ENGINE_TAG}/llama-${ENGINE_TAG}-bin-macos-arm64.tar.gz"
    curl -fL --retry 3 -o "$tmp/llama.tar.gz" "$url" \
        || die "release download failed ($url) — install llama-server yourself and rerun"
    tar xzf "$tmp/llama.tar.gz" -C "$tmp"
    src=$(find "$tmp" -name llama-server -type f | head -1)
    [ -n "$src" ] || die "llama-server missing from the release archive — layout changed? extract manually into runtime/build/bin"
    mkdir -p runtime/build/bin
    cp "$src" runtime/build/bin/
    find "$tmp" \( -name '*.dylib' -o -name '*.metal' \) -exec cp {} runtime/build/bin/ \; || true
    chmod +x runtime/build/bin/llama-server
    rm -rf "$tmp"
}

# GPU detection. CPU is the invariant default; Metal exists only in native mode (Docker
# on macOS has no GPU passthrough); NVIDIA is detect-and-point-at-docs (docs/gpu.md)
# until a CUDA image variant lands.
detect_gpu() {
    # Plain `if`s throughout: under set -e a false `[ … ] && …` list aborts the caller
    # (or silently truncates a $(…) substitution), which here would report gpu="".
    if [ "${FORCE_CPU:-0}" = 1 ]; then
        echo none
        return
    fi
    case "$(uname -s)/$(uname -m)" in
        Darwin/arm64)
            echo metal-native ;;
        Linux/*)
            if command -v nvidia-smi >/dev/null 2>&1; then
                echo cuda-available
            else
                echo none
            fi ;;
        *)
            echo none ;;
    esac
}

# Connectivity, decided once per invocation (~3 s worst case). Any HTTP response counts
# as online; only transport failure (DNS, TLS, unreachable) means offline. The boot must
# never die on a registry it cannot reach when everything it needs is already local
# (2026-08-07: a dead network + a neighbor-clobbered db tag took the whole stack down).
probe_net() {
    if curl -fsSI --max-time 3 "${MUTA_NET_PROBE_URL:-https://huggingface.co}" \
        >/dev/null 2>&1; then
        echo online
    else
        echo offline
    fi
}

print_plan() {
    echo "host=$(uname -s)/$(uname -m)"
    echo "mode=$MODE"
    echo "gpu=$(detect_gpu)"
    echo "net=$(probe_net)"
}

native_up() {
    "${PY:-python3}" -c "import orchestrator, uvicorn" >/dev/null 2>&1 \
        || die "project not importable by ${PY:-python3} — activate your venv and run 'make install'"
    fetch_native_engine
    info "starting db (docker)"
    # A docker-mode backend still publishing :8000 would crash uvicorn below with a bare
    # "address already in use" — stop it (no-op when nothing is running).
    docker compose stop backend >/dev/null 2>&1 || true
    docker compose up -d --wait db || die "db failed to start"
    info "starting frontend (docker, proxying /v1 to this host)"
    BACKEND_UPSTREAM="host.docker.internal:8000" docker compose up -d --no-deps frontend \
        || die "frontend failed to start"
    bold "Native dev mode — backend runs in THIS terminal. Ctrl-C stops it; './run.sh down' stops the containers."
    info "chat UI:   http://localhost:3000   (proxies 502 until the model finishes loading — seconds natively)"
    info "API:       http://localhost:8000/v1  (docs at http://localhost:8000/docs)"
    export MUTA_RT_AUTOSTART=1
    export MUTA_RT_MODEL_DIR="$MODEL_DIR"
    export MUTA_RT_MODEL_FILE="$MODEL_FILE"
    export MUTA_RT_MODEL_ALIAS="$MODEL_ALIAS"
    export MUTA_RT_N_CTX=2048
    export MUTA_RT_ENABLE_THINKING=1
    export MUTA_RT_AUTO_DOWNLOAD=0
    export MUTA_RT_DRAFT_MODEL=models/draft/Qwen3.5-0.8B-Q4_K_M.gguf
    # Speculation is measured net-negative on native CPU in every form (RESULTS.md
    # 2026-08-01: draft n-max 3 → −47% at 98.8% acceptance, n-max 8 → −13% at 92.9%,
    # ngram → −27% at 24.6% — CPU verify pays full price). One env flip re-enables it.
    export MUTA_RT_SPEC_TYPE=none
    export MUTA_RT_STARTUP_TIMEOUT_S=300
    export TUTOR_ROOT="$PWD"
    # Metal is opt-in (--gpu), NOT the native default: measured 2026-08-08 (RESULTS.md,
    # bare-engine A/B), -ngl all is neutral-to-slightly-negative for the hybrid
    # Qwen3.5-4B at this pin — layers assign to MTL0 but decode doesn't move. Native
    # CPU is already the ~10x-over-emulation win; don't default to a measured no-op.
    if [ "${GPU_OPT:-0}" = 1 ] && [ -z "${MUTA_RT_N_GPU_LAYERS:-}" ] \
        && [ "$(detect_gpu)" = metal-native ]; then
        export MUTA_RT_N_GPU_LAYERS=all
        info "Metal: offloading all layers (measured neutral for Qwen3.5-4B — see docs/gpu.md)"
    fi
    # No MUTA_RT_N_THREADS here — but not because the engine default wins: RuntimeConfig
    # now derives P-core-pinned threads on Apple silicon itself (runtime/config.py,
    # measured +26% and stable vs the engine's all-cores default).
    exec "${PY:-python3}" -m uvicorn orchestrator.main:app --host 0.0.0.0 --port 8000
}

MODE=docker
NO_CACHE=0
FORCE_CPU=0
GPU_OPT=0
DEFAULT_MODEL="models/core/Qwen3.5-4B-IQ4_XS.gguf"
MODEL="$DEFAULT_MODEL"
while [ $# -gt 0 ]; do
    case "$1" in
        --native)   MODE=native ;;
        --cpu)      FORCE_CPU=1 ;;
        --gpu)      GPU_OPT=1 ;;
        plan)       MODE=plan ;;
        --build)    NO_CACHE=1 ;;
        --model)    [ $# -ge 2 ] || die "--model needs a path  (try --help)"
                    MODEL="$2"; shift ;;
        --model=*)  MODEL="${1#--model=}" ;;
        down)       exec docker compose down ;;
        logs)       exec docker compose logs -f ;;
        -h|--help)  usage; exit 0 ;;
        *)          die "unknown option: $1  (try --help)" ;;
    esac
    shift
done

# `plan` is side-effect-free by contract: it must answer before docker, models, or the
# network are even looked at, so it works on a bare clone and in tests.
if [ "$MODE" = plan ]; then
    print_plan
    exit 0
fi

# --- Core-model selection (hot-swap seam) --------------------------------------------
# The identity of the served model lives in MUTA_RT_MODEL_DIR/FILE/ALIAS and nowhere
# else; everything below only derives those three values from $MODEL.
MODEL="${MODEL#./}"
if [ "$MODEL" != "$DEFAULT_MODEL" ]; then
    # A custom model is never auto-provisioned: fetch_models.py only knows the pinned
    # roster, so a missing file here would otherwise surface minutes later as a boot
    # failure with a misleading "provisioning" step in between.
    [ -e "$MODEL" ] || die "model not found: $MODEL — fetch or quantize it first \
(pinned candidates: scripts/fetch_models.py --quant-variants / --with-draft)"
    case "$MODEL" in
        models/*) ;;
        *) [ "$MODE" = native ] \
            || die "docker mode mounts only ./models into the container — pass a repo-relative path under models/ (got: $MODEL)" ;;
    esac
    warn "custom core model: $MODEL"
    warn "  vision (mmproj-F16) pairs with the Qwen3.5-4B family; other cores degrade vision"
fi
MODEL_DIR=$(dirname "$MODEL")
MODEL_FILE=$(basename "$MODEL")
if [ "$MODEL" = "$DEFAULT_MODEL" ]; then
    MODEL_ALIAS="qwen3.5-4b"   # unchanged /v1/models identity for the default
else
    MODEL_ALIAS=$(basename "$MODEL" .gguf | tr '[:upper:]' '[:lower:]')
fi
if [ "$MODE" = docker ]; then
    # docker-compose.yml interpolates these (host path → the ./models mount at /app).
    export MUTA_MODEL_DIR="/app/$MODEL_DIR"
    export MUTA_MODEL_FILE="$MODEL_FILE"
    export MUTA_MODEL_ALIAS="$MODEL_ALIAS"
fi

command -v docker >/dev/null 2>&1 || die "docker not found — install Docker Desktop / Engine."
docker info >/dev/null 2>&1 || die "docker daemon isn't running — start it."
docker compose version >/dev/null 2>&1 || die "docker compose v2 not found — update Docker."

mkdir -p models

if [ "$MODE" = docker ]; then
    gpu_hint=$(detect_gpu)
    if [ "$gpu_hint" = metal-native ]; then
        warn "emulated x86 on Apple Silicon: './run.sh --native' runs the arm64 engine natively — ~10x faster (measured, RESULTS.md 2026-08-08)"
    elif [ "$gpu_hint" = cuda-available ]; then
        warn "NVIDIA GPU detected: see docs/gpu.md for the CUDA backend variant"
    fi
fi

# ---------------------------------------------------------------------------
# 1. Images
# ---------------------------------------------------------------------------
NET=$(probe_net)
if [ "$NET" = offline ]; then
    info "offline — skipping builds/pulls; using what is already local"
fi

if [ "$MODE" = native ]; then
    if [ "$NET" = offline ]; then
        docker image inspect muta-frontend:latest >/dev/null 2>&1 \
            || die "offline and no local frontend image — connect once and rerun"
        info "native mode: offline, using the existing frontend image"
    else
        info "native mode: building only the frontend image (the backend runs on this host)"
        docker compose build frontend || die "frontend image build failed"
    fi
elif [ "$NET" = offline ]; then
    docker image inspect muta-backend:latest muta-frontend:latest >/dev/null 2>&1 \
        || die "offline and no local images exist — connect once and rerun ./run.sh"
elif [ "$NO_CACHE" = 1 ]; then
    info "rebuilding images from scratch"
    docker compose build --no-cache
else
    info "building images (cached; the first build compiles llama.cpp and is slow)"
    if ! docker compose build; then
        # A flaky network can fail even a fully-cached build (base-image re-resolution).
        # Existing local images are a better outcome than no stack at all.
        if docker image inspect muta-backend:latest muta-frontend:latest >/dev/null 2>&1; then
            warn "image build failed (network?) — continuing with the existing local images"
        else
            die "image build failed and no local images exist — check the network and rerun"
        fi
    fi
fi

# ---------------------------------------------------------------------------
# 2. Model provisioning (idempotent: sha256-verified files are skipped)
# ---------------------------------------------------------------------------
required_models=(
    "$MODEL"
    "models/core/mmproj-F16.gguf"
    "models/asr/moonshine-tiny-en-int8/tokens.txt"
    "models/asr/silero_vad.onnx"
    "models/tts/piper/en_US-joe-medium.onnx"
    "models/embed/bge-small-en-v1.5-q8_0.gguf"
)
DRAFT="models/draft/Qwen3.5-0.8B-Q4_K_M.gguf"
missing=0
for f in "${required_models[@]}"; do
    [ -e "$f" ] || { missing=1; break; }
done
if [ "$missing" = 1 ] && [ "$NET" = offline ]; then
    warn "offline, and these required model files are missing:"
    for f in "${required_models[@]}"; do
        if [ ! -e "$f" ]; then warn "  $f"; fi
    done
    die "connect once and rerun ./run.sh — downloads resume where they stopped"
elif [ "$missing" = 1 ]; then
    info "provisioning models into ./models (first time: ~4 GB — resumable, so rerun on failure)"
    # --mmproj-precision f16: no first-party Q8_0 projector exists (docs/model-provenance.md);
    # --with-draft: the tier-B speculative-decoding draft (Qwen3.5-0.8B — no 0.6B exists).
    if [ "$MODE" = native ]; then
        "${PY:-python3}" scripts/fetch_models.py --with-draft --mmproj-precision f16 \
            || die "model provisioning failed — rerun ./run.sh --native (downloads resume)"
    else
        docker compose run --rm --no-deps backend \
            python3.10 scripts/fetch_models.py --with-draft --mmproj-precision f16 \
            || die "model provisioning failed — rerun ./run.sh (downloads resume where they stopped)"
    fi
elif [ ! -e "$DRAFT" ]; then
    # The draft only speeds decoding up — the stack runs without it, so its absence must
    # never block a boot. _speculation_flags skips --spec-draft-model when the file is missing.
    warn "speculation draft absent ($DRAFT) — running without it. Fetch it with:"
    if [ "$MODE" = native ]; then
        warn "  ${PY:-python3} scripts/fetch_models.py --with-draft --only draft"
    else
        warn "  docker compose run --rm --no-deps backend python3.10 scripts/fetch_models.py --with-draft --only draft"
    fi
else
    info "models already provisioned"
fi

# ---------------------------------------------------------------------------
# 3. Up, in dependency order (db → backend → frontend), waiting on healthchecks
# ---------------------------------------------------------------------------
if [ "$MODE" = native ]; then
    native_up   # execs uvicorn; never returns
fi

info "starting the stack (backend is healthy once the model is loaded — minutes on Apple silicon)"
# Offline: --pull never makes a genuinely-missing image fail fast with our message
# instead of hanging on a registry that cannot answer. Deliberately a plain string
# expanded unquoted: empty-array expansion under set -u breaks macOS's bash 3.2.
PULL_NEVER=""
if [ "$NET" = offline ]; then PULL_NEVER="--pull never"; fi
# shellcheck disable=SC2086
if ! docker compose up -d --wait $PULL_NEVER; then
    warn "stack did not become healthy. Most useful next step:"
    warn "  docker compose ps"
    warn "  docker compose logs backend --tail 50"
    warn "On Apple silicon: enable Rosetta for x86 emulation and give Docker ≥ 12 GB memory."
    exit 1
fi

bold  "Muta is up."
info  "chat UI:   http://localhost:3000   (open in a browser; mic needs localhost, not a LAN IP)"
info  "API:       http://localhost:8000/v1  (docs at http://localhost:8000/docs)"
info  "stop with: ./run.sh down"
