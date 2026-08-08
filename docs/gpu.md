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

## Metal (Apple Silicon) — supported today

Docker on macOS has no GPU passthrough, so Metal means **native mode**:

```sh
./run.sh --native        # db + frontend in docker; gateway + Metal llama-server on host
./run.sh --native --cpu  # same, forced CPU (measurement baselines)
```

Native mode auto-exports `MUTA_RT_N_GPU_LAYERS=all` on Darwin/arm64 unless you set the
variable yourself or pass `--cpu`. The pinned b10035 `macos-arm64` release that
`run.sh` fetches into `runtime/build/bin/` ships with Metal (`libggml-metal`); the
`llama-server` on PATH at `/usr/local/bin` is an unpinned x86 build — never use it for
numbers. Both CORE-TEXT and CORE-VISION offload; measured results live in RESULTS.md
(`native` context).

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
