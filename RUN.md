# Running Muta

## Start here

```bash
./run.sh
```

That's it. It builds the three images if they're missing, downloads the model roster into
`./models` if it's missing (~4 GB, resumable), starts **db → backend → frontend** in
dependency order, waits for health, and prints the UI URL:

- **Landing page:** http://localhost:3000
- **Muta app:** http://localhost:3000/chat/
- **API:** http://localhost:8000/v1 (interactive docs at http://localhost:8000/docs)

To share this laptop, open **Muta → Settings → Host mode** after startup. Muta shows a secure
LAN URL and QR code, waits for the host to approve each new account, and keeps each learner's
history private. The default **ADTC competition** policy queues beyond the competition-safe
reply limit; **Use this system** detects available RAM/CPU and raises simultaneous capacity when
safe. See [docs/muta-share.md](docs/muta-share.md) for the complete host, learner, certificate,
persistence, and removal workflow.

```bash
./run.sh            # bring the stack up                                [default]
./run.sh down       # stop it (conversations survive — see Persistence)
./run.sh logs       # follow all three containers' logs
./run.sh --build    # force a clean image rebuild first
./run.sh --model models/core/candidates/Qwen3.5-4B-UD-Q3_K_XL.gguf
                    # hot-swap the core GGUF (default models/core/Qwen3.5-4B-IQ4_XS.gguf)
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

`./run.sh --native` skips the amd64 emulation tax for day-to-day dev: only the db stays in
Docker; the gateway, bundled UI and llama-server run on host loopback (arm64). Open
`http://localhost:8000/chat/`. The pinned
llama.cpp `b10035` macos-arm64 release is fetched into `runtime/build/bin` on first
use, so engine parity with the container is kept. Requires `make install` (importable
venv). Ctrl-C stops the app; `./run.sh down` stops the db container. Audio degrades
to text-only unless sherpa-onnx is installed on the host — expected in native mode.

Docker (`./run.sh`, no flag) remains the reproducible Linux/amd64 control and the build
boundary for the compiled AVX2 engine. The extracted native Linux two-process topology is
the portable product shape. Re-verify changes against the control, but record final report
measurements only on the native x86 target laptop. Mac-native numbers remain dev signals
only (`bench/optimization-log.md` rule).

## Native Linux mode (GCP experiment VM / portable topology)

The Compose stack remains the reproducible control, but it is not required while native
experiments run. Build the control once, then extract the exact verified engine from it:

```bash
make build
./run.sh export-linux
```

The exporter installs `llama-server` and `llama-bench` under `runtime/build/bin/`, exports the
complete offline browser bundle from the frontend image into `ui/dist/`, and writes
`runtime/build/native-linux-manifest.json`. It refuses a non-x86-64 ELF, the wrong llama.cpp
pin (must be b10035 / 602f828), unresolved shared libraries, unknown image provenance, forbidden
AVX-512 signatures, or incomplete UI assets. The manifest records source-image identities,
source-tree/Git identity, engine version, dependencies, and binary/UI hashes. Docker is only the
one-time build/extraction boundary.

After the host venv is installed (`python3 -m venv .venv`, then
`.venv/bin/pip install -e '.[dev]'`), both launch paths are Docker- and network-free:

```bash
./run.sh down                    # stop the control before measuring
./run.sh --native-engine         # llama-server only, http://127.0.0.1:8080
./run.sh --native-linux          # gateway + supervised engine + SQLite
```

Full native mode serves the landing page at <http://127.0.0.1:8000/>, the app at
<http://127.0.0.1:8000/chat/>, and stores conversations
in `data/muta.sqlite3`; it does not start PostgreSQL or nginx. `MUTA_OFFLINE=1` is set by
default, disabling even the connectivity probe (set it to `0` only for an intentional cloud
test). Bind stays on loopback. From a
Mac, use an SSH tunnel rather than opening a public firewall rule:

```bash
gcloud compute ssh muta-vm --zone=us-west1-b -- -L 8000:127.0.0.1:8000
```

### Keep the GCP native UI running

Do not launch the GCP gateway with `nohup`: when its SSH session is collected, the gateway can
disappear while its engine child keeps the native ports occupied. Install the checked-in systemd
user unit once instead (the GCP checkout is `/home/$USER/Muta`). Enable it without starting first,
then enable linger before taking over the two native ports:

```bash
systemctl --user stop muta-gateway.service 2>/dev/null || true
mkdir -p ~/.config/systemd/user
install -m 0644 deploy/systemd/muta-gateway.service \
  ~/.config/systemd/user/muta-gateway.service
systemctl --user daemon-reload
systemctl --user enable muta-gateway.service
sudo loginctl enable-linger "$USER"
```

On the first migration only, identify the old listeners and verify both belong to this checkout
before terminating them. Do not use a broad `pkill` command:

```bash
set -eu
gateway_pid="$(pgrep -f '^(.*/)?[.]venv/bin/python -m uvicorn orchestrator[.]main:app .*--port 8000$' || true)"
engine_pid="$(pgrep -f '^(.*/)?runtime/build/bin/llama-server .*--port 8080( |$)' || true)"
[ "$(printf '%s\n' "$gateway_pid" | wc -w)" -eq 1 ] || {
  echo "expected exactly one legacy gateway; refusing takeover" >&2; exit 1;
}
[ "$(printf '%s\n' "$engine_pid" | wc -w)" -eq 1 ] || {
  echo "expected exactly one legacy engine; refusing takeover" >&2; exit 1;
}
test "$(readlink -f "/proc/$gateway_pid/cwd")" = "$HOME/Muta"
test "$(readlink -f "/proc/$engine_pid/cwd")" = "$HOME/Muta"
ps -fp "$gateway_pid" -p "$engine_pid"

wait_port_free() {
  port="$1"; attempts=0
  while ss -H -ltn "sport = :$port" | grep -q .; do
    attempts=$((attempts + 1))
    [ "$attempts" -lt 90 ] || return 1
    sleep 1
  done
}

kill -TERM "$gateway_pid"
wait_port_free 8000 || { echo "gateway port did not clear" >&2; exit 1; }
kill -0 "$engine_pid" 2>/dev/null && kill -TERM "$engine_pid"
wait_port_free 8080 || { echo "engine port did not clear" >&2; exit 1; }
systemctl --user start muta-gateway.service

attempts=0
until curl -fsS http://127.0.0.1:8000/v1/ready \
    | grep -Eq '"ready"[[:space:]]*:[[:space:]]*true'; do
  attempts=$((attempts + 1))
  [ "$attempts" -lt 90 ] || { echo "Muta did not become ready" >&2; exit 1; }
  sleep 1
done
```

Exit SSH, reconnect, and run the readiness check once more. That proves the service—not the
deployment shell—owns the live processes. Later upgrades only need
`systemctl --user restart muta-gateway.service`; do not repeat the legacy takeover.

The optional `~/.config/muta/native.env` file can override native environment variables without
editing the unit. Gateway and engine bind addresses are deliberately pinned to `127.0.0.1` in the
executed command; connect through the SSH tunnel above. Check and safely restart it with:

```bash
systemctl --user status muta-gateway.service
journalctl --user -u muta-gateway.service -f
curl -fsS http://127.0.0.1:8000/v1/ready \
  | grep -Eq '"ready"[[:space:]]*:[[:space:]]*true'
systemctl --user restart muta-gateway.service
```

The exploratory VM engine benchmark is:

```bash
make bench-native-linux
make bench-native-linux ARGS="--sweep LINUX-PRODUCT"
```

It refuses enabled host swap or a running Compose backend, verifies the engine manifest, hashes
the model, and writes a fingerprinted artifact under `bench/.artifacts/gcp-cloud-proxy/` labelled
`x86 cloud proxy (GCP n2-custom-4-8192, 2C/4T)`. These measurements guide experiments but are
**not report-grade**: the cloud Xeon exposes AVX-512 (the binary does not use it), memory bandwidth
is provider-dependent, and package temperature is unavailable.

## The three containers

| Container | Image | What it runs | Port |
|---|---|---|---|
| `db` | `postgres:16-alpine` | conversations, messages, attachments, user settings | 127.0.0.1:15432 (host tests) |
| `backend` | `docker/backend.Dockerfile` | FastAPI gateway (uvicorn) which supervises `llama-server` as a child; vision spawns a second, TTL-reaped llama-server on demand | 8000 |
| `frontend` | `docker/frontend.Dockerfile` | nginx serving the landing page at `/`, the app at `/chat/`, and proxying `/v1` (same origin ⇒ no CORS; SSE unbuffered; WebSocket upgrade) | 3000 |

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
| Core LLM | `models/core/Qwen3.5-4B-IQ4_XS.gguf` |
| Vision projector | `models/core/mmproj-F16.gguf` |
| ASR | `models/asr/moonshine-tiny-en-int8/` |
| VAD | `models/asr/silero_vad.onnx` |
| TTS | `models/tts/piper/en_US-joe-medium.onnx` (CC0) |
| RAG embeddings | `models/embed/bge-small-en-v1.5-q8_0.gguf` |
| Competition-safe core / speculation draft | `models/draft/Qwen3.5-0.8B-Q4_K_M.gguf` |

`make verify-models` re-checks hashes, licences and load smoke.

**Optional, not in the roster: the TTFT preamble model.** `make fetch-ttft` provisions
TinyStories-1M into `models/ttft/` (15 MB) — an in-process NumPy model that writes filler
while the 4B prefills, so the pane fills in ~1.6 ms instead of seconds. It is deliberately
outside `fetch-models`: upstream declares **no licence**, so it is dev/measurement only and
off by default. `MUTA_RT_TTFT_PREAMBLE=1` enables it.
[`docs/ttft-preamble.md`](docs/ttft-preamble.md) has the full story.

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

In the Compose control, conversations, messages and attachments live in Postgres, in the named
volume `muta-pgdata`. `./run.sh down` / `docker compose down` **keeps** them;
`docker compose down -v` is the only thing that deletes them.

Native Linux uses the portable SQLite file `data/muta.sqlite3`. Copying that file while the
native app is stopped backs it up; deleting it erases only native-mode conversations. The two
stores are intentionally separate, so control data cannot contaminate native experiments.

Host-side tests reach the same db on `127.0.0.1:15432`
(`MUTA_TEST_DB_URL` overrides; store tests skip cleanly when it's down).

## Configuration

Backend env (set in `docker-compose.yml`; all `MUTA_RT_*` overridable):

| Variable | Default (compose) | Meaning |
|---|---|---|
| `MUTA_RT_DB_URL` | host/native: `sqlite:///data/muta.sqlite3`; compose: `postgresql://muta:muta@db:5432/muta` | persistence URL |
| `MUTA_RT_MODEL_DIR` / `_FILE` | `/app/models/core` / `Qwen3.5-4B-IQ4_XS.gguf` | core GGUF |
| `MUTA_RT_DRAFT_MODEL` | `/app/models/draft/Qwen3.5-0.8B-Q4_K_M.gguf` | speculative draft (Qwen3.5 family only — Qwen3 vocab is incompatible; skipped if absent) |
| `MUTA_RT_AUTOSTART` | `1` | gateway lifespan starts/supervises llama-server |
| `MUTA_RT_STARTUP_TIMEOUT_S` | `900` | model-load allowance (emulation is slow) |
| `MUTA_RT_REQUEST_TIMEOUT_S` | `600` | per-request client timeout |
| `TUTOR_ROOT` | `/app` | root for vision/audio model paths |
| `MUTA_RT_N_CTX` | native: `12288` total (`6144` per lane); Compose: `2048` | active shared context; hard request fitting reserves per-lane reply headroom |
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
| `MUTA_RT_TTFT_PREAMBLE` | `0` (off) | in-process warm-up model fills the prefill window (`make fetch-ttft` first) |
| `MUTA_RT_TTFT_MAX_TOKENS` | `48` | preamble length cap — also caps the ~80 ms of one core it costs |
| `MUTA_RT_TTFT_MODEL_DIR` | `models/ttft` | resolved against `TUTOR_ROOT` when relative |

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
`make test` / `make lint` / `make contract` are the per-task developer surface. The static
browser client also has dependency-free Node 22 tests at `make ui-test`; CI runs both suites,
while the deploy image remains Python-only.
