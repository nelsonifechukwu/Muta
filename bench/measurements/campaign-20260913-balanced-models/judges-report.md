# Gate 1 replay

Five automated-test prompts and five human-judge prompts from the supplied Gate 1 feedback. The Two Sigma prompt occurs twice, so the ten items are not ten independent samples. Unreadable currency glyphs were restored to ₦ in two prompts; other wording is unchanged apart from whitespace.

The GCP scalar Gate 1 requests have ended; review and selection status are reported separately. Mac and GCP use the same ten prompts and 1,024-token output limit. This limit is our local setting, not a confirmed official judge limit. The grades are provisional semantic assessments against our fixed local rubric, not official panel grades.

12 completed GCP scalar sets have manual assessments. The table ranks GCP scalar rubric points out of 100, with Mac results alongside for comparison. Failed and incomplete sets have no score or rank.

| GCP rank | Model | Mac finished finals / 10 | Mac rubric | GCP scalar captured / 10 | GCP scalar finished finals / 10 | GCP scalar rubric | GCP recorded state |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | Muta Tutor Qwen2.5 1.5B Q4_K_M | 10/10 | 44 | 10/10 | 10/10 | 47 | reviewed |
| 2 | Qwen3 1.7B Q4_0 | 3/10 | 32 | 10/10 | 3/10 | 28 | reviewed |
| 2 | VibeThinker 1.5B Q4_K_M | 2/10 | 22 | 10/10 | 2/10 | 28 | reviewed |
| 4 | LFM2.5 1.2B Thinking Q4_0 | 2/10 | 25 | 10/10 | 2/10 | 25 | reviewed |
| 5 | MiniCPM5 1B pure Q4_0 | 3/10 | 25 | 10/10 | 3/10 | 24 | reviewed |
| 6 | LFM2.5 2.6B Q4_0 | 2/10 | 20 | 10/10 | 2/10 | 20 | reviewed |
| 6 | LFM2.5 2.6B QAD-Q4_0 | 2/10 | 27 | 10/10 | 2/10 | 20 | reviewed |
| 6 | MiniCPM5 2B Q4_K_M | 2/10 | 20 | 10/10 | 2/10 | 20 | reviewed |
| 6 | Qwen3.5 2B Q4_K_M | 2/10 | 20 | 10/10 | 2/10 | 20 | reviewed |
| 10 | Qwen3.5 2B Q4_0 | 2/10 | 20 | 10/10 | 1/10 | 10 | reviewed |
| 11 | MiniCPM5 1B Q4_K_M | 2/10 | 16 | 10/10 | 1/10 | 6 | reviewed |
| 12 | OpenReasoning Nemotron 1.5B Q4_K_M | 0/10 | 0 | 10/10 | 0/10 | 0 | reviewed |
| — | Falcon-H1-Tiny-R 0.6B Q4_K_M | 0/10 | failed; not ranked | 5/10 | 0/10 | — | failed |

Manual grading credits delivered final answers only. Separate reasoning and all `<think>`-block content receive no final-answer credit. A truncated final answer can earn points for completed criteria. A normal stop means the answer finished, not that it was correct. Many reasoning models exhaust the shared token limit before reaching a final answer, so these grades measure delivery under that limit rather than unconstrained reasoning ability.

The main Mac and GCP judges tests cap host prompt cache at 256 MiB. The earlier control pilot used the default ceiling and is retained separately. Mac accuracy screens do not supply laptop throughput, memory, or competition totals.

Falcon also failed the GCP scalar Gate 1 replay: five responses were captured before a parser error on the sixth request. It remains unranked. Nemotron completed all ten requests but delivered no final text before the token limit, giving 0/100 under the final-only rubric. This does not imply zero underlying mathematical knowledge. Full responses and the Falcon failure log remain available.

The Mac comparison is complete for twelve models under these fixed protocols. It does not replace the GCP scalar replay. Qwen3.5 2B Q4_K_M leads the raw-completion STEM assessment; the fine-tuned Qwen2.5 control leads this final-answer Gate 1 screen. These different rankings reflect different prompts, request formats, token budgets and grading rules, not a universal model ranking.

[Reviewed GCP scalar prompts, answers and assessments](gcp-judges-responses.md) · [Supplementary Mac prompts and responses](prompt-responses.md) · [Source-bound GCP scalar reviews](manual-judges-gcp/).
