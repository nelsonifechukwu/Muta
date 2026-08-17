# Audit-kernel proxy: how fast will the ADTC audit box decode our ternary GGUFs?

**Date:** 2026-08-17 (02:19–03:51 local) · **Machine:** Apple M1 (4P+4E, 8 GB), macOS, shared/contended box
(all runs serialized through `scripts/with_lock.py`) · **Tree:** `opt/llama.cpp-generic` = copy of `opt/llama.cpp`
(llama.cpp `48d22e2` = **b10360**, shallow clone; the audit binary is b10175 — the generic TQ/K-quant kernels have
not changed between the two as far as we can tell, but the shallow clone cannot diff it) + the two-file patch
`results/audit_proxy/muta-audit-proxy.patch`.

## Why a proxy

The audit binary is llama.cpp b10175 built `GGML_NATIVE=OFF GGML_AVX=OFF GGML_AVX2=OFF GGML_FMA=OFF GGML_F16C=OFF`
(x86-64, SSE4.2 only). In `ggml/src/ggml-cpu/arch/x86/quants.c` the kernels we care about are guarded as follows
(checked in this tree):

| kernel | x86 fast paths | consequence for the audit build |
|---|---|---|
| `ggml_vec_dot_tq1_0_q8_K` | `#if defined(__AVX2__)` … `#else` generic | **generic C** |
| `ggml_vec_dot_tq2_0_q8_K` | `#if defined(__AVX2__)` … `#else` generic | **generic C** |
| `ggml_vec_dot_q4_K_q8_K`  | `__AVX2__` / `__AVX__` … `#else` generic | **generic C** (token_embd, get_rows only) |
| `ggml_vec_dot_q6_K_q8_K`  | `__AVX2__` / `__AVX__` … `#else` generic | **generic C** (output.weight, 235 MiB) |
| repack (`CPU_REPACK` buffer) | Q4_K/Q6_K repack needs AVX2 (x86) or NEON+dotprod (ARM) | **no repack** on the audit build |

We cannot run x86 here, so the proxy is an ARM build in which those four `vec_dot`s are forced to their
`*_generic` C bodies (`ggml/src/ggml-cpu/quants.c`) via `MUTA_FORCE_GENERIC=1`, and the `CPU_REPACK` extra buffer
type is switched off via `MUTA_NO_REPACK=1` (this llama-bench has no `--no-repack`; the env gate lives in
`ggml_backend_cpu_get_extra_buffer_types`, `ggml-cpu.cpp`). The rest of the graph (attention, norms, Q8_K
activation quantization, sampling) still runs NEON-optimized on the M1, so the proxy is slightly *optimistic* for
non-weight work; for tg that work is a small fraction of the token time.

Both compilers auto-vectorize the generic loops with 128-bit vectors in 32-bit lanes (checked by cross-compiling
`quants.c` with `clang -target x86_64-apple-macos12 -O3 -msse4.2 -S` and `clang -O3 -mcpu=native -S` and counting
mnemonics inside `ggml_vec_dot_tq2_0_q8_K_generic`: x86 → `pmovsxbd/pmovzxbd` + `pmaddwd/pmulld` + `paddd` (4 lanes);
ARM → `sshll/sshll2` + `mul/mla .4s` + `addv`), so "M1 generic" vs "x86 SSE4.2 generic" is a like-for-like
vector-width comparison; the remaining gap is core IPC, clock, and compiler (the audit box is presumably GCC).

## Build

```
rsync -a --exclude build-cpu --exclude 'build-cpu*.log' opt/llama.cpp/ opt/llama.cpp-generic/
# patch: results/audit_proxy/muta-audit-proxy.patch  (arch/arm/quants.c: MUTA_GENERIC_FALLBACK at the top of the
#        four vec_dot functions; ggml-cpu.cpp: skip CPU_REPACK buft when MUTA_NO_REPACK is set)
~/miniforge3/envs/ai/bin/cmake -S opt/llama.cpp-generic -B opt/llama.cpp-generic/build -DCMAKE_BUILD_TYPE=Release \
  -DGGML_METAL=OFF -DGGML_BLAS=OFF -DLLAMA_CURL=OFF -DGGML_NATIVE=ON -DLLAMA_BUILD_TESTS=OFF \
  -DLLAMA_BUILD_SERVER=OFF -DLLAMA_OPENSSL=OFF
~/miniforge3/envs/ai/bin/cmake --build opt/llama.cpp-generic/build -j 8 --target llama-bench
```
Configure log: `-mcpu=native`, dotprod present, **i8mm absent** (`-U__ARM_FEATURE_MATMUL_INT8`), so on this M1 the
native ARM path is NEON+dotprod, `nrc==1` everywhere, and Q4_K/Q6_K repack picks the `q6_K_8x4` layout for
`output.weight` only (`token_embd.weight` is a get_rows tensor and is never repacked; the load log says so).

## Commands (all through the machine lock; runner = `scripts/audit_kernel_proxy.sh`, collector = `scripts/audit_kernel_proxy_report.py`)

```
BENCH=opt/llama.cpp-generic/build/bin/llama-bench
TQ2=/Users/timii/Developer/Muta/muta-iq/model/bitcpm4-8b-tq2_0.gguf
TQ1=/Users/timii/Developer/Muta/muta-iq/opt/models/bitcpm4-8b-tq1_0.gguf
COMMON="-p 0 -n 128 -r 3 -t 4 -ngl 0 -v -o json"
# NEON, repack default            : python3 scripts/with_lock.py --tag X -- $BENCH -m $M $COMMON
# NEON, no repack                 : MUTA_NO_REPACK=1                      … same
# generic C, repack default       : MUTA_FORCE_GENERIC=1                  … same
# generic C, no repack (=audit)   : MUTA_FORCE_GENERIC=1 MUTA_NO_REPACK=1 … same
# per-core point                  : MUTA_FORCE_GENERIC=1 MUTA_NO_REPACK=1 $BENCH -m $TQ2 -p 0 -n 128 -r 1 -t 1 -ngl 0 -v -o json
# prompt processing on generic C  : MUTA_FORCE_GENERIC=1 MUTA_NO_REPACK=1 $BENCH -m $TQ2 -p 512 -n 0 -r 1 -t 4 -ngl 0 -v -o json
```
Raw outputs: `results/audit_proxy/<tag>.json` (llama-bench JSON incl. `samples_ts`) and `<tag>.err` (`-v` load log);
run log `results/audit_proxy/matrix.log`.

## Sizes

```
$ ls -l
-rw-r--r--  2373839616  Aug 15 14:28  /Users/timii/Developer/Muta/muta-iq/model/bitcpm4-8b-tq2_0.gguf   (2.21 GiB, 2.32 BPW; TQ2_0 body 1864.5 MiB + Q6_K output 235.4 MiB + Q4_K token_embd 161.4 MiB + F32 1.0 MiB)
-rw-r--r--  2018372352  Aug 17 02:11  /Users/timii/Developer/Muta/muta-iq/opt/models/bitcpm4-8b-tq1_0.gguf (1.88 GiB, 1.97 BPW; TQ1_0 body 1525.5 MiB + same output/embd)
```
Load-log buffer lines (`-v`):

| model | config | `CPU_Mapped model buffer size` | `CPU_REPACK model buffer size` |
|---|---|---|---|
| TQ2_0 | repack default | 2026.90 MiB | 235.35 MiB (`repack tensor output.weight with q6_K_8x4`) |
| TQ2_0 | `MUTA_NO_REPACK=1` | 2262.25 MiB | (line absent — no CPU_REPACK buffer) |
| TQ1_0 | repack default | 1687.90 MiB | 235.35 MiB (`… output.weight with q6_K_8x4`) |
| TQ1_0 | `MUTA_NO_REPACK=1` | 1923.25 MiB | (line absent) |

Weight bytes streamed per generated token (everything except `token_embd`, which is a row gather), from gguf-py
tensor sizes: **TQ2_0 = 2,202,920,704 B = 2.203 GB (2100.9 MiB)**, **TQ1_0 = 1,847,453,440 B = 1.847 GB (1761.9 MiB)**.
`implied GB/s = tok/s × those bytes`.

## Results (llama-bench, tg128 unless stated, `-r 3`, M1, 4 threads unless stated)

| model | kernel path | repack | threads | test | tok/s ± stddev | samples (tok/s) | implied GB/s (weights) |
|---|---|---|---|---|---|---|---|
| TQ2_0 | NEON+dotprod (native M1) | default (q6_K_8x4 on output) | 4 | tg128 | **15.92 ± 2.52** | 17.60, 17.13, 13.02 | 35.1 |
| TQ2_0 | NEON+dotprod (native M1) | off | 4 | tg128 | **20.45 ± 0.20** | 20.48, 20.24, 20.64 | 45.1 |
| TQ2_0 | generic C (`*_generic`) | default (q6_K_8x4 on output) | 4 | tg128 | **3.84 ± 0.13** | 3.69, 3.87, 3.96 | 8.45 |
| TQ2_0 | generic C (`*_generic`) | off  ← audit-build analogue | 4 | tg128 | **3.70 ± 0.21** | 3.48, 3.70, 3.91 | 8.15 |
| TQ1_0 | NEON+dotprod (native M1) | default | 4 | tg128 | **13.19 ± 0.31** | 13.55, 12.97, 13.05 | 24.4 |
| TQ1_0 | NEON+dotprod (native M1) | off | 4 | tg128 | **13.12 ± 1.25** | 14.57, 12.46, 12.34 | 24.2 |
| TQ1_0 | generic C | default | 4 | tg128 | **3.00 ± 0.03** | 3.02, 3.01, 2.96 | 5.54 |
| TQ1_0 | generic C | off  ← audit-build analogue | 4 | tg128 | **2.88 ± 0.07** | 2.92, 2.92, 2.80 | 5.33 |
| TQ2_0 | generic C | off | **1** | tg128 (`-r 1`) | **1.09** | 1.09 | **2.40 GB/s per core** |
| TQ2_0 | generic C | off | 4 | **pp512** (`-r 1`) | **4.13** | 4.13 | n/a |

Noise floor: the box was shared with other agents' jobs the whole time (free RAM ~70 MB during runs; the model
is mmapped so it competes for page cache); single samples swing ±15% (see the TQ2_0 NEON/repack third sample and
the TQ1_0 NEON/no-repack first sample). The generic-C rows — the ones that matter — are tight (sd 1–6%) and the
repack/no-repack pairs agree within 4%, which is expected: repack only ever touches `output.weight` (11% of the
bytes) and TQ types have no repack layout at all. Treat the NEON repack-vs-no-repack gap on TQ2_0 as noise, not
signal.

## Interpretation

**(a) TQ1_0 vs TQ2_0 on generic C.** `2.88 / 3.70 = 0.78` (no-repack) and `3.00 / 3.84 = 0.78` (repack):
**TQ1_0 decodes ~22% *slower* than TQ2_0 on the generic C path**, even though it streams 16% fewer bytes
(1.85 vs 2.20 GB/token). Per byte the generic TQ1_0 kernel costs ~1.5× TQ2_0 (5.3 vs 8.2 GB/s): the base-3
unpack (`q * pow3[l]`, `(q*3)>>8`, five trits per byte plus the `qh` tail) is more integer work per element than
TQ2_0's `(q >> 2l) & 3`, and both kernels are **compute-bound, not bandwidth-bound** — 8 GB/s on four cores is a
fraction of what the memory system delivers to the NEON path (45 GB/s). Same ordering on NEON (`13.1 / 20.5 =
0.64`). So on the audit machine TQ1_0 buys ~350 MB of file size and pays ~22% of decode speed; there is no
speed argument for TQ1_0 there.

**pp512 on generic C is ~4.1 tok/s at 4 threads — essentially the same as tg (3.7 tok/s).** The generic
`vec_dot` has no batching win (each prompt token costs the same per-weight integer work as a generated token),
so a 512-token prompt on the audit box will take of the order of **2–3 minutes** before the first generated
token. If the audit's llama-bench reports pp as well as tg, expect pp ≈ tg on these kernels.

**(b) Estimate for the audit box** (4-vCPU Intel i5 10th gen / Comet Lake, ~3.6 GHz all-core, generic C
auto-vectorized to SSE4.x 128-bit int ops, no repack). Anchors: M1 Firestorm @ ~3.2 GHz does **1.09 tok/s per
core = 2.40 GB/s of TQ2_0 weights per core** on generic C, and 3.70 tok/s on 4 threads (3.4× scaling; the
kernel is compute-bound so threads scale ~linearly until physical cores run out — memory bandwidth is not the
limiter at 8 GB/s). Scaling factors applied to the per-core number: clock ×1.125 (3.6/3.2); core IPC on this
kind of 128-bit widen-multiply-accumulate loop, Skylake-class vs Firestorm ×0.5–0.8 (Firestorm has ~2× the
SIMD-integer issue width and a much larger OoO window; `pmulld` is 2 uops/10-cycle latency on Skylake vs
single-cycle-throughput `mul.4s` on Firestorm; GCC-vs-clang codegen differences fold into the same band).
That gives **0.6–1.0 tok/s per physical core**, i.e.

| audit box assumption | TQ2_0 tg128 | TQ1_0 tg128 (×0.78) | pp512 |
|---|---|---|---|
| 4 vCPU = **4 physical cores** (×3.4 scaling) | **≈ 2.7 tok/s** (2.1–3.3) | **≈ 2.1 tok/s** (1.6–2.6) | ≈ 3 tok/s |
| 4 vCPU = **2 cores + HT** (×1.25 for SMT over 2 cores) | **≈ 2.0 tok/s** (1.5–2.5) | **≈ 1.6 tok/s** (1.2–2.0) | ≈ 2.2 tok/s |

**These are M1-generic-C proxy numbers with roughly ±40% uncertainty** (unknown compiler/flags beyond
"SSE4.2 only", unknown vCPU-to-core mapping, unknown VM overhead and turbo behaviour, and the proxy still runs
non-weight ops on NEON). The robust conclusions are the ratios, not the absolute values: on the audit build
both ternary formats are **~5.5× slower than the NEON path** and **compute-bound at ~2 GB/s per core**, TQ1_0
is ~0.78× TQ2_0, and prompt processing gains nothing over generation. If the audit target is a tok/s number,
the only levers that move it are fewer weight bytes *and* fewer integer ops per byte on the generic C path
(e.g. a smaller/pruned body — TQ1_0 does not help), or convincing the auditors to enable AVX2.

## Files

- `results/audit_kernel_proxy.md` — this report
- `results/audit_proxy/*.json`, `*.err`, `matrix.log`, `summary.json` — raw runs
- `results/audit_proxy/muta-audit-proxy.patch` — the two-file patch applied to `opt/llama.cpp-generic`
- `scripts/audit_kernel_proxy.sh` (runner), `scripts/audit_kernel_proxy_report.py` (table collector)
