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

### S0.2 — Model geometry

Task A2 (S0.2): per-layer/head byte tables for the streaming residency
manager's ledger, produced by `scripts/layer_sizes.py`
(`.venv/bin/python scripts/layer_sizes.py`, no args = the three pinned
models + `bundle/muta-duo-q.gguf`) via `GGUFReader` from this tree's
`llama.cpp/gguf-py`. Every number below cross-checks exactly against the
plan's independently-measured expectations (`docs/STREAMING_IMPL_PLAN.md:28`).

**`ReaderTensor.data_offset` semantics (verified empirically, not assumed):**
it is already the tensor's **absolute** file offset, not header-relative —
`gguf_reader.py:339` computes `data_offs = start_offs + offset_tensor[0]`
inside `_build_tensors`, where `start_offs` is `GGUFReader.data_offset` (the
aligned start of the data section) — the addition already happened inside
the reader. Confirmed on all four inputs: `min(t.data_offset for t in
reader.tensors) == reader.data_offset` exactly, and `max(t.data_offset +
t.n_bytes) == file size on disk` exactly (zero trailing slack in every
case). So the correct absolute offset is `tensor.data_offset` used as-is —
adding `reader.data_offset` to it again would double-count the header.

#### (a) Summary

| model | total bytes | n_layers | blk total MiB | b_layer min/avg/max MiB | token_embd MiB (quant) | output.weight? | output_norm bytes |
|---|---|---|---|---|---|---|---|
| SmolLM2-135M-Instruct-Q4_K_M | 105,454,144 | 30 | 70.2 | 2.2 / 2.3 / 2.5 | 28.7 (Q8_0) | no — **TIED** | 2,304 |
| Qwen3.5-0.8B-MTP-Q4_K_M | 549,698,976 | 25 | 314.8 | 9.9 / 12.6 / 14.5 | 198.9 (Q6_K) | no — **TIED** | 4,096 |
| Qwen3.5-4B-Q4_K_M | 2,740,937,888 | 32 | 2106.2 | 57.7 / 65.8 / 70.3 | 497.3 (Q6_K) | no — **TIED** | 10,240 |
| `bundle/muta-duo-q.gguf` `[m0]` (front, 0.8B) | 538,735,872† | 25 | 314.8 | 9.9 / 12.6 / 14.5 | 198.9 (Q6_K) | no — **TIED** | 4,096 |
| `bundle/muta-duo-q.gguf` `[m1]` (expert, 4B) | 2,729,969,664† | 32 | 2106.2 | 57.7 / 65.8 / 70.3 | 497.3 (Q6_K) | no — **TIED** | 10,240 |

† bundle rows: sum of that prefix group's tensor bytes (payload bytes, not
a whole-file size — the two groups share one file).

All five confirm STREAMING_IMPL_PLAN.md's independently-measured numbers
exactly: 4B `token_embd` 497.3 MiB, blk total 2106.2 MiB, 32 layers,
per-layer 57.7–70.3 MiB, tied head; 0.8B embd 198.9 MiB, blk 314.8 MiB, 25
layers, tied; SmolLM2 embd 28.7 MiB, blk 70.2 MiB, 30 layers, tied. **No
`output.weight` tensor exists anywhere** — all five are tied-embedding
heads, confirming the plan's "HEAD pseudo-layer" design (`token_embd` must
be treated as the logits matmul's weight, not excluded as a pure
embedding-lookup table). The bundle's per-group byte totals are
bit-identical to their standalone counterparts (same per-layer, embd, and
norm byte counts) — a second, independent confirmation of Phase 1/G1's
lossless-repack result, this time via file geometry rather than hashing.

Bundle payload intervals (per-prefix, `[min data offset, max offset+len)`):
`m0` `[21,934,464, 560,670,336)` (513.8 MiB span — matches 314.8 blk + 198.9
embd + small misc), `m1` `[560,670,336, 3,290,640,000)` (2603.5 MiB span).
The two intervals are contiguous with the header's data-section start
(21,934,464) and the file's end (3,290,640,000), and `m0`'s interval ends
exactly where `m1`'s begins — no gap, no overlap between the two packed
sub-models.

#### (b) Per-layer table — 4B (`Qwen3.5-4B-Q4_K_M.gguf`; bundle `[m1]` byte-identical, only offsets differ)

| layer | MiB | layer | MiB | layer | MiB | layer | MiB |
|---|---|---|---|---|---|---|---|
| 0 | 70.3 | 8 | 64.5 | 16 | 64.5 | 24 | 70.3 |
| 1 | 70.3 | 9 | 70.3 | 17 | 64.5 | 25 | 64.5 |
| 2 | 70.3 | 10 | 64.5 | 18 | 70.3 | 26 | 64.5 |
| 3 | 64.1 | 11 | 58.3 | 19 | 57.7 | 27 | 64.1 |
| 4 | 64.5 | 12 | 70.3 | 20 | 64.5 | 28 | 70.3 |
| 5 | 64.5 | 13 | 64.5 | 21 | 70.3 | 29 | 70.3 |
| 6 | 70.3 | 14 | 64.5 | 22 | 64.5 | 30 | 70.3 |
| 7 | 58.3 | 15 | 64.1 | 23 | 57.7 | 31 | 63.5 |

min 57.7 MiB (layers 19, 23), max 70.3 MiB (12 of the 32 layers: 0, 1, 2,
6, 9, 12, 18, 21, 24, 28, 29, 30), avg 65.8 MiB. Six distinct per-layer
sizes appear (70.3 / 64.5 / 64.1 / 58.3 / 57.7 / 63.5 MiB) — consistent
with the plan's note that Qwen3.5-4B mixes GDN (Gated-DeltaNet) and
full-attention layers with different tensor shapes per type
(`docs/STREAMING_IMPL_PLAN.md:28`); this task measured byte sizes only and
did not cross-reference which numeric layer indices are which
architectural type. Every layer's per-tensor extent equals its byte-sum
exactly (`extent/sum = 1.000` on all 32 rows, per `scripts/layer_sizes.py`
output) — each layer's tensors are laid out back-to-back with zero
padding, far inside the 1.05x contiguity threshold.

0.8B (25 layers, 9.9–14.5 MiB) and SmolLM2 (30 layers, 2.2–2.5 MiB) are
identical in kind — also perfectly contiguous (`extent/sum = 1.000` on
every row, zero flags in either) — and are fully captured by the min/avg/max
in (a); their full per-layer rows are in the script's stdout, omitted here
per the task's compact-table guidance.

#### (c) Layer-order monotonicity

**PASS on all five** (three standalone files, two bundle prefix groups):
each layer's minimum tensor offset increases strictly with layer index in
every case, zero exceptions.

#### (d) token_embd position

Not the first tensor in any of the five — `output_norm.weight` (2,304 to
10,240 bytes, a rounding error next to `token_embd`) is written first in
every case, `token_embd.weight` immediately second, then the layer-0
tensors. E.g. 4B: `output_norm.weight` at offset 10,968,224 (10,240 B),
then `token_embd.weight` at 10,978,464 (497.3 MiB), then `blk.0.*` starting
at 10,978,464 + 497.3 MiB. Same pattern in the other four (SmolLM2, 0.8B,
bundle `[m0]`, bundle `[m1]`). Functionally this still satisfies the
plan's "HEAD pseudo-layer, pinned first" intent
(`docs/STREAMING_IMPL_PLAN.md:49`): the tiny norm ahead of it costs a
one-page rounding error, not a real placement problem for a pin-first
policy.

### S0.3 — Eviction semantics probe

Task A3 (S0.3): the go/no-go for the whole streaming design. Standalone C11
probe `scripts/stream_probe.c` (single file, compiles clean with
`-Wall -Wextra` on both Linux/gcc-11.4.0 and macOS/AppleClang-21) that mmaps
the whole 4B model file once (`PROT_READ, MAP_SHARED`, matching llama.cpp's
own strategy) and measures, against three page-aligned 256 MiB regions
(A/B/C at file offsets 512/1024/1536 MiB), whether `madvise(MADV_DONTNEED)`
+ `posix_fadvise(POSIX_FADV_DONTNEED)` actually uncharges cgroup v2
`memory.current` — the primitive the entire residency-manager design
depends on. A post-review fix pass (see `docs/WORKLOG.md` Phase 5 / Task
A3) added step 4b (a chunked-`WILLNEED` discriminator) and a warm guard
before step 5; the numbers below are from that fixed probe's official run,
superseding the first pass.

**Container run (gate-grade)**: `scripts/stream_env.sh drop_caches` then a
fresh `cgrun 3g` (nothing else running), compiling and running in-container
against `/models/Qwen3.5-4B-Q4_K_M.gguf` (2,740,937,888 bytes). Full
`-Wall -Wextra` compile: zero warnings.

| step | before(B) | after(B) | delta(B) | mincore% | ms | rss(KB) | cg_file(B) |
|---|---|---|---|---|---|---|---|
| 1. touch A | 30,003,200 | 299,769,856 | +269,766,656 | 100.0 | 104.3 | 263,560 | 296,054,784 |
| 2. madvise(A,DONTNEED) alone | 299,769,856 | 299,769,856 | +0 | 100.0 | 1.6 | 1,416 | 296,054,784 |
| **3. fadvise(A,DONTNEED) [KEY]** | 299,769,856 | 31,334,400 | **-268,435,456** | 0.0 | 6.3 | 1,416 | 27,619,328 |
| 3b-i. touch B | 31,334,400 | 300,216,320 | +268,881,920 | 100.0 | 104.2 | 263,560 | 296,316,928 |
| 3b-ii. fadvise(B) no madvise first | 300,216,320 | 300,216,320 | +0 | 100.0 | 3.0 | 263,560 | 296,316,928 |
| 3b-iii. madvise(B,DONTNEED) | 300,216,320 | 300,216,320 | +0 | 100.0 | 1.4 | 1,416 | 296,316,928 |
| **3b-iv. fadvise(B,DONTNEED) after madvise** | 300,216,320 | 31,780,864 | **-268,435,456** | 0.0 | 6.3 | 1,416 | 27,881,472 |
| 4. madvise(C,WILLNEED)+poll | 31,780,864 | 32,591,872 | +811,008 | 0.5 | 10,004.0 | 1,612 | 29,257,728 |
| 4b. chunked WILLNEED(2MiB)+poll | 31,281,152 | 199,839,744 | +168,558,592 | 62.5 | 10,007.3 | 1,612 | 195,719,168 |
| **5. MAP_FIXED remap C + fadvise (pre-step residency 100.0%)** | 301,281,280 | 32,845,824 | **-268,435,456** | 0.0 | 8.7 | 1,612 | 28,143,616 |

`memory.peak` for the run: 301,281,280 B. `memory.stat`: `anon 389120`,
`file 28684288`. `OOMKilled=false`, `exit_status=0`, cap=3g (plenty of
headroom; the largest simultaneous working set — A+B+C all partially
resident around step 4b/5 — never exceeds ~590 MiB).

**Step 3 (THE KEY MEASUREMENT)**: `madvise(DONTNEED)` alone leaves
`memory.current` unchanged (Δ=0, page cache still charged, as expected) and
mincore still 100% resident. `posix_fadvise(DONTNEED)` issued *after* that
madvise then uncharges **exactly** -268,435,456 B = -256 MiB = -region,
**100.0% reclaimed**, mincore drops to 0%. Confirms the plan's primitive
works exactly as designed.

**Step 3b (ordering control, region B)**: `fadvise(DONTNEED)` issued
*without* a prior `madvise(DONTNEED)` uncharges **nothing** (Δ=0, mincore
stays 100%) — `invalidate_mapping_pages()` skips pages still mapped into a
process's page tables. Following with `madvise(DONTNEED)` (Δ=0, as step 2
showed) then `fadvise(DONTNEED)` again reclaims the full -268,435,456 B
(100%), byte-identical to step 3. **This proves the PTEs-first ordering
requirement is real and load-bearing**, not a theoretical concern: the
residency manager MUST call `madvise(MADV_DONTNEED)` before
`posix_fadvise(POSIX_FADV_DONTNEED)` on every eviction, or the fadvise is a
silent no-op.

**Step 4 (single WILLNEED prefetch)**: the `madvise(MADV_WILLNEED)` call
itself is non-blocking (0.12 ms), confirming it does not synchronously
block the calling thread (matches R10's expectation). But contrary to the
plan's assumption that this drives an effective background prefetch,
mincore never reached the 95% threshold within the 10 s poll timeout —
only 0.5% resident. **Two different counters, two different deltas, not
interchangeable**: `memory.current` (the gate metric) rose by only
+811,008 B over the step; `memory.stat`'s `file` counter, read from the
*previous* row's 27,881,472 B baseline to this row's 29,257,728 B, rose by
a larger +1,376,256 B. The 565,248 B gap between the two is not a
contradiction — `record_row()` samples `rss`/`memory.stat` *after* it has
already captured the row's own `memory.current` "after" value (and, for
this row specifically, after one extra `mincore_percent()` call in
between), so the two readings are not simultaneous snapshots; in that
extra window some more file-backed readahead landed while a similar amount
of other (mostly transient/anon) charge was concurrently reclaimed,
netting out to a smaller `memory.current` rise than `file`'s. This gap
itself varies run to run (712,704 B in the pre-fix run, 565,248 B here),
consistent with sampling-timing skew rather than a fixed discrepancy —
whereas the **`file` counter's own step-4 delta reproduced exactly**
(+1,376,256 B, identical in both runs), evidence that the single-call
`WILLNEED` readahead window is a fixed, deterministic OS quantity, not
noise.

**Step 4b (chunked-`WILLNEED` discriminator)**: added after review flagged
that a single 256 MiB `WILLNEED` call is not enough evidence to rule
`WILLNEED` out — a per-call readahead cap (`force_page_cache_ra` chunking
against `bdi->io_pages`/`ra_pages`, reset on every fresh `madvise()` call)
predicts the same step-4 data but implies *repeated* small `WILLNEED`
calls would do much better. Region C was evicted to a clean 0.0%-resident
baseline first, then `WILLNEED`'d in 128 calls of 2 MiB each from a second
thread while the main thread polled mincore exactly as in step 4.
**Result: 62.5% resident after the same 10 s window — up from single-call
step 4's 0.5%, a ~120x improvement in the `file`-counter-based prefetch
rate (0.131 MiB/s single-call vs ~15.9 MiB/s chunked) and ~209x in raw
`memory.current` growth (0.077 MiB/s vs ~16.1 MiB/s).** This confirms the
per-call-cap hypothesis: `WILLNEED` is not fundamentally inert, it is
capped per call. But even chunked `WILLNEED` still did not reach the 95%
threshold in 10 s, and its ~16 MiB/s effective rate remains **~150x slower
than an explicit touch** (step 1: 2453.5 MiB/s here; 1.1–2.4 GiB/s across
runs) — at that rate, fully warming one 256 MiB region would take ~16 s,
vastly more than a token-generation budget can spare. **Verdict on
`WILLNEED`: neither "works" nor "fully inert" — chunking it is
measurably, reproducibly better than one big call, but touch/read remains
the mechanism the residency manager should actually use for
ahead-of-decode prefetch; chunked `WILLNEED` is a validated-but-inferior
alternative, not a preferred one.**

**Step 5 (plan-B: `MAP_FIXED` remap + fadvise) — now independently
validated**: a warm guard (`if mincore(C) < 95%: touch(C)`) runs
unconditionally right before step 5's own measurement window, after step
4b (so the WILLNEED measurements above are untouched by it). Step 4b only
reached 62.5%, so the guard's touch fired, bringing C to **100.0%
resident** immediately before step 5's `before`/`after` snapshots — the
printed pre-step residency in the table and verdict block confirms this.
With that precondition genuinely met, step 5 reclaims **exactly
-268,435,456 B = -256 MiB = -region, 100.0%**, byte-identical to step 3.
**The `MAP_FIXED` fallback is now a real, non-confounded pass** — not
needed for this task's verdict (step 3 already passed cleanly), but no
longer an open question either.

**macOS run (informational)**: `cc -std=c11 -O2 -pthread -Wall -Wextra`,
run against `models/Qwen3.5-4B-Q4_K_M.gguf` on the host (AppleClang 21.0.0,
arm64, page size 16384). Fault bandwidth 729.6 MiB/s (step 1). `mincore%`
stays at **100.0 for every single step, including step 4b**, which
therefore *starts* from 100.0% resident (Darwin's `MADV_DONTNEED` never
actually evicted C to begin with) — so 4b's "128 calls, 1.07 ms, mincore
≥95% at 4.35 ms, 58918.3 MiB/s" is not a meaningful prefetch measurement
on this platform, only a restatement that nothing was ever evicted; **this
confirms, again, that `MADV_DONTNEED` is advisory-only on Darwin** — unlike
Linux, it does not unmap or evict anything the kernel can observe via
`mincore`. The single `madvise(MADV_WILLNEED)` call on C (step 4) took
132.41 ms and mincore reached ≥95% at 142.44 ms (prefetch bandwidth 1797.2
MiB/s) — on Darwin the call is effectively synchronous/blocking for this
size (`call ≈ time-to-95%`), the opposite of the container's
non-blocking-but-capped behavior. `posix_fadvise` and cgroup
`memory.current` are both unavailable (`#ifdef __APPLE__` branches print
`SKIPPED`/`n/a` throughout, exactly as specified) — Darwin has no
equivalent whole-file eviction primitive or cgroup-style accounting to
probe.

**VERDICT: PRIMARY** — `madvise(MADV_DONTNEED)` followed by
`posix_fadvise(POSIX_FADV_DONTNEED)`, in that order, uncharges cgroup v2
`memory.current` (step 3: 100.0% of the region reclaimed; step 3b: proves
the ordering is required, not incidental). The streaming design's core
eviction assumption **holds** in the gate-grade container environment. The
`MAP_FIXED` fallback (step 5) is also now independently validated at
100.0% (not needed, since step 3 already passed cleanly, but confirmed
available). Task A3 status: **not blocked** — proceed with
`madvise(DONTNEED)` → `posix_fadvise(DONTNEED)`, strictly in that order,
as the residency manager's eviction primitive; for ahead-of-decode
prefetch, use an explicit touch/read loop, not `MADV_WILLNEED` (chunked or
otherwise) — see step 4b.
