---
license: apache-2.0
base_model: Qwen/Qwen2.5-1.5B-Instruct
pipeline_tag: text-generation
language:
  - en
tags:
  - gguf
  - llama-cpp
  - lora
  - education
  - mathematics
  - science
---

# Muta Tutor Qwen2.5 1.5B Q4_K_M

This is the vector-configuration finalist from Muta's ADTC fine-tuning campaign. It starts from
`Qwen/Qwen2.5-1.5B-Instruct`, applies BF16 LoRA with rank 16 for 500 steps on a licence-clean
multiple-choice math and science mixture, merges the adapter, and exports the result as Q4_K_M
GGUF.

## File

`Muta-Tutor-Qwen2.5-1.5B-Q4_K_M.gguf`

SHA-256: `a750d00d458c6ab38925364ea1413db00648449180941e47025736d09922e1eb`

```bash
hf download timiiowolabi/Muta-Tutor-Qwen2.5-1.5B-ADTC-GGUF \
  Muta-Tutor-Qwen2.5-1.5B-Q4_K_M.gguf
```

## Evaluation

The candidate and untuned control were evaluated with the same GGUF conversion, quantization,
prompt format, and GCP CPU-proxy harness.

| Measure | Control | Fine-tuned |
|---|---:|---:|
| ARC-Easy acc_norm, 500 samples | 74.4% | 77.8% |
| Scalar total score | 65.3277 | 67.0475 |
| Vector total score | 82.4386 | 84.1387 |

The repository includes the training manifest, licence-clean dataset manifest, artifact hashes,
and the full fine-tuning summary. Performance was measured on a cloud CPU proxy; temperature was
unavailable, and peak RSS includes a 45 MiB estimate for the profiler root process. The secondary
held-out battery is pending because its first attempt overlapped unrelated CPU work and was
discarded.

## Status

This remains a competition candidate. It still requires Muta's final embedded tutor template,
live tutoring validation, the secondary held-out battery, and profiling on the physical target
laptop.
