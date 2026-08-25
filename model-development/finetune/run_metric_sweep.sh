#!/usr/bin/env bash
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="${VENV_PATH:-$HERE/.venv}"
RUN_ROOT="${RUN_ROOT:-$HERE/runs-metric}"
MCQ_DATA="${MCQ_DATA:-$HERE/data-metric-mcq}"
HYBRID_DATA="${HYBRID_DATA:-$HERE/data-metric-hybrid}"
LICENSED_DATA="${LICENSED_DATA:-$HERE/data-metric-licensed-hybrid}"
LICENSED_MCQ_DATA="${LICENSED_MCQ_DATA:-$HERE/data-metric-licensed-mcq}"
PYTHON="$VENV_PATH/bin/python"

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
export TOKENIZERS_PARALLELISM=false
export HF_XET_HIGH_PERFORMANCE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

mkdir -p "$RUN_ROOT/logs"

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
  if "$PYTHON" "$HERE/train_lora.py" --output "$output" "$@" >"$log" 2>&1; then
    printf 'PASS %s\n' "$name"
  else
    printf 'FAIL %s\n' "$name"
    tail -40 "$log"
  fi
}

Q35_REV="2fc06364715b967f1860aea9cf38778875588b17"
Q25_REV="989aa7980e4cf806f80c7fef2b1adb7bc71aa306"

# Lower learning rates test whether the first sweep's metric regression was forgetting.
run_one qwen25-bf16-r16-mcq-lr2e5-500 \
  --model Qwen/Qwen2.5-1.5B-Instruct --revision "$Q25_REV" \
  --train "$MCQ_DATA/train.jsonl" --validation "$MCQ_DATA/validation.jsonl" \
  --rank 16 --learning-rate 2e-5 --max-steps 500 --eval-steps 250 \
  --gguf-method q4_k_m

run_one qwen25-bf16-r16-hybrid-lr2e5-500 \
  --model Qwen/Qwen2.5-1.5B-Instruct --revision "$Q25_REV" \
  --train "$HYBRID_DATA/train.jsonl" --validation "$HYBRID_DATA/validation.jsonl" \
  --rank 16 --learning-rate 2e-5 --max-steps 500 --eval-steps 250 \
  --gguf-method q4_k_m

run_one qwen25-bf16-r32-mcq-lr1e5-250 \
  --model Qwen/Qwen2.5-1.5B-Instruct --revision "$Q25_REV" \
  --train "$MCQ_DATA/train.jsonl" --validation "$MCQ_DATA/validation.jsonl" \
  --rank 32 --learning-rate 1e-5 --max-steps 250 --eval-steps 125 \
  --gguf-method q4_k_m

# QLoRA is repeated on the corrected data so method and dataset effects are separable.
run_one qwen25-qlora-r16-mcq-lr2e5-250 \
  --model Qwen/Qwen2.5-1.5B-Instruct --revision "$Q25_REV" \
  --train "$MCQ_DATA/train.jsonl" --validation "$MCQ_DATA/validation.jsonl" \
  --rank 16 --learning-rate 2e-5 --max-steps 250 --eval-steps 125 --qlora \
  --gguf-method q4_k_m

# The smaller scalar-lane model receives one low-LR metric-aligned control.
run_one qwen35-bf16-r16-mcq-lr2e5-400 \
  --model Qwen/Qwen3.5-0.8B --revision "$Q35_REV" \
  --train "$MCQ_DATA/train.jsonl" --validation "$MCQ_DATA/validation.jsonl" \
  --rank 16 --learning-rate 2e-5 --max-steps 400 --eval-steps 200 \
  --gguf-method q4_0

# Known-licence control: excludes OpenBookQA because its current dataset card has no licence.
run_one qwen25-bf16-r16-licensed-mcq-lr2e5-500 \
  --model Qwen/Qwen2.5-1.5B-Instruct --revision "$Q25_REV" \
  --train "$LICENSED_MCQ_DATA/train.jsonl" --validation "$LICENSED_MCQ_DATA/validation.jsonl" \
  --rank 16 --learning-rate 2e-5 --max-steps 500 --eval-steps 250 \
  --gguf-method q4_k_m

run_one qwen25-bf16-r16-licensed-hybrid-lr2e5-500 \
  --model Qwen/Qwen2.5-1.5B-Instruct --revision "$Q25_REV" \
  --train "$LICENSED_DATA/train.jsonl" --validation "$LICENSED_DATA/validation.jsonl" \
  --rank 16 --learning-rate 2e-5 --max-steps 500 --eval-steps 250 \
  --gguf-method q4_k_m
