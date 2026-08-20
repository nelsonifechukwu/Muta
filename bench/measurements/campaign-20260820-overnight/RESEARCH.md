# Research notes — 20 August 2026

## Competition boundary

The submitted artifact is one GGUF. The executable participant profiler runs its own
`llama-bench` and accuracy adapter. Runtime changes such as speculative decoding, prompt caching,
KV-cache policy, thread selection, and custom memory streaming do not change this score unless the
organiser changes the executable. They remain product optimizations, not model-file optimizations.

The public challenge page and executable profiler use different performance formulas. This
campaign preserves both:

- executable profiler: `S_perf = 100 * min(TPS / 15, 1)`;
- public page: `S_perf = 100 * TPS / TPS_max`, evaluated here with an effective denominator of
  `max(pre-entry cohort floor, candidate TPS)`.

## Local inference references

The following local references were read before the campaign:

- `books/the-physics-of-llm-inference-apr-21-revision.pdf`;
- `books/buildanllminferenceengineinc.pdf`;
- `books/Inference Engineering.epub`.

They support three constraints used in the experiment design: CPU decode is generally limited by
weight traffic, tensor packing and kernel support can matter more than nominal bit width, and
additional threads stop helping after memory bandwidth saturates. The campaign therefore measures
each exact GGUF on both the profiler-compatible scalar binary and the portable AVX2 binary instead
of estimating throughput from file size.

## Model search

The staged screen covered these model classes:

- official small general models: Qwen3.5-0.8B, Qwen3.5-2B, Gemma-3-1B;
- small mathematics fine-tunes: Qwen3-0.6B Math-Expert, Qwen2-0.5B NuminaMath;
- larger reasoning specialists: OpenMath-Nemotron-1.5B, VibeThinker-1.5B, Noema-2B;
- one Qwen3.5-0.8B reasoning distill as a provenance-controlled comparison.

Advancement required a valid license, exact revision and SHA-256, successful b10175 load, useful
scalar throughput, and acceptable ARC-Easy. The manifest records every file and revision. Raw
throughput and accuracy rows remain in this directory, including rejected candidates.

## Math-Expert provenance

The public source card describes Qwen3-0.6B Math-Expert as a full BF16 fine-tune of Qwen3-0.6B on
`unsloth/OpenMathReasoning-mini`, using TRL supervised fine-tuning and chain-of-thought examples.
The card does not publish training hyperparameters or a benchmark table. The GGUF repository uses
static quants and states that an importance-matrix series is unavailable. The upstream NVIDIA
OpenMathReasoning dataset is CC-BY-4.0; the smaller Unsloth mirror does not carry an equally complete
dataset card. These limitations are recorded because the direct profiler result alone does not
establish training reproducibility or hidden-task generalization.

Primary sources:

- <https://huggingface.co/suayptalha/Qwen3-0.6B-Math-Expert>
- <https://huggingface.co/mradermacher/Qwen3-0.6B-Math-Expert-GGUF>
- <https://huggingface.co/datasets/unsloth/OpenMathReasoning-mini>
- <https://huggingface.co/datasets/nvidia/OpenMathReasoning>
- <https://arxiv.org/abs/2504.16891>

## Quantization evidence

Recent reasoning-quantization studies report that low-bit post-training quantization can introduce
large mathematical-reasoning losses and that targeted recovery training can restore some of the
loss. The local measurements reproduce the first claim: pure Q4_0 raises scalar generation from
11.93 to 22.79 tok/s but lowers ARC-Easy-50 from 68% to 52%. Raising only the tied embedding to Q6_K
or Q8_0 does not recover the loss. Raising the last four transformer blocks to Q5_0 reaches 56% and
13.59 tok/s, still below Q4_K_M on the measured score.

Sources:

- <https://arxiv.org/abs/2501.03035>
- <https://arxiv.org/abs/2505.11574>
- <https://arxiv.org/abs/2601.14888>

A new quantization-aware fine-tune was not attempted on the CPU-only VM. Promoting such a file would
require a GPU training environment, a frozen dataset and recipe, F16/BF16 export, GGUF conversion,
and the same profiler and broader-accuracy gates used here.

## Methods excluded from the GGUF score

llama.cpp supports server-side draft, n-gram, EAGLE, and MTP speculation, but these require runtime
flags. The profiler's `llama-bench` invocation does not enable them. Additional MTP tensors would
therefore add bytes without improving the measured run. See
<https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md> and the open
`llama-bench` MTP feature request <https://github.com/ggml-org/llama.cpp/issues/22947>.

Context metadata also cannot change the fixed p512/tg128 workload. The embedded chat template can
affect interactive judging, but it does not affect raw `llama-bench` throughput or the profiler's
multiple-choice adapter. Vocabulary pruning was not attempted on the Qwen GPT-2/BPE tokenizer
because the current pruner does not rewrite BPE merges safely.

## Embedded-template gate

The final Qwen3.5-0.8B artifact rewrites GGUF metadata only. An independent raw-tensor comparison
verified all 320 tensors and 496,192,768 tensor bytes as identical to the pinned source. The
template injects the tutor system prompt and forces non-thinking ChatML when the caller supplies no
setting.

The live four-prompt battery found a practical reason for the forced setting: in automatic thinking
mode, both finalists consumed the 256-token allowance in `reasoning_content` and returned no answer.
Non-thinking mode produced direct answers, but both models failed the √2 proof prompt. This test is
an acceptance check rather than an accuracy score. Its full responses are retained in the campaign
directory.

## Finalist results by CPU configuration

The direct participant-profiler run and the controlled AVX2 screen produce the following result:

| Artifact | Direct scalar TPS / RSS / ARC-Easy-50 / total | AVX2 pp512 / tg128 / est. RSS / total |
|---|---:|---:|
| Qwen3-0.6B Math-Expert Q4_K_M | 12.72 / 540.32 MiB / 68% / 77.9324 | 153.9351 / 39.2320 / 759.7 MiB / **81.8803** |
| Muta Tutor Qwen3.5-0.8B Q4_0 final | 12.63 / 670.39 MiB / 64% / 75.3895 | 98.0094 / 27.1509 / 928.1 MiB / 79.4104 |

AVX2 totals use ARC-Easy-50 and the executable profiler's fixed 15 tok/s cap. Both models saturate
the performance term. Math-Expert then leads through its four-point accuracy advantage and lower
estimated RSS. Substituting the matched ARC-Easy-500 estimates reverses the AVX2 order: Qwen scores
76.8104 and Math-Expert 75.1803. This larger-sample result is diagnostic.

The AVX2 binary is SHA-256 `4abfa11a3f86b8c5e4d508cce10daf8f381c968585a3e5961fea3d5cbe312fd8`.
It enables AVX/AVX2/FMA/F16C and disables native tuning and AVX-512. AVX2 RSS is measured child-tree
peak plus a 45 MiB profiler-root estimate. Math-Expert used the exact finalist GGUF. Qwen used the
pinned source whose tensor identity with the final metadata-wrapped artifact is recorded above.
