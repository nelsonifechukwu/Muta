#!/usr/bin/env bash
# Container entrypoint — brings up the target's two-process topology (ROADMAP A.2):
# llama-server (the engine) plus the gateway, which has the other four services mounted
# into it. Running each Python service separately would cost 60-100 MB RSS apiece and turn
# any single crash into a disqualifying execution crash.
#
# The gateway is deliberately started even when the engine is missing or failed: /v1/chat
# answers 503 with a fix hint and /v1/ready reports {"inference": false}, which is a far
# better failure than a container that refuses to boot.
set -uo pipefail

log() { printf '[entrypoint] %s\n' "$*" >&2; }

# An explicit command wins, so `docker run muta-dev python3.10 -m pytest` runs pytest rather
# than silently booting the app. Anything that manages its own engine (runtime.cli does)
# lands here too.
if [ "$#" -gt 0 ]; then
    exec "$@"
fi

if [ "${MUTA_NO_ENGINE:-0}" = "1" ]; then
    log "MUTA_NO_ENGINE=1 — gateway only; /v1/chat will return 503"
else
    if [ ! -d "${MUTA_RT_MODEL_DIR:-/app/models}" ] || \
       ! ls "${MUTA_RT_MODEL_DIR:-/app/models}"/*.gguf >/dev/null 2>&1; then
        log "no .gguf in ${MUTA_RT_MODEL_DIR:-/app/models} — the engine will try to fetch one."
        log "mount weights with:  -v \"\$(pwd)/models:/app/models\""
    fi
    # NOTE(9 Aug): this keeps a Python supervisor (~40 MB RSS) alive purely to hold the
    # engine subprocess — ~0.11 pts of S_eff. The native extraction should launch
    # llama-server directly instead. Fine for dev, not for the target.
    log "starting llama-server"
    python3.10 -m runtime.server &
    engine_pid=$!
    trap 'kill -TERM "${engine_pid}" 2>/dev/null || true' INT TERM EXIT
fi

log "starting gateway on 0.0.0.0:8000"
exec python3.10 -m uvicorn orchestrator.main:app --host 0.0.0.0 --port 8000
