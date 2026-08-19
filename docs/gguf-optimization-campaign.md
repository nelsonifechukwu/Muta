# GGUF-only optimization campaign — 19 August 2026

## Decision target

The campaign initially relied on an old repository claim that organisers had privately
confirmed a physical AVX2 audit and uncapped cohort-relative score on 6 August. Cross-checking
on 19 August found no source for that claim. Current official sources conflict: the challenge
page describes relative scoring/target laptops, while the profiler README/code use a capped
15 tok/s reference and cloud-VM audit mode. This campaign follows the executable profiler.

The GCP `n2-custom-4-8192` VM is an **x86 cloud proxy (2 physical cores / 4 threads)**. It is
useful for same-host candidate comparisons but cannot measure the target laptop's DDR4
bandwidth or thermal penalty. No cloud result is report-grade target evidence.

## Evidence rules

- One BF16 source revision per quantization ladder; no low-bit up-quantization.
- One exact b10175 reference binary (native/AVX/AVX2/FMA/F16C disabled) and binary SHA for
  every scored timed row. AVX2 rows are retained as a separate deployment comparison.
- Interleaved repetitions, append-only JSONL, whole-process-tree RSS at 100 ms.
- Accuracy tasks, sample counts, templates and seeds remain separate; missing tasks are never
  borrowed from another quant or model.
- Scores use the profiler's fixed 15 tok/s cap. The conflicting webpage-relative formula is
  shown only as clearly labelled sensitivity, never averaged with the profiler score.
- Temperature is unknown on GCP and is labelled unknown, not assumed cool.

For two candidates A and B below the profiler cap, the measurable score difference is:

```text
ΔS = 0.5·Δaccuracy_points + 2·ΔTPS − (20 / 7)·ΔRSS_GB − ΔP_thermal
```

Once a candidate reaches 15 tok/s, additional throughput is worth zero under this rule.

## Technique map

| Technique | Campaign treatment | Reason |
|---|---|---|
| Q4_K_S / Q4_K_M / IQ4_XS / Q5_0 / Q5_K_M / Q6_K / Q3_K_M | Direct BF16 ladder | File size is not RSS on AVX2: Q4_0 and Q4_K repack, while IQ4_XS, Q5_K, Q6_K and Q3_K do not. |
| Importance-aware quantization | Test with pinned 137-chunk vendor matrix | llama.cpp supports `--imatrix`; activation-aware methods preserve salient channels better than weight-magnitude-only selection. The matrix identifies its source as `calibration_datav3.txt`, but that corpus is not published with the artifact, so strict evaluation-set disjointness cannot be independently proved and is recorded as a limitation. |
| Per-tensor mixed quantization | Promote only from the best body quant | Protect output/embedding and `ffn_down`/attention-value tensors only when measured quality repays bytes and RSS. |
| Tied versus retained output head | Highest-priority isolated A/B | Upstream declares tied embeddings, but removing a higher-precision output copy can still change low-bit logits. |
| Layer pruning | One middle layer first; hard quality gate | It saves real dense GGUF bytes, but recent evidence finds multi-step reasoning unusually depth-sensitive. |
| Unstructured / 2:4 pruning | Documented rejection | SparseGPT and Wanda can preserve dense-model quality, but the submitted dense GGUF and stock llama.cpp kernels still store and multiply zeros; no scored size/TPS gain. |
| Smaller architecture | Same-host controls after the structural ladder | A genuinely smaller trained model can dominate pruning; prior 1B candidates were fast but failed maths quality. |
| Distillation | Existing distilled checkpoint only | Distillation is valuable when followed by training, but a new reproducible train/merge/convert/audit cycle is not feasible on the 8 GB CPU VM in seven hours. |
| Quantization-aware fine-tuning | Research-backed next campaign, not fabricated here | QAT and LR-QAT can recover low-bit loss, but require GPU training, data/provenance and full re-evaluation before a GGUF exists. |
| Vocabulary pruning | Rejected for current Qwen tooling | Qwen uses GPT-2 BPE with 151,387 merge rules and no `tokenizer.ggml.scores`; the existing SPM pruner neither parses nor rewrites that graph. |
| Context metadata | Safety-only finalist A/B | The profiler fixes its own `p512/tg128` workload; metadata cannot reduce mapped weights. Never alter RoPE base to fake a smaller context. |
| Tensor layout/alignment | Validate, do not hand-rewrite | Stock llama.cpp quantization already enforces block shapes and alignment. A custom layout unsupported by the audit binary is a load failure. |
| Embedded template / sampling defaults | Live judging A/B only | Metadata can improve the human tutoring interaction, but must not be credited to raw llama-bench or template-free lm-eval rows. |
| Low-rank/SVD replacement | Rejected from prior destructive result | Dense low-rank factors require graph/runtime support and prior Muta-IQ SVD experiments showed unacceptable reconstruction error at byte-saving ranks. |

## Scientific basis

- llama.cpp's official quantizer exposes importance matrices, per-tensor type overrides and
  layer pruning: <https://github.com/ggml-org/llama.cpp/blob/master/tools/quantize/README.md>.
- AWQ motivates activation-aware protection of salient channels:
  <https://arxiv.org/abs/2306.00978>.
- SparseGPT and Wanda show that one-shot pruning can preserve model quality, but they do not
  create a speedup in a dense-only submitted format: <https://arxiv.org/abs/2301.00774> and
  <https://arxiv.org/abs/2306.11695>.
- Vocabulary trimming can work for multilingual models when the tokenizer graph and embedding
  rows are rewritten coherently: <https://arxiv.org/abs/2305.15020>. That prerequisite is not
  met by the current Qwen pruner.
- QAT and low-rank QAT can improve low-bit quality but are training procedures, not metadata
  edits: <https://arxiv.org/abs/2305.17888> and <https://arxiv.org/abs/2406.06385>.
- Layer pruning without recovery is risky for generative reasoning:
  <https://arxiv.org/abs/2602.01997>.

## Campaign artifacts

Raw rows, a scored summary, candidate recipes, source/tool hashes and the final decision are
stored under `bench/measurements/campaign-20260819/`. GGUF files remain untracked and are
identified exclusively by immutable SHA-256.

## Primary profiler-reference verdict

The score-of-record comparison used b10175 commit `60bccc…`, binary sha256 `7f01dc…9370`,
with native/AVX/AVX2/AVX-512/FMA/F16C disabled on the GCP 2C/4T proxy. The incumbent retained
llama-bench's five default internal repetitions; slow scalar challengers used a clearly labelled
one-repetition promotion screen. All used `p512/tg128`, `-ngl 0`, the same binary and whole-tree
RSS sampler.

| Artifact | Decode TPS | Est. profiler RSS MiB | ARC-Easy proxy | Est. S_total, capped 15 | Verdict |
|---|---:|---:|---:|---:|---|
| **Muta Tutor Qwen3-1.7B Q4_0 tied** `a98ce3…` | **9.9869** | **1133.1** | **72%** | **72.81** | **keep / submission winner** |
| Qwen3-1.7B Q4_K_M tied `e8a413…` | 5.2954 | 1183.5 | 72% | 63.29 | reject |
| Qwen3-1.7B Q5_K_M tied `17ddf7…` | 4.7839 | 1364.5 | 76% | 63.76 | reject; Easy gain does not repay scalar decode/RSS |
| Qwen3-1.7B IQ4_XS tied `aea3cb…` | 2.4961 | 1081.8 | 70% | 56.97 | reject |
| BitCPM4-8B TQ2_0 envocab `069621…` | 0.8108 | 2316.3 | 88% | 59.16 | reject under profiler rule; retain as UI/alternative candidate |

RSS adds a 45 MiB estimate for the profiler Python root process to the measured llama-bench
child-tree peak. The resulting efficiency term and composite are therefore estimates. The
winner is decisive on this objective. Q4_K_M preserves Easy accuracy but loses 4.69 tok/s;
IQ4_XS saves only 51 MiB while losing 7.49 tok/s and two accuracy points; BitCPM gains 16
accuracy points but loses 9.18 tok/s and adds 1.16 GiB. The score uses ARC-Easy as a labelled
proxy for the unavailable judging-panel `S_acc`, and thermal is unknown on GCP.

## Supplemental AVX2 result (not the score-of-record)

The AVX2 proxy showed why deployment and audit evidence must be kept separate: the 974 MB
Q4_0 file occupied about 2.0 GiB RSS,
whereas the 920 MB IQ4_XS candidate occupied about 1.0 GiB, but Q4_0 decoded faster. Kernel
choice, repack, accuracy and bytes must be scored together.

The finalist evidence is:

| Artifact | Decode TPS | RSS MiB | ARC-Easy | ARC-Challenge | SciQ | Verdict |
|---|---:|---:|---:|---:|---:|---|
| Qwen Q4_0 control `a98ce3…` | ≈16.6 | ≈2049 | 72% | 42% | 94% | superseded control |
| Qwen Q4_K_S tied `bff602…` | ≈16.8 | ≈2030 | 72% | — | — | low-denominator hedge |
| Qwen Q4_K_M tied `e8a413…` | ≈16.5 | ≈1990 | 72% | 48% | 96% | balanced Qwen winner |
| Qwen Q5_K_M tied `17ddf7…` | ≈12.9 | ≈1364 | 76% | 42% | 94% | Easy-only bump; reject |
| BitCPM4-8B TQ2_0 `069621…` | ≈7.47 | ≈2316 | 88% | 54% | not completed | accuracy leader |

The values marked `≈` summarize multiple internal repetitions and are for orientation; use
the exact means, standard deviations and task intervals in the campaign summary. The tests are
small promotion gates, not estimates of the hidden judging-panel score.

Those rows no longer choose the submission. They remain useful for product latency and for a
future versioned AVX2 audit image. The primary verdict below is regenerated from the exact
SIMD-disabled profiler reference binary and the fixed 15 tok/s cap.

### Negative results that stopped branches

- Tying the Q4_0 output head saved about 175 MB of file bytes with no ARC-Easy loss (72% in
  both controls), so it stays.
- Q3_K_M plus a Q6_K embedding/head fell to 66% ARC-Easy; protecting the head did not recover
  the small-body quant. The IQ4_XS mixed candidate was slower and larger than uniform IQ4_XS.
- Removing one middle layer improved decode only modestly and lost two ARC-Easy points. It is
  competitive only under an implausibly low performance denominator.
- The 0.8B control was much faster (about 26.4 tok/s at 828 MiB RSS), but prior maths-quality
  gates make it an unsafe tutor. Smaller is not automatically better when accuracy is half the
  competition score.
- Vocabulary pruning was not applied to Qwen's GPT-2 BPE graph; doing so with the existing
  SentencePiece-only tool would silently corrupt tokenization. BitCPM's previously reviewed
  English-vocabulary prune remains the only safe vocabulary optimization in the finalist set.
