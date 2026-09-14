# Gate 2 model evaluation and ranking report

## Objective

Replace the empty Gate 2 audit chapter with a connected account of the completed balanced-model campaign. The chapter will explain why the screen was run, how the thirteen executable artifacts were compared, what ARC-Easy-500, the 100-prompt STEM battery, and the ten-prompt Gate 1 replay each measure, and why Muta Tutor Qwen2.5 1.5B Q4_K_M advances despite not leading every proxy.

## Evidence boundary

- Treat `results.csv`, `judges-ranking.csv`, the manual ledgers, raw JSONL, response transcripts, and the campaign reports as the sources of record.
- Keep scalar GCP as the primary resource protocol and vector GCP as a secondary CPU proxy. One shared ARC-Easy-500 result belongs to each artifact; it is not a scalar/vector pair.
- State that the ARC archive retains aggregate scores and confidence intervals only. Neither the local archive nor the read-only VM audit contains per-item model choices or log-likelihood samples, so 6,500 ARC answers cannot be reconstructed without a new instrumented run.
- Keep Mac STEM, Mac Gate 1, GCP Gate 1, and partial GCP STEM attempts separate. Missing Falcon records remain missing and unranked; Nemotron's reviewed zero remains a real final-output result.
- Do not alter any grade, synthesize a response, or present a reconstructed total as a completed official-profiler run.

## Report structure

1. Rename chapter 2 and every navigation reference from “Audit setup” to “Model evaluation and ranking”.
2. Open with the change from benchmark accuracy to dependable tutoring behavior.
3. Present the full candidate inventory, including Spark as runtime-excluded rather than a measured zero.
4. Define the scalar/vector configurations once, then describe the ARC, STEM, and Gate 1 protocols and their different grading boundaries.
5. Use compact vertical figures for ARC-Easy-500, reconstructed scalar/vector totals, matched Mac STEM results, and GCP Gate 1 replay results. Give every figure a text summary and exact-value table where needed.
6. Explain the conflicting leaders and the balanced selection: MiniCPM5 1B pure Q4_0 leads the scalar resource proxy, Qwen3.5 2B Q4_K_M leads the raw-completion STEM screen, and fine-tuned Qwen2.5 leads ARC and the GCP final-answer replay.
7. Close with the decision to continue development with fine-tuned Muta Tutor Qwen2.5 1.5B, while retaining its written-reasoning, multilingual, physical-target, thermal, and eligibility limitations.

## Response evidence

- Generate a static, load-on-demand evidence bundle under `muta-iq/dashboard/evidence/gate-2/` from the source-bound response and assessment files.
- Provide native model, test, and prompt selectors. Render prompts, answer fields, separate reasoning, completion state, and rubric decisions with `textContent`, never `innerHTML`.
- Include Mac STEM, GCP Gate 1, Mac Gate 1, and the distinct GCP STEM capture attempts. Include an ARC aggregate view that explicitly reports the unavailable per-item answers.
- Copy the canonical result tables and raw response files into the published evidence bundle for download. Extend the local server and static builder so the same relative URLs work locally and after deployment.

## Verification

- Add static and builder tests for chapter naming, thirteen-artifact coverage, tied ranks, Falcon blank-versus-Nemotron-zero handling, ARC sample limitation, response-bundle coverage, safe text rendering, and published evidence paths.
- Reconcile chart constants and tables against `results.csv` and `judges-ranking.csv`.
- Run the campaign evidence tests, dashboard suite, full repository suite, JavaScript syntax check, and diff check.
- Render and exercise the chapter and response explorer at desktop and phone widths, check console output, and submit the result to an independent read-only reviewer.

This task does not authorize a new benchmark run, training, commit, push, or unrelated UI-service repair.
