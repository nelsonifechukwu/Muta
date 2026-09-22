# Pilot comparison review protocol

## Scope and frozen tests

Compare the previous Muta Q4_K_M with all eight round-two 20,000-row pilot
Q4_K_M exports. Reuse the unchanged ten judges prompts and the fixed 100-prompt
STEM battery. The earlier HF/PEFT-versus-GGUF run is supporting evidence, not the
matched deployment-artifact comparison. Preserve all original model outputs.

The implementation/execution addendum is owned separately by the evaluation
runner. This protocol fixes interpretation before inspecting its new outputs.

## Review rules

- Verify terminal receipts, model identities, prompt identities, raw-response
  hashes, item counts, decoding settings, and truncation before scoring.
- Report the 50 STEM multiple-choice option matches separately from explanation
  quality. Correct option letters do not prove correct reasoning.
- Agent semantic review of each written STEM response records two binary
  judgements: core answer/concept is correct without material contradiction;
  all requested reasoning/teaching components are supplied and correct. Include
  a short reason, exact response hash, and any uncertainty. Do not call agent
  review human grading or official competition marking.
- For judges prompts, apply the existing ten-point criterion weights
  semantically rather than by keyword presence. Equivalent valid mathematics
  counts; a matching number embedded in contradictory working does not validate
  that working. Give no independent-check credit for an invalid second method.
- Treat the four language-dependent points on human_03 as unverified until a
  qualified Yorùbá reviewer checks the explanation and bilingual quizzes.
  Report reviewed judges points out of 96 and preserve the unverified component
  separately. Do not claim Yorùbá fluency from diacritics or an agent score.
- automated_01 and human_04 have identical text. Report the ten-prompt replay
  score plus a deduplicated sensitivity score; never call these ten independent
  questions. Require exact equality of the generation signature: answer text,
  reasoning_content, finish_reason, and generated_tokens. Do not require raw
  HTTP byte identity: request IDs, timestamps, and timing fields vary normally.
  Any generation-signature disagreement under identical greedy input is a
  nondeterminism/integrity signal to investigate, not independent evidence of
  performance. Disable prompt caching for this comparison.
- Review is agent-based and may be unblinded while evidence is collected. State
  that limitation explicitly and independently cross-check the recommended
  candidate's errors and scores; do not describe this as blinded human review.
- All truncations remain visible. Do not silently retry only a favoured model.
  Any necessary larger-token-cap rerun must apply to every compared model.
- STEM M34 asks for a rule that fits four sequence terms, not a unique rule.
  Accept the intended n(n + 1) rule and next term 30, or another explicitly
  stated consistent rule that actually fits all four terms and its next term.
  Do not reject mathematically valid alternatives solely for differing from 30.

## Known answer checks

- Chalk: C; 6 times 500 = 3,000 naira.
- Mastery: S(t) = T + (S(0) - T) exp(-kt), with the initial condition satisfied;
  convergence to T assumes k > 0. A positive lower initial mastery approaches T
  without exponential growth without bound.
- Equal-distance journey: times 1.5 and 0.75 hours, total 2.25 hours; mean speed
  120/2.25 = 53 1/3 km/h, not the arithmetic mean of the speeds.
- Rice: cost 74,000; discounted price 1,955/kg; revenues 57,500 and 29,325;
  total revenue 86,825; profit 12,825; 17.331...%, rounding to 17.3%.
- Offline capacity: the given facts do not determine a unique parameter count.
  The ideal operation budget is 8e11 operations in 0.2 seconds. Any parameter
  bound needs output length and operations per parameter per generated token;
  practical memory/bandwidth and other overheads further constrain it.
- Proportional acquisition: a rate proportional to positive personalization
  tends to zero as personalization tends to zero and is unbounded in the
  ideal linear model as it tends to infinity. Realistic saturation may be
  discussed explicitly as a change of model, not substituted silently.

## Selection and reporting

Use side-by-side judges and STEM correctness/teaching tables with paired gains
and regressions against the incumbent. Development loss is not answer accuracy.
Do not manufacture a single weighted metric after seeing the results. A
replacement recommendation requires credible improvement without a material
regression on another core quality measure; otherwise retain the incumbent and
report the best challenger and its trade-offs. A small pilot test can support
only a provisional benchmark-specific recommendation, not universal superiority.

Inference queues may overlap for throughput, so their timings are diagnostic.
Do not report these A100 measurements as target CPU performance or an ADTC total.
Full-data training and final target CPU validation remain separate milestones.
