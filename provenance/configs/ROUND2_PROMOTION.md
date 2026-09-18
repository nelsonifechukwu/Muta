# Round-two pilot compilation and promotion

Compile one immutable table snapshot after copying the Oracle and CSD3 run trees to
separate roots. A candidate ID may exist in only one root.

```bash
python model-development/finetune/compile_round2_pilots.py \
  --config provenance/configs/pilot-sweep.json \
  --run-root /path/to/oracle/pilots \
  --run-root /path/to/csd3/pilots \
  --protocol-deviation provenance/calibration/oracle-b64-20260918/protocol-deviation.json \
  --output provenance/results/pilots-YYYYMMDDTHHMMSSZ
```

The compiler verifies the frozen treatment, training-manifest and terminal-marker
binding, data fingerprints, row counts, metric hashes, adapter tree, completed step
count, and peak-VRAM receipt. It writes JSON, CSV, Markdown, and its own receipt.
Invalid, missing, running, incomplete, or failed pilots remain visible in the table
but make the compiler exit with status 2; only an all-complete table is promotion-ready.
Run it from a clean committed checkout: the compiler receipt captures repository
status before creating the result directory, and promotion rejects a dirty or
different compiler.

The protocol-deviation receipt narrowly binds the measured 64 × 1 implementation
override to the original 16 × 4 pilot config. Both have effective batch 64. The
compiler rejects any other split and verifies the raw calibration files.
It also groups completed pilots by exact Python/Torch/CUDA/package receipt. Mixed
groups remain visible as an experimental-confound warning; use a matched bridge
run before interpreting host-split results as a pure hyperparameter comparison.

After the matched-prompt evaluation has identified the best clean and warm pilots,
freeze the three full runs. Selection is always explicit; this command never chooses
a winner from loss alone. Every pilot adapter must appear complete in the same
immutable matched-prompt evidence tree.

```bash
python model-development/finetune/build_round2_promotions.py \
  --pilot-config provenance/configs/pilot-sweep.json \
  --pilot-results provenance/results/PILOT/pilot-results.json \
  --pilot-evaluation-dir provenance/evaluation/PILOT_MATCHED_PROMPTS \
  --best-clean-id CLEAN_ID \
  --best-warm-id WARM_ID \
  --rights-clean-rows 300000 \
  --clean-selection-note "Best clean candidate on the preregistered evaluation." \
  --warm-selection-note "Best warm candidate on the preregistered evaluation." \
  --output provenance/configs/full-runs.json
```

The frozen config contains exactly three treatments: best-clean private-enriched,
best-warm private-enriched, and the same warm hyperparameters with private sources
excluded. Each uses effective batch 64 and explicit quarter, half, and final-step
evaluation/checkpoint milestones.

Launch one treatment with the same verified base, tokenizer, training artifact, and
development artifact used by the pilot campaign:

```bash
python model-development/finetune/launch_round2_full.py \
  --config provenance/configs/full-runs.json \
  --candidate-id full-best-warm-rights-clean \
  --clean-base /path/to/upstream-qwen25 \
  --warm-base /path/to/incumbent-muta-merged \
  --clean-lineage /path/to/upstream-base.json \
  --warm-lineage /path/to/incumbent-recovery.json \
  --dataset-manifest /path/to/muta-stem-v2-sft-300k/manifest.json \
  --validation-manifest /path/to/round2-dev-5000/manifest.json \
  --output-root /path/to/runs/full
```

After an interrupted run, repeat the command with
`--resume-from-checkpoint /path/to/checkpoint-N`. The trainer rechecks the expected
row and step counts and the explicit milestone receipts before completion.
Checkpoint rotation retains at most three directories; the manifest separately
records every save callback so quarter/half/end evidence remains explicit.
