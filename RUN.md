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
```

> **First run is slow.** The backend image compiles llama.cpp (pinned `b10035`,
> AVX2-only — the same engine discipline as `main`) and the model download is ~4 GB.
> Every later run starts in seconds.

> **Apple silicon:** everything runs under x86 emulation. In Docker Desktop settings,
> enable **"Use Rosetta for x86_64/amd64 emulation"** and give Docker **≥ 12 GB memory** —
> the core model tree is ~3.3 GB and an image question spawns a second ~3.3 GB vision
> instance (weights pages are shared, its KV is not). Token speed under emulation is not
> meaningful; correctness is.

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
- The speculative-decoding **draft** is the small dev GGUF, `models/Qwen3-0.6B/`
  (fetch with `make model`). It's optional: when absent the engine simply runs
  without speculation. (`--with-draft` can still fetch the pinned tier-B
  Qwen3.5-0.8B if you want that instead — point `MUTA_RT_DRAFT_MODEL` at it.)

The roster (all under `./models`, volume-mounted into the backend, never baked):

| Role | File |
|---|---|
| Core LLM | `models/core/Qwen3.5-4B-Q4_K_M.gguf` |
| Vision projector | `models/core/mmproj-F16.gguf` |
| ASR | `models/asr/moonshine-tiny-en-int8/` |
| VAD | `models/asr/silero_vad.onnx` |
| TTS | `models/tts/piper/en_US-joe-medium.onnx` (CC0) |
| RAG embeddings | `models/embed/bge-small-en-v1.5-q8_0.gguf` |
| Speculation draft (optional) | `models/Qwen3-0.6B/Qwen3-0.6B-Q4_K_M.gguf` |

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
| `MUTA_RT_DRAFT_MODEL` | `/app/models/Qwen3-0.6B/Qwen3-0.6B-Q4_K_M.gguf` | speculative draft (skipped if absent) |
| `MUTA_RT_AUTOSTART` | `1` | gateway lifespan starts/supervises llama-server |
| `MUTA_RT_STARTUP_TIMEOUT_S` | `900` | model-load allowance (emulation is slow) |
| `MUTA_RT_REQUEST_TIMEOUT_S` | `600` | per-request client timeout |
| `TUTOR_ROOT` | `/app` | root for vision/audio model paths |
| `MUTA_RT_N_CTX` | `2048` | context size (keeps core+draft under the ladder cap) |
| `MUTA_RT_ENABLE_THINKING` | `0` | Qwen thinking mode (minutes-long on emulated CPU) |
| `MUTA_CORE_CAP_MIB` | `5400` | ladder's core-RSS cap; default 4300 is main's 7 GB budget |

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
