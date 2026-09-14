# Mac judges-prompt review: MiniCPM5 2B Q4_K_M

Provisional assistant review, not an official judges' score. All ten response and reasoning records were read. The model scores **20/100** under the existing local rubric.

| Finished final answers | Truncated requests | Partial finals | Reasoning-only responses |
|---:|---:|---:|---:|
| 2 / 10 | 8 / 10 | 0 | 8 / 10 |

The model correctly finishes the chalk calculation and photosynthesis multiple-choice question, earning ten points each. The other eight requests exhaust the 1,024-token output budget before any final answer. Correct calculations inside unfinished reasoning earn no final-answer credit.

This is the main Mac Metal treatment: embedded chat template, no external system prompt, 4,096-token context, 256 MiB cache cap, temperature 0, seed 3407, and at most 1,024 generated tokens. It is separate from GCP scalar accuracy and does not establish the model's performance with longer output budgets.

The [criterion-level record](minicpm-2b.json) contains each pass/fail decision and rationale with the source-file, model and server hashes.
