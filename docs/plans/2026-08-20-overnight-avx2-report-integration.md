# Overnight AVX2 report integration

## Objective

Make the 20 August AVX2/FMA/F16C finalist results explicit throughout the Muta IQ report. Keep
the 19 August five-artifact campaign as dated evidence, but stop presenting it as the latest model
selection result.

## Evidence boundary

- Direct scalar results come from the complete participant-profiler reports in
  `bench/measurements/campaign-20260820-overnight/`.
- AVX2 throughput and child-tree RSS come from the controlled b10175 screen on the same GCP
  2C/4T proxy. The AVX2 binary enables AVX/AVX2/FMA/F16C and disables native tuning and AVX-512.
- AVX2 profiler RSS is an estimate: measured child-tree RSS plus the retained 45 MiB profiler-root
  allowance.
- The final Qwen artifact was run directly through the scalar profiler. Its AVX2 row transfers the
  screen result from the pinned source file only because all 320 tensors and 496,192,768 tensor
  bytes were verified identical.
- ARC-Easy-50 is the executable-profiler proxy. ARC-Easy-500 is a larger diagnostic and must not be
  labelled an official score.

## Changes

1. Extend the generated overnight summary with fixed-15 AVX2 score components for both the
   50-item and 500-item accuracy inputs, plus explicit RSS and provenance fields.
2. Add a prominent paired scalar/AVX2 finalist figure and detailed table to the overnight chapter.
3. Expand the AVX2 benchmark ledger from the five 19 August artifacts to include the two latest
   finalists, while retaining campaign dates and evidence labels.
4. Update the overview, recommendation, experiment ledger, FAQ, report notes, `muta-iq/REPORT.md`,
   and `RESULTS.md` so the raw AVX2 leader and risk-adjusted recommendation are not conflated.
5. Add regression tests for the generated arithmetic, required report elements, exact values, and
   provenance wording.
6. Run the focused and full test suites, then inspect the local report at desktop and narrow widths.
7. Align every report visual with the current two-finalist decision: update the candidate funnel,
   calculator defaults, artifact derivation, and cohort-relative sensitivity chart. Preserve older
   figures only when their date and historical purpose are explicit.

## Acceptance criteria

- The report states that Math-Expert is the fixed-15 AVX2 leader with ARC-Easy-50 at 81.8803.
- The report states that Qwen3.5 0.8B leads the two-finalist AVX2 diagnostic with ARC-Easy-500 at
  76.8104 versus 75.1803.
- The report shows scalar and AVX2 totals side by side for both latest finalists.
- No latest AVX2 value is described as a direct participant-profiler measurement.
- The dated 19 August result remains accessible and clearly labelled as historical.
- Dashboard tests and the repository test suite pass.
- No figure selects the retired 19 August artifact or omits the 20 August finalists from a
  current-campaign comparison.
- The score calculator opens with the current direct scalar leader, and the artifact diagram
  describes the recommended Qwen3.5 submission file.
