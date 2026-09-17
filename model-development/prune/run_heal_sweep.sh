#!/usr/bin/env bash
# Heal each shortlisted pruned checkpoint with the recorded LoRA recipe on licensed-hybrid;
# train an unpruned control with the identical recipe so the pruning cost is isolated.
# Usage (GPU host): SPECS="21L-contiguous 24L-contiguous" BEST=21L-contiguous ./run_heal_sweep.sh
# Re-runs resume: training is skipped when training-manifest.json exists, export when the
# export manifest exists, so a failed export is retried without retraining. Exits 1 on any FAIL.
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
FAILS=0

fail() {  # name stage
  echo "FAIL $1 ($2) $(date -u +%FT%TZ)"; tail -30 "$RUNS/logs/$1.log"; FAILS=$((FAILS + 1))
}

heal() {  # name source lr steps
  local name=$1 source=$2 lr=$3 steps=$4 out="$RUNS/$1"
  if [[ -f "$out/training-manifest.json" ]]; then
    echo "SKIP train $name (manifest exists)"
  else
    echo "START $name $(date -u +%FT%TZ)"
    if ! "$PY" "$FT/train_lora.py" --model "$source" --revision local \
         --train "$DATA/train.jsonl" --validation "$DATA/validation.jsonl" --output "$out" \
         --rank 16 --learning-rate "$lr" --max-steps "$steps" --eval-steps 250 \
         > "$RUNS/logs/$name.log" 2>&1; then
      fail "$name" train; return 1
    fi
  fi
  if [[ -f "$out/$name.export-manifest.json" ]]; then
    echo "SKIP export $name (manifest exists)"
  else
    if ! LLAMA_DIR="$LLAMA_DIR" "$HERE/export_gguf.sh" "$out/merged_16bit" "$out/$name" "$PY" \
         >> "$RUNS/logs/$name.log" 2>&1; then
      fail "$name" export; return 1
    fi
  fi
  # The exported GGUF must have the depth and parameter count of the checkpoint we healed.
  if [[ -f "$source/prune-manifest.json" ]]; then
    if ! "$PY" - "$source/prune-manifest.json" "$out/$name.export-manifest.json" <<'PYCHK' >> "$RUNS/logs/$name.log" 2>&1
import json, sys
p, e = (json.load(open(a)) for a in sys.argv[1:3])
ok = p["params_count"] == e["params_count"] and p["num_hidden_layers"] == e["block_count"]
print("depth/params cross-check", "OK" if ok else "MISMATCH", p["num_hidden_layers"], e["block_count"], p["params_count"], e["params_count"])
sys.exit(0 if ok else 1)
PYCHK
    then fail "$name" cross-check; return 1; fi
  fi
  echo "PASS $name $(date -u +%FT%TZ)"
}

heal control-28L-hybrid-lr5e5-1000 "$RUNS/tutor-28L/merged_16bit" 5e-5 1000
for spec in $SPECS; do
  heal "heal-$spec-lr5e5-1000" "$RUNS/pruned-$spec" 5e-5 1000
done
heal "heal-$BEST-lr2e5-1000" "$RUNS/pruned-$BEST" 2e-5 1000
echo "HEAL_DONE fails=$FAILS $(date -u +%FT%TZ)"
[[ $FAILS -eq 0 ]]
