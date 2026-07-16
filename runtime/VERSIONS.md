# Pinned versions

Reproducibility is load-bearing: the 9 Aug native extraction must reproduce these exact
binaries (ROADMAP 15 Jul). Fill in and freeze before the target-hardware window.

| Component | Version / pin | Notes |
|---|---|---|
| llama.cpp | dev: prebuilt release **b10035** (commit `602f828b4`), macos-arm64, in `runtime/build/bin` | Target build pins a **commit SHA** built in-container into `runtime/build/bin` with AVX2 flags |
| Base image | `ubuntu:22.04` (digest TBD) | matches the target OS exactly |
| Python | 3.10 (target) / 3.12 (dev) | `requires-python = ">=3.10"` |
| Model | `unsloth/Qwen3-0.6B-GGUF` · `Qwen3-0.6B-Q4_K_M.gguf` | provenance: `Qwen/Qwen3-0.6B` |

## Target build flags (ROADMAP 15 Jul)

Built inside the `linux/amd64` container, **not** with the Homebrew binary used for dev:

```
-DGGML_NATIVE=OFF -DGGML_AVX2=ON -DGGML_AVX512=OFF -DGGML_F16C=ON -DGGML_FMA=ON
```

AVX2 baseline, never AVX-512 (illegal-instruction fault on much of the target field = hard
failure). Confirm ELF x86-64 output with `file`.
