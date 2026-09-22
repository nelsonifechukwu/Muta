# Full-data promotion after matched GGUF screening

This addendum advances the already-authorized campaign; it does not change the
deployed model. The source of selection is the completed nine-GGUF comparison,
not the earlier mixed HF/PEFT diagnostics or development loss alone.

Latest user steering: the private-data exclusion ablation remains cancelled.
Add a third treatment continuing the selected warm-r16-lr5e6 pilot, alongside
the fresh clean and fresh warm runs. All use the entire artifact: its verified
manifest contains 300,350 rows, not 350,000. Do not pad or substitute a dataset.
The schema-v3 builder now replaces the obsolete exclusion ablation with that
continuation treatment. The reviewed config was frozen after real GPU smoke and
interruption/resume checks; see `provenance/results/FULL_TRAINING_LAUNCH_STATUS.md`
for exact hashes, live controller identity and current CSD3 authentication status.

## Frozen treatments

| Treatment | Selected pilot hyperparameters | Rows | Proposed host |
|---|---|---:|---|
| Clean, private-enriched | clean-r16-lr1e5 | 300,350 | Oracle |
| Warm, private-enriched | warm-r16-lr5e6 | 300,350 | CSD3, subject to admission/budget |
| Continue selected warm pilot | warm-r16-lr5e6 | 300,350 additional | Oracle after clean |

The first two runs start fresh adapters on the original clean or already-merged
Muta v1 parent. The third loads the exact selected pilot adapter as trainable
onto its exact Muta v1 parent, once only; it is not applied to weights already
containing that adapter. Reset the optimizer and learning-rate schedule for
this new full-data stage; do not describe it as exact checkpoint resume. Its
prior pilot exposure is additional training history, not extra unique data.
The unchanged pilot remains a separately retained evaluation control.

Each new stage is one epoch, effective batch 64, context 512, seed 3407, BF16
completion-only LoRA. Keep quarter/half/final
checkpoints, select the best development-loss checkpoint and retain the final
checkpoint separately. Epoch position must remain explicit in all comparisons.

Clean-r16 is selected for stronger STEM tutoring: reviewed MC 42 versus 39,
written core 28 versus 23, and complete written responses 20 versus 18 relative
to clean-r32. Its judges score is substantially worse, 34 versus 47; this is an
explicit domain-prioritization decision after viewing results, not a universal
winner or preregistered composite. Warm-r16-lr5e6 leads written core and judges
scores, with the MC regressions already disclosed in the pilot report.

## Gates before any full run

1. Recheck live processes and unique run directories; never duplicate a run.
2. Adapt promotion validation to accept the canonical, fully revalidated GGUF
   semantic comparison. Bind the eight export manifests back to the compiled
   pilot adapters and training parents. Retain the older evaluation verifier;
   do not weaken its checks to make incompatible evidence pass.
3. Bind the hardened real interruption/resume receipt to the exact trainer and
   input fingerprints. Its treatments were 12 steps, so add a fresh 24-step
   smoke with the final trainer to satisfy the original 20–100-step smoke gate.
   If continuation loading changes the trainer, repeat the required resume
   check for that exact source hash and verify pilot-adapter initialization.
   Preserve the prior bounded smoke without relabelling it.
4. Freeze selections, comparison/export hashes, smoke/resume evidence, config
   hash and executable source hashes before launch. Use immutable source
   snapshots; no unrelated commits, private data publication or large Mac copies.
5. Independent adversarial review and targeted tests must pass.
6. Confirm CSD3 budget afresh: the 12:30Z check showed four GPU-hours remaining.
   One 1-GPU run needs roughly 2.2 hours before contingency; reserve 3 hours.
   Do not submit two full runs against that balance. Oracle runs the clean
   treatment and then pilot continuation. A queued CSD3 job remains assigned there until explicitly
   resolved, so Oracle must not duplicate it.

## Completion requirements

All checkpoints remain experimental until export, matched held-out correctness
and tutoring tests, and target-CPU qualification. Save unedited baseline and
candidate outputs, exact adapters/scripts/metrics/curves/hashes and private-safe
dataset descriptions. GPU quality results are not CPU speed or official ADTC
scores. Existing pilot artifacts and failed attempts remain intact.

Use the proposed winner-test design in
`2026-09-18-full-data-winner-test-design.md`; freeze its final battery, rubrics,
thresholds and software before generating finalist responses. The design is
not a claim that a fresh benchmark has already been built or run.
