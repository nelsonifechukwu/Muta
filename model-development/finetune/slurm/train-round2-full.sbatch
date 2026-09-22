#!/usr/bin/env bash
#SBATCH --job-name=muta-r2-full-warm
#SBATCH --account=mlmi-ein21-sl2-gpu
#SBATCH --partition=ampere
#SBATCH --qos=gpu1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=03:00:00
#SBATCH --no-requeue
#SBATCH --export=NONE
#SBATCH --open-mode=append
#SBATCH --output=/rds/user/ein21/hpc-work/muta-round2/logs/%x-%j.out
#SBATCH --error=/rds/user/ein21/hpc-work/muta-round2/logs/%x-%j.err

# Submit only after the current-source smoke and budget/readiness gates pass:
# sbatch train-round2-full.sbatch /absolute/snapshot /absolute/config.json SHA256
# This entry point is fresh-warm only. It never resumes or initializes a pilot.
set -euo pipefail
umask 077

if [[ $# -ne 3 || ! "$3" =~ ^[0-9a-f]{64}$ ]]; then
  printf '%s\n' 'Usage: sbatch train-round2-full.sbatch SNAPSHOT_ROOT CONFIG_PATH EXPECTED_CONFIG_SHA256' >&2
  exit 2
fi
MUTA_SNAPSHOT=$1
MUTA_CONFIG=$2
MUTA_CONFIG_SHA256=$3
if [[ "$MUTA_SNAPSHOT" != /* || "$MUTA_CONFIG" != /* ]]; then
  printf '%s\n' 'Snapshot and config paths must be absolute.' >&2
  exit 2
fi
: "${SLURM_JOB_ID:?This script must run within a Slurm job.}"
: "${SLURM_CPUS_PER_TASK:?Missing Slurm CPU allocation.}"

source /etc/profile.d/modules.sh
module purge
module load rhel8/default-amp
export SLURM_EXPORT_ENV=ALL

MUTA_WORK=/rds/user/ein21/hpc-work/muta-round2
MUTA_OUTPUT_ROOT="$MUTA_WORK/runs/full"
MUTA_CANDIDATE=full-best-warm-private-enriched
MUTA_OUTPUT="$MUTA_OUTPUT_ROOT/$MUTA_CANDIDATE"
MUTA_PYTHON="$MUTA_WORK/env/bin/python"
export HF_HOME="$MUTA_WORK/cache/huggingface"
export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export UNSLOTH_COMPILE_LOCATION="$MUTA_WORK/cache/unsloth-full-warm-$SLURM_JOB_ID"
source "$MUTA_WORK/env/bin/activate"

# Validate the exact config/source snapshot before atomically claiming the stable
# candidate directory. A duplicate submission or prior failed run is not reused.
"$MUTA_PYTHON" - "$MUTA_SNAPSHOT" "$MUTA_CONFIG" "$MUTA_CONFIG_SHA256" \
  "$MUTA_OUTPUT" "$SLURM_JOB_ID" "${BASH_SOURCE[0]}" <<'PY'
import hashlib
import json
import sys
import time
from pathlib import Path

snapshot, config, expected, output, job_id, batch_script = sys.argv[1:]
snapshot, config, output = Path(snapshot), Path(config), Path(output)
sys.path.insert(0, str(snapshot / "model-development/finetune"))
from launch_round2_full import load_frozen_config, select_candidate

frozen, digest = load_frozen_config(config, expected_sha256=expected)
candidate = select_candidate(
    frozen, candidate_id="full-best-warm-private-enriched", candidate_index=None
)
if (
    frozen["schema_version"] != 3
    or candidate["planned_rows"] != 300350
    or candidate["lineage"] != "warm"
    or candidate["private_policy"] != "include"
    or candidate.get("initial_adapter_tree_sha256") is not None
    or candidate.get("initialization") != "fresh_adapter"
):
    raise SystemExit("This job permits only the frozen v3 fresh-warm 300350-row treatment")
if output.parent.is_symlink() or output.is_symlink():
    raise SystemExit("Refusing a symlinked full-run output directory")
output.parent.mkdir(parents=True, exist_ok=True)
output.mkdir(exist_ok=False)
receipt = {
    "schema_version": 1,
    "kind": "exclusive_fresh_slurm_run_claim",
    "created_unix": time.time(),
    "slurm_job_id": job_id,
    "snapshot": str(snapshot.resolve()),
    "config": str(config.resolve()),
    "config_sha256": digest,
    "source_code": frozen["source_code"],
    "candidate": candidate,
    "slurm_script_sha256": hashlib.sha256(Path(batch_script).read_bytes()).hexdigest(),
}
with (output / "slurm-claim.json").open("x", encoding="utf-8") as handle:
    json.dump(receipt, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY

MUTA_EVENT_LOG="$MUTA_OUTPUT/slurm-events.log"
trap 'MUTA_EXIT_CODE=$?; printf "exit_epoch=%s exit_code=%s job_id=%s\n" "$(date +%s)" "$MUTA_EXIT_CODE" "$SLURM_JOB_ID" >> "$MUTA_EVENT_LOG"' EXIT
printf 'start_epoch=%s job_id=%s candidate=%s config_sha256=%s\n' \
  "$(date +%s)" "$SLURM_JOB_ID" "$MUTA_CANDIDATE" "$MUTA_CONFIG_SHA256" >> "$MUTA_EVENT_LOG"
cd "$MUTA_SNAPSHOT"
srun --unbuffered "$MUTA_PYTHON" \
  "$MUTA_SNAPSHOT/model-development/finetune/launch_round2_full.py" \
  --config "$MUTA_CONFIG" \
  --expected-config-sha256 "$MUTA_CONFIG_SHA256" \
  --candidate-id "$MUTA_CANDIDATE" \
  --python "$MUTA_PYTHON" \
  --clean-base "$MUTA_WORK/bases/upstream-qwen25" \
  --warm-base "$MUTA_WORK/bases/incumbent-muta-merged" \
  --clean-lineage "$MUTA_WORK/lineage/upstream-base.json" \
  --warm-lineage "$MUTA_WORK/lineage/incumbent-recovery.json" \
  --dataset-manifest "$MUTA_WORK/data/muta-stem-v2-sft-300k/manifest.json" \
  --validation-manifest "$MUTA_WORK/data/round2-dev-5000/manifest.json" \
  --output-root "$MUTA_OUTPUT_ROOT" \
  --dataloader-workers 8
