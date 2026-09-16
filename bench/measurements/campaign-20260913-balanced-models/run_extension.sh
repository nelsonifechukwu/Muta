#!/usr/bin/env bash
set -euo pipefail

repo="${1:-/home/elijahnelson/Muta}"
campaign="$repo/bench/measurements/campaign-20260913-balanced-models"
models_root="$campaign/models"
raw="$campaign/raw"
mkdir -p "$raw" "$campaign/stem-server-logs"

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

requested=(
    "MiniCPM5-2B-Q4_K_M.gguf"
    "LFM2.5-2.6B-QAD-Q4_0.gguf"
    "MiniCPM5-1B-Q4_K_M.gguf"
    "Qwen3.5-2B-Q4_K_M.gguf"
    "VibeThinker-1.5B-q4_k_m.gguf"
    "Falcon-H1R-0.6B-Q4_K_M.gguf"
    "nvidia_OpenReasoning-Nemotron-1.5B-Q4_K_M.gguf"
)

gate="$campaign/load-gate-extension.tsv"
if [[ ! -f "$gate" ]]; then
    echo "missing $gate; run load_gate_extension.sh first" >&2
    exit 1
fi

models=()
for filename in "${requested[@]}"; do
    if awk -F '\t' -v model="$filename" '$1 == model && $2 == "pass" {found=1} END {exit !found}' "$gate"; then
        models+=("$models_root/$filename")
    fi
done
if [[ "${#models[@]}" == 0 ]]; then
    echo "no extension candidate passed the b10175 load gate" >&2
    exit 1
fi

for file in "${models[@]}"; do
    [[ -f "$file" ]] || { echo "missing model: $file" >&2; exit 1; }
    filename="${file##*/}"
    if rg -q "\"model\": \"$filename\"" "$raw/throughput.jsonl" "$raw/accuracy.jsonl" \
        "$raw/stem-responses.jsonl" 2>/dev/null; then
        echo "existing measurement found for $filename; refusing a duplicate extension" >&2
        exit 1
    fi
done

cd "$repo"
sudo systemctl stop google-cloud-ops-agent.service
systemctl --user stop muta-gateway.service

if pgrep -x llama-bench >/dev/null || pgrep -x llama-server >/dev/null || \
    pgrep -f '[l]m_eval' >/dev/null || pgrep -f '[a]dtc_profiler' >/dev/null; then
    echo "unexpected model or profiler process before extension" >&2
    exit 1
fi

echo "extension throughput phase started $(date -u +%FT%TZ)"
bench/.venv-profiler/bin/python -m bench.adtc_bakeoff \
    --models "${models[@]}" \
    --bench "scalar=bench/.artifacts/llama.cpp-b10175/build/bin/llama-bench" \
    --rounds 1 \
    --reps 5 \
    --hardware-context x86_cloud_proxy_gcp_n2_custom_4_8192_2c4t_scalar_b10175 \
    --out "$raw/throughput.jsonl"
echo "extension throughput phase ended $(date -u +%FT%TZ)"

if pgrep -x llama-bench >/dev/null || pgrep -x llama-server >/dev/null || \
    pgrep -f '[l]m_eval' >/dev/null || pgrep -f '[a]dtc_profiler' >/dev/null; then
    echo "unexpected model or profiler process before extension accuracy" >&2
    exit 1
fi

echo "extension accuracy phase started $(date -u +%FT%TZ)"
bench/.venv-profiler/bin/python -m bench.adtc_bakeoff \
    --models "${models[@]}" \
    --accuracy \
    --tasks arc_easy:500 \
    --venv-python bench/.venv-profiler/bin/python \
    --hardware-context x86_cloud_proxy_gcp_n2_custom_4_8192_2c4t_official_accuracy \
    --out "$raw/accuracy.jsonl"
echo "extension accuracy phase ended $(date -u +%FT%TZ)"

if pgrep -x llama-bench >/dev/null || pgrep -x llama-server >/dev/null || \
    pgrep -f '[l]m_eval' >/dev/null || pgrep -f '[a]dtc_profiler' >/dev/null; then
    echo "unexpected model or profiler process before extension STEM phase" >&2
    exit 1
fi

echo "extension STEM phase started $(date -u +%FT%TZ)"
bench/.venv-profiler/bin/python -m bench.run_stem_prompt_suite \
    --server bench/.artifacts/llama.cpp-b10175/build/bin/llama-server \
    --models "${models[@]}" \
    --out "$raw/stem-responses.jsonl" \
    --events "$raw/stem-events.jsonl" \
    --logs "$campaign/stem-server-logs" \
    --port 18080 \
    --threads 4
echo "extension STEM phase ended $(date -u +%FT%TZ)"

bench/.venv-profiler/bin/python -m bench.balanced_model_report \
    --throughput "$raw/throughput.jsonl" \
    --vector-throughput "$raw/vector-throughput.jsonl" \
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
} > "$campaign/system-after-extension.txt"
