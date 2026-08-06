# Audit parity — how the self-reported S_perf/S_eff numbers must be produced

**Status:** written 2026-08-05 from the profiler source at `bench/adtc-profiler` (= upstream
HEAD `7adbe08`), llama.cpp b10175 source, and the official pages. Companion to the
2026-08-05 addendum in [rules-digest.md](rules-digest.md).

## Which numbers actually score — settled 2026-08-06

Organizer answers, recorded here because two of them invalidate earlier reasoning:

- **`S_perf = TPS/TPS_max`, uncapped and cohort-relative** — not the profiler README's
  `min(TPS/15, 1)`. Throughput scales linearly into the score with no saturation point,
  so there is no "fast enough" threshold to stop at.
- **The audit runs on the physical Standard Laptop** (i5 10th-12th gen / Ryzen 5
  3000-5000, 8 GB DDR4, Ubuntu 22.04), **not** the SIMD-less reference container.
- Gate 1 is **August 25**.

The second answer changes the engineering target completely, because a normal laptop
build has AVX2 — which means **weight repack runs**, and repack is the dominant term in
peak RSS. See "The repack composition rule" below. The container analysis that used to
live in this section is retained only as the contingency case, in case a cloud-VM audit
reappears at Gate 2.

## The repack composition rule — the single most important fact for S_eff

llama.cpp copies repackable tensors into private anonymous memory at load. On x86 **only
Q4_0 and Q4_K repack**; Q5_K, Q6_K, Q3_K and IQ4_XS never do (`repack.cpp` registers
`iq4_nl`, not `iq4_xs`). Therefore:

> **peak RSS ≈ file size + the repackable fraction of the file**

Measured on the audit-pin engine built with AVX2 (2026-08-06, `/usr/bin/time -l`):

| model | file GiB | peak RSS GB | overhead |
|---|---|---|---|
| 4B IQ4_XS | 2.31 | 2.65 | +0.34 |
| 4B UD-Q3_K_XL | 2.27 | 3.20 | +0.93 |
| 4B Q4_K_M | 2.55 | 4.21 | +1.66 |
| 4B Q4_0-EH (all-Q4_0) | 2.22 | 4.85 | +2.63 |
| 2B Q6_K | 1.47 | 1.73 | +0.26 |

A file made entirely of repackable types doubles; a file made of non-repacking types does
not grow at all. **Choosing the quant type is choosing the memory footprint**, and file
size alone predicts it badly — the smallest file here is the heaviest in RAM.

## The self-report build (what `llama-bench` on our PATH must be)

**Match a stock laptop build — do not tune it.** The audit measures on their machine with
their binary, and reconciliation compares the two readings:

```bash
cmake -B build -DBUILD_SHARED_LIBS=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build --target llama-bench
```

That is deliberately the plainest possible invocation: `GGML_NATIVE` defaults on, AVX2/FMA
/F16C/BMI2 come along, and **repack stays enabled**. Every temptation to be clever here is
a reconciliation risk rather than a score gain:

- `-DGGML_CPU_REPACK=OFF` would cut our reported RSS by 1.5-2.6 GB — and the audit, running
  a stock build, would measure the full figure. Delta `(audit − sub)/sub` of +50% or more is
  an outright **fail**, not a lower score. The same logic kills cgroup memory caps and any
  other footprint suppression.
- `-march=native` on our machine is fine for the *product*, but tuning past the audit box's
  ISA inflates a number they cannot reproduce.

**Consequence worth stating plainly: build flags cannot buy S_eff any more.** With the
audit on real hardware running a stock binary, the only lever left on peak RSS is the
**quant composition of the submitted file** — see the repack composition rule above. That
is now the primary model-selection criterion, ahead of file size.

*Contingency:* if a Gate-2 audit reappears in the SIMD-less reference container, the
matching self-report build is the all-SIMD-off one (AVX/AVX2/FMA/F16C `OFF`), where no
repack occurs and Q4_0 is the only vectorized weight kernel. Keep that build around; it
is the reason `Qwen3.5-4B-Q4_0-EH` exists.

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
