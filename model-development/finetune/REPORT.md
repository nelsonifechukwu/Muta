# Fine-tuning campaign

## Question

Can supervised parameter updates improve the two leading GGUF candidates without increasing
their deployment footprint? Qwen3.5 0.8B remains in Q4_0 for the scalar configuration;
Qwen2.5 1.5B remains in Q4_K_M for the vector configuration.

## Design

The campaign trained 15 candidates on one NVIDIA A100 40 GB. It varied:

- BF16 LoRA and 4-bit QLoRA;
- ranks 8, 16, and 32;
- balanced, reasoning-heavy, multiple-choice, and hybrid data;
- learning rates from 1e-5 to 1e-4; and
- 250–500 optimization steps or one full epoch.

All runs used seed 3407, 1,024-token context, completion-only loss, micro-batch 4, and four-step
gradient accumulation. The effective batch size was 16. Adapters covered the attention and MLP
projection tensors. Every survivor was merged, exported to its deployment quantization, and
evaluated as a GGUF. Training loss was not a promotion criterion.

The final comparisons use matched controls. Qwen2.5 uses an untuned checkpoint passed through
the same export and quantization path. Qwen3.5 uses a rank-16, zero-learning-rate control passed
through the same adapter, merge, export, and quantization path. Its effective weight update is
zero, and its tensor names and types match the trained artifact.

## Why the first sweep failed

The first eight candidates used clean training splits, but their mixture did not match the
profiler task. Most examples were long solutions, tutoring dialogue, or general chat; only about
2,200 examples used the profiler's short multiple-choice continuation format. Validation loss
therefore measured fit to the training mixture rather than transfer to ARC-Easy.

The data builder also concatenated the raw prompt and completion as `Answer:choice`. The
evaluation harness supplies `Answer:` as context and ` choice` as the continuation. That leading
space can change BPE tokenization. On ARC-Easy-500, the first-phase Qwen3.5 QLoRA model scored
56.8% against the recorded 58.8% base, while Qwen2.5 BF16 rank 16 scored 66.6% against 71.8%.
None of the eight candidates was promoted.

## Data correction

The corrected phase matched the raw continuation format before tokenization and trained on
source training splits only. A held-out guard contained 8,477 validation and test questions. It
removed 111 train-to-held-out overlaps and 187 cross-source duplicates using exact matching,
five-gram Jaccard similarity, sequence similarity, and duplicate prompt/completion checks.

The final Qwen3.5 mixture used 15,355 training and 808 validation rows from ARC-Easy,
ARC-Challenge, OpenBookQA, and QASC. The final Qwen2.5 submission candidate used a licence-clean
10,756/566-row mixture of ARC and QASC multiple-choice examples. OpenBookQA was removed from this
candidate because its current dataset card does not state a licence. SciQ was excluded because
its licence is non-commercial; evaluation sets such as MMLU-Pro were not used for training.

The corrected phase also tested hybrid mixtures with verified GSM8K and OpenR1-Math solutions.
They did not beat the multiple-choice candidates on the measured objective. QLoRA reduced
training memory but did not improve the final quantized model.

## Final matched results

Accuracy is ARC-Easy `acc_norm` over the same 500 items. Throughput is the mean of two clean
rounds, each containing five internal repetitions on the GCP 2-core/4-thread proxy. RSS is the
measured benchmark child tree plus a 45 MiB estimate for the profiler process. Temperature is
unavailable on GCP.

| Model | Control → tuned accuracy | Scalar tok/s | Scalar RSS | Scalar total | Vector tok/s | Vector RSS | Vector total |
|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen3.5 0.8B Q4_0 | 55.2% → **70.2%** | 13.60 | 691 MiB | 72.8896 → **80.3664** | 27.69 | 969 MiB | 74.8959 → **82.3962** |
| Qwen2.5 1.5B Q4_K_M | 74.4% → **77.8%** | 5.63 | 1,117 MiB | 65.3277 → **67.0475** | 17.44 | 1,706 MiB | 82.4386 → **84.1387** |

Qwen3.5 gains 15.0 accuracy points and approximately 7.5 total points in either CPU
configuration. Qwen2.5 gains 3.4 accuracy points and approximately 1.7 total points. Throughput
and RSS remain effectively unchanged within each matched pair, so the score changes are
accuracy gains rather than performance or memory trade-offs.

The Qwen3.5 secondary battery provides a limited transfer check:

| Benchmark | Samples | Control → tuned |
|---|---:|---:|
| ARC-Challenge | 100 | 32% → **42%** |
| OpenBookQA | 100 | 32% → **33%** |
| GSM8K strict | 25 | 16% → **20%** |

The Qwen2.5 secondary battery is pending. An unrelated package build occupied the CPU host, so
the run was stopped rather than retained as contaminated evidence. QASC was unavailable in the
installed evaluation registry and is not reported as zero.

## Decision

- **Scalar configuration:** fine-tuned Qwen3.5 0.8B Q4_0, total 80.3664.
- **Vector configuration:** fine-tuned Qwen2.5 1.5B Q4_K_M, total 84.1387.

Neither GGUF is submission-ready yet. The selected artifact must receive the embedded tutor
template and sampling defaults, pass the live tutoring and stop-token battery, and complete the
physical-laptop profiler run with temperature and throttling measurements. Qwen2.5 also needs
its interrupted secondary battery completed.

## Reproducibility

The machine-readable result is in `results/summary.json`. Dataset manifests, training manifests,
artifact records, raw benchmark rows, and scripts are retained in this directory. The workflow
uses pinned versions of Unsloth, Transformers, PEFT, bitsandbytes, and llama.cpp. Generated
checkpoints and GGUF weights remain outside git.

Method references: [LoRA](https://arxiv.org/abs/2106.09685),
[QLoRA](https://arxiv.org/abs/2305.14314),
[QASC](https://huggingface.co/datasets/allenai/qasc),
[OpenR1-Math](https://huggingface.co/datasets/open-r1/OpenR1-Math-220k), and the
[Unsloth Qwen3.5 guide](https://unsloth.ai/docs/models/qwen3.5/fine-tune).
