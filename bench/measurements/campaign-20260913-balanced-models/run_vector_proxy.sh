#!/usr/bin/env bash
set -euo pipefail

repo="${1:-/home/elijahnelson/Muta}"
campaign="$repo/bench/measurements/campaign-20260913-balanced-models"
models_root="$campaign/models"
raw="$campaign/raw"
vector_bench="$repo/bench/.artifacts/llama.cpp-b10175/build-avx2-rerun-20260819/bin/llama-bench"
mkdir -p "$raw"

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

[[ -x "$vector_bench" ]] || { echo "missing vector binary: $vector_bench" >&2; exit 1; }
[[ ! -e "$raw/vector-throughput.jsonl" ]] || {
    echo "$raw/vector-throughput.jsonl already exists; refusing duplicate runs" >&2
    exit 1
}

requested=(
    "Muta-Tutor-Qwen2.5-1.5B-Finetuned-Q4_K_M.gguf"
    "LFM2.5-1.2B-Thinking-Q4_0.gguf"
    "MiniCPM5-1B-Q4_0.gguf"
    "Qwen3.5-2B-Q4_0.gguf"
    "Qwen3-1.7B-Q4_0.gguf"
    "LFM2.5-2.6B-Q4_0.gguf"
    "MiniCPM5-2B-Q4_K_M.gguf"
    "LFM2.5-2.6B-QAD-Q4_0.gguf"
    "MiniCPM5-1B-Q4_K_M.gguf"
    "Qwen3.5-2B-Q4_K_M.gguf"
    "VibeThinker-1.5B-q4_k_m.gguf"
    "Falcon-H1R-0.6B-Q4_K_M.gguf"
    "nvidia_OpenReasoning-Nemotron-1.5B-Q4_K_M.gguf"
)

extension_gate="$campaign/load-gate-extension.tsv"
models=()
for filename in "${requested[@]}"; do
    [[ -f "$models_root/$filename" ]] || continue
    if [[ "$filename" == "MiniCPM5-2B-Q4_K_M.gguf" || \
          "$filename" == "LFM2.5-2.6B-QAD-Q4_0.gguf" || \
          "$filename" == "MiniCPM5-1B-Q4_K_M.gguf" || \
          "$filename" == "Qwen3.5-2B-Q4_K_M.gguf" || \
          "$filename" == "VibeThinker-1.5B-q4_k_m.gguf" || \
          "$filename" == "Falcon-H1R-0.6B-Q4_K_M.gguf" || \
          "$filename" == "nvidia_OpenReasoning-Nemotron-1.5B-Q4_K_M.gguf" ]]; then
        [[ -f "$extension_gate" ]] || continue
        awk -F '\t' -v model="$filename" \
            '$1 == model && $2 == "pass" {found=1} END {exit !found}' "$extension_gate" || continue
    fi
    models+=("$models_root/$filename")
done

[[ "${#models[@]}" -gt 0 ]] || { echo "no compatible vector candidates found" >&2; exit 1; }

cd "$repo"
sudo systemctl stop google-cloud-ops-agent.service
systemctl --user stop muta-gateway.service

if pgrep -x llama-bench >/dev/null || pgrep -x llama-server >/dev/null || \
    pgrep -f '[l]m_eval' >/dev/null || pgrep -f '[a]dtc_profiler' >/dev/null; then
    echo "unexpected model or profiler process before vector phase" >&2
    exit 1
fi

echo "vector throughput phase started $(date -u +%FT%TZ)"
bench/.venv-profiler/bin/python -m bench.adtc_bakeoff \
    --models "${models[@]}" \
    --bench "vector=$vector_bench" \
    --rounds 1 \
    --reps 5 \
    --hardware-context x86_cloud_proxy_gcp_n2_custom_4_8192_2c4t_vector_b10175 \
    --out "$raw/vector-throughput.jsonl"
echo "vector throughput phase ended $(date -u +%FT%TZ)"
