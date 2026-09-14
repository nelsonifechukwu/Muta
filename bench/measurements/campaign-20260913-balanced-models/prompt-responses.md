# Prompts and model responses

This index preserves the matched Mac Metal screen, including completed sets and failed requests. Captured counts below define coverage; missing answers are not zero grades. GCP measurements and replays remain separate.

STEM: 100 raw-completion prompts per model, with 256 output tokens for multiple choice and 512 for written responses. Gate 1: ten chat prompts per model, with a shared 1,024-token output budget including reasoning. These are local test limits, not confirmed organizer limits.

The Gate 1 set contains five automated-test prompts and five human-judge prompts supplied with the original feedback. Unreadable currency glyphs were restored to ₦ in two prompts; other wording is unchanged apart from whitespace. Local rubric scores are assistant assessments, not organizer grades.

| Model | Full STEM responses | Full Gate 1 responses | Provisional Mac Gate 1 rubric |
|---|---:|---:|---:|
| Muta Tutor Qwen2.5 1.5B · Q4_K_M | [100/100](<transcripts/mac/Muta-Tutor-Qwen2.5-1.5B-Finetuned-Q4_K_M.gguf/stem.md>) | [10/10](<transcripts/mac/Muta-Tutor-Qwen2.5-1.5B-Finetuned-Q4_K_M.gguf/judges.md>) | 44/100 |
| LFM2.5 1.2B Thinking · Q4_0 | [100/100](<transcripts/mac/LFM2.5-1.2B-Thinking-Q4_0.gguf/stem.md>) | [10/10](<transcripts/mac/LFM2.5-1.2B-Thinking-Q4_0.gguf/judges.md>) | 25/100 |
| MiniCPM5 1B · pure Q4_0 | [100/100](<transcripts/mac/MiniCPM5-1B-Q4_0.gguf/stem.md>) | [10/10](<transcripts/mac/MiniCPM5-1B-Q4_0.gguf/judges.md>) | 25/100 |
| Qwen3.5 2B · Q4_0 | [100/100](<transcripts/mac/Qwen3.5-2B-Q4_0.gguf/stem.md>) | [10/10](<transcripts/mac/Qwen3.5-2B-Q4_0.gguf/judges.md>) | 20/100 |
| Qwen3 1.7B · Q4_0 | [100/100](<transcripts/mac/Qwen3-1.7B-Q4_0.gguf/stem.md>) | [10/10](<transcripts/mac/Qwen3-1.7B-Q4_0.gguf/judges.md>) | 32/100 |
| LFM2.5 2.6B · Q4_0 | [100/100](<transcripts/mac/LFM2.5-2.6B-Q4_0.gguf/stem.md>) | [10/10](<transcripts/mac/LFM2.5-2.6B-Q4_0.gguf/judges.md>) | 20/100 |
| MiniCPM5 2B Q4_K_M | [100/100](<transcripts/mac/MiniCPM5-2B-Q4_K_M.gguf/stem.md>) | [10/10](<transcripts/mac/MiniCPM5-2B-Q4_K_M.gguf/judges.md>) | 20/100 |
| LFM2.5 2.6B QAD-Q4_0 | [100/100](<transcripts/mac/LFM2.5-2.6B-QAD-Q4_0.gguf/stem.md>) | [10/10](<transcripts/mac/LFM2.5-2.6B-QAD-Q4_0.gguf/judges.md>) | 27/100 |
| MiniCPM5 1B Q4_K_M | [100/100](<transcripts/mac/MiniCPM5-1B-Q4_K_M.gguf/stem.md>) | [10/10](<transcripts/mac/MiniCPM5-1B-Q4_K_M.gguf/judges.md>) | 16/100 |
| Qwen3.5 2B Q4_K_M | [100/100](<transcripts/mac/Qwen3.5-2B-Q4_K_M.gguf/stem.md>) | [10/10](<transcripts/mac/Qwen3.5-2B-Q4_K_M.gguf/judges.md>) | 20/100 |
| VibeThinker 1.5B Q4_K_M | [100/100](<transcripts/mac/VibeThinker-1.5B-q4_k_m.gguf/stem.md>) | [10/10](<transcripts/mac/VibeThinker-1.5B-q4_k_m.gguf/judges.md>) | 22/100 |
| Falcon-H1-Tiny-R 0.6B Q4_K_M | [0/100](<transcripts/mac/Falcon-H1R-0.6B-Q4_K_M.gguf/stem.md>) | [3/10](<transcripts/mac/Falcon-H1R-0.6B-Q4_K_M.gguf/judges.md>) | incomplete; unranked |
| OpenReasoning Nemotron 1.5B Q4_K_M | [100/100](<transcripts/mac/nvidia_OpenReasoning-Nemotron-1.5B-Q4_K_M.gguf/stem.md>) | [10/10](<transcripts/mac/nvidia_OpenReasoning-Nemotron-1.5B-Q4_K_M.gguf/judges.md>) | 0/100 |

Empty and truncated answers are retained verbatim. Falcon's failed requests remain visibly missing; no answers are fabricated or substituted. A source hash changing invalidates its attached manual assessment.

## Separate evidence

- [Campaign report](report.md)
- [Measurements and separate accuracy assessments](results.csv)
- [Separate GCP and Mac Gate 1 rankings](judges-ranking.csv)
- [Matched Mac STEM ranking](stem-report.md)
- [Gate 1 replay and grading](judges-report.md)
- [GCP scalar prompts, answers and assessments](gcp-judges-responses.md)
- [Original GCP scalar STEM review](manual-stem/)
- [Matched Mac STEM review](manual-stem-mac/)
- [GCP scalar Gate 1 raw responses](raw/judges-responses.jsonl)

Runtime-excluded artifacts: Spark-X2.5-1.7B-Q4_K_M.gguf.
