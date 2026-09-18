# Muta proof of training

This directory is the Gate 2 evidence bundle for the 2026-09-18 Muta round-two
fine-tuning campaign. Generated claims are accepted only when their files and
SHA-256 receipts agree.

## Campaign matrix

| Control or treatment | Parent | Purpose |
|---|---|---|
| Upstream control | pinned Qwen2.5-1.5B-Instruct | Unmodified matched-export control |
| Incumbent Muta | published Q4_K_M, SHA `a750d00d...` | Previous best model |
| Clean pilots | pinned Qwen + 300K STEM | Isolate the new dataset effect |
| Warm pilots | merged incumbent Muta + 300K STEM | Direct continuation requested for Muta |
| Rights-clean finalist | Muta/DeepMind 300,000 rows | Distribution-safe fallback |
| Private-enriched finalist | all 300,350 rows | Private competition/practice candidate |

The warm lineage is explicitly two-stage. Its first stage used the prior
licence-clean ARC/QASC MCQ mixture. No old adapter is applied twice: the new
adapter is trained over the already-merged incumbent checkpoint.

## Required final contents

| Path | Evidence |
|---|---|
| `lineage/` | base, incumbent, adapter, merged-checkpoint and GGUF receipts |
| `dataset/` | source/licence description, safe sample, manifests and split proof |
| `configs/` | preregistered sweep and every resolved run config |
| `scripts/` | frozen train, merge, quantize, evaluate and collection scripts |
| `runs/` | adapters, logs, Trainer state, metrics and loss curves |
| `evaluation/` | full identical-prompt outputs and score tables |
| `selected/` | winning adapter, hashes, merge and Q4_K_M receipts |

The full 300,350-row dataset stays private. Any public representative sample
must contain only `muta_verified_stem_v2` or `deepmind_mathematics` records.
The 350 WAEC/Cheetah rows remain labelled private-use/restricted; project-owner
approval is not described as a publisher licence.

Training is performed on SSH/Slurm GPU hosts, not a hosted notebook. Therefore
the notebook-link requirement is not applicable; host receipts and Slurm job
IDs replace it.
