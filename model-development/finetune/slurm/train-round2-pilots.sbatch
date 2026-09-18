#!/usr/bin/env bash
#SBATCH --job-name=muta-r2-pilot
#SBATCH --account=mlmi-ein21-sl2-gpu
#SBATCH --partition=ampere
#SBATCH --qos=gpu1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=00:30:00
#SBATCH --array=0-3%4
#SBATCH --no-requeue
#SBATCH --signal=B:USR1@90
#SBATCH --export=NONE
#SBATCH --output=/rds/user/ein21/hpc-work/muta-round2/logs/%x-%A_%a.out
#SBATCH --error=/rds/user/ein21/hpc-work/muta-round2/logs/%x-%A_%a.err

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

srun --unbuffered python "$MUTA_WORK/training/launch_round2.py" \
  --config "$MUTA_WORK/configs/pilot-sweep.json" \
  --candidate-index "$SLURM_ARRAY_TASK_ID" \
  --host-filter csd3 \
  --clean-base "$MUTA_WORK/bases/upstream-qwen25" \
  --warm-base "$MUTA_WORK/bases/incumbent-muta-merged" \
  --clean-lineage "$MUTA_WORK/lineage/upstream-base.json" \
  --warm-lineage "$MUTA_WORK/lineage/incumbent-recovery.json" \
  --dataset-manifest "$MUTA_WORK/data/muta-stem-v2-sft-300k/manifest.json" \
  --validation-manifest "$MUTA_WORK/data/round2-dev-5000/manifest.json" \
  --output-root "$MUTA_WORK/runs/pilots" \
  --batch-size 64 \
  --eval-batch-size 64 \
  --gradient-accumulation 1 \
  --dataloader-workers 8
