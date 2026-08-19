# AVX2 score-of-record rerun plan

**Date:** 2026-08-19
**Status:** Complete
**Scope:** Isolate the effect of portable x86 AVX/AVX2/FMA/F16C kernels on the existing
five-model score-of-record comparison without changing artifacts, quality proxies, scoring,
benchmark dimensions, or the retained scalar baseline.

## Invariants

- llama.cpp remains pinned to b10175 / `60bccc3763395e01b039aa1ddeacc8cc0ea69f70`.
- The existing scalar build and raw evidence are read-only inputs.
- The new build uses `GGML_NATIVE=OFF`, AVX/AVX2/FMA/F16C ON, and every AVX-512 option OFF.
- The VM must expose AVX, AVX2, FMA, and F16C before any measurement begins.
- Models are accepted only after their complete SHA-256 hashes match the campaign manifest.
- Every measurement uses the existing GCP 2C/4T context, `p512/tg128`, `-ngl 0`, two
  physical-core threads, the existing tree-RSS sampler, and five llama-bench internal samples.
- ARC-Easy proxies and the capped `TPS_REFERENCE = 15` score are reused unchanged.
- Scalar and AVX2 evidence remain separate; neither regime silently replaces the other.

## Procedure

1. Capture CPU topology/flags and the scalar binary path, commit, configuration, hash, and
   reported feature line.
2. Stop product services, confirm no competing benchmark/inference process, and build into a
   separate AVX2 directory from the pinned checkout.
3. Verify the CMake cache, compiler, binary hash, commit, disassembly safety, and runtime
   feature report before accepting the build.
4. Run the five pinned artifacts with the portable benchmark harness and retain raw JSONL.
5. Produce scalar-versus-AVX2 deltas, speedups, RSS changes, capped-15 scores, and verdicts.
6. Add a clearly separated AVX2/FMA/F16C section and artifact manifest to the experiment
   report, run focused/full validation, and synchronize the grouped commit to GitHub and GCP.

## Acceptance

- No required VM feature missing; AVX-512 remains disabled.
- All five artifact hashes match and all five runs complete with five internal samples.
- The report states both winners, BitCPM and Q4_0 speedups, ranking changes, measurement limits,
  and exact provenance without presenting the GCP cloud proxy as target-laptop evidence.
