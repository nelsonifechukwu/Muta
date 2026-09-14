# Qwen3.5 2B Q4_K_M: Mac STEM manual assessment

Provisional assistant assessment of all 100 raw-completion responses. This is neither an official ADTC grade nor a competition score.

| Category | Complete pass | Core answer correct |
|---|---:|---:|
| Math multiple choice | 22/25 | 22/25 |
| Written math | 22/25 | 25/25 |
| Science multiple choice | 23/25 | 25/25 |
| Written science | 10/25 | 23/25 |
| Total | 77/100 | 95/100 |

Complete pass requires the right answer, every requested substantive component or check, and no unresolved material error in the returned text. Core correctness records the central answer separately; it does not establish a complete or reliable explanation.

## Execution and grading

Mac/Metal, 2,048-token context, temperature 0, seed 42, two CPU threads, 99 GPU layers, 256 MiB cache; 256 generated tokens for multiple choice and 512 for written prompts. The request uses raw completion, without a chat template or external system prompt. Configuration and model-start records are retained with hashes in the JSON.

All returned text is assessed, including literal thinking markers and drafting text. This differs from the judges chat evaluation, which scores only final-answer text. A token-limit finish does not fail an already complete answer. A correct option value can pass without a letter; an unretracted wrong label cannot. A required check needs a genuinely distinct numerical method or an inverse calculation/substitution, not a repeated derivation. This clarification does not require independently checking every intermediate step.

96 responses reach the token limit; 0 are empty. 71 contain an unclosed literal thinking marker. These are protocol diagnostics, not automatic accuracy deductions.

## Failures

| Category | IDs failing the complete-answer policy |
|---|---|
| Math multiple choice | M12, M19, M25 |
| Written math | M39, M43, M48 |
| Science multiple choice | S07, S18 |
| Written science | S26, S27, S28, S29, S31, S32, S33, S34, S36, S37, S39, S40, S45, S46, S50 |

Each failure and pass has a per-response reason in the accompanying JSON, with source line, raw-response hash, original parser result, strict decision, and separate core decision.

S31 retains core credit for correctly distinguishing viral colds from bacterial infections. Its unqualified claim that sinusitis is often bacterial fails the complete-answer policy because it misstates an antibiotic indication. Independent review checked [CDC outpatient guidance](https://www.cdc.gov/antibiotic-use/hcp/clinical-care/adult-outpatient.html), which reports 90–98% of rhinosinusitis cases are viral. This does not penalize the accurate, weaker statement that sinusitis can be bacterial.

The S32 altitude example was checked against [NASA's metric atmosphere model](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/earth-atmosphere-equation-metric/): pressure at 3,000 m is approximately 70.2 kPa, about 69% of sea-level pressure, not half. The oxygen fraction remains approximately unchanged, so oxygen partial pressure has the same relative reduction.

## Review status

All 100 expected IDs, category counts, source/configuration/event hashes, per-response hashes, model/server identities, and score sums were validated. Focused independent review is complete for disputed explanation, verification and safety boundaries. The primary assessor read all 100 full responses; the independent reviewers examined selected cases, not a second complete 100-response assessment.
