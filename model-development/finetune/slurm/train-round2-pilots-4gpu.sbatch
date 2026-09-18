#!/usr/bin/env bash
#SBATCH --job-name=muta-r2-pilot-4g
#SBATCH --account=mlmi-ein21-sl2-gpu
#SBATCH --partition=ampere
#SBATCH --qos=intr
#SBATCH --nodes=1
#SBATCH --ntasks=4
#SBATCH --gres=gpu:4
#SBATCH --cpus-per-task=8
#SBATCH --mem=256G
#SBATCH --time=00:27:30
#SBATCH --no-requeue
#SBATCH --export=NONE
#SBATCH --output=/rds/user/ein21/hpc-work/muta-round2/logs/%x-%j.out
#SBATCH --error=/rds/user/ein21/hpc-work/muta-round2/logs/%x-%j.err

set -euo pipefail

source /etc/profile.d/modules.sh
module purge
module load rhel8/default-amp
export SLURM_EXPORT_ENV=ALL

MUTA_WORK=/rds/user/ein21/hpc-work/muta-round2
export HF_HOME="$MUTA_WORK/cache/huggingface"
export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

source "$MUTA_WORK/env/bin/activate"

muta_pids=()
for muta_candidate_index in 0 1 2 3; do
  srun --exclusive --exact --nodes=1 --ntasks=1 --cpus-per-task=8 \
    --mem=60G --gres=gpu:1 --gpu-bind=single:1 --unbuffered \
    --output="$MUTA_WORK/logs/%x-%A_${muta_candidate_index}.out" \
    --error="$MUTA_WORK/logs/%x-%A_${muta_candidate_index}.err" \
    env UNSLOTH_COMPILE_LOCATION="$MUTA_WORK/cache/unsloth-${muta_candidate_index}" \
    python "$MUTA_WORK/repo/model-development/finetune/launch_round2.py" \
      --config "$MUTA_WORK/configs/pilot-sweep.json" \
      --candidate-index "$muta_candidate_index" \
      --host-filter csd3 \
      --clean-base "$MUTA_WORK/bases/upstream-qwen25" \
      --warm-base "$MUTA_WORK/bases/incumbent-muta-merged" \
      --clean-lineage "$MUTA_WORK/lineage/upstream-base.json" \
      --warm-lineage "$MUTA_WORK/lineage/incumbent-recovery.json" \
      --dataset-manifest "$MUTA_WORK/data/muta-stem-v2-sft-300k/manifest.json" \
      --validation-manifest "$MUTA_WORK/data/round2-dev-5000/manifest.json" \
      --output-root "$MUTA_WORK/runs/pilots" \
      --protocol-deviation "$MUTA_WORK/calibration/oracle-b64-20260918/protocol-deviation.json" \
      --batch-size 64 \
      --eval-batch-size 64 \
      --gradient-accumulation 1 \
      --dataloader-workers 8 &
  muta_pids+=("$!")
done

muta_status=0
for muta_pid in "${muta_pids[@]}"; do
  wait "$muta_pid" || muta_status=1
done
exit "$muta_status"
