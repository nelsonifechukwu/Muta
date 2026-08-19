# ADTC GGUF optimization campaign — 19 August 2026

## Outcome

This directory is the decision record for the seven-hour GGUF-only campaign. A 19 August
provenance audit retracted the repository's unsupported claim of a private 6 August organiser
clarification. The current official sources conflict, so this record deliberately preserves four
non-interchangeable evidence lanes:

1. `official-profiler/`: complete participant-mode runs emitted and schema-validated by the
   bundled ADTC profiler. Its `summary.*` is the primary fixed-15 decision surface and its peak
   RSS directly includes the profiler root and benchmark child.
2. `scalar15.jsonl` and root `summary.*`: b10175 profiler-reference no-AVX measurements,
   scored with `min(TPS/15, 1) × 100`. This matches the profiler's throughput path and is the
   broader promotion-screen lane: the incumbent uses
   llama-bench's default five internal repetitions;
   scalar challengers use one recorded internal repetition as a time-boxed promotion screen.
   `measurement_tier` and the full command make that precision difference visible.
3. `avx2.jsonl` and `avx2-website-relative-summary.*`: AVX2 deployment measurements scored
   with the challenge webpage's cohort-relative `100 × TPS/TPS_max`, retained at every tested
   pre-entry cohort floor. Because the submitted candidate joins the cohort, its effective
   denominator is `max(floor, candidate TPS)`. This is a labelled alternative, never blended
   with the primary ranking.
4. `avx2-score-of-record/`: a fresh five-model ISA-controlled rerun using the same capped-15
   score as the scalar lane. Every AVX2 candidate has five internal samples; complete CPU/build
   provenance and scalar-versus-AVX2 deltas are retained beside the raw JSONL.

The fresh capped-15 AVX2 rerun nominally selects **Qwen3-1.7B Q4_K_M tied** at 80.4484,
versus 80.2818 for Muta Tutor pure Q4_0, 80.1089 for IQ4_XS, 79.6307 for Q5_K_M and
72.5121 for BitCPM. The Q4_K_M lead is only 0.1666 points and its decode variance is much
higher, so this is a proxy winner rather than a submission promotion. BitCPM recovers from
0.8108 to 7.4876 tok/s (9.235×), proving the scalar kernel caused most of its collapse, but it
still does not win the capped score.

The AVX2/webpage alternative produced **four denominator-dependent finalists**:

- **BitCPM4-8B TQ2_0, vocabulary-pruned** (`069621…`) is the accuracy leader and the
  submission choice from a 60 tok/s pre-entry cohort floor upward.
- **Qwen3-1.7B Q3_K_M, tied head** (`455de7…`) wins at the 15 tok/s floor because it is
  itself faster than that floor, so its effective denominator becomes its own throughput.
- **Qwen3-1.7B Q4_K_S, tied head** (`bff602…`) wins at the 30 tok/s floor.
- **Qwen3-1.7B Q5_K_M, tied head** (`17ddf7…`) wins at the 45 tok/s floor, where its
  Easy accuracy gain narrowly repays the slower decode.

There is no honest single webpage-relative score until the cohort's `TPS_max` and judging-panel
`S_acc` are known. The alternative summary therefore reports the winner at six denominators
instead of averaging them. Both profiler lanes use the published fixed reference 15.

The direct profiler result keeps **Muta Tutor / Qwen3-1.7B pure Q4_0 tied** as the winner, but
reveals a close efficiency hedge:

| Full participant-mode report | TPS | Direct profiler peak RSS | ARC-Easy-50 | S_total @ capped 15 |
|---|---:|---:|---:|---:|
| **Muta Tutor Qwen3-1.7B pure Q4_0 tied** | **9.79** | **1116.31 MiB** | **72%** | **72.4653** |
| Qwen3.5-0.8B Q4_K_M | 9.74 | 694.73 MiB | 68% | 71.5416 |
| BitCPM4-8B TQ2_0 vocabulary-pruned | 0.81 | 2306.56 MiB | 88% | 59.1843 |
| Qwen3.5-4B IQ4_XS | 1.13 | 2627.34 MiB | 76% | 52.9293 |

The winner leads the 0.8B hedge by only 0.9237 composite points: its four-point ARC-Easy gain
repays 421.58 MiB of additional RSS while throughput is effectively tied. The historical 0.8B
maths/tutoring gates remain a product-quality warning, but are not mixed into this ARC-only score.
The promotion-screen summary still contains the broader Qwen quant ladder; it remains the basis
for rejecting Q4_K_M/Q5_K_M/IQ4_XS variants that were not all rerun through the expensive full
profiler path.

## What was actually measured — AVX2 alternative

All rows used one VM, one binary and one invocation shape; the raw JSONL retains each separate
benchmark invocation:

| Field | Value |
|---|---|
| Host | GCP `n2-custom-4-8192`, 2 physical cores / 4 SMT, 8 GB |
| Label | `x86_cloud_proxy_gcp_n2_custom_4_8192_2c4t` |
| llama.cpp | b10175, commit `60bccc3763395e01b039aa1ddeacc8cc0ea69f70` |
| llama-bench SHA-256 | `4abfa11a3f86b8c5e4d508cce10daf8f381c968585a3e5961fea3d5cbe312fd8` |
| Build policy | AVX2 baseline, `GGML_NATIVE=OFF`, AVX-512 disabled |
| Workload | `llama-bench -p 512 -n 128 -ngl 0`, default 2 threads |
| Accuracy | exact profiler Python/LM adapter, raw GGUF; each task and sample count retained |
| Efficiency | peak whole-process-tree RSS sampled around the same run |
| Thermal | unavailable; no GCP row is report-grade target-laptop evidence |

`avx2.jsonl` is append-only and contains every model/binary hash, command, internal
five-sample timing vector, RSS observation and stderr tail. The aggregator refuses to pool
different hosts, binaries, or artifacts with the same filename.

## Main evidence

The exact AVX2 values are machine-readable in `avx2-website-relative-summary.tsv`. The decisive observed pattern
was:

| Candidate | ARC-Easy n=50 | ARC-Challenge n=50 | SciQ n=50 | Interpretation |
|---|---:|---:|---:|---|
| current Qwen Q4_0 | 72% | 42% | 94% | immutable control |
| Qwen Q4_K_M tied | 72% | 48% | 96% | broad improvement over control |
| Qwen Q5_K_M tied | 76% | 42% | 94% | ARC-Easy bump did not generalize |
| BitCPM4-8B TQ2_0 | 88% | 54% | not completed in the time box | broad accuracy leader |

These are small diagnostic samples, not a claim about the hidden judging score. Wilson 95%
intervals are emitted per task. Historical GSM8K-40 chat-style evidence (not merged into the
raw-profiler score) also favours BitCPM, 77.5% versus 70% for the shipped Qwen.

## Technique verdicts

| Technique | Result |
|---|---|
| Uniform quant ladder | Q4_K_M is the balanced Qwen winner; Q5_K_M trades too much TPS for a narrow Easy gain. |
| Importance matrix | Used consistently for the Qwen ladder; the vendor calibration corpus is unpublished, so disjointness is not independently provable. |
| Tied output head | Keep. Tied and untied pure-Q4 controls both scored 72% ARC-Easy; tying saved about 175 MB of file bytes. |
| Mixed embedding/head precision | Reject. Q3_K_M+Q6_K fell to 66% ARC-Easy and IQ4_XS+Q6_K was slower and larger than uniform IQ4_XS. |
| One-layer pruning | Reject. Only about 3.7% faster than the control and lost two ARC-Easy points; it is not the winner at any retained cohort floor. |
| Smaller architecture | 0.8B is the speed hedge (about 26.4 tok/s and 828 MiB RSS), but prior maths-quality evidence is below the tutoring gate. |
| Vocabulary pruning | Not attempted on Qwen: the current tool cannot coherently rewrite GPT-2 BPE merges. BitCPM's previously verified byte-exact English-preserving prune remains valid. |
| Unstructured sparsity | Reject for a stock dense GGUF/runtime: zeros still occupy bytes and are multiplied. |
| Distillation / QAT / fine-tuning | Research-backed future work, not fabricated on an 8 GB CPU VM inside seven hours. Only finished checkpoints can enter a GGUF-only campaign. |
| Context metadata | No scored leverage: the profiler fixes p512/tg128. |
| Layout/alignment | Stock quantizer output retained; an unsupported custom layout is a load-failure risk. |
| Embedded template | Required for live judging and verified separately from raw telemetry; never credited to ARC/TPS. |

## Reproduction

1. Provision the BF16 source, importance matrix, b10360 quantizer, and b10175 benchmark
   binary at the exact hashes in `manifest.json`.
2. Run `bench/build_gguf_candidates.sh SOURCE IMATRIX LLAMA_QUANTIZE OUT_DIR`.
3. Run `bench.adtc_bakeoff` with the exact host label and append to a new JSONL.
4. Generate the fail-closed view:

   ```bash
   python -m bench.official_profiler_summary \
     --manifest official-profiler/manifest.json \
     --json official-profiler/summary.json \
     --tsv official-profiler/summary.tsv

   python -m bench.campaign_summary \
     --input scalar15.jsonl --accuracy-input avx2.jsonl \
     --performance-formula profiler_capped --tps-max 15 \
     --json summary.json --tsv summary.tsv

   python -m bench.campaign_summary \
     --input avx2.jsonl --performance-formula website_relative \
     --tps-max 15,30,45,60,100,150 \
     --json avx2-website-relative-summary.json \
     --tsv avx2-website-relative-summary.tsv
   ```

The GGUFs themselves remain untracked; immutable hashes are the identity surface. No model
is promoted from this cloud proxy without a final run on the physical target laptop.
