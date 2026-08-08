# GPU auto-detect + Internet capabilities — approved design (2026-08-08)

**Status:** approved (user, 2026-08-08). Phases land in order, each with tests and a
same-day RESULTS.md entry. Offline-first is preserved throughout: every online feature is
opportunistic and opt-in; the tutor keeps working with zero network, zero GPU.

## Why

- The multimodality fixes (RESULTS.md 2026-08-08) made vision *correct* but the emulation
  tax makes it *slow* (~4 min/photo at the Qwen-VL 1024-image-token floor). The best
  engine this box has — Metal on the M2 Pro — sits unused.
- On 2026-08-07 the stack failed to boot with everything needed already local, because
  `docker compose` insisted on reaching a registry (and another project's arm64 pull had
  clobbered the shared `postgres:16-alpine` tag). Offline resilience is a bug fix, not a
  feature.
- The user wants the tutor to *use* the internet when it is genuinely there: model/system
  updates, web-grounded answers, and an optional cloud-model boost.

## The shape: a capabilities layer

The gateway already publishes memory state (the degradation ladder). This adds a sibling
surface: probe **GPU** (at boot) and **connectivity** (at boot + ~1/min), publish through
`/v1/ready` checks and telemetry, and let run.sh, the gateway, and the UI key off it.
Contract changes are additive-only, as always.

## P1 — GPU auto-detect, Metal first

- `run.sh` gains hardware detection with CPU as the universal fallback:
  - **Darwin/arm64:** native mode is the GPU path (Docker on macOS has no GPU
    passthrough). The pinned b10035 `macos-arm64` release run.sh already fetches is a
    Metal build (`.metal` files ship in the archive). Detection sets
    `MUTA_RT_N_GPU_LAYERS=-1` (all layers) in `native_up` unless the user pinned a value.
    Docker mode on Apple Silicon prints a one-line suggestion to use `./run.sh --native`.
  - **Linux + `nvidia-smi`:** print how to enable the CUDA variant
    (`docker/backend.cuda.Dockerfile` + a compose `gpu` profile with device
    reservations). The CUDA image is opt-in and untestable on this dev box — detection
    and wiring ship; the build is exercised by whoever has the hardware.
  - `--cpu` forces the current behavior everywhere.
- `runtime/profiles.py`: `core_text_command`/`core_vision_command` learn
  `--n-gpu-layers` from config (today only `runtime/server.py`'s path passes it). The
  vision instance offloads too — that is where the latency hurts most.
- The AVX2 container invariant is untouched; `n_gpu_layers` defaults to 0.
- **Verify:** RESULTS.md entry, `native` context: decode + prefill tok/s and
  peak RSS, CPU vs Metal, same prompts as the 2026-08-01 sweep.

## P2 — Offline-resilient boot + provisioning/updates

- `run.sh` probes connectivity once (≤ ~3 s total budget) → ONLINE/OFFLINE:
  - OFFLINE + all images present locally → skip build, `docker compose up --pull never`,
    boot normally with one warning line.
  - OFFLINE + something missing → die naming exactly what is missing and the command to
    run when back online. Never a raw registry TLS traceback.
  - ONLINE → today's behavior (build with cache, provision models).
- Pin `db` to `postgres:16-alpine@sha256:…` (digest of the multi-arch manifest list) so a
  neighboring project's pull can never clobber the platform resolution again.
- `./run.sh update` (online only): pull code, re-run the hash-skipping model fetcher,
  rebuild images, restart.
- Gateway: a `connectivity` probe (HEAD to `MUTA_NET_PROBE_URL`, default a small
  well-known endpoint; ~1/min, never on the request path) feeding telemetry and
  `/v1/ready` as `online: true|false`; the UI shows a quiet status dot.

## P3 — Cloud model boost (opt-in)

- Config: `MUTA_CLOUD_URL` (any OpenAI-compatible chat endpoint), `MUTA_CLOUD_MODEL`,
  `MUTA_CLOUD_API_KEY`. All three set + online = enabled; anything else = local.
- `/v1/chat/stream` routes to the cloud endpoint when enabled; **any** failure —
  connect error, 4xx/5xx, mid-stream drop — falls back to the local engine. The SSE
  event shape is unchanged (the contract does not move); the partial-persist guarantee
  holds on both paths.
- Telemetry and the UI badge the answer source (`local`/`cloud`) — it is never silent
  that student text left the device. Off by default; a deployment decision.
- Note before implementation: consult the current provider API docs (the claude-api
  skill) rather than assuming; prefer the OpenAI-compatible shape the codebase already
  speaks (`InferenceClient`).

## P4 — Web-augmented tutoring (opt-in)

- No agentic tool-calling on a 4B model. Instead, RAG-style grounding: when online and
  `MUTA_SEARCH_URL` is configured (SearXNG or similar; no API key required by default),
  the gateway fetches top-k snippets for the student's question and injects them as
  context, returning sources alongside the reply (additive contract field) for the UI to
  render.
- Offline, disabled, or fetch failure → the answer proceeds without web context,
  silently. A slow search must never delay the first token past a small budget
  (~2 s); on miss, skip.

## Error handling (all phases)

Degradation, not errors: GPU absent → CPU; offline → local-only; cloud fails → local
mid-stream; search fails → ungrounded answer. No student-facing failure may name a
subsystem; every refusal says what to do instead.

## Testing

- P1: command-construction unit tests (`--n-gpu-layers` presence/absence per config);
  run.sh detection under faked `uname`/`nvidia-smi` (bats-style shell probe or a small
  pytest wrapper invoking `run.sh --print-plan`).
- P2: run.sh offline path under a faked failing registry; digest-pin boot test;
  connectivity probe unit tests (monkeypatched HEAD).
- P3: cloud routing + fallback unit tests against a fake OpenAI-compatible server
  (success, 401, mid-stream drop → local resume); contract regression (`make contract`
  diff is additive).
- P4: injection formatting, budget/miss behavior, source propagation; contract additive.
