# Manual judge-prompt review: three main Mac runs

Provisional assistant grading under the existing ten-prompt rubric. These are **not official
panel scores** and are separate from ARC-Easy and the GCP profiler-score estimates. All three
sets below used the main Metal configuration, a 256 MiB cache cap and a 1,024-token total
generation budget. The earlier pilot is excluded.

| Model | Manual rubric | Finished final answers | Truncated requests |
|---|---:|---:|---:|
| Fine-tuned Muta Qwen2.5 1.5B Q4_K_M | 44/100 | 10/10 | 0/10 |
| Qwen3 1.7B Q4_0 | 32/100 | 3/10 | 7/10 |
| MiniCPM5 1B pure Q4_0 | 25/100 | 3/10 | 7/10 |

The scores assess the substantive final text delivered within this budget. Correct work in
`reasoning_content` earns no final-answer credit. Qwen3 produced one additional substantive
but truncated final answer; MiniCPM produced two truncated introductory fragments without
the requested model or explanation. Each captured set contains all ten prompts.

| Prompt | Muta Qwen2.5 | Qwen3 | MiniCPM5 |
|---|---:|---:|---:|
| Proportional learning | 1 | 0 | 0 |
| Mastery ODE | 6 | 0 | 0 |
| 4 TOPS capacity | 0 | 0 | 0 |
| Chalk calculation | 2 | 10 | 10 |
| Photosynthesis MCQ | 10 | 10 | 10 |
| Average-speed misconception | 4 | 0 | 0 |
| DNA relationships | 8 | 6 | 5 |
| Bilingual photosynthesis | 4 | 6 | 0 |
| Proportional learning repeat | 1 | 0 | 0 |
| Rice profit | 8 | 0 | 0 |

Muta's completed answers still contain substantial errors: ₦2,500 for six ₦500 chalk boxes,
48 km/h instead of 53⅓, invalid learning-rate limits, and 17.2% instead of 17.3% profit. Its
ODE ends with the correct formula but uses invalid integration-constant working. Its purported
Yorùbá section is entirely English.

Qwen3 and MiniCPM answer both simple multiple-choice questions correctly. Most longer responses
consume the budget in reasoning. Their completed genetics explanations incorrectly describe
proteins as instructions or pages within a genetic book. Qwen3 rejects a student's correct
answer about chromosome location; MiniCPM asks a misleading question that assumes a mature human
red blood cell can synthesize proteins. Qwen3's partial bilingual answer repeats “koko” in
place of a translation.

This is a comparison at the tested output budget, not a claim about performance with longer
generation. The DNA and pedagogy criteria require reviewer judgment; all passed/failed items,
weights, reasons, completion states and source hashes are in
[control-minicpm-qwen3.json](control-minicpm-qwen3.json) for independent review.
