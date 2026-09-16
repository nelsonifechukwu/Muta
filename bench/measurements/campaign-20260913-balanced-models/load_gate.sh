#!/usr/bin/env bash
set -euo pipefail

repo="${1:-/home/elijahnelson/Muta}"
campaign="$repo/bench/measurements/campaign-20260913-balanced-models"
models="$campaign/models"
bench="$repo/bench/.artifacts/llama.cpp-b10175/build/bin/llama-bench"
result="$campaign/load-gate.tsv"
logs="$campaign/load-gate-logs"
mkdir -p "$logs"
printf 'model\tresult\texit_code\n' > "$result"

candidates=(
    "Muta-Tutor-Qwen2.5-1.5B-Finetuned-Q4_K_M.gguf"
    "LFM2.5-1.2B-Thinking-Q4_0.gguf"
    "MiniCPM5-1B-Q4_0.gguf"
    "Qwen3.5-2B-Q4_0.gguf"
    "Qwen3-1.7B-Q4_0.gguf"
    "LFM2.5-2.6B-Q4_0.gguf"
    "Spark-X2.5-1.7B-Q4_K_M.gguf"
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
