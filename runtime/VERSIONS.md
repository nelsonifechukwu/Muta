# Pinned versions

Reproducibility is load-bearing: the 9 Aug native extraction must reproduce these exact
binaries (ROADMAP 15 Jul). Fill in and freeze before the target-hardware window.

| Component | Version / pin | Notes |
|---|---|---|
| llama.cpp | **b10035** (commit `602f828b4`) | dev on macOS: prebuilt release, arm64, in `runtime/build/bin`. Container: built from source at this tag by `docker/dev.Dockerfile` (`ARG LLAMA_CPP_REF`) into the same path. Verified in-image: `version: 1 (602f828)`, `GNU 11.4.0 for Linux x86_64` |
| Base image | `ubuntu:22.04` · index `sha256:0e0a0fc6d18feda9db1590da249ac93e8d5abfea8f4c3c0c849ce512b5ef8982` · linux/amd64 manifest `sha256:0d779ea97881505f5ef0039336ee85edba27519bdba968c284c86ee066a973c8` (observed 16 Jul 2026) | matches the target OS exactly. **Recorded, not yet enforced** — see below |
| Python | 3.10.12 (container/target) / 3.12 (dev, macOS) | `requires-python = ">=3.10"` |
| Model | `unsloth/Qwen3-0.6B-GGUF` · `Qwen3-0.6B-Q4_K_M.gguf` (396,705,472 B) | provenance: `Qwen/Qwen3-0.6B`. Why this repo and not the one the ROADMAP names: [`docs/smoke-fixture.md`](../docs/smoke-fixture.md) |
| Git SHA | injected at build time via `--build-arg MUTA_GIT_SHA` → `ENV` | the image has no `.git` and no `git` binary; a benchmark number without provenance is unusable in the report (ROADMAP 16 Jul) |

## Base-image pin — recorded now, enforced before 9 Aug

`docker/dev.Dockerfile` still says `FROM --platform=linux/amd64 ubuntu:22.04`, **not** the
digest. Deliberate, and it is a real (small) reproducibility hole until closed:

- Pinning to the digest now freezes out a month of security and toolchain updates during
  active development, and any base drift would surface as a confusing mid-sprint break.
- `CLAUDE.md` schedules the freeze for **before 9 Aug**, which is when reproducibility starts
  being load-bearing: the native extraction must reproduce the container's binaries exactly.

**Action before the target window:** change the `FROM` to
`ubuntu:22.04@sha256:0e0a0fc6…`, rebuild, and re-verify the ISA assertion. Until then, treat
the digest above as *observed*, not *guaranteed*.

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
