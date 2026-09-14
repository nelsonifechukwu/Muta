# MiniCPM5 1B Q4_K_M: GCP scalar judge-prompt assessment

MiniCPM5 1B Q4_K_M receives **6/100** under the provisional local rubric. This is not an official panel score, ARC-Easy accuracy or the composite competition score.

All ten requests completed. The only delivered final is the single letter **C** for the chalk question. It earns four points for the correct option and two for a concise answer, but no points for the numerical total or calculation, which appear only in reasoning.

| Result | Count |
| --- | ---: |
| Finished final answer | 1/10 |
| Partial final answer | 0/10 |
| Reasoning only at the token limit | 9/10 |

The photosynthesis request repeatedly drafts the correct option and explanation but never delivers them. Every human-judge prompt likewise ends without final text. These cases receive zero, even when intermediate reasoning contains correct work.

## Protocol

The verified Q4_K_M artifact ran on the pinned GCP scalar server with two CPU threads, no GPU offload, a 4,096-token context and a 256 MiB prompt-cache ceiling. Requests used its embedded template, no external system prompt, temperature 0, top-p 1 and seed 3407.

The output allowance was 1,024 tokens, including reasoning. The result measures delivery under that fixed budget; it does not establish unrestricted reasoning ability. This artifact is distinct from the separately tested pure Q4_0 MiniCPM5 1B.

## Evidence

[The criterion-level record](minicpm-1b-q4km.json) retains all ten decisions, exact model and execution identities, prompt hashes, lifecycle events, individual response-line hashes and the captured source-prefix hash. The [raw scalar responses](../raw/judges-responses.jsonl) remain unchanged.

An independent reviewer confirmed the six-point chalk grade and all nine reasoning-only completions. No Mac grades or performance measurements were pooled into this result.
