# Dashboard AVX2 campaign section

Date: 2026-08-19

Status: Complete

## Goal

Add the controlled AVX2/FMA/F16C score-of-record rerun to the Muta IQ HTML report as its own
chapter. Keep it visibly separate from the official scalar profiler campaign and the
website-relative sensitivity sweep.

## Evidence contract

- Read the five rows from
  `bench/measurements/campaign-20260819/avx2-score-of-record/comparison.json`.
- Preserve the fixed/capped 15 tok/s score, exact artifact names, build SHA, benchmark geometry,
  five-sample policy, estimated profiler RSS label, and unknown-temperature warning.
- Describe Q4_K_M as the nominal AVX2 proxy winner, not the promoted submission model.
- Keep Muta Tutor Q4_0 as the current executable-profiler choice.

## Changes

1. Add an AVX2 chapter link to the top navigation and contents rail.
2. Add a build-policy strip, verdict summary, five-model comparison table, interpretation, and
   provenance disclosure after the direct campaign.
3. Add responsive styles that preserve the report's existing editorial layout.
4. Add static tests that compare the rendered numbers and labels with `comparison.json`.
5. Update the dashboard README and verify the real local report at desktop and phone widths.

## Acceptance

- AVX, AVX2, FMA, and F16C are shown as ON; native and AVX-512 are shown as OFF.
- All five models, throughput values, speedups, RSS estimates, accuracy proxies, and totals match
  the committed comparison artifact.
- The section states the 0.1666-point nominal margin and Q4_K_M variance caveat.
- Dashboard tests, JavaScript syntax, link checks, and visual inspection pass.
