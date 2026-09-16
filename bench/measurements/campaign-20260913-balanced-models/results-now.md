# Current benchmark results

All thirteen load-compatible models have completed ARC-Easy-500 and GCP scalar/vector throughput measurements. Twelve completed the matched Mac STEM and Gate 1 screens and have manual assessments. Falcon failed the Mac screen. The GCP scalar Gate 1 replay is still incomplete in this snapshot; no final submission selection is established.

Response-count snapshot: 2026-09-14T19:20:56+00:00. GCP counts reflect the latest synchronized evidence, not a live counter.

## Accuracy, speed, memory and efficiency

Scalar determines this provisional score ordering. Vector means the separately measured AVX2/FMA/F16C CPU build on the same VM. Accuracy is the shared official-profiler ARC-Easy `acc_norm` result, not a judges grade. Its evaluation wheel has a separately compiled CPU path; these are not paired scalar and vector accuracy runs.

| Model | ARC-Easy-500 | Scalar / vector tg128 (tok/s) | Estimated scalar / vector RSS (MiB) | Scalar / vector efficiency | Scalar / vector total |
|---|---:|---:|---:|---:|---:|
| MiniCPM5 1B pure Q4_0 | 55.8% | 18.30 / 30.80 | 727 / 1,088 | 89.86 / 84.82 | 75.87 / 74.86 |
| LFM2.5 1.2B Thinking Q4_0 | 46.0% | 13.78 / 23.70 | 804 / 1,351 | 88.78 / 81.16 | 68.32 / 69.23 |
| Muta Tutor Qwen2.5 1.5B Q4_K_M | 77.8% | 5.64 / 17.28 | 1,117 / 1,707 | 84.42 / 76.19 | 67.06 / 84.14 |
| MiniCPM5 1B Q4_K_M | 56.0% | 9.55 / 27.72 | 799 / 1,111 | 88.86 / 84.50 | 64.86 / 74.90 |
| Qwen3 1.7B Q4_0 | 65.2% | 7.81 / 15.39 | 1,212 / 1,941 | 83.09 / 72.92 | 64.83 / 77.18 |
| Falcon-H1-Tiny-R 0.6B Q4_K_M | 30.4% | 13.69 / 35.79 | 498 / 766 | 93.06 / 89.31 | 61.20 / 63.06 |
| Qwen3.5 2B Q4_0 | 65.0% | 6.20 / 13.10 | 1,368 / 2,043 | 80.92 / 71.50 | 61.07 / 72.99 |
| Qwen3.5 2B Q4_K_M | 65.2% | 4.42 / 11.86 | 1,430 / 1,921 | 80.04 / 73.20 | 57.45 / 70.95 |
| MiniCPM5 2B Q4_K_M | 67.6% | 3.97 / 12.36 | 1,652 / 2,560 | 76.96 / 64.28 | 57.12 / 71.38 |
| OpenReasoning Nemotron 1.5B Q4_K_M | 53.6% | 5.77 / 17.20 | 1,117 / 1,706 | 84.41 / 76.20 | 55.23 / 72.04 |
| LFM2.5 2.6B QAD-Q4_0 | 45.4% | 6.18 / 10.77 | 1,709 / 3,006 | 76.16 / 58.06 | 50.29 / 55.84 |
| LFM2.5 2.6B Q4_0 | 43.6% | 6.23 / 10.36 | 1,709 / 3,006 | 76.15 / 58.06 | 49.48 / 54.13 |
| VibeThinker 1.5B Q4_K_M | 39.2% | 5.77 / 16.73 | 1,242 / 1,831 | 82.67 / 74.45 | 47.66 / 64.49 |

The totals are reconstructed estimates, not completed end-to-end official-profiler runs. Throughput is directly measured with five llama-bench repetitions. Estimated profiler RSS adds a fixed 45 MiB Python-root allowance to measured benchmark process-tree RSS. The CSV also retains measured RSS without that allowance. Efficiency = 100 × (7 − estimated RSS in GiB) / 7. Performance = 100 × min(TPS / 15, 1). Total = 0.50 × accuracy + 0.30 × performance + 0.20 × efficiency. Temperature is unavailable on GCP; no thermal penalty is applied.

## 100-prompt STEM test

All twelve complete Mac sets were manually reviewed. The matched ranking is below; the separate GCP capture inventory follows it. This historical test uses raw completion without the embedded chat template. It is not equivalent to normal instruction-model chat, and all returned text is assessed, including planning text. It is not a final-answer-only tutoring-quality score.

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

### Separate GCP capture inventory

These counters are not manual accuracy grades. MC counts use extracted option letters only. The three completed original scalar semantic reviews remain separate in `manual-stem/`; remaining GCP STEM answers are not fully adjudicated.

| Model | Original GCP scalar / 100 | MC options correct / captured | Written captured / 50 | Separate scalar restart / 100 | Separate GCP vector / 100 | Mac / 100 |
|---|---:|---:|---:|---:|---:|---:|
| MiniCPM5 1B pure Q4_0 | 100/100 | 7/50 | 50/50 | 0/100 | 0/100 | 100/100 |
| LFM2.5 1.2B Thinking Q4_0 | 100/100 | 25/50 | 50/50 | 0/100 | 0/100 | 100/100 |
| Muta Tutor Qwen2.5 1.5B Q4_K_M | 100/100 | 44/50 | 50/50 | 0/100 | 0/100 | 100/100 |
| MiniCPM5 1B Q4_K_M | 100/100 | 13/50 | 50/50 | 0/100 | 0/100 | 100/100 |
| Qwen3 1.7B Q4_0 | 100/100 | 33/50 | 50/50 | 0/100 | 0/100 | 100/100 |
| Falcon-H1-Tiny-R 0.6B Q4_K_M | 0/100 | not run | 0/50 | 0/100 | 0/100 | 0/100 |
| Qwen3.5 2B Q4_0 | 100/100 | 10/50 | 50/50 | 0/100 | 0/100 | 100/100 |
| Qwen3.5 2B Q4_K_M | 35/100 | 5/25 | 10/50 | 28/100 | 100/100 | 100/100 |
| MiniCPM5 2B Q4_K_M | 100/100 | 9/50 | 50/50 | 0/100 | 0/100 | 100/100 |
| OpenReasoning Nemotron 1.5B Q4_K_M | 0/100 | not run | 0/50 | 0/100 | 0/100 | 100/100 |
| LFM2.5 2.6B QAD-Q4_0 | 100/100 | 25/50 | 50/50 | 0/100 | 0/100 | 100/100 |
| LFM2.5 2.6B Q4_0 | 100/100 | 24/50 | 50/50 | 0/100 | 0/100 | 100/100 |
| VibeThinker 1.5B Q4_K_M | 0/100 | not run | 0/50 | 0/100 | 100/100 | 100/100 |

The two partial scalar attempts for Qwen3.5 2B Q4_K_M overlap and remain separate. They are not combined with each other or with vector/Mac responses. Legacy scalar records lack a hardware-context field; the original runner/log provenance identifies that stage, and the missing field remains explicit. See the [GCP STEM attempt inventory](gcp-stem-attempts.md) for all response files and execution differences, including thread and cache settings.

## Judges prompts

The GCP scalar Gate 1 replay is still incomplete in this snapshot; no final submission selection is established. Mac and GCP use the same ten prompts and 1,024-token output limit. This limit is our local setting, not a confirmed official judge limit. The grades are provisional semantic assessments against our fixed local rubric, not official panel grades.

10 completed GCP scalar sets have separate manual assessments. Failed, unreviewed and incomplete sets have no score or rank. All rubric grades below are out of 100. This paired table follows the completed Mac ordering; the [scalar-only ranking](gcp-judges-responses.md) orders the reviewed GCP results.

| Mac rank | Model | Mac finished finals / 10 | Mac rubric | GCP scalar captured / 10 | GCP scalar finished finals / 10 | GCP scalar rubric | GCP recorded state |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | Muta Tutor Qwen2.5 1.5B Q4_K_M | 10/10 | 44 | 10/10 | 10/10 | 47 | reviewed |
| 2 | Qwen3 1.7B Q4_0 | 3/10 | 32 | 10/10 | 3/10 | 28 | reviewed |
| 3 | LFM2.5 2.6B QAD-Q4_0 | 2/10 | 27 | 10/10 | 2/10 | 20 | reviewed |
| 4 | LFM2.5 1.2B Thinking Q4_0 | 2/10 | 25 | 10/10 | 2/10 | 25 | reviewed |
| 4 | MiniCPM5 1B pure Q4_0 | 3/10 | 25 | 10/10 | 3/10 | 24 | reviewed |
| 6 | VibeThinker 1.5B Q4_K_M | 2/10 | 22 | 9/10 | 2/10 | — | partial |
| 7 | LFM2.5 2.6B Q4_0 | 2/10 | 20 | 10/10 | 2/10 | 20 | reviewed |
| 7 | MiniCPM5 2B Q4_K_M | 2/10 | 20 | 10/10 | 2/10 | 20 | reviewed |
| 7 | Qwen3.5 2B Q4_0 | 2/10 | 20 | 10/10 | 1/10 | 10 | reviewed |
| 7 | Qwen3.5 2B Q4_K_M | 2/10 | 20 | 10/10 | 2/10 | 20 | reviewed |
| 11 | MiniCPM5 1B Q4_K_M | 2/10 | 16 | 10/10 | 1/10 | 6 | reviewed |
| 12 | OpenReasoning Nemotron 1.5B Q4_K_M | 0/10 | 0 | 0/10 | 0/10 | — | not started |
| — | Falcon-H1-Tiny-R 0.6B Q4_K_M | 0/10 | failed; not ranked | 0/10 | 0/10 | — | not started |

Manual grading credits delivered final answers only. Separate reasoning and all `<think>`-block content receive no final-answer credit. A truncated final answer can earn points for completed criteria. A normal stop means the answer finished, not that it was correct. Many reasoning models exhaust the shared token limit before reaching a final answer, so these grades measure delivery under that limit rather than unconstrained reasoning ability.

The main Mac and GCP judges tests cap host prompt cache at 256 MiB. The earlier control pilot used the default ceiling and is retained separately. Mac accuracy screens do not supply laptop throughput, memory, or competition totals.

Falcon failed generation on Mac and in the earlier GCP vector STEM batch. Those failures do not establish the outcome of its separate scalar Gate 1 attempt; that state is reported in the table above. The vector STEM batch completed Qwen3.5 Q4_K_M and VibeThinker, then stopped on Falcon before reaching Nemotron. No failed run is substituted with a zero accuracy score.

The Mac comparison is complete for twelve models under these fixed protocols. It does not replace the GCP scalar replay. Qwen3.5 2B Q4_K_M leads the raw-completion STEM assessment; the fine-tuned Qwen2.5 control leads this final-answer Gate 1 screen. These different rankings reflect different prompts, request formats, token budgets and grading rules, not a universal model ranking.

## Evidence

- [Download CSV](results-now.csv)
- [GCP ARC-Easy records](raw/accuracy.jsonl)
- [GCP scalar throughput](raw/throughput.jsonl)
- [GCP vector throughput](raw/vector-throughput.jsonl)
- [Original GCP STEM responses](raw/stem-responses.jsonl)
- [Separate scalar STEM restart](raw/stem-responses-gcp-remainder.jsonl)
- [GCP STEM attempt inventory and execution differences](gcp-stem-attempts.md)
- [GCP vector STEM responses](raw/stem-responses-vector-remainder.jsonl)
- [Mac queue and per-model responses](mac-accuracy/)
- [Mac control pilot](raw/judges-responses-mac-pilot.jsonl)
- [Criterion-level manual judges assessments](manual-judges/)
- [Separate GCP scalar judges assessments](manual-judges-gcp/)
- [Complete prompts and returned answers](prompt-responses.md)
- [Criterion-level Mac STEM assessments](manual-stem-mac/)

Spark-X2.5-1.7B remains excluded because the pinned runtime cannot load its architecture.
