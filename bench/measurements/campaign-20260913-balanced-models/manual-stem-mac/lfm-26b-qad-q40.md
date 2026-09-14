# LFM2.5 2.6B QAD Q4_0: Mac STEM manual assessment

Provisional assistant review of all 100 raw-completion responses. This is not an official ADTC grade or competition score.

| Category | Complete pass | Core answer correct |
|---|---:|---:|
| Math multiple choice | 19/25 | 21/25 |
| Written math | 15/25 | 17/25 |
| Science multiple choice | 21/25 | 24/25 |
| Written science | 5/25 | 13/25 |
| Total | 60/100 | 75/100 |

Complete pass requires the correct answer, all requested substantive components and checks, and no unresolved material error. Core correctness is a separate diagnostic; it does not establish a complete explanation.

## Execution and grading

Mac/Metal, 2,048-token context, temperature 0, seed 42, two CPU threads, 99 GPU layers and 256 MiB cache. Multiple-choice responses have a 256-token limit; written responses have a 512-token limit. Requests use raw completion without a chat template or external system prompt.

All returned text is assessed, including thinking markers and drafting text. This differs from the judges chat test's final-answer-only policy. Explicit self-correction is allowed. A correct option value can pass without its letter; an unretracted wrong label cannot. Requested checks need a distinct numerical method or inverse/substitution calculation, not repetition. Token limits and extra formatting do not automatically fail an otherwise complete answer.

37 responses reach the token limit; 0 are empty. 6 contain an unclosed literal thinking marker. These counts describe the protocol, not automatic grading deductions.

## Incomplete or incorrect answers

| Category | IDs failing the complete-answer policy |
|---|---|
| Math multiple choice | M14, M16, M17, M19, M21, M25 |
| Written math | M30, M33, M38, M39, M41, M42, M43, M44, M47, M49 |
| Science multiple choice | S03, S06, S07, S08 |
| Written science | S26, S27, S28, S29, S30, S31, S32, S33, S34, S36, S37, S38, S39, S40, S45, S46, S47, S48, S49, S50 |

The JSON records a reason for every answer, separate core and strict decisions, source line, response hash, original parser flag and provenance. Repeated invented instructions are counted as non-answers when no solution is delivered; correct material before a cutoff is still assessed.

## Review boundaries

Independent review confirmed that S41's correct food-chain mechanism and S44's resolved sharp/blunt comparison pass despite imprecise wording. S49 describes a stronger future immune response, but stops before explaining retained immune memory; it receives core credit only.

S31 incorrectly calls oseltamivir an antibiotic; [CDC identifies it as an antiviral](https://www.cdc.gov/flu/treatment/antiviral-drugs.html). S46 gives a false general eclipse interval: [NASA describes about two lunar eclipses per year on average](https://science.nasa.gov/science-research/planetary-science/27mar_tetrad/), not one every two or three months.

## Verification

All 100 expected IDs, four category counts, source/configuration/event hashes, per-response hashes, model/server identities and score sums are validated. The primary assessor read all answers in full; independent assessors reviewed selected disputed cases, not a second full set of 100.
