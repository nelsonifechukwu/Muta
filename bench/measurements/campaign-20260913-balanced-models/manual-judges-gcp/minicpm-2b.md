# MiniCPM5 2B: GCP scalar judge-prompt assessment

MiniCPM5 2B Q4_K_M receives **20/100** under the provisional local rubric. This is not an official panel score, ARC-Easy accuracy or the composite competition score.

All ten requests completed. Only two delivered final answers; the remaining eight reached the 1,024-token limit with their text confined to separate reasoning.

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

## Protocol

The run used the verified GGUF on the pinned GCP scalar server: two CPU threads, no GPU offload, a 4,096-token context and 256 MiB prompt-cache ceiling. Each request used its embedded chat template, no external system prompt, temperature 0, top-p 1 and seed 3407.

The 1,024-token budget includes reasoning. Correct intermediate work, including the differential-equation solution and average-speed calculation, earns no final-answer credit if it is never delivered. No partial final occurs here.

## Evidence

[The criterion-level record](minicpm-2b.json) binds all ten decisions to exact prompt text, raw-record hashes, model identity, execution settings and lifecycle events. It retains a captured prefix hash of [the growing scalar response file](../raw/judges-responses.jsonl).

An independent reviewer confirmed both ten-point multiple-choice grades and checked all eight empty-final records. Raw responses, Mac assessments and inference settings were not changed.
