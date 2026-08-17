# BitCPM4-8B TQ2_0 — S_eff / S_perf optimization plan (2026-08-17, overnight)

> STATUS 2026-08-17 04:30: executed. Outcome in `REPORT.md`; the audit-binary finding (stock b10175, no AVX) reordered the priorities: GGUF bytes are what is scored.

## The scoring physics (from the adtc-profiler 0.1.0 source, read in full)

- `throughput` = stock **`llama-bench -m <gguf> -p 512 -n 128 -ngl 0 --output json`** — whatever
  `llama-bench` is first on `PATH`, no other flags. `n_threads` = llama-bench default
  (`hw.perflevel0.physicalcpu` = **4** on M1; physical cores on Linux). tg row = 128 single-token
  decodes from an empty context (n_ctx=128, KV negligible); pp row = 512 random tokens (n_ctx=512,
  n_ubatch=512). 5 reps each + warmup. Model kept loaded across both tests.
- `memory.peak_rss_mb` = **sum of RSS of the profiler process + all descendants**, sampled every
  100 ms for the whole llama-bench run (psutil `memory_info().rss`). RSS counts **mapped resident
  pages, file-backed included**; unmapped page cache does not count.
- `S_perf = min(TPS/15, 1)·100` (profiler README) — the dashboard uses the site's relative
  formula (TPS_max = fastest submission). Either way: TPS ≥ 15 is the floor, more is never worse.
- `S_eff = (7 GB − peak_rss_GB)/7 · 100`. Every −100 MB = +1.43 S_eff = +0.29 S_total.
- Audit (Gate 2) re-runs the same profiler on a CPU-only Linux VM (`docker --memory=7.5g`);
  tolerance ±15 % RSS / ±25 % TPS → flag, >50 % → **fail**. On Linux llama.cpp mmaps with
  `MAP_POPULATE` → RSS ≈ whole file + buffers regardless of what is touched.

## Baseline (this machine: Apple M1, 4P+4E, 8 GB, 16 KiB pages, macOS 27.0, Homebrew llama.cpp b10360)

| run | pp512 | tg128 | peak RSS | note |
|---|---|---|---|---|
| profiler run-14 (2026-08-16) | 27.5 | 15.75 | 2224 MB | memory-pressured Mac |
| tonight, thrash | 27.1 | 14.4 ± 8.0 | 2132 MB | compressor held 3.7 GB; llama-bench at 30 % CPU |
| tonight, calm | 31.9 | **17.70 ± 0.54** | **2564 MB** | whole file resident (WILLNEED at load) + ~190 MB buffers |

File: 2372 MB = 1955 MB TQ2_0 blocks (32 layers × 61.1 MB) + 247 MB `output.weight` Q6_K
+ 169 MB `token_embd.weight` Q4_K + 1 MB norms. Per-token weight traffic ≈ 2204 MB
(embedding rows excluded).

## Levers, ordered by (score gain × audit safety)

### A. GGUF-only (survives a stock audit binary)
1. **TQ1_0 requant** of the 224 ternary tensors: 2.0625 → 1.6875 bpw, lossless (same ternary
   values, same f16 block scale) → −355 MB file/RSS. Cost: slower kernel. **Measure tg.**
2. `output.weight` Q6_K → Q5_K/Q4_K (−40/−78 MB, −2–4 % per-token traffic). Accuracy check.
3. `token_embd.weight` Q4_K → Q3_K/Q2_K (−40/−80 MB; only matters where the whole file is
   populated — Linux audit, calm Mac). Accuracy check (embedding quality matters).
4. Layer pruning (each layer 61 MB, +3 % TPS): candidate only if perplexity/arc cost is small.
5. Mixed TQ1_0/TQ2_0 per layer to sit exactly at the TPS floor.

### B. Engine (custom `llama-bench` first on PATH — participant-mode; audit reproducibility is
   the open question researched in parallel)
1. CPU-only native build (no Metal/BLAS init, `-mcpu=native`): baseline RSS/TPS delta.
2. Default thread count 8 (use E-cores) — llama-bench takes no `-t` from the profiler.
3. No load-time WILLNEED/populate → untouched embedding rows never resident.
4. **Residency window ("partial weight streaming")**: keep a pinned set resident, stream the
   rest through a sliding W-layer window from the page cache: prefetch thread touches layer
   N+1..N+W, evict layer N−1 (macOS: `mmap(MAP_FIXED)` remap — `madvise(DONTNEED)` is
   advisory-only on Darwin per pilot-v2 DISCOVERY; Linux: `madvise(DONTNEED)`). RSS drops by
   the streamed fraction; cost = soft-fault rate. **Measure soft-fault bandwidth first** — it
   decides how much can be streamed at ≥15 tok/s. Disk-fed streaming is out (pilot-v2: 2.3 tok/s
   at 1.5 GB/token, D≈3 GB/s → ≤200 MB/token affordable).
5. TQ2_0 NEON kernel: ~1 vector op per weight byte (unpack shifts/ands + dotprod) → ~10 GB/s
   per P-core → 4 cores ≈ 40 GB/s ≈ 18 tok/s ceiling — it is instruction-bound at about the
   memory-bandwidth line. LUT (bitnet.cpp TL1-style) or fewer-op unpack could raise it.

### C. SVD
- Compute singular spectra of the ternary FFN/attn matrices and rel-Frobenius error vs rank
  (ranks multiple of 256 as in the deleted 2026-08-16 plan). Ternary matrices are near
  full-rank with flat spectra: expect the answer to be quantitative "no" for FFN, maybe for
  the output head. Report with data.

## Order of work tonight
1. Facts: soft-fault bandwidth, memcpy/pread bandwidth, SSD cold read, thread sweep. (now)
2. A1–A3 requants + tg/RSS/ppl measurements. (parallel, subagent)
3. B1–B4 residency-window prototype in `opt/llama.cpp` (patch), RSS–TPS curve. (subagent)
4. C spectra. (subagent)
5. Adversarial review of each result; assemble the submission GGUF; run the real
   `adtc-profiler` (participant, with accuracy); RESULTS.md + docs.
