# RESULTS — configuration/architecture changes, paired with measured results

**The rule: every configuration or architecture edit lands with a same-day entry here,**
stating the exact configuration that produced the numbers. No entry, no change. Entries are
grouped by day, newest first. This file is the human-readable daily journal; the scored
ablation rows (ADTC exchange-rate math) stay in [`bench/optimization-log.md`](bench/optimization-log.md),
and engine behaviours the numbers depend on are in [`docs/engine-flags.md`](docs/engine-flags.md).

**Metrics of record:**
- **Peak RAM** — RSS of the llama-server process tree (the unit the ladder and the
  competition profiler use). Where a reading was unreliable, that is said explicitly.
- **Max tok/s** — decode rate, engine-reported (`timings.predicted_per_second`), warm run.
- Plus, when measured: prefill tok/s, draft acceptance, multi-turn prefix reuse.

**Hardware contexts** (every number names one):
- `emulated` — Apple M2 Pro host (10-core, 16 GiB); Docker VM aarch64, 8 GiB / 10 vCPU,
  running the `linux/amd64` AVX2 engine under binary translation. Dev signal only.
- `native` — same M2 Pro, pinned llama.cpp `b10035` **arm64** release on the host. Dev
  signal only.
- `x86 target` — the competition-class box. **No numbers exist yet**; only these will be
  report-grade.

Model throughout (unless noted): `models/core/Qwen3.5-4B-Q4_K_M.gguf` — hybrid
architecture, 8/32 full-attention layers (per-token KV ≈ 24.5 KiB at q8_0-K/f16-V),
24 recurrent layers at a constant **50.25 MiB f32 state per slot** (and per context
checkpoint). Thinking on, `--reasoning-budget 512`.

---

## 2026-07-31

### A. Capped engine config (the new baseline) — docker/emulated

**Configuration** (now the `RuntimeConfig` defaults, emitted by `runtime/server.py`;
PRs #4–#10): `-c 2048 --parallel 2 --ctx-checkpoints 4 --cache-ram 256 -b 512 -ub 128
--cache-type-k q8_0 --reasoning-budget 512 --threads 8 --threads-batch 10 --jinja`,
speculation **off** for this measurement. Previous config differed in: `-np` auto (→4
slots), checkpoints 32/slot, cache-ram 8192 MiB, threads 10/10, engine flags injected via
a compose JSON string.

| Metric | Value |
|---|---|
| Peak RAM (after multi-turn probe) | **4.44 GB** (was 4.8 GB and still climbing under the old config) |
| Max tok/s (decode, warm) | **6.72** |
| Multi-turn prefix reuse | turn 2 processed 30 of 65 prompt tokens (checkpoint restore intact under the 4-checkpoint cap) |

**Notes:** RSS is now *bounded by design* — worst case ≈ 2 slots × (50 MiB state + 4 × 50 MiB
checkpoints) + 256 MiB prompt cache ≈ 750 MiB over the ~2.9 GB load footprint. One
consequence to decide on: explicit `-np 2` splits `-c 2048` into **1024 tokens per slot**
(`kv_unified=false`); the old auto mode shared 2048. Long dialogues hit the slot ceiling
sooner; raising `MUTA_RT_N_CTX` to 4096 costs only ~50 MiB (attention KV is cheap on this
hybrid) and is pending a decision. `docker stats` disagreed with in-container `ps aux` on
this host; `ps aux` inside the container is the reading trusted here.

### B. Config A + speculative decoding (Qwen3.5-0.8B draft) — docker/emulated

**Configuration:** A plus `--spec-type draft-simple --spec-draft-model
models/draft/Qwen3.5-0.8B-Q4_K_M.gguf --spec-draft-n-max 8 --spec-draft-n-min 1
--spec-draft-p-min 0.75`. (First time speculation has *ever* been active on this branch —
see Notes.)

| Metric | Value |
|---|---|
| Peak RAM | **≈ 5.46 GB** (+1.02 GB vs A) |
| Max tok/s (decode, warm) | **4.77** (−29% vs A) |
| Draft acceptance | **98.4%** (316/321 tokens; engine-reported 0.979 / 0.993 per turn) |
| Multi-turn prefix reuse | identical to A (30/65) |

**Notes:** the headline result of the day — **near-perfect acceptance, still slower.**
On CPU, verifying a drafted batch costs close to full price (no idle-compute discount as
on GPUs), so you pay for generation twice. Verdict parked pending x86 target numbers;
flip with one line: `MUTA_RT_SPEC_TYPE: "none"`. Historical correction: speculation was
configured but **silently dead** before today (b10035 requires `--spec-type`; also the
previously-configured Qwen3-0.6B draft is vocab-incompatible — 151,936 vs 248,320 — and
is rejected by the engine outright).

### C. Native mode (`./run.sh --native`) — same RuntimeConfig, arm64 engine on host

**Configuration:** identical `RuntimeConfig` flags to A/B except no thread pinning
(llama.cpp's own Apple P/E-core detection), pinned llama.cpp `b10035` (`602f828b4`)
macos-arm64 release binary, gateway via host uvicorn; db + frontend stay in docker
(nginx upstream `host.docker.internal:8000`).

| Metric | draft OFF | draft ON (0.8B) |
|---|---|---|
| Max tok/s (decode, warm) | **30.84** | 24.72 (−20%) |
| Draft acceptance | — | 98.41% |
| Multi-turn prefix reuse | 30/65 | 30/65 |
| Peak RAM | not reliably measured (host `ps` RSS readings implausible — flagged, not trusted; engine-accounted ≈ 2.9 GB expected) | same caveat |

**Notes:** **~4.5× the emulated stack** (30.84 vs 6.72) — the single biggest dev-loop win
available; emulation, not the engine, was the dominant cost on this machine. Speculation
is net-negative natively too, so the CPU verify-cost argument holds even off emulation.
Model load: seconds, vs minutes emulated.

### D. Fixes that changed no numbers but changed their meaning

- `runtime/kvmath.py` now models the hybrid: per-token KV was **overstated 4×**
  (all-32-layer formula) and the 50.25 MiB/slot recurrent state was uncounted.
  `docs/kv-budget.md` regenerated; budget "fits?" verdicts are now trustworthy (with the
  checkpoint-multiplication footnote).
- Verification method traps recorded in `docs/engine-flags.md`: this engine build prints
  **no** `[spec]`/checkpoint banner at default verbosity (verify via `GET /slots` →
  `"speculative":true` or `timings.draft_n`), and `docker stats` mem readings were
  internally inconsistent on this host.

---

## 2026-07-30

### A. Pre-optimization production config (session baseline) — docker/emulated

**Configuration** (what the compose stack actually ran before today's changes):
`-c 2048 --jinja -b 512 -ub 128 --cache-type-k q8_0 --reasoning-budget 512` via
`MUTA_RT_EXTRA_SERVER_ARGS`, everything else at engine defaults: `-np` **auto → 4 slots**
(unified KV, 2048 shared), **32 context checkpoints/slot**, **8192 MiB** prompt cache,
threads **10/10** (all VM cores, shared with gateway/db/nginx). Draft flags present but
**inert** (no `--spec-type`) — no speculation despite the config's intent.

| Metric | Value |
|---|---|
| RAM at load | 2.9 GB (model 2603 MiB — of which 1297 MiB AVX2-repacked into anonymous RAM — context 250 MiB, compute 31 MiB) |
| Peak RAM after just 4 short requests | **4.77 GB, still climbing** (8 checkpoints ≈ 400 MiB + 12 prompt-cache saves ≈ 57 MiB each) |
| Max tok/s (decode, warm) | **~5.3** (cold first run 2.95; run-to-run variance 3.1–5.4 — emulation is noisy) |
| Prefill tok/s | 10.1–13.2 at `-ub 128` |
| Multi-turn prefix reuse | works: turn 2 processed 149 of 269 tokens (checkpoint restored at end of turn-1 prompt); identical re-prompt processed only 4 |

**Notes:** the unbounded RAM drift and the 4-slot state cost (4 × 50 MiB for a single-user
stack) motivated the caps that landed 07-31. Reuse working even with thinking-stripped
history was a positive surprise (checkpoint restore, `size = 50.251 MiB` in the log).

### B. n-gram speculation experiments — docker/emulated, config A + `--spec-type ngram-simple`

| Variant | Result |
|---|---|
| Engine defaults (lookup N=12) | **zero drafts generated** — silent no-op on tutoring content |
| Tuned `size-n 4 / size-m 12` | drafts fire: 12% acceptance (turn 1), 22% (turn 2, mean accepted run 3.3); decode ≈ baseline — net-neutral under emulation, zero RAM cost |

**Notes:** parked as the zero-RAM option for the x86 target box (`spec_type:
"ngram-simple"` is wired with the tuned params).

### C. Engine facts established (no config change; they gate everything above)

`--spec-type` gate (default `none` — draft flags alone are dead); Qwen3-0.6B **rejected**
as draft (vocab 151,936 vs 248,320); `-np auto` = 4 slots; default threads = all cores;
`--cache-ram` default 8192 MiB; hybrid state = 50.25 MiB/slot/checkpoint; prompt-cache
entry ≈ 57 MiB per conversation.

---

## Earlier (reconstructed from repo records — provenance approximate)

### ~2026-07-24 → 29 — compose-comment era measurements (docker/emulated, 4B)

- "~3.7 tok/s" decode with thinking on — consistent with the 07-30 cold-run 2.95–3.7 band.
- "Core + the speculation draft measure ~4.2 GiB" — **now known to be misattributed**: the
  draft never loaded (dead flags); the 4.2 GiB was the core engine's own unbounded
  checkpoint/prompt-cache drift, the thing the 07-31 caps fixed.
- "Unbounded thinking measured 1946 tokens (8.7 min) on 'say hello'" — motivated
  `--reasoning-budget 512`, which remains in force.

### 2026-07-20 — autonomous profile run (from `bench/optimization-log.md`)

- 18.1 tok/s / 0.58 GB / S_total 73.4 — **Qwen3-0.6B smoke fixture**, `dev_host_provisional`,
  not comparable with any 4B row above.
