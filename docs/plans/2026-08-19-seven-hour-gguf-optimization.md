# Seven-hour GGUF optimization campaign — 2026-08-19

## Objective

Maximize the ADTC 2026 composite score using only the submitted GGUF. Preserve the current
Muta Tutor Qwen3-1.7B pure-Q4_0 tied-head artifact as an immutable control. Promote a new
artifact only when it wins on reproducible score evidence and passes load, prompt-quality,
hash, license, and clean-download gates.

The official audit measures the raw GGUF with llama.cpp. Product flags, RAG, speculative
decoding, KV-cache settings, Docker, and gateway optimizations cannot improve the submitted
file's telemetry score and are outside this campaign.

## Measurement contract

- Accuracy: profiler-parity raw-GGUF `arc_easy` first; `arc_challenge`, SciQ, GSM8K and fixed
  tutor prompts only for survivors. Record sample count and metric; never merge unlike tasks.
- Performance: exact profiler invocation, `llama-bench -p 512 -n 128 -ngl 0`, on the
  b10175 reference build with native/AVX/AVX2/FMA/F16C disabled. Decode TPS is the scored
  value. The AVX2 run is retained as separately labelled product/deployment evidence.
- Efficiency: peak whole-process-tree RSS sampled every 100 ms around the same invocation.
- Score: the executable official profiler's `S_perf = min(TPS / 15, 1) * 100`. The public
  challenge webpage conflicts, but no sourced clarification resolves it; website-relative
  values are sensitivity-only and cannot overrule the audit implementation.
- Reliability: no OOM/crash/illegal instruction; model loads in b10175 and b10360; all model
  files carry byte count, SHA-256, recipe, source revision, and license provenance.
- Thermal: unavailable on the GCP VM and explicitly reported as unknown. No cloud number is
  presented as target-laptop report evidence.

## Search funnel

Every stage is one-variable-at-a-time. A candidate that is dominated on accuracy, speed, and
RSS stops early; the expensive accuracy battery is reserved for the Pareto frontier.

### Controls and quantization ladder

1. Current Muta Tutor: Qwen3-1.7B pure Q4_0, tied head, baked template.
2. Untied bartowski Q4_0 source: isolates tied-head savings.
3. From the pinned high-precision Qwen3-1.7B source: pure Q4_0, Q4_K_S, Q4_K_M, IQ4_XS,
   Q5_0, Q5_K and Q6_K. This is deliberately wider than a file-size ladder: on x86 AVX2,
   Q4_0 and Q4_K repack while Q5_K, Q6_K, Q3_K and IQ4_XS do not, so the smallest file can
   have the largest scored RSS.
4. Mixed candidates are based on the best non-repacking body quant, selectively protecting
   high-sensitivity tensors with Q6_K/F16 or shrinking low-sensitivity tensors only when the
   measured AVX2 RSS/TPS exchange earns the change.
5. Importance-matrix quantization only if a disjoint math/science calibration matrix can be
   produced from the high-precision source. Never calibrate on evaluation examples.

### Structural and architecture candidates

6. Vocabulary: inspect the tokenizer graph before any rewrite. The current Qwen artifact is
   GPT-2/BPE with 151,387 merge rules and no sentencepiece score vector; the existing pruner
   cannot rewrite that graph coherently, so unsafe CJK-only deletion is a recorded rejection,
   not an experiment performed on the submission candidate.
7. Layer pruning: small late-layer removals supported by `llama-quantize --prune-layers`,
   gated immediately on load and ARC-Easy. Unstructured sparsity is documented, not shipped:
   dense GGUF kernels store and multiply zeros, so it saves neither bytes nor scored time.
8. Smaller dense architectures: Qwen3.5-2B pure Q4_0/tied where supported, plus the strongest
   already-measured 1–1.7B controls. Off-the-shelf distilled models are admitted only if the
   exact profiler stack loads them coherently.
9. BitCPM accuracy control: benchmark the existing best head/embedding mix under the same
   no-AVX reference binary. It remains a live contender until the common-host matrix settles it.

### Behaviour stored in the GGUF

10. Context metadata is tested for load/RSS effect but is not expected to change the fixed
    profiler invocation. The embedded chat template and sampling defaults are evaluated on
    the four competition prompts plus a fixed math/science tutor set; they may move qualitative
    `S_acc` but cannot be credited to automated ARC or TPS.
11. Fine-tuning/distillation are decision-gated. A seven-hour CPU-only run cannot honestly
    train, validate, convert, and audit a new model. Existing distilled checkpoints can compete;
    new training is scheduled only if measured post-quantization loss shows enough headroom to
    repay the accuracy, provenance, and deadline risk.

## Promotion rule

A candidate replaces the control only if it has the highest common-host reference-profiler
composite at the fixed 15 tok/s cap, does not materially degrade the harder-task or tutoring
gates, and reproduces from a clean pinned recipe. The conflicting webpage-relative formula is
reported separately and never averaged into the primary verdict.
Differences inside benchmark uncertainty are treated as ties; the smaller, simpler, more
portable artifact wins a tie.

## Deliverables

- Append-only raw campaign JSONL and a scored summary JSON/TSV.
- Dashboard campaign view with technique, provenance, metrics, score sensitivity, and verdict.
- Updated `RESULTS.md`, `bench/optimization-log.md`, Muta-IQ report, and a decision memo that
  explicitly covers every technique requested, including negative and infeasible results.
- Independent adversarial review, exact finalist rerun, grouped commits, and GitHub push.

## Bundled-profiler confirmation extension

After the promotion funnel completed, four representative exact artifacts were promoted to full
`adtc-profiler run --mode participant` confirmation on the same idle GCP proxy:

1. the selected Qwen3-1.7B pure-Q4_0 tied-head submission;
2. the BitCPM4-8B TQ2_0 vocabulary-pruned accuracy leader;
3. the previous Qwen3.5-4B IQ4_XS product model;
4. the Qwen3.5-0.8B Q4_K_M speed/size hedge.

The runs are serialized and use the exact b10175 no-AVX benchmark binary already pinned above.
Unlike the promotion screens, their RSS comes directly from the profiler's root-plus-child
sampler and their reports pass the profiler's own schema and parameter-count checks. Raw reports,
report hashes and the fail-closed aggregate live in
`bench/measurements/campaign-20260819/official-profiler/`. This extension confirms the shortlist;
it does not erase the broader quant-ladder screens or the separately preserved AVX2/webpage lane.
