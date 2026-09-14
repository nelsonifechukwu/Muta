# Qwen3.5 2B Q4_K_M: GCP scalar judge-prompt assessment

Qwen3.5 2B Q4_K_M receives **20/100** under the provisional local rubric. This is not an official panel score, ARC-Easy accuracy or the composite competition score.

All ten requests completed. Two delivered final answers; eight reached the local token limit with their output confined to separate reasoning. No partial final occurred.

| Prompt | Score | Delivered result |
| --- | ---: | --- |
| Proportional learning model | 0/10 | No final answer |
| Mastery differential equation | 0/10 | No final answer |
| Offline LLM capacity | 0/10 | No final answer |
| Lagos chalk calculation | 10/10 | C; 6 × ₦500 = ₦3,000 |
| Photosynthesis multiple choice | 10/10 | B; correct one-sentence explanation |
| Average-speed tutoring | 0/10 | No final answer |
| DNA tutoring | 0/10 | No final answer |
| English/Yorùbá photosynthesis | 0/10 | No final answer |
| Repeated proportional model | 0/10 | No final answer |
| Onitsha rice profit | 0/10 | No final answer |

Correct intermediate work appears in reasoning, including the differential-equation solution and average-speed calculation. It earns no delivered-answer credit because the student-facing answer fields are empty.

## Protocol

The verified Q4_K_M artifact ran on the pinned GCP scalar server: two CPU threads, no GPU offload, a 4,096-token context and 256 MiB prompt-cache ceiling. Requests used its embedded chat template, no external system prompt, temperature 0, top-p 1 and seed 3407.

The 1,024-token allowance includes reasoning and is a local campaign setting, not an asserted official judge limit. The result measures delivery under this setting. A substantive partial final would receive credit for completed criteria, but this set contains none.

## Evidence

[The criterion-level record](qwen35-2b-q4km.json) retains all ten decisions, exact model and execution identities, prompt hashes, lifecycle events, individual raw-record hashes and the captured source-prefix hash. The [raw scalar responses](../raw/judges-responses.jsonl) remain unchanged.

An independent reviewer confirmed both ten-point answers and all eight reasoning-only completions. No Mac assessments, Q4_0 results or performance measurements were pooled into this score.
