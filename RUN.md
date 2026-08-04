# Running Muta (dev branch — the 3-container stack)

## Start here

```bash
./run.sh
```

That's it. It builds the three images if they're missing, downloads the model roster into
`./models` if it's missing (~4 GB, resumable), starts **db → backend → frontend** in
dependency order, waits for health, and prints the UI URL:

- **Chat UI:** http://localhost:3000
- **API:** http://localhost:8000/v1 (interactive docs at http://localhost:8000/docs)

```bash
./run.sh            # bring the stack up                                [default]
./run.sh down       # stop it (conversations survive — see Persistence)
./run.sh logs       # follow all three containers' logs
./run.sh --build    # force a clean image rebuild first
./run.sh --model models/core/candidates/Qwen3.5-4B-UD-Q3_K_XL.gguf
                    # hot-swap the core GGUF (default models/core/Qwen3.5-4B-Q4_K_M.gguf)
```

**`--model PATH`** (works with docker and `--native` modes) serves a different core GGUF
without editing anything — the D1 bake-off seam. The file must already exist
(`scripts/fetch_models.py --quant-variants` fetches the pinned candidates;
`--with-draft` the 0.8B) and, in docker mode, live under `./models` (the only directory
mounted into the container). The `/v1/models` alias follows the filename (default keeps
`qwen3.5-4b`). Two pairings to know: vision's `mmproj-F16.gguf` belongs to the
Qwen3.5-4B family, so non-4B cores degrade vision; and the docker default keeps draft
speculation active, so a core outside the Qwen3.5 vocab (248,320) fails the engine boot —
set `MUTA_RT_SPEC_TYPE=none` first for such cores.

> **First run is slow.** The backend image compiles llama.cpp (pinned `b10035`,
> AVX2-only — the same engine discipline as `main`) and the model download is ~4 GB.
> Every later run starts in seconds.

> **Apple silicon:** everything runs under x86 emulation. In Docker Desktop settings,
> enable **"Use Rosetta for x86_64/amd64 emulation"** and give Docker **≥ 12 GB memory** —
> the core model tree is ~3.3 GB and an image question spawns a second ~3.3 GB vision
> instance (weights pages are shared, its KV is not). Token speed under emulation is not
> meaningful; correctness is.

## Native dev mode (Apple silicon)

`./run.sh --native` skips the amd64 emulation tax for day-to-day dev: db and frontend
stay in docker, the gateway + llama-server run on the host (arm64). The pinned
llama.cpp `b10035` macos-arm64 release is fetched into `runtime/build/bin` on first
use, so engine parity with the container is kept. Requires `make install` (importable
venv). Ctrl-C stops the backend; `./run.sh down` stops the containers. Audio degrades
to text-only unless sherpa-onnx is installed on the host — expected in native mode.

Docker (`./run.sh`, no flag) remains the default and the shape that ships: linux/amd64,
compose-gated health, the compiled AVX2 engine. Use it for anything you are about to
call a measurement of the real system, and re-verify there after native-mode iteration.
Mac-native numbers are dev signals only (`bench/optimization-log.md` rule).

## The three containers

| Container | Image | What it runs | Port |
|---|---|---|---|
| `db` | `postgres:16-alpine` | conversations, messages, attachments, user settings | 127.0.0.1:15432 (host tests) |
| `backend` | `docker/backend.Dockerfile` | FastAPI gateway (uvicorn) which supervises `llama-server` as a child; vision spawns a second, TTL-reaped llama-server on demand | 8000 |
| `frontend` | `docker/frontend.Dockerfile` | nginx serving the static UI and proxying `/v1` (same origin ⇒ no CORS; SSE unbuffered; WebSocket upgrade) | 3000 |

Startup ordering is enforced with healthchecks: `db` must accept connections before
`backend` starts; `backend` is *healthy* only once `/v1/ready` reports
`{"ready":true}` — gateway up, **model loaded**, database reachable — and only then does
`frontend` start.

## Models

Provisioning goes through `scripts/fetch_models.py` (the pinned-revision, sha256-verified
path). `./run.sh` runs it for you inside the backend image when anything is missing:

```bash
docker compose run --rm --no-deps backend \
    python3.10 scripts/fetch_models.py --with-draft --mmproj-precision f16
```

- `--mmproj-precision f16` is required: no first-party Q8_0 vision projector exists
  (`docs/model-provenance.md`), and the fetcher refuses to guess.
- The speculative-decoding **draft of record** is the pinned tier-B Qwen3.5-0.8B,
  `models/draft/Qwen3.5-0.8B-Q4_K_M.gguf` — fetched by `--with-draft` in the command
  above (`./run.sh` passes it automatically). It's optional: when absent the engine
  simply runs without speculation. The small dev GGUF `models/Qwen3-0.6B/`
  (`make model`) is **not** a draft candidate: the engine rejects it outright
  ("the target and draft vocabs are not compatible" — Qwen3's vocab is 151,936 vs
  Qwen3.5-4B's 248,320); it exists only as the smoke-test fixture
  (`docs/smoke-fixture.md`).

The roster (all under `./models`, volume-mounted into the backend, never baked):

| Role | File |
|---|---|
| Core LLM | `models/core/Qwen3.5-4B-Q4_K_M.gguf` |
| Vision projector | `models/core/mmproj-F16.gguf` |
| ASR | `models/asr/moonshine-tiny-en-int8/` |
| VAD | `models/asr/silero_vad.onnx` |
| TTS | `models/tts/piper/en_US-joe-medium.onnx` (CC0) |
| RAG embeddings | `models/embed/bge-small-en-v1.5-q8_0.gguf` |
| Speculation draft (optional) | `models/draft/Qwen3.5-0.8B-Q4_K_M.gguf` |

`make verify-models` re-checks hashes, licences and load smoke.

## Talk to it

Everything the UI does goes through `/v1` — so everything works from `curl` too
(directly on :8000, or through the proxy on :3000).

```bash
curl -s localhost:8000/v1/ready
# {"ready":true,"checks":{"gateway":true,"inference":true,"db":true}}

# Blocking turn:
curl -s localhost:8000/v1/chat -H 'content-type: application/json' -d '{
  "student_id": "ada",
  "message": "I keep getting quadratic equations wrong"
}'
# → carries conversation_id; pass it back to continue the thread

# Streaming turn (SSE):
curl -N -s localhost:8000/v1/chat/stream -H 'content-type: application/json' -d '{
  "student_id": "ada", "message": "Factorise x^2 + 5x + 6"
}'
# data: {"reasoning": "..."}   ← Qwen3.5 thinking
# data: {"delta": "..."}       ← answer tokens
# data: {"done": true, "conversation_id": "...", "tokens_per_second": ...}

# Photo of handwritten work (multipart):
curl -s localhost:8000/v1/tutor/vision -F session_id=ada -F image=@work.jpg
# {"session_id":"ada","transcription":"∫ x² dx = ...","accepted":true,"attachment_id":3,...}

# Uploaded audio → text (503 with a friendly message if ASR is unavailable):
curl -s localhost:8000/v1/audio/transcribe -F audio=@question.m4a

# History (how the UI reloads a thread):
curl -s "localhost:8000/v1/conversations?student_id=ada"
curl -s  localhost:8000/v1/conversations/<id>/messages

# Live telemetry (the UI strip): one-shot or 1 Hz SSE
curl -s  localhost:8000/v1/conversations/<id>/telemetry
curl -N -s localhost:8000/v1/conversations/<id>/telemetry/stream
# {"rss_gb":3.21,"peak_rss_gb":3.4,"cpu_temp_c":null,"throttled":null,
#  "tokens_per_second":4.2,"generating":true}
```

`cpu_temp_c`/`throttled` are `null` wherever the host exposes no sensors (always the case
for Docker on macOS — the UI shows "—"); on a Linux host with hwmon they're real.

The voice loop is a WebSocket (`WS /v1/audio/voice`): the browser streams 16 kHz PCM, the
backend runs Silero VAD → when you stop talking it transcribes with Moonshine, streams the
LLM reply, synthesizes each sentence with Piper, and the browser auto-plays it — no click.
The mic needs a secure context: **http://localhost:3000 works, a LAN IP does not.**

## Persistence

Conversations, messages and attachments live in Postgres, in the named volume
`muta-pgdata`. `./run.sh down` / `docker compose down` **keeps** them;
`docker compose down -v` is the only thing that deletes them.

Host-side tests reach the same db on `127.0.0.1:15432`
(`MUTA_TEST_DB_URL` overrides; store tests skip cleanly when it's down).

## Configuration

Backend env (set in `docker-compose.yml`; all `MUTA_RT_*` overridable):

| Variable | Default (compose) | Meaning |
|---|---|---|
| `MUTA_RT_DB_URL` | `postgresql://muta:muta@db:5432/muta` | Postgres DSN |
| `MUTA_RT_MODEL_DIR` / `_FILE` | `/app/models/core` / `Qwen3.5-4B-Q4_K_M.gguf` | core GGUF |
| `MUTA_RT_DRAFT_MODEL` | `/app/models/draft/Qwen3.5-0.8B-Q4_K_M.gguf` | speculative draft (Qwen3.5 family only — Qwen3 vocab is incompatible; skipped if absent) |
| `MUTA_RT_AUTOSTART` | `1` | gateway lifespan starts/supervises llama-server |
| `MUTA_RT_STARTUP_TIMEOUT_S` | `900` | model-load allowance (emulation is slow) |
| `MUTA_RT_REQUEST_TIMEOUT_S` | `600` | per-request client timeout |
| `TUTOR_ROOT` | `/app` | root for vision/audio model paths |
| `MUTA_RT_N_CTX` | `2048` | context size (keeps core+draft under the ladder cap) |
| `MUTA_RT_ENABLE_THINKING` | `1` | Qwen thinking mode (minutes-long on emulated CPU) |
| `MUTA_CORE_CAP_MIB` | `5400` | ladder's core-RSS cap; default 4300 is main's 7 GB budget |
| `MUTA_RT_N_PARALLEL` | `2` | server slots (each costs ~50 MiB f32 state on the hybrid 4B) |
| `MUTA_RT_CTX_CHECKPOINTS` | `2` | recurrent-state checkpoints per slot, ~50 MiB each |
| `MUTA_RT_CACHE_RAM_MIB` | `256` | host-RAM prompt cache cap (engine default: 8192) |
| `MUTA_RT_KV_UNIFIED` | `1` | slots share the full `-c` window (explicit `-np` would otherwise split it) |
| `MUTA_RT_N_THREADS` / `MUTA_RT_N_THREADS_BATCH` | auto: P-core count on Apple silicon, engine default elsewhere (compose: `8` / `10`) | decode / prefill threads |
| `MUTA_RT_N_BATCH` / `_UBATCH` | `512` / `128` | logical / physical batch (compute-buffer size) |
| `MUTA_RT_CACHE_TYPE_K` | `q8_0` | K-cache quantization |
| `MUTA_RT_REASONING_BUDGET` | `512` | max thinking tokens before the answer is forced |
| `MUTA_RT_SPEC_TYPE` | `draft-simple` | `none` \| `draft-simple` \| `ngram-simple` |

## Troubleshooting

- **`docker compose ps` shows backend `starting` for minutes** — normal on first boot and
  under emulation: it's loading 2.6 GB of weights. `./run.sh logs` and watch
  `data/logs/llama-server.log` lines appear.
- **Stack never becomes healthy** — `docker compose logs backend --tail 50`. The usual
  causes: Docker memory too low (raise to ≥ 12 GB) or a half-downloaded model
  (rerun `./run.sh`; downloads resume and verify by sha256).
- **Voice button does nothing** — you're not on `localhost` (mic requires a secure
  context), or ASR is degraded: `curl -s localhost:8000/v1/audio/transcribe -F audio=@x.wav`
  explains itself.
- **Vision replies `accepted:false`** — the degradation ladder refused to spawn the second
  model instance (not enough free memory). Give Docker more memory; text tutoring keeps
  working regardless.
- **Wipe everything** — `docker compose down -v && docker image prune` and delete
  `./models` if you want the downloads gone too.

## What the Makefile is for

`make help` lists everything. The stack lives behind `./run.sh` / `make up` / `make down`;
`make dev` runs the gateway on the host against the compose db for a fast edit loop;
`make test` / `make lint` / `make contract` are the per-task developer surface.
