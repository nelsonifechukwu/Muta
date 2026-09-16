#!/usr/bin/env bash
set -euo pipefail

repo="${1:-/home/elijahnelson/Muta}"
campaign="$repo/bench/measurements/campaign-20260913-balanced-models"
models_root="$campaign/models"
raw="$campaign/raw"
out="$raw/stem-responses-vector-remainder.jsonl"
events="$raw/stem-events-vector-remainder.jsonl"
server="$repo/bench/.artifacts/llama.cpp-b10175/build-avx2-rerun-20260819/bin/llama-server"

mkdir -p "$raw" "$campaign/stem-server-logs-vector-remainder"

exec 9>/tmp/muta-benchmark.lock
if ! flock -n 9; then
    echo "another Muta benchmark campaign holds /tmp/muta-benchmark.lock" >&2
    exit 1
fi

restore_services() {
    sudo systemctl start google-cloud-ops-agent.service || true
    systemctl --user start muta-gateway.service || true
}
trap restore_services EXIT

[[ -x "$server" ]] || { echo "missing vector server: $server" >&2; exit 1; }
[[ ! -e "$out" ]] || { echo "$out already exists; refusing duplicate runs" >&2; exit 1; }
[[ ! -e "$events" ]] || { echo "$events already exists; refusing duplicate runs" >&2; exit 1; }

models=(
    "$models_root/Qwen3.5-2B-Q4_K_M.gguf"
    "$models_root/VibeThinker-1.5B-q4_k_m.gguf"
    "$models_root/Falcon-H1R-0.6B-Q4_K_M.gguf"
    "$models_root/nvidia_OpenReasoning-Nemotron-1.5B-Q4_K_M.gguf"
)

for model in "${models[@]}"; do
    [[ -f "$model" ]] || { echo "missing model: $model" >&2; exit 1; }
done

cd "$repo"
sudo systemctl stop google-cloud-ops-agent.service
systemctl --user stop muta-gateway.service

if pgrep -x llama-bench >/dev/null || pgrep -x llama-server >/dev/null || \
    pgrep -f '[l]m_eval' >/dev/null || pgrep -f '[a]dtc_profiler' >/dev/null; then
    echo "unexpected model or profiler process before vector STEM screen" >&2
    exit 1
fi

bench/.venv-profiler/bin/python -m bench.run_stem_prompt_suite \
    --server "$server" \
    --models "${models[@]}" \
    --out "$out" \
    --events "$events" \
    --logs "$campaign/stem-server-logs-vector-remainder" \
    --port 18080 \
    --threads 4 \
    --hardware-context x86_cloud_proxy_gcp_n2_custom_4_8192_2c4t_vector_b10175
