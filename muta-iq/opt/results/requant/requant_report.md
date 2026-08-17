# BitCPM4-8B head/embedding requantization sweep — report

Date: 2026-08-17. Machine: Apple M1 (8 GB), CPU-only native llama.cpp b10360
(`/Users/timii/Developer/Muta/muta-iq/opt/llama.cpp/build-cpu/bin`), 4 threads for every
perplexity/bench/accuracy run. All heavy commands were serialized behind the machine-wide
lock (`opt/scripts/with_lock.py`); other agents' *unlocked* processes (compiles, Python
sidecars) were sometimes active, so tok/s has ~±1.5 tok/s run-to-run noise (see notes).

Baseline: `/Users/timii/Developer/Muta/muta-iq/model/bitcpm4-8b-tq2_0.gguf` — 224 TQ2_0
body tensors (1864.5 MiB) + 64 F32 norms, `output.weight` Q6_K [4096×73448] 235.4 MiB,
`token_embd.weight` Q4_K 161.4 MiB; file 2,373,839,616 B (2263.9 MiB).

## Results

| variant | file MiB (bytes) | Δ vs base MiB | body / out / embd MiB | PPL (±) | ΔPPL % | tg128 tok/s (±) | rebench tok/s | arc_easy (50) |
|---|---|---|---|---|---|---|---|---|
| base `bitcpm4-8b-tq2_0 (competition file)` | 2263.9 (2373839616) | +0.0 | 1865.5 / 235.4 Q6_K / 161.4 Q4_K | 10.5581 (±0.509) | +0.00 | 17.41 (±0.12) | 17.58 (±0.15) | 0.84 (acc_norm, n=50) |
| V2 `bitcpm4-8b-tq2_0-oq5_k-eq4_k` | 2225.8 (2333883904) | -38.1 | 1865.5 / 197.2 Q5_K / 161.4 Q4_K | 10.5725 (±0.510) | +0.14 | 19.76 (±0.28) | — | — |
| V3 `bitcpm4-8b-tq2_0-oq4_k-eq4_k` | 2189.9 (2296278528) | -74.0 | 1865.5 / 161.4 Q4_K / 161.4 Q4_K | 10.5722 (±0.509) | +0.13 | 18.32 (±0.43) | — | 0.84 (acc_norm, n=50) |
| V4 `bitcpm4-8b-tq2_0-oiq4_xs-eq4_k` | 2180.9 (2286877184) | -82.9 | 1865.5 / 152.4 IQ4_XS / 161.4 Q4_K | 10.5985 (±0.510) | +0.38 | 18.94 (±0.82) | — | — |
| V5 `bitcpm4-8b-tq2_0-oq5_0-eq4_k` | 2225.8 (2333883904) | -38.1 | 1865.5 / 197.2 Q5_0 / 161.4 Q4_K | 10.5625 (±0.509) | +0.04 | 18.29 (±0.07) | — | 0.84 (acc_norm, n=50) |
| V6 `bitcpm4-8b-tq2_0-oq4_k-eq3_k` | 2151.8 (2256322816) | -112.1 | 1865.5 / 161.4 Q4_K / 123.3 Q3_K | 10.5726 (±0.509) | +0.14 | 18.94 (±0.18) | 18.13 (±0.14) | 0.84 (acc_norm, n=50) |
| V7 `bitcpm4-8b-tq2_0-oq4_k-eiq4_xs` | 2180.9 (2286877184) | -82.9 | 1865.5 / 161.4 Q4_K / 152.4 IQ4_XS | 10.5671 (±0.509) | +0.09 | 21.28 (±0.85) | — | — |
| V8 `bitcpm4-8b-tq1_0-oq4_k-eq4_k` | 1850.9 (1940811264) | -413.0 | 1526.5 / 161.4 Q4_K / 161.4 Q4_K | 10.5722 (±0.509) | +0.13 | 14.41 (±0.33) | 12.17 (±0.09) | 0.84 (acc_norm, n=50) |
| V9* `bitcpm4-8b-tq2_0-oq4_k-eq2_k` | 2122.7 (2225768448) | -141.2 | 1865.5 / 161.4 Q4_K / 94.1 Q2_K | 10.5814 (±0.510) | +0.22 | 17.98 (±0.50) | — | — |

Column notes: file/tensor sizes are MiB (2^20) from gguf-py (`tensor_bytes.py`); "tg128"
is `llama-bench -p 0 -n 128 -r 3 -t 4 -ngl 0` `avg_ts` (± stddev over reps) taken right
after each variant's PPL run; "rebench" is a second, back-to-back confirmation run
(V8 with `-r 5`) done at the end under identical conditions; PPL is
`llama-perplexity -c 512 -b 512 --chunks 12 -t 4` on the fixed 59 KB corpus
(`ppl_corpus.txt` = bytes 200000..260000 of `competition.txt`, page markers stripped;
6144 scored tokens); ΔPPL is relative to the baseline's 10.5581; arc_easy is the
competition profiler's own `adtc_profiler.accuracy.run_benchmark(task='arc_easy',
limit=50, seed=42)` (acc_norm, 50 samples — 1 sample = 0.02, so it cannot resolve
sub-percent PPL differences; earlier official runs also gave 0.84).
V9 (`*`) is an extra variant beyond the requested list (Q2_K embedding), added because the
embedding turned out to be nearly free to shrink.

## What was verified

* **Requantizing the TQ2_0 body to TQ2_0 is a byte-for-byte copy.** For V2, all 288
  `blk.*` tensors (224 TQ2_0 + 64 F32) were compared with gguf-py
  (`GGUFReader(...).tensors[i].data`, `verify_body.py`): 288/288 identical, 0 different
  (`verify_v2_body.txt`). llama-quantize's log confirms it never says "converting to"
  for `blk.*` when the target type equals the source type; only `output.weight` (and
  `token_embd.weight` when its type changes) is dequantized→requantized.
* **TQ2_0 → TQ1_0 body is value-lossless.** Six tensors spanning attn/ffn/all layer
  depths dequantized (gguf-py `dequantize`) from the base and from the TQ1_0 file are
  identical (`maxabsdiff=0`, `verify_tq1_0_body.txt`): same ternary values, same f16
  block scale, ~40% zeros. Consequence: V8's PPL is bit-identical to V3's
  (10.5722 ± 0.50925 for both) — the only thing TQ1_0 changes is bytes and speed.
* All requested type combinations were accepted; no "row size not a multiple of block
  size" rejections (both 4096 and 73448-row dims are fine for the 256-block K/IQ types
  because ne[0]=4096 is what matters).

## Observations

1. **Head (output.weight) precision is what moves PPL; the embedding barely does.**
   Q6_K→Q4_K head: +0.13% PPL for −74 MiB. Q6_K→Q5_0: +0.04% for −38 MiB.
   Q6_K→Q5_K: +0.14% for −38 MiB (Q5_0 measured better than Q5_K at identical size —
   requantizing an already-Q6_K tensor with a simple 32-block RTN quantizer appears to
   compound less error than the K-quant super-block search; treat as one data point).
   Q6_K→IQ4_XS: +0.38% for −83 MiB — the worst PPL-per-MiB of the head options.
2. **Embedding: Q4_K→Q3_K costs nothing measurable** (V6 10.5726 vs V3 10.5722, −38 MiB);
   Q4_K→IQ4_XS is also free (V7 10.5671, −9 MiB); Q4_K→Q2_K costs +0.09% more (V9
   10.5814, −67 MiB vs Q4_K). The embedding is a lookup table, so its quantization noise
   is input noise the ternary body tolerates.
3. **TQ1_0 body saves 339 MiB (−413 MiB total with the Q4_K head) but decodes at
   12.2–14.4 tok/s at 4 threads on the M1**, vs 17.4–17.6 for the baseline and 18.1–19.8
   for any TQ2_0/Q4-or-Q5-head variant. TQ1_0's base-3 unpacking is compute-bound on
   NEON, and prompt processing is slower too (PPL run 6:52 vs ~4:30). It fails the
   ≥15 tok/s floor on both measurements, so it is not usable at 4 threads on this box.
4. **Speed:** every Q4/Q5 head is faster than the Q6_K head (Q6_K's NEON dot is the
   slowest of these), so shrinking the head is a free ~+1 tok/s. The spread among
   identical-head variants (V3 18.3 / V6 18.9 / V7 21.3 / V9 18.0, and V6 18.9→18.1 on
   rebench) is measurement noise from unlocked background load, not the embedding type.
   RSS: llama.cpp mmaps the file, so peak RSS tracks file size 1:1 (+ ~150 MB fixed).
5. arc_easy (50 samples) is 0.84 for base, V3, V5, V6 and V8 — no variant moved it.
6. Repack behaviour was deliberately not analysed here (out of scope; measurements only).

## Recommendation

**(a) Minimum RSS at ≥15 tok/s: V6 `bitcpm4-8b-tq2_0-oq4_k-eq3_k.gguf`** — TQ2_0 body,
Q4_K head, Q3_K embedding: 2151.8 MiB (2,256,322,816 B), −112 MiB (−4.9%) vs the
competition file, PPL +0.14%, 18.1–18.9 tok/s (faster than the baseline's 17.4–17.6),
arc_easy 0.84. If every MiB counts, V9 (`...-oq4_k-eq2_k`, Q2_K embedding) trims another
29 MiB (2122.7 MiB, −141 MiB total) for +0.22% PPL and 18.0 tok/s — a fair trade but a
measurably worse PPL, so V6 is the default pick. Do **not** ship the TQ1_0 body (V8):
−413 MiB but 12–14 tok/s at 4 threads.

**(b) Safest accuracy: V5 `bitcpm4-8b-tq2_0-oq5_0-eq4_k.gguf`** — TQ2_0 body, Q5_0
head, Q4_K embedding: 2225.8 MiB, −38 MiB, PPL +0.04% (within noise of the baseline),
18.3 tok/s, arc_easy 0.84. Given observation 2, an untested `Q5_0 head + Q3_K
embedding` (~2188 MiB, −76 MiB) would very likely keep the +0.04% PPL and is the obvious
next candidate if (b) needs to be smaller.

Files kept on disk (`/Users/timii/Developer/Muta/muta-iq/opt/models/`):
`bitcpm4-8b-tq2_0-oq5_0-eq4_k.gguf` (V5), `bitcpm4-8b-tq2_0-oq4_k-eq3_k.gguf` (V6),
`bitcpm4-8b-tq1_0-oq4_k-eq4_k.gguf` (V8), `bitcpm4-8b-tq2_0-oq4_k-eq2_k.gguf` (V9).
V2, V3, V4, V7 were deleted after measurement
(all metrics are in this directory; each regenerates deterministically in ~30 s with the
command below). `bitcpm4-8b-tq1_0.gguf` belongs to the concurrent job and was only read.

## Exact commands

Corpus (Python): bytes `[200000:260000]` of
`.../scratchpad/competition.txt`, lines matching `^\s*=+\s*PAGE\s+\d+\s*=+\s*$` removed →
`ppl_corpus.txt` (59,244 B).

Every command below was run as
`/Users/timii/Developer/Muta/muta-iq/opt/scripts/with_lock.py --tag <tag> -- <cmd>`
(full per-variant log in `commands.log`; `B=/Users/timii/Developer/Muta/muta-iq/opt/llama.cpp/build-cpu/bin`,
`M=/Users/timii/Developer/Muta/muta-iq/opt/models`, `R=/Users/timii/Developer/Muta/muta-iq/opt/results/requant`):

```
# quantize (TQ2_0-body variants; source = competition file; V8 used $M/bitcpm4-8b-tq1_0.gguf + FTYPE TQ1_0)
$B/llama-quantize --allow-requantize --output-tensor-type <OUT> --token-embedding-type <EMB> \
    /Users/timii/Developer/Muta/muta-iq/model/bitcpm4-8b-tq2_0.gguf $M/bitcpm4-8b-tq2_0-o<out>-e<emb>.gguf TQ2_0 8
#   V2 Q5_K Q4_K | V3 Q4_K Q4_K | V4 IQ4_XS Q4_K | V5 Q5_0 Q4_K | V6 Q4_K Q3_K | V7 Q4_K IQ4_XS | V9 Q4_K Q2_K
$B/llama-quantize --allow-requantize --output-tensor-type Q4_K --token-embedding-type Q4_K \
    $M/bitcpm4-8b-tq1_0.gguf $M/bitcpm4-8b-tq1_0-oq4_k-eq4_k.gguf TQ1_0 8            # V8
# per-tensor-type bytes
/Users/timii/miniforge3/envs/ai/bin/python $R/tensor_bytes.py <gguf>
# perplexity
$B/llama-perplexity -m <gguf> -f $R/ppl_corpus.txt -c 512 -b 512 --chunks 12 -t 4
# decode speed
$B/llama-bench -m <gguf> -p 0 -n 128 -r 3 -t 4 -ngl 0 -o json        # rebench of V8 used -r 5
# accuracy (profiler's own check)
/Users/timii/miniforge3/envs/ai/bin/python -c "from pathlib import Path; from adtc_profiler import accuracy; \
    print(accuracy.run_benchmark(Path('<gguf>'), task='arc_easy', limit=50, seed=42))"
# lossless checks
/Users/timii/miniforge3/envs/ai/bin/python $R/verify_body.py <src.gguf> <out.gguf>   # raw-byte compare of blk.*
```
Raw logs: `quant_*.log`, `ppl_*.log`, `bench_*.json`, `rebench_*.json`, `acc_*.log`,
`tensors_*.txt`, `verify_*.txt`, driver scripts `run_variant.sh`, `run_acc.sh`, `batch*.sh`, `chain*.sh`.
