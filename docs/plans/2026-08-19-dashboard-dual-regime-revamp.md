# Dashboard dual-regime campaign revamp

Date: 2026-08-19

Status: Complete

## Goal

Reframe the Muta IQ report around the controlled scalar and portable AVX2/FMA/F16C benchmark
regimes. Make Q4_K_M the current optimisation choice under the newly requested AVX2 policy while
preserving Q4_0 as the scalar-profiler winner.

## Visual hierarchy

1. Replace the single-regime hero with a paired decision panel.
2. Add a grouped bar chart with scalar and AVX2 total-score bars beside each other for all five
   shared artifacts. Print each total on its bar and highlight each regime's winner.
3. Keep the detailed scalar-to-AVX2 measurement matrix behind a disclosure.
4. Add a compact AVX2 score-of-record card to the operational appendix.

## Report-wide reconciliation

- Add the controlled AVX2 proxy as its own evidence lane.
- Update the score calculator defaults and current-state summary for Q4_K_M under AVX2.
- Rewrite the kernel, ternary, campaign, experiment-ledger, FAQ, and conclusion copy so every
  scalar number is explicitly labelled and every current AVX2 number points to the same evidence.
- Preserve the direct participant-profiler table as historical scalar evidence; do not overwrite
  it with estimated AVX2 RSS.

## Data flow

- Expose `avx2-score-of-record/comparison.json` through the dashboard state API.
- Render the grouped chart and appendix table from that JSON.
- Keep static headline values guarded by tests against the same artifact.

## Acceptance

- Five model groups, two bars per group, total labels, and winner highlights render correctly.
- The report calls Q4_K_M the current AVX2 choice at 80.4484 and Q4_0 the scalar winner.
- AVX/AVX2/FMA/F16C ON and native/AVX-512 OFF remain visible.
- Desktop and phone layouts, API data, static evidence checks, JavaScript, and the full test suite
  pass before the grouped commit is pushed and synchronized to GCP.
