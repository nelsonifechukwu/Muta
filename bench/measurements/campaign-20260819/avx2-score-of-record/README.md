# AVX2/FMA/F16C score-of-record rerun — 19 August 2026

## Outcome

This is a fresh, controlled five-model rerun of the retained scalar score-of-record matrix with
only the portable x86 SIMD build policy changed. It does **not** replace the scalar evidence or
the complete bundled-profiler reports. Under the profiler's capped-15 formula, Q4_K_M is the
nominal AVX2 winner by 0.1666 points; that lead is too small to call a robust promotion without a
physical target run.

| Artifact | Scalar tg128 | AVX2 tg128 ± sd | Speedup | Scalar est. RSS | AVX2 est. RSS | ARC-Easy | Scalar score | AVX2 score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Muta Tutor Qwen3-1.7B Q4_0 tied `a98ce3…` | 9.9869 | 16.8927 ± 0.1642 | 1.691× | 1133.1 MiB | 2049.4 MiB | 72% | **72.8122** | 80.2818 |
| **Qwen3-1.7B Q4_K_M tied `e8a413…`** | 5.2954 | **15.6714 ± 1.2364** | 2.959× | 1183.5 MiB | 1989.7 MiB | 72% | 63.2887 | **80.4484** |
| Qwen3-1.7B Q5_K_M tied `17ddf7…` | 4.7839 | 12.7191 ± 0.0784 | 2.659× | 1364.5 MiB | 1364.6 MiB | 76% | 63.7606 | 79.6307 |
| Qwen3-1.7B IQ4_XS tied `aea3cb…` | 2.4961 | 14.0644 ± 0.0942 | 5.635× | 1081.8 MiB | 1082.3 MiB | 70% | 56.9738 | 80.1089 |
| BitCPM4-8B TQ2_0 envocab `069621…` | 0.8108 | 7.4876 ± 0.0562 | **9.235×** | 2316.3 MiB | 2316.4 MiB | 88% | 59.1587 | 72.5121 |

AVX2 pp512 results were 47.0716, 55.4554, 24.3231, 23.9364 and 13.6569 tok/s in the same row
order. Exact timing vectors, wall times, RSS values and commands are in `results.jsonl` and
`comparison.json`.

## Controlled build

Source: llama.cpp b10175, commit
`60bccc3763395e01b039aa1ddeacc8cc0ea69f70`, built with CMake 3.22.1 and GNU 11.4.0 on Ubuntu
22.04. The scalar binary remains at SHA-256
`7f01dc0465d64f726b2b66139859a8ff1ca204f4901e18b71ddfa678dea19370`.
The fresh AVX2 binary is SHA-256
`4abfa11a3f86b8c5e4d508cce10daf8f381c968585a3e5961fea3d5cbe312fd8`.

```bash
cmake -S bench/.artifacts/llama.cpp-b10175 \
  -B bench/.artifacts/llama.cpp-b10175/build-avx2-rerun-20260819 \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_NATIVE=OFF \
  -DGGML_AVX=ON \
  -DGGML_AVX2=ON \
  -DGGML_FMA=ON \
  -DGGML_F16C=ON \
  -DGGML_AVX512=OFF \
  -DGGML_AVX512_VBMI=OFF \
  -DGGML_AVX512_VNNI=OFF \
  -DGGML_OPENMP=ON \
  -DLLAMA_CURL=OFF \
  -DBUILD_SHARED_LIBS=OFF

cmake --build \
  bench/.artifacts/llama.cpp-b10175/build-avx2-rerun-20260819 \
  --target llama-bench -j2
```

The complete generated cache is retained as `CMakeCache.txt` and the public cache view as
`cmake-cache.txt`. Configure output records the selected backend flags:

```text
-msse4.2;-mf16c;-mfma;-mbmi2;-mavx;-mavx2
GGML_SSE42;GGML_F16C;GGML_FMA;GGML_BMI2;GGML_AVX;GGML_AVX2
```

The fresh binary and its CPU backend archive reproduce the independent earlier AVX2 build
byte-for-byte. GGML's runtime trace reports:

```text
CPU : SSE3 = 1 | SSSE3 = 1 | AVX = 1 | AVX2 = 1 | F16C = 1 | FMA = 1 |
BMI2 = 1 | LLAMAFILE = 1 | OPENMP = 1 | REPACK = 1 |
```

The scalar trace omits AVX, AVX2, F16C and FMA. Every AVX-512 CMake switch is OFF, no AVX-512
feature appears in the runtime trace, and the retained disassembly scan found zero ZMM/opmask or
selected AVX-512 instruction signatures.

## Host and method

The GCP `n2-custom-4-8192` proxy exposes two physical cores / four SMT threads and the required
AVX, AVX2, FMA and F16C flags. The host also exposes AVX-512, which this build deliberately does
not use. The exact `lscpu`, `/proc/cpuinfo`, `nproc` and sensor output is in `cpu.txt`.

All five SHA-256-verified GGUFs were run once through `bench/adtc_bakeoff.py`. Each invocation was:

```bash
llama-bench -m MODEL -p 512 -n 128 -o json -ngl 0 -r 5
```

No thread flag was supplied, matching the profiler. The binary selected two physical-core
threads. The harness sampled the llama-bench process-tree RSS every 100 ms; the score adds the
same 45 MiB profiler-root estimate used by the retained scalar promotion screen. ARC-Easy values
were reused by immutable model hash and were not rerun.

## Interpretation

- AVX2 materially reverses the scalar kernel ordering. Q4_K_M rises 2.959× and nominally beats
  Q4_0 because both clear the 15 tok/s cap while Q4_K_M's estimated RSS is 59.7 MiB lower.
- The nominal Q4_K_M margin is only 0.1666 total points. Its five decode samples include one
  13.6101 tok/s outlier and have much higher variance than the other candidates. This is an AVX2
  proxy winner, not enough evidence to replace the scalar-profiler submission choice.
- Q4_0 gains 1.691× but AVX2 repacking adds about 916 MiB to estimated profiler RSS. The speed
  gain still improves its capped score by 7.4696 points.
- IQ4_XS is the strongest non-repacking efficiency hedge: 5.635× faster, essentially unchanged
  RSS, and only 0.3395 points behind the nominal AVX2 winner despite its two-point Easy deficit.
- BitCPM's scalar collapse was primarily an ISA/kernel effect: TQ2_0 recovers 9.235×. It is now
  operationally viable at 7.49 tok/s, but 2.26 GiB estimated RSS and sub-cap throughput leave it
  7.94 points behind Q4_K_M. Its quality lead does not make it the capped-15 winner.

Therefore the current executable-profiler submission remains Muta Tutor pure Q4_0 tied. If a
portable AVX2 build rather than the published scalar profiler governs the final machine, Q4_K_M
becomes the nominal quant choice, with IQ4_XS close enough to warrant confirmation on the physical
target. The two regimes remain separately labelled and neither is silently overwritten.

## Evidence limitations

- This is a sensorless GCP cloud proxy, not the physical competition laptop. Package temperature
  and throttling could not be measured, so no thermal penalty is applied and thermal remains
  unknown.
- The scalar incumbent has five internal repetitions, while the four scalar challengers are the
  retained one-repetition promotion screen requested by the original campaign. Every AVX2 row has
  five internal repetitions.
- AVX2 RSS is estimated profiler parity, not a new full participant-mode profiler run: measured
  child-tree peak plus the retained 45 MiB root-process estimate.
- The ARC-Easy proxy has only 50 samples and is not the hidden tutoring-quality judgment.
