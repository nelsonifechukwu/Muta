#!/usr/bin/env bash
# Heal each shortlisted pruned checkpoint with the recorded LoRA recipe on licensed-hybrid;
# train an unpruned control with the identical recipe so the pruning cost is isolated.
# Usage (GPU host): SPECS="21L-contiguous 24L-contiguous" BEST=21L-contiguous ./run_heal_sweep.sh
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FT="$HERE/../finetune"
PY="${PY:-$FT/.venv/bin/python}"
DATA="${DATA:-$FT/data-metric-licensed-hybrid}"
RUNS="$HERE/runs-prune"
LLAMA_DIR="${LLAMA_DIR:?}"
SPECS="${SPECS:?space-separated e.g. '21L-contiguous 24L-contiguous'}"
BEST="${BEST:?the first spec to also heal at lr 2e-5}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}" TOKENIZERS_PARALLELISM=false PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
mkdir -p "$RUNS/logs"

heal() {  # name source lr steps
  local name=$1 source=$2 lr=$3 steps=$4 out="$RUNS/$1"
  if [[ -f "$out/training-manifest.json" ]]; then echo "SKIP $name"; return 0; fi
  echo "START $name $(date -u +%FT%TZ)"
  if "$PY" "$FT/train_lora.py" --model "$source" --revision local \
       --train "$DATA/train.jsonl" --validation "$DATA/validation.jsonl" --output "$out" \
       --rank 16 --learning-rate "$lr" --max-steps "$steps" --eval-steps 250 \
       > "$RUNS/logs/$name.log" 2>&1 \
     && LLAMA_DIR="$LLAMA_DIR" "$HERE/export_gguf.sh" "$out/merged_16bit" "$out/$name" "$PY" >> "$RUNS/logs/$name.log" 2>&1; then
    echo "PASS $name"
  else
    echo "FAIL $name"; tail -30 "$RUNS/logs/$name.log"
  fi
}

heal control-28L-hybrid-lr5e5-1000 "$RUNS/tutor-28L/merged_16bit" 5e-5 1000
for spec in $SPECS; do
  heal "heal-$spec-lr5e5-1000" "$RUNS/pruned-$spec" 5e-5 1000
done
heal "heal-$BEST-lr2e5-1000" "$RUNS/pruned-$BEST" 2e-5 1000
echo "HEAL_DONE $(date -u +%FT%TZ)"
