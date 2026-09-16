#!/usr/bin/env bash
set -euo pipefail

repo="${1:-/home/elijahnelson/Muta}"
campaign="$repo/bench/measurements/campaign-20260913-balanced-models"
models_root="$campaign/models"
raw="$campaign/raw"
mkdir -p "$raw" "$campaign/stem-server-logs"

restore_services() {
    sudo systemctl start google-cloud-ops-agent.service || true
    systemctl --user start muta-gateway.service || true
}
trap restore_services EXIT

models=(
    "$models_root/Muta-Tutor-Qwen2.5-1.5B-Finetuned-Q4_K_M.gguf"
    "$models_root/LFM2.5-1.2B-Thinking-Q4_0.gguf"
    "$models_root/MiniCPM5-1B-Q4_0.gguf"
    "$models_root/Qwen3.5-2B-Q4_0.gguf"
    "$models_root/Qwen3-1.7B-Q4_0.gguf"
    "$models_root/LFM2.5-2.6B-Q4_0.gguf"
)

cd "$repo"
sudo systemctl stop google-cloud-ops-agent.service
systemctl --user stop muta-gateway.service

if pgrep -x llama-bench >/dev/null || pgrep -x llama-server >/dev/null || \
    pgrep -f '[l]m_eval' >/dev/null || pgrep -f '[a]dtc_profiler' >/dev/null; then
    echo "unexpected model or profiler process before accuracy phase" >&2
    exit 1
fi

if [[ -e "$raw/accuracy.jsonl" ]]; then
    echo "$raw/accuracy.jsonl already exists; refusing to append a duplicate campaign" >&2
    exit 1
fi

echo "accuracy phase started $(date -u +%FT%TZ)"
bench/.venv-profiler/bin/python -m bench.adtc_bakeoff \
    --models "${models[@]}" \
    --accuracy \
    --tasks arc_easy:500 \
    --venv-python bench/.venv-profiler/bin/python \
    --hardware-context x86_cloud_proxy_gcp_n2_custom_4_8192_2c4t_official_accuracy \
    --out "$raw/accuracy.jsonl"
echo "accuracy phase ended $(date -u +%FT%TZ)"

if pgrep -x llama-bench >/dev/null || pgrep -x llama-server >/dev/null || \
    pgrep -f '[l]m_eval' >/dev/null || pgrep -f '[a]dtc_profiler' >/dev/null; then
    echo "unexpected model or profiler process before STEM phase" >&2
    exit 1
fi

if [[ -e "$raw/stem-responses.jsonl" ]]; then
    echo "$raw/stem-responses.jsonl already exists; refusing to append duplicate responses" >&2
    exit 1
fi

echo "STEM phase started $(date -u +%FT%TZ)"
bench/.venv-profiler/bin/python -m bench.run_stem_prompt_suite \
    --server bench/.artifacts/llama.cpp-b10175/build/bin/llama-server \
    --models "${models[@]}" \
    --out "$raw/stem-responses.jsonl" \
    --events "$raw/stem-events.jsonl" \
    --logs "$campaign/stem-server-logs" \
    --port 18080 \
    --threads 4
echo "STEM phase ended $(date -u +%FT%TZ)"

bench/.venv-profiler/bin/python -m bench.balanced_model_report \
    --throughput "$raw/throughput.jsonl" \
    --accuracy "$raw/accuracy.jsonl" \
    --artifacts "$campaign/artifacts.csv" \
    --stem "$raw/stem-responses.jsonl" \
    --csv "$campaign/results.csv" \
    --report "$campaign/report.md"

{
    date -u +%FT%TZ
    uptime
    free -h
    ps -eo pid,ppid,pcpu,pmem,comm,args --sort=-pcpu | head -20
} > "$campaign/system-after.txt"
