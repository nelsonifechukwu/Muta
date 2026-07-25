#!/usr/bin/env bash
# Muta — one command to a running stack.
#
#   ./run.sh            build (cached), provision models, start db + backend + frontend,
#                       print the UI URL
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
Usage: ./run.sh [--build] | down | logs

  (no args)   bring up the full stack and print the frontend URL
  --build     force a clean (no-cache) image rebuild first
  down        docker compose down (conversations survive: the muta-pgdata volume stays)
  logs        docker compose logs -f

The first run compiles llama.cpp (slow) and downloads ~4 GB of models into ./models
(kept for every later run). Later runs start in seconds.
EOF
}

NO_CACHE=0
case "${1:-}" in
    "")         ;;
    --build)    NO_CACHE=1 ;;
    down)       exec docker compose down ;;
    logs)       exec docker compose logs -f ;;
    -h|--help)  usage; exit 0 ;;
    *)          die "unknown option: $1  (try --help)" ;;
esac

command -v docker >/dev/null 2>&1 || die "docker not found — install Docker Desktop / Engine."
docker info >/dev/null 2>&1 || die "docker daemon isn't running — start it."
docker compose version >/dev/null 2>&1 || die "docker compose v2 not found — update Docker."

mkdir -p models

# ---------------------------------------------------------------------------
# 1. Images
# ---------------------------------------------------------------------------
if [ "$NO_CACHE" = 1 ]; then
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
    "models/core/Qwen3.5-4B-Q4_K_M.gguf"
    "models/core/mmproj-F16.gguf"
    "models/asr/moonshine-tiny-en-int8/tokens.txt"
    "models/asr/silero_vad.onnx"
    "models/tts/piper/en_US-joe-medium.onnx"
    "models/embed/bge-small-en-v1.5-q8_0.gguf"
)
DRAFT="models/Qwen3-0.6B/Qwen3-0.6B-Q4_K_M.gguf"
missing=0
for f in "${required_models[@]}"; do
    [ -e "$f" ] || { missing=1; break; }
done
if [ "$missing" = 1 ]; then
    info "provisioning models into ./models (first time: ~4 GB — resumable, so rerun on failure)"
    # --mmproj-precision f16: no first-party Q8_0 projector exists (docs/model-provenance.md);
    # --with-draft: the tier-B speculative-decoding draft (Qwen3.5-0.8B — no 0.6B exists).
    docker compose run --rm --no-deps backend \
        python3.10 scripts/fetch_models.py --with-draft --mmproj-precision f16 \
        || die "model provisioning failed — rerun ./run.sh (downloads resume where they stopped)"
elif [ ! -e "$DRAFT" ]; then
    # The draft only speeds decoding up — the stack runs without it, so its absence must
    # never block a boot. build_command skips --model-draft when the file is missing.
    warn "speculation draft absent ($DRAFT) — running without it. Fetch it with: make model"
else
    info "models already provisioned"
fi

# ---------------------------------------------------------------------------
# 3. Up, in dependency order (db → backend → frontend), waiting on healthchecks
# ---------------------------------------------------------------------------
info "starting the stack (backend is healthy once the model is loaded — minutes on Apple silicon)"
if ! docker compose up -d --wait; then
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
