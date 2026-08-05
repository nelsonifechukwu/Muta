# Audit parity — how the self-reported S_perf/S_eff numbers must be produced

**Status:** written 2026-08-05 from the profiler source at `bench/adtc-profiler` (= upstream
HEAD `7adbe08`), llama.cpp b10175 source, and the official pages. Companion to the
2026-08-05 addendum in [rules-digest.md](rules-digest.md).

## Which numbers actually score — two readings, one strategy

- The official page annotates the S_perf formula with "**TPSact: actual tokens/sec during
  audit**", and its FAQ says final benchmarks run on the organizers' machine. Under this
  reading the AUDIT re-run is scored and our submission.json is an integrity claim.
- The Gate-1 leaderboard exists before any audit, so self-reported numbers plausibly rank
  provisionally until Gate 2 re-runs them.

Both readings collapse to the same strategy: **maximize what the audit environment will
measure, and self-report numbers produced the same way the audit produces them.** A
self-report the audit can't reproduce within tolerance is flagged (>±25% TPS / ±15% RSS)
or failed (>±50%) — and `first_token_latency_ms` (pp512) is reconciled at ±25% too, which
kills any build-mismatch posture on its own: AVX2-vs-SSE pp deltas run 4–8×.

## The audit environment (verified from the reference Dockerfile)

llama.cpp **b10175** built with `GGML_NATIVE/AVX/AVX2/AVX512/FMA/F16C = OFF` (SSE4.2+BMI2
stay on via defaults), llama-bench on PATH, run under `docker --memory=7.5g`, profiler
invocation fixed: `llama-bench -m model.gguf -p 512 -n 128 -ngl 0 -o json` (no `-t`).
Consequences (source-verified):

- Only **Q4_0** weights have a vectorized (SSSE3) dot kernel there; Q4_K/Q5_K/Q6_K/Q8_0/IQ*
  run generic scalar C. Quant choice moves audit TPS by multiples.
- **No repack** (all x86 repack gates are compile-time AVX2) → audit peak tree RSS ≈
  GGUF file size + ~0.35–0.5 GB (profiler python ~35–55 MB included; lm-eval imports are
  lazy and outside the sampling window).
- Cloud-VM thermal sensors read null → P_thermal unreachable there.

## The self-report build (what `llama-bench` on our PATH must be)

```bash
# b10175, audit-matched CPU features, static, no repack:
cmake -B build -DBUILD_SHARED_LIBS=OFF \
      -DGGML_NATIVE=OFF -DGGML_AVX=OFF -DGGML_AVX2=OFF -DGGML_AVX512=OFF \
      -DGGML_FMA=OFF -DGGML_F16C=OFF \
      -DCMAKE_BUILD_TYPE=Release
cmake --build build --target llama-bench
```

Rationale: matching the audit's kernel map compresses the reconciliation delta to
hardware-only variance, and pp/tg deltas then move together. An AVX2-built self-report
against an SSE audit near-certainly hard-fails TTFT and likely TPS.

If the audit turns out to run AVX2 on the Standard Laptop instead (unconfirmed), the
right self-report build is AVX2 **with `-DGGML_CPU_REPACK=OFF`**: repack on x86 AVX2 is a
prefill-only optimization (PR #12332: pp +61–76%, tg128 −2%) that adds ~+1.3–2.5 GB
anonymous RSS — strictly score-negative for the fixed tg128+RSS metrics. Rehearse both
builds; ship the numbers from whichever matches the audit mode once organizers clarify.

## Launch posture for the measurement run

- Bare metal Ubuntu 22.04, the real 8 GB laptop (`environment.ram_gb` reads host meminfo —
  a bigger box betrays itself), AC power, idle, network down, performance governor
  (`cpupower frequency-set -g performance`), dual-channel RAM verified via
  `dmidecode -t memory` (single-channel halves bandwidth-bound tg).
- **Never launch the profiler under a cgroup cpuset** (docker `--cpuset-cpus`,
  systemd `AllowedCPUs`): llama-bench's thread-count probe fails EINVAL on excluded CPUs
  and falls back to ALL physical cores — guaranteed oversubscription. Plain `taskset` is
  safe (constrains placement, never the count). Never disable SMT in BIOS on hybrid
  Intel (the sibling-skip logic then halves the P-core count).
- `nice -n -10` on the profiler is cheap insurance for the 5-rep average; avoid RT
  scheduling (`--prio 2` measured pathological).
- Thermal: the tg row runs after all pp reps, thermally soaked; a cool chassis and a
  cold start protect both the scored tg and the self-reported `core_temp_c_peak`
  (P_thermal fires at ≥85 °C, read from our own report on bare metal).
- Do not suppress RSS artificially (cgroup memory.high, zram tricks): audit RSS ≈ file
  size plus ~0.4 GB; a submitted value below audit/1.15 flags, below audit/1.5 fails,
  and a near-zero value is an automatic structural fail.

## Rehearsal = the reference image itself

```bash
cd bench/adtc-profiler && docker build -t adtc-profiler:local .
docker run --rm --memory=7.5g -v "$PWD/../submission:/submission:ro" \
  -v /tmp/artifacts:/artifacts adtc-profiler:local \
  run --submission /submission --mode audit --output /artifacts/audit-rehearsal.json
adtc-profiler compare submission.json /artifacts/audit-rehearsal.json
```

The `compare` verdict must be `pass` before Gate 1 ships. (On the Apple dev host this
runs under emulation — numbers are not audit-grade, but the compare mechanics and the
schema are exercised end-to-end; the real rehearsal belongs on the x86 box.)

## What does NOT work (dead ends, so nobody retries)

- `LLAMA_ARG_*`/`OMP_NUM_THREADS` env vars: llama-bench has its own parser; the OpenMP
  `num_threads` clause overrides OMP_NUM_THREADS (only `OMP_THREAD_LIMIT` caps it).
- `ulimit -m` (unenforced since Linux 2.4) and `ulimit -v` (aborts the model mmap).
- BLAS/MKL (batch≥32 only — never touches tg128), THP (file mmaps ineligible),
  allocator preloads (no hot-path allocations), mlock (raises RSS, anti-scoring).
- Packaging modes: the profiler never reads `model.packaging`; the audit benchmarks the
  bare GGUF with the reference llama-bench regardless — a custom docker image cannot
  carry an optimized runtime into the scored path.
