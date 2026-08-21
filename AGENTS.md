# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## What this is

An **offline, adaptive AI tutor for math and scientific reasoning** built for the ADTC 2026 competition (deadline **Wed 12 Aug 2026**). It must run on an **8 GB, CPU-only** laptop (Ubuntu 22.04, integrated graphics, no GPU) delivered from a flash drive with **zero install and no network**. The design bet: a small quantized model + retrieval + verified tool calls beats a large model squeezed onto constrained hardware.

**Current state: skeleton + working inference layer.** `README.md` and `ROADMAP.md` hold the plan (source of truth). A runnable backend exists and passes its tests: `pyproject.toml` (one workspace), `contracts/` (the frozen `/v1` Pydantic contract + generated `openapi.yaml`), `orchestrator/` (a `gateway` router plus `math`/`retrieval`/`pedagogy`/`exam` sub-apps that `main.py` assembles into one process), a `Makefile`, and `docker/dev.Dockerfile`. **`runtime/` is now real**: model provisioning (local folder default, Hugging Face fallback), a `llama-server` supervisor + HTTP client (the llama.cpp engine), and multi-turn chat with SQLite persistence (`ConversationStore` + `ChatEngine`) — wired into `/v1/chat`. Default model: Qwen3-0.6B Q4_K_M (`unsloth/Qwen3-0.6B-GGUF`). The math/retrieval/pedagogy/exam endpoints and the other gateway routes are still stubbed `501`. Still empty placeholders: `bench/`, `corpus/`, `model-development/`, `ui/`, `docs/`. When writing new code, follow the layout and naming the roadmap prescribes (below) — this is a Step 3 "clean partition" (see Working method), so files landing in the right place with the right names is load-bearing.

**Source of truth is `ROADMAP.md`** (a day-by-day build plan, ~1400 lines) and `README.md`. Read the relevant ROADMAP day/phase before implementing a task — it already contains the plan, the rationale, and the reference links for most work. Do not re-derive decisions the roadmap has already made (e.g. why AVX2 not AVX-512, why temporal corpus splits, why services collapse at deploy).

## The scoring function is the compass

Every technical decision is judged against the competition score, not taste:

```
S_total = 0.50·S_acc + 0.30·S_perf + 0.20·S_eff − P_thermal
S_perf  = 100 · min(TPS_actual / 15, 1.0)          # TPS_max ≈ 15, provisional
S_eff   = 100 · (7 − PeakRAM_GB) / 7               # 7 GB budget
P_thermal = 10   if package temp > 85 °C or throttling flagged
```

**Exchange rate** (the most-used numbers in the project — check every optimization against them):
- **+2.00 pts** per tok/s · **−2.86 pts** per GB of peak RAM · **+0.50 pts** per accuracy point.
- So **1 GB RAM saved = 1.43 tok/s = 5.7 accuracy points.**
- Break-even for any RAM-spending optimization: `ΔTPS ≥ 1.43 × ΔRAM_GB`. A 1 GB draft model must return ≥ 1.43 tok/s or it is net-negative.
- Zero-RAM-cost speedups (n-gram/prompt-lookup speculation, prompt caching) are strictly dominant → they are Phase 1 work, done before anything that costs RAM.

**Hard failures are disqualification, not deductions:** OOM kill, sandbox/execution crash, illegal-instruction fault. `S_acc` = *tutoring quality* (the 50% term), not just final-answer correctness — a correct Socratic response may never state the answer, so evaluation must be mode-aware, never plain exact-match.

**One governing fact:** CPU autoregressive decode is **memory-bandwidth bound, not compute bound**. Shrinking bytes-moved-per-token (weight + KV quantization) buys more than faster arithmetic. More threads stop helping once bandwidth saturates but keep producing heat — so the thread cap is a scoring decision (avoid the −10 thermal cliff), not a performance one. RAM is a linear dial; temperature is a wall.

## Dev → deploy discipline (do not violate)

- **Develop** on MacBook Pro M2 (ARM) **inside Docker built `--platform=linux/amd64`** from day one, so binaries are already x86-64 ELF. **Deploy** by extracting the container to a native portable build (AppImage / portable dir) on a flash drive — no Docker daemon, no VM, no install on the target.
- **Never build with `-mavx512`.** AVX2 is the baseline (`-DGGML_AVX2=ON -DGGML_AVX512=OFF`, `GGML_NATIVE=OFF`) with runtime feature detection for wider ISA. Much of the target field (Zen 3, 12th-gen consumer Intel) faults on AVX-512 = a hard failure.
- **All benchmark numbers in the report come from the x86 target box (9–11 Aug), never the Mac.** Everything else (model files, corpus, RAG index, Python, frontend, config) ports cleanly and is architecture-independent.
- **Peak RAM is scored as RSS, not PSS** — verified from the official profiler's source (`docs/rules-digest.md`; `memory.py` sums `psutil` RSS over `[root] + root.children(recursive=True)`, and never reads `smaps_rollup`). The roadmap's `mmap`-makes-RSS-misleading reasoning is technically right but scores nothing: since RSS ≥ PSS under `mmap`, reporting PSS would inflate `S_eff` in the flattering direction, on the term the design optimizes. **Optimise and report RSS; keep PSS for diagnosis only.** `bench/score.py` names the parameter `peak_rss_gb` so the unit-of-record is at the call site. Measure across the **whole process tree** — `llama-server` + gateway + Python + FAISS + embedder all count against the same 7 GB. Watch `--cache-ram` (defaults to 8 GiB, an instant OOM on this budget — cap it explicitly).

## Architecture

**Backend-first, contract-first, headless.** The backend is a container exposing HTTP; the browser UI is the *first client, not a privileged one*. Everything is reachable by `curl` before a pixel exists — this is what makes "any frontend can connect", the 30-phone classroom demo (30 API clients over LAN), and headless `S_acc` evaluation fall out for free.

**Logical microservices, collapsed process topology.** Six logical services are developed / tested / adversarially-reviewed independently against their own contract, then **co-located into one FastAPI process at deploy via `app.mount()`** (running N supervised processes on the target would make any single crash a disqualifying execution crash, and each Python service costs ~60–100 MB RSS):

| Service | Owns |
|---|---|
| `inference` | `llama-server`, GGUF, KV cache, speculation (already its own process w/ HTTP API) |
| `math` | SymPy routing, verification, units — sandboxed & timeout-bounded |
| `retrieval` | FAISS index, embedder, context assembly |
| `pedagogy` | curriculum DAG, learning twin, tutoring modes, personas (+ SQLite) |
| `exam` | question generator, marking schemes, WAEC-Bench |
| `gateway` | contract surface, routing, static UI — the only service clients address |

**Target topology on the deploy machine: two processes** — `llama-server` and the mounted gateway.

**The `/v1/` OpenAPI contract is the one cross-cutting artifact.** Its source of truth is the Pydantic models in `contracts/models.py`; `contracts/openapi.yaml` is *generated* from the assembled app via `make contract` (`python -m contracts.openapi`), so spec and code cannot drift — never hand-edit the YAML. The surface is versioned (`/v1`) from the first commit. **Nothing downstream may bypass it** — UI, phones, `eval.py`, CLI, and future clients all speak only `/v1/`, importing shapes from `contracts`. Freezing this contract (and the corpus schema) is what lets the three lanes work in parallel; treat both as frozen before parallel work depends on them.

## Repository layout ↔ team lanes

The directory partition is the lane partition (parallel work with no real-time coordination). Note: the ROADMAP writes paths with a leading slash (`/bench`); these are repo-relative (`bench/`).

- **`contracts/`** — the frozen `/v1` contract, shared by every lane. `models.py` (Pydantic, source of truth), generated `openapi.yaml`, and `tests/` (contract smoke tests). Import shapes from here; regenerate the YAML with `make contract`.
- **`runtime/`** — *Lane A (Systems/Runtime).* The inference layer + llama.cpp build. `config.py` (`RuntimeConfig`, `MUTA_RT_*` env), `models.py` (`resolve_model` — local-first, HF fallback, always yields a local GGUF because deploy is offline), `server.py` (`LlamaServer` supervisor; finds the binary via `MUTA_RT_LLAMA_SERVER_BIN` → `runtime/build/bin` → PATH), `client.py` (`InferenceClient` → llama-server `/v1/chat/completions`, blocking + streaming), `memory.py` (`ConversationStore`, SQLite), `chat.py` (`ChatEngine`, the multi-turn loop — system prompt injected by the caller, no pedagogy of its own), `cli.py` (`make chat`), `run.sh`, `VERSIONS.md` (pin llama.cpp SHA / base-image digest before 9 Aug). The `llama-server` binary is **not vendored** — `brew install llama.cpp` for dev, container build into `runtime/build/bin` for the target.
- **`bench/`** — *Lane B (ML/Correctness).* `score.py` (scoring function — a bug here misdirects a month; keep `test_score.py` green), `profile.py` (end-to-end measurement; also cross-checked against `llama-bench`), `eval.py` (accuracy + KL-divergence vs F16 + flip rate), `run_bakeoff.py`, `optimization-log.md` (before/after row per change), `PROTOCOL.md`, `waec/` (WAEC-Bench + `METHODOLOGY.md`).
- **`corpus/`** — *Lane B.* `ingest.py` (math-aware PDF→text), `schema.json` (the single schema every downstream consumer reads — `subject` must accommodate physics/chem/bio, not just math), `sources.md`.
- **`orchestrator/`** — *Lane C / gateway.* The one deployable app. `main.py` assembles it (includes the gateway `/v1` router, `app.mount()`s the sub-apps under `/internal/*`, serves the UI); `gateway/` holds the public router (`routes.py`) + a standalone app; `math/`, `retrieval/`, `pedagogy/`, `exam/` are the sub-apps (each a full FastAPI app runnable standalone via `uvicorn orchestrator.<svc>.app:app`); `_common.py` is the service factory; `config.py` carries the `mounted`/`split` topology; `prompts/` holds persona prompts. Design prompts with a **stable shared prefix first, per-student text last** so the prompt cache hits (prompt architecture is a performance decision).
- **`ui/`** — *Lane C.* Browser client — first consumer of the `/v1/` contract, not the product. Offline KaTeX (no CDN). Built output at `ui/dist/` is auto-served at `/chat` when present.
- **`docs/`** — externalized tribal knowledge (see below). `docs/api/EXAMPLES.md` holds the curl walkthrough (the OpenAPI spec itself lives in `contracts/`); decision docs include `build-flags.md`, `rules-digest.md`, `quant-types.md`, `smoke-fixture.md`, `model-decision.md`, `native-extraction-plan.md`, `target-day-runbook.md`, `plans/`.
- **`models/`, `model-development/`** — model artifacts and fine-tuning work (Unsloth); GGUFs/indexes tracked via Git LFS (`.gitattributes`). *Suggested (not yet done): rename `model-development/` → `training/` and keep artifacts vs training code separate.*

## Commands

**`./run.sh` is the front door** — one command from a clean clone to a conversation. Docker by
default (provisions image + weights + engine, then chats); `--native` for the fast host loop on
a Mac; `--serve` for the HTTP app instead of the REPL; `-- <args>` passes through to the REPL
(e.g. `-- --conversation <id>`). `RUN.md` documents it and the by-hand equivalents. The Makefile
below stays the per-task developer surface.

`make help` lists everything. Working today (Python ≥3.10; `make install` sets up an editable install):

- `make dev` — run the assembled app (`uvicorn orchestrator.main:app --reload`, port 8000). Public surface at `/v1`, interactive docs at `/docs`. Sub-apps can also run standalone in split mode.
- `make contract` — regenerate `contracts/openapi.yaml` from the Pydantic models. Run it whenever the contract changes; commit the result.
- `make test` — pytest (contract smoke tests live in `contracts/tests/`). `make lint` / `make fmt` — ruff.
- `make contract-test` — schemathesis property-fuzzes a running server (`make dev` first) against `/openapi.json`.
- `make build` — build the `linux/amd64` dev image from `docker/dev.Dockerfile`. Two stages: stage 1 compiles llama.cpp (pinned `b10035`) with `GGML_AVX2=ON GGML_AVX512=OFF GGML_NATIVE=OFF LLAMA_CURL=OFF`, then **asserts** x86-64 ELF and greps the disassembly for AVX-512 mnemonics — the build fails rather than letting an illegal-instruction fault become a disqualification on the target. Stage 2 ships only the binaries (`llama-server`, `llama-bench`) next to the app, so no compiler reaches the final image. Weights are mounted, never baked. `docker/entrypoint.sh` runs the two-process topology and starts the gateway even when the engine is absent (503 by design, not a boot failure); an explicit command overrides the app (`docker run muta-dev python3.10 -m pytest`).
- `make model` — download the default GGUF (Qwen3-0.6B Q4_K_M) into `models/`.
- `make serve` — launch `llama-server` on `127.0.0.1:8080` against the resolved model (needs `brew install llama.cpp` or a container build).
- `make chat` — interactive multi-turn REPL against the runtime (auto-starts a server if none is up). Full stack: `make serve` + `make dev`, then `POST /v1/chat` with a `conversation_id` for memory. Conversations persist in `data/muta.sqlite3`.

Stubbed until Phase 1 — each echoes its ROADMAP reference rather than failing silently:

- `make smoke` — `docker run` → server → health → test prompt → profiler JSON. The loop every later change is validated against.
- `make bench` — `profile.py` (end-to-end) + `llama-bench` (engine ceiling) to the same JSONL; the gap between them is this stack's own overhead.
- `make profile` — wires in the official ADTC local profiler as a third measurement path.
- `make package` — extract the container to a native portable build (per `docs/native-extraction-plan.md`).

CI (to add): contract tests + `make build` on push, publishing the image to GHCR.

Base image: `FROM --platform=linux/amd64 ubuntu:22.04`. Confirm ELF x86-64 output with `file`; confirm buildx emulation with `docker buildx ls`.

## Working method (the standing engineering protocol)

The README's "Four-Step Guide" (README lines 174–181) is the team's protocol, and much of the ROADMAP's structure encodes it:

1. **Study before writing.** Read the relevant code/spec/ROADMAP day and write an explicit plan (to `docs/plans/`) before implementing anything non-trivial.
2. **Externalize tribal knowledge into `docs/`.** Every non-obvious decision (a "why", an invariant, a rejected alternative) is written down structured, because parallel implementers cannot ask clarifying questions mid-task. No decision is made in a standup and left there.
3. **Partition cleanly** — the lane/directory boundaries above; freeze the API contract and corpus schema before parallel work depends on them.
4. **Pair every writer with an adversarial reviewer** in a fresh, separate context whose only job is to assume the output is wrong and find why. Apply hardest where a silent bug is most expensive: `score.py`, `profile.py`, the Paper 2 rubric grader, and the memory guard. **No task is done until an adversarial reviewer from another lane has tried to break it and failed.**

**Standing rule:** every optimization is recorded as a before/after row in `bench/optimization-log.md` *the day it lands*, scored through `score.py`. The report's ablation table is built continuously, not at the end.
