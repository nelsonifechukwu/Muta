# BitCPM4-8B (TQ2_0) — S_eff / S_perf optimization report, 2026-08-17

> "Optimization is not 'make the number go up.' It's picking the least-bad tradeoff among
> things that fight each other." — Arjun Virk

Machine for every number below unless stated: Apple M1 (4P+4E), 8 GB, 16 KiB pages, macOS 27.0,
CPU-only llama.cpp (Homebrew b10360 = the profiler's stock path; `opt/llama.cpp/build-cpu`
= our patched b10360). All heavy runs serialized through `opt/scripts/with_lock.py`.

## 0. What is actually scored (read the profiler, not the brochure)

- `throughput` = stock `llama-bench -m <gguf> -p 512 -n 128 -ngl 0` (no other flags; 4 threads
  by default on M1 = `hw.perflevel0.physicalcpu`).
- `memory.peak_rss_mb` = summed RSS (profiler + `llama-bench`) at 10 Hz. Mapped file pages
  count; unmapped page cache does not.
- **Gate-2 audit** = the profiler's Docker image: llama.cpp **b10175 built with
  AVX/AVX2/FMA/F16C OFF** (SSE4.2 only) on a 4-vCPU / 8 GB x86 VM. Consequences: (i) TQ1_0,
  TQ2_0 and every k-quant run their *generic C* kernels there; (ii) Linux `MAP_POPULATE`
  makes RSS ≈ whole file + buffers; (iii) no way to ship an engine or flags — **only the GGUF
  bytes reach the scored run.** Tolerance participant→audit: ±15 % RSS / ±25 % TPS (flag), >50 %
  (fail).
- S_perf: profiler README `min(TPS/15,1)·100`; the ADTF site says `100·TPS/TPS_max` (fastest
  submission). S_eff = `(7 GB − peak RSS)/7 GB · 100` — every −100 MB = +1.43.

## 1. Baseline

| run | pp512 | tg128 | peak RSS | note |
|---|---|---|---|---|
| Homebrew b10360, calm machine | 31.9 | 17.7 ± 0.5 | **2564 MB** | whole 2372 MB file populated (WILLNEED) + 235 MiB `CPU_REPACK` copy of `output.weight` + buffers |
| profiler run-14 (2026-08-16, pressured Mac) | 27.5 | 15.75 | 2224 MB | pages being evicted under memory pressure |
| our CPU-only b10360, tg only, quiet | — | 18.1–21.0 | 2276–2288 MB | no Metal/BLAS init |

File anatomy: 224 TQ2_0 tensors 1955 MB (61.1 MB/layer) + `output.weight` Q6_K 247 MB +
`token_embd.weight` Q4_K 169 MB (only touched rows resident on macOS; fully populated on
Linux) + norms 1 MB. Per-token weight traffic ≈ 2204 MB → at 54 GB/s memory ceiling the
kernel-independent bound is ~24 tok/s; the NEON TQ2_0 dot (~1 vector op per weight byte)
lands at 18–21.

## 2. Partial weight streaming — the numbers

**Question 1 as asked:** "if I/O is max 7 GB/s (find actual), how much of the model can be
weight-streamed and still reach 20 tok/s?"

*Actual I/O on this machine:* cold SSD sequential read **1.35 GB/s** (single stream and 4
parallel streams alike; `dd bs=8m` on an uncached file); page-cache-hot `pread` 7.0 GB/s (memcpy
bound); mmap soft-fault + read 32.7 GB/s (4 threads); warm mapped read 54 GB/s.

*Disk-fed streaming (bytes come from the SSD every token):* per-token compute of the resident
part is ~48 ms at best (21 tok/s), so 20 tok/s leaves **no** I/O budget at all on this
machine; at 15 tok/s (66.7 ms) the overlap budget is 18.7 ms → 18.7 ms × 1.35 GB/s =
**~25 MB per token (1 % of the model)** — or ~130 MB (6 %) at a hypothetical 7 GB/s.
pilot-v2 measured the same physics last week (Qwen3.5-4B, 1.5 GB streamed/token at
D≈3 GB/s → 2.3 tok/s). Disk streaming cannot buy a meaningful RSS reduction at ≥15 tok/s.

*Page-cache-fed streaming (residency window; the engine in `opt/llama.cpp`, see
`STREAMING_ENGINE.md`):* the process keeps only a sliding window of layers mapped; the rest
stays in the OS page cache and is soft-faulted back each token. Measured with the same
tg-style llama-bench (`-p 0 -n 64 -r 2 -t 4`), `opt/results/engine_sweep.tsv`:

| config | tg tok/s | peak RSS | steady RSS |
|---|---|---|---|
| no streaming (our CPU-only b10360) | 20.96 | 2288 MB | 2288 |
| stream all, no prefetch, W=0, no repack | **10.49** | **385 MB** | 313 |
| stream all, 2 helper prefetch threads, W=2 | 9.97 | 444 | 357 |
| stream all, mlock prefetch, W=6 | 4.48 | 626 | 358 |
| pin 600 MB (head + 6 layers), stream rest | 12.53 | 993 | 886 |
| pin 1200 MB (head + 16 layers) | 14.85 | 1522 | 1473 |
| pin 1500 MB, helpers W=6 | 17.12 | 2146 | 2145 |

The curve is linear: **t_token ≈ 48 ms + ~25 ms per streamed GB** — the cost of soft-faulting
16 KiB pages back in (≈32–40 GB/s effective vs 54 GB/s mapped). Helper prefetch threads
(E-cores; mlock or WILLNEED+touch) never keep up with 4 P-cores consuming 61 MB every
1.75 ms and only add lock contention (mlock is pathological: 4.5 tok/s); the compute threads
faulting inline *are* the fastest populate path on Darwin. So:

- **RSS floor ≈ 385 MB (tg) at 10.5 tok/s** — 6× less RAM for 2× less speed.
- **15 tok/s ⇔ ~1.5 GB peak RSS** (pin ≈ 1.2 GB), **17 tok/s ⇔ ~2.1 GB**.
- Profiler-style runs (pp512 + tg128, pruned model, `MUTA_UBATCH=128`, helper at
  user-initiated QoS + back-pressure): stream-all **10.47 tok/s @ 279 MB** peak, pin 1000/1300 MB
  13.0/14.0 tok/s @ 1136/1408 MB, pin 1500 MB **15.35 tok/s @ 1636 MB**, no streaming 18.7 @
  2129 MB. The real `adtc-profiler` with this engine on PATH: 10.49 tok/s @ 354 MB and 15.42 @
  1676 MB (`opt/results/submission_engine_*.json`; profiler process included in RSS).

None of this reaches the audit (stock binary, `MAP_POPULATE`), but it is the deployment
runtime's real footprint and the answer to the question.

## 3. mmap — how to use it for the highest score

The RSS the profiler sees is *mapped resident pages*. Three regimes:

1. **Stock binary, Linux (= the audit):** `llama_mmap` uses `MAP_POPULATE` → every byte of the
   file is resident from load; RSS ≈ **file size + KV + compute buffers (+ profiler ~50 MB)**.
   Nothing about *how* mmap is used can be changed from the GGUF; only *how many bytes* it maps.
   So "using mmap efficiently" for the scored run means **making the file smaller** and not
   paying for repack copies: vocab pruning (−164 MB), head/embedding types (§5), TQ1_0 vs TQ2_0
   (§5).
2. **Stock binary, macOS (= what a participant self-reports with Homebrew llama.cpp):**
   `posix_madvise(WILLNEED)` on Darwin synchronously populates the whole mapping (measured: RSS
   1 → 2265 MB in 118 ms), and on ARM the CPU backend additionally *copies* Q4_K/Q5_K/Q6_K/Q8_0
   heads into an anonymous `CPU_REPACK` buffer (235 MiB here) → the head is charged twice. RSS
   is then also hostage to memory pressure (2126–2602 MB observed for the same file tonight).
   GGUF-side mitigation for the Mac number: a head type that ARM does not repack (Q5_0, IQ4_XS,
   Q3_K) or a row count that defeats the 8-row repack condition (`ne[1] % 8 != 0`) — the latter
   costs tg speed (measured −8 % with 44397 rows), so we pad the pruned vocab to a multiple of
   64 instead and keep the repack.
3. **Our engine (`opt/llama.cpp`):** `MUTA_MMAP_LAZY=1` skips the load-time populate (untouched
   embedding rows never become resident: −160 MB on macOS at zero TPS cost), `MUTA_NO_REPACK=1`
   avoids the double charge, `MUTA_UBATCH=128` shrinks the pp compute buffer, and
   `MUTA_STREAM=1` turns the mapping into a residency window (§2). Darwin specifics that
   decide the implementation: `madvise(DONTNEED)` is a no-op for file mappings — evict with a
   `MAP_FIXED` remap of the same range (atomic, 0.06 ms/64 MB); `mlock` is the fastest
   populate in isolation but serializes against concurrent soft faults; inline faulting by the
   4 compute threads is the fastest populate in practice; cold sequential mmap faults run at
   0.4–0.9 GB/s (a cold start must warm the page cache first — the engine `pread`s the file once
   through an 8 MB scratch buffer, because `WILLNEED` would populate RSS).

## 4. SVD — quantitative no

`opt/results/svd/svd_report.md` (singular spectra of 25 ternary matrices, the head and the
embedding, Marchenko–Pastur baselines, ternary-factor reconstruction test):

- Ternary FFN matrices are numerically full-rank with spectra within a few % of an i.i.d.
  random matrix (energy at rank 2048: 0.67–0.78 vs 0.71 random). No byte saving exists until
  rank < 3276 (TQ2_0 factors), where the FP32-optimal relative Frobenius error is already
  0.23–0.31; at the F16-factor break-even (rank 422) it is 0.81–0.89.
- Attention: same picture (rank-2048 error 0.19–0.26 at zero saving); only 12 % of per-token
  bytes anyway.
- Output head (Q6_K, 10 % of bytes/token): F16 factors break even at rank 1591 with error 0.59;
  a real saving (rank 1024) costs 0.70. A lower k-quant of the head is the cheaper route to the
  same MiB. Token embedding: irrelevant to tok/s (get_rows) and equally full-rank.
- The 2026-08-16 plan's specific proposal (rank-2048 TQ2_0 factor pairs on `ffn_down`, 62 % of
  the bytes): BitNet-style ternarized factors reconstruct with **0.80** relative error;
  llama.cpp's own `quantize_row_tq2_0` on the real-valued factors gives error **> 1** (worse
  than an all-zero matrix). The trained ternary weights are stored *exactly* by TQ2_0; every
  rank that saves bytes lands at 25–90 % error. **Dropped.**

## 5. GGUF-level levers (the ones the audit will actually see)

### 5.1 English-scoped vocabulary pruning — **adopted**

39.5 % of the MiniCPM vocabulary is CJK-script pieces (28,932 + 100 fullwidth/kana), never
produced when tokenizing English/math/code. `opt/scripts/prune_vocab.py` drops them, renumbers
ids, rewrites the tokenizer arrays and `*_token_id` keys, pads the count to a multiple of 64
(44,416 tokens — keeps ARM's 8-row `q6_K` repack path; the unpadded 44,397 lost it and 8 % tg),
and slices `token_embd.weight` (Q4_K) / `output.weight` (Q6_K) rows at the raw block level.
`opt/scripts/verify_prune.py`: kept rows byte-identical, special ids remapped by string,
**tokenization identical on 20,464 tokens** of English/math/code/diacritics, zero dropped-piece
uses. Effects:

| | base | pruned (envocab64) |
|---|---|---|
| file | 2372 MB | **2208 MB (−164)** |
| per-token weight bytes | 2204 MB | 2107 MB (−4.4 %) |
| params (profiler fraud check, "8B" ±15 %) | 8.185 B | 7.947 B ✓ |
| PPL, 12×512 English chunks | 10.558 ± 0.51 | **10.473 ± 0.50** (renormalisation: softmax mass no longer leaks into CJK rows — not a quality gain per se) |
| Homebrew stock llama-bench (profiler-identical) | pp 36.6 / **tg 19.12** / peak **2567 MB** | pp 34.3 / **tg 19.61** / peak **2465 MB** |

On the audit's Linux `MAP_POPULATE` the whole −164 MB shows up in RSS (+2.3 S_eff); on the
Mac only −102 MB did (the rest was never resident under memory pressure). Model semantics for
English input are unchanged by construction (identical token ids → identical hidden states →
identical logits for kept tokens). Adversarial review (`opt/results/review_prune.md`, PASS
with notes): bit-identical logits over kept tokens on the real engine, 4/4 greedy generations
identical, 27 adversarial texts tokenize identically; llama-vocab derives nothing from ids;
caveats — fullwidth punctuation/`（）＝` and U+3000 now byte-fall-back (pasted CJK-locale math
tokenizes differently), non-greedy sampling differs at a fixed seed (renormalised softmax),
`general.languages` still says `["zh","en"]`.

### 5.2 TQ1_0 body — rejected with data

Lossless requant (same ternary values + f16 block scale; 8 s with `llama-quantize
--allow-requantize`), −340 MB (2018 MB file). But the base-3 unpack costs ~1.5× the integer
work per byte: on the audit-analogue generic-C path **2.88 vs 3.70 tok/s (−22 %)**, on NEON
13.1 vs 15.9–20.5 (−25–35 %). Under either S_perf formula the −22–35 % TPS costs more than the
+4.9 S_eff buys (`opt/results/audit_kernel_proxy.md`).

### 5.3 Output-head / embedding types — measured, left at Q6_K / Q4_K

Head Q6_K→Q5_0/Q5_K/Q4_K/IQ4_XS: PPL 10.563 / 10.573 / 10.572 / 10.599 vs 10.558 (all inside
±0.5 noise); embedding Q4_K→Q3_K/IQ4_XS is PPL-free (10.573/10.567 with the Q4_K head), Q2_K
+0.22 %; arc_easy(50) 0.84 for every variant tested (base, Q4_K head, Q5_0 head, Q3_K embd,
TQ1_0). On the pruned model that is at most −48 MB (Q5_0 head + Q3_K embedding; 0.7 S_eff,
0.14 S_total). Q5_0 is also *not* on ARM's repack list, so it would avoid the Mac-side double
charge. Not worth any risk on the 50 %-weight judged accuracy for 0.14 points; kept Q6_K/Q4_K
— documented as an available follow-up. (`opt/results/requant/requant_report.md`.)

### 5.4 What the audit box will measure (proxy, ±40 %)

Generic-C TQ2_0 is compute-bound at ~2.4 GB/s per core (M1 P-core, 1 thread 1.09 tok/s; 4
threads 3.7 tok/s; pp512 4.1 tok/s). An i5-10th-gen 4-vCPU VM without AVX2 lands around
**2–3.3 tok/s tg** for any 2.2 GB ternary/k-quant file — S_perf will be low for every 8B-class
submission unless the organisers restore AVX2 in the profiler image (then TQ2_0 is the fastest
quant there is: 141 GB/s vec_dot in the upstream PR). Not attempted: encoding the ternary
weights exactly as Q4_0 (`q ∈ {7,8,9}`, `d = s`) to use the SSSE3 kernel — 2.2× the bytes for
a speculative speed gain; noted as a contingency only.

### 5.5 Layer pruning — not attempted

61 MB and +3 % tg per layer, but S_acc is 50 % of the score and BitCPM-CANN-8B already sits at
95.7 % of the FP model; not a trade to make blind.

## 6. Recommendation and the submission

**Shipped in `muta-iq/`:** `metadata.json` → `model/bitcpm4-8b-tq2_0-envocab.gguf` (TQ2_0 body,
Q6_K head, Q4_K embedding, 44,416-token English-scoped vocab, 2208 MB, sha256
`069621f1…237d`), `download_model.sh` (fetch or derive + verify), and `submission.json` from the
real `adtc-profiler run --mode participant` with the **stock Homebrew llama-bench** (the path the
organisers document for participants — nothing exotic on PATH):

| official participant run (2026-08-17 04:2x, calm M1) | value |
|---|---|
| tokens_per_second_generation | **18.21** (base 19.12 same night; the 2026-08-16 official runs were 14.7–15.8 under memory pressure) |
| first_token_latency_ms | 15,110 (pp 33.9 tok/s) |
| peak_rss_mb / steady | **2462.3** / 2253 (base 2567 same night) |
| arc_easy (50) | 0.84 (unchanged) |
| params 7.947 B, `params_match` true; throttled false | |
| S_perf (min(TPS/15,1)) / S_eff | 100 / 65.6 |

Why this and not the streaming engine's 279 MB: the scored numbers come from the audit's stock
binary; a self-report of 279 MB would fail the ±15 %/50 % reproducibility check outright. The
engine numbers are recorded separately (`opt/results/submission_engine_*.json`, RESULTS.md) as
the deployment runtime's footprint and as report material.

**Priorities that remain (not tonight's scope):**
1. Upload the pruned GGUF to the team's HF repo and set `MODEL_URL` in `download_model.sh`
   (the fallback derives it locally from the upstream file — deterministic, sha256 pinned).
2. If the profiler image keeps AVX2 off at Gate 2, every 8B-class file scores ~2–3 tok/s there;
   the only in-rules levers are fewer bytes (done) and — speculative — Q4_0-encoded ternary for
   the SSSE3 kernel at 2.2× the RSS. Re-check the profiler repo before Aug 25.
3. The app should run on the streaming engine (`MUTA_STREAM=1 … MUTA_STREAM_PIN_MB≈1500` for
   ~15 tok/s at ~1.6 GB, or full streaming for the 8 GB shared-laptop classroom story).
