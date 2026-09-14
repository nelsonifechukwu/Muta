# Balanced model comparison

Retain the fine-tuned **Muta Tutor Qwen2.5 1.5B Q4_K_M** as the control for the next stage. It has the highest ARC-Easy result (77.8%) and GCP Gate 1 rubric score (47/100), and delivers finished final answers to all ten Gate 1 requests. Its reconstructed score is 67.06 on scalar and 84.14 on vector. This is a next-stage choice, not a claim of competition qualification or a guaranteed winning model.

**Qwen3.5 2B Q4_K_M** is the alternative for further chat validation: it leads the Mac raw-completion STEM test with 77 complete passes and 95 correct central answers. In GCP chat, however, it finishes only two of the ten Gate 1 answers and scores 20/100 under the local output limit.

**MiniCPM5 1B pure Q4_0** leads the scalar ARC-based proxy at 75.87, but achieves only 6/100 complete STEM passes on Mac and 24/100 Gate 1 rubric points on GCP. That resource-weighted score alone does not establish the tutoring quality required for this track.

Thirteen artifacts completed GCP performance and ARC-Easy-500 measurements. Twelve completed and were manually assessed on both the GCP Gate 1 replay and the separate Mac accuracy screens. Falcon failed generation and is unranked on those screens; Spark could not load on the pinned runtime and is excluded.

## Accuracy, speed, memory and efficiency

Scalar determines this provisional score ordering. Vector means the separately measured AVX2/FMA/F16C CPU build on the same VM. Accuracy is the shared official-profiler ARC-Easy `acc_norm` result, not a judges grade. Its evaluation wheel has a separately compiled CPU path; these are not paired scalar and vector accuracy runs.

| Model | ARC-Easy-500 | Scalar / vector pp512 (tok/s) | Scalar / vector tg128 (tok/s) | Decode gain | Estimated scalar / vector RSS (MiB) | Scalar / vector efficiency | Scalar / vector total |
|---|---:|---:|---:|---:|---:|---:|---:|
| MiniCPM5 1B pure Q4_0 | 55.8% | 29.76 / 95.67 | 18.30 / 30.80 | 1.68× | 727 / 1,088 | 89.86 / 84.82 | 75.87 / 74.86 |
| LFM2.5 1.2B Thinking Q4_0 | 46.0% | 21.06 / 67.79 | 13.78 / 23.70 | 1.72× | 804 / 1,351 | 88.78 / 81.16 | 68.32 / 69.23 |
| Muta Tutor Qwen2.5 1.5B Q4_K_M | 77.8% | 7.81 / 61.60 | 5.64 / 17.28 | 3.06× | 1,117 / 1,707 | 84.42 / 76.19 | 67.06 / 84.14 |
| MiniCPM5 1B Q4_K_M | 56.0% | 14.66 / 112.80 | 9.55 / 27.72 | 2.90× | 799 / 1,111 | 88.86 / 84.50 | 64.86 / 74.90 |
| Qwen3 1.7B Q4_0 | 65.2% | 13.64 / 44.71 | 7.81 / 15.39 | 1.97× | 1,212 / 1,941 | 83.09 / 72.92 | 64.83 / 77.18 |
| Falcon-H1-Tiny-R 0.6B Q4_K_M | 30.4% | 17.24 / 119.34 | 13.69 / 35.79 | 2.61× | 498 / 766 | 93.06 / 89.31 | 61.20 / 63.06 |
| Qwen3.5 2B Q4_0 | 65.0% | 12.61 / 42.46 | 6.20 / 13.10 | 2.11× | 1,368 / 2,043 | 80.92 / 71.50 | 61.07 / 72.99 |
| Qwen3.5 2B Q4_K_M | 65.2% | 7.08 / 40.32 | 4.42 / 11.86 | 2.68× | 1,430 / 1,921 | 80.04 / 73.20 | 57.45 / 70.95 |
| MiniCPM5 2B Q4_K_M | 67.6% | 5.10 / 40.14 | 3.97 / 12.36 | 3.12× | 1,652 / 2,560 | 76.96 / 64.28 | 57.12 / 71.38 |
| OpenReasoning Nemotron 1.5B Q4_K_M | 53.6% | 7.77 / 60.47 | 5.77 / 17.20 | 2.98× | 1,117 / 1,706 | 84.41 / 76.20 | 55.23 / 72.04 |
| LFM2.5 2.6B QAD-Q4_0 | 45.4% | 8.84 / 28.97 | 6.18 / 10.77 | 1.74× | 1,709 / 3,006 | 76.16 / 58.06 | 50.29 / 55.84 |
| LFM2.5 2.6B Q4_0 | 43.6% | 8.85 / 28.86 | 6.23 / 10.36 | 1.66× | 1,709 / 3,006 | 76.15 / 58.06 | 49.48 / 54.13 |
| VibeThinker 1.5B Q4_K_M | 39.2% | 7.81 / 60.25 | 5.77 / 16.73 | 2.90× | 1,242 / 1,831 | 82.67 / 74.45 | 47.66 / 64.49 |

The totals are reconstructed estimates, not completed end-to-end official-profiler runs. Throughput is directly measured with five llama-bench repetitions. Estimated profiler RSS adds a fixed 45 MiB Python-root allowance to measured benchmark process-tree RSS. The CSV also retains measured RSS without that allowance. Efficiency = 100 × (7 − estimated RSS in GiB) / 7. Performance = 100 × min(TPS / 15, 1). Total = 0.50 × accuracy + 0.30 × performance + 0.20 × efficiency. Temperature is unavailable on GCP; no thermal penalty is applied.

## STEM accuracy on Mac

The same 100 prompts were tested on Mac Metal for all twelve complete runs. Each category has 25 questions. A complete pass requires a correct central result, all requested substantive reasoning and checks, and no unresolved material error. Core correctness is a separate diagnostic.

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

This historical test uses raw completion, not the embedded chat template. All returned text is assessed, including planning. It is not the same test or grading policy as the final-answer-only Gate 1 replay. [STEM methods and assessments](stem-report.md) · [Every Mac prompt and response](prompt-responses.md).

## Gate 1 replay on GCP

These are the five automated-test prompts and five human-judge prompts in the supplied Gate 1 feedback, with local criterion-based grading. They are known prompts, not an unseen test. The repeated Two Sigma question occupies two positions. Two unreadable currency glyphs were restored to ₦; other wording is unchanged apart from whitespace.

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

Scores are local rubric points, not percentages of questions correct or official panel scores. The 1,024-token limit includes reasoning and is a local setting, not a confirmed competition limit. Only delivered final text receives credit. Partial final answers can earn completed-criterion points; unclosed thinking receives none. Nemotron therefore scores zero despite some correct intermediate work. Falcon has no grade because its run failed.

[Gate 1 methods and interpretation](judges-report.md) · [Every GCP prompt, response and decision](gcp-judges-responses.md).

## Execution and limitations

- GCP is an x86 cloud proxy with four logical CPUs, two physical cores and approximately 8 GiB RAM. It is not the physical audit laptop. Scalar disables AVX/AVX2/FMA/F16C; vector enables AVX2/FMA/F16C with AVX-512 disabled. These labels describe the selected builds, not a guarantee that every scalar-build instruction is SISD.
- GCP Gate 1 uses two CPU threads, no GPU, context 4,096, a 256 MiB host prompt-cache cap, temperature 0, seed 3407, top-p 1 and each artifact’s embedded chat template without an external system prompt. The paired Mac replay uses the same request settings with GPU offload on an M4 Pro with 24 GiB RAM. Answers can differ across backends; Mac scores are not substituted into GCP grades.
- Mac STEM uses context 2,048, temperature 0, seed 42 and 256/512 output tokens for multiple-choice/written prompts, without a chat template. Earlier GCP STEM attempts also differ in thread and cache settings. Their partial and overlapping records remain separate in the [GCP STEM inventory](gcp-stem-attempts.md); they are not added to the Mac totals.
- Model execution was serial. Locks and host checks prevented competing campaign inference; watchdogs recorded interruptions from detected build activity. These records do not prove continuous absence of every unrelated CPU workload. Response wall times are not used as benchmark throughput.
- Manual assessments used full responses and recorded criterion decisions. Selected cases received independent review. The small, known Gate 1 set and protocol-specific STEM test are insufficient to establish general tutoring superiority. No new fine-tuning was performed in this comparison.
- Stock challengers still need a documented adaptation and base-versus-adapted comparison. The supplied Gate 2 guidance permits disclosed prompt-only adaptation as well as weight training. This campaign does not certify submission eligibility.

## Files

- [All measurements, separate accuracy grades and sources](results.csv)
- [GCP scalar judges ranking](judges-ranking.csv)
- [STEM report](stem-report.md) and [Gate 1 report](judges-report.md)
- [GCP prompts and complete responses](gcp-judges-responses.md), [Mac prompts and complete responses](prompt-responses.md), and [GCP STEM attempts](gcp-stem-attempts.md)
- [Artifact inventory](artifacts.csv), [adjudication policy](ADJUDICATION.md), and [Falcon failure](failures/falcon-gcp-scalar.md)
- [Host completion audit](host-completion.md): no inference remains. The gateway restore failed because native UI synchronization omits required SVG assets; the UI is unavailable. This separate fault has not been repaired.

Earlier `results-now` files are retained as interim snapshots. The files linked above contain the completed comparison.
