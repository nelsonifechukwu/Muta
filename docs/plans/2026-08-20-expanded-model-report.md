# Expanded model report plan

## Objective

Integrate the paired scalar and portable vector measurements for the eight-model
architecture screen into the Muta IQ report without weakening the distinction
between measured evidence, proxy evidence, and the current submission choice.

## Changes

1. Store the compact campaign summary as a report data source and expose it
   through the dashboard state endpoint.
2. Extend the instruction-set comparison to every main measured model. Use one
   shared chart palette and legend order across the report: direct profiler in
   blue, scalar configuration in amber, and portable vector execution in green. Mark a
   winner with an outline rather than a different fill.
3. Convert comparable bar charts from horizontal to compact vertical layouts.
   Keep axes explicit, use bounded heights, and allow a wide chart to scroll on
   narrow screens instead of making it tall.
4. Update the report text, tables, captions, accessible summaries, experiment
   ledger, and current-state section. Preserve the report's existing writing
   style and keep the vector proxy leader separate from the risk-adjusted
   submission recommendation.
5. Add regression tests for the data source, candidate count, score values,
   chart orientation, shared legend, and visible decision language.
6. Render the report at desktop and phone widths and correct any overflow,
   label collision, or inconsistent legend before completion.
7. Run ARC-Easy at n=500 for the provisional Qwen2.5 1.5B leader, retain the
   raw evidence, and rescore both CPU configurations with the larger sample.

## Acceptance criteria

- The eight new candidates appear in the report with scalar and vector evidence.
- The expanded comparison identifies Qwen2.5 1.5B Q4_K_M as the validated
  vector candidate at 71.8% ARC-Easy over 500 questions and 80.7697 total.
- The report retains Qwen3.5 0.8B as the supplied-profiler submission choice
  because the corresponding scalar totals are 72.7895 versus 63.8176.
- All bar-chart figures are vertical and use the same semantic colours and
  legend labels.
- Visible report prose contains no dates, commit identifiers, or binary hashes.
- Static tests, dashboard tests, JavaScript syntax checks, and browser checks
  pass.
