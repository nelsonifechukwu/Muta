# Audit parity — how the self-reported S_perf/S_eff numbers must be produced

**Status:** written 2026-08-05 from the profiler source at `bench/adtc-profiler` (= upstream
HEAD `7adbe08`), llama.cpp b10175 source, and the official pages. Companion to the
2026-08-05 addendum in [rules-digest.md](rules-digest.md).

## Which numbers actually score — corrected 2026-08-19

The previous version claimed that organisers privately resolved the formula and hardware on
6 August. That claim has no attached email, link, quote, issue, or forum message, and later
project research explicitly records that no public clarification exists. Do not treat it as
evidence.

Two current official sources conflict. The challenge webpage describes a physical Standard
Laptop and cohort-relative `100·TPS/TPS_max`. The official profiler README/code describe audit
mode in secure cloud VMs and implement `min(TPS/15, 1)·100`. For reproducible campaign
decisions, the executable profiler is the score-of-record: **fixed 15 tok/s, capped, reference
cloud-VM binary**. The webpage interpretation remains a labelled sensitivity only.

## AVX2 repack composition — product/physical-laptop evidence, not audit parity

llama.cpp copies repackable tensors into private anonymous memory at load. On x86 **only
Q4_0 and Q4_K repack**; Q5_K, Q6_K, Q3_K and IQ4_XS never do (`repack.cpp` registers
`iq4_nl`, not `iq4_xs`). Therefore:

> **peak RSS ≈ file size + the repackable fraction of the file**

Measured on the b10175 engine built with AVX2 (2026-08-06, `/usr/bin/time -l`):

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

**Match the published reference Dockerfile.** At b10175 that disables native, AVX, AVX2,
AVX-512, FMA and F16C. No repack executes and Q4_0 retains its SSSE3 kernel:

```bash
cmake -B build -DBUILD_SHARED_LIBS=OFF \
      -DGGML_NATIVE=OFF -DGGML_AVX=OFF -DGGML_AVX2=OFF -DGGML_AVX512=OFF \
      -DGGML_FMA=OFF -DGGML_F16C=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build --target llama-bench
```

An AVX2 build remains useful to predict deployment UX, but its TPS/RSS must not be mixed with
the score-of-record. If ADTF publishes a versioned audit image that enables AVX2, rerun and
promote that evidence; until then the reference image wins the provenance tie.

## Launch posture for the measurement run

- Reference container on an x86 host, 7.5 GiB cgroup limit, no swap, otherwise idle. Record
  the host as a cloud proxy; do not call it the physical target laptop.
- **Never launch the profiler under a cgroup cpuset** (docker `--cpuset-cpus`,
  systemd `AllowedCPUs`): llama-bench's thread-count probe fails EINVAL on excluded CPUs
  and falls back to ALL physical cores — guaranteed oversubscription. Plain `taskset` is
  safe (constrains placement, never the count). Never disable SMT in BIOS on hybrid
  Intel (the sibling-skip logic then halves the P-core count).
- `nice -n -10` on the profiler is cheap insurance for the 5-rep average; avoid RT
  scheduling (`--prio 2` measured pathological).
- Thermal sensors may be unavailable in a cloud VM. Record unknown; never rewrite it as cool.
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
