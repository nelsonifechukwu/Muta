# D6 — Phase 0 baselines

Host: Apple M2 Pro (6P+4E), CPU-only build (Metal off, Accelerate BLAS on), llama.cpp `7ba604f`, threads=6 (llama-bench default). NOT the deployment target (x86-64 Ubuntu 8 GB); numbers are the local comparison reference for G2c/G6 only.

`llama-bench -p 512 -n 128`:

| model | size | pp512 tok/s | tg128 tok/s | peak RSS (default ctx) | peak RSS (duo ctx) |
|---|---|---|---|---|---|
| SmolLM2-135M-Instruct Q4_K_M (front) | 98.87 MiB | 2596.34 +/- 210.11 | 441.38 +/- 53.93 | 362 MiB | 272 MiB (`-c 4096`) |
| Qwen3.5-4B Q4_K_M (expert) | 2.54 GiB | 105.11 +/- 5.41 | 26.63 +/- 0.63 | 6.19 GiB | 5.31 GiB (`-c 8192`) |

Peak RSS via `/usr/bin/time -l` on a `llama-completion -no-cnv -n 128` run (macOS deviation from the plan's `-v`).

Notes:
- Decode-speed ratio front:expert = ~16.6x — the economic basis for routing/co-drafting.
- Expert RSS exceeds its weights by ~2.8 GiB; attributed to the BLAS path dequantizing large matmul operands to F32 in compute buffers (largest: 2560x248320 output projection ~2.5 GB f32). The deployment build (no Accelerate) will not show this; treat G7's absolute numbers with that caveat and re-verify on target hardware.
