# R4 — What exactly runs on the ADTC audit box (llama.cpp b10175, no-AVX x86)

**Date:** 2026-08-17 · **Author:** research agent (team-muta) · **Scope:** verify, against the llama.cpp source at tag
`b10175` and the adtc-profiler repo, which kernels the Gate-2 audit binary executes for each GGUF quant type, and rank
the types by decode (tg) speed on that binary.

**Ground truth used:** sparse clone of `ggml-org/llama.cpp` at tag `b10175` = commit `60bccc3763395e01b039aa1ddeacc8cc0ea69f70`
(2026-07-28, "add rdna3.5, and 3 to mmq configs …"), the profiler `Dockerfile`/`README.md`/`throughput.py`/`accuracy.py`
(GitHub `main` = `ac2e137dca`, 2026-08-15), a clang cross-compile of the kernels for `x86_64 -msse4.2 -mbmi2`, and a
GCC 12.2 compile of the same kernels via the Compiler Explorer API (Debian bookworm ships GCC 12.2 — the compiler the
Dockerfile actually uses). All line numbers below are for `b10175`. Nothing here was *executed* on x86 (no x86 box, no
Rosetta, no Docker on this Mac) — the speed numbers are static-analysis estimates anchored to two measurements (§7).

---

## 0. Decisive answer (TL;DR)

1. **The audit binary is a single, statically linked CPU backend compiled with exactly `-msse4.2 -mbmi2` (plus `-O3 -DNDEBUG`,
   OpenMP, llamafile on, repack on). There is no runtime dispatch** — `GGML_CPU_ALL_VARIANTS` and `GGML_BACKEND_DL` default
   `OFF`, `BUILD_SHARED_LIBS=OFF` makes them impossible, and `ggml_cpu_has_avx2()` is a compile-time `#if defined(__AVX2__)`
   → `0`. Even on an AVX-512 host the binary uses SSE4.2/SSSE3 code paths only.
2. **Only two GGUF quant types have a hand-written x86 SIMD `vec_dot` that survives without AVX: `Q4_0` (SSSE3 path) and
   `Q1_0` (SSSE3 path, binary weights only).** `Q8_0` has no SSSE3 path — it runs its scalar tail loop, which GCC 12
   auto-vectorises poorly (shuffle-port bound). **Every other type — Q4_1, Q5_0/1, all K-quants, TQ1_0/TQ2_0, all IQ types,
   IQ4_NL/XS, MXFP4, NVFP4, Q2_0 — runs the generic C `*_generic` body** (or a scalar tail loop) compiled by GCC 12 with SSE4.2
   auto-vectorisation of varying quality.
3. **No repack** on the audit build (all x86 repack layouts require `ggml_cpu_has_avx2()`/`avx512()`; Q5_K/Q6_K/Q8_0 repack is
   NEON-only anyway). **No llamafile/tinyBLAS sgemm** for any type without AVX (`llamafile_sgemm` returns `false` for every
   `Atype` on a plain-SSE build, and it is never used for `n < 2`, i.e. never for tg). Prompt processing therefore costs the
   same per token as generation on the audit build (M1 proxy: pp512 4.1 vs tg128 3.7 tok/s).
4. **Ranking by tg speed per weight on the audit build (fixed model), highest first — estimated relative to Q4_0 = 1.00
   (compute-bound regime, GCC 12.2 codegen, Skylake-class port model; ±40 %):**

   | rank | type | kernel actually run | est. cycles/weight | rel. tg per weight | bytes/weight | rel. tg per **byte** of file |
   |---|---|---|---|---|---|---|
   | 1 | **Q4_0** | hand SSSE3 (`x86/quants.c:770-839`) | 0.25–0.30 | **1.00** | 0.5625 | **1.00** |
   | 1= | Q1_0 (binary only) | hand SSSE3 (`x86/quants.c:657-692`) | 0.25–0.30 | 1.0 | 0.1406 | 4.0 (n/a for ternary) |
   | 3 | Q8_0 | scalar tail loop, GCC auto-vec (p5-bound) | 0.45–0.8 | 0.35–0.6 | 1.0625 | 0.2–0.3 |
   | 4 | Q4_K | generic C, GCC auto-vec (2 passes) | 0.7–0.9 | 0.3–0.4 | 0.5625 | 0.3–0.4 |
   | 4= | **TQ2_0** | generic C, GCC auto-vec (per-32 reductions) | 0.7–1.0 | 0.3–0.4 | 0.2578 | 0.13–0.18 |
   | 6 | Q5_K | generic C | 0.9–1.1 | ~0.27 | 0.6875 | ~0.33 |
   | 7 | Q6_K | generic C (unpack pass is heavy) | 1.2–1.5 | ~0.2 | 0.8203 | ~0.3 |
   | 7= | Q3_K | generic C | 1.2–1.5 | ~0.2 | 0.4297 | ~0.15 |
   | 7= | TQ1_0 | generic C, half scalar (`imull`) | 1.2–1.6 | ~0.2 | 0.2109 | ~0.075 |
   | 10 | Q2_K | generic C, mostly scalar (`sarx/imull`) | 1.2–2 | 0.15–0.25 | 0.3281 | ~0.1 |
   | 10= | Q2_0 | generic C, **scalar** (no x86 impl at all) | ~1.2 | ~0.25 | 0.2813 | ~0.12 |
   | 12 | Q4_1 | generic C, GCC **scalar** | ~2 | ~0.15 | 0.625 | ~0.17 |
   | 13 | IQ4_NL / MXFP4 | scalar tail loop w/ table lookups | ~2.3 | ~0.13 | 0.5625 / 0.531 | ~0.13 |
   | 14 | **IQ4_XS** | generic C, scalar table lookups | ~2.5 | ~0.12 | 0.5313 | ~0.11 |
   | 15 | Q5_0 / Q5_1 | generic C, scalar (11.8 instr/weight) | ~4 | ~0.07 | 0.6875 | ~0.09 |
   | 16 | IQ2_*, IQ3_*, IQ1_M | generic C, scalar grid lookups | 3–7 | 0.05–0.1 | 0.26–0.44 | tiny |

   *"rel. tg per byte"* = tokens/s you get per byte of model file at equal RSS, i.e. how a Q4_0 model of N params compares with
   a TQ2_0 model of 2.18·N params: **at equal file size a Q4_0 model decodes ~5–7× faster than a TQ2_0 model on the audit
   build in the compute-bound regime, until the memory-bandwidth ceiling (≈ VM GB/s ÷ file GB, identical for both) caps it.**
   The robust conclusions are the tiers, not the decimals: *hand-SIMD (Q4_0) ≫ auto-vectorised generic (Q8_0, Q4_K, TQ2_0,
   Q5_K) > heavy generic (Q6_K, Q3_K, TQ1_0, Q2_K, Q2_0) ≫ scalar table-lookup (Q4_1, IQ4_XS, IQ4_NL, MXFP4, Q5_0, IQ2/IQ3)*.
5. **Practical consequences** (details §8): (i) if the model can be re-chosen, a Q4_0 GGUF (`--pure`, output tensor Q8_0 or Q4_0,
   **no** imatrix-induced Q4_1 layers) is the fastest thing the audit binary can run per byte; (ii) if BitCPM4-8B stays, TQ2_0
   is the right body type (TQ1_0 is ~0.8× per weight and Q2_0 is worse), but move `output.weight` from Q6_K to Q8_0 (or Q4_0):
   Q6_K's generic kernel is one of the slowest per weight and it is 235 MiB of the busiest tensor; (iii) never ship IQ4_XS,
   IQ4_NL, MXFP4, Q4_1, Q5_0/Q5_1, or any IQ2/IQ3 tensor to this audit; (iv) expect the audit tg to be 3–10× below an AVX2
   laptop's, so participant-side numbers must come from the same no-AVX build or the ±25 %/50 % variance check will flag/fail.
6. **Verification gap:** all cycle estimates are static. The one thing that would settle it is running the exact Docker
   stage-1 build (`test-quantize-perf --op vec_dot_q --type …` and `llama-bench`) on any x86 box — a free GitHub-Actions
   `ubuntu-latest` runner (4 vCPU x86) would do; see §9.

---

## 1. What the profiler runs (verified facts)

### 1.1 Dockerfile (`Africa-Deep-Tech-Foundation/adtc-profiler`, `main` @ `ac2e137dca`, fetched 2026-08-17)

Stage 1 (verbatim):

```
FROM debian:bookworm-slim AS llama-build
ARG LLAMACPP_REF=b10175
RUN apt-get update && apt-get install -y --no-install-recommends build-essential cmake git ca-certificates …
RUN git clone --depth 1 --branch "${LLAMACPP_REF}" https://github.com/ggerganov/llama.cpp.git /src/llama.cpp \
    && cd /src/llama.cpp \
    && cmake -B build \
        -DBUILD_SHARED_LIBS=OFF \
        -DGGML_NATIVE=OFF \
        -DGGML_AVX=OFF \
        -DGGML_AVX2=OFF \
        -DGGML_AVX512=OFF \
        -DGGML_FMA=OFF \
        -DGGML_F16C=OFF \
        -DGGML_BLAS=OFF \
        -DGGML_CUDA=OFF \
        -DGGML_METAL=OFF \
    && cmake --build build --config Release --target llama-bench llama-cli llama-server -j2
```

Stage 3 copies `llama-bench`, `llama-cli`, `llama-server` from stage 1 into `/usr/local/bin/` (`python:3.11-slim`, installs
`libgomp1` — i.e. the binary is an OpenMP build). Comment in the file: *"Stage 1: build llama.cpp (CPU-only, for parity with
Standard Laptop profile)"*.

Stage 2 builds the **llama-cpp-python wheel with only `CMAKE_ARGS="-DGGML_NATIVE=OFF"`** ("Portable CPU build — no
-march=native, the wheel must run on any audit VM"). Because `GGML_NATIVE=OFF` flips `INS_ENB` to `ON` (§2.1), that wheel is an
**AVX2+FMA+F16C+BMI2** build. It is used only by `accuracy.py` (lm-eval log-prob scoring via `llama_cpp.Llama`), **not** for
throughput.

### 1.2 What is timed

`adtc_profiler/throughput.py` (verified in the installed 0.1.0 package and the repo): `_find_llama_bench()` takes the first
`llama-bench` on `PATH` (in the image: the stage-1 no-AVX binary) and runs
`llama-bench -m <gguf> -p 512 -n 128 -ngl 0 --output json` (no `-t`, no `-fa`, no `-ctk`). S_perf uses the `n_gen>0` row's
`avg_ts` (`throughput.tokens_per_second_generation`); `first_token_latency_ms = n_prompt/pp_rate*1000` is recorded but the
README score formula only uses TPS. README (verbatim): `S_perf = min(TPS / TPS_REFERENCE, 1.0) * 100`, `TPS_REFERENCE = 15.0`;
audit is run as `docker run --rm --memory=7.5g … --mode audit`; tolerances participant-vs-audit
`throughput.tokens_per_second_generation ±25 % → flag, >50 % → fail`.

`llama-bench` defaults at b10175 (`tools/llama-bench/llama-bench.cpp:366-400`): `n_batch 2048`, `n_ubatch 512`,
`type_k/type_v F16`, `flash_attn AUTO`, `mmap` load, `n_threads = common_cpu_get_num_math()` which on x86-64 Linux
(non-hybrid) resolves to `common_cpu_get_num_physical_cores()` = number of distinct `thread_siblings` sets in `/sys` —
**2 threads on a "4 vCPU = 2 cores × 2 HT" VM, 4 on a "4 cores" VM** (Docker sees the host topology). `reps 5`.

### 1.3 Commits after 2026-08-15

Repo `pushed_at 2026-08-15T18:23:29Z`; only branch `main`; newest commit `ac2e137dca 2026-08-15 fix(packaging): lower minimum
Python requirement to >=3.10` touches `pyproject.toml` only. The Dockerfile's last change is `0bab3f33be 2026-07-29 fix(cli+build):
fail-safe pipeline, exit-code contract, working Docker build`. **Nothing after 2026-08-15 changes the build.**

---

## 2. (a) CMake resolution for the Dockerfile's cmake line

### 2.1 Which options end up ON/OFF (llama.cpp b10175)

`ggml/CMakeLists.txt`:

```
105  if (CMAKE_CROSSCOMPILING OR DEFINED ENV{SOURCE_DATE_EPOCH})
106      message(STATUS "Setting GGML_NATIVE_DEFAULT to OFF")
107      set(GGML_NATIVE_DEFAULT OFF)
108  else()
109      set(GGML_NATIVE_DEFAULT ON)
110  endif()
…
141  if (GGML_NATIVE OR NOT GGML_NATIVE_DEFAULT)
142      set(INS_ENB OFF)
143  else()
144      set(INS_ENB ON)
145  endif()
…
152  option(GGML_CPU_REPACK       "ggml: use runtime weight conversion of Q4_0 to Q4_X_X" ON)
154  option(GGML_SSE42            "ggml: enable SSE 4.2"          ${INS_ENB})
155  option(GGML_AVX              "ggml: enable AVX"              ${INS_ENB})
156  option(GGML_AVX_VNNI         "ggml: enable AVX-VNNI"         OFF)
157  option(GGML_AVX2             "ggml: enable AVX2"             ${INS_ENB})
158  option(GGML_BMI2             "ggml: enable BMI2"             ${INS_ENB})
159  option(GGML_AVX512           "ggml: enable AVX512F"          OFF)
165      option(GGML_FMA          "ggml: enable FMA"              ${INS_ENB})
166      option(GGML_F16C         "ggml: enable F16C"             ${INS_ENB})
183  option(GGML_CPU_ALL_VARIANTS "ggml: build all variants of the CPU backend (requires GGML_BACKEND_DL)" OFF)
 86  option(GGML_BACKEND_DL             "ggml: build backends as dynamic libraries (requires BUILD_SHARED_LIBS)" OFF)
197  option(GGML_LLAMAFILE                       "ggml: use LLAMAFILE"                             ${GGML_LLAMAFILE_DEFAULT})
245  option(GGML_OPENMP                          "ggml: use OpenMP"                                ON)
```

Top-level `CMakeLists.txt:149-151`: `if (NOT DEFINED GGML_LLAMAFILE) set(GGML_LLAMAFILE_DEFAULT ON)` → **`GGML_LLAMAFILE=ON`**
in a llama.cpp build. `CMakeLists.txt:10-12`: no `CMAKE_BUILD_TYPE` given → forced `Release` → GCC gets `-O3 -DNDEBUG`.

In the Docker build: not cross-compiling, `SOURCE_DATE_EPOCH` unset → `GGML_NATIVE_DEFAULT=ON`; the Dockerfile passes
`GGML_NATIVE=OFF` → `INS_ENB=ON` → every ISA option *not* explicitly overridden defaults **ON**. Result:

| option | value | why |
|---|---|---|
| `GGML_NATIVE` | OFF | Dockerfile |
| `GGML_SSE42` | **ON** | `INS_ENB` default, not overridden |
| `GGML_BMI2` | **ON** | `INS_ENB` default, not overridden |
| `GGML_AVX`, `GGML_AVX2`, `GGML_FMA`, `GGML_F16C`, `GGML_AVX512` | OFF | Dockerfile |
| `GGML_AVX_VNNI`, `AVX512_*`, `AMX_*` | OFF | defaults |
| `GGML_CPU_ALL_VARIANTS` | OFF | default; would `FATAL_ERROR` without `GGML_BACKEND_DL` (`ggml/src/CMakeLists.txt:371-373`) |
| `GGML_BACKEND_DL` | OFF | default; would `FATAL_ERROR` without `BUILD_SHARED_LIBS` (`ggml/src/CMakeLists.txt:188-189`) — and the Dockerfile sets `BUILD_SHARED_LIBS=OFF` |
| `GGML_LLAMAFILE` | ON | top-level default |
| `GGML_CPU_REPACK` | ON | default (but inert, §4) |
| `GGML_OPENMP` | ON | default; `libgomp1` in the runtime image |
| `GGML_CPU_KLEIDIAI`, `GGML_CPU_HBM` | OFF | defaults |

### 2.2 Which `-m` flags are emitted (`ggml/src/ggml-cpu/CMakeLists.txt`, x86, non-MSVC)

```
305  if (GGML_NATIVE)
306      list(APPEND ARCH_FLAGS -march=native)
307  else ()
308      if (GGML_SSE42)   list(APPEND ARCH_FLAGS -msse4.2)  list(APPEND ARCH_DEFINITIONS GGML_SSE42) endif()
312      if (GGML_F16C)    list(APPEND ARCH_FLAGS -mf16c)   … endif()
316      if (GGML_FMA)     list(APPEND ARCH_FLAGS -mfma)    … endif()
320      if (GGML_BMI2)    list(APPEND ARCH_FLAGS -mbmi2)   list(APPEND ARCH_DEFINITIONS GGML_BMI2) endif()
324      if (GGML_AVX)     list(APPEND ARCH_FLAGS -mavx)    … endif()
328      if (GGML_AVX2)    list(APPEND ARCH_FLAGS -mavx2)   … endif()
332-367  (AVX_VNNI, AVX512*, AMX* likewise)
368  endif()
…
731  message(STATUS "Adding CPU backend variant ${GGML_CPU_NAME}: ${ARCH_FLAGS} ${ARCH_DEFINITIONS}")
733  target_compile_options(${GGML_CPU_NAME} PRIVATE ${ARCH_FLAGS})
```

→ **`ARCH_FLAGS = -msse4.2 -mbmi2`**, `ARCH_DEFINITIONS = GGML_SSE42 GGML_BMI2` (configure log will say
`Adding CPU backend variant ggml-cpu: -msse4.2;-mbmi2 GGML_SSE42;GGML_BMI2`). With GCC, `-msse4.2` implies `-msse4.1 -mssse3
-msse3 -mpopcnt` and defines `__SSE4_2__ __SSE4_1__ __SSSE3__ __SSE3__ __POPCNT__`; `-mbmi2` defines `__BMI2__`. **`__AVX__`,
`__AVX2__`, `__FMA__`, `__F16C__`, `__AVX512F__` are all undefined** — those are the macros every kernel `#if` tests.

Two side notes: `__BMI2__` is only used inside `#if defined __AVX2__` blocks in `x86/quants.c` (iq1_s/iq1_m `_pdep_u64`) and in
`ggml_cpu_has_bmi2()`, so it buys nothing except letting GCC emit `sarx/shlx` in scalar code (seen in the GCC output for
`q2_K` generic) — which means the audit CPU must have BMI2 (Haswell/Excavator or newer; every 2026 cloud vCPU does).
`GGML_SSE42` similarly makes the binary require SSE4.2 (Nehalem+).

### 2.3 Variant / dispatch logic (`ggml/src/CMakeLists.txt`)

```
371  if (GGML_CPU_ALL_VARIANTS)
372      if (NOT GGML_BACKEND_DL)
373          message(FATAL_ERROR "GGML_CPU_ALL_VARIANTS requires GGML_BACKEND_DL")
…
378-401  ggml_add_cpu_backend_variant(x64 / sse42 / sandybridge / haswell(SSE42 AVX F16C FMA AVX2 BMI2) / skylakex / … )
…
464  elseif (GGML_CPU)
465      ggml_add_cpu_backend_variant_impl("")
466  endif()
```

Both gates are OFF in the Docker build → line 465: **one CPU backend, tag `""`, statically linked**. The runtime feature
probes are compile-time constants (`ggml/src/ggml-cpu/ggml-cpu.c`):

```
3610 int ggml_cpu_has_avx2(void) {
3611 #if defined(__AVX2__)
3612     return 1;
3613 #else
3614     return 0;
3615 #endif
```

(same pattern for `avx`, `avx512`, `f16c`, `fma`, `bmi2`, `sse3`, `ssse3`). **Decisive:** on the audit binary
`ggml_cpu_has_avx2()==0`, `ggml_cpu_has_ssse3()==1`, regardless of the host CPU. No AVX2 kernel can ever be selected.

The `GGML_CPU_ALL_VARIANTS` list (lines 378-401) shows what a `sse42` variant would be: exactly `SSE42` — i.e. the audit
binary is the `sse42` variant of the multi-variant scheme *plus* BMI2 (and llamafile, which is compiled in but inert, §5).

---

## 3. (b) `ggml/src/ggml-cpu/arch/x86/quants.c` — which `#if` path each `vec_dot` takes

Guard structure at b10175 (line numbers = the `#if`/`#elif`/`#else` of each function). "generic" means the function body ends
in `ggml_vec_dot_*_generic(...)` from `ggml/src/ggml-cpu/quants.c`; "scalar tail" means the SIMD block is skipped and the
scalar `for (; ib < nb; ++ib)` loop that follows `#endif` processes *all* blocks.

| vec_dot (x86 file) | `__AVX512F__` | `__AVX2__` | `__AVX__` | `__SSSE3__` | fallback | **audit build (SSE4.2 only) runs** |
|---|---|---|---|---|---|---|
| `q1_0_q8_0` (l.555) | (uses AVX2 path) | l.569 | l.607 | **l.657** | l.693 → generic | **hand SSSE3** |
| `q4_0_q8_0` (l.701) | (AVX2 path) | l.718 | l.742 | **l.770** | l.839 scalar tail | **hand SSSE3** (+ scalar tail for an odd last block) |
| `q4_1_q8_1` (l.859) | – | l.875 (`AVX2||AVX`) | l.875 | – | l.909 → generic | generic C |
| `mxfp4_q8_0` (l.918) | – | l.935 | l.965 | – | l.990 scalar tail (kvalues_fp4 lookups) | scalar tail |
| `nvfp4_q8_0` (l.1004) | – | l.1019 | l.1065 | – | l.1120 scalar tail | scalar tail |
| `q5_0_q8_0` (l.1142) | – | l.1159 | l.1182 | – | l.1213 → generic | generic C |
| `q5_1_q8_1` (l.1222) | – | l.1239 | l.1265 | – | l.1299 → generic | generic C |
| `q8_0_q8_0` (l.1308) | – | l.1325 | l.1343 | – | l.1362 scalar tail | **scalar tail loop** (GCC vectorises it, poorly) |
| `tq1_0_q8_K` (l.1376) | – | l.1388 | – | – | l.1500 → generic | generic C |
| `tq2_0_q8_K` (l.1508) | – | l.1520 | – | – | l.1566 → generic | generic C |
| `q2_K_q8_K` (l.1574) | – | l.1586 | l.1652 | – | l.1758 → generic | generic C |
| `q3_K_q8_K` (l.1766) | – | l.1782 | l.1886 | – | l.2028 → generic | generic C |
| `q4_K_q8_K` (l.2038) | – | l.2057 | l.2122 | – | l.2204 → generic | generic C |
| `q5_K_q8_K` (l.2216) | – | l.2235 | l.2314 | – | l.2414 → generic | generic C |
| `q6_K_q8_K` (l.2426) | – | l.2439 | l.2510 | – | l.2615 → generic | generic C |
| `iq2_xxs_q8_K` (l.2660) | – | l.2673 | l.2715 | – | l.2770 → generic | generic C |
| `iq2_xs_q8_K` (l.2778) | – | l.2791 | l.2909 | – | l.3067 → generic | generic C |
| `iq2_s_q8_K` (l.3075) | – | l.3088 | l.3160 | – | l.3252 → generic | generic C |
| `iq3_xxs_q8_K` (l.3260) | – | l.3273 | l.3319 | – | l.3376 → generic | generic C |
| `iq3_s_q8_K` (l.3384) | – | l.3397 | l.3480 | – | l.3586 → generic | generic C |
| `iq1_s_q8_K` (l.3594) | – | l.3607 (BMI2 sub-path l.3620) | l.3657 | – | l.3705 → generic | generic C |
| `iq1_m_q8_K` (l.3713) | – | l.3728 (BMI2 sub-path l.3759) | l.3825 | – | l.3911 → generic | generic C |
| `iq4_nl_q8_0` (l.3920) | – | l.3937 | l.3966 | – | l.3991 scalar tail (kvalues_iq4nl lookups) | scalar tail |
| `iq4_xs_q8_K` (l.4004) | – | l.4017 | l.4054 | – | l.4102 → generic | generic C |
| `q2_0_q8_0` | **no x86 implementation at all** — `arch-fallback.h:86` `#define ggml_vec_dot_q2_0_q8_0_generic ggml_vec_dot_q2_0_q8_0` | | | | | generic C (scalar) |
| `quantize_row_q8_0` (l.302) | – | l.309 (`AVX2||AVX`) | l.309 | – | l.393 `quantize_row_q8_0_ref` | scalar ref |
| `quantize_row_q8_1` (l.400) | – | l.405 | l.405 | – | l.497 `quantize_row_q8_1_ref` | scalar ref |
| `quantize_row_q8_K` (l.505) | **always** `quantize_row_q8_K_ref` on x86 (no SIMD path exists even with AVX2) | | | | | scalar ref |

Notes:
* There is **no `__AVX512F__`-specific vec_dot body** in this file at b10175 (`__AVX512F__` appears only at l.28/41/68/139 in
  helper guards); AVX-512 builds run the AVX2 kernels. Irrelevant for the audit but explains why "AVX512 off" costs nothing.
* The SSSE3 helper block (l.28-40 `mul_sum_i8_pairs` = `_mm_sign_epi8`+`_mm_maddubs_epi16`+`_mm_madd_epi16`; l.276-298
  `bytes_from_bits_16`, `hsum_float_4x4`) is compiled under `#if defined(__AVX__)||…||defined(__SSSE3__)`, so the SSSE3 paths
  build cleanly with `-msse4.2`.
* `GGML_TYPE_Q1_0 = 41` and `GGML_TYPE_Q2_0 = 42` exist at b10175 (`ggml/include/ggml.h:431-432`; `GGML_TYPE_COUNT = 43`).
  `block_q1_0` = 128 sign bits + fp16 scale (18 B / 128 w = **1.125 bpw**, values ±d); `block_q2_0` = 64 × 2-bit + fp16 scale
  (18 B / 64 w = **2.25 bpw**, codes 00/01/10/11 → −1/0/+1/+2 × d, `ggml-quants.c:439-457`). Q2_0 can hold ternary exactly but
  has no x86 kernel and a scalar generic loop; Q1_0 has an excellent SSSE3 kernel but cannot hold a zero.
* `vec_dot_type` (`ggml-cpu.c:215-410`): Q8_0 for Q1_0/Q2_0/Q4_0/Q5_0/Q8_0/MXFP4/NVFP4/IQ4_NL; Q8_1 for Q4_1/Q5_1; **Q8_K for
  all K-quants, TQ1_0/TQ2_0, IQ*/IQ4_XS**. `.nrows = 2` paths are `#if defined(__ARM_FEATURE_MATMUL_INT8)`/SVE only → `nrows=1`
  on x86 (`ggml-cpu.c:243-247, 275-279`).

---

## 4. (c) `ggml/src/ggml-cpu/repack.cpp` — what gets repacked

`ggml_repack_get_optimal_repack_type()` (`repack.cpp:4528-4725`) — x86-relevant branches:

| type | condition for a repack layout on x86 | layout | audit build (no AVX2) | plain-AVX2 x86 build |
|---|---|---|---|---|
| Q4_0 | `ggml_cpu_has_avx2()` (or SVE+i8mm) `&& ne[1]%8==0` | `q4_0_8x8_q8_0` | **none** | Q4_0 8x8 |
| Q4_K | `ggml_cpu_has_avx2() && ne[1]%8==0` | `q4_K_8x8_q8_K` | none | Q4_K 8x8 |
| Q2_K | `ggml_cpu_has_avx512() && ne[1]%8==0` | `q2_K_8x8_q8_K` | none | none (needs AVX-512) |
| IQ4_NL | `ggml_cpu_has_avx2() && ne[1]%8==0` | `iq4_nl_8x8_q8_0` | none | IQ4_NL 8x8 |
| MXFP4 | `ggml_cpu_has_avx2() && ne[1]%8==0` | `mxfp4_8x8_q8_0` | none | MXFP4 8x8 |
| Q5_K, Q6_K, Q8_0 | NEON (dotprod / i8mm) only | – | none | none |
| TQ1_0, TQ2_0, Q3_K, Q5_0, IQ*, Q1_0, Q2_0 | no repack path exists | – | none | none |

Because `ggml_cpu_has_avx2()` is compile-time `0` on the audit build, **the function returns `nullptr` for every tensor**; the
`CPU_REPACK` extra buffer type is registered (`GGML_USE_CPU_REPACK` is defined, `CMakeLists.txt:574-576`) but never claims a
tensor, so all weights stay in the mmap'd `CPU_Mapped` buffer and go through `vec_dot`. (`arch-fallback.h:87-111` also maps every
x86 `ggml_gemv_*/ggml_gemm_*` that lacks an AVX2 body to its `_generic` twin — moot here.) The x86 `arch/x86/repack.cpp`
gemv/gemm bodies are all under `__AVX2__`/`__AVX512F__` guards.

---

## 5. (d) llamafile / tinyBLAS (`ggml/src/ggml-cpu/llamafile/sgemm.cpp`)

`GGML_USE_LLAMAFILE` is defined and `sgemm.cpp` is compiled (`ggml-cpu/CMakeLists.txt:80-86`), and `ggml_compute_forward_mul_mat`
calls `llamafile_sgemm` first (`ggml-cpu.c:1295-1318` for `src1` already in `vec_dot_type`, `:1366-1389` after quantising
`src1`) and falls through to the standard per-row `vec_dot` loop only if it returns `false`. The dispatcher (`sgemm.cpp:3805-4164`):

```
3819 #if !defined(__MMA__)
3820     if (n < 2)          // "only enable sgemm for prompt processing"
3821         return false;
…
3829 case GGML_TYPE_F32:
3832 #if defined(__AVX512F__)     tinyBLAS<16, __m512, …>
3838 #elif defined(__AVX__) || defined(__AVX2__)   tinyBLAS<8, __m256, …>
3844 #elif defined(__ARM_NEON) … #elif __VXE__ … #elif __MMA__ … #elif __riscv_v_intrinsic …
3888 #else
3889         return false;
3957 case GGML_TYPE_F16:  AVX512F | (AVX||AVX2)&&F16C | ARM | VXE | riscv | MMA … else return false
4041 case GGML_TYPE_Q8_0: #if defined(__AVX2__) || defined(__AVX512F__) || defined(__AVX__)  tinyBLAS_Q0_AVX … #elif DOTPROD … #elif MMA … #else return false
4078 case GGML_TYPE_Q4_0: same guards
4115 case GGML_TYPE_Q5_0: AVX-family only, else false
4131 case GGML_TYPE_IQ4_NL: AVX-family only, else false
4147 default: return false;
```

There is **no SSE-only tinyBLAS instantiation** for any type (the `#if defined(__SSE__)` blocks at l.87-91/251-265/334-338 only
define `load<__m128>`/`madd` helpers that nothing instantiates on a non-AVX x86 build). Therefore on the audit build
`llamafile_sgemm` returns `false` for **every** `Atype` → both pp and tg use the standard `vec_dot` GEMV path. Consequences:
* tg is unaffected (sgemm is never used for `n < 2` anyway);
* **pp512 costs the same per token as tg** on this build (each prompt token = one full pass of `vec_dot` over all weights,
  no batching gain, no repack GEMM). Our M1 generic proxy measured pp512 = 4.13 tok/s vs tg128 = 3.70 tok/s
  (`opt/results/audit_kernel_proxy.md`). Expect the audit's `-p 512` phase to take 512/tg seconds (2–6 min for a 8B ternary
  model) — not scored, but it lengthens the run and warms the CPU (thermal penalty rule: >85 °C or throttling).

---

## 6. (e) Activation quantisation and fp16 without F16C

* **Q8_K activation quantisation** (`vec_dot_type` for all K-quants, TQ*, IQ*): `quantize_row_q8_K` in `x86/quants.c:505-507`
  is `quantize_row_q8_K_ref(x, y, k)` unconditionally — the scalar reference loop (per 256 floats: max, scale, `nearest_int`,
  16 `bsums`). This is identical on AVX2 builds, so it is not an audit-specific penalty. Cost per token ≈ Σ(input dims of all
  matmuls) ≈ 1 M floats for a 4B model → a few ms vs. hundreds of ms of matmul: negligible for tg; also negligible for pp
  (O(tokens × dim) vs O(tokens × dim × rows)).
* **Q8_0 / Q8_1 activation quantisation** (for Q4_0/Q8_0/…): AVX/AVX2 paths at l.309/405, else `quantize_row_q8_0_ref` — scalar,
  same order of cost, negligible.
* **fp16 → fp32** without `__F16C__` (`simd-mappings.h:56-62` selects `_cvtsh_ss` only under `__F16C__`; `:144-151` falls back to
  `ggml_lookup_fp16_to_fp32` = a load from the 64 K-entry (256 KiB) `ggml_table_f32_f16`). Per-block scale conversions in the
  kernels are 1–2 loads per 32–256 weights (visible in the asm as `movzwl … ; movss ggml_table_f32_f16(,%rax,4)`) — negligible.
  fp32 → fp16 is the bit-twiddling `GGML_COMPUTE_FP32_TO_FP16` (`:154-155`).
* Where it *does* cost: everything that touches whole F16 tensors — (i) `ggml_cpu_fp16_to_fp32` bulk conversion is a scalar
  table-lookup loop unless `__F16C__` (`ggml-cpu.c:3472-3521`); (ii) the SSE3 `GGML_F16_VEC` (`simd-mappings.h:898-996`) loads
  4 halves via 4 table lookups (`__sse_f16x4_load`) and stores via 4 bit-twiddles; (iii) CPU flash-attention with the default
  **F16 KV cache** accumulates V in an F16 buffer via `ggml_vec_mad_f16` (`ops.cpp:8566-8661`, `VKQ16`), i.e. per token
  `n_layer × n_head × n_kv × head_dim` half↔float conversions through the lookup/bit-twiddle paths. For tg128 from an empty
  context (`n_kv` ≤ 128) that is a few % of a 8B model's token time but ~10 % of a 1.7B model's; it is a per-token constant that
  hits every quant type equally (nothing at the GGUF level changes it — llama-bench is invoked with default `-ctk f16`).
  PR #21636's table (below) shows AVX → AVX+F16C = +13 % tg for a Q1_0 model, an upper bound for what F16C is worth on this
  workload; the SSSE3 row of that table was measured **without** F16C, like the audit build.
* Everything else (RMS-norm, RoPE, softmax, SiLU, F32 vec ops) runs on the SSE3 4-wide `GGML_SIMD` path — fine.

---

## 7. Kernel cost on the audit build — evidence

### 7.1 Method

`ggml/src/ggml-cpu/quants.c` (generic bodies) and `arch/x86/quants.c` (Q4_0/Q8_0/Q1_0 SSSE3 + tails) at b10175 were
(a) cross-compiled here with `clang -target x86_64-apple-macos12 -O3 -msse4.2 -mbmi2 -DNDEBUG -S` and (b) compiled as one
self-contained harness with **GCC 12.2 (`x86-64 gcc 12.2`) via the Compiler Explorer API, flags `-O3 -DNDEBUG -msse4.2 -mbmi2`**
— the compiler and flags the Dockerfile actually produces (Debian bookworm = GCC 12.2.0). Hot loops were located by backward
jumps and their instruction mix counted. Reproduce: sparse-clone tag b10175, extract the `*_generic` bodies + block structs +
the SSSE3 helpers into one file (`ggml_table_f32_f16` as an extern), POST to `https://godbolt.org/api/compiler/cg122/compile`.

### 7.2 GCC 12.2 hot loops (what the audit binary contains)

| kernel (audit path) | hot loop instrs / weights | instr/weight | dominant uops (Skylake port) | est. cycles/weight (kernel only) |
|---|---|---|---|---|
| `q4_0_q8_0` SSSE3 main loop | 72 / 64 | 1.1 | 8 psignb + 4 pmaddubsw + 4 pmaddwd + 4 cvtdq2ps + 4 mulps + 4 addps (p01), 8 loads, 4 prefetch; p5 idle | **0.25–0.30** |
| `q1_0_q8_0` SSSE3 | 144 / 128 | 1.1 | 16 pshufb + 16 pcmpeqb (p5), maddubs/madd | 0.25–0.30 |
| `q8_0_q8_0` scalar tail (GCC auto-vec) | 60 / 32 | 1.9 | 8 pmovsxbw + 8 pmovsxwd + 10 psrldq (**26 p5 uops/32 w**), 4 pmullw, 9 paddd | **0.45–0.8** (p5-bound; better on 2-shuffle-port cores) |
| `tq2_0_q8_K` generic | 83 / 32 (inner `.L84`, ×4 per 128) | 2.6 | 8 pmulld (2 uops each), 8 psrad, 8 pmovsx + 8 psrldq (p5), 8 pand, 17 paddd, per-32 horizontal reduce | **0.7–1.0** |
| `q4_K_q8_K` generic | 56 / 32 (mult pass) + 226 / 256 (unpack/scales/bsums) | 2.6 | 8 pmovsxbw + 8 punpck (p5), 8 pmullw + 4 pmulhw, 8 paddd; unpack: pand/psrlw/stores + 15 scalar imull | **0.7–0.9** |
| `q5_K_q8_K` generic | 56 / 32 + 309 / 256 | 3.0 | as Q4_K + qh masking (pcmpeqb/pandn/paddb) | 0.9–1.1 |
| `q6_K_q8_K` generic | 34 / 16 + 259 / 128 | 4.1 | unpack: 80 paddb + 40 pand + 20 psrlw per 128 | 1.2–1.5 |
| `q3_K_q8_K` generic | 35 / 16 + 237 / 128 | 4.0 | 56 pand, pcmpeqb/psubb masks | 1.2–1.5 |
| `tq1_0_q8_K` generic | 656 / 256 (+150-instr tail) | 2.6–3.1 | 40 pmullw + 40 pmovsxwd + 50 psrldq **+ 48 scalar imull + 56 movzbl** | 1.2–1.6 |
| `q2_K_q8_K` generic | 244–374 / 128–256 | 1.5–2.9 | **scalar**: 34 imull, 32 sarx (BMI2), 32 movsbl | 1.2–2 |
| `q2_0_q8_0` generic | 224 / 64 | 3.5 | **scalar**: 32 imull, 32 movsbl, 24 shrb/andl | ~1.2 |
| `q4_1_q8_1` generic | 193 / 32 | 6.0 | **scalar** (clang vectorises it, GCC does not) | ~2 |
| `iq4_nl_q8_0` tail / `mxfp4` tail | 220 / 32 | 6.9 | scalar: 64 movsbl (table gathers), 32 imull | ~2.3 |
| `iq4_xs_q8_K` generic | 453–467 / 64 | 7.2 | scalar: **128 movsbl** table gathers, 64 imull | ~2.5 |
| `q5_0_q8_0` generic | 377 / 32 | 11.8 | scalar bit-gathering | ~4 |
| `q4_0_q8_0` *generic* (not used on x86 — shows what SSSE3 saves) | 219 / 32 | 6.8 | scalar | ~2.3 (→ SSSE3 kernel ≈ 7–9× better) |

Cycle estimates assume a Skylake/Cascade-Lake-class core (3 vector ALU ports p0/p1/p5, shuffles on p5 only, `pmulld` 2 uops);
Zen 2/3 and Ice Lake+ have two shuffle pipes, which mainly helps the p5-bound Q8_0/generic loops (lower end of the ranges).
Kernel-only numbers are lower bounds; end-to-end tg per weight adds ~30–60 % (threading barriers, Q8 quantisation, attention,
SMT sharing) — see the anchor below.

Clang's codegen (what our M1 proxy and any clang-built x86 would run) differs: it fully unrolls the 256-blocks and keeps
vector accumulators (tq2_0: 591 instr/256 = 2.3/w with 56 `pmulld`; q4_K: 528/256 = 2.1/w with 118 `pmaddwd`; q8_0: 29/32
using `pmaddwd`; q4_1: vectorised 1.8/w). **GCC's generic loops are 1.3–3× worse than clang's** for TQ2_0/Q8_0/Q4_1, so the
M1-clang proxy in `opt/results/audit_kernel_proxy.md` is optimistic for the audit's GCC build.

### 7.3 Anchors (measured, not estimated)

1. **llama.cpp PR #21636** "ggml-cpu: Optimized x86 and generic cpu q1_0 dot (follow up)" (merged 2026-04-20, author pl752),
   Bonsai 1.7B **Q1_0**, AMD Ryzen 5 7640HS (Zen 4, 65 W, WSL, LPDDR5-6400, 10 threads), same binary family with different
   ISA flags — the only public like-for-like SSSE3-vs-scalar-vs-AVX2 llama.cpp table I could find:

   | flow | pp512 t/s | tg128 t/s |
   |---|---|---|
   | Scalar (generic C) | 13.07 | 9.38 |
   | `SSSE3` | 43.43 | 32.56 |
   | `AVX` | 53.54 | 40.70 |
   | `AVX` + `F16C` | 73.87 | 45.94 |
   | `AVX2` + `FMA` | 131.03 | 73.85 |
   | `AVX512` | 137.75 | 76.91 |

   → hand-SSSE3 kernel = **3.5× the generic-C tg** and **0.44× AVX2**; generic C = 0.13× AVX2. 32.56 t/s × 1.7 G weights over
   6 physical cores at ~4.5 GHz ≈ **0.49 cycles/weight end-to-end** for an SSSE3 hand kernel — consistent with the
   0.25–0.30 kernel-only estimate above plus overheads. (https://github.com/ggml-org/llama.cpp/pull/21636)
2. **Our M1 generic-C proxy** (`opt/results/audit_kernel_proxy.md`, 2026-08-17): BitCPM4-8B, TQ2_0 body 2.2 GB, `*_generic`
   forced, no repack, clang/NEON auto-vec: tg128 **3.70 ± 0.21 tok/s** at 4 threads, **1.09 tok/s single-thread = 2.40 GB/s =
   ≈9.3 G weights/s per core** (0.34 cycles/weight at 3.2 GHz — Firestorm's 4×128-bit SIMD + clang's unrolled codegen);
   TQ1_0 generic = 0.78 × TQ2_0; NEON native = 20.45 tok/s (5.5× the generic path); pp512 generic 4.13 tok/s ≈ tg.
3. Context only (AVX2 kernels, *not* the audit): compilade's PR #8151 `test-quantize-perf --op vec_dot_q` on a Core m3-8100Y:
   TQ2_0 141.8, Q2_K 81.7, TQ1_0 70.3, Q8_0 67.0, Q4_K 64.2, Q4_0 52.2, F16 30.6 GB/s fp32-equivalent — the AVX2 ordering
   (TQ2_0 fastest) **inverts** on the audit build because the TQ2_0 AVX2 kernel is the thing that is missing.
   (https://github.com/ggml-org/llama.cpp/pull/8151)
4. Anecdotal: KoboldCpp "failsafe" (no SIMD) users report ~8 s/token for a 7B Q4_0 on old laptops
   (https://github.com/LostRuins/koboldcpp/discussions/199) — consistent with "scalar ≈ 7× slower than SSSE3 for Q4_0" (§7.2 last row).

No public llama-bench table for a no-AVX x86 build of K-quants/TQ2_0 exists that I could find (searched GitHub issues/discussions,
HF, koboldcpp); the numbers in §7.2 are the best available substitute until §9 is done.

---

## 8. What this means for team-muta

### 8.1 Absolute tg estimates for the audit VM (assumptions: 4 physical cores ≈ 2.8 GHz, ~15 GB/s, GCC 12 build; ±50 %; halve
the compute-bound rows if the VM is 2 cores × 2 HT, because llama-bench will then use 2 threads)

| candidate | file (weights streamed/token) | limiter | est. tg128 |
|---|---|---|---|
| BitCPM4-8B **TQ2_0** (current, envocab-pruned) | ≈2.2 GB | compute (0.7–1.0 c/w × 8 G) | **1.3–2.7 tok/s** (the M1 proxy's 2.7 assumed clang-quality codegen; GCC-based estimate centres on ~1.6) |
| BitCPM4-8B TQ1_0 | ≈1.85 GB | compute | 1.0–2.1 (≈0.78× TQ2_0) |
| a 4B dense model, **Q4_0 pure** (out Q8_0) | ≈2.3 GB | bandwidth (kernel 0.3 c/w would allow ~7) | **4–7 tok/s** |
| same 4B, Q4_K_M | ≈2.5 GB | compute (0.8 c/w) | 2.5–4 |
| same 4B, Q8_0 | ≈4.3 GB | compute≈bandwidth | ~3 |
| same 4B, IQ4_XS | ≈2.2 GB | compute (2.5 c/w) | ~1 |
| a 1.7B dense model, Q4_0 pure | ≈1.0 GB | bandwidth | 12–15 |

`S_perf = min(TPS/15,1)×100`, so every tok/s below 15 is worth 2 points of S_perf (0.6 points of total score); the accuracy
half of the score (judged responses) is what decides whether a smaller Q4_0 model is acceptable — outside R4's remit.

### 8.2 GGUF-level levers that survive the audit (only the file reaches the audit)

1. **Body type for the ternary model:** TQ2_0 is the right choice among what exists at b10175 — TQ1_0 is ~0.8× per weight
   (and 1.2–1.6 c/w under GCC), Q2_0 is scalar-only generic and 9 % bigger, Q1_0 cannot hold zeros. Packing ternary weights
   exactly into Q4_0 blocks (custom writer: `d = s`, `q ∈ {7,8,9}`; note `quantize_row_q4_0_ref` would *not* be exact) would
   run the SSSE3 kernel ~3× faster per weight but at 4.5 GB the model becomes bandwidth-bound (~3 tok/s) and S_eff collapses
   (RSS ~4.6 GB → S_eff ≈ 34 vs ≈ 67): net loss. Not recommended.
2. **`output.weight` (235 MiB Q6_K today):** Q6_K's generic kernel is ~1.2–1.5 c/w and this tensor is read once per token;
   requantising it to **Q8_0** (0.45–0.8 c/w, +100 MiB, no accuracy loss) or **Q4_0** (0.25–0.3 c/w, −75 MiB, small accuracy
   cost) removes ~3–5 % of the token time and (Q4_0) 75 MiB of RSS. `token_embd` is a `get_rows` tensor — kernel irrelevant,
   only bytes matter (Q4_0 = Q4_K size).
3. **If a non-ternary model is chosen:** quantise with `llama-quantize … q4_0 --pure --output-tensor-type q8_0
   --token-embedding-type q4_0` (or `--pure` + `--output-tensor-type q4_0`). Reasons from `src/llama-quant.cpp` @ b10175:
   the plain `Q4_0` ftype makes `output.weight` **Q6_K** (l.452-473: `else if (new_type != GGML_TYPE_Q8_0) new_type = GGML_TYPE_Q6_K`),
   and with an imatrix it turns the first `n_layer/8` `ffn_down` tensors into **Q4_1** (l.618-624) — GCC compiles Q4_1's generic
   body **scalar** (6 instr/weight), a 6–8× slower kernel sitting in the busiest tensors of the first layers. Never use
   Q4_K_M/Q5_K_M/Q6_K/IQ4_XS/IQ4_NL/MXFP4 mixes for this audit.
4. **Row sizes:** the SSSE3 Q4_0 loop processes blocks in pairs (l.781 `for (; ib + 1 < nb; ib += 2)`); rows are always a multiple
   of 32, and an odd block count only adds one scalar block per row — irrelevant.

### 8.3 Operational

* pp512 on the audit build ≈ tg speed → the `-p 512` phase alone takes 512/tg s (3–7 min for the 8B ternary model at 1.3–2.7
  tok/s) before the 5 × tg128 reps; total run of the order of 15–20 min per model. Thermal penalty rule (>85 °C / throttle) is
  more likely to bite the slower the model.
* Participant-side `submission.json` numbers must be produced with the **same no-AVX build** (build the profiler image, or build
  b10175 with the Dockerfile's cmake line) — an AVX2/NEON native run will be 3–10× faster than the audit and fail the
  `>50 %` variance check (README tolerance table).
* The llama-cpp-python wheel in the image is an AVX2 build (stage 2, `-DGGML_NATIVE=OFF` only): the accuracy stage will SIGILL
  on a CPU without AVX2 — not our problem, but it tells you the auditors' VMs do have AVX2 that the scored binary is not
  allowed to use.

---

## 9. What is verified vs inferred, and how to close the gap

**Verified by reading source (b10175) / repo:** everything in §1–§6 and the guard/line tables; the exact flag set
`-msse4.2 -mbmi2`; single static backend; compile-time feature probes; no repack; no sgemm; scalar Q8_K quantisation; lookup-table
fp16. **Verified by compiling with GCC 12.2 (godbolt) and clang:** the instruction mixes in §7.2. **Measured:** the two anchors in
§7.3 (one on Zen 4 x86 with SSSE3 vs scalar vs AVX2 for Q1_0; one on M1 with generic-C forced for TQ2_0/TQ1_0).
**Inferred (±40–50 %):** cycles/weight, tiers, and the tok/s table in §8.1 — the *ordering* is robust (it follows from which
loops are hand-vectorised vs auto-vectorised vs scalar), the ratios are not.

**Cheapest way to make it measured (recommended before Gate 1):** run the exact stage-1 build on any x86-64 Linux box — e.g. a
GitHub Actions `ubuntu-latest` job (4 vCPU x86, free): `git clone --depth 1 --branch b10175 …; cmake -B build -DBUILD_SHARED_LIBS=OFF
-DGGML_NATIVE=OFF -DGGML_AVX=OFF -DGGML_AVX2=OFF -DGGML_AVX512=OFF -DGGML_FMA=OFF -DGGML_F16C=OFF -DGGML_BLAS=OFF; cmake --build build
--target llama-bench test-quantize-perf -j`, then `for t in q4_0 q8_0 q4_K q5_K q6_K tq1_0 tq2_0 iq4_xs q4_1 q2_0 q1_0; do
./build/bin/test-quantize-perf --op vec_dot_q -i 2000000 --type $t; done` (per-type GB/s and cycles/32 vals on the real kernels), plus
`llama-bench -m <small gguf> -p 512 -n 128 -ngl 0 -o json` on a ~1 GB Q4_0 vs TQ2_0 pair. That converts §7.2/§8.1 from estimates into
data in under an hour of runner time and also gives the participant-side numbers the variance check needs.

---

## 10. Sources

* llama.cpp tag `b10175` (`60bccc37…`, 2026-07-28): `ggml/CMakeLists.txt`, `ggml/src/CMakeLists.txt`, `ggml/src/ggml-cpu/CMakeLists.txt`,
  `ggml/src/ggml-cpu/arch/x86/quants.c`, `ggml/src/ggml-cpu/quants.c`, `ggml/src/ggml-cpu/arch-fallback.h`, `ggml/src/ggml-cpu/repack.cpp`,
  `ggml/src/ggml-cpu/arch/x86/repack.cpp`, `ggml/src/ggml-cpu/llamafile/sgemm.cpp`, `ggml/src/ggml-cpu/ggml-cpu.c`, `ggml/src/ggml-cpu/ops.cpp`,
  `ggml/src/ggml-cpu/simd-mappings.h`, `ggml/src/ggml-common.h`, `ggml/src/ggml-quants.c`, `ggml/include/ggml.h`, `tools/llama-bench/llama-bench.cpp`,
  `common/common.cpp`, `src/llama-quant.cpp` — https://github.com/ggml-org/llama.cpp/tree/b10175
* adtc-profiler: https://raw.githubusercontent.com/Africa-Deep-Tech-Foundation/adtc-profiler/main/Dockerfile ,
  https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler (README scoring/tolerance/docker sections; commits API: last push
  2026-08-15 `ac2e137dca`, Dockerfile last changed `0bab3f33be` 2026-07-29); installed package `adtc_profiler` 0.1.0
  (`throughput.py`, `accuracy.py`).
* PR #21636 (Q1_0 x86 SSSE3/AVX/AVX2 kernels + benchmark table): https://github.com/ggml-org/llama.cpp/pull/21636
* PR #8151 (TQ1_0/TQ2_0 introduction, AVX2/NEON `test-quantize-perf` table): https://github.com/ggml-org/llama.cpp/pull/8151
* KoboldCpp failsafe-mode anecdote: https://github.com/LostRuins/koboldcpp/discussions/199
* ADTC challenge page ("Standard Laptop profile … 8 GB RAM and 4 CPU cores"): https://africadeeptech.org/challenge-2026/ ,
  submission template: https://github.com/Africa-Deep-Tech-Foundation/adtc-2026-submission-template
* Team artefacts: `opt/results/audit_kernel_proxy.md` (M1 generic-C proxy), memory note `adtc-profiler-scoring-mechanics.md`.
* Compiler Explorer API used for the GCC 12.2 x86-64 compile: https://godbolt.org/api/compiler/cg122/compile
