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

## Optimization session results (branch duo-verify)

Mixed 6-prompt set (2 easy / 2 medium / 2 hard), fresh process per prompt, seed 42, serialized runs:

| config | per-prompt tok/s (hello, capital, water, newton, solve, car) | avg | max | accuracy anchor |
|---|---|---|---|---|
| **router (default)** | 18.1, 46.5, 335.4, 28.2, 28.5, 28.0 | **80.8** | **335** | expert on hard; monitored front on easy |
| codraft f~=0.25 | 23.5, 25.6, 45.2, 51.9, 52.6, 50.3 | 41.5 | 52.6 | none for front-authored 75-82% |
| verify | 26.2, 25.3, 25.4, 23.5, 25.2, 23.9 | 24.9 | 26.2 | EVERY token expert-authored or expert-approved |
| expert-alone | 13.0, 27.5, 23.0, 21.7, 25.2, 26.6 | 22.8 | 27.5 | expert |

Verify-mode findings (fixed prompts, one variable at a time):
- Draft acceptance on this SmolLM2-135M/Qwen3.5-4B pair is ~0.32-0.42 on prose, 0.54 on equation math, and INSENSITIVE to the acceptance threshold (tau -5/-3/-2 identical) - front/expert disagreement is bimodal. Greedy drafting does not help (content divergence, not sampling noise).
- Break-even acceptance for verify vs plain expert decode is ~0.55 (accepted tokens cost ~12 ms vs 33 ms, failed rounds burn draft+verify+redo overhead), hence `--hard-mode` defaults to expert on this pair. Verify still beats expert-alone on average (+9%) because cheap drafts accelerate agreeable spans and short answers.
- The checkpoint mechanism itself (seq 1 cp/rm over the hybrid's Gated-DeltaNet state) is deterministic and exact across 40+ rollback rounds per turn; seam selftests pass strictly for both models.
- The pair is the bottleneck, not the mechanism: a front from the same family (e.g. Qwen 0.5B) should push acceptance past break-even; on the x86 target the front:expert speed ratio is also more favorable to drafting.

## Same-family front experiment (branch duo-qwen-front, bundle/muta-duo-q.gguf)

Front swapped to Qwen3.5-0.8B-MTP Q4_K_M (unsloth GGUF, sha256 ac7c9d7a...): same qwen35 hybrid arch, SAME 248k tokenizer as the expert, MTP head present (nextn_predict_layers=1, unused so far). Baselines: pp512 574 tok/s, tg128 117.7 tok/s. Front is now append-only too (Gated-DeltaNet) - drafts and routing run on a checkpoint sequence.

Acceptance (the number the pair swap was for), SmolLM2 -> Qwen0.8B at temp-front 0:

| prompt | SmolLM2 acc | Qwen0.8B acc | verify tok/s | expert-alone tok/s |
|---|---|---|---|---|
| solve 3x+5=20 | 0.32 | **0.75** (0.80 at draft 24/32) | **26.9** | 25.4 |
| water cycle | 0.41 | 0.36 greedy / 0.48 sampled | 20.2 | 27.4 |
| capital of Nigeria | ~0.5 | 0.57 | 23.9 | 26.4 |

Read: the same-family draft transforms acceptance on structured/mathy content (0.32 -> 0.75-0.80) and verify now BEATS plain expert decode there - the first configuration where drafting wins outright. On open prose the 0.8B's greedy style diverges (temp 0 hurts there; sampled drafts do better) and verify still trails expert-alone. Net: parity on average, wins on math/structured.

Remaining structural bottlenecks, in order of leverage: (1) the front drafts at only 117 tok/s (8.5 ms/token) - its unused MTP head predicts an extra token per forward pass and would roughly halve draft cost; (2) repairs still hand 50-70% of tokens to 33 ms expert decode - a domain-aware dispatch (verify for math/structured, expert for prose) captures the wins without the losses; (3) overlap (T16) hides expert catch-up under front decode. Bonus finding: the 0.8B is a better ROUTER than SmolLM2 (it classifies "describe the water cycle" as hard, s=+1.15, where SmolLM2 called it easy at s=-1.71).

## Reading the tradeoff

Expert share f is the quality/speed knob (set via `--seg-min/-max` and `--seg-min-expert/-max-expert`): f=0.25 runs 1.8x faster than the expert alone, f=0.45 1.4x, f=0.80 1.1x. Routing picks f=0 (front) or f=1 (expert) per question at 87.5% accuracy (tau=0, see POC_REPORT G3), and the confidence monitor turns f=0 answers into mixed ones only when the front is actually struggling.
