# Muta IQ dashboard experiment report plan

Date: 2026-08-19

## Goal

Turn `muta-iq/dashboard/` from a profiler console into a chaptered, interactive progress report without removing its profiling controls or changing any score, benchmark, campaign, or API calculation. The report should explain how Muta moved from a broad small-model search to `muta-tutor-qwen3-1.7b-q4_0.gguf`, why the current choice is provisional, and which findings belong to the product runtime rather than the GGUF-only judging path.

The primary audience is a technically literate competition reviewer who did not witness the experiments. A second audience is the team returning later to add the next campaign.

## Evidence contract

Every reported number must remain attached to one of four lanes:

1. **Official-profiler result** — a direct full participant run produced by the official executable. Peak RSS is measured over the profiler root and its child process tree. These results form the current decision surface.
2. **Profiler-parity estimate** — a controlled reconstruction of the official no-AVX environment. Throughput is measured directly; profiler-root RSS is estimated from the documented offset. Repetition counts remain visible.
3. **Website-relative sensitivity result** — an AVX2 deployment measurement rescored under the public website's cohort-relative performance denominator. It is a sensitivity analysis, not an official result.
4. **Development result** — an earlier or product-runtime experiment on Mac, Docker, GCP, or another engine regime. It explains a decision but cannot be compared as if it came from the campaign.

The mixed-machine SQLite archive stays available for inspection and keeps its existing calculation. It must not be presented as a campaign ranking.

Accuracy values are labelled as proxies, including their sample size and confidence interval when available. `S_acc` is not described as the judging panel's final qualitative score. GCP thermal readings are marked unavailable; “no throttling reported” is not converted into a temperature claim.

## Information architecture

The report will use a narrow editorial reading column, a sticky chapter index on wide screens, numbered sections, short design notes, interactive figures, and optional “check the reasoning” disclosures. It takes the chapter discipline and explicit trade-off notes from the two supplied writing references without copying their appearance or voice.

1. **Current answer** — one-sentence verdict, exact artifact, reproducibility identifiers, remaining uncertainty.
2. **The problem** — target hardware, submission boundary, score equation, and exchange rates.
3. **How to read the evidence** — the four evidence lanes and the difference between the executable profiler and public website formula.
4. **Baseline and runtime sweeps** — the July baseline, resource caps, thread/KV sweep, failed speculative decoding, and measured bandwidth ceiling.
5. **Model funnel** — the 4B/2B/0.8B quality study, August candidate audit, template failures, and the move from parameter-count intuition to audit-kernel fit.
6. **Quantization and GGUF constraints** — Q4, IQ4, importance matrices, tied heads, repacking, mmap, and why GGUF-only submission changes the optimisation surface.
7. **The ternary branch** — BitCPM pruning, TQ1 slowdown, SVD and sparsity rejections, and what the branch established.
8. **Weight streaming** — the disk-budget calculation, measured residency frontier, and the distinction between a useful product engine and an unavailable submission lever.
9. **August 19 campaign** — direct official runs, parity screens, website-relative sensitivity, and the current selection.
10. **Experiment ledger** — compact status and evidence table covering wins, losses, neutral results, deferred work, and reasons.
11. **Challenge FAQ progress** — each relevant FAQ mapped to current evidence; non-applicable progress cells intentionally blank.
12. **Operational appendix** — the existing campaign tables, live run status, historical archive, and model actions.

## Interactions and figures

- Score exchange-rate calculator with fixed, documented formula and no persistence.
- Runtime optimisation comparison chart.
- Model-funnel scatter plot with separate provenance styling.
- Weight-streaming Pareto chart plus a disk-budget control.
- Official campaign score decomposition and throughput/RSS plot.
- Website-relative sensitivity control that shows the winner changing with the cohort floor.
- Filterable experiment ledger.
- Collapsible design notes, method details, and FAQ items.
- Existing profiler, history, promotion, deletion, and cancellation controls remain intact.

All figures will be native HTML/SVG and work without a network connection. Equations use MathML or readable HTML, with a plain-text fallback. Charts include a textual summary and do not rely on colour alone.

## Copy rules

- Prefer short sentences, concrete subjects, and explicit evidence labels.
- Use “measured,” “estimated,” and “rescored” only for their corresponding lanes.
- Use “current choice” or “current winner,” not “final model.”
- State what a failed experiment taught us; do not dramatise the failure.
- Avoid inflated claims about intelligence, educational quality, readiness, or African-language support.
- Preserve exact model names, units, dates, hashes, sample sizes, and caveats.
- Use “Muta IQ” in prose and `MUTA-IQ` for the product mark.

## Implementation boundaries

- Edit `index.html`, `style.css`, and `script.js` for the report and copy.
- Keep the current element IDs and API calls needed by `app.py`.
- Do not change `compute_scores`, campaign records, stored runs, profiling arguments, or endpoints.
- Edit server messages only when wording can improve without changing status codes, payload shapes, or control flow.
- Add lightweight static tests only where they protect the evidence labels or preserved controls.

## Verification

1. Run the dashboard Python test suite.
2. Check JavaScript syntax and scan for broken local references.
3. Start the dashboard against its real API and inspect desktop and narrow layouts in the in-app browser.
4. Exercise quick-run toggle state, campaign tables, history modal, report modal, and the new controls without launching a destructive profiling run.
5. Compare every campaign number and label against the campaign JSON/Markdown sources.
6. Run the no-AI-slop checks over all user-facing copy and revise flagged passages by judgment.
7. Give the completed work to a fresh adversarial reviewer, then resolve factual, provenance, accessibility, or functionality findings before handoff.
