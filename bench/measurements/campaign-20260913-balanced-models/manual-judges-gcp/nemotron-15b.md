# OpenReasoning Nemotron 1.5B Q4_K_M: GCP scalar judge-prompt assessment

Nemotron receives **0/100** under the provisional local delivered-answer rubric. All ten requests completed, but every response reached the 1,024-token allowance before closing its inline reasoning block. None delivered a finished or substantive partial final answer.

This is not an official panel score, ARC-Easy accuracy or the composite competition score. It does not mean every intermediate calculation was wrong.

| Prompt | Score | Delivered result |
| --- | ---: | --- |
| Proportional learning model | 0/10 | No final answer |
| Mastery differential equation | 0/10 | No final answer |
| Offline LLM capacity | 0/10 | No final answer |
| Lagos chalk calculation | 0/10 | No final answer |
| Photosynthesis multiple choice | 0/10 | No final answer |
| Average-speed tutoring | 0/10 | No final answer |
| DNA tutoring | 0/10 | No final answer |
| English/Yorùbá photosynthesis | 0/10 | No final answer |
| Repeated proportional model | 0/10 | No final answer |
| Onitsha rice profit | 0/10 | No final answer |

Correct work appears in the saved reasoning, including the differential-equation solution, ₦3,000 chalk calculation and 53.33 km/h average speed. Other passages contain errors or repetition. Neither correct intermediate work nor a phrase such as “final answer” inside an unclosed reasoning block earns delivered-final credit.

## Protocol

The verified artifact ran on the pinned GCP scalar server with two CPU threads, no GPU offload, a 4,096-token context and a 256 MiB prompt-cache ceiling. Requests used the embedded chat template, no external system prompt, temperature 0, top-p 1 and seed 3407.

The 1,024-token allowance includes reasoning and is a local campaign setting, not an asserted official judge limit. All ten answer fields are nonempty and contain literal unclosed think blocks; all separate reasoning fields are empty. A substantive partial final would earn completed-criterion credit, but this set contains none. No runtime failure was recorded for this model.

## Evidence

[The criterion ledger](nemotron-15b.json) retains all ten decisions, exact artifact and execution identities, lifecycle events, individual raw-record hashes and the captured source-prefix hash. [Raw scalar responses](../raw/judges-responses.jsonl) remain unchanged. Mac assessments and performance measurements are not pooled into this result.

An independent reviewer read all ten complete responses without consulting the primary ledger and confirmed the absence of final text, all completion counts and the zero-point result under this policy.
