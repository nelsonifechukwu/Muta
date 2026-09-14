# Matched Mac STEM assessment

Twelve complete sets of the same 100 prompts. Falcon failed and remains unranked. These are provisional semantic assessments of raw-completion outputs, not official panel scores.

All twelve complete Mac sets were manually reviewed. This historical test uses raw completion without the embedded chat template. It is not equivalent to normal instruction-model chat, and all returned text is assessed, including planning text. It is not a final-answer-only tutoring-quality score.

| Rank | Model | Complete pass / 100 | Core correct / 100 | Math MC / 25 | Math written / 25 | Science MC / 25 | Science written / 25 |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | Qwen3.5 2B Q4_K_M | 77 | 95 | 22 | 22 | 23 | 10 |
| 2 | Qwen3.5 2B Q4_0 | 71 | 94 | 23 | 20 | 21 | 7 |
| 3 | LFM2.5 2.6B QAD-Q4_0 | 60 | 75 | 19 | 15 | 21 | 5 |
| 4 | Qwen3 1.7B Q4_0 | 59 | 81 | 15 | 21 | 16 | 7 |
| 5 | Muta Tutor Qwen2.5 1.5B Q4_K_M | 57 | 80 | 22 | 11 | 20 | 4 |
| 6 | LFM2.5 2.6B Q4_0 | 52 | 60 | 7 | 15 | 24 | 6 |
| 7 | LFM2.5 1.2B Thinking Q4_0 | 41 | 53 | 18 | 10 | 10 | 3 |
| 8 | OpenReasoning Nemotron 1.5B Q4_K_M | 35 | 60 | 18 | 10 | 6 | 1 |
| 9 | MiniCPM5 2B Q4_K_M | 17 | 35 | 9 | 4 | 1 | 3 |
| 10 | VibeThinker 1.5B Q4_K_M | 16 | 22 | 6 | 1 | 8 | 1 |
| 11 | MiniCPM5 1B Q4_K_M | 11 | 31 | 10 | 0 | 1 | 0 |
| 12 | MiniCPM5 1B pure Q4_0 | 6 | 16 | 3 | 0 | 1 | 2 |

Complete pass requires the correct main answer, all requested substantive reasoning and checks, and no unresolved material error. Core correctness records the central result even if supporting explanation is missing or faulty. A distinct numerical second method can satisfy a requested check. Token limits, repetition and formatting alone do not fail an otherwise complete answer. All grades are provisional assistant assessments; selected borderline cases received independent review.

[Per-answer decisions](manual-stem-mac/) · [Every prompt and unedited response](prompt-responses.md).

## Reading the comparison

The two Qwen3.5 2B quantizations have the most complete answers in this screen. Their 94–95 correct central answers fall to 71–77 complete passes when missing checks, incomplete explanations and material errors are included. This difference matters for a tutor that must explain a result, not merely state it.

The 100-prompt test does not apply the model chat template. Some outputs continue a question list, repeat instructions, or expose unfinished planning. These failures count under this historical raw-completion protocol, but do not establish how the same artifact behaves in chat. The [Gate 1 replay](judges-report.md) tests that separately.

STEM grades assess the entire returned completion, including planning. Gate 1 grades assess delivered final text only. Their totals must not be subtracted as if they measured the same behavior.

Each category has 25 questions. Complete-pass ranking uses ties without an arbitrary tie-break score. Core correctness is diagnostic and is not substituted for the competition accuracy term.

[GCP measurements and separate response inventory](report.md) · [All prompts and model answers](prompt-responses.md).
