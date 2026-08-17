# Residency-window weight streaming for llama.cpp (muta patch, 2026-08-17)

Patch lives in `muta-iq/opt/llama.cpp` (llama.cpp **b10360**, shallow clone; every change is
marked `[muta]`; new files `src/llama-residency-lite.{h,cpp}`). Build:

```
~/miniforge3/envs/ai/bin/cmake -S opt/llama.cpp -B opt/llama.cpp/build-cpu -DCMAKE_BUILD_TYPE=Release \
  -DGGML_METAL=OFF -DGGML_BLAS=OFF -DLLAMA_CURL=OFF -DGGML_NATIVE=ON -DLLAMA_BUILD_TESTS=OFF \
  -DLLAMA_BUILD_SERVER=OFF -DLLAMA_OPENSSL=OFF
cmake --build opt/llama.cpp/build-cpu -j 8 --target llama-bench llama-completion llama-perplexity llama-quantize
```

## What it does

`llama-bench` (and every other tool) keeps only a **sliding window of layers mapped+resident**;
the rest of the mmap'd file lives in the OS page cache, which the process's RSS does not count.
Nothing is copied: weights are read in place from the `MAP_SHARED PROT_READ` mapping exactly as
stock llama.cpp does — the patch only controls *which pages of that mapping are currently mapped
into the process*.

Mechanism (env-configured because the profiler passes llama-bench no flags):

| piece | how |
|---|---|
| units | per-layer page-aligned byte ranges from `tensors_by_name` (`blk.N.*` → unit N; `output.weight` → HEAD; norms/rope → MISC, always resident; `token_embd` excluded — rows fault on demand) |
| load | `init_mappings(prefetch=false)` when streaming: no `WILLNEED`/`MAP_POPULATE`, so untouched bytes never become resident |
| gate | `cb_eval` scheduler callback: the first graph node whose src is a weight of a *new* unit is a gate; at its POST all earlier units are complete (ASK runs ahead of compute, POST does not) |
| evict | Darwin: `mmap(addr,len,PROT_READ,MAP_SHARED\|MAP_FIXED,fd,off)` remap of the unit's ranges (atomic PTE replacement, same bytes → concurrent readers are safe). Linux: `munlock`+`madvise(DONTNEED)`. `madvise(DONTNEED)` is advisory-only on Darwin (measured) |
| prefetch | optional helper threads populate units `u+1..u+W` (`mlock` or `WILLNEED`+touch). **Measured: never worth it** — the compute threads faulting inline are the fastest populate path; default config is `MUTA_STREAM_PREFETCH=0 MUTA_STREAM_W=0` (helper only evicts) |
| helper priority | user-initiated QoS by default (`MUTA_STREAM_QOS=2`); a background-QoS helper starves for tens of ms and RSS balloons by the layers computed meanwhile (spikes to 1–2 GB) — plus inline back-pressure at the gate when >`MUTA_STREAM_MAXLAG` evictions are pending |
| cold start | `MUTA_STREAM_WARM=1` (default): `pread` the whole file into a scratch buffer once (page cache warm, RSS +8 MB) — cold soft-faults through compute threads run at 0.3 GB/s and `WILLNEED` would populate RSS |
| HEAD | its gate node is the logits matmul itself → evicted at its own POST |
| repack | `MUTA_NO_REPACK=1` keeps Q4_K/Q5_K/Q6_K/Q8_0 heads in the mmap (b10360 on ARM otherwise copies `output.weight` Q6_K into a 235 MiB anonymous `CPU_REPACK` buffer — double-charged RSS with a stock binary) |
| buffers | `MUTA_UBATCH=n` caps `n_ubatch` (llama-bench forces 512 → ~150 MB compute buffer during pp) |

Knobs: `MUTA_STREAM=1`, `MUTA_STREAM_PREFETCH=0|1`, `MUTA_STREAM_W`, `MUTA_STREAM_HELPERS`,
`MUTA_STREAM_MODE=mlock|touch`, `MUTA_STREAM_PIN=head,L0-L11`, `MUTA_STREAM_PIN_MB=<budget>`,
`MUTA_STREAM_QOS=0|1|2`, `MUTA_STREAM_MAXLAG`, `MUTA_STREAM_WARM`, `MUTA_STREAM_STATS=1`,
`MUTA_STREAM_TRACE=1`, `MUTA_MMAP_LAZY=1`, `MUTA_NO_REPACK=1`, `MUTA_UBATCH=n`.
Patch: `opt/patches/0001-muta-residency-window-b10360.patch`; rebuild with `opt/build_engine.sh`. Compile-time default via
`-DMUTA_STREAM_DEFAULT=1`.

Correctness: greedy output is byte-identical with streaming on/off (checked with
`llama-completion --temp 0`), as it must be — the bytes never change, only their residency.
Adversarial review 2026-08-17 (`opt/results/review_engine.md`): PASS-with-notes — byte-identical
output in every configuration incl. multi-ubatch prompts, MAP_FIXED remap is atomic
(`VM_FLAGS_OVERWRITE`) so a mistimed eviction can only cost soft-faults; the medium findings
(defaults were the worst config, `--mlock` conflict, evict failures uncounted, no host-buffer
guard, nextn layers, dup-after-mmap) were fixed the same night; known limitation: gate state is
per model, so streaming assumes one compute stream per model (llama-bench, llama-completion, a
single-slot server — not a parallel server or an MTP sibling context).

## Measured primitives (this M1, page-cache-hot 2.26 GB file; `opt/results/memprobe*_m1.txt`)

| primitive | cost | note |
|---|---|---|
| warm mmap read, 4 thr | 54 GB/s | memory ceiling |
| soft-fault + read after remap, 4 thr | 32.7 GB/s | what compute threads see when they fault inline |
| MAP_FIXED remap evict | 0.06 ms / 64 MB (2.4 ms if mlocked) | RSS drops immediately |
| mlock populate | 1.8–2.5 ms / 64 MB, then full-speed reads | pathological (5–15 ms) when compute faults the same file concurrently |
| WILLNEED (+touch) | 3 ms (+3 ms) / 64 MB | WILLNEED alone → half-speed reads |
| cold SSD | 1.35 GB/s | single or 4 parallel streams |

Compute consumes a 61 MB layer every ~1.75 ms (35 GB/s) at 18 tok/s, so no helper configuration
can stay ahead: the compute threads end up faulting inline (≈32–40 GB/s effective) — that is the
physical ceiling of full streaming on this machine (~10.5 tok/s), and helpers only add
contention (mlock: 4.5 tok/s). Measured curve (`opt/results/engine_sweep.tsv`,
`engine_profile.tsv`): t_token ≈ 48 ms + ~25 ms per streamed GB; profiler-style runs on the
pruned model: stream-all **10.5 tok/s @ 279 MB peak**, pin 1500 MB **15.35 tok/s @ 1636 MB**,
no streaming 18.7 @ 2129 MB.

## What this is and is not

- It is a real bounded-RSS engine: on a machine with less free RAM the same process still runs,
  degrading to disk speed (1.35 GB/s here → ~0.6 tok/s at full streaming) instead of failing.
- It is **not** something the ADTC audit will measure: Gate 2 runs the profiler's own stock
  `llama-bench` (b10175, no AVX) with `MAP_POPULATE`, so RSS there ≈ file size + buffers
  regardless of this patch. See `opt/docs/PLAN.md` and RESULTS.md for how the two number sets
  are kept separate.
