# G6/G7 — DUO perf matrix

Host: Apple M2 Pro, CPU-only (Metal off, Accelerate BLAS on), 6 threads, llama.cpp `7ba604f` + `bundle-poc`. Sequential mode (no overlap; see POC_REPORT known-limits). Answer prompts: easy = capital question, hard = linear equation, codraft/escalation = "Explain Newton's second law with an example." Peak RSS via `/usr/bin/time -l`. Reproduce with `bash scripts/bench_duo.sh`.

## Matrix

| row | tokens | expert share f | end-to-end tok/s | ingest ms (front/expert) | wall per answer | peak RSS |
|---|---|---|---|---|---|---|
| front alone (baseline) | tg128 | 0.00 | 441-495 | - | - | 272 MiB |
| expert alone (baseline) | tg128 | 1.00 | 26.6-29.5 | - | - | 5.31 GiB |
| router-easy | 8 | 0.00 | 46.8 (incl. 150 ms routing) | - | 0.17 s | 5.73 GiB |
| router-hard | 302 | 1.00 | 26.8 | - | 11.3 s | 5.74 GiB |
| router-escalated (carry) | 636 | mixed | 28.9 | - | 22.0 s | 5.72 GiB |
| codraft f=0.25 | 511 | 0.25 | **48.6** | 342 / 4615 | 10.5 s | 5.71 GiB |
| codraft f=0.45 | 346 | 0.45 | 36.1 | 478 / 3216 | 9.6 s | 5.32 GiB |
| codraft f=0.80 | 886 | 0.80 | 29.6 | 623 / 2505 | 29.9 s | 5.71 GiB |

All rows well under the 6.5 GB G7 budget. The duo process (BOTH models + BOTH contexts + double-mmapped bundle) peaks only ~0.4 GiB above the expert-ALONE baseline: the OS page cache shares the physical pages of the single bundle file across both mappings, and the 135M front adds ~100 MB weights + small KV. This is the two-mmap-one-file claim confirmed empirically.

## Predicted vs measured (sequential model)

`T ~= N * (f/r_e + (1-f)/r_f) + t_ingest_front + t_ingest_expert`, with r_f ~= 400 tok/s and r_e ~= 30 tok/s measured in-duo:

| row | predicted | measured | error |
|---|---|---|---|
| codraft f=0.25 | 10.2 s (48.7 tok/s) | 10.5 s (48.6 tok/s) | +3% |
| codraft f=0.45 | 9.4 s | 9.6 s | +2% |
| codraft f=0.80 | 27.2 s | 29.9 s | +10% |
| router-hard | ~11 s | 11.3 s | +3% |

The model tracks measurements closely; the f=0.80 gap is sampler + logprob overhead on the 248k-vocab expert at high expert share. With overlap (deferred T16), the `t_ingest_expert` term would partially hide under front decode; on this host that term is only 3-4.6 s of which at most the front-decode time (~1 s) could be hidden - the quantitative reason overlap was deferred.

## Reading the tradeoff

Expert share f is the quality/speed knob (set via `--seg-min/-max` and `--seg-min-expert/-max-expert`): f=0.25 runs 1.8x faster than the expert alone, f=0.45 1.4x, f=0.80 1.1x. Routing picks f=0 (front) or f=1 (expert) per question at 87.5% accuracy (tau=0, see POC_REPORT G3), and the confidence monitor turns f=0 answers into mixed ones only when the front is actually struggling.
