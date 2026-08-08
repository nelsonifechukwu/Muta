# P3 — Cloud model boost (opt-in): Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When `MUTA_CLOUD_URL` + `MUTA_CLOUD_MODEL` + `MUTA_CLOUD_API_KEY` are all set **and** the box is online, chat routes to the cloud endpoint; any pre-stream failure falls back silently to the local engine; the answer's source is never hidden.

**Architecture:** `InferenceClient` (already OpenAI-shaped) gains `api_key` and a `template_kwargs` switch; a new `CloudFallbackClient` wraps a cloud + a local instance behind the same three methods `ChatEngine` uses (`chat_with_timings`, `stream`, `stream_events`) and records which backend served last; `get_engine()` wires it when the three env vars are set; the SSE `done` event and the UI badge the source.

**Tech Stack:** httpx, pytest monkeypatch (house `_FakeStream` idiom from `test_client_stream_events.py`).

## Global Constraints

- Off unless all three env vars are set — a deployment decision, never a default.
- Fallback policy: cloud failure **before the first streamed chunk** → silent local retry; **mid-stream** failure → propagate (the existing dropped-stream partial-persist path handles it). Non-streaming `chat_with_timings`: any cloud exception → local.
- Offline (`online()` is False **or** None) → local, no cloud attempt.
- The `/v1` contract stays additive; SSE `done` gains an optional `source` field.
- Student text reaching a third party must be visible: UI badge + `source` field, always.

---

### Task 1: `InferenceClient` speaks to authenticated OpenAI-compatible endpoints

**Files:** Modify `runtime/client.py`; test `runtime/tests/test_client_cloud.py` (new).

**Interfaces:** `InferenceClient(base_url, *, model, enable_thinking, timeout, api_key: str | None = None, template_kwargs: bool = True)`. `api_key` → `Authorization: Bearer …` on both HTTP calls; `template_kwargs=False` omits `chat_template_kwargs` (strict providers 400 on unknown fields; llama-server keeps the default).

- [x] Step 1: failing tests — capture `headers=` and payload via monkeypatched `httpx.post`/`httpx.stream`; assert bearer header present with key / absent without; `chat_template_kwargs` present by default / absent with `template_kwargs=False`.
- [x] Step 2: RED (TypeError: unexpected keyword).
- [x] Step 3: implement (store `self._headers`, thread through both calls; guard `_payload`).
- [x] Step 4: GREEN + existing client tests still pass + ruff.
- [x] Step 5: commit `client: api_key + template_kwargs — one OpenAI-shaped client for local and cloud`.

### Task 2: `CloudFallbackClient`

**Files:** Create `runtime/cloud.py`; test `runtime/tests/test_cloud.py` (new).

**Interfaces:** `CloudFallbackClient(cloud: InferenceClient, local: InferenceClient, online: Callable[[], bool | None])` with `chat_with_timings`, `stream`, `stream_events`, and `last_source: str` (`"cloud"`/`"local"`, starts `"local"`).

- [x] Step 1: failing tests — fake clients (lists of events / raising stubs): cloud used when online-true; local when online False/None; pre-first-chunk cloud error → local events, `last_source == "local"`; mid-stream cloud error → propagates after the yielded prefix; `chat_with_timings` falls back on exception.
- [x] Step 2: RED (ModuleNotFoundError).
- [x] Step 3: implement — `stream_events`: if not online → local; else open cloud iterator, pull the first event inside try; on Exception → local passthrough; then yield the first event + the rest outside the guard. `stream` filters `content` from `stream_events` (same contract as `InferenceClient.stream`).
- [x] Step 4: GREEN + ruff.
- [x] Step 5: commit `runtime: CloudFallbackClient — cloud when online, silent local fallback before first token`.

### Task 3: wiring — `get_engine`, SSE `source`, UI badge

**Files:** Modify `orchestrator/gateway/deps.py` (env-gated wrap), `orchestrator/gateway/routes.py` (`done` event gains `source` when the engine's client exposes `last_source`), `ui/app.js` (+`ui/styles.css`): a small "cloud" tag next to the assistant message when `done.source == "cloud"`. Test: extend `orchestrator/tests/test_connectivity.py`-style wiring test in `orchestrator/tests/test_cloud_wiring.py` — env set + `deps.get_engine.cache_clear()` → engine.client is a `CloudFallbackClient`; env unset → plain `InferenceClient`.

- [x] Step 1: failing wiring tests; RED.
- [x] Step 2: implement deps branch + SSE field + UI badge; GREEN; `make contract` (no schema change expected — `done` is already free-form JSON on the SSE stream; verify).
- [x] Step 3: commit `gateway: cloud boost wired — env-gated, source always visible`.

### Task 4: close P3

- [x] Step 1: live verification without external dependencies: point `MUTA_CLOUD_URL` at the local llama-server (`http://127.0.0.1:8081`) with a dummy key on `make dev` → source=cloud plumbing proves out; then point it at a dead port → first token still arrives (silent local fallback). Document both in RESULTS.md.
- [x] Step 2: full suite + ruff green.
- [x] Step 3: RESULTS.md entry + check off this plan + commit `results: cloud boost verified via loopback + dead-port fallback; P3 closed`.
