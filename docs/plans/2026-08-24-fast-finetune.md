# Fast ADTC fine-tuning campaign

## Goal

Produce weight-tuned GGUF candidates for the two evidence-backed submission lanes without
changing the verified submission until a candidate passes the complete regression gate.

## Candidates

1. Scalar lane: Qwen3.5 0.8B, exported as Q4_0.
2. Vector lane: Qwen2.5 1.5B Instruct, exported as Q4_K_M.

Both runs start from pinned Hugging Face checkpoints and use BF16 LoRA. QLoRA is excluded for
the primary controls because the available GPU has sufficient memory and the Qwen3.5
fine-tuning guidance warns that four-bit training produces unusually large quantization
differences. A QLoRA branch is retained as an explicit experiment rather than assumed inferior.

## Sweep

For each architecture, compare a full BF16 rank-16 control with three 250-step branches:

1. BF16 rank 8, learning rate 1e-4, balanced data;
2. BF16 rank 32, learning rate 5e-5, reasoning-heavy data; and
3. 4-bit QLoRA rank 16, learning rate 1e-4, reasoning-heavy data.

The reasoning-heavy profile removes general-conversation replay and caps MathDial at 750 rows.
The balanced profile preserves general chat and the full tutoring slice. Training loss is only a
screening signal: candidate ranking uses the exported GGUFs.

## Dataset

Use only training splits:

- GSM8K reasoning solutions;
- ARC-Easy and ARC-Challenge multiple-choice continuations in the profiler's raw format;
- OpenBookQA multiple-choice continuations;
- MathDial misconception-correction tutoring examples;
- a small general-conversation replay slice; and
- deterministic, verified African-context arithmetic examples.

ARC validation/test, the existing ARC-Easy-500 evaluation set, both submitted prompts, and all
other evaluation splits remain excluded. Every source revision and per-split count is written to
the generated dataset manifest.

## Training and export

- BF16 LoRA, rank 16, alpha 16, attention and MLP projections, assistant/completion-only loss.
- One epoch at 1024-token context with deterministic seeds, micro-batch 4, gradient
  accumulation 4 and loss-only evaluation. The effective training batch is 16. The colocated
  vLLM process is paused during each measured sweep so training has exclusive use of the A100;
  its files and launch configuration remain unchanged.
- Merge into the original precision checkpoint.
- Export the merged checkpoint and final GGUF; preserve the selected quant type per lane.
- Apply the existing metadata-only Muta tutor-template rewrite to the exported GGUF, then verify
  the rewritten file with the pinned audit llama.cpp build. The raw profiler accuracy path does
  not apply a chat template, so weight tuning and live-chat persona checks remain separate gates.

## Promotion gate

A candidate may replace its base only after:

1. exact-GGUF ARC-Easy-500 evaluation through the profiler accuracy implementation;
2. additional ARC-Challenge, OpenBookQA, science and numerical-reasoning checks;
3. the two submitted prompts plus a held-out hidden-prompt-style tutoring battery;
4. scalar and vector throughput/RSS measurements with five internal repetitions on the GCP
   proxy;
5. llama.cpp load, template, output-termination and offline-provisioning checks; and
6. no major task regression or score reduction under either recorded scoring interpretation.

Training loss alone is never a promotion criterion.

## Phase 2: metric-aligned data correction

The first eight-run sweep improved held-out language-model loss but did not improve the
Qwen3.5 ARC-Easy-500 result. Its mixture was clean but contained too little data in the
profiler's raw multiple-choice prompt shape. Before claiming that LoRA is ineffective, run a
second controlled phase on Qwen2.5 with:

1. a multiple-choice curriculum using every training-only ARC, OpenBookQA and QASC example;
2. a hybrid curriculum that adds a small number of GSM8K solutions and short OpenR1 traces
   that passed both Math Verify and reasoning-completeness checks;
3. exact and near-duplicate filtering against every source validation/test question;
4. lower learning rates to reduce catastrophic forgetting;
5. the same ARC-Easy-50 promotion gate, followed by ARC-Easy-500 and both scalar/vector CPU
   measurements for survivors.

The licence gate is tested independently with a licensed-MCQ profile that removes OpenBookQA
without adding long-form data. This separates licensing from curriculum effects. A second
licensed-hybrid control tests whether retaining verified worked solutions improves broader
reasoning without losing the multiple-choice gain.

The first sweep also concatenated raw prompts and completions as `Answer:choice`. lm-eval's
multiple-choice requests use `Answer:` as context and ` choice` as the continuation. The second
phase must preserve that leading-space boundary because it changes BPE tokenization and the
continuation likelihood being optimized.

Do not use SciQ because its non-commercial licence is incompatible with a low-risk competition
submission. Do not use MMLU-Pro test data or MMLU validation/test data for training. Do not use
large synthetic corpora without per-example correctness filters.

## Dashboard integration

The report update must preserve the two CPU configurations as separate decisions. It will:

1. publish one machine-readable fine-tuning summary with matched controls, 500-item accuracy,
   scalar/vector telemetry, fixed-15 scores, and held-out results;
2. replace the pre-tuning overview and current-state values with the tuned finalists;
3. add a compact fine-tuning chapter showing the configuration screen, the matched control
   deltas, and a directly labelled grouped-bar figure with a visible table fallback;
4. add the adopted and rejected fine-tuning findings to the experiment ledger and update the
   requirement status where the submission candidate changes; and
5. test the data path, score arithmetic, responsive layout, visible evidence labels, and static
   fallback at the dashboard's normal local server.

The report must identify the 45 MiB profiler-root allowance as an estimate, not a direct memory
measurement. Interrupted Qwen2.5 secondary held-out runs remain pending and cannot be rendered
as zero or as completed evidence.
