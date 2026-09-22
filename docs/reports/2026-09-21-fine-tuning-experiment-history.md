# Muta fine-tuning and selection history

The expanded Gate 2 record is in [03 · Improving Accuracy: Model fine-tuning](https://muta-iq.vercel.app/#gate-2-experiments), with dedicated anchors for the [data](https://muta-iq.vercel.app/#g2-exp-data), [pilots](https://muta-iq.vercel.app/#g2-exp-pilots), [full runs](https://muta-iq.vercel.app/#g2-exp-full), [science-tutor selection](https://muta-iq.vercel.app/#g2-exp-science), [matched decision](https://muta-iq.vercel.app/#g2-exp-evaluation), [loss record](https://muta-iq.vercel.app/#g2-exp-loss), and [packaging](https://muta-iq.vercel.app/#g2-exp-packaging).

## 1. Baseline and method

The Gate 1 Muta model was produced with BF16 LoRA:

| Item | Setting |
|---|---|
| Base | Qwen2.5-1.5B-Instruct |
| Adapter | LoRA, rank 16 |
| Learning rate | 2 × 10⁻⁵ |
| Steps | 500 |
| Loss | Assistant-only |

The later sweep kept BF16 LoRA because it used the available GPUs efficiently.
QLoRA was preregistered as a memory-control branch, but no completed QLoRA
result is in the retained experiment records and it must not be reported as an
executed run.

Shared pilot settings were effective batch 64, 512-token maximum sequence
length, rank-specific α, dropout 0, seed 3407, warmup/cosine schedule and
attention/MLP projection targets. Each pilot used 20,000 training rows and
5,000 validation rows, with 313 optimizer steps.

## 2. 20K hyperparameter pilots

Eight BF16 LoRA pilots were completed. Four used fresh Qwen weights and four
started from the recovered Muta parent. The values below are final validation
losses; lower is not an accuracy or tutoring score.

| Pilot | Init. | Rank | LR | Dev loss |
|---|---|---:|---:|---:|
| warm-r16-lr2e5 | Muta | 16 | 2 × 10⁻⁵ | 0.217060 |
| warm-r32-lr1e5 | Muta | 32 | 1 × 10⁻⁵ | 0.339828 |
| clean-r32-lr1e5 | Qwen | 32 | 1 × 10⁻⁵ | 0.346829 |
| warm-r16-lr1e5 | Muta | 16 | 1 × 10⁻⁵ | 0.578009 |
| clean-r16-lr1e5 | Qwen | 16 | 1 × 10⁻⁵ | 0.593257 |
| warm-r32-lr5e6 | Muta | 32 | 5 × 10⁻⁶ | 0.685911 |
| warm-r16-lr5e6 | Muta | 16 | 5 × 10⁻⁶ | 0.961763 |
| warm-r8-lr5e6 | Muta | 8 | 5 × 10⁻⁶ | 1.151685 |

Loss gallery: [all eight pilots](https://muta-iq.vercel.app/#g2-exp-pilots) · [interactive gallery and provenance](https://muta-iq.vercel.app/#g2-exp-loss).

The sweep selected `warm-r16-lr5e6` as the practical pilot lineage for later
full-data comparison. This was a provisional selection, not proof of overall
superiority.

## 3. Full-data runs

Three full-data BF16 LoRA runs were then completed, each using the verified
300,350-row private artifact:

| Run | Initialization | Rank / LR | Final dev loss | Outcome |
|---|---|---|---:|---|
| Clean | Fresh Qwen2.5-1.5B-Instruct | 16 / 1 × 10⁻⁵ | 0.018999 | Exported |
| Warm | Recovered Muta parent | 16 / 5 × 10⁻⁶ | 0.022473 | Exported |
| Pilot continuation | Exact `warm-r16-lr5e6` adapter lineage; fresh optimizer/schedule | 16 / 5 × 10⁻⁶ | 0.022921 | Exported |

Selected full-run checkpoint: step 4693. Loss plots and run provenance: [full-data experiment section](https://muta-iq.vercel.app/#g2-exp-full) · [loss record](https://muta-iq.vercel.app/#g2-exp-loss).

The lower full-run losses reflect the larger training run and are not directly
comparable with the 20K pilot losses across different hosts, datasets and
training stages.

## 4. Science-tutor dataset and pilots

The science-tutor corpus was built for tutoring behavior, not only answer
matching. It targeted conceptual, quantitative, experimental and scientific
judgment skills, misconception repair, adaptive dialogue and accessible
explanations across mathematics, physics, chemistry, biology and Earth science.

Candidate sources included SciInstruct, ScienceQA/SciQ, MathDial and
ConvoLearn. SciInstruct was quarantined as distillation-style data; only
source-screened examples admitted by the final manifest entered training.
Teacher-model drafts were treated as drafts, not ground truth. Calculations
were recomputed and weak, contradictory or unsupported examples were rejected.

| Split | Rows |
|---|---:|
| Training | **8,002** |
| Development | **1,577** |
| Final holdout | **1,591** |

The four science pilots all completed 126 steps on the same 8,002 training rows:

| Pilot | Initialization | Result |
|---|---|---|
| P1 | Untouched Qwen + fresh LoRA | Completed |
| P2 | Original Muta + fresh LoRA | Completed |
| P3 | Historical warm-pilot adapter; fresh optimizer/schedule | Completed |
| P4 | DeepSeek-R1-Distill-Qwen + native tokenizer/masking | Completed |

Science-pilot loss plot: [four-pilot panel and selection record](https://muta-iq.vercel.app/#g2-exp-science).

Development selection used 12 candidate checkpoints × 72 prompts. `P1-end`
had the highest unguarded point score, but failed the preregistered regression
guard. `P2-half` was the only lineage admitted to refinement:

| Candidate | M / 64 | S / 32 | T / 32 | Index | Decision |
|---|---:|---:|---:|---:|---|
| P2-half | 52 | 17 | 24 | 72.66% | **Advance** |
| P1-end | 51 | 18 | 26 | 74.22% | Guard failure |
| P4-half | 45 | 15 | 25 | 66.41% | Reject |
| P3-half | 45 | 6 | 15 | 51.56% | Reject |

This was a development-stage decision only; it did not promote P2 to
deployment.

## 5. Final matched comparison

The final roster compared the incumbent, untouched Qwen, historical warm pilot,
untouched DeepSeek and P2-half. The frozen practical battery contained 2,000
questions; the known judges/STEM results were joined descriptively from sealed
runs. “Judges” is a keyword screen, not a complete semantic grade.

| Model | Held-out science | Practical / 2,000 | Tutor quality / 64 | Judges / 100 | STEM MC / 50 |
|---|---:|---:|---:|---:|---:|
| **Previous Muta** | **83.565%** | **41.325** | **22** | **57** | 32 |
| P2-half | 83.565% | 39.850 | 12 | 50 | 32 |
| Untouched Qwen | 82.554% | 38.425 | 17 | 61 | **35** |
| Historical warm | 83.375% | 12.500 | 8 | 57 | 30 |
| Untouched DeepSeek | Answer-delivery failure | 0.200 | 15 | Failed gate | Failed gate |

The conservative promotion rule required no material practical or known-suite
regression plus a tutoring advantage. P2 tied the incumbent on held-out science
but trailed on the practical battery and tutor quality. Therefore:

**Final decision: retain the previous Muta Tutor Qwen2.5-1.5B.** No challenger
was promoted and the default deployment file was not swapped.

Full comparison receipt: [final matched decision](https://muta-iq.vercel.app/#g2-exp-evaluation).

Loss gallery for all retained histories: [five-model comparison and original Muta](https://muta-iq.vercel.app/#g2-exp-loss).

## 6. Interpretation and limits

The experiments show that more supervised fine-tuning did not improve the
incumbent on the frozen practical/tutoring tests. They do **not** prove that
all further fine-tuning would cause catastrophic forgetting or that gains are
impossible. They show that these data mixtures, checkpoints and training
settings did not justify replacement; future work should improve data quality,
dialogue coverage and verification before increasing training volume.

Target-CPU qualification was not measured in these runs. GPU timings are not
ADTC CPU scores. Raw responses, loss curves, hashes, failed attempts and source
licence records remain in `provenance/`.

## 7. Post-selection packaging

After model selection, the requested Qwen3.5-style judge template was embedded
as metadata in a separate, tensor-identical GGUF. It is a packaging variant,
not a new fine-tune or a new winner. The original incumbent remains unchanged.
See the [Gate 2 packaging record](https://muta-iq.vercel.app/#g2-exp-packaging).
