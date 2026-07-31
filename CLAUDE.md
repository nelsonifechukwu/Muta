# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Which branch you are on matters

- **`main`** — the ADTC 2026 competition build: one container, two processes, SQLite,
  flash-drive deploy tooling. `README.md` + `ROADMAP.md` are its plan of record.
- **`dev` (this branch)** — a **long-lived alternative architecture**: a conventional
  3-container web app (Postgres + backend + nginx frontend). It is *not* destined for merge
  into `main`. The plan that built it: `docs/plans/2026-07-25-three-container-architecture.md`.

The competition heritage still explains many invariants (AVX2-only engine build, pinned
model provenance, degradation-not-errors, mode-aware tutoring), but the deploy story on
this branch is `docker compose`, not a flash drive. Historical docs under `docs/` that
mention `deploy/`, `bundle/` or the TUI describe `main`.

## What this is

An **offline, adaptive AI tutor for math and scientific reasoning**, re-architected on
this branch as three containers, all `--platform=linux/amd64`, orchestrated by
`docker-compose.yml`:

| Container | Runs | Port |
|---|---|---|
| `db` | Postgres 16 — conversations, messages, attachments (BYTEA), user settings (JSONB); named volume `muta-pgdata` | 127.0.0.1:15432 |
| `backend` | FastAPI gateway (uvicorn); its lifespan supervises `llama-server` as a child (`MUTA_RT_AUTOSTART=1`); vision = second, TTL-reaped llama-server; audio = sherpa-onnx in-process | 8000 |
| `frontend` | nginx: static vanilla-JS chat UI + same-origin `/v1` reverse proxy (SSE unbuffered, WS upgrade) | 3000 |

**`./run.sh` is the front door**: build (cached) → provision models → `compose up --wait`
(db → backend → frontend, healthcheck-gated) → print `http://localhost:3000`. `RUN.md`
documents it and every curl equivalent.

Working end-to-end: streamed chat (SSE; Qwen3.5 thinking rendered as a collapsible block),
conversation persistence + sidebar (Postgres), image → transcription → tutoring
(`/v1/tutor/vision`, image stored as an attachment), uploaded-audio transcription
(`/v1/audio/transcribe`: ffmpeg → Moonshine), the full voice loop (`WS /v1/audio/voice`:
Silero VAD endpoint → Moonshine → LLM stream → per-sentence Piper TTS auto-played,
barge-in supported), and live per-conversation telemetry
(`/v1/conversations/{id}/telemetry[/stream]`: process-tree RSS, peak, CPU temp, throttle
flag, tok/s — `null` → "—" in the UI when unmeasurable, e.g. Docker on macOS).
The math/pedagogy/exam sub-app endpoints remain `501` stubs, as on main.

## Models (pinned, verified, mounted — never baked)

Provisioning is `scripts/fetch_models.py` (+ `model_specs.py`, `verify_models.py`): exact
HF revisions in `models/pins.lock.json`, sha256 verified twice, licences captured into
`models/LICENSES/`. A full fetch **requires `--mmproj-precision f16`** (no first-party
Q8_0 projector exists — `docs/model-provenance.md`) and `--with-draft` for the
speculation draft. `run.sh` invokes exactly that inside the backend image when files are
missing; downloads are resumable and hash-skipped when present.

The roster: core `models/core/Qwen3.5-4B-Q4_K_M.gguf` + `mmproj-F16.gguf` (vision),
Moonshine tiny int8 (ASR), `models/asr/silero_vad.onnx` (VAD — underscore; the dash name
never existed on disk), Piper `en_US-joe-medium` at its native **22050 Hz** (CC0 — lessac
is NOT redistributable), bge-small (embeddings). The speculation draft of record is the
pinned tier-B Qwen3.5-0.8B, `models/draft/Qwen3.5-0.8B-Q4_K_M.gguf` (fetched by
`--with-draft`; `run.sh` does this automatically), wired in via `--spec-type
draft-simple` + `--spec-draft-model` — this llama.cpp pin (b10035) activates
speculation only when `--spec-type` is passed, `--spec-draft-model` alone is a silent
no-op (`docs/engine-flags.md`) — and skipped when absent. Qwen3-0.6B cannot serve as a
draft here (vocab 151,936 vs Qwen3.5-4B's 248,320 — "vocabs are not compatible"); it
remains only the small dev/smoke fixture (`make model`).

## Architecture rules that still bind

- **Contract-first.** The `/v1` surface is generated from `contracts/models.py`
  (`make contract` → `contracts/openapi.yaml`; never hand-edit; commit the result).
  Changes are **additive-only**. Every client — UI, curl, tests — speaks `/v1`; the
  browser reaches it through the nginx proxy, so there is deliberately **no CORS anywhere**.
- **Engine build discipline is unchanged**: llama.cpp pinned `b10035`,
  `GGML_AVX2=ON GGML_AVX512=OFF GGML_NATIVE=OFF`; `docker/backend.Dockerfile` *asserts*
  x86-64 ELF and greps the disassembly for AVX-512 mnemonics — the build fails rather than
  shipping an illegal-instruction fault.
- **Sub-app mounting** (`orchestrator/main.py`): the gateway router owns `/v1`;
  math/retrieval/pedagogy/exam/bench stay mounted under `/internal/*`, absent from the
  public schema (a contract test enforces it).
- **Degradation, not errors**: engine down → 503 with instructions; vision refused by the
  ladder → friendly `accepted:false`; ASR/TTS absent → explicit text-only message;
  telemetry unmeasurable → `null`; a dropped stream persists the partial assistant reply.
  A student-facing crash is the one failure that is never acceptable.
- **The flags are the memory budget**: context/slot/thread numbers live in
  `runtime/profiles.py` (vision command, `BundlePaths` — `TUTOR_ROOT=/app` in the
  container) and `RuntimeConfig` (`MUTA_RT_*`) — nowhere else.

## Layout (what changed vs main)

- `docker-compose.yml`, `docker/backend.Dockerfile`, `docker/frontend.Dockerfile`,
  `docker/nginx.conf` — the stack. `run.sh` — the front door.
- `ui/` — static chat client (`index.html`, `styles.css`, `app.js`, `audio.js`,
  `worklet.js`). KaTeX/marked/DOMPurify vendored **at frontend-image build** (pinned
  versions; no CDN at runtime). Claude-style theme: `#faf9f5` page, serif prose, centered
  48rem column, warm terracotta accents.
- `runtime/memory.py` — **Postgres** ConversationStore (psycopg3 + pool; same public API
  plus `list_messages`/attachments/settings/`ping`; message ordering still by serial id;
  ISO-8601 TEXT timestamps). DSN via `MUTA_RT_DB_URL`; `db_path`/SQLite is gone.
- `runtime/config.py`/`server.py` — draft-model speculation flags, `request_timeout_s`,
  `autostart`. `runtime/chat.py` — streams persist partial replies on early close; stream
  methods return `(conversation_id, user_message_id, iterator)`.
- `orchestrator/telemetry.py` — bounded TelemetryHub (1 Hz tree-RSS/temp sampler thread,
  per-conversation tok/s). Reuses `bench/sampler.py`'s extracted
  `family()`/`family_rss_bytes()`/`read_temp_c()` — the tree-walk exists once.
- `orchestrator/gateway/audio_routes.py` — `/v1/audio/transcribe` + `WS /v1/audio/voice`.
  Audio config of record: `orchestrator/audio/audio.yaml` (paths resolve against
  `TUTOR_ROOT`).
- `orchestrator/gateway/routes.py` — conversation surface for the UI:
  `GET /v1/conversations`, `GET/DELETE /v1/conversations/{id}[...]`,
  `GET /v1/attachments/{id}`, telemetry routes; `/v1/chat/stream` is in the contract.
- **Deleted on this branch**: `runtime/cli.py` (REPL), `bench/tui.py` (TUI), `bundle/`,
  `deploy/` (systemd/flash-drive tooling), `docker/dev.Dockerfile` + `entrypoint.sh`.

## Commands

`make help` lists everything (Python ≥3.10; `make install` for an editable install).

- `./run.sh` / `make up` / `make down` — the stack. `./run.sh logs` to follow.
- `make dev` — gateway on the host with reload (fast edit loop; reaches the compose `db`
  at `127.0.0.1:15432` via `MUTA_RT_DB_URL`'s default). `make serve` — host llama-server.
- `make test` — pytest. Store tests need the compose db (`docker compose up -d db`) and
  **skip cleanly when it's down**. `make lint` / `make fmt` — ruff.
- `make contract` — regenerate `contracts/openapi.yaml`; commit the result.
- `make fetch-models` / `make verify-models` — the provisioning path (RUN.md has the exact
  flags `run.sh` uses).
- `make smoke` — ready + proxied-health probe against a running stack.

## Working method (the standing engineering protocol)

1. **Study before writing.** Read the relevant plan/docs first; plans live in `docs/plans/`.
2. **Externalize tribal knowledge into `docs/`** — every non-obvious decision (a "why", an
   invariant, a rejected alternative) is written down (`docs/model-provenance.md` is the
   canonical example).
3. **Partition cleanly** — the `/v1` contract is the seam; regenerate, never hand-edit.
4. **Pair every writer with an adversarial reviewer** in a fresh context whose only job is
   to assume the output is wrong and find why. Apply hardest where a silent bug is most
   expensive: the Postgres store's ordering semantics, stream partial-persist, the voice
   WS loop, and compose health/ordering.
