# GPU support

The deploy target is CPU (AVX2, pinned b10035) and stays that way — GPU is an
opportunistic dev/deploy accelerator, never a requirement. `./run.sh plan` prints what
this box offers without side effects:

```
host=Darwin/arm64
mode=plan
gpu=metal-native | cuda-available | none
```

## The knob

`MUTA_RT_N_GPU_LAYERS` — `0` (default), an exact layer count, `auto`, or `all` (the
engine's own `-ngl` vocabulary at the b10035 pin). Two things worth knowing:

- At the pin, `-ngl` **defaults to `auto`**: an *unpinned* spawn on a Metal-built binary
  would offload silently. That is why both `runtime/server.py` and the vision spawn
  (`runtime/profiles.py`) always pass the flag explicitly, defaulting to `0`.
- The flag is inert on a CPU-only build (the container's AVX2 engine has no GPU backend),
  so it is always present and always safe.

## Apple Silicon — native mode is the accelerator; Metal measured neutral

Docker on macOS has no GPU passthrough, so GPU experiments mean **native mode**:

```sh
./run.sh --native        # the ~10x path: arm64 engine on the host, CPU
./run.sh --native --gpu  # + Metal offload (experimental; see the measurement below)
```

**Measured 2026-08-08** (RESULTS.md, `native` context, M2 Pro, bare-engine A/B on
Qwen3.5-4B-IQ4_XS at b10035): `-ngl all` assigns all layers to `MTL0` (verified at
`-lv 5`) yet decode is 19–20 tok/s vs CPU's 20–21, prefill even — **neutral to slightly
negative**, most plausibly the hybrid model's recurrent-scan ops falling back per-op.
That is why `--gpu` is an explicit experiment flag, not the native default: the real
speedup is native-vs-emulation itself (~87 vs ~7.6 prefill tok/s, ~20 vs ~5.3 decode).
Re-test when the engine pin moves or the core model stops being a hybrid.

The pinned b10035 `macos-arm64` release that `run.sh` fetches into `runtime/build/bin/`
ships with Metal (`libggml-metal`); the `llama-server` on PATH at `/usr/local/bin` is an
unpinned x86 build — never use it for numbers.

## NVIDIA / CUDA — detected, not yet shipped

`run.sh` detects `nvidia-smi` on Linux and points here. No CUDA image variant exists in
this repo yet because no development box has the hardware to verify one. The recipe when
someone does:

1. Copy `docker/backend.Dockerfile` to `docker/backend.cuda.Dockerfile`; in the
   llama.cpp build stage replace the CPU flags with `-DGGML_CUDA=ON` (keep the pin) and
   base the runtime stage on an `nvidia/cuda` runtime image matching the driver.
2. Add a compose profile:

   ```yaml
   backend-cuda:
     extends: backend
     build: { dockerfile: docker/backend.cuda.Dockerfile }
     profiles: [gpu]
     deploy:
       resources:
         reservations:
           devices:
             - driver: nvidia
               count: 1
               capabilities: [gpu]
   ```

3. Set `MUTA_RT_N_GPU_LAYERS=all` for the service and record measurements in RESULTS.md
   before calling it supported.

Until then, `gpu=cuda-available` is a pointer, not a promise.
