# DUO PoC — Discovery (Phase 0 ground truth)

## D1 — Tree recency & Qwen3.5 support

- llama.cpp commit: `7ba604f1cb61cd14898138e9abc0b4ff2601f180` (Sun Aug 9 00:42:50 2026 +0200), shallow clone, clean tree.
- Qwen3.5: `LLM_ARCH_QWEN35` / `LLM_ARCH_QWEN35MOE` in `src/llama-arch.h:46-47`; arch strings `"qwen35"` / `"qwen35moe"` (`src/llama-arch.cpp:41-42`). Gated-DeltaNet implementation: `src/models/qwen35.cpp`, `src/models/delta-net-base.cpp` (+ `qwen3next.cpp`, `kimi-linear.cpp` sharing SSM tensor plumbing: `LLM_TENSOR_SSM_ALPHA/BETA`, `llama-arch.h:476,483`).
- `models/Qwen3.5-4B-Q4_K_M.gguf` header contains `general.architecture` = `qwen35` (byte-level peek; full dump in D4). Go.

## D2 — Build

- Host: macOS (Darwin 25.5.0), Apple Silicon (arm64), AppleClang 21.0.0. NOT the deployment target (x86-64 Ubuntu); all perf numbers here are comparative.
- Configure: `cmake -S llama.cpp -B llama.cpp/build -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF -DGGML_METAL=OFF -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_CXX_FLAGS="-nostdinc++ -isystem /Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/include/c++/v1"` (see WORKLOG for why the last two flags exist).
- Targets: llama-cli, llama-bench, llama-tokenize, llama-quantize, plus llama-completion (added — see D3).
- Result: all built after three toolchain fixes (broken CLT libc++ shadow dir, Rosetta cmake `-mcpu=native` probe misfire, x86_64 Homebrew OpenSSL unlinkable into arm64 → `-DLLAMA_OPENSSL=OFF`). Full detail in WORKLOG.
- Final configure: `cmake -S llama.cpp -B llama.cpp/build -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF -DGGML_METAL=OFF -DCMAKE_OSX_ARCHITECTURES=arm64 -DGGML_NATIVE=OFF -DGGML_CPU_ARM_ARCH=armv8.5-a+dotprod+i8mm+fp16 -DCMAKE_CXX_FLAGS="-nostdinc++ -isystem /Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/include/c++/v1" -DLLAMA_OPENSSL=OFF`

## D3 — Model smoke tests

Tool note: this tree's `llama-cli` is a new full-screen UI; with `-p ... -no-cnv` and stdin at EOF it busy-spins at 100% CPU inside `console::readline` (sampled the stuck process to confirm). Deviation: use **`llama-completion`** (old-style tool, built additionally) for all scripted/deterministic runs; `llama-cli -st` also exists but llama-completion is the cleaner instrument. `-no-cnv` on llama-completion gives raw un-templated completion — that is the identity-gate mode for G1/G2b.

- Front (`--temp 0 --seed 42 -n 48`): "Photosynthesis is a process used by plants, algae, and some bacteria to convert light energy into chemical energy, which is then used to produce glucose, a type of sugar, from carbon dioxide." Loads, coherent. PASS.
- Expert (same flags): emits `<think>\n\n</think>` then "Photosynthesis is the biological process by which plants, algae, and some bacteria convert light energy into chemical energy, transforming carbon dioxide and water into glucose and oxygen." Loads, coherent. PASS.
- Phase-3 note: the expert's template auto-opens a think block; co-draft/router prompt construction must account for it (close it or keep it empty when continuing shared answers).

## D4 — Metadata

Full dumps: `docs/meta-front.txt`, `docs/meta-expert.txt`. Extract:

| | front: SmolLM2-135M-Instruct Q4_K_M | expert: Qwen3.5-4B Q4_K_M (Unsloth) |
|---|---|---|
| `general.architecture` | `llama` | `qwen35` |
| `general.alignment` | absent (default 32) | absent (default 32) |
| GGUF version / tensors / KVs | 3 / 272 / 33 | 3 / 426 / 46 |
| block_count / context_length | 30 / 8192 | 32 / 262144 |
| embedding / heads / kv-heads | 576 / 9 / 3 | 2560 / 16 / 4 |
| vocab size | 49152 | 248320 (tokens array) |
| tokenizer.ggml.model / .pre | `gpt2` / `smollm` | `gpt2` / `qwen35` |
| chat template | ChatML (`tokenizer.chat_template` present) | ChatML-family Unsloth template (has image/video namespace preamble; text path is ChatML) |
| BOS / EOS ids | bos=1 (`<|im_start|>`), eos=2 (`<|im_end|>`), add_bos=False | eos=248046, pad=248055, no bos key |
| hybrid-SSM keys | none (dense llama) | `qwen35.ssm.{conv_kernel=4,state_size=128,group_count=16,time_step_rank=32,inner_size=4096}`, `full_attention_interval=4` |

Implications recorded: expert vocab is 248k (plan assumed ~152k — only affects logprob softmax cost, negligible); both models little-endian; expert is hybrid (3 of 4 layers Gated-DeltaNet) confirming the append-only/no-partial-rewind constraint (plan T12).

## D5 — Verdict-token probe (SmolLM2)

First candidate pair wins: `" A"` -> token **330**, `" B"` -> token **389** (each exactly one token, via `llama-tokenize --ids --no-bos`). Backups also single-token: bare `"A"`/`"B"` = 49/50, `" yes"`/`" no"` = 9805/787. `" 1"`/`" 2"` are two tokens each (rejected).

## D6 — Baselines

See `bench/baseline.md`. Headline: front 2596/441 tok/s (pp512/tg128), expert 105/26.6 tok/s; front:expert decode ratio ~16.6x. Peak RSS at duo contexts: front 272 MiB (`-c 4096`), expert 5.31 GiB (`-c 8192`, ~2.8 GiB of it is BLAS F32 dequant compute buffers — mac-specific, see baseline.md note).

## Phase 0 gate results

- Both models load and generate coherent text (D3): PASS
- DISCOVERY.md complete (D1-D5): PASS
- bench/baseline.md exists (D6): PASS

## S0 — Streaming ground truth (Phase 5)

Task A1 (S0.1): container gate environment + disk-bandwidth ground truth for
`docs/STREAMING_IMPL_PLAN.md`. All numbers below measured 2026-08-12 from the
`pilot/v2` worktree; llama.cpp tree unchanged at `master @ 01f58cd`.

### Environment

- Host: Docker Desktop 29.1.3, native **aarch64** linuxkit VM.
- In-container `uname -r`: `6.12.54-linuxkit`; `uname -m`: `aarch64`.
- `getconf PAGESIZE`: **4096** (the VM's page size — NOT the M2 Pro host's native
  16 KiB; every alignment/range-table calculation in later phases must use 4096,
  not the host's `getconf PAGESIZE`).
- THP (`/sys/kernel/mm/transparent_hugepage/enabled`): `[always] madvise never` —
  THP is ON by default in this VM. Confirms R9 (STREAMING_PLAN.md risks table):
  streamed mappings need explicit `MADV_NOHUGEPAGE` or THP will coarsen eviction
  granularity above the page-table level.
- Image: `muta-stream` built from `scripts/Dockerfile.streaming`
  (`ubuntu:22.04` + `build-essential cmake git sysstat time python3
  ca-certificates`, `--no-install-recommends`). `cmake --version` in-image:
  3.22.1. `gcc --version`: 11.4.0.
- Volumes: `muta-build` (cmake build tree), `muta-models` (mid-tier model, +
  `bundle/muta-trio.gguf` once it exists — task A4). Neither existed before this
  task; both created idempotently by `scripts/stream_env.sh`.

### D — disk bandwidth (the ledger's D)

Methodology: `scripts/stream_env.sh drop_caches` (privileged `sync; echo 3 >
/proc/sys/vm/drop_caches` inside the VM) immediately before each cold read;
`dd if=<4B model> of=/dev/null bs=1M` via `scripts/stream_env.sh cgrun 2048m
<dd...>` (named-container wrapper, `--memory=2048m --memory-swap=2048m
--cpus=6 --cgroupns=private`). Full file each run: `Qwen3.5-4B-Q4_K_M.gguf`,
2,740,937,888 bytes.

| # | path | iflag | MB/s (decimal) | GiB/s | memory.peak | notes |
|---|---|---|---|---|---|---|
| (a) | `muta-models` volume | `direct` | **2977.0** | 2.77 | 5,681,152 B (5.4 MiB) | cold (post drop_caches); tiny memory.peak confirms O_DIRECT bypasses the page cache — the design's core assumption |
| (b) | repo bind-mount (virtiofs) | `direct` | 2901.9 | 2.70 | 5,959,680 B (5.7 MiB) | cold (post drop_caches); **O_DIRECT was accepted on virtiofs, not rejected** — see deviation below |
| (c1) | `muta-models` volume | (buffered) | 1963.5 | 1.83 | 2,147,483,648 B (== the 2048 MiB cap, exactly) | cold, 1st run — page cache fills to the cgroup's memory.max and gets reclaimed; **not OOM-killed** (`OOMKilled=false`) |
| (c2) | `muta-models` volume | (buffered) | **7188.3** | 6.69 | 605,110,272 B (577 MiB) | 2nd run, fresh container — cached ceiling; fast because the VM's page cache (shared across containers, per-inode) is already warm from (c1) |

**The ledger's D is (a): 2977 MB/s (≈2.77 GiB/s), volume + O_DIRECT, cold.** This
is the number every later S0/S1 latency prediction (`t_verify ≈ (S−R)/D`, the
Milestone-A `1.3–1.9 tok/s` envelope, G9's ±30% check) should use. It is an
emulated-aarch64-on-Apple-Silicon number, not the x86 ADTC target — same caveat
DISCOVERY.md's D2 already carries for compute.

Deviation vs plan: STREAMING_IMPL_PLAN.md's verified-ground-truth section states
bind mounts are "the wrong IO class for gates" for O_DIRECT, hence models go on
a named volume — confirmed as the right design choice (that's still why (a), not
(b), is the ledger's D), but the *reason* needs a correction: it is **not**
that O_DIRECT is rejected on virtiofs in this Docker Desktop version (29.1.3) —
`dd iflag=direct` succeeded on the bind mount at (b) and both cold numbers are
close to each other and far below the (c2) cached ceiling, which is itself
evidence the virtiofs read really did bypass cache rather than silently
falling back to buffered I/O against an already-warm host-side cache. The
volume is still preferred for gates because it is the VM-native block path
(no host-macOS caching layer to reason about at all), not because direct I/O
is unavailable on the bind mount.

Also notable: (c1)'s `memory.peak` landing on *exactly* 2,147,483,648 bytes
(2048 MiB, the container's own `--memory` cap) with `OOMKilled=false` is a
direct, gate-grade confirmation that page-cache charges under cgroup v2 are
reclaimed under pressure rather than triggering OOM — the mechanism the whole
evict-via-`fadvise` design (STREAMING_PLAN.md's core design) depends on to be
survivable even before the residency manager exists.

### cgrun harness self-test

`scripts/stream_env.sh cgrun` was validated both ways before being trusted for
the D runs above:
- Normal exit: `cgrun 256m echo hello-from-cgrun` → `exit_status=0
  OOMKilled=false`, `memory.peak=5,419,008 B`, container removed after.
- OOM path: `cgrun 64m python3 -c "bytearray(300*1024*1024)"` → killed by the
  kernel OOM killer inside the cgroup, `exit_status=137`,
  `memory.peak=67,108,864 B` (== the 64 MiB cap, exactly), **`OOMKilled=true`**
  correctly reported via `docker inspect -f '{{.State.OOMKilled}}'` on the
  named (non-`--rm`) container before it is `docker rm`'d.

### Build: streaming-gate llama.cpp targets (`scripts/stream_env.sh build`)

Configured once (idempotent re-configure into the `muta-build` volume) with
`-DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF -DGGML_BLAS=OFF -DGGML_NATIVE=OFF
-DGGML_CPU_ARM_ARCH=armv8.5-a+dotprod+i8mm+fp16 -DLLAMA_BUILD_EXAMPLES=ON`
(the last flag is required — `llama-speculative-simple` lives under
`examples/`, only added to the build when `LLAMA_BUILD_EXAMPLES=ON`), built
`-j8` with GNU make `-k` (keep-going) so one broken target does not block the
rest.

Target names matched the brief exactly (`llama-completion`, `llama-duo`,
`llama-bench`, `llama-speculative-simple`) — no renaming needed.

- **`llama-completion`, `llama-bench`, `llama-speculative-simple`: build and
  run clean** (`--version`/`--help` smoke-tested in-container; version string
  confirms `GNU 11.4.0 for Linux aarch64`).
- **`llama-duo`: FAILS to compile under GCC on this Ubuntu 22.04 image** —
  `tools/duo/duo.cpp:170-172`, `va_start`/`va_end` used in `jtrace()` without
  including `<cstdarg>`. It compiles on macOS (AppleClang/libc++) only because
  some other transitively-included header happens to pull in the declaration
  there — a latent portability bug the plan's environment change (Linux/GCC
  gate container) surfaced for the first time; `llama.cpp/build/bin/llama-duo`
  (existing macOS build, untouched) runs fine. **Not fixed in this task**: task
  A1 is explicitly environment/measurement-only and the working instructions
  for this task forbid touching llama.cpp's git or leaving its tree dirty
  while A2-A4 may run in parallel against the same clean `01f58cd` checkout.
  The one-line fix (`#include <cstdarg>`) belongs on the `streaming` branch in
  a later task, logged here so it isn't lost.

### macOS `build-noblas` (BLAS off, dev-loop reference build)

`llama.cpp/build-noblas` configured with the full macOS flag set from Global
constraints plus `-DCMAKE_BUILD_TYPE=Release -DGGML_BLAS=OFF`; only
`llama-completion` built (per task scope). Existing `llama.cpp/build` (BLAS
on) left untouched — verified via `git -C llama.cpp status` showing a clean
tree before and after, and by re-`file`-checking `llama.cpp/build/bin/llama-completion`
unchanged (still `Mach-O 64-bit executable arm64`).

Verification:
- `CMakeCache.txt`: `GGML_BLAS:BOOL=OFF` (vs `ON` in the untouched `build/`
  cache) — confirmed by direct diff of both caches.
- The `ggml-blas` backend subdirectory is only added to the build graph when
  `GGML_BLAS` is `ON` (`ggml/src/CMakeLists.txt`); `build-noblas`'s tree has
  **no `ggml/src/ggml-blas/` directory at all** — the BLAS `cblas_sgemm` path
  (the thing that actually F32-dequants the tied head into a ~2.5 GiB
  transient, per Global constraints) is not merely disabled, it is not
  compiled in.
- `-framework Accelerate` **is** present in `ggml-cpu`'s link line. This is
  expected and harmless: it comes from the separate `GGML_ACCELERATE` CMake
  option (`ggml/CMakeLists.txt`), which defaults `ON` on Apple platforms
  independently of `GGML_BLAS` and only gates `GGML_USE_ACCELERATE`-conditioned
  vDSP vector-op acceleration inside the CPU backend — not the `ggml-blas`
  backend's whole-matrix BLAS offload that requires the F32 conversion. Net:
  "GGML_BLAS is OFF" (the brief's verification criterion) holds; Accelerate
  linkage without the BLAS backend does not reintroduce the risk.
- `llama.cpp/build-noblas/bin/llama-completion`: builds, is a genuine
  `Mach-O 64-bit executable arm64` (not an accidental x86_64/Rosetta build —
  same trap DISCOVERY.md's D2 already documents), `--version`/`--help` run
  clean. (The binary's own `--version` string prints "for Darwin x86_64" —
  a pre-existing cosmetic-only quirk in the version banner's host-arch string,
  unrelated to the actually-compiled target arch; not a build defect.)

### models volume

`scripts/stream_env.sh models` copied `models/Qwen3.5-4B-Q4_K_M.gguf`
(2,740,937,888 bytes, sha256 `00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4`
inside the volume) into `muta-models`; `bundle/muta-trio.gguf` does not exist
yet (created in task A4) and was correctly skipped, by design, rather than
erroring. `models/` on the host was only ever bind-mounted read-only.

**Verdict: the container gate environment is real and load-bearing** — cgroup
v2 memory accounting behaves exactly as STREAMING_PLAN.md's design assumes
(page cache charged and reclaimed, not OOM-killing; O_DIRECT reads leave
almost no charge), `D = 2977 MB/s` is the number for every later prediction,
and the one build gap found (`llama-duo`/GCC) is scoped and deferred rather
than silently absent.
