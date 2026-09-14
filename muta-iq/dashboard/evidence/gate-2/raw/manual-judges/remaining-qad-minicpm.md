# Remaining Mac judges batches: manual assessment

Provisional assistant review, not an official competition score. All 20 final-answer and reasoning fields were read. Only delivered final text earns points; unfinished reasoning is excluded. The ten requests contain nine unique prompts because the proportional-learning question is repeated.

| Model | Score | Stopped finals | Truncated final fragments | Reasoning only |
|---|---:|---:|---:|---:|
| LFM2.5 2.6B QAD Q4_0 | 27/100 | 2 | 1 | 7 |
| MiniCPM5 1B Q4_K_M | 16/100 | 2 | 0 | 8 |

Both batches use the recorded Mac/Metal configuration: 4,096-token context, 1,024 generated-token limit, temperature 0, seed 3407, two CPU threads, 99 GPU layers, 256 MiB cache, embedded chat templates, and no external system prompt. These are accuracy observations, not GCP throughput or memory measurements. Both models have eight length-limit finishes.

## Prompt-level decisions

| Prompt | LFM QAD | MiniCPM Q4_K_M | Delivered evidence |
|---|---:|---:|---|
| Proportional learning | 0/10 | 0/10 | No final text. |
| Mastery differential equation | 7/10 | 0/10 | LFM delivers the correct solution, applies the initial condition, and interprets approaching the tutor's level. Its final text is truncated. |
| Offline model capacity | 0/10 | 0/10 | No final text. |
| Chalk calculation | 10/10 | 10/10 | Both select C and calculate 6 × 500 = 3,000. |
| Photosynthesis choice | 10/10 | 6/10 | LFM supplies B and a concise explanation. MiniCPM supplies only “B. Photosynthesis”. |
| Average-speed tutoring | 0/10 | 0/10 | No final text. |
| DNA tutoring | 0/10 | 0/10 | No final text. |
| Bilingual photosynthesis | 0/10 | 0/10 | No final text. |
| Proportional learning, repeat | 0/10 | 0/10 | No final text. |
| Rice profit | 0/10 | 0/10 | No final text. |

LFM's ODE fragment earns 4 points for the solution, 1 for the initial condition, and 2 for connecting the tutor's level to the student's limiting mastery. It omits the positive-k condition and reaches the token limit before addressing one-to-one tutoring's scaling constraints. Its excluded reasoning does not fill those omissions.

MiniCPM's photosynthesis answer earns 4 points for option B and 2 for naming the process. It receives neither the explanation points nor the concise-explanation points: an absent explanation does not satisfy either criterion.

An independent agent reviewed the LFM ODE final fragment and all delivered MiniCPM finals. The review confirmed both partial-credit decisions and retained the totals without changes. Source hashes, model and runtime metadata, all 20 prompt IDs, rubric weights, and score sums were validated.

The scores measure this template and generation-budget treatment. They do not establish performance with longer generation limits or different reasoning controls. The accompanying JSON retains every criterion, weight, decision, reason, source location, model hash, source-file hash, and response hash.
