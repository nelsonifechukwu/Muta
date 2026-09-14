# GCP scalar judge-prompt assessment: first three models

These are provisional assistant-graded results for the ten retained judge-prompt positions, not official panel scores, ARC-Easy accuracy or the composite ADTC score. All thirty requests completed. A completed request does not necessarily contain a final answer.

| Model | Local rubric score | Finished finals | Partial finals | No final answer |
| --- | ---: | ---: | ---: | ---: |
| Fine-tuned Muta Qwen2.5 1.5B Q4_K_M | 47/100 | 10/10 | 0/10 | 0/10 |
| LFM2.5 1.2B Thinking Q4_0 | 25/100 | 2/10 | 1/10 | 7/10 |
| MiniCPM5 1B pure Q4_0 | 24/100 | 3/10 | 0/10 | 7/10 |

## Fixed protocol

All three models use the same recorded GCP scalar server, two CPU threads, no GPU offload, 4,096-token context and 256 MiB prompt-cache ceiling. Each request uses the GGUF's embedded chat template, no external system prompt, temperature 0, top-p 1, seed 3407 and a 1,024-token output budget that includes reasoning.

Only delivered final text earns points. Separate reasoning and literal think blocks were read but excluded. A partial final earns only criteria completed before truncation. The two short-answer criteria retain the existing 500-character concise-response threshold; sentence-format deviations are noted separately. These ten positions contain nine unique prompt wordings because the proportional-model prompt is repeated.

The scores below apply the existing criterion weights by semantic review. No keyword grade or Mac result is substituted.

| Prompt | Muta Qwen2.5 | LFM Thinking | MiniCPM5 |
| --- | ---: | ---: | ---: |
| automated_01 — Two Sigma proportional model | 8 | 0 | 0 |
| automated_02 — Mastery differential equation | 1 | 0 | 0 |
| automated_03 — Offline LLM capacity | 0 | 0 | 0 |
| automated_04 — Lagos chalk calculation | 2 | 10 | 10 |
| automated_05 — Photosynthesis multiple choice | 10 | 10 | 10 |
| human_01 — Average-speed misconception | 3 | 0 | 0 |
| human_02 — DNA genes chromosomes and proteins | 6 | 5 | 4 |
| human_03 — Bilingual photosynthesis tutoring | 0 | 0 | 0 |
| human_04 — Two Sigma model repeat | 8 | 0 | 0 |
| human_05 — Onitsha rice profit | 9 | 0 | 0 |

## Findings

The control delivers all ten finals. Its chalk answer is wrong, its differential-equation solution reverses the exponential sign, and its average-speed calculation incorrectly adds 1.5 and 0.75 hours to two hours. The two-point chalk score rewards concision only, not correctness.

Its rice calculation correctly gives ₦86,825 revenue, ₦12,825 profit and 17.3% profit on cost. The attempted check ignores the discounted batch and obtains 24.3%; the verification point is withheld. Its bilingual answer repeats English under the Yorùbá heading and omits water and chlorophyll.

LFM finishes both multiple-choice answers correctly. Its partial DNA final identifies several relationships but calls proteins instructions; seven other responses end inside unclosed think blocks. MiniCPM5 finishes the two multiple-choice answers and its DNA answer. The latter confuses proteins with instructions, uses an invalid understanding question and does not repair a specific incorrect conceptual answer. Its seven remaining requests have empty final fields.

The reasoning-model scores therefore reflect both correctness and failure to deliver within this token budget. They do not establish how well those models would answer with a larger budget.

## Evidence and review

[Criterion-level decisions](first-three.json) retain every point, reason and flag, exact GGUF identities, execution settings, lifecycle events, prompt hashes and individual raw-record hashes. The source is [the scalar response file](../raw/judges-responses.jsonl); the assessment is bound to a captured prefix as that file continues to grow. [The rubric](../../../judges_prompt_report.py) and [exact prompt suite](../../../judges_prompt_suite.py) are unchanged.

An independent reviewer read all six disputed control responses and both reasoning-model DNA finals. The lead reviewer confirmed that MiniCPM5's generic response to “I don't understand” does not meet the incorrect-answer correction criterion. Raw responses and Mac assessments were not changed.
