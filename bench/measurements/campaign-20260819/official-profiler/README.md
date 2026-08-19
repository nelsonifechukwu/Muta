# Bundled ADTC profiler confirmation runs

This directory contains the profiler's own schema-validated participant reports, not a
reconstruction from `llama-bench` telemetry. Each candidate was run sequentially with:

```bash
adtc-profiler run \
  --submission <synthesized-candidate-directory> \
  --mode participant \
  --output <candidate>.json
```

The executable was `adtc-profiler 0.1.0` from source commit
`7adbe08f157e9b96a670426339aca2a519706bdc`. `PATH` selected the profiler-reference
llama.cpp b10175 `llama-bench` at commit
`60bccc3763395e01b039aa1ddeacc8cc0ea69f70`, binary SHA-256
`7f01dc0465d64f726b2b66139859a8ff1ca204f4901e18b71ddfa678dea19370`. Its build has
native/AVX/AVX2/AVX-512/FMA/F16C disabled, is static, and has CUDA disabled.
The in-process accuracy stack was llama-cpp-python 0.3.35 (libllama SHA-256
`113665710f3103712eb24bf2c897b83beb0029fc93df62cd99123b77b7911047`), lm-eval 0.4.12,
NumPy 2.4.6 and datasets 5.0.1; these exact versions are also retained in `manifest.json`.

The profiler itself performed all of the following:

- its default `p512/tg128`, CPU-only throughput run with five internal benchmark samples;
- 10 Hz peak-RSS sampling over the profiler root and its `llama-bench` child tree;
- ARC-Easy through its in-process llama-cpp-python/lm-eval adapter, seed 42, limit 50;
- schema validation and the GGUF parameter-count fraud check.

`manifest.json` binds every report to the exact GGUF bytes and report bytes. `summary.json`
and `summary.tsv` are regenerated fail-closed by `python -m
bench.official_profiler_summary`; the aggregator rejects hash drift, mixed environments,
failed parameter checks, missing ARC-Easy data, or invalid throughput/RSS.

## Result

| Candidate | Generation TPS | Peak RSS | ARC-Easy-50 | Fixed-15 composite |
|---|---:|---:|---:|---:|
| **Muta Tutor Qwen3-1.7B pure Q4_0 tied** | **9.79** | **1116.31 MiB** | **72%** | **72.4653** |
| Qwen3.5-0.8B Q4_K_M | 9.74 | 694.73 MiB | 68% | 71.5416 |
| BitCPM4-8B TQ2_0 vocabulary-pruned | 0.81 | 2306.56 MiB | 88% | 59.1843 |
| Qwen3.5-4B IQ4_XS | 1.13 | 2627.34 MiB | 76% | 52.9293 |

The winner is unchanged, but the 0.8B hedge is only 0.9237 points behind. That margin should
not be generalized beyond the recorded ARC-Easy proxy: prior maths/tutoring evidence remains a
separate quality gate, and the Wilson intervals from 50 questions overlap substantially.

## Interpretation limits

- These are full **participant-mode** profiler runs on the GCP 2C/4T proxy. Running the same
  local command with `--mode audit` would only relabel the environment; it would not recreate
  an organiser-controlled cloud image, so this record does not do that.
- The ARC-Easy result is an accuracy proxy, not the hidden validation set or judging-panel
  tutoring score.
- GCP exposes no package-temperature sensor. The reports contain `core_temp_c_peak: null` and
  cannot establish absence of a thermal penalty on a physical laptop.
- The accuracy phase can contact Hugging Face metadata services even when its dataset is cached;
  these reports are not an offline-deployment proof.
- Each report retains only the benchmark mean, not the five-element internal timing vector.
  The campaign's reconstructed promotion-screen lane retains its raw timing vectors separately.

## Regeneration

```bash
python -m bench.official_profiler_summary \
  --manifest bench/measurements/campaign-20260819/official-profiler/manifest.json \
  --json bench/measurements/campaign-20260819/official-profiler/summary.json \
  --tsv bench/measurements/campaign-20260819/official-profiler/summary.tsv
```

The dashboard loads this direct-profiler summary as its first campaign panel and keeps the
reconstructed profiler-parity and AVX2/webpage-relative lanes in separate panels.
