# LFM2.5 2.6B Q4_0: Mac STEM manual assessment

Provisional assistant review of all 100 raw-completion responses. This is not an official ADTC grade or competition score.

| Category | Complete pass | Core answer correct |
|---|---:|---:|
| Math multiple choice | 7/25 | 7/25 |
| Written math | 15/25 | 20/25 |
| Science multiple choice | 24/25 | 24/25 |
| Written science | 6/25 | 9/25 |
| Total | 52/100 | 60/100 |

Complete pass requires the correct answer, all requested substantive components and checks, and no unresolved material error. Core correctness is a separate diagnostic; it does not establish a complete explanation.

## Execution and grading

Mac/Metal, 2,048-token context, temperature 0, seed 42, two CPU threads, 99 GPU layers and 256 MiB cache. Multiple-choice responses have a 256-token limit; written responses have a 512-token limit. Requests use raw completion without a chat template or external system prompt.

All returned text is assessed, including thinking markers and drafting text. This differs from the judges chat test's final-answer-only policy. Explicit self-correction is allowed. A correct option value can pass without its letter; an unretracted wrong label cannot. Requested checks need a distinct numerical method or inverse/substitution calculation, not repetition. Token limits and extra formatting do not automatically fail an otherwise complete answer.

52 responses reach the token limit; 2 are empty. 5 contain an unclosed literal thinking marker. These counts describe the protocol, not automatic grading deductions.

## Incomplete or incorrect answers

| Category | IDs failing the complete-answer policy |
|---|---|
| Math multiple choice | M01, M02, M03, M04, M05, M08, M09, M11, M13, M14, M15, M16, M18, M19, M20, M21, M23, M24 |
| Written math | M28, M29, M30, M34, M39, M42, M43, M44, M45, M50 |
| Science multiple choice | S01 |
| Written science | S26, S27, S28, S29, S30, S32, S33, S34, S35, S36, S37, S38, S40, S41, S43, S44, S45, S48, S49 |

The JSON records a reason for every answer, separate core and strict decisions, source line, response hash, original parser flag and provenance. Repeated invented instructions are counted as non-answers when no solution is delivered; correct material before a cutoff is still assessed.

## Review boundaries

Independent review retained passes for S39, S42, S46 and S47. Their correct substantive explanations meet the prompts despite imprecise supplementary wording about water uptake, statistical significance, lunar observers and vapour-pressure dependence. Those caveats remain in the JSON.

## Verification

All 100 expected IDs, four category counts, source/configuration/event hashes, per-response hashes, model/server identities and score sums are validated. The primary assessor read all answers in full; independent assessors reviewed selected disputed cases, not a second full set of 100.
