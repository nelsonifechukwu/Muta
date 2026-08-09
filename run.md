# Running the DUO PoC

All commands from the repo root. Binaries land in `llama.cpp/build/bin/`.

## 0. One-time setup

Build llama.cpp (flags below are what this Mac needs — see `docs/DISCOVERY.md` D2 for why):

```bash
cmake -S llama.cpp -B llama.cpp/build \
  -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF -DGGML_METAL=OFF \
  -DCMAKE_OSX_ARCHITECTURES=arm64 -DGGML_NATIVE=OFF \
  -DGGML_CPU_ARM_ARCH=armv8.5-a+dotprod+i8mm+fp16 \
  -DLLAMA_OPENSSL=OFF \
  -DCMAKE_CXX_FLAGS="-nostdinc++ -isystem /Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/include/c++/v1"
cmake --build llama.cpp/build -j --target llama-duo llama-completion llama-bench llama-tokenize
```

Two bundles exist: `bundle/muta-duo.gguf` (SmolLM2-135M front + Qwen3.5-4B expert) and `bundle/muta-duo-q.gguf` (Qwen3.5-0.8B front, same-family - much higher verify-mode acceptance; see bench/results.md). Pass either via `--bundle`.

Pack the two models into one bundle (only needed if `bundle/muta-duo.gguf` is missing):

```bash
source .venv/bin/activate
python3 scripts/pack_bundle.py --out bundle/muta-duo.gguf \
  --model models/SmolLM2-135M-Instruct-Q4_K_M.gguf:m0.:front \
  --model models/Qwen3.5-4B-Q4_K_M.gguf:m1.:expert
python3 scripts/verify_bundle.py bundle/muta-duo.gguf models/*.gguf   # optional byte-level check
```

## 1. Chat with it

With no `-p` / `--prompts-file`, llama-duo reads chat turns from stdin: type at the `>` prompt, enter to send, `/exit` or Ctrl-D to quit. History persists for the whole session.

```bash
# router mode (default): easy -> 135M front, hard -> 4B expert, auto-escalation mid-answer
llama.cpp/build/bin/llama-duo --bundle bundle/muta-duo.gguf --quiet

# clean chat: add --no-trace to hide the [seg]/[turn] stat lines and just see responses
llama.cpp/build/bin/llama-duo --bundle bundle/muta-duo.gguf --quiet --no-trace

# codraft: both models co-author every answer, switching at sentence boundaries
llama.cpp/build/bin/llama-duo --bundle bundle/muta-duo.gguf --mode codraft --quiet

# random: models take over at random word boundaries (mid-sentence allowed);
# author drawn per segment with P(front)=--p-front, P(expert)=1-p; length from [seg-min, seg-max]
llama.cpp/build/bin/llama-duo --bundle bundle/muta-duo.gguf --mode random --p-front 0.7 --seg-min 8 --seg-max 24 --quiet

# verify: speculative-style co-decoding - the front drafts, the expert approves/corrects
# every span in batched forward passes (expert-anchored accuracy; speed depends on how
# often the pair agrees - see bench/results.md "verify mode" notes)
llama.cpp/build/bin/llama-duo --bundle bundle/muta-duo.gguf --mode verify --quiet
```

### What you see

Tokens stream live, color-coded by author: **cyan = front (135M), yellow = expert (4B)** — model switches are visible in real time. When stdout is not a terminal, `[front]`/`[expert]` tags replace the colors. Dim `[[conf-cut -Nch]]` / `[[draft discarded; expert restarts]]` markers show confidence-trigger retractions as they happen (router mode). The `[seg]`/`[turn]` lines on stderr add per-segment stats (author, tokens, tok/s, mean logprob, cut reason); `--no-trace` hides them for a clean chat.

## 2. One-off runs (no chat loop)

```bash
# single question per mode
llama.cpp/build/bin/llama-duo --bundle bundle/muta-duo.gguf --mode router  -p "Solve 3x + 5 = 20 and explain each step."
llama.cpp/build/bin/llama-duo --bundle bundle/muta-duo.gguf --mode codraft -p "Explain Newton's second law with an example."
llama.cpp/build/bin/llama-duo --bundle bundle/muta-duo.gguf --mode random --p-front 0.5 -p "Explain why the sky is blue."

# scripted multi-turn (one user message per line)
llama.cpp/build/bin/llama-duo --bundle bundle/muta-duo.gguf --prompts-file bench/prompts/easy.txt

# routing scores only (no answers; tab-separated "score<TAB>prompt")
llama.cpp/build/bin/llama-duo --bundle bundle/muta-duo.gguf --route-only --prompts-file bench/prompts/hard.txt
```

One-off runs do not stream by default (keeps captured output clean); add `--stream` to watch them live.

## 3. Flags

| flag | default | what it does |
|---|---|---|
| `--mode router\|codraft\|random\|verify` | router | routing / sentence-boundary co-drafting / random co-decoding / expert-verified drafting |
| `--hard-mode expert\|verify` | expert | router: how hard-routed prompts are answered |
| `--draft N` / `--draft-max N` | 16 / 24 | verify: adaptive front draft length |
| `--repair-min N` | 12 | verify: expert repair span after a rejection (doubles on consecutive rejects) |
| `--verify-rule logprob\|greedy` / `--accept-threshold F` | logprob / −3.0 | verify: acceptance test for drafted tokens |
| `--p-front F` / `--p-expert F` | 0.5 / 1−p_front | random mode: probability each segment's author is front/expert (validated to sum to 1) |
| `--seg-min/--seg-max N` | 24/96 | segment budgets; in random mode, bounds of each segment's random length |
| `--seg-min-expert/--seg-max-expert N` | same | codraft only: expert-specific budgets (small = faster, large = higher quality) |
| `--carry-draft` | off | router: on escalation the expert continues the front's draft instead of restarting (much faster) |
| `--route-threshold F` | 0.0 | routing cutoff; lower = escalate to expert more often (0.0 measured best: 87.5%) |
| `--conf-window N` / `--conf-threshold F` | 16 / −2.5 | mean-logprob window and trigger; threshold closer to 0 = front gives up sooner |
| `--closer expert\|either` | expert | whether the expert must sign off before a co-draft/random answer can end |
| `--temp-front/--temp-expert F` | 0.7/0.6 | sampling temperatures (`--top-p-front/-expert` too) |
| `--ctx-front/--ctx-expert N` | 4096/8192 | context sizes |
| `-t N` | math cores | threads |
| `-n N` | 1024 | per-answer token cap |
| `--seed N` | 42 | sampling AND random-mode switching pattern (reproducible runs) |
| `--stream` / `--no-stream` | auto | live token output; auto = on in chat, off for `-p`/`--prompts-file` |
| `--quiet` | off | suppress library logs (traces stay) |
| `--no-trace` | off | suppress `[seg]`/`[turn]` trace lines |
| `--json-trace FILE` | off | mirror traces as JSON lines |
| `--route-only` | off | print routing scores only, do not answer |
| `--selftest-seams` | off | after each codraft/random turn, verify tokenization seams byte-exactly |

`llama-duo -h` prints the full list.

## 4. Benchmarks and gates

```bash
bash scripts/bench_duo.sh              # G3 routing sweep + G6/G7 perf+RSS matrix -> bench/.runs/
```

Results and analysis live in `bench/baseline.md`, `bench/results.md`, `docs/POC_REPORT.md`.

## 5. Loading a single model from the bundle (patched llama.cpp)

Any patched tool takes `--bundle-prefix` (`m0.` = front, `m1.` = expert):

```bash
llama.cpp/build/bin/llama-completion -m bundle/muta-duo.gguf --bundle-prefix m1. -p "hello" -n 32
llama.cpp/build/bin/llama-bench      -m bundle/muta-duo.gguf --bundle-prefix m0. -p 512 -n 128
```
