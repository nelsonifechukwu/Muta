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
