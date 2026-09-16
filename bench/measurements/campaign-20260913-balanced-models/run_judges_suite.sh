#!/usr/bin/env bash
set -euo pipefail

repo="${1:-/home/elijahnelson/Muta}"
campaign="$repo/bench/measurements/campaign-20260913-balanced-models"
models_root="$campaign/models"
raw="$campaign/raw"
server="$repo/bench/.artifacts/llama.cpp-b10175/build/bin/llama-server"
mkdir -p "$raw" "$campaign/judges-server-logs"

exec 9>/tmp/muta-benchmark.lock
if ! flock -n 9; then
    echo "another Muta benchmark campaign holds /tmp/muta-benchmark.lock" >&2
    exit 1
fi

restore_services() {
    if [[ -n "${watchdog_pid:-}" ]]; then
        kill -TERM "$watchdog_pid" 2>/dev/null || true
        wait "$watchdog_pid" 2>/dev/null || true
    fi
    if [[ -n "${benchmark_pid:-}" ]]; then
        kill -CONT "$benchmark_pid" 2>/dev/null || true
        kill -TERM "$benchmark_pid" 2>/dev/null || true
        wait "$benchmark_pid" 2>/dev/null || true
    fi
    sudo systemctl start google-cloud-ops-agent.service || true
    systemctl --user start muta-gateway.service || true
}
trap restore_services EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

[[ -x "$server" ]] || { echo "missing judge-replay server: $server" >&2; exit 1; }
[[ ! -e "$raw/judges-responses.jsonl" ]] || {
    echo "$raw/judges-responses.jsonl already exists; refusing duplicate runs" >&2
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
    case "$filename" in
        MiniCPM5-2B-Q4_K_M.gguf|LFM2.5-2.6B-QAD-Q4_0.gguf|MiniCPM5-1B-Q4_K_M.gguf|Qwen3.5-2B-Q4_K_M.gguf|VibeThinker-1.5B-q4_k_m.gguf|Falcon-H1R-0.6B-Q4_K_M.gguf|nvidia_OpenReasoning-Nemotron-1.5B-Q4_K_M.gguf)
            [[ -f "$extension_gate" ]] || continue
            awk -F '\t' -v model="$filename" \
                '$1 == model && $2 == "pass" {found=1} END {exit !found}' "$extension_gate" || continue
            ;;
    esac
    models+=("$models_root/$filename")
done

[[ "${#models[@]}" -gt 0 ]] || { echo "no compatible judge-replay candidates found" >&2; exit 1; }
[[ "${#models[@]}" -eq "${#requested[@]}" ]] || {
    echo "judge replay requires all ${#requested[@]} validated artifacts; found ${#models[@]}" >&2
    exit 1
}

cd "$repo"
sudo systemctl stop google-cloud-ops-agent.service
systemctl --user stop muta-gateway.service

if pgrep -x llama-bench >/dev/null || pgrep -x llama-server >/dev/null || \
    pgrep -f '[l]m_eval' >/dev/null || pgrep -f '[a]dtc_profiler' >/dev/null; then
    echo "unexpected model or profiler process before judge replay" >&2
    exit 1
fi

echo "judge-prompt phase started $(date -u +%FT%TZ)"
bench/.venv-profiler/bin/python -m bench.run_judges_prompt_suite \
    --server "$server" \
    --models "${models[@]}" \
    --out "$raw/judges-responses.jsonl" \
    --events "$raw/judges-events.jsonl" \
    --logs "$campaign/judges-server-logs" \
    --port 18081 \
    --threads 2 \
    --hardware-context x86_cloud_proxy_gcp_n2_custom_4_8192_2c4t_scalar_b10175 &
benchmark_pid=$!
bash "$campaign/gcp_isolation_watchdog.sh" "$benchmark_pid" \
    >"$campaign/judges-isolation.log" 2>&1 &
watchdog_pid=$!
wait "$benchmark_pid"
benchmark_pid=""
wait "$watchdog_pid" || true
watchdog_pid=""
echo "judge-prompt phase ended $(date -u +%FT%TZ)"

bench/.venv-profiler/bin/python -m bench.judges_prompt_report \
    --responses "$raw/judges-responses.jsonl" \
    --events "$raw/judges-events.jsonl" \
    --artifacts "$campaign/artifacts.csv" \
    --csv "$campaign/judges-ranking.csv" \
    --report "$campaign/judges-report.md"
