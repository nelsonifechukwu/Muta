# Qwen3.5 2B Q4_0: Mac STEM manual assessment

Provisional assistant assessment of all 100 raw-completion responses. This is neither an official ADTC grade nor a competition score.

| Category | Complete pass | Core answer correct |
|---|---:|---:|
| Math multiple choice | 23/25 | 24/25 |
| Written math | 20/25 | 23/25 |
| Science multiple choice | 21/25 | 25/25 |
| Written science | 7/25 | 22/25 |
| Total | 71/100 | 94/100 |

Complete pass requires the right answer, every requested substantive component or check, and no unresolved material error in the returned text. Core correctness records the central answer separately; it does not establish a complete or reliable explanation.

## Execution and grading

Mac/Metal, 2,048-token context, temperature 0, seed 42, two CPU threads, 99 GPU layers, 256 MiB cache; 256 generated tokens for multiple choice and 512 for written prompts. The request uses raw completion, without a chat template or external system prompt. Configuration and model-start records are retained with hashes in the JSON.

All returned text is assessed, including literal thinking markers and drafting text. This differs from the judges chat evaluation, which scores only final-answer text. A token-limit finish does not fail an already complete answer. A correct option value can pass without a letter; an unretracted wrong label cannot. A required check needs a genuinely distinct numerical method or an inverse calculation/substitution, not a repeated derivation. This clarification does not require independently checking every intermediate step.

92 responses reach the token limit; 0 are empty. 67 contain an unclosed literal thinking marker. These are protocol diagnostics, not automatic accuracy deductions.

## Failures

| Category | IDs failing the complete-answer policy |
|---|---|
| Math multiple choice | M12, M24 |
| Written math | M30, M34, M38, M43, M50 |
| Science multiple choice | S01, S07, S12, S15 |
| Written science | S26, S28, S29, S30, S31, S33, S34, S37, S38, S39, S40, S42, S45, S46, S47, S48, S49, S50 |

Each failure and pass has a per-response reason in the accompanying JSON, with source line, raw-response hash, original parser result, strict decision, and separate core decision.

The pressure example in S47 was checked against [NASA's metric atmosphere model](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/earth-atmosphere-equation-metric/). Substituting 3,000 m gives approximately 70.2 kPa, rather than the response's 80 kPa. The physical explanation otherwise retains core credit.

## Review status

All 100 expected IDs, category counts, source/configuration/event hashes, per-response hashes, model/server identities, and score sums were validated. Focused independent review is complete. S36 passes: its intact-molecule/recoverability and new-substance evidence correctly supports the physical/chemical distinction; the additional colour-change evidence is weak but not a categorical false law. The primary assessor read all 100 full responses; the independent reviewers examined selected cases, not a second complete 100-response assessment.
