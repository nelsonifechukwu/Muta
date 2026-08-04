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

## 2026-08-04

### C. `./run.sh --model PATH` — the core model is now hot-swappable (config change, no perf delta claimed)

**Change:** `run.sh` grew `--model PATH` (default `models/core/Qwen3.5-4B-Q4_K_M.gguf`,
docker + native modes). The served-model identity still lives only in
`MUTA_RT_MODEL_DIR/FILE/ALIAS`; the flag just derives those three values —
`docker-compose.yml`'s three model lines became `${MUTA_MODEL_*:-<old literal>}`
interpolations (bare `docker compose up` / `make up` unchanged), `native_up`'s hardcoded
exports became the derived values, and the provisioning gate now checks the *chosen*
file (a missing custom model dies immediately with a fetch hint instead of triggering a
roster fetch that couldn't produce it). Alias = filename stem lowercased; the default
keeps the exact `qwen3.5-4b` identity. Guardrails: docker mode requires the file under
`./models` (the only mount); a warn fires on any override (mmproj pairs with the 4B
family; docker's active draft speculation rejects out-of-vocab cores — flip
`MUTA_RT_SPEC_TYPE=none`). Motivated by section B below: the 4B-vs-0.8B and D1
quant-candidate comparisons need model swaps without config edits.

**Verified (same day):** `bash -n`; `--help`; `docker compose config` resolves the three
env values correctly both bare (old literals) and overridden; `--model missing.gguf`
and bare `--model` die with the intended messages; live native boot with
`MUTA_RT_MODEL_*` set exactly as the flag derives them for
`models/draft/Qwen3.5-0.8B-Q4_K_M.gguf` (alt ports 8001/8181 — a prior gateway held
8000) — `/v1/ready` reached `inference:true`, the engine's `/v1/models` reported
`qwen3.5-0.8b-q4_k_m`, and a probe completion decoded at **110.7 tok/s** (native,
`dev_host_provisional`; consistent with section B's 96–104 llama-bench rows). A full
emulated-docker boot with a swapped model was **not** run (10+ min emulation tax);
compose-level env resolution is verified, the in-container boot path is the same
`RuntimeConfig` seam. RUN.md documents the flag.

### B. Core-model bake-off through the scored path: Qwen3.5-4B vs Qwen3.5-0.8B — native + docker/emulated, `dev_host_provisional`

**Question:** what would each model score as *the* core model, on all three axes? First-ever
rows for the 0.8B as core (it had only ever been measured as a draft).

**Tooling:** profiler-mirror script (preserved at `bench/.artifacts/adtc_mirror-20260804.py`)
replicating the ADTC methodology exactly per `docs/rules-digest.md` — `llama-bench -m <gguf>
-p 512 -n 128 -o json` with 0.1 s psutil whole-tree RSS sampling — plus one deliberate
deviation: `-ngl 0`, because the arm64 dev binary would otherwise offload to Metal and the
audit box has no GPU. Native `llama-bench` was extracted into `runtime/build/bin/` from the
same pinned b10035 macos-arm64 release archive `run.sh` uses (it ships only `llama-server`).
Docker rows ran the backend image's own x86 `llama-bench` under emulation. **Ambient load:**
host was not quiet (load avg 4.4 → 8.5 across the native rounds); native rows are 2
interleaved A/B rounds and were consistent anyway. Raw rows:
`bench/.artifacts/model-compare-20260804.jsonl`.

| Context | Model | decode tok/s (tg128, scored) | prefill tok/s (pp512) | peak tree RSS |
|---|---|---|---|---|
| native | 4B Q4_K_M | 26.46 ±0.83 / 25.94 ±1.42 | 90.4 / 91.0 | 5.08 / 5.28 GB |
| native | 0.8B Q4_K_M | 96.15 ±9.33 / 103.96 ±4.29 | 441.7 / 457.5 | 1.26 GB |
| docker/emulated | 4B Q4_K_M | 3.89 ±0.09 | 14.4 | 4.36 GB |
| docker/emulated | 0.8B Q4_K_M | 7.59 ±0.12 | 88.5 | 0.88 GB |

**Findings that outlive the numbers:**

1. **The scored-path RSS is not our tuned footprint.** llama-bench runs with its own default
   flags — none of `RuntimeConfig`'s caps apply. 4B scored-path RSS is **4.36 GB on the x86
   code path** (2.55 GiB mmap + ~1.3 GiB AVX2 repack + ctx) vs the tuned server's 3.1 GiB
   phys_footprint, and `--no-repack` cannot be passed to the audit's fixed invocation. S_eff
   for the 4B is therefore ~37, not ~55, and no server-flag work can move it. The only lever
   on S_eff is the model file itself (smaller quant / smaller model).
2. **llama-bench defaults to 6 threads on the M2 Pro natively** (= P-core count) — the audit
   path lands on the good thread count by itself there; the emulated container used all 10
   vCPUs (its default), consistent with the known-bad all-cores regime.
3. **Emulation compresses the model-size speed ratio** (0.8B/4B = 1.95× emulated vs 3.8×
   native). Bandwidth-bound decode on real hardware tracks file-size ratio (5.15×) closer
   than translated-compute does; do not size-extrapolate from emulated rows.
4. Scored through `bench/score.py` at provisional `tps_max=15`, with **estimated** accuracy
   (no lm-eval measurement exists for either GGUF; hidden-task mix unknown): the verdict
   flips on two unknowns — the accuracy gap and the audit box's memory bandwidth. With a
   math-domain-like gap (est. ~72 vs ~38) the 4B wins wherever it clears ~13 tok/s
   (needs ≳27 GiB/s bandwidth); with an arc_easy-like gap (est. ~84 vs ~66) the 0.8B wins
   in every scenario because +50 S_eff pts (+10) plus any S_perf shortfall of the 4B
   outweigh a ≤20-point accuracy gap (−10). Break-even accuracy gap ≈ 20 + 0.6×(15 −
   4B_tok/s on the audit box) points. Decision stays with the 4B pending measured lm-eval
   on both GGUFs and the organizer answers (task mix, audit hardware) — see the session
   summary in the conversation log / recommendation below.

**Verdict:** 4B remains the core model. The 0.8B-as-core option is real only if the hidden
accuracy task is easy-MCQ-like *or* the audit box is bandwidth-starved (<~25 GiB/s) *or*
the cohort tps_max lands far above 15 — all three currently unknowable from here. The
already-staged D1 smaller-4B-quant bake-off (UD-Q3_K_XL 2.1 GiB, IQ4_XS 2.3 GiB) attacks
the same S_perf/S_eff deficit without the accuracy cliff and should run first. Measuring
real lm-eval accuracy for both GGUFs is the single highest-value next measurement: the
whole decision is one accuracy delta.

### A. Cheap native probes — decode-thread floor (T4/T5) and repack toggle (WINNER-NOREPACK) — native, `dev_host_provisional`

**Tooling:** `WINNER-NOREPACK`, `T4-DECODE`, `T5-DECODE` added to `bench/native_sweep.py`'s
`CONFIGS` (cactus-inspired: their macOS decode path caps at 4–5 threads even on big cores,
and they deliberately keep weights file-backed/evictable, accepting −17% decode —
`docs/cactus-survey.md` items 2–3). `T4-DECODE`/`T5-DECODE` are `_T6` with `--threads`
dropped to 4/5 (`--threads-batch` held at 6 — prefill was never in question). `WINNER-NOREPACK`
is the shipped `WINNER` config plus `--no-repack` (Step 1 confirmed the flag exists at this
pin: `--repack, -nr, --no-repack ... default: enabled`; see `docs/engine-flags.md`).

**Conditions — read before trusting a number:** this sweep did **not** run on a quiet host
and did **not** complete in one sitting. It spans three sessions — 2026-08-01 23:37 (load avg
~4.3), 2026-08-02 ~08:03 (load avg not captured at that exact point, but the surrounding
session was ~5–20), and 2026-08-04 03:22–03:41 (load avg swinging 3.9–20.1 within the
20-minute window) — while another project's `llama-cli`/IDE tooling ran concurrently
throughout (not killed, per standing instruction). Two runs were lost to the load: a
background chain died mid-round after an apparent environment reset (engine log shows the
second `WINNER` invocation receiving two SIGINTs and exiting before its JSON row was
written), and one `WINNER` full-suite anchor itself failed late (`ReadTimeout`) after its
four decode probes were already captured — that row is kept with `ok: false` since the
decode/prefill numbers it recorded before failing are still valid data points, but it has no
`footprint_mib`. Every remaining run after the second stall used the **speed** suite for
`T4/T5-DECODE` and the `WINNER` anchors (full suite only for the original two `WINNER` rows
and `WINNER-NOREPACK`, where the footprint reading is the point). Given all this, **decode
maxes here are well below the 2026-08-01 quiet(er)-host record of 31.09** (section A above) —
verdicts below are relative A/B within each interleaved round, not absolute performance
claims.

**All rows collected this task** (`bench/.artifacts/native-sweep.jsonl`; `decode_tps` = the 4
warm throughput probes, `decode_tps_max` includes the 2 reuse-probe generations per the
harness convention):

| Config | Suite | decode_tps (4 probes) | decode_tps_max | floor (min probe) | prefill tps | phys_footprint MiB |
|---|---|---|---|---|---|---|
| WINNER (anchor 1) | full | 15.05, 22.86, 13.17, 18.25 | 22.86 | 13.17 | 67.4 | 3236 |
| T4-DECODE (round 1) | speed | 11.38, 8.97, 14.2, 15.0 | 20.06 | 8.97 | 55.9 | 3152 |
| WINNER (anchor 2, `ok:false` — late ReadTimeout, decode probes valid) | full | 2.21, 11.88, 16.58, 23.33 | 23.33 | 2.21† | 70.2 | — (never reached) |
| T5-DECODE (round 1) | speed | 19.19, 15.69, 12.88, 16.21 | 24.66 | 12.88 | 61.6 | 3098 |
| WINNER (anchor 3) | speed | 13.16, 24.56, 27.38, 24.22 | 27.38 | 13.16 | 78.4 | 3104 |
| WINNER-NOREPACK | full | 26.59, 27.09, 26.49, 20.68 | 27.09 | 20.68 | 73.0 | **602** |
| T4-DECODE (round 2) | speed | 24.86, 25.89, 24.95, 25.65 | 25.89 | 24.86 | 83.4 | 3097 |
| WINNER (anchor 4) | speed | 19.31, 22.42, 22.82, 25.04 | 25.04 | 19.31 | 67.0 | 3098 |
| T5-DECODE (round 2) | speed | 25.65, 18.97, 18.89, 25.35 | 25.65 | 18.89 | 84.8 | 3326 |

† Anchor 2's 2.21 tok/s single-probe floor is treated as an untrusted extreme-contention
outlier (nothing else in the sweep, including the same run's other three probes, is
anywhere near it) and is excluded from the floor comparisons below.

**Verdict — `T4-DECODE`: reject.** Decision rule (stated in advance): keep only if max ≥
`WINNER`'s max **and** the loaded-host floor improves. Round 1 (heavy load) fails both
outright: max 20.06 is below *both* bracketing `WINNER` anchors (22.86, 23.33) and floor
8.97 is well below the bracketing floor of 13.17. Round 2 (lighter load) is not a rescue:
max 25.89 beats the immediately-following `WINNER` anchor (25.04) but stays below the
immediately-preceding one (27.38), and while its floor (24.86) exceeds the following
anchor's floor (19.31), that is the lightest-load, best-case pairing in the whole dataset —
not the "loaded-host floor improves" case the probe exists to test. The regime the lever was
supposed to help (contention) is exactly where it measured worst.

**Verdict — `T5-DECODE`: inconclusive under load — re-run on a quiet host.** Same rule.
Round 1: max 24.66 beats the preceding anchor (23.33) but loses to the following one
(27.38); floor 12.88 is a statistical tie with the following anchor's floor (13.16, Δ0.28).
Round 2: max 25.65 marginally beats the preceding anchor (25.04, Δ0.61); floor 18.89 is
marginally *below* the preceding anchor's floor (19.31, Δ−0.42). Every comparison is inside
the noise band this host produced elsewhere in the same session (single-probe swings of
4–13 tok/s within one run were common). Per the standing instruction for this task, a
result this close under heavy, uncontrolled load is recorded as inconclusive rather than a
marginal keep — `runtime/config.py` is **not** changed; the P-core count (6) stays the
default. Re-run both configs on a quiet host before revisiting.

**Verdict — `WINNER-NOREPACK`: keep as a documented product-RAM lever (not wired as
default in this task).** `phys_footprint` after the full suite's 3-conversation stressor:
**602 MiB with `--no-repack`, vs 3097–3326 MiB across every one of the other eight rows in
this table** (repack on) — a consistent ~2.5–2.6 GiB drop, robust across both suite type and
wildly different load conditions (the cleanest signal this noisy host produced all task).
This corrects `docs/engine-flags.md`'s older "~1.3 GiB repacked" estimate — repacking
appears to anonymize most of the model's weight matrices, not a fixed ~1.3 GiB subset.
Decode was **not** measurably worse: NOREPACK's max (27.09) and floor (20.68) both sit at
or above the full range of `WINNER` anchors in this table (22.86–27.38 max, 13.16–19.31
floor) — no sign of cactus's reported −17% for the equivalent trade, though see the
ambient-load caveat above. Accuracy 4/4, longctx accepted, checkpoint reuse identical
(29/33) — nothing else regressed.

Priced with `bench/score.py`'s exchange rate at the provisional `tps_max=15`
(`ExchangeRate.delta_points(tps_before=27.38, delta_tps=27.09-27.38, delta_ram_gb=(602-3236)/1024)`):
**ΔS_total = +7.35**, and essentially all of it is the RAM term — both 27.38 and 27.09 tok/s
sit well past the `tps_max=15` clamp, so `S_perf` scores identically for either and the
decode delta contributes ≈0. **Caveat that matters more than the price:**
`docs/rules-digest.md` confirms the ADTC profiler's throughput *and* RSS sampling both wrap
a `llama-bench`/`llama-cli` invocation the profiler launches itself
(`llama-bench -m <model.gguf> -p 512 -n 128 --output json`, fixed flags) — entirely
independent of `RuntimeConfig`/`runtime/server.py`. `--no-repack` is therefore a
**product-RAM-only** win: it shrinks our own backend container's/dev-host's actual memory
use, but is not expected to move the official `memory.peak_rss_mb` score at all. No
`RuntimeConfig` field for repack exists yet; wiring `--no-repack` in as a default (a new
field + `server.py` flag emission + a `test_server_command.py` case) is a follow-up
decision, not made in this task — the brief's Step 4 only mandates a `runtime/config.py`
edit for a `T4/T5-DECODE` keep, and neither of those kept.

**Provenance:** raw rows in `bench/.artifacts/native-sweep.jsonl` (names `WINNER`,
`T4-DECODE`, `T5-DECODE`, `WINNER-NOREPACK`); engine logs in
`bench/.artifacts/native-logs/` (`WINNER.log` holds the last-run invocation only — the
sweep harness truncates per-name logs on each run, so the failed anchor-2 attempt's log
was overwritten by anchor 3/4's later runs; the SIGINT evidence for the lost background
round was observed directly during the session, not preserved in a committed log). Engine
b10035 arm64 release, Qwen3.5-4B-Q4_K_M, thinking on, budget 512, unchanged from the
2026-08-01 sweep.

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

### C. Bandwidth-ceiling diagnostic (bench/ceiling.py) — native, `dev_host_provisional`

**Tooling:** new `bench/ceiling.py` (+ `bench/test_ceiling.py`, 3 tests) — the
cactus-blog diagnostic (`docs/cactus-survey.md`): CPU decode of a dense GGUF is
memory-bandwidth-bound (each token streams ~the whole weight file once), so
`ceiling_tps = bandwidth / model_bytes` gives a same-order-of-magnitude speed limit,
and `measured / ceiling` grades whether thread/flag tuning is still worth doing.
`measure_copy_bandwidth_bytes_s()` is a best-of-N STREAM-copy-style numpy probe
(reads+writes counted); the model's file size stands in for bytes/token (attention-KV
and SSM-state re-reads are each <2% on this hybrid at `-c 2048`, so the ceiling is a
few percent optimistic — the safe direction for a stop rule).

**Command:**

```bash
python3 -m bench.ceiling --model models/core/Qwen3.5-4B-Q4_K_M.gguf --measured 31.1
```

(31.1 tok/s = the 2026-08-01 native decode record, section A above.)

**Host was busy** during this run: `llama-cli` at ~92% CPU and `codex` at ~85% CPU were
both running concurrently (load average 5.35/7.31/6.05 on the 10-core, 6P+4E M2 Pro),
contending for the same memory bandwidth the probe measures. 5 consecutive invocations
swung 38.5–95.1 GiB/s (ceiling 15.1–37.3 tok/s, "% of ceiling" 83–206% — the >100%
readings are the probe undershooting true bandwidth under contention, not decode
outrunning memory). Since contention can only *lower* a measured copy bandwidth, never
inflate it, the highest of the 5 runs is the least-contaminated estimate and is the one
recorded below; the low outliers are noted for honesty, not used.

| Metric | Value |
|---|---|
| Model size (bytes/token proxy) | 2.55 GiB (2,740,937,888 bytes) |
| Measured copy bandwidth (best of 5 busy-host runs) | **95.1 GiB/s** |
| Ceiling (`ceiling_tps`) | **37.3 tok/s** |
| Measured decode (native, section A) | 31.1 tok/s |
| **% of ceiling** | **83%** |

**Interpretation (per the brief's rule: ≥70% → tuning done; ≤40% → not bandwidth-limited):**
83% is ≥70% — thread/flag tuning on this box is essentially done; further native decode
gains need a smaller model (quantization/weight size), not more threading or flag work.
This lines up with cactus's own iPhone 17 Pro figure (140/169 = 83%) almost exactly,
despite completely different hardware, which is a reasonable sanity check on the method.

**x86 target prediction:** not produced yet — no spec-sheet bandwidth number exists for
the competition box. Once known, run
`python3 -m bench.ceiling --model models/core/Qwen3.5-4B-Q4_K_M.gguf --bandwidth-gib-s <spec>`
to get its predicted ceiling without needing the hardware in hand.

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
