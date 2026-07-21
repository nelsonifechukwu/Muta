#!/usr/bin/env bash
# Muta — one command to start chatting.
#
#   ./run.sh                  chat, in Docker (default)
#   ./run.sh --native         chat, on the host
#   ./run.sh --serve          run the HTTP app instead of a REPL
#   ./run.sh --tui            chat TUI with a live metrics panel (host)
#   ./run.sh --help           everything else
#
# Docker is the default because it's linux/amd64 — the shape that actually ships. Everything
# needed (image, weights, engine binary) is provisioned on demand, so a clean clone reaches a
# conversation in one command.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

IMAGE="${IMAGE:-muta-dev:latest}"
MODE=docker
ACTION=chat
FORCE_BUILD=0
ARGS=()

# `COPY . .` copies the working tree, not HEAD — so an image built from an uncommitted tree
# must not claim to be that commit. A wrong SHA is worse than no SHA in a benchmark report.
git_sha() {
    local sha dirty=""
    sha=$(git rev-parse HEAD 2>/dev/null) || { echo unknown; return; }
    [ -n "$(git status --porcelain 2>/dev/null)" ] && dirty="-dirty"
    echo "${sha}${dirty}"
}

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
info() { printf '\033[36m▸\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'EOF'
Usage: ./run.sh [options] [-- <extra args for the chat REPL>]

  (no options)      chat in Docker                                [default]
  --native          chat on the host, using .venv
  --serve           run the HTTP app (gateway :8000) instead of the REPL
  --tui             chat TUI + live metrics panel (host; boots the app for you)
  --build           rebuild the image before running
  --image NAME      image tag (default: muta-dev:latest)
  --help            this

Examples:
  ./run.sh                                  # start chatting
  ./run.sh --native                         # ...without emulation (much faster on a Mac)
  ./run.sh --serve                          # HTTP app; then curl localhost:8000/v1/chat
  ./run.sh --tui                            # interactive TUI with tok/s + RAM on screen
  ./run.sh -- --conversation <id>           # resume a stored thread
  ./run.sh --native -- --mode subgoal       # break the problem into sub-goals

Modes are socratic (default) and subgoal — the two prompts in orchestrator/prompts/.

Conversations persist in data/muta.sqlite3 and survive restarts either way.
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --native)  MODE=native ;;
        --docker)  MODE=docker ;;
        --serve)   ACTION=serve ;;
        --tui)     ACTION=tui; MODE=native ;;
        --chat)    ACTION=chat ;;
        --build)   FORCE_BUILD=1 ;;
        --image)   IMAGE="$2"; shift ;;
        -h|--help) usage; exit 0 ;;
        --)        shift; ARGS+=("$@"); break ;;
        *)         die "unknown option: $1  (try --help)" ;;
    esac
    shift
done

mkdir -p models data

# ---------------------------------------------------------------------------
# Native
# ---------------------------------------------------------------------------
run_native() {
    if [ ! -x .venv/bin/python ]; then
        info "creating .venv"
        python3 -m venv .venv
    fi
    # Cheap import check beats a slow unconditional pip install on every launch.
    if ! .venv/bin/python -c "import runtime.config" >/dev/null 2>&1; then
        info "installing dependencies (first run)"
        .venv/bin/python -m pip install --quiet --upgrade pip
        .venv/bin/python -m pip install --quiet -e ".[dev]"
    fi

    # find_binary() order: MUTA_RT_LLAMA_SERVER_BIN -> runtime/build/bin -> PATH.
    if [ -z "${MUTA_RT_LLAMA_SERVER_BIN:-}" ] \
       && [ ! -x runtime/build/bin/llama-server ] \
       && ! command -v llama-server >/dev/null 2>&1; then
        die "llama-server not found — native mode needs one.

  Either drop a prebuilt binary in runtime/build/bin/
    https://github.com/ggml-org/llama.cpp/releases   (pin: b10035)
  or:  brew install llama.cpp
  or just use Docker, which builds its own:  ./run.sh"
    fi

    if [ "$ACTION" = serve ]; then
        info "gateway on http://127.0.0.1:8000  (docs at /docs)"
        exec .venv/bin/python -m uvicorn orchestrator.main:app --port 8000
    fi
    if [ "$ACTION" = tui ]; then
        run_tui
        return
    fi
    exec .venv/bin/python -m runtime.cli "${ARGS[@]+"${ARGS[@]}"}"
}

# ---------------------------------------------------------------------------
# TUI — boot the engine + gateway, run the terminal client, tear it all down.
# The TUI attaches to host PIDs to sample RAM honestly, so it is native-only.
# ---------------------------------------------------------------------------
run_tui() {
    local engine_pid="" gateway_pid="" started_engine=0 started_gateway=0

    cleanup_tui() {
        [ "$started_gateway" = 1 ] && kill "$gateway_pid" 2>/dev/null || true
        [ "$started_engine" = 1 ] && kill "$engine_pid" 2>/dev/null || true
    }
    trap cleanup_tui EXIT INT TERM

    if ! curl -sf http://127.0.0.1:8080/health >/dev/null 2>&1; then
        info "starting llama-server on :8080"
        .venv/bin/python -m runtime.server >data/llama-server.log 2>&1 &
        engine_pid=$!
        started_engine=1
    fi
    if ! curl -sf http://127.0.0.1:8000/v1/health >/dev/null 2>&1; then
        info "starting gateway on :8000"
        .venv/bin/python -m uvicorn orchestrator.main:app --port 8000 >data/gateway.log 2>&1 &
        gateway_pid=$!
        started_gateway=1
    fi

    info "waiting for the engine to load the model…"
    local i
    for i in $(seq 1 120); do
        if curl -sf http://127.0.0.1:8000/v1/ready 2>/dev/null | grep -q '"ready":true'; then
            break
        fi
        [ "$i" = 120 ] && die "app did not become ready in time — see data/gateway.log and data/llama-server.log"
        sleep 1
    done

    .venv/bin/python -m bench.tui
}

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------
run_docker() {
    command -v docker >/dev/null 2>&1 || die "docker not found. Use ./run.sh --native instead."
    docker info >/dev/null 2>&1 || die "docker daemon isn't running — start Docker Desktop."

    if [ "$FORCE_BUILD" = 1 ] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
        info "building $IMAGE (linux/amd64; compiles llama.cpp — slow the first time)"
        docker buildx build --platform=linux/amd64 -f docker/dev.Dockerfile \
            --build-arg MUTA_GIT_SHA="$(git_sha)" \
            -t "$IMAGE" .
    fi

    # The image is linux/amd64. On Apple silicon that's QEMU, and inference crawls.
    case "$(uname -m)" in
        arm64|aarch64)
            warn "linux/amd64 image on $(uname -m): inference runs emulated and is much"
            warn "  slower than real. Fine for correctness; use --native for a quick chat,"
            warn "  and never trust tok/s from here (real numbers come from the x86 box)."
            ;;
    esac

    if ! ls models/*.gguf >/dev/null 2>&1; then
        info "no weights in models/ — the first run downloads ~378 MB into it (kept for next time)"
    fi

    local mounts=(-v "$PWD/models:/app/models" -v "$PWD/data:/app/data")

    # -t only when stdin really is a terminal: `echo hi | ./run.sh` dies with
    # "the input device is not a TTY" otherwise.
    local tty=(-i)
    [ -t 0 ] && tty+=(-t)

    if [ "$ACTION" = serve ]; then
        info "gateway on http://127.0.0.1:8000  (docs at /docs; Ctrl-C to stop)"
        exec docker run --rm --platform=linux/amd64 "${tty[@]}" -p 8000:8000 "${mounts[@]}" "$IMAGE"
    fi

    # runtime.cli starts its own llama-server, so the entrypoint's app path is bypassed.
    exec docker run --rm --platform=linux/amd64 "${tty[@]}" "${mounts[@]}" "$IMAGE" \
        python3.10 -m runtime.cli "${ARGS[@]+"${ARGS[@]}"}"
}

bold "Muta · ${MODE} · ${ACTION}"
case "$MODE" in
    native) run_native ;;
    docker) run_docker ;;
esac
