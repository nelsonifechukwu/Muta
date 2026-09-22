# Round-two pilot compilation and promotion

## Current execution: schema v3

The user authorized these **three** all-data treatments. The private-exclusion
ablation is cancelled; it must not be launched from a historical v1/v2 config.

| ID | Initialization | Rows | LoRA / LR |
|---|---|---:|---|
| `full-best-clean-private-enriched` | Fresh adapter on original Qwen | 300,350 | r16 / 1e-5 |
| `full-best-warm-private-enriched` | Fresh adapter on recovered Muta v1 merged parent | 300,350 | r16 / 5e-6 |
| `full-best-warm-pilot-continuation` | Exact selected `warm-r16-lr5e6` pilot adapter on its original Muta v1 parent | 300,350 additional | r16 / 5e-6 |

All stages use one epoch, context 512, effective batch 64 (64 × 1), BF16,
completion-only loss, seed 3407, checkpoints/evaluation at 1,174 / 2,347 / 4,693
optimizer steps. Continuation resets the optimizer and learning-rate schedule;
it is not a checkpoint resume of the pilot. Its prior 20K exposure remains part
of its training history. Keep the unchanged pilot as an evaluation control.

The new trainer hash invalidates the earlier 12-step resume proof as a current
launch gate. Preserve it as historical evidence. Before freezing v3, run:

1. A fresh clean 24-step smoke, milestones 6/12/24, logging every step.
2. A separate warm pilot-continuation 24-step stage, actually interrupt it with
   SIGTERM after checkpoint 6, then resume that same stage to step 24. Preserve
   the process record, initial resolved config, checkpoint-6 state and immutable
   adapter-initialization sessions. The initial session must prove exact pilot
   tensor values were copied once; the resumed session must defer to its own
   checkpoint without reapplying pilot initialization.

Both use subsets from the exact verified training/development manifests. The
validator checks actual per-step metrics, checkpoint state, minimum-loss adapter,
tensor structure, terminal hashes and original loss-curve receipts. It numerically
checks every SVG data point against recorded metrics and hashes the original PNG;
it does **not** require matching Matplotlib versions or byte-identical pixels
rendered on another OS. No curves or metrics are invented or regenerated.

```bash
python model-development/finetune/build_round2_promotions.py \
  --pilot-config provenance/configs/pilot-sweep.json \
  --pilot-results provenance/results/pilots-combined-20260918/pilot-results.json \
  --canonical-comparison-dir provenance/results/all-gguf-cuda-comparison-20260918 \
  --export-root provenance/exports \
  --current-smoke-dir /path/to/fresh-clean-24 \
  --current-resume-dir /path/to/warm-continuation-resumed-24 \
  --interruption-receipt /path/to/interruption.json \
  --best-clean-id clean-r16-lr1e5 \
  --best-warm-id warm-r16-lr5e6 \
  --clean-selection-note "STEM priority; judges regressed 34 vs 47 against clean-r32." \
  --warm-selection-note "Written/judges leader; reviewed MC regressions disclosed." \
  --output provenance/configs/full-runs-v3.json
```

Freeze the resulting **byte SHA256** independently in the launch command/receipt.
The v3 launcher requires `--expected-config-sha256`; recomputing a local sidecar
does not substitute for that external expected digest. It also checks the exact
builder/helper/launcher/trainer source hashes and all supplied runtime input
paths (base trees, lineage files, tokenizer, dataset and validation shards) before
spawning the trainer. Source snapshots may have no Git metadata: their actual
hashes are authoritative, and no false claim of a clean committed checkout is
made. The evidence tree can be staged on Oracle to avoid copying large smoke
checkpoints to the Mac. Old absolute comparison-input paths relocate only through
their repository-relative `provenance/` suffix, still requiring the pinned bytes.

```bash
python model-development/finetune/launch_round2_full.py \
  --config provenance/configs/full-runs-v3.json \
  --expected-config-sha256 FROZEN_BYTE_SHA256 \
  --candidate-id full-best-warm-pilot-continuation \
  --initial-adapter /path/to/selected-warm-pilot/adapter \
  --clean-base /path/to/upstream-qwen25 \
  --warm-base /path/to/incumbent-muta-merged \
  --clean-lineage /path/to/upstream-base.json \
  --warm-lineage /path/to/incumbent-recovery.json \
  --dataset-manifest /path/to/muta-stem-v2-sft-300k/manifest.json \
  --validation-manifest /path/to/round2-dev-5000/manifest.json \
  --output-root /path/to/runs/full
```

For either fresh treatment, omit `--initial-adapter`. For an interrupted full
stage, add `--resume-from-checkpoint` pointing to that stage's latest complete
checkpoint and retain the original initializer argument if it is continuation.

## Historical pilot compiler and v1/v2 reproduction

The sections below document the retained historical schemas. Their exclusion
treatment is **not** the current launch plan. Schema v2 deliberately requires its
historical trainer hashes and cannot bless the new continuation trainer.

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

## Canonical matched-GGUF promotion gate

The canonical full-data path uses the sealed nine-GGUF CUDA comparison, not the
earlier mixed PEFT/HF diagnostic. It re-runs the retained comparison compiler's
sealed-run, ledger and aggregate validators without emitting another report. It
also binds all eight evaluated Q4_K_M files through their frozen quantization
manifests to the compiled pilot adapter, training manifest and training-parent
hashes.

The selections are fixed by
`docs/plans/2026-09-18-full-data-promotion-addendum.md`:

| Lineage | Pilot | Decision boundary |
|---|---|---|
| clean | `clean-r16-lr1e5` | STEM priority: reviewed MC 42 vs 39 and written core 28 vs 23 against clean-r32; judges regressed 34 vs 47. |
| warm | `warm-r16-lr5e6` | Leads reviewed written core and judges; reviewed MC regressions remain disclosed. |

Before freezing, supply both independent training gates: the retained 12-step real
SIGTERM/resume proof and a fresh completed 20–100-step smoke (the campaign run is
24 steps) made by the exact current trainer on the exact dataset/development
fingerprints. The shorter proof cannot substitute for the promotion smoke.
The 24-step smoke uses milestones 6/12/24, effective batch 64, and logging every
optimizer step. Preserve its full `adapter/` and `checkpoints/` trees (including
the root trainer state), loss metrics/curves, resolved config, terminal marker,
and a non-empty `stdout.log`; promotion verifies those files and inventories the
whole completed tree. Losses must be finite numeric values, scheduled evaluation
multiplicity must be exact, and the copied final adapter must be the actual
minimum-development-loss checkpoint. The verifier parses every retained
safetensors header/payload layout and the causal-LM LoRA config; renamed arbitrary
bytes, placeholder plots, and self-consistently resealed JSON are rejected.

```bash
python model-development/finetune/build_round2_promotions.py \
  --pilot-config provenance/configs/pilot-sweep.json \
  --pilot-results provenance/results/pilots-combined-20260918/pilot-results.json \
  --canonical-comparison-dir provenance/results/all-gguf-cuda-comparison-20260918 \
  --export-root provenance/exports \
  --hardened-resume-verification \
    provenance/calibration/hardened-smoke-20260918/receipts/verification.json \
  --promotion-smoke-dir /path/to/completed-24-step-smoke \
  --best-clean-id clean-r16-lr1e5 \
  --best-warm-id warm-r16-lr5e6 \
  --rights-clean-rows 300000 \
  --clean-selection-note \
    "STEM-priority choice; judges regressed 34 vs 47 relative to clean-r32." \
  --warm-selection-note \
    "Written-core and judges leader; reviewed MC regressions remain disclosed." \
  --output provenance/configs/full-runs.json
```

Schema v2 freezes the canonical comparison/ledger/source hashes, the exact eight
export-manifest receipts, both training gates, and the promotion builder, launcher
and trainer/helper hashes. It also freezes the complete shared treatment
(512-token context, seed 3407, 64 × 1 batch split, warmup 0.03, zero weight decay,
logging interval 47) and the expected clean/warm base-tree, lineage-receipt,
tokenizer, training-manifest, and validation-manifest hashes. The launcher must
join every supplied runtime path to those authorities before constructing the
trainer command. The resulting file must be written exactly to
`provenance/configs/full-runs.json` and committed. At launch, the validator compares
the parsed JSON object with `HEAD:provenance/configs/full-runs.json`; its separate
sidecar checks file bytes. This is semantic Git-object equality, not byte-for-byte
Git equality. The legacy and canonical argument sets are mutually
exclusive; there is no fallback between evidence modes.

## Retained legacy PEFT path

The original matched-prompt PEFT verifier remains available for reproducing the
earlier schema-v1 workflow. Selection is explicit; the command never chooses a
winner from loss alone. Every pilot adapter must appear complete in the same
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

Both schemas freeze exactly three treatments: best-clean private-enriched,
best-warm private-enriched, and the same warm hyperparameters with private sources
excluded. Each uses effective batch 64 and explicit quarter, half, and final-step
evaluation/checkpoint milestones. The launcher revalidates the frozen schema and
its sidecar before constructing a trainer command.

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
