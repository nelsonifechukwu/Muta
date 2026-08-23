# Configuration reference

Every environment variable that affects the running system, in one place. They are
currently spread across **three uncoordinated families** and were documented nowhere
together; `RUN.md` covers only the `MUTA_RT_*` subset plus `TUTOR_ROOT`. This is the full
map.

Columns: **Variable | Default | What it does | Where read (`file:line`)**. "Default" is the
code default; where `docker-compose.yml` overrides it for the deployed backend, that is
noted in the same cell as `(compose: …)`.

> **Which family wins?** Read [§Families and precedence](#families-and-precedence) first —
> `MUTA_RT_*` and `TUTOR_*`/`PROFILE` overlap and, for the engine port and slot count, they
> disagree. That section says which one the running 3-container stack actually obeys.

---

## Families and precedence

There are three env-var families, and they are **not** a single coherent surface:

1. **`MUTA_RT_*`** (`runtime/config.py`, Pydantic `RuntimeConfig`, prefix `MUTA_RT_`) — the
   **primary, authoritative** config for the 3-container stack. The gateway's chat client
   and the auto-started `llama-server` both read `RuntimeConfig`. **This is the family to
   use.** `docker-compose.yml` sets the deployed backend almost entirely through it.
2. **`TUTOR_*` / `PROFILE`** (`runtime/profiles.py` and friends) — the serving-profile /
   `BundlePaths` world inherited from the **retired single-container/systemd build**
   (`archive/main-competition-build`; see `CLAUDE.md`). **Partially live, partially dead** on
   this stack (details below). Do not use it to configure the main text engine.
3. **`MUTA_*` (non-`RT`) one-offs** — cloud boost, web grounding, the connectivity probe,
   the degradation-ladder cap, and the compose model-interpolation vars. Small but important
   (two of them are the off-device data-flow switches — see
   [`privacy-and-data-flows.md`](privacy-and-data-flows.md)).

**The conflict that matters — engine port and slot count.** Both families define an engine
port and a slot count, and they differ:

| Concern | `MUTA_RT_*` value | `TUTOR_*`/`PROFILE` value | Who wins on the running stack |
|---|---|---|---|
| Text-engine port | `MUTA_RT_SERVER_PORT` = **8080** | `TUTOR_CORE_PORT` = **8081** | **`MUTA_RT_SERVER_PORT` (8080)** — the auto-started engine binds it (`server.py:65`) and the gateway's chat client talks to it (`deps.py:46`, `config.py:158`). |
| Slot count | `MUTA_RT_N_PARALLEL` = **2** | profile `n_parallel` (e.g. `classroom` = **6**) | **`MUTA_RT_N_PARALLEL` (2)** for the *actual* engine (`server.py:70`). |

The `TUTOR_*`/`PROFILE` engine values are read only by machinery that is **misaligned or
inert** on the 3-container stack:

- `get_slot_client()` (`deps.py:101-106`) dials `TUTOR_CORE_PORT` (**8081**) — but nothing
  serves on 8081 here (the engine is on 8080). So the KV suspend/resume endpoints
  (`/v1/session/{id}/suspend|resume`) and the `engine.slots` block of `/v1/metrics`
  effectively point at a **dead port**.
- `get_sessions()` (`deps.py:114-143`) sizes admission from the profile's `n_parallel`
  (`classroom` = **6**), which **disagrees** with the engine's real `--parallel 2`.
- `core_text_command()` (`profiles.py:254`) — the whole `TUTOR_*`-driven CORE-TEXT
  invocation — is **not executed** on this stack; the engine command is built by
  `runtime/server.py` from `RuntimeConfig` instead.

**Legacy / redundant, safe to ignore on this stack:** `TUTOR_CORE_PORT`,
`TUTOR_CORE_THREADS`, `TUTOR_CORE_THREADS_BATCH`, `TUTOR_SPECULATION`, `TUTOR_DRAFT_PORT`,
`PROFILE`'s slot/context numbers, and the entire `orchestrator/config.py` `MUTA_*` split-mode
family (`MUTA_DEPLOY_MODE`, `MUTA_LLAMA_SERVER_URL`, `MUTA_MATH_URL`, …) — that `settings`
singleton is **imported nowhere** in the active code path.

**Still live from the `TUTOR_*` family:** `TUTOR_ROOT` (model/data root for vision + audio +
bundle paths), and the vision-instance knobs `TUTOR_VISION_PORT`, `TUTOR_VISION_THREADS`,
`TUTOR_KV_TYPE`, `TUTOR_TTS_ENGINE`, plus the audio/retrieval sub-app ports — because
`core_vision_command()` and the audio/retrieval apps *do* run.

---

## Family 1 — `MUTA_RT_*` (RuntimeConfig, the primary surface)

Source: `runtime/config.py` (prefix `MUTA_RT_`, also honours a local `.env`). Defaults below
are the class defaults; the `Qwen3-0.6B` smoke-fixture defaults are what ship in
`config.py`, while `docker-compose.yml` overrides most of them for the real 4B deployment.

### Model provisioning

| Variable | Default | What it does | Where read |
|---|---|---|---|
| `MUTA_RT_MODEL_SOURCE` | `local` | `local` (use a GGUF in `model_dir`) or `hf` (download) | `config.py:51` |
| `MUTA_RT_MODEL_DIR` | `models/Qwen3-0.6B` *(compose: `/app/models/core`)* | directory holding the core GGUF | `config.py:52`, compose `:51` |
| `MUTA_RT_MODEL_FILE` | `Qwen3-0.6B-Q4_K_M.gguf` *(compose: `Qwen3.5-4B-IQ4_XS.gguf`)* | core GGUF filename | `config.py:53`, compose `:52` |
| `MUTA_RT_HF_REPO` | `unsloth/Qwen3-0.6B-GGUF` | HF repo to pull from when source=`hf`/auto-download | `config.py:54` |
| `MUTA_RT_HF_FILE` | `Qwen3-0.6B-Q4_K_M.gguf` | HF filename to pull | `config.py:55` |
| `MUTA_RT_BASE_REPO` | `Qwen/Qwen3-0.6B` | provenance only (safetensors source) | `config.py:56` |
| `MUTA_RT_AUTO_DOWNLOAD` | `true` *(compose: `0`)* | download from HF if the local file is missing | `config.py:59`, compose `:66` |

### llama-server (the selected text or multimodal engine)

| Variable | Default | What it does | Where read |
|---|---|---|---|
| `MUTA_RT_LLAMA_SERVER_BIN` | `None` | explicit `llama-server` path; else search build dir then `PATH` | `config.py:62`, `server.py:33` |
| `MUTA_RT_SERVER_HOST` | `127.0.0.1` | engine bind host (loopback) | `config.py:63`, `server.py:64` |
| `MUTA_RT_SERVER_PORT` | `8080` | **engine bind port — the one the gateway actually talks to** | `config.py:64`, `server.py:65` |
| `MUTA_RT_MODEL_ALIAS` | `qwen3-0.6b` *(compose: `qwen3.5-4b`)* | `/v1/models` alias | `config.py:65`, compose `:53` |
| `MUTA_RT_MMPROJ_PATH` | `None` *(Compose defaults to the paired 4B projector; `run.sh` supplies the verified 0.8B projector for the recommended model)* | exact projector loaded into the selected `llama-server`; absent means text-only. Catalog selection verifies its size and SHA-256 before advertising image input | `config.py`, `model_catalog.py`, `server.py`, compose, `run.sh` |
| `MUTA_RT_IMAGE_MIN_TOKENS` | `1024` | minimum visual-token budget passed as `--image-min-tokens`; the guarded image is downscaled before this engine sees it | `config.py`, `server.py` |
| `MUTA_RT_IMAGE_MAX_TOKENS` | `2048` | hard visual-token ceiling passed as `--image-max-tokens` and reserved by ChatEngine; must be ≥ the minimum | `config.py`, `server.py`, `chat.py`, `deps.py` |
| `MUTA_RT_N_CTX` | `4096` *(native: `12288`; Compose: `8192`)* | total unified context; hard request fitting uses `n_ctx / n_parallel` as each concurrent lane's guaranteed share. Compose gives each of two lanes 4096 tokens: a 2048-token image ceiling plus 2048 for the real tutor prompt, safety reserve and a useful reply | `config.py`, `deps.py`, compose, `run.sh` |
| `MUTA_RT_N_THREADS` | `None` → P-cores on Apple silicon, engine default elsewhere *(compose: `8`)* | decode threads | `config.py:73`, compose `:81` |
| `MUTA_RT_N_GPU_LAYERS` | `0` | GPU offload layers (also read by the vision command) | `config.py:76`, `profiles.py:398` |
| `MUTA_RT_N_PARALLEL` | `2` | **engine slots (the real slot count)** | `config.py:83`, `server.py:70` |
| `MUTA_RT_CTX_CHECKPOINTS` | `2` | recurrent-state checkpoints per slot (~50 MiB each) | `config.py:89`, `server.py:71` |
| `MUTA_RT_CACHE_RAM_MIB` | `256` | host-RAM prompt cache cap (`--cache-ram`; engine default 8192) | `config.py:90`, `server.py:72` |
| `MUTA_RT_KV_UNIFIED` | `true` | slots share the full `-c` window (explicit `-np` would split it) | `config.py:95`, `server.py:75` |
| `MUTA_RT_N_THREADS_BATCH` | `None` → P-cores *(compose: `10`)* | prefill threads | `config.py:96`, compose `:82` |
| `MUTA_RT_N_BATCH` | `512` | logical batch size | `config.py:104`, `server.py:76` |
| `MUTA_RT_N_UBATCH` | `128` | physical batch size (compute-buffer size) | `config.py:105`, `server.py:77` |
| `MUTA_RT_CACHE_TYPE_K` | `q8_0` | K-cache quantization | `config.py:106`, `server.py:78` |
| `MUTA_RT_NO_REPACK` | `false` | pass `--no-repack` (keep weights file-backed vs repack into anon RAM) | `config.py:115`, `server.py:82` |
| `MUTA_RT_REASONING_BUDGET` | `512` | launch `--reasoning-budget`: default max thinking tokens before the answer is forced (`-1` = unrestricted) | `config.py:116`, `server.py:79` |
| `MUTA_RT_REASONING_BUDGET_EXTENDED` | `2048` | per-request thinking cap for the UI's "Extended" level — sent as `reasoning_budget_tokens` on the chat request (no engine relaunch); older engine pins ignore it | `config.py`, `routes.py::_apply_thinking` |
| `MUTA_RT_ENABLE_THINKING` | `true` *(compose: `1`)* | Qwen3 hybrid thinking on/off (via `--jinja`); overridable per request by the UI's reasoning selector | `config.py:121`, compose `:60` |
| `MUTA_RT_EXTRA_SERVER_ARGS` | `[]` | extra raw args appended to the `llama-server` command | `config.py:122`, `server.py:89` |
| `MUTA_RT_STARTUP_TIMEOUT_S` | `120.0` *(compose: `900`)* | model-load wait before giving up | `config.py:123`, compose `:88` |
| `MUTA_RT_REQUEST_TIMEOUT_S` | `120.0` *(compose: `600`)* | per-request client timeout (between stream chunks) | `config.py:126`, compose `:89` |
| `MUTA_RT_SPEC_TYPE` | `none` | speculation: `none` \| `draft-simple` \| `ngram-simple` | `config.py:140`, `server.py:96` |
| `MUTA_RT_DRAFT_MODEL` | `None` *(compose: `/app/models/draft/Qwen3.5-0.8B-Q4_K_M.gguf`)* | draft GGUF for `draft-simple`; absent → speculation off | `config.py:141`, compose `:86` |
| `MUTA_RT_DRAFT_MAX` | `8` | `--spec-draft-n-max` | `config.py:142`, `server.py:104` |
| `MUTA_RT_DRAFT_MIN` | `1` | `--spec-draft-n-min` | `config.py:143`, `server.py:105` |
| `MUTA_RT_AUTOSTART` | `false` *(compose: `1`)* | gateway lifespan starts/supervises `llama-server` | `config.py:145`, `main.py:97`, compose `:47` |

### Muta Power policy

These controls affect Muta-owned optional work only. They do not change the operating
system's CPU governor or suspend the computer. The learner-facing switch is on by default;
operators can disable the policy globally with `MUTA_RT_POWER_OPTIMIZATION=0`.

| Variable | Default | What it does | Where read |
|---|---|---|---|
| `MUTA_RT_POWER_OPTIMIZATION` | `true` | master switch for battery-aware request shaping and critical-reserve protection | `config.py`, `deps.py` |
| `MUTA_RT_POWER_POLL_INTERVAL_S` | `15` | minimum seconds between host battery reads | `config.py`, `power.py` |
| `MUTA_RT_POWER_SENSOR_GRACE_S` | `120` | keep an already-active Critical reserve through a brief total sensor/provider failure | `config.py`, `power.py` |
| `MUTA_RT_POWER_CRITICAL_PERCENTAGE` | `12` | enter Critical mode at or below this battery percentage | `config.py`, `power.py` |
| `MUTA_RT_POWER_CRITICAL_TIME_S` | `1800` | enter Critical mode at or below this estimated time remaining | `config.py`, `power.py` |
| `MUTA_RT_POWER_HYSTERESIS_PERCENTAGE` | `3` | extra percentage required before leaving Critical mode | `config.py`, `power.py` |
| `MUTA_RT_POWER_HYSTERESIS_TIME_S` | `900` | extra estimated seconds required before leaving Critical mode | `config.py`, `power.py` |
| `MUTA_RT_POWER_ECO_REASONING_BUDGET` | `256` | Auto-mode thinking-token cap while discharging | `config.py`, `power.py` |
| `MUTA_RT_POWER_ECO_MAX_TOKENS` | `800` | ordinary response cap while discharging | `config.py`, `power.py` |
| `MUTA_RT_POWER_CRITICAL_MAX_TOKENS` | `512` | ordinary response cap in Critical mode; thinking is also disabled | `config.py`, `power.py` |

Critical reserve still blocks legacy auxiliary vision and TTS work so the shared laptop retains
capacity for tutoring. Browser image questions now use the already-selected chat engine rather
than that auxiliary process. Turning the learner switch off restores ordinary response budgets,
but does not bypass the host-wide safeguard. Explicit Extended reasoning and schema-constrained
assessment responses retain their requested budgets in every mode.

### Persistent memory

| Variable | Default | What it does | Where read |
|---|---|---|---|
| `MUTA_RT_DB_URL` | `sqlite:///data/muta.sqlite3` *(compose overrides: `postgresql://muta:muta@db:5432/muta`)* | Persistence URL. SQLite is the daemon-free host/portable default; PostgreSQL remains the explicit Compose control. | `config.py`, `memory.py`, `sqlite_memory.py`, compose, `run.sh` |
| `MUTA_RT_MAX_HISTORY_MESSAGES` | `20` | multi-turn context trim; **also the max turns cloud boost sends off-device** | `config.py:151` |
| `MUTA_RT_HISTORY_TOKEN_BUDGET` | `1200` | estimated-token ceiling for replayed history; trims oldest prompt turns without deleting stored history | `config.py`, `chat.py` |
| `MUTA_RT_CONTEXT_SAFETY_TOKENS` | `192` | chat-template/context margin reserved before fitting `max_tokens` | `config.py`, `chat.py` |
| `MUTA_RT_STREAM_RETRY_ATTEMPTS` | `5` | bounded automatic resumes for transient streamed transport failures | `config.py`, `chat.py` |
| `MUTA_RT_STREAM_RETRY_BACKOFF_S` | `0.5` | initial exponential resume backoff, capped at four seconds | `config.py`, `chat.py` |

### `MUTA_RT_`-prefixed but **not** RuntimeConfig fields

These carry the `MUTA_RT_` prefix but are read directly from `os.environ`, not through
`RuntimeConfig` — an inconsistency worth knowing when auditing:

| Variable | Default | What it does | Where read |
|---|---|---|---|
| `MUTA_RT_VISION_STARTUP_S` | `60.0` *(compose: `300`)* | cold-spawn wait for the vision `llama-server` | `runtime/vision.py:53`, compose `:92` |
| `MUTA_RT_VISION_MEMORY_MAX_MIB` | `4352` | legacy ceiling for the standalone auxiliary vision manager. The browser image/chat path does not start that process, and the Host planner no longer reserves it | `runtime/profiles.py`, `runtime/vision.py`, compose |
| `MUTA_RT_LLAMA_CLI_BIN` | `None` | `llama-cli` path used by `verify_models` | `scripts/verify_models.py:53` |

`MUTA_OFFLINE=1` is set automatically by the Linux-native launcher. It forces the cached
connectivity verdict to `false` without making an HTTP probe, so the portable/experiment path
does not emit background network traffic. Compose leaves it unset for deliberate online-feature
testing.

---

## Family 2 — `TUTOR_*` / `PROFILE` (profiles / BundlePaths — partly legacy)

Source: `runtime/profiles.py` plus the audio/retrieval apps. See
[Families and precedence](#families-and-precedence) for **which of these are inert on the
3-container stack**. "Live?" flags whether the running stack actually consumes it.

| Variable | Default | What it does | Where read | Live? |
|---|---|---|---|---|
| `TUTOR_ROOT` | `/opt/tutor` *(compose: `/app`)* | root for vision/audio/bundle model + data paths | `profiles.py:166`, `main.py:98`, `audio/config.py:63`, compose `:93` | **Yes** |
| `PROFILE` | `classroom` | selects a `ServingProfile` (context/slots/cache) | `profiles.py:75` | Partly — slot/ctx numbers only feed the (misaligned) session admission + vision cache type |
| `TUTOR_KV_TYPE` | *(profile default `q8_0`)* | overrides KV cache type | `profiles.py:82` | Yes (vision uses `profile.cache_type`) |
| `TUTOR_MLOCK` | *(profile default `false`)* | overrides `mlock` | `profiles.py:84` | Legacy (core-text only) |
| `TUTOR_TTS_ENGINE` | `piper` *(solo-demo: `kokoro`)* | selects the TTS engine | `profiles.py:86` | Yes |
| `TUTOR_CORE_THREADS` | `0` (→ derive from thread table) | decode threads for **core-text** command | `profiles.py:149` | **Legacy** — core-text cmd unused; engine uses `MUTA_RT_N_THREADS` |
| `TUTOR_CORE_THREADS_BATCH` | `0` | prefill threads for **core-text** command | `profiles.py:150` | **Legacy** (as above; use `MUTA_RT_N_THREADS_BATCH`) |
| `TUTOR_VISION_THREADS` | `0` | threads for the **vision** instance | `profiles.py:151` | **Yes** |
| `TUTOR_LLAMA_SERVER_BIN` | *(unset)* | engine binary for `BundlePaths.engine_bin()` (vision spawn) | `profiles.py:202` | Yes (vision) |
| `TUTOR_CORE_PORT` | `8081` | port `get_slot_client()` dials **and** core-text bind port | `deps.py:103`, `profiles.py:273` | **Misaligned** — nothing serves 8081 here (engine is 8080) |
| `TUTOR_VISION_PORT` | `8082` | vision instance bind port | `profiles.py:384` (`port()`) | **Yes** |
| `TUTOR_EMBED_PORT` | `8083` | embed server bind port | `profiles.py:426`, `retrieval/app.py:36` | Sub-app only |
| `TUTOR_ASR_PORT` | `8084` | ASR service bind port | `audio/service.py:150` | Sub-app only |
| `TUTOR_DRAFT_PORT` | `8086` | draft/hint server bind port | `profiles.py:448` | **Legacy** |
| `TUTOR_SPECULATION` | `c` | legacy `b`/`c` speculation gate for core-text | `profiles.py:325` | **Legacy** — use `MUTA_RT_SPEC_TYPE` |
| `TUTOR_AUDIO_CONFIG` | *(bundled `audio.yaml`)* | path to the audio config yaml | `audio/config.py:62` | Yes (audio) |
| `TUTOR_INDEX_DIR` | `${TUTOR_ROOT}/index` | retrieval index directory | `retrieval/app.py:28` | Sub-app only |

> The `orchestrator/config.py` split-mode `MUTA_*` vars (`MUTA_DEPLOY_MODE`,
> `MUTA_LLAMA_SERVER_URL`, `MUTA_MATH_URL`, `MUTA_RETRIEVAL_URL`, `MUTA_PEDAGOGY_URL`,
> `MUTA_EXAM_URL`) are **omitted deliberately**: that `settings` object is imported nowhere in
> the active code path, so setting them has no effect on the running stack.

---

## Family 3 — cloud boost, web grounding, probe, ladder, infra

Small `MUTA_*` (non-`RT`) and infrastructure vars. **All off by default** except where a
compose/env default is shown. The first four are the off-device switches — see
[`privacy-and-data-flows.md`](privacy-and-data-flows.md).

| Variable | Default | What it does | Where read |
|---|---|---|---|
| `MUTA_CLOUD_URL` | *(unset)* | cloud OpenAI-compatible endpoint; **enables cloud boost only with the other two** | `deps.py:55` |
| `MUTA_CLOUD_MODEL` | *(unset)* | cloud model name | `deps.py:56` |
| `MUTA_CLOUD_API_KEY` | *(unset)* | cloud API key (see [secrets handling](#secrets-handling)) | `deps.py:57` |
| `MUTA_SEARCH_URL` | *(unset)* | SearXNG base URL; enables web grounding (with `use_web:true` + online) | `routes.py:192`, `websearch.py:29` |
| `MUTA_NET_PROBE_URL` | `https://huggingface.co` | host the connectivity probe HEADs (~1/min); also gates cloud/web | `connectivity.py:23`, `run.sh:115` |
| `MUTA_NET_PROBE_INTERVAL_S` | `60` | seconds between connectivity probes | `connectivity.py:24` |
| `MUTA_CORE_CAP_MIB` | `4300` *(compose: `5400`)* | degradation-ladder core-RSS cap (MiB) — L4 fires above it | `ladder.py:42`, compose `:63` |
| `MUTA_MODEL_DIR` / `MUTA_MODEL_FILE` / `MUTA_MODEL_ALIAS` | *(unset; compose interpolation)* | **host-side** interpolation for `MUTA_RT_MODEL_*`, exported by `./run.sh --model` | compose `:51-53`, `run.sh:254-256` |

### Frontend / infrastructure

| Variable | Default | What it does | Where read |
|---|---|---|---|
| `BACKEND_UPSTREAM` | `backend:8000` *(native mode: `host.docker.internal:8000`)* | nginx `/v1` reverse-proxy target | compose `:120`, `run.sh:157` |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `muta` / `muta` / `muta` | Postgres bootstrap credentials for the `db` container | compose `:13-15` |
| `HF_HOME` | *(compose: `/app/models/.cache/huggingface`)* | HF cache location (kept inside the mount, resumable) | compose `:96` |
| `HF_HUB_DOWNLOAD_TIMEOUT` / `HF_HUB_ETAG_TIMEOUT` | `30` | HF download/etag timeouts (set if unset) | `scripts/fetch_models.py:48-49` |

---

## Logging

There is **no `MUTA_LOG_LEVEL`** (or any log-level env var). This is a gap, not an omission
in this doc: log level is **hardcoded** to `INFO` in the standalone entrypoints
(`runtime/server.py:187`, `orchestrator/audio/service.py:147`), and under uvicorn (the
deployed path) the app never calls `basicConfig`, so its module loggers
(`muta.gateway.*`, `muta.runtime.*`) inherit uvicorn's configuration. To change verbosity
today you configure uvicorn's logging, not a Muta variable.

---

## Secrets handling

`MUTA_CLOUD_API_KEY` is the only secret in this system. Handle it carefully:

- **Do not commit it.** Never put it in `docker-compose.yml`, in a tracked `.env`, or in any
  file under version control.
- **It is exposed by `docker inspect` if set in the compose `environment:` block.** Any value
  placed there is visible to anyone who can run `docker inspect` on the backend container (and
  appears in `docker compose config` output). That is the wrong place for a key.
- **Prefer an `env_file` or compose secrets.** Point the backend at an untracked `env_file:`
  (git-ignored), or use Docker/compose secrets so the value is mounted rather than baked into
  the container's environment inspection surface. Rotate it if it was ever committed or placed
  inline.
- **Least privilege.** Enabling cloud boost sends children's data off-device (see
  [`privacy-and-data-flows.md`](privacy-and-data-flows.md)); scope the key to the minimum the
  provider allows and prefer leaving all three `MUTA_CLOUD_*` vars unset for school
  deployments.
