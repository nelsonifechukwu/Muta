# Pinned versions

Reproducibility is load-bearing: the 9 Aug native extraction must reproduce these exact
binaries (ROADMAP 15 Jul). Fill in and freeze before the target-hardware window.

| Component | Version / pin | Notes |
|---|---|---|
| llama.cpp | **b10035** (commit `602f828b4`) | dev on macOS: prebuilt release, arm64, in `runtime/build/bin`. Container: built from source at this tag by `docker/dev.Dockerfile` (`ARG LLAMA_CPP_REF`) into the same path. Verified in-image: `version: 1 (602f828)`, `GNU 11.4.0 for Linux x86_64` |
| Base image | `ubuntu:22.04` (digest TBD) | matches the target OS exactly |
| Python | 3.10 (target) / 3.12 (dev) | `requires-python = ">=3.10"` |
| Model | `unsloth/Qwen3-0.6B-GGUF` · `Qwen3-0.6B-Q4_K_M.gguf` | provenance: `Qwen/Qwen3-0.6B` |

## Target build flags (ROADMAP 15 Jul) — implemented

Built inside the `linux/amd64` container, **not** with the prebuilt binary used for dev.
Live in `docker/dev.Dockerfile` stage 1:

```
-DGGML_NATIVE=OFF -DGGML_AVX2=ON -DGGML_AVX512=OFF -DGGML_F16C=ON -DGGML_FMA=ON
```

AVX2 baseline, never AVX-512 (illegal-instruction fault on much of the target field = hard
failure). `LLAMA_CURL=OFF` additionally drops the `-hf` puller and libcurl: the target is
offline and `runtime/models.py` provisions weights itself.

Both facts are **asserted at build time**, so a wrong-ISA binary can never reach the flash
drive — `file` must report x86-64 ELF, and the disassembly must contain no AVX-512 mnemonics.
The build fails otherwise. Verifying on the target box would be too late.
