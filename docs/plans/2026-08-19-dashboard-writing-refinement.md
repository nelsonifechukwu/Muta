# Dashboard writing refinement

Date: 2026-08-19

## Goal

Refine the updated interactive report with the `no-ai-slop` editing rules. Preserve its evidence,
calculations, chapter order, interactions, technical vocabulary, and candid first-person-plural
voice. Edit only prose that sounds staged, generic, over-explained, or internally inconsistent.

## Scope

- Read every visible sentence in `muta-iq/dashboard/index.html` and every generated label,
  experiment finding, FAQ answer, warning, and profiler message in `script.js`.
- Keep official-profiler results, profiler-parity estimates, website-relative sensitivity results,
  and development results in separate evidence lanes.
- Reconcile the artifact diagram with the campaign's isolated tied-versus-untied A/B result without
  changing any recorded campaign value.
- Leave strong sentences and the new reading layout alone.

## Editing checks

1. Remove formulaic contrasts, self-conscious interpretation, decorative punch lines, and repeated
   explanation.
2. Replace abstract or portable claims with the report's existing measurements and mechanisms.
3. Keep model names, dates, units, confidence intervals, hashes, caveats, and status labels exact.
4. Run every item in the `no-ai-slop` eval after editing. Any failure triggers another pass.
5. Run the dashboard tests, JavaScript syntax check, browser checks at desktop and phone widths,
   and a fresh adversarial review before handoff.
