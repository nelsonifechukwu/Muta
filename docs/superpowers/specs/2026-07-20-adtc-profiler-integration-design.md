# ADTC profiler integration — design

**Date:** 2026-07-20 · **Status:** approved, pending implementation plan
**Fills:** `make profile` (stubbed since 16 Jul), `bench/profile.py` (0 bytes), and adds `make monitor`.

## Goal

Wire the official [`adtc-profiler`](https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler)
into Muta so that two things exist:

1. **An autonomous test mode** — one command, no human in the loop, that measures both the
   *scored* path and the *product* path, scores both through `bench/score.py`, and records the
   result.
2. **Continuous terminal updates while the app runs** — a live read on the two scored resource
   terms (`S_perf`, `S_eff`) during ordinary development.

## The constraint that shapes everything

**The official profiler cannot produce live updates on a running app, and never measures our
product.** Read from the source at the pinned SHA:

- `cli.py` wraps a single `llama-bench` subprocess in `memory.sample_during()` and
  `thermal.sample_thermal()`, then emits one JSON at the end. There is no streaming mode.
- `memory.sample_during(pid=None)` defaults to `psutil.Process().pid` — **the profiler's own
  PID**. The tree it walks is the profiler plus the `llama-bench` child. `llama-server`, the
  gateway, FastAPI, FAISS and the embedder are never in that tree.
- `throughput.measure()` shells out to `llama-bench -m <model.gguf> -p 512 -n 128`. No HTTP, no
  tokenizer round-trip through our code.

So the two asks land on two different mechanisms, and conflating them would produce a number
the audit cannot reproduce:

| Ask | Mechanism | Measures |
|---|---|---|
| Autonomous test mode | the real `adtc-profiler`, invoked verbatim | `llama-bench` against the GGUF — **the scored path** |
| Live terminal updates | our own sampler, methodology-identical | the two-process product tree — **the path that can OOM** |

This is the split `docs/rules-digest.md` already anticipated: "`bench/profile.py` gets a mode
that mirrors the official methodology exactly, instead of trusting our own harness to agree
with theirs."

## Pinned upstream

`Africa-Deep-Tech-Foundation/adtc-profiler` @ **`cf3432cf54216617429cf3f9d3d7150fb891fdd1`** —
verified 2026-07-20 as upstream `HEAD`, and the same SHA `docs/rules-digest.md` cites. Every
integration point below is read from that commit; re-verify before changing the pin.

## Findings that change the implementation

Four things read out of the source that are not obvious from the README.

### 1. The `throttled` flag uses the wrong threshold

`thermal.py:report()` computes `throttled = bool(peak_temp and peak_temp >= 95.0)`, with a
source comment calling it "best-effort … revisit in Phase 2". The official penalty rule is
**core temperature exceeds 85 °C** *or* throttling is detected.

**Consequence:** a run peaking at 90 °C reports `throttled: false` while incurring the −10
penalty in reality. `bench/adtc/report.py` must apply the 85 °C rule to `core_temp_c_peak`
itself and pass `max_temp_c` into `score()`, using the profiler's `throttled` only as an
additional `or` condition — never as the sole signal.

### 2. `runtime/client.py` cannot report throughput

`InferenceClient.chat()` (`runtime/client.py:42`) returns a bare `str`. There are no token
counts or timings, so the product path has nothing to compute TPS from.

**Consequence:** the client needs a timings-bearing return path. Add
`chat_with_timings() -> Generation` (a frozen dataclass carrying `text`, `prompt_tokens`,
`completion_tokens`, `elapsed_s`, and llama-server's `timings` block when present).
`chat()` stays as-is and delegates, so no existing caller changes.

TPS derivation prefers llama-server's own `timings.predicted_per_second`; falls back to
`completion_tokens / elapsed_s`. The fallback is recorded in the artifact so a number from
wall-clock is never mistaken for one from the engine.

### 3. Python floor conflict, and a licence discrepancy

Profiler requires **Python ≥3.11**; Muta's `pyproject.toml` sets `requires-python = ">=3.10"`.
It also pulls `click`, `rich`, `jsonschema`. And `LICENSE` is **GPL-3.0** while
`pyproject.toml` declares `license = { text = "MIT" }` — an unresolved upstream contradiction.

**Consequence:** the profiler is installed into an isolated venv and invoked as a subprocess.
It never enters Muta's import graph, no GPL source enters the tree, and the 3.10 floor holds.

### 4. `llama-bench` discovery will fail by default

`throughput._find_llama_bench()` uses `shutil.which()` over `PATH` only. Our binary lives in
`runtime/build/bin` (container build) or a brew prefix (dev).

**Consequence:** the harness prepends the resolved binary directory to the subprocess `PATH`.
It does not modify the developer's shell.

## Architecture

```text
bench/
  sampler.py            THE measurement core — profiler-identical RSS math
  monitor.py            live HUD; external process, attaches by PID       → make monitor
  profile.py            product-path pass (currently 0 bytes)             → make bench
  autotest.py           autonomous orchestrator                            → make profile
  adtc/
    __init__.py
    install.py          bootstraps bench/.venv-profiler @ cf3432cf
    submission.py       synthesizes the submission dir
    report.py           profiler JSON → score() inputs
  submission/
    metadata.json       checked-in Gate 1 claims (version controlled)
  .artifacts/           gitignored: submission.json, runs.jsonl, synthesized submission dir
  .venv-profiler/       gitignored
```

### `bench/sampler.py` — the one measurement core

A line-by-line port of upstream `memory.py`, with the tree root parameterised so it can point
at *our* process instead of the sampler's own:

- poll every **0.1 s**
- `rss = sum(p.memory_info().rss for p in [root] + root.children(recursive=True) if p.is_running())`
- `peak_rss_mb = max(observed)`
- `steady_state_rss_mb = mean of samples in the last min(60 s, duration / 2)`
- swallow `NoSuchProcess` / `AccessDenied` per-sample, matching upstream

**It is the only place this math exists.** `monitor.py`, `profile.py`, and `autotest.py` all
call it. Nothing re-derives the formula.

A port can drift from upstream. Mitigation is a cross-check test (below), not vigilance.

Thermal sampling is a parallel port of `thermal.py` (0.5 s, `_CORE_HINTS` label matching,
`max()`), with the 85 °C rule applied at scoring time per finding 1.

### `bench/monitor.py` — the live HUD

A **standalone process**, not a thread inside the app. Rationale is scoring, not tidiness: a
sampler inside the gateway adds its own RSS to the tree it reports, and to the tree the real
profiler would measure. An external observer is free.

Resolution order for the target PID: `--pid` → pidfile at `data/muta.pid` → probe the listener
on port 8000 → error with an actionable message.

Nothing currently writes a pidfile, so this work adds one: the gateway writes `data/muta.pid`
on startup and removes it on shutdown. The port probe stays as the fallback for stacks started
outside the normal entrypoints (a bare `uvicorn`, a container).

RSS comes from walking the tree directly. **TPS cannot** — an external observer never sees a
generation. So the gateway keeps a bounded ring buffer (64 entries) of recent generation
timings, exposed at `GET /internal/bench/metrics`. That path is `/internal/*`, **not `/v1`**,
so the frozen contract is untouched and `contracts/openapi.yaml` does not change. If the
endpoint is absent or 404s, the HUD degrades to RSS-only rather than dying.

Rendered with `rich.Live` at 2 Hz. Note that the profiler's own `rich` lives in the isolated
venv and is **not** importable from Muta's environment — so `rich>=13` is added to Muta's
`[dev]` extra in `pyproject.toml`. It is dev tooling and never reaches the flash drive, so it
costs no runtime RAM. `monitor.py` degrades to plain ANSI if the import fails, keeping the HUD
usable from a bare `[project]` install.

```text
muta ⏻ pid 4821   tree: llama-server, uvicorn, +2      elapsed 04:12
RSS    peak 2.31 GB   steady 2.08 GB   budget 7.00 GB   S_eff  67.0
TPS    11.4 t/s last  9.8 avg/8        tps_max 15 prov  S_perf 76.0
TEMP   —  unmeasurable on darwin       cpu p99 84%
```

Every displayed score term is computed by calling `bench.score.score()` — the HUD never does
its own arithmetic on the scoring function.

### `bench/adtc/install.py`

Bootstraps `bench/.venv-profiler` on demand:

1. Locate a Python ≥3.11 interpreter (`python3.11`, `python3.12`, `python3`, checking version).
   Absent → error naming `uv python install 3.11` / pyenv.
2. `python -m venv bench/.venv-profiler`
3. `pip install "git+https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler.git@cf3432cf54216617429cf3f9d3d7150fb891fdd1"`
4. Verify `adtc-profiler --help` runs; record the resolved SHA in `bench/.artifacts/profiler-version.json`

Idempotent — a present, verified venv is a no-op. Network is needed on first bootstrap only;
profiling is dev-time work that never ships to the offline target.

### `bench/adtc/submission.py`

The profiler needs a submission directory containing `metadata.json` and the model file.

**Durable claims are checked in** at `bench/submission/metadata.json` — `team_id`, `submitter`,
`domain`, `language_scope`, `african_alpha_claim`, `budget_laptop_claim`,
`cross_disciplinary_pairing`, `test_prompts`. This is a Gate 1 deliverable and must be
reviewable and diffable.

**Volatile parts are generated** into `bench/.artifacts/submission/` at run time:

- `model.gguf` — hardlink (copy fallback) of the path from `runtime.models.resolve_model()`
- the `_runtime` block — `model_path`, `docker_image`
- `model.parameters_estimate` — **derived from the actual GGUF header**, not hand-written

That last point is not cosmetic. `cli.py` runs `gguf.fraud_check(claimed_estimate,
gguf_meta["params_count"])` and writes `model_info.params_match` into the report. A stale
claimed string after a model swap produces a fraud-check failure in a competition artifact.
Deriving it from the header makes that class of failure unreachable.

`domain` is set for this project's actual field rather than the sample's `coding_assistants`.

### `bench/adtc/report.py`

Parses the profiler's JSON into `score()` keyword arguments. Responsibilities:

- `throughput.tokens_per_second_generation` → `tps_actual`
- `memory.peak_rss_mb / 1024` → `peak_rss_gb` (score.py names it for RSS deliberately)
- `cpu_thermal.core_temp_c_peak` → `max_temp_c`; **`None` propagates as `None`** so
  `score()` sets `thermal_unknown` rather than reading unmeasured as safe
- `throttled` per finding 1 — the 85 °C rule applied here, profiler flag OR'd in
- missing required fields → raise, never default to zero

`accuracy` is left to the caller. With `--skip-accuracy` the block is `[]`, and the hidden 30%
subset is unavailable to us regardless; the harness passes accuracy through explicitly and
labels it as an assumption in the artifact rather than inventing a number.

### `bench/profile.py` — the product path

The pass that exercises what the profiler never touches:

1. Boot the two-process topology (`LlamaServer` + gateway)
2. Attach `bench/sampler.py` rooted at the gateway process
3. Replay the fixture prompts from `bench/submission/metadata.json` `test_prompts` through
   `POST /v1/chat` — via the contract, like every other client
4. Collect peak/steady RSS, per-generation TPS, thermal
5. Return a record in the same shape `adtc/report.py` produces, so both paths score identically

### `bench/autotest.py` — the autonomous mode

`make profile`. No human in the loop:

1. `install.ensure_profiler()`
2. `runtime.models.resolve_model()` (offline-first)
3. `submission.synthesize()`
4. Run the profiler with `PATH` prepended, `--mode participant --skip-accuracy`
   → `bench/.artifacts/submission.json` — **the scored path**
5. Run `profile.run_product_path()` — **the path that can OOM**
6. Score both via `bench.score.score()`
7. Print both plus the delta
8. Append a row to `bench/optimization-log.md` and a record to `bench/.artifacts/runs.jsonl`

Exit codes: `0` pass · `1` product path disqualifying (OOM / crash / over the 7 GB budget) ·
`2` profiler schema validation failed · `3` fraud check `params_match: false`.

Both paths are scored because they fail differently. The engine can bench cleanly while the
product OOMs — and per `CLAUDE.md`, an OOM kill is a **disqualification, not a deduction**. A
harness that only ran the scored path would report a healthy number for a submission that
cannot survive its own audit.

### Host provenance — do not let a Mac number reach the report

`CLAUDE.md` is explicit: all benchmark numbers in the report come from the x86 target box,
never the Mac. So every artifact records `platform.machine()`, `platform.system()`, and the
git SHA (with the `-dirty` suffix, matching the Makefile's existing `GIT_SHA` logic).

Records produced on `darwin`/`arm64` are stamped `provenance: "dev_host_provisional"`, and
`optimization-log.md` rows from a dev host carry that marker inline. The harness does not
refuse to run on a Mac — the fast loop matters — but a provisional number can never be
mistaken for a report-grade one.

## Makefile surface

| Target | Behaviour |
|---|---|
| `make profile` | autonomous both-paths run + scored verdict (replaces the stub) |
| `make monitor` | live HUD; `ARGS="--pid <n>"` to target explicitly (new) |
| `make bench` | product-path pass only — the fast iteration loop (replaces the stub) |
| `make smoke` | unchanged, out of scope |

`.gitignore` gains `bench/.venv-profiler/` and `bench/.artifacts/`. `bench/submission/metadata.json`
is the only new file that is deliberately tracked.

## Error handling

Every failure names the fix. Ambiguity here costs a debugging session on target day.

| Failure | Response |
|---|---|
| No Python ≥3.11 | error naming `uv python install 3.11` / pyenv |
| No network on first bootstrap | error naming the pinned SHA and the vendoring fallback |
| `llama-bench` not found | error naming `make build` and `brew install llama.cpp` |
| Model unresolvable | delegate to `resolve_model()`'s existing error |
| Profiler exits 2 (bad submission) | surface its stderr verbatim; do not paraphrase |
| Profiler exits 3 (schema invalid) | surface stderr; exit 2 — this is a Gate 1 blocker |
| `params_match: false` | hard failure, exit 3 — fatal at audit, so fatal here |
| Product path OOM / non-zero exit | `score(oom_or_crash=True)` → `DISQUALIFIED`; exit 1 |
| Gateway not running (`make monitor`) | actionable message listing the resolution order tried |
| `/internal/bench/metrics` 404 | degrade to RSS-only, note it in the panel |
| No temperature sensor | `None` → `thermal_unknown`, displayed as `—`, never as safe |

## Testing

Existing `bench/test_score.py` stays green and untouched.

- **`bench/test_sampler.py`** — steady-state window math on a golden series (both the <120 s
  and ≥120 s branches); peak = max; tree walk picks up a spawned child; dead-process samples
  are skipped, not zeroed.
  **Cross-check:** shells into the pinned profiler venv, feeds the *same synthetic sample
  series* through upstream `MemorySampler.report()` and ours, asserts equality. Skipped when
  the venv is absent; required in CI. This is what makes the port safe against drift.
- **`bench/test_adtc_report.py`** — profiler JSON → `score()` inputs; `core_temp_c_peak: null`
  → `thermal_unknown`; 90 °C → penalty applied despite `throttled: false` (finding 1);
  missing required field raises rather than defaulting.
- **`bench/test_submission.py`** — `_runtime` synthesis; `parameters_estimate` derived from a
  GGUF header fixture; keys starting with `_` stripped from the report's submission block.
- **`bench/test_autotest.py`** — orchestration against a stub `adtc-profiler` on `PATH` and a
  stub product path; asserts each exit code; no model download, no network.
- **`bench/test_monitor.py`** — PID resolution order; degradation when the metrics endpoint is
  absent; panel renders with `None` temperature.

Per `CLAUDE.md`'s working method, `sampler.py` and `adtc/report.py` are the two files where a
silent bug is most expensive — they feed the scoring function — so both get an adversarial
review pass before this is called done.

## Out of scope

- **Accuracy / `S_acc`.** The hidden 30% subset is unpublished, and `accuracy.py` runs lm-eval
  against the raw GGUF — our tutoring layer is invisible to it (`rules-digest.md` Q6). Wiring
  lm-eval is separate work.
- `make smoke`, `make package`.
- Resolving the Gate-1 date conflict or the six open questions in `rules-digest.md`.
- Vendoring the profiler as an offline fallback — designed for, not built.

## Open items inherited, not resolved here

`tps_max` stays at the provisional 15.0 with `tps_max_provenance="provisional_reference"`,
which `score.py` already models. Per `rules-digest.md` Q2 the real value is the cohort maximum,
so every artifact records the provenance alongside the number. When the true value lands, the
recorded runs can be rescored without re-measuring.
