# `dev` Branch — 3-Container Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A long-lived `dev` branch where `./run.sh` (no flags) brings up db → backend → frontend as three healthy linux/amd64 containers: Postgres-backed conversations, llama-server (Qwen3.5-4B + mmproj + speculative draft) behind the FastAPI gateway with SSE streaming, per-conversation telemetry, a voice loop (Silero VAD → Moonshine ASR → LLM → Piper TTS), and a Claude-styled web chat UI.

**Architecture:** Backend container runs the gateway (uvicorn) which supervises llama-server as a child via lifespan (`MUTA_RT_AUTOSTART=1`); vision stays an ephemeral second llama-server (existing `VisionManager`). Frontend is nginx serving a static vanilla-JS UI and reverse-proxying `/v1` (same-origin ⇒ no CORS). `runtime/memory.py` is ported from SQLite to psycopg3/Postgres with an identical public API. All new `/v1` surface is additive.

**Tech stack:** FastAPI/uvicorn, llama.cpp b10035 (AVX2, no AVX-512), psycopg3 + psycopg_pool, sherpa-onnx (Moonshine/Silero/Piper), nginx:alpine, vanilla JS + KaTeX 0.16.11 + marked 12.0.2 + DOMPurify (vendored at image build), docker compose.

## Global Constraints

- All three images built/run `--platform=linux/amd64`.
- `main` must remain byte-identical: never commit to `main`; all work on `dev`.
- Weights are mounted (`./models:/app/models`), never baked into images.
- Model provisioning goes through the existing `scripts/fetch_models.py` path. Full fetch **requires `--mmproj-precision f16`** (hard gate at `scripts/fetch_models.py:521`) and `--with-draft` for the draft model.
- **Deviation (documented):** task asked for draft "Qwen3.5-0.6B"; no such model exists in the Qwen3.5 family. The repo's pinned, licence-audited tier-B draft is `unsloth/Qwen3.5-0.8B-GGUF` → `models/draft/Qwen3.5-0.8B-Q4_K_M.gguf`. Use it.
- `/v1` contract changes are additive-only; regenerate `contracts/openapi.yaml` via `make contract` after any contract change; never hand-edit the YAML.
- UI assets fully offline at runtime (no CDN); build-time network is allowed (images already clone llama.cpp / pip install).
- Frontend calls `/v1/chat` + `/v1/chat/stream` (student/conversation-scoped), **never** `/v1/tutor/*` (session/admission machinery expects the classroom-profile engine).
- Telemetry metrics that are unavailable (e.g. CPU temp in Docker-on-macOS) report `null`, UI shows "—"; never crash.
- Unavailable audio engines degrade to text with an explicit error event, never a silent failure.

## Context

The repo is an offline AI tutor (ADTC 2026) currently architected as one Docker container running two processes (llama-server + mounted FastAPI gateway), with a TUI/REPL front-end, SQLite conversations, and extensive flash-drive/systemd deploy tooling (`deploy/`, `bundle/`). This task creates a **long-lived alternative architecture** on `dev` — a conventional 3-container web app — while `main` continues to carry the competition build. Much of what's needed already exists and is reused: model roster fully pinned (`models/pins.lock.json` already resolves Qwen3.5-4B-Q4_K_M + mmproj-F16 + Moonshine + Silero + Piper joe + bge-small + draft 0.8B; core/mmproj/asr/vad/tts/embed already on disk, draft not yet fetched), SSE streaming (`/v1/chat/stream`, currently `include_in_schema=False`), vision (`/v1/tutor/vision` + `VisionManager`), an audio WS service with fake-engine tests (sherpa-onnx never vendored), and the ADTC profiler-faithful RSS/thermal sampler (`bench/sampler.py`) reusable for telemetry.

**Pre-existing working-tree state on main:** `M RUN.md` (+33 lines of vision docs), `D TDD-system-architecture.md.md`. These are snapshotted as the first `dev` commit so `main`'s committed state is untouched (checking out `main` later shows a clean tree; the delta lives in `dev` history).

---

## KEEP / DELETE list (complete)

### DELETE on `dev` (with the compensating edit that must land in the same task)

| Path | Why / paired edit |
|---|---|
| `runtime/cli.py` (REPL) | Nothing imports it. Pair: drop Makefile `chat` target; run.sh rewrite removes its call sites. |
| `runtime/run.sh`, `runtime/Dockerfile` (0-byte) | Single-process launcher glue; unreferenced. |
| `bench/tui.py`, `bench/test_tui.py` | TUI replaced by web UI. Pair: drop Makefile `tui` target + `textual` dev-dep (`rich` stays — `bench/monitor.py`). |
| `docker/entrypoint.sh` | Replaced by image `CMD` + lifespan engine supervision (same task as new Dockerfile). |
| `docker/dev.Dockerfile` | Superseded by `docker/backend.Dockerfile` (same stage-1 engine build + ISA assertion carried over verbatim). |
| `deploy/` — all 17 files (`build.sh`, `fetch_models.sh` [self-declared SUPERSEDED], `stage.sh`, `install.sh`, `selftest.sh`, `package.sh`, `versions.lock`, `licenses.json`, `etc/profile.env`, `etc/audio.yaml`, `units/{tutor-core,tutor-gw,tutor-embed,tutor-audio}.service`, `units/tutor.slice`, `units/earlyoom.conf`, `units/zram-generator.conf`) | Flash-drive/systemd tooling. Pairs: migrate a corrected `audio.yaml` into `orchestrator/audio/` **first** (T8 lands before the deploy/ deletion in T9); drop Makefile `engine`/`stage`/`selftest`/`package` targets; delete the `deploy/licenses.json`-reading test in `scripts/test_fetch_models.py`. |
| `bundle/` — all 9 files (`__init__.py`, `layout.py`, `manifest.py`, `stage.py`, `versions.py`, `tests/×3`) | Flash-drive artifact logic. Pairs: remove `"bundle"` from `pyproject.toml` `packages` + `testpaths`; drop Makefile `manifest` target; delete the `bundle.manifest`-importing test in `scripts/test_fetch_models.py` (the remaining `test_every_shipped_artifact_declares_a_permissive_licence` still covers the licence invariant). |
| Makefile targets: `chat`, `tui`, `engine`, `manifest`, `stage`, `selftest`, `package` | Plus `.PHONY` line cleanup. |
| `run.sh` bodies: `run_native`, `run_tui`, `run_docker` | Full rewrite to compose front door (T4). |
| SQLite implementation inside `runtime/memory.py` | Rewritten to Postgres (same module path/class name — importers unchanged). |

### KEEP (the three containers depend on these)

- **`contracts/`** — entire; `/v1` still governs. Additions are additive; regenerate YAML.
- **`scripts/`** — `fetch_models.sh/.py`, `verify_models.sh/.py`, `model_specs.py`, `test_fetch_models.py` (minus the two doomed tests) — **the** model-provisioning path.
- **`runtime/`** — `config.py`, `models.py`, `server.py`, `client.py`, `chat.py`, `memory.py` (rewritten), `vision.py`, `vision_client.py`, `profiles.py` (**required**: `VisionManager` → `core_vision_command`/`BundlePaths`; also the speculation-flag reference), `gguf.py`, `kvmath.py`, `slots.py`, `tests/` (ported where they touch the store).
- **`orchestrator/`** — everything: gateway (routes, deps, sampling, ladder, sessions, images, prompt_layout), tools, audio (fixed + extended), pedagogy/twin, sub-apps, bench_metrics, prompts.
- **`bench/`** minus tui — `score.py`, `sampler.py` (extended for telemetry), `profile.py`, `autotest.py`, `monitor.py`, `adtc/`, tests.
- **`models/MANIFEST.json`, `models/pins.lock.json`, `models/LICENSES/`** — tracked provenance (updated once when the draft is first fetched).
- **`docs/`** — decision docs stay (history); `docs/plans/` gains this plan.
- `README.md`, `ROADMAP.md` — untouched (main's plan of record; CLAUDE.md on dev explains the divergence).

---

### Task T0: Branch, snapshot, plan file

**Files:** none modified beyond git state + `docs/plans/2026-07-25-three-container-architecture.md` (new)

- [ ] **Step 1:** `git checkout -b dev` (carries the uncommitted working tree).
- [ ] **Step 2:** Commit the pre-existing state verbatim:
```bash
git add -A RUN.md TDD-system-architecture.md.md
git commit -m "chore: snapshot working-tree state inherited from main"
```
- [ ] **Step 3:** Copy this plan to `docs/plans/2026-07-25-three-container-architecture.md` (project convention: plans live in `docs/plans/`; includes the keep/delete list). Commit.
- [ ] **Step 4:** Verify `git log main -1` still shows `0d91d26` and `git diff main..dev --stat` shows only the snapshot + plan.

### Task T1: Runtime plumbing (config, draft flags, partial-persist, timeouts) — TDD

**Files:** Modify `runtime/config.py`, `runtime/server.py`, `runtime/chat.py`, `runtime/client.py`, `orchestrator/gateway/deps.py`; Test `runtime/tests/test_server_command.py` (new), `runtime/tests/test_chat.py` (extend)

**Interfaces produced:** `RuntimeConfig.db_url: str`, `.draft_model: Path|None`, `.draft_max: int=8`, `.draft_min: int=1`, `.request_timeout_s: float=120`, `.autostart: bool=False` (env `MUTA_RT_DB_URL`, `MUTA_RT_DRAFT_MODEL`, `MUTA_RT_REQUEST_TIMEOUT_S`, `MUTA_RT_AUTOSTART`). `db_path` field is deleted with the SQLite path (T2 consumes `db_url`).

- [ ] **Step 1:** Write failing tests: `LlamaServer.build_command` emits `--model-draft <p> --draft-max 8 --draft-min 1 --draft-p-min 0.75` when `cfg.draft_model` exists (tmp file), and omits all draft flags when unset or missing.
- [ ] **Step 2:** Implement in `build_command` (crib `runtime/profiles.py:336-351`):
```python
if self.cfg.draft_model and Path(self.cfg.draft_model).is_file():
    cmd += ["--model-draft", str(self.cfg.draft_model),
            "--draft-max", str(self.cfg.draft_max), "--draft-min", str(self.cfg.draft_min),
            "--draft-p-min", "0.75"]
```
- [ ] **Step 3:** Write failing test: `stream_events_chat` persists the partial assistant text when the consumer abandons/errors the iterator mid-stream (fake client whose generator raises after 2 chunks → assert both chunks persisted).
- [ ] **Step 4:** Implement partial-persist in `runtime/chat.py` — wrap the drain loops of `stream_chat`/`stream_events_chat` in `try/finally`; in `finally`, if accumulated chunks are non-empty and not yet persisted, `store.add_message(cid, "assistant", "".join(chunks))`.
- [ ] **Step 5:** Thread `request_timeout_s` → `InferenceClient(timeout=...)` in `deps.get_engine()`.
- [ ] **Step 6:** `pytest runtime/ -q` green; `ruff check .`; commit.

### Task T2: Postgres `ConversationStore` port — TDD

**Files:** Rewrite `runtime/memory.py`; Create `runtime/tests/conftest.py`; Modify `runtime/tests/test_memory.py`, `runtime/tests/test_chat.py`, `pyproject.toml` (add `psycopg[binary]>=3.2`, `psycopg-pool>=3.2`), `orchestrator/gateway/deps.py` (construct with `cfg.db_url`)

**Interfaces produced (unchanged where existing):** `ConversationStore(dsn)`; `create_conversation(student_id, *, mode, persona, subject, language, title) -> str`; `get_conversation(id) -> dict|None`; `list_conversations(student_id) -> list[dict]`; `delete_conversation(id)`; `add_message(cid, role, content) -> int`; `get_messages(cid, limit=None) -> list[dict]` (role/content/created_at, chronological, last-N via DESC+reversed); `close()`. **New:** `list_messages(cid) -> list[dict]` (adds `id` + `attachments: [{id,kind,mime}]`); `add_attachment(kind, mime, data, conversation_id=None, message_id=None) -> int`; `get_attachment(id) -> dict|None` (`kind,mime,data`); `link_attachment(attachment_id, conversation_id, message_id)`; `set_title(cid, title)` (only if currently NULL); `get_settings(student_id) -> dict` / `put_settings(student_id, settings: dict)`.

Schema (idempotent DDL at construction; TEXT ISO-8601 UTC timestamps for exact dict-shape parity — they sort lexicographically = chronologically; `BIGSERIAL` preserves the order-by-id semantics):
```sql
CREATE TABLE IF NOT EXISTS conversations (
  id TEXT PRIMARY KEY, student_id TEXT NOT NULL,
  mode TEXT, persona TEXT, subject TEXT, language TEXT, title TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS messages (
  id BIGSERIAL PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, id);
CREATE INDEX IF NOT EXISTS idx_conversations_student ON conversations(student_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS attachments (
  id BIGSERIAL PRIMARY KEY,
  conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
  message_id BIGINT REFERENCES messages(id) ON DELETE SET NULL,
  kind TEXT NOT NULL CHECK (kind IN ('image','audio')),
  mime TEXT NOT NULL, data BYTEA NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS user_settings (
  student_id TEXT PRIMARY KEY, settings JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TEXT NOT NULL);
```

Implementation notes: `psycopg_pool.ConnectionPool(dsn, min_size=1, max_size=8, kwargs={"row_factory": psycopg.rows.dict_row})`, opened with a ~30 s bounded retry (Postgres first-boot init-restart window). Every method: `with self._pool.connection() as conn:`; `add_message` uses `with conn.transaction():` for INSERT + `UPDATE conversations SET updated_at`; `INSERT ... RETURNING id` replaces `lastrowid`. No `threading.Lock` (the pool is the concurrency mechanism).

- [ ] **Step 1:** `runtime/tests/conftest.py` — `store` fixture: connect admin DSN from `MUTA_TEST_DB_URL` (default `postgresql://muta:muta@127.0.0.1:15432/muta`), create database `muta_test` if absent (catch `DuplicateDatabase`), build store against `muta_test`, `TRUNCATE conversations, messages, attachments, user_settings CASCADE` between tests; `pytest.skip("postgres unavailable")` when connect fails. Dev loop while T4 doesn't exist yet: `docker run -d --name muta-pg -p 127.0.0.1:15432:5432 -e POSTGRES_USER=muta -e POSTGRES_PASSWORD=muta -e POSTGRES_DB=muta postgres:16`.
- [ ] **Step 2:** Port the 4 tests in `test_memory.py` to the fixture; add failing tests for `list_messages` (ids + attachment refs), `add_attachment`/`get_attachment`/`link_attachment` round-trip, `set_title` only-if-null, settings round-trip, FK cascade on `delete_conversation`.
- [ ] **Step 3:** Implement the rewrite; run `pytest runtime/tests/test_memory.py -v` green.
- [ ] **Step 4:** Port `test_chat.py` to the fixture (it constructs a real store). `pytest runtime/ -q` green.
- [ ] **Step 5:** Update `deps.get_engine()` → `ConversationStore(cfg.db_url)`. Contract smoke tests still pass (they override `get_engine`). Commit.

### Task T3: Lifespan supervision + ops hardening

**Files:** Modify `orchestrator/main.py`, `orchestrator/gateway/routes.py` (`/v1/ready`), `orchestrator/gateway/deps.py`; Test `orchestrator/tests/test_lifespan.py` (new)

- [ ] **Step 1:** In `_lifespan`, when `RuntimeConfig().autostart`: `mkdir -p` `$TUTOR_ROOT/data/logs` and `$TUTOR_ROOT/data/kv-slots` (vision's `--log-file` dies without it); start `LlamaServer(cfg).ensure(log_file=...)` in a **daemon thread** (a blocking/raising `ensure` in lifespan would crash-loop the container; gateway binds immediately, `/v1/ready` reports `inference:false` until green); start an asyncio task ticking `get_vision().reap_if_idle()` every 30 s (currently the reaper has zero callers — without it the ~3.3 GB vision instance lives forever).
- [ ] **Step 2:** Shutdown path in lifespan `finally`: stop vision (`get_vision().stop()`), stop the engine if we started it (`LlamaServer.stop()` — terminate → wait 10 → kill).
- [ ] **Step 3:** `/v1/ready` gains a `db` check (store construction/`SELECT 1` wrapped; returns `{"ready":false,"checks":{...,"db":false}}` — still HTTP 200; compose healthcheck greps the body).
- [ ] **Step 4:** Tests: autostart-off lifespan is a no-op; ready-shape includes `db`. `pytest` green; commit.

### Task T4: Compose, images, nginx, `.dockerignore`, `run.sh` rewrite

**Files:** Create `docker-compose.yml`, `docker/backend.Dockerfile`, `docker/frontend.Dockerfile`, `docker/nginx.conf`, `ui/index.html` (placeholder until T7); Modify `.dockerignore`, `run.sh` (rewrite); Delete `docker/dev.Dockerfile`, `docker/entrypoint.sh`

- [ ] **Step 1:** `.dockerignore`: replace `models/*.gguf` with `models` (13 GB of weights currently enters the build context — `models/core` 3.2G + stray `models/Phi4` 7.2G; weights arrive via the runtime mount), keep `data/`, add `ui/node_modules`, `ui/dist`.
- [ ] **Step 2:** `docker/backend.Dockerfile` — stage 1 copied **verbatim** from `dev.Dockerfile` (llama.cpp `b10035`, AVX2 flags, ELF + objdump AVX-512 assertions); stage 2 changes: apt adds `curl ffmpeg`; pip adds `--only-binary=:all: "sherpa-onnx>=1.10"`; drop `ENV MUTA_RT_DB_PATH`; add `ENV TUTOR_ROOT=/app`; **no ENTRYPOINT**, instead:
```dockerfile
CMD ["python3.10", "-m", "uvicorn", "orchestrator.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
- [ ] **Step 3:** `docker/nginx.conf`:
```nginx
map $http_upgrade $connection_upgrade { default upgrade; '' close; }
server {
  listen 80;
  root /usr/share/nginx/html;
  location /v1/ {
    proxy_pass http://backend:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
    client_max_body_size 32m;
  }
  location / { try_files $uri /index.html; }
}
```
- [ ] **Step 4:** `docker/frontend.Dockerfile`:
```dockerfile
FROM --platform=linux/amd64 nginx:1.27-alpine
WORKDIR /usr/share/nginx/html
RUN mkdir -p vendor/katex vendor \
 && wget -qO- https://github.com/KaTeX/KaTeX/releases/download/v0.16.11/katex.tar.gz | tar xz -C vendor \
 && wget -qO vendor/marked.min.js https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js \
 && wget -qO vendor/purify.min.js https://cdn.jsdelivr.net/npm/dompurify@3.1.6/dist/purify.min.js
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY ui/ /usr/share/nginx/html/
```
- [ ] **Step 5:** `docker-compose.yml`:
```yaml
services:
  db:
    image: postgres:16
    platform: linux/amd64
    environment: { POSTGRES_USER: muta, POSTGRES_PASSWORD: muta, POSTGRES_DB: muta }
    volumes: [ "muta-pgdata:/var/lib/postgresql/data" ]
    ports: [ "127.0.0.1:15432:5432" ]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U muta -d muta"]
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 10s
  backend:
    build: { context: ., dockerfile: docker/backend.Dockerfile }
    platform: linux/amd64
    init: true
    stop_grace_period: 30s
    depends_on:
      db: { condition: service_healthy }
    ports: [ "8000:8000" ]
    volumes: [ "./models:/app/models" ]
    environment:
      MUTA_RT_AUTOSTART: "1"
      MUTA_RT_DB_URL: postgresql://muta:muta@db:5432/muta
      MUTA_RT_MODEL_DIR: /app/models/core
      MUTA_RT_MODEL_FILE: Qwen3.5-4B-Q4_K_M.gguf
      MUTA_RT_MODEL_ALIAS: qwen3.5-4b
      MUTA_RT_AUTO_DOWNLOAD: "0"
      MUTA_RT_DRAFT_MODEL: /app/models/draft/Qwen3.5-0.8B-Q4_K_M.gguf
      MUTA_RT_STARTUP_TIMEOUT_S: "900"
      MUTA_RT_REQUEST_TIMEOUT_S: "600"
      TUTOR_ROOT: /app
      HF_HOME: /app/models/.cache/huggingface
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://localhost:8000/v1/ready | grep -q '\"ready\":true'"]
      interval: 10s
      timeout: 5s
      retries: 30
      start_period: 300s
  frontend:
    build: { context: ., dockerfile: docker/frontend.Dockerfile }
    platform: linux/amd64
    depends_on:
      backend: { condition: service_healthy }
    ports: [ "3000:80" ]
    healthcheck:
      test: ["CMD-SHELL", "wget -q -O /dev/null http://127.0.0.1/"]
      interval: 5s
      timeout: 3s
      retries: 5
volumes:
  muta-pgdata:
```
- [ ] **Step 6:** Rewrite `run.sh` (full replacement): no-flag path = check `docker` + `docker compose version` → `docker compose build` when images missing or `--build` given → model presence check (all six tier-A paths + draft) and if missing: `docker compose run --rm backend python3.10 scripts/fetch_models.py --with-draft --mmproj-precision f16` (writes land on the host mount; idempotent via sha256 skip) → `docker compose up -d --wait` → print `http://localhost:3000` (mic requires a secure context — localhost qualifies, LAN IPs don't; say so in the failure hint) → on `--wait` failure, print `docker compose logs backend --tail 50` hint. Subcommands: `./run.sh down` (no `-v`), `./run.sh logs`. Delete `run_native`/`run_tui`/`run_docker`/REPL paths.
- [ ] **Step 7:** Verify end-to-end: `./run.sh` → three containers healthy (`docker compose ps`); `curl -s localhost:8000/v1/ready` shows all checks true; SSE works through the proxy:
```bash
curl -N -s localhost:3000/v1/chat/stream -H 'content-type: application/json' \
  -d '{"student_id":"smoke","message":"What is 2+2? One short hint."}'
```
- [ ] **Step 8:** Commit (including the updated `models/pins.lock.json` + `models/MANIFEST.json` from the first draft fetch).

### Task T5: Conversation/attachment API + contract — TDD

**Files:** Modify `orchestrator/gateway/routes.py`, `contracts/models.py`, `contracts/tests/test_contract_smoke.py`; regenerate `contracts/openapi.yaml`

**Interfaces produced (contracts/models.py):**
```python
class AttachmentRef(BaseModel):  id: int; kind: str; mime: str
class MessageOut(BaseModel):     id: int; role: str; content: str; created_at: str; attachments: list[AttachmentRef] = []
class ConversationOut(BaseModel): id: str; student_id: str; title: str | None = None; mode: str | None = None; updated_at: str; created_at: str
class ConversationList(BaseModel): conversations: list[ConversationOut] = []
class MessageList(BaseModel):     conversation_id: str; messages: list[MessageOut] = []
class TranscribeResponse(BaseModel): text: str; attachment_id: int | None = None
# ChatRequest gains: attachment_ids: list[int] = []
# VisionReply gains: attachment_id: int | None = None
```

- [ ] **Step 1:** Failing contract-smoke tests for: `GET /v1/conversations?student_id=x` (200, list shape), `GET /v1/conversations/{id}/messages` (200 + 404-for-unknown), `DELETE /v1/conversations/{id}` (200), `GET /v1/attachments/{id}` (404 unknown), `/v1/chat/stream` present in the OpenAPI paths.
- [ ] **Step 2:** Implement routes (all thin wrappers over the store via `get_engine().store`): list_conversations, list_messages (+attachment refs), delete_conversation, `GET /v1/attachments/{id}` → `Response(content=row["data"], media_type=row["mime"])`. Promote `/v1/chat/stream` (`include_in_schema=True`, `responses={200: {"content": {"text/event-stream": {}}}}`, SSE headers `Cache-Control: no-cache`, `X-Accel-Buffering: no`).
- [ ] **Step 3:** `tutor_vision`: accept optional `conversation_id: str | None = Form(None)`; persist the prepared image via `store.add_attachment("image", mime, prepared.data, conversation_id=...)`; return `attachment_id`.
- [ ] **Step 4:** `/v1/chat` + `/v1/chat/stream`: honor `attachment_ids` — after the user message is persisted, `store.link_attachment(aid, cid, message_id)` for each. New conversations get `title=message[:80]` (pass through `ChatEngine` open path).
- [ ] **Step 5:** `make contract`; commit YAML + code + tests.

### Task T6: Telemetry — TDD

**Files:** Modify `bench/sampler.py` (extract reusables), `orchestrator/gateway/routes.py`, `contracts/models.py`; Create `orchestrator/telemetry.py`; Test `orchestrator/tests/test_telemetry.py` (new)

**Interfaces produced:** `bench/sampler.py`: `family(pids) -> list[psutil.Process]` (walk `[root]+children(recursive=True)`, dedup by pid) and module-level `read_temp_c() -> float | None` (extracted from `ThermalSampler._read_temp`, which now delegates; `test_sampler.py` stays green). `orchestrator/telemetry.py`:
```python
class TelemetryHub:                      # process-wide singleton, get_hub()
    def start(self) -> None             # daemon thread, 1 Hz: rss_bytes = sum(family(os.getpid()) rss);
                                        # peak monotonic since boot; temp = read_temp_c() (cache "unavailable" after
                                        # first None so we don't shell out to `sensors` every second)
    def begin(self, cid) / end(self, cid)          # generating flag
    def tick(self, cid, n_tokens: int)             # per content-delta; deque[(monotonic, n)]
    def snapshot(self, cid) -> TelemetrySnapshot   # tok/s = tokens in trailing 2 s window / window; None when no window
class TelemetrySnapshot(BaseModel):   # contracts/models.py
    rss_gb: float; peak_rss_gb: float
    cpu_temp_c: float | None = None; throttled: bool | None = None
    tokens_per_second: float | None = None; generating: bool = False
```
`throttled = None if temp is None else temp > 85.0`. Hub state is plain attributes updated by the sampling thread, read by async handlers (atomic reads; bounded memory — **do not** reuse `TreeSampler`, it appends samples unboundedly).

- [ ] **Step 1:** Failing unit tests: rolling tok/s window math; snapshot with temp=None → `throttled is None`; peak monotonicity; `read_temp_c()` returns None when `psutil.sensors_temperatures` is empty and `sensors` is absent (monkeypatch).
- [ ] **Step 2:** Implement sampler extraction + hub; `pytest bench/ orchestrator/ -q` green.
- [ ] **Step 3:** Wire: hub started in lifespan; `chat_stream`'s generator calls `hub.begin(cid)` / `hub.tick(cid, 1)` per content delta / `hub.end(cid)` in `finally`.
- [ ] **Step 4:** Routes: `GET /v1/conversations/{id}/telemetry` (snapshot, `response_model=TelemetrySnapshot`) and `GET /v1/conversations/{id}/telemetry/stream` — **async** generator (sync generators occupy threadpool threads), 1 Hz `data: {json}\n\n`, SSE headers as in T5. GET means the browser's native `EventSource` works.
- [ ] **Step 5:** `make contract`; verify in compose: open the stream while a chat generates — tok/s non-null during generation, temp null on macOS. Commit.

### Task T7: Frontend (Claude-styled chat UI)

**Files:** Create `ui/index.html`, `ui/styles.css`, `ui/app.js` (worklet + audio JS land in T8); Modify `docker/frontend.Dockerfile` only if asset paths change

**Design spec (concrete, so styling isn't improvised):** warm neutral palette — page `#faf9f5`, sidebar `#f0eee6`, text `#3d3929`, accent/user-bubble tint `#da7756` at 8% fill with `#bd5d3a` accents, borders `#e8e6dc`; headings + assistant prose in a serif stack `ui-serif, Georgia, "Times New Roman", serif`; UI chrome in `-apple-system, "Segoe UI", sans-serif`; centered chat column `max-width: 48rem`; user messages as right-aligned rounded bubbles (12px radius), assistant messages as plain prose on the page background; sticky composer at the bottom in a rounded card with soft shadow; left sidebar (collapsible) listing conversations + "New chat"; telemetry strip as a slim fixed bar above the composer: `RAM 3.2 GB · peak 3.4 GB · — °C · throttle — · 4.1 tok/s`, rendering "—" for every `null`.

Mechanics (all in `app.js`, no framework, no build step):
- `student_id`: `localStorage["muta-student"] ||= crypto.randomUUID()`.
- Sidebar: `GET /v1/conversations?student_id=…`; click → `GET /v1/conversations/{id}/messages` → render history (attachments render as `<img src="/v1/attachments/{id}">` thumbnails / audio chips); delete button → `DELETE /v1/conversations/{id}`.
- Send (Enter; Shift+Enter newline): POST `/v1/chat/stream` and parse SSE from `fetch` (no EventSource for POST):
```js
const res = await fetch("/v1/chat/stream", {method: "POST", headers: {"content-type": "application/json"},
  body: JSON.stringify({student_id, message, conversation_id, attachment_ids})});
const reader = res.body.getReader(); const dec = new TextDecoder(); let buf = "";
for (;;) {
  const {done, value} = await reader.read(); if (done) break;
  buf += dec.decode(value, {stream: true});
  let i; while ((i = buf.indexOf("\n\n")) >= 0) {
    const frame = buf.slice(0, i); buf = buf.slice(i + 2);
    for (const line of frame.split("\n")) if (line.startsWith("data: ")) handle(JSON.parse(line.slice(6)));
  }
}
```
  `handle`: `reasoning` → append into a collapsed "Thinking…" `<details>` block; `delta` → append text node to the live assistant div; `done` → capture `conversation_id`, then finalize the bubble: `marked.parse` → `DOMPurify.sanitize` → `innerHTML` → `renderMathInElement(el, {delimiters: [{left:"$$",right:"$$",display:true},{left:"$",right:"$",display:false},{left:"\\(",right:"\\)",display:false},{left:"\\[",right:"\\]",display:true}]})`. Plain text during streaming; one render pass at the end (KaTeX per token is pathological).
- Telemetry: on generation start, `new EventSource("/v1/conversations/{id}/telemetry/stream")`; update strip per event; close a few seconds after `done`.
- Image upload button + drag-drop (`dragover`/`drop` on the chat column, overlay hint): POST `/v1/tutor/vision` (`multipart`: `session_id`=student_id, `conversation_id` if known, `image`) → show thumbnail chip in the composer → on send, prefix the message with the transcription context: `Problem transcribed from my image: "<transcription>"\n\n<user text>` and pass `attachment_ids=[attachment_id]`. `accepted:false` → toast the `detail`, degrade to text.
- Audio upload button + drag-drop: POST `/v1/audio/transcribe` (T8) → put `text` into the composer and auto-send with `attachment_ids`.
- Vendored assets referenced relatively: `vendor/katex/katex.min.css`, `vendor/katex/katex.min.js`, `vendor/katex/contrib/auto-render.min.js`, `vendor/marked.min.js`, `vendor/purify.min.js`.
- Static HTML/CSS/JS lives in `ui/` at repo root and is COPY'd by the frontend image; it is **not** served by FastAPI (`ui/dist` mount stays dormant).

- [ ] **Step 1:** Build the page skeleton + styles per spec; placeholder replaced.
- [ ] **Step 2:** Implement conversations sidebar + history reload + delete.
- [ ] **Step 3:** Implement streaming send loop + thinking block + KaTeX/markdown finalize.
- [ ] **Step 4:** Implement telemetry strip (EventSource; "—" for nulls).
- [ ] **Step 5:** Implement image + audio upload/drag-drop chips (audio path finishes in T8).
- [ ] **Step 6:** `docker compose build frontend && docker compose up -d` → verify in browser: stream renders token-by-token; `$\int x^2\,dx$` renders; image Q&A works; conversation survives `docker compose down && ./run.sh` (acceptance 4). Commit.

### Task T8: Audio — sherpa wiring, transcribe endpoint, voice WS loop — TDD

**Files:** Create `orchestrator/audio/audio.yaml`, `orchestrator/gateway/audio_routes.py`, `ui/worklet.js`; Modify `orchestrator/audio/config.py`, `orchestrator/audio/engines.py`, `orchestrator/main.py` (include router), `contracts/models.py` (TranscribeResponse already in T5 — keep here if deferred), `ui/app.js`, `pyproject.toml` (`sherpa-onnx>=1.10` main deps); Test `orchestrator/tests/test_audio_engines.py` (new), extend `orchestrator/tests/test_audio_service.py`

Fixes required first (all verified bugs):
- `orchestrator/audio/config.py`: `DEFAULT_CONFIG = Path(__file__).parent / "audio.yaml"` (was `deploy/etc/audio.yaml` — deleted in T9); `VadConfig.model` default → `"models/asr/silero_vad.onnx"` (underscore — the dash file doesn't exist); `TtsConfig` gains per-voice `data_dir`; drop the hardcoded 24000 assumption.
- `orchestrator/audio/engines.py` `SherpaTts`: instantiate exactly as the proven `scripts/verify_models.py:363-371` — `model=<voice>.onnx`, `tokens=<dir>/tokens.txt` (currently passes the `.onnx.json` — bug), `data_dir=<dir>/espeak-ng-data`; capture the **actual** `audio.sample_rate` returned by `synthesize()` (en_US-joe-medium is 22050 Hz; trusting the config would play 9% fast).
- New `orchestrator/audio/audio.yaml`: engine sherpa-onnx, model_dir `models/asr/moonshine-tiny-en-int8`, vad model `models/asr/silero_vad.onnx`, voice `en` → `models/tts/piper/en_US-joe-medium.onnx` + tokens + espeak-ng-data, paths resolved against `TUTOR_ROOT`.
- New `SileroVad` engine class in `engines.py` (crib `scripts/verify_models.py:328-345`): `sherpa_onnx.VadModelConfig` + `VoiceActivityDetector`; `available=False` + fallback to the existing `Endpointer` energy policy when sherpa/model missing.

**Voice WS protocol** (`WS /v1/audio/voice` via `@router.websocket` in `audio_routes.py`, included in the gateway router):
- client → server: text `{"type":"start","student_id","conversation_id":null|str,"mode":"socratic"}`, then binary 16 kHz mono int16 PCM frames (~320 ms), text `{"type":"stop"}` (force endpoint), `{"type":"barge"}` (cancel).
- server → client: `{"type":"transcript","text","conversation_id"}` at VAD endpoint; `{"type":"reasoning"|"delta","text"}` during generation; per sentence `{"type":"tts_start","sample_rate":<actual>}` + binary PCM frames + `{"type":"tts_end"}`; finally `{"type":"done"}`. On missing ASR: `{"type":"error","reason":"asr-unavailable","fallback":"type your question"}` and close.
- Handler stays a single async function: VAD `accept` inline (cheap C++), ASR finalize via `run_in_threadpool`, LLM via `starlette.concurrency.iterate_in_threadpool(engine.stream_events_chat(...)[1])`, sentence-split content deltas (`[.!?]` boundaries) → `orchestrator/audio/mathspeech.to_speech(sentence)` → `run_in_threadpool(tts.synthesize)` → `send_bytes`. Barge-in: set a flag, close the iterator (T1's partial-persist keeps the half-reply), stop sending TTS. Half-duplex MVP: the **client** mutes mic frames during playback.

`POST /v1/audio/transcribe`: multipart `audio` file (+ optional `conversation_id`) → `ffmpeg -i pipe:0 -f s16le -ac 1 -ar 16000 pipe:1` (subprocess, 30 s timeout) → ASR → persist attachment (`kind="audio"`, original bytes) → `TranscribeResponse{text, attachment_id}`. 503 with a clear message when ASR unavailable.

**Client audio (`ui/worklet.js` + `app.js`):** mic button → `getUserMedia({audio:true})` → one persistent `AudioContext` created on this click (it is also the playback context — creating it on the user gesture is what lets TTS auto-play later without another click) → `AudioWorklet` capturing at native rate, posting Float32 chunks; main thread linear-resamples to 16 kHz, converts to int16, batches ~320 ms, `ws.send(ArrayBuffer)`. `ScriptProcessorNode` fallback behind a feature check. Playback: int16 frames → `AudioBuffer` at the handshake `sample_rate` → gapless scheduling on the same context. Voice replies stream into the normal chat transcript too (transcript + deltas render as a normal turn).

- [ ] **Step 1:** Failing engine tests: `SherpaTts` config construction (monkeypatched sherpa module) uses `tokens.txt` + `data_dir`; `SileroVad` degrades to `available=False` without sherpa; config loads the new default path; yaml round-trip resolves the underscore VAD path.
- [ ] **Step 2:** Implement fixes + `SileroVad`; green.
- [ ] **Step 3:** Failing route tests: transcribe 503-when-unavailable path; voice WS start→error handshake with Null engines (TestClient websocket).
- [ ] **Step 4:** Implement `audio_routes.py` (transcribe + voice loop); green locally (engines Null on host — protocol tests only).
- [ ] **Step 5:** Frontend mic capture + playback + barge-in; audio upload wiring.
- [ ] **Step 6:** In compose (sherpa wheels present in the image): real round-trip — click mic, speak, get spoken reply with no further clicks (acceptance 2). `make contract` if models changed. Commit.

### Task T9: Deletions + de-referencing (paired sub-steps, tree green after each)

**Files:** Delete per the KEEP/DELETE table; Modify `Makefile`, `pyproject.toml`, `scripts/test_fetch_models.py`

- [ ] **Step 1:** `git rm runtime/cli.py runtime/run.sh runtime/Dockerfile`; drop Makefile `chat`; `pytest -q` green.
- [ ] **Step 2:** `git rm bench/tui.py bench/test_tui.py`; drop Makefile `tui`; remove `textual` from dev extras (keep `rich`).
- [ ] **Step 3:** `git rm -r bundle/`; `pyproject.toml`: remove `"bundle"` from `packages` and `testpaths`; drop Makefile `manifest`; delete `test_packaging_accepts_every_licence_we_actually_pin` (imports `bundle.manifest`) from `scripts/test_fetch_models.py`.
- [ ] **Step 4:** `git rm -r deploy/`; drop Makefile `engine`/`stage`/`selftest`/`package`; delete `test_declared_bundle_licences_match_the_pinned_artifacts` (reads `deploy/licenses.json`). (`orchestrator/audio` already re-homed its config in T8.)
- [ ] **Step 5:** Makefile additions/repurpose: `build` → `docker compose build`; new `up` → `docker compose up -d --wait`; new `down`; keep `dev test lint fmt contract contract-test serve model fetch-models verify-models profiles core-cmd kv-budget index audio bench profile monitor smoke`. Fix `.PHONY`.
- [ ] **Step 6:** Full `pytest -q` + `ruff check .` green; `docker compose build` still succeeds (no `COPY` references to deleted paths). Commit.

### Task T10: Docs (`RUN.md`, `CLAUDE.md`)

**Files:** Rewrite `RUN.md`; Modify `CLAUDE.md`

- [ ] **Step 1:** `RUN.md` rewrite: `./run.sh` front door (compose), the three containers + ports (frontend :3000, backend :8000, db :15432), model provisioning (incl. the `--mmproj-precision f16` + `--with-draft` invocation and the 0.8B-draft deviation note), curl walkthrough (chat, stream, vision, transcribe, telemetry), config table (`MUTA_RT_DB_URL` etc.), troubleshooting: Docker Desktop memory ≥ 12 GB recommended (core ~3.3 GB + ephemeral vision ~3.3 GB + draft + PG), enable Rosetta for x86 emulation on Apple silicon (QEMU-TCG is ~1 tok/s class), mic requires `http://localhost` (secure context), conversations persist in the `muta-pgdata` volume (`docker compose down -v` is the only way to lose them).
- [ ] **Step 2:** `CLAUDE.md`: add a `dev`-branch preamble (long-lived 3-container architecture; `main` carries the competition single-container build) and update Current state / Architecture / Commands / layout sections to match (delete references to `deploy/`, `bundle/`, TUI, entrypoint; document compose topology, Postgres store, telemetry, voice loop). Leave README/ROADMAP untouched.
- [ ] **Step 3:** Commit.

---

## Verification (acceptance criteria, end-to-end)

1. **Fresh-clone path:** `git clone … && git checkout dev && ./run.sh` → wait for `--wait` → `docker compose ps` shows db/backend/frontend all `healthy`; browser at `http://localhost:3000` streams a chat reply token-by-token; KaTeX renders `$x^2$`.
2. **Vision:** upload a photo of a math problem (button and drag-drop) → transcription-prefixed question → streamed answer. `curl -F session_id=t -F image=@work.jpg localhost:3000/v1/tutor/vision` returns `accepted:true` + `attachment_id`.
3. **Voice:** click mic, ask aloud, stop talking → transcript appears, reply streams, spoken reply auto-plays — zero additional clicks.
4. **Telemetry:** strip live-updates during generation (RAM/peak always numeric; temp/throttle "—" on macOS, numeric on a Linux host with hwmon); `curl localhost:3000/v1/conversations/<id>/telemetry` returns the snapshot with `null`s where unavailable.
5. **Persistence:** note conversation id → `docker compose down && ./run.sh` → conversation and its messages/attachments reload in the sidebar.
6. **main untouched:** `git rev-parse main` == `0d91d26…`; `git status` on main clean after checkout (snapshot commit lives on dev).
7. **Suites:** `make test` green (Postgres tests run against the compose db at `127.0.0.1:15432`, skip cleanly when it's down); `ruff check .` clean; `make contract` produces no diff (YAML committed in sync).
8. Adversarial review pass (project protocol): reviewer in a fresh context attacks the Postgres port (ordering semantics, partial-persist), the voice WS loop, and the compose healthcheck/ordering before the branch is declared done.
