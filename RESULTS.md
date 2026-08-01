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

## 2026-08-01

### A. Native engine tuning sweep — 24 configs, engine-only (no gateway/db/docker) — native

**Tooling:** new `bench/native_sweep.py` — drives the pinned arm64 `llama-server`
directly over `/v1/chat/completions` (same endpoint the gateway uses) and records warm
decode (max over 4 throughput probes + the 2 reuse-probe generations = metric of
record), prefill (~900-token prompt), tree-RSS
(25 ms sampling) **and macOS `phys_footprint`**, two-turn checkpoint reuse, a
>1024-token window probe, 4 greedy accuracy probes, and a 3-conversation RAM stressor.
Measurement finding that unblocks native RAM numbers: sampled RSS on macOS swings with
file-backed page eviction (2.6–5.3 GiB on identical configs) — `phys_footprint`
(`/usr/bin/footprint`) is the honest figure and is stable run-to-run (±2%).

**Winner (now the `RuntimeConfig` defaults):** old caps + `--threads 6 --threads-batch 6`
(P-core count, auto-derived on Apple silicon by `runtime/config.py`) + `--kv-unified` +
`--ctx-checkpoints 2`, speculation **off natively** (`run.sh --native` now exports
`MUTA_RT_SPEC_TYPE=none`). Unchanged: `-c 2048 -np 2 --cache-ram 256 -b 512 -ub 128
--cache-type-k q8_0 --reasoning-budget 512 --jinja`.

| Metric (native, M2 Pro) | old defaults | new defaults |
|---|---|---|
| Max tok/s (decode, warm; interleaved 3×3 A/B) | 29.78 (median-of-maxes 29.09) | **31.09** (median-of-maxes 30.13) |
| Decode floor under ambient load (busy host, same morning) | **6.4** (B0 probes 6.4–23.5; `-t 10` collapses to 4.4) | 20.5 across winner-family runs (T6+KVU 28.5–29.6; shipped combo 20.6–26.7 in the same window) |
| Prefill tok/s (907-token prompt, median) | 80.8 | **93.1** |
| phys_footprint after 3-conversation stressor | 3519 MiB | **3137 MiB (−382)** |
| Longest accepted prompt | 1024/slot — 1495 tokens → **400** `exceed_context_size_error` (artifact row `B0-longctx-verify`) | full 2048 shared (1495 tokens OK) |
| Two-turn checkpoint reuse | 29/33 prompt_n | 29/33 (identical) |
| Accuracy probes (greedy ×4) | 4/4 | 4/4 |

Decode tok/s here is the max over the 4 warm throughput probes plus the 2 reuse-probe
generations of a run (applied identically to both arms).

**Why each flag:**
- **Threads = P-cores (6/6):** decode is barrier-synchronized; one thread on an E-core
  stalls every step. Engine default measured 23.5 max with a 6.4 floor under load;
  `-t 6` gave the sweep's best maxes (29.6–31.1); `-t 10` catastrophic (4.4). The
  *stability* win needs `--kv-unified` too — `-t 6` alone still probed one 12.2. Prefill
  also loses from E-cores (`-tb 8/10` → 74/61 vs 97 tok/s). Compose still pins 8/10 for
  the container via env (unchanged).
- **`--kv-unified`:** explicit `-np 2` had silently flipped unified KV off, splitting
  `-c 2048` into 1024/slot (the 07-31 open decision). Unified restores the full shared
  window at *lower* footprint (3328 vs 3375) — resolves that decision without raising
  `-c`.
- **`--ctx-checkpoints 2`** (was 4): two-turn restore identical; stressed footprint
  stepped 3519 (old defaults) → 3262 (T6 + checkpoints 2) → 3137 MiB (full winner), and
  the checkpoint cut alone bounds −201 MiB worst-case (2 slots × 2 × 50.25 MiB). 1 also
  passed the two-turn probe but leaves no slack for longer dialogs.

### B. Rejected levers (measured, so nobody re-tries them silently) — native

- **Speculation, every form, remains net-negative on native CPU** (draft-off 29.6):
  draft n-max 3/p-min 0.90/2 draft threads → **15.75** despite 98.8% acceptance;
  n-max 8/p-min 0.75 → 25.89 (92.9%); ngram-simple 4/12 → 21.55 (24.6% acceptance,
  up from 12–22% emulated). Draft configs cost +~520 MiB footprint. x86 target verdict
  still pending (unchanged).
- **`-fa on`** decode-neutral alone; with `--cache-type-v q8_0` the stressed footprint
  was ≈ neutral (3489 vs the 3519 stressed baseline) and decode probed slower that
  round — no win to bank on 8 attention layers, f16 V kept.
- **`-ub 256/512`**: no prefill gain natively (89/84 vs 97 at `-ub 128`); ub 128 also
  keeps the smallest compute buffer. **`--no-mmap`**: −28% decode, +1 GiB footprint.
  **`--mlock`**: unstable decode, no footprint win. **`--cache-ram 64`**: works, but the
  saving is small and it starves cross-conversation warmth; 256 kept (a cap, not a cost).
- `--prio 2`: pathological stalls (0.4 tok/s outliers, prefill 0.9) — never again.

**Provenance:** engine b10035 arm64 release, Qwen3.5-4B-Q4_K_M, thinking on, budget 512;
raw rows in `bench/.artifacts/native-sweep.jsonl`, engine logs in
`bench/.artifacts/native-logs/`. The rows were recorded with the session iteration of
the harness; `bench/native_sweep.py` is its cleaned committed successor (same probes —
the ad-hoc `PRIO2`/`AB-*`/`B0-longctx-verify` rows came through its `run_config()` API,
and full-suite rows recorded before the long-prompt probe existed lack a `longctx` key).
Config changes in `runtime/config.py` / `runtime/server.py` / `run.sh` (tests updated).
Docker/emulated numbers for the new `kv_unified`/`ctx_checkpoints` defaults were NOT
re-measured (native-only session) — and note the docker default now pairs
`--kv-unified` with active draft speculation, a combination no row measures together;
the next docker session should verify both before trusting its numbers.

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
