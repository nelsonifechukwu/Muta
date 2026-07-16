# Running Muta

## Start here

```bash
./run.sh
```

That's it. It builds the image if it's missing, fetches the weights if they're missing, boots
the engine, and drops you into a conversation. Runs in Docker by default, because that's
`linux/amd64` — the shape that actually ships.

```bash
./run.sh                          # chat, in Docker                      [default]
./run.sh --native                 # chat, on the host (much faster on a Mac)
./run.sh --serve                  # the HTTP app on :8000, instead of a REPL
./run.sh -- --conversation <id>   # resume a stored thread
./run.sh --help                   # the rest
```

First run in Docker is slow — it compiles llama.cpp and pulls ~378 MB of weights. Both are
cached, so every run after is quick. Conversations persist in `data/muta.sqlite3` and survive
restarts, container rebuilds, and `--rm`.

> **One caveat, and it matters.** The image is `linux/amd64`. On an ARM Mac it runs under QEMU
> emulation, so tokens/sec in the container is **much slower than real and meaningless as a
> measurement** — that's emulation overhead, not the model. `./run.sh --native` is the
> responsive way to chat on a Mac. Per the ROADMAP, every number in the report comes from the
> x86 target box (9-11 Aug); trust neither path here for benchmarks.

The rest of this document is what `./run.sh` does for you, for when you need to do it by hand.

---

## 1. Docker

### Build

```bash
make build          # docker buildx build --platform=linux/amd64 -f docker/dev.Dockerfile -t muta-dev:latest .
```

This compiles llama.cpp from source (pinned to `b10035`, see `runtime/VERSIONS.md`) with the
AVX2 baseline and AVX-512 **off**, then asserts both facts before the image is allowed to
exist. On an ARM Mac the compile is emulated and takes a while — it's cached afterwards.

Why those flags matter: much of the target field (Zen 3, 12th-gen consumer Intel) faults on
AVX-512, and an illegal-instruction fault is a **hard failure — disqualification, not a
deduction**. `GGML_NATIVE=OFF` stops cmake from tuning the build to whatever CPU built it.

### Run

The model is **not** baked into the image (a 378 MB layer on every push, for a file that's
provisioned anyway). Mount it:

```bash
mkdir -p models data
make model                              # first time only: fetch the GGUF into models/

docker run --rm -it \
  -p 8000:8000 \
  -v "$(pwd)/models:/app/models" \
  -v "$(pwd)/data:/app/data" \
  muta-dev:latest
```

Then in another terminal, jump to [Talk to it](#3-talk-to-it).

Mounting `data/` is what makes conversations outlive the container. Drop it and every
`docker run` starts amnesiac.

If `models/` is empty the engine tries to fetch the GGUF itself, which needs network — fine
on your laptop, impossible on the target. Provisioning it up front is the honest rehearsal.

### Useful variations

Any command you pass wins over the app, so the image doubles as the toolbox:

```bash
# gateway only — no engine, no weights needed. /v1/chat returns 503 by design.
docker run --rm -it -p 8000:8000 -e MUTA_NO_ENGINE=1 muta-dev:latest

# tests inside the image
docker run --rm muta-dev:latest python3.10 -m pytest

# poke around
docker run --rm -it --entrypoint bash muta-dev:latest

# the engine's own benchmark (the ceiling this stack is measured against)
docker run --rm -v "$(pwd)/models:/app/models" --entrypoint /app/runtime/build/bin/llama-bench \
  muta-dev:latest -m /app/models/Qwen3-0.6B-Q4_K_M.gguf
```

---

## 2. Native (fastest dev loop)

```bash
python3 -m venv .venv && source .venv/bin/activate
make install
make model                    # fetch the GGUF into models/
```

You also need a `llama-server` binary. `find_binary()` looks in this order:
`MUTA_RT_LLAMA_SERVER_BIN` → `runtime/build/bin/` → `PATH`. Either grab a
[prebuilt release](https://github.com/ggml-org/llama.cpp/releases) and unpack it into
`runtime/build/bin/`, or `brew install llama.cpp`.

**Keep the venv activated.** The Makefile defaults to `PY ?= python3`, so without it you get
a confusing `ModuleNotFoundError: pydantic_settings`. Or override: `make PY=.venv/bin/python <target>`.

### Interactive chat

```bash
make chat
```

Starts an engine if none is running, then streams a multi-turn conversation. Engine logs go
to `data/llama-server.log` so they don't shred your terminal. `exit` or Ctrl-D quits, and it
prints the conversation id on the way out:

```bash
make chat -- --conversation <id>     # resume that thread in a fresh process
```

Resuming is the bit worth trying — it's what proves persistence is real and not in-memory.

### Full stack

Two terminals, venv active in both:

```bash
make serve      # llama-server on :8080
make dev        # gateway on :8000, auto-reload
```

---

## 3. Talk to it

Everything is reachable by `curl` before a pixel exists — that's the point of the
backend-first design, and it's what makes the 30-phone classroom demo and headless
evaluation fall out for free.

```bash
curl -s localhost:8000/v1/ready
# {"ready":true,"checks":{"gateway":true,"inference":true}}
```

```bash
curl -s localhost:8000/v1/chat -H 'content-type: application/json' -d '{
  "student_id": "ada",
  "message": "I keep getting quadratic equations wrong"
}'
```

The response carries a `conversation_id`. Pass it back to continue the thread:

```bash
curl -s localhost:8000/v1/chat -H 'content-type: application/json' -d '{
  "student_id": "ada",
  "conversation_id": "<id from last response>",
  "message": "so what do I do first?"
}'
```

Interactive docs: <http://127.0.0.1:8000/docs>.

### Two things that look broken but aren't

- **The tutor won't just tell you the answer.** Default mode is `socratic` and its prompt
  forbids stating answers outright. Pass `"mode": "direct"` if you want a straight response.
  (Qwen3-0.6B follows this only loosely — it sometimes blurts the answer anyway. That's the
  model being small, and it's what the bake-off on 19-22 Jul is for.)
- **`"verified": false` on every reply.** Hardcoded until answers route through the
  `math`/SymPy service. It is not lying to you yet.

---

## 4. What's actually running

Two processes, which is the target topology:

```
llama-server  :8080   the engine — GGUF, KV cache (its own process, HTTP API)
gateway       :8000   the /v1 contract + math, retrieval, pedagogy, exam mounted in
```

The four sub-apps are developed and reviewed standalone (`uvicorn orchestrator.<svc>.app:app`)
but `app.mount()` into the gateway at deploy. Running them as separate processes would cost
60-100 MB RSS each against a **7 GB budget**, and would turn any single crash into a
disqualifying execution crash.

Only `:8000` is published. The engine stays on loopback.

---

## 5. Configuration

Every knob is a `MUTA_RT_*` env var (or a `.env` file). Full list with defaults:
`runtime/config.py`. The ones you'll actually reach for:

| Variable | Default | Notes |
|---|---|---|
| `MUTA_RT_MODEL_DIR` | `models` | `/app/models` in the container |
| `MUTA_RT_MODEL_FILE` | `Qwen3-0.6B-Q4_K_M.gguf` | |
| `MUTA_RT_MODEL_SOURCE` | `local` | `hf` to force a download |
| `MUTA_RT_AUTO_DOWNLOAD` | `true` | set `false` to rehearse offline |
| `MUTA_RT_LLAMA_SERVER_BIN` | *(search)* | overrides binary lookup |
| `MUTA_RT_N_CTX` | `4096` | context window |
| `MUTA_RT_N_THREADS` | *(auto)* | **a scoring decision, not a perf one** — more threads stop helping once memory bandwidth saturates but keep making heat, and >85 °C is a flat −10 |
| `MUTA_RT_ENABLE_THINKING` | `false` | Qwen3 hybrid reasoning; on = slower, more tokens |
| `MUTA_RT_DB_PATH` | `data/muta.sqlite3` | conversations live here |
| `MUTA_RT_MAX_HISTORY_MESSAGES` | `20` | history trim, excludes system prompt |

Resolution is **local-first, HF-fallback, always yielding a local path** — because the
deploy target has no network. llama-server's own `-hf` puller is deliberately compiled out.

---

## 6. Troubleshooting

**`/v1/chat` returns 503** — the engine isn't up. That's the designed answer, not a bug.
Check `curl localhost:8000/v1/ready`; in Docker read the `[entrypoint]` lines; natively make
sure `make serve` is running and check `data/llama-server.log`.

**`ModuleNotFoundError: pydantic_settings`** — venv isn't active. `source .venv/bin/activate`.

**`llama-server not found`** — see [Native](#2-native-fastest-dev-loop). Doesn't happen in
Docker; the image builds its own.

**Chat exits on its own** — fixed. A blank line used to quit, so a stray Enter pressed while
a reply streamed would end the session. Blank lines now re-prompt. Your old conversations are
still in SQLite; resume with `--conversation <id>`.

**Container is glacial on a Mac** — expected, see the warning at the top. Use native.

**Port in use** — `MUTA_RT_SERVER_PORT=8081 make serve`, or `-p 8001:8000` for the gateway.

---

## 7. What doesn't work yet

- `/v1/diagnose`, `/v1/generate_question`, `/v1/mastery`, `/v1/verify` → **501**. Each echoes
  its ROADMAP reference rather than failing silently.
- `make smoke`, `make bench`, `make profile`, `make package` → stubs that print their
  ROADMAP date.
- `bench/`, `corpus/`, `ui/`, `docs/` → empty. Notably **`bench/score.py` doesn't exist**;
  the ROADMAP calls it the compass and warns a bug there misdirects a month.
- **`--cache-ram` is unset**, so llama-server defaults to 8 GiB. On a 7 GB budget that's an
  OOM — and an OOM kill is disqualification. Harmless on a dev box with RAM to spare; must be
  capped explicitly before the target run.
- The container keeps a ~40 MB Python supervisor alive just to hold the engine subprocess
  (~0.11 pts of `S_eff`). The 9 Aug native extraction should launch `llama-server` directly.
