# Muta IQ evidence-led report rewrite

## Objective

Rewrite `muta-iq/dashboard/` as one connected model-selection account. The current-results section will use the retained eight-model scalar/vector campaign, followed immediately by the Qwen2.5 1.5B ARC-Easy-500 validation. Earlier Math-Expert, Qwen3.5, quantization, and direct-profiler results will remain only where they explain filtering or the runtime-dependent submission decision.

## Evidence rules

- Regenerate `bench/measurements/model-extension/summary.json` from its three retained JSONL inputs through `bench/model_extension_summary.py` and `bench/score.py`.
- One accuracy evaluation belongs to one GGUF and protocol. Reuse the same ARC-Easy percentage when rescoring scalar and vector throughput/RSS; never infer an accuracy change from the CPU execution path.
- Keep ARC-Easy-50 rankings separate from ARC-Easy-500 validation. Do not compare unmatched sample sizes without labelling the mismatch.
- Keep direct participant-profiler, controlled scalar/vector, development, and website-relative evidence visibly separate.
- State unavailable comparisons and unmeasured temperature rather than filling gaps.

## Report structure

1. Competition motivation, hardware/submission constraints, and scoring.
2. Complete measured model field, grouped by dense scale, compact/mobile architecture, and specialist/distilled model.
3. Initial filtering and direct-profiler evidence.
4. Complete method sections for quantization; mixed precision; tied embeddings; vocabulary reduction; pruning; smaller architectures; distillation/fine-tuning; tensor layout/repacking; context/KV; weight residency; thread/runtime settings; scalar/vector execution; embedded behaviour; and speculation.
5. Canonical eight-model ARC-Easy-50 ranking and figures.
6. Immediate Qwen2.5 ARC-Easy-500 confidence adjustment.
7. Runtime-dependent selection: Qwen3.5 for the supplied scalar profiler, Qwen2.5 only after vector-runtime, physical-target, and tutor-behaviour checks.

## Implementation and verification

- Make the eight-model summary expose its shared-accuracy invariant and validation protocol.
- Restrict the current architecture chart/table to all eight and only those eight models; move earlier two-model evidence to its historical method context.
- Use the existing semantic colours consistently: direct profiler blue, scalar amber, vector green, diagnostic purple.
- Update static safeguards to check the full ranking, n=50/n=500 separation, shared accuracy, selection language, section completeness, and absence of visible dates/build identifiers.
- Run the complete test suite, JavaScript syntax and formatting checks, link/overflow checks, and render the live report at desktop and phone widths.
- Obtain an adversarial review, inspect the diff, commit, push, and fast-forward the tracked GCP checkout without cleaning or deleting untracked files.
