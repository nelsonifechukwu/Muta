---
license: apache-2.0
base_model: Qwen/Qwen3.5-0.8B
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

# Muta Tutor Qwen3.5 0.8B Q4_0

This is the scalar-configuration finalist from Muta's ADTC fine-tuning campaign. It starts from
`Qwen/Qwen3.5-0.8B`, applies BF16 LoRA with rank 16 for 400 steps on multiple-choice math and
science training data, merges the adapter, and exports the result as Q4_0 GGUF.

## File

`Muta-Tutor-Qwen3.5-0.8B-Q4_0.gguf`

SHA-256: `552de22f7ea6f161a458985900e2c961d7578baa1ea9c23018ae27151623ff26`

```bash
hf download timiiowolabi/Muta-Tutor-Qwen3.5-0.8B-ADTC-GGUF \
  Muta-Tutor-Qwen3.5-0.8B-Q4_0.gguf
```

## Evaluation

The candidate and its zero-learning-rate export control were evaluated with the same GGUF
conversion, quantization, prompt format, and GCP CPU-proxy harness.

| Measure | Control | Fine-tuned |
|---|---:|---:|
| ARC-Easy acc_norm, 500 samples | 55.2% | 70.2% |
| Scalar total score | 72.8896 | 80.3664 |
| Vector total score | 74.8959 | 82.3962 |

Held-out checks improved from 32% to 42% on ARC-Challenge-100, 32% to 33% on
OpenBookQA-100, and 16% to 20% on GSM8K-25.

The repository includes the training manifest, dataset manifest, artifact hashes, and the full
fine-tuning summary. Performance was measured on a cloud CPU proxy; temperature was unavailable,
and peak RSS includes a 45 MiB estimate for the profiler root process.

## Status

This remains a competition candidate. It still requires Muta's final embedded tutor template,
live tutoring validation, and profiling on the physical target laptop.
