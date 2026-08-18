#!/usr/bin/env bash
# Exploratory bare-host benchmark for the GCP x86 cloud proxy. Never report-grade.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

die() { printf 'error: %s\n' "$*" >&2; exit 1; }

[ "$(uname -s)/$(uname -m)" = "Linux/x86_64" ] \
    || die "native benchmark requires Linux/x86_64"

if [ -n "${PY:-}" ]; then
    bench_python="$PY"
elif [ -x .venv/bin/python ]; then
    bench_python=.venv/bin/python
else
    bench_python=python3
fi

"$bench_python" scripts/export_native_linux.py --verify-only \
    || die "verified native engine missing; run './run.sh export-linux'"
"$bench_python" -c "import httpx, numpy, psutil" >/dev/null 2>&1 \
    || die "benchmark dependencies missing; activate the project venv or run 'make install'"

model="${MUTA_BENCH_MODEL:-models/core/Qwen3.5-4B-IQ4_XS.gguf}"
[ -f "$model" ] || die "model not found: $model"
case "$model" in
    /*) model_path="$model" ;;
    *) model_path="$PWD/$model" ;;
esac

# A running control contaminates native RSS/bandwidth. Detect it when Docker is available,
# but do not make Docker a runtime dependency of the benchmark itself.
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    if [ -n "$(docker compose ps -q 2>/dev/null || true)" ]; then
        die "Compose services are running; stop the control with './run.sh down' before benchmarking"
    fi
fi

for port in 8000 8080 8089; do
    "$bench_python" -c 'import socket,sys; s=socket.socket(); s.bind(("127.0.0.1", int(sys.argv[1]))); s.close()' \
        "$port" >/dev/null 2>&1 || die "port $port is occupied; stop the existing gateway/engine/sweep first"
done

swap_kib=$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)
[ "${swap_kib:-0}" = 0 ] || die "host swap is enabled; disable it before benchmark measurements"

export MUTA_BENCH_SERVER_BIN="$PWD/runtime/build/bin/llama-server"
export MUTA_BENCH_MODEL="$model_path"
export MUTA_BENCH_ARTIFACT_DIR="$PWD/bench/.artifacts/gcp-cloud-proxy"
export MUTA_BENCH_CONTEXT="x86 cloud proxy (GCP n2-custom-4-8192, 2C/4T)"
export MUTA_BENCH_REPORT_GRADE=0
export MUTA_GIT_SHA="${MUTA_GIT_SHA:-$("$bench_python" scripts/source_identity.py --id)}"

exec "$bench_python" -m bench.target_box --hash --label gcp-n2-cloud-proxy "$@"
