# Overnight GGUF model search — 20 August 2026

## Objective

Find a defensible improvement over the current submitted artifact for ADTC 2026 Math &
Scientific Reasoning. The deliverable remains one GGUF file. A result is not promoted unless
the exact file loads in the pinned llama.cpp/profiler stack, remains within the 7 GiB RSS
budget, and improves the measured score or presents a justified accuracy/performance hedge.

## Evidence lanes

The public challenge page and the executable profiler do not implement the same performance
formula. This campaign preserves both without combining them:

1. **Executable-profiler lane:** participant-mode `adtc-profiler 0.1.0`, scalar b10175
   benchmark binary, `S_perf = 100 * min(TPS / 15, 1)`.
2. **Portable AVX2 lane:** b10175 with AVX2, FMA and F16C enabled, AVX-512 disabled,
   `S_perf = 100 * TPS / max(pre-entry cohort floor, candidate TPS)`.

The GCP VM is an x86 cloud proxy, not a physical target-laptop result. It has 2 physical cores,
4 threads, 8 GB RAM and no usable temperature sensor.

## Frozen controls

| Control | SHA-256 | Purpose |
|---|---|---|
| Muta Tutor Qwen3-1.7B pure Q4_0 tied | `a98ce36e9ff97e52…` | current scalar-profiler winner |
| Qwen3.5-0.8B Q4_K_M | `bd258782e35f7f45…` | closest scalar-profiler efficiency hedge |
| scalar b10175 `llama-bench` | `7f01dc0465d64f72…` | executable-profiler throughput parity |
| AVX2 b10175 `llama-bench` | `4abfa11a3f86b8c…` | portable deployment proxy |

Baseline score-of-record: Muta Tutor, 9.79 generation tok/s, 1116.31 MiB peak RSS,
72% ARC-Easy-50, total 72.4653 under the executable-profiler formula.

## Candidate gates

Candidates are tested in increasing cost. A failure is retained rather than dropped.

1. **Exact low-cost quant gate.** Compare the official Qwen3.5-0.8B Q4_0 with the existing
   Q4_K_M control on both binaries. Run ARC-Easy-50 and the full profiler if it can exceed the
   incumbent after measured RSS.
2. **Balanced small-model screen.** Test Noema-2B, VibeThinker-1.5B and
   OpenMath-Nemotron-1.5B from immutable model revisions. Use a one-round throughput screen,
   then ARC-Easy/ARC-Challenge/SciQ only for viable files.
3. **Speed hedges.** Screen two sub-0.6B open math specialists. They advance only if the
   performance gain survives a broad-science accuracy check.
4. **Quantization sweep.** For any advancing BF16 source, compare Q4_0, Q4_K_M and at most one
   quality-preserving quant. Do not up-quantize an already quantized source.
5. **Exact profiler confirmation.** Run participant mode for every finalist, preserving its
   raw report, model hash, report hash and environment identity.

## Promotion rules

- No result is described as an official competition score; ARC-Easy is an accuracy proxy.
- A candidate with OOM, load failure, missing provenance, non-commercial terms, or RSS above
  7 GiB is rejected.
- Quantization variants must keep exact model-family and chat-template provenance.
- Small accuracy samples are reported with Wilson 95% intervals.
- A nominal gain smaller than benchmark variance is not a decisive promotion.
- Fine-tuning is attempted only if a reproducible dataset, base revision, training recipe and
  conversion path fit the remaining time. A speculative or partially trained file is not
  promoted.
- The physical target laptop remains the final authority for temperature and report-grade TPS.

## Output

Raw rows, exact manifests, generated summaries and rejected-candidate reasons remain in this
directory. The end of `muta-iq/REPORT.md` receives a direct account of the search, the measured
progression, figures, the winning file and the unresolved risks.
