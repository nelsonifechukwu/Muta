#!/usr/bin/env bash
set -euo pipefail

repo="${1:-/home/elijahnelson/Muta}"
campaign="$repo/bench/measurements/campaign-20260913-balanced-models"
models="$campaign/models"
bench="$repo/bench/.artifacts/llama.cpp-b10175/build/bin/llama-bench"
result="$campaign/load-gate-extension.tsv"
logs="$campaign/load-gate-logs"
mkdir -p "$logs"
printf 'model\tresult\texit_code\n' > "$result"

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

sudo systemctl stop google-cloud-ops-agent.service
systemctl --user stop muta-gateway.service

candidates=(
    "MiniCPM5-2B-Q4_K_M.gguf"
    "LFM2.5-2.6B-QAD-Q4_0.gguf"
    "MiniCPM5-1B-Q4_K_M.gguf"
    "Qwen3.5-2B-Q4_K_M.gguf"
    "VibeThinker-1.5B-q4_k_m.gguf"
    "Falcon-H1R-0.6B-Q4_K_M.gguf"
    "nvidia_OpenReasoning-Nemotron-1.5B-Q4_K_M.gguf"
)

for model in "${candidates[@]}"; do
    if pgrep -af '[l]lama-(server|bench|cli)|[l]m_eval|[a]dtc_profiler' >/dev/null; then
        echo "unexpected model or profiler process before $model" >&2
        exit 1
    fi
    echo "load gate: $model"
    set +e
    timeout 300 "$bench" -m "$models/$model" -p 32 -n 4 -r 1 -ngl 0 \
        > "$logs/$model.log" 2>&1
    rc=$?
    set -e
    if [[ "$rc" == 0 ]]; then
        printf '%s\tpass\t0\n' "$model" >> "$result"
    else
        printf '%s\tfail\t%s\n' "$model" "$rc" >> "$result"
        tail -20 "$logs/$model.log"
    fi
done

cat "$result"
