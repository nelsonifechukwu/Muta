#!/usr/bin/env bash
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="${VENV_PATH:-$HERE/.venv}"
RUN_ROOT="${RUN_ROOT:-$HERE/runs}"
BALANCED_DATA="${BALANCED_DATA:-$HERE/data}"
REASONING_DATA="${REASONING_DATA:-$HERE/data-reasoning}"
PYTHON="$VENV_PATH/bin/python"

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
export TOKENIZERS_PARALLELISM=false
export HF_XET_HIGH_PERFORMANCE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

mkdir -p "$RUN_ROOT/logs"
if [[ ! -f "$REASONING_DATA/manifest.json" ]]; then
  "$PYTHON" "$HERE/build_dataset.py" \
    --output "$REASONING_DATA" --profile reasoning-heavy \
    >"$RUN_ROOT/logs/dataset-reasoning-heavy.log" 2>&1
fi

run_one() {
  local name="$1"
  shift
  local output="$RUN_ROOT/$name"
  local log="$RUN_ROOT/logs/$name.log"
  if [[ -f "$output/training-manifest.json" ]]; then
    printf 'SKIP %s (manifest exists)\n' "$name"
    return 0
  fi
  printf 'START %s\n' "$name"
  if "$PYTHON" "$HERE/train_lora.py" \
    --output "$output" --legacy-raw-concatenation "$@" >"$log" 2>&1; then
    printf 'PASS %s\n' "$name"
  else
    printf 'FAIL %s\n' "$name"
    tail -40 "$log"
  fi
}

Q35_REV="2fc06364715b967f1860aea9cf38778875588b17"
Q25_REV="989aa7980e4cf806f80c7fef2b1adb7bc71aa306"

# Full BF16 controls for both submission lanes.
run_one qwen35-bf16-r16-balanced-full \
  --model Qwen/Qwen3.5-0.8B --revision "$Q35_REV" \
  --train "$BALANCED_DATA/train.jsonl" --validation "$BALANCED_DATA/validation.jsonl" \
  --rank 16 --learning-rate 1e-4 --epochs 1 --eval-steps 100 --gguf-method q4_0

run_one qwen25-bf16-r16-balanced-full \
  --model Qwen/Qwen2.5-1.5B-Instruct --revision "$Q25_REV" \
  --train "$BALANCED_DATA/train.jsonl" --validation "$BALANCED_DATA/validation.jsonl" \
  --rank 16 --learning-rate 1e-4 --epochs 1 --eval-steps 100 --gguf-method q4_k_m

# Three 250-step branches per architecture: lower-rank, higher-rank/lower-LR, and QLoRA.
run_one qwen35-bf16-r8-balanced-250 \
  --model Qwen/Qwen3.5-0.8B --revision "$Q35_REV" \
  --train "$BALANCED_DATA/train.jsonl" --validation "$BALANCED_DATA/validation.jsonl" \
  --rank 8 --learning-rate 1e-4 --max-steps 250 --eval-steps 125 --gguf-method q4_0

run_one qwen35-bf16-r32-reasoning-250 \
  --model Qwen/Qwen3.5-0.8B --revision "$Q35_REV" \
  --train "$REASONING_DATA/train.jsonl" --validation "$REASONING_DATA/validation.jsonl" \
  --rank 32 --learning-rate 5e-5 --max-steps 250 --eval-steps 125 --gguf-method q4_0

run_one qwen35-qlora-r16-reasoning-250 \
  --model Qwen/Qwen3.5-0.8B --revision "$Q35_REV" \
  --train "$REASONING_DATA/train.jsonl" --validation "$REASONING_DATA/validation.jsonl" \
  --rank 16 --learning-rate 1e-4 --max-steps 250 --eval-steps 125 --qlora --gguf-method q4_0

run_one qwen25-bf16-r8-balanced-250 \
  --model Qwen/Qwen2.5-1.5B-Instruct --revision "$Q25_REV" \
  --train "$BALANCED_DATA/train.jsonl" --validation "$BALANCED_DATA/validation.jsonl" \
  --rank 8 --learning-rate 1e-4 --max-steps 250 --eval-steps 125 --gguf-method q4_k_m

run_one qwen25-bf16-r32-reasoning-250 \
  --model Qwen/Qwen2.5-1.5B-Instruct --revision "$Q25_REV" \
  --train "$REASONING_DATA/train.jsonl" --validation "$REASONING_DATA/validation.jsonl" \
  --rank 32 --learning-rate 5e-5 --max-steps 250 --eval-steps 125 --gguf-method q4_k_m

run_one qwen25-qlora-r16-reasoning-250 \
  --model Qwen/Qwen2.5-1.5B-Instruct --revision "$Q25_REV" \
  --train "$REASONING_DATA/train.jsonl" --validation "$REASONING_DATA/validation.jsonl" \
  --rank 16 --learning-rate 1e-4 --max-steps 250 --eval-steps 125 --qlora --gguf-method q4_k_m
