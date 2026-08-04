# Optimization log

**ROADMAP deliverable: Tue 14 Jul, `[All]`.** The standing rule: **every optimization is
recorded here as a before/after row the day it lands**, scored through
[`bench/score.py`](score.py). The report's ablation table is built continuously, not
reconstructed from memory in August.

An unlogged optimization did not happen. A logged one that made the score worse is more
valuable than an unlogged one that helped — the ablation table is the project's central thesis
under test, and a negative row is evidence.

## How to add a row

1. Measure before and after with the **same** harness, model, flags and fixture set
   (`make bench`). One variable at a time.
2. Score both through `score.py` and use `compare(before, after)` — it attributes the delta to
   a component and names the driver.
3. Paste the `ΔS_total` it reports. Do not eyeball it.
4. **Verdict** is `keep` / `revert` / `park`. `park` means it needs a decision you can't make
   alone — say who decides.

Numbers taken on a Mac (native or emulated) are **dev signals only** and must be tagged as
such. Only the x86 target box produces report numbers (ROADMAP 9–11 Aug).

## The exchange rate governs every verdict

At the provisional `TPS_max = 15`: **+2.00 pts per tok/s · −2.86 pts per GB · +0.50 per
accuracy point.** So **1 GB = 1.43 tok/s = 5.7 accuracy points**, and any RAM-spending change
must clear `ΔTPS ≥ 1.43 × ΔRAM_GB` to be worth it.

> **Caveat, and it will bite.** [`docs/rules-digest.md`](../docs/rules-digest.md) establishes
> that `TPS_max` is **"highest speed across all submissions"**, not a fixed 15. The exchange
> rate is therefore a function of the cohort: at a cohort max of 30 a tok/s is worth **1.00**
> pt and the break-even **doubles to 2.86 tok/s per GB**. Some verdicts below could flip sign
> when the real `TPS_max` is known. Record the `tps_max` each row was scored against — do not
> assume 15 forever. `score.py` carries `tps_max_provenance` for exactly this reason.

## Log

| Date | Change | Harness | tps_max | Before (TPS / RAM / Acc) | After (TPS / RAM / Acc) | ΔTPS | ΔRAM | ΔAcc | ΔS_total | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-07-31 | RSS ceilings: -np 2, --ctx-checkpoints 4, --cache-ram 256 (was auto-4/32/8192) | two-turn probe, docker/emulated | 15 | ~6.72 / 4.8 GB / — | 6.72 / 4.44 GB / — | ~0 | -0.36 GB | 0 | dev_host_provisional — RAM row only | keep |
| 2026-07-31 | speculation ON: --spec-type draft-simple + Qwen3.5-0.8B (dead flags + incompatible 0.6B before) | two-turn probe, docker/emulated | 15 | 6.72 / — / — | 4.77 / +1.02 GB / — | -1.95 | +1.02 GB | 0 | dev_host_provisional — acceptance 98.4% ; target-box row pending | park (needs x86 numbers) |
| 2026-07-31 | run.sh --native (pinned arm64 b10035 on host; docker default unchanged) | two-turn probe, native | 15 | 6.72 tok/s docker-emulated | 24.72 tok/s native (draft off: 30.84 tok/s; acceptance 98.41%) | +18.00 | ~0 | 0 | dev_host_provisional — dev-loop only, never report-grade | keep |
| 2026-08-01 | threads = P-core count (6/6, auto-derived on darwin; engine default before) | bench/native_sweep.py, native, interleaved 3×3 A/B | 15 | 29.78 max (probed 6.4–23.5 under morning load; -t 10 collapses to 4.4) / — / 4-4 probes | 31.09 max; winner-family floor 20.5 under the same load | +1.31 (max); the loaded-host floor is the real win | 0 | 0 | dev_host_provisional — darwin-only code path, x86 untouched | keep |
| 2026-08-01 | --kv-unified with explicit -np 2 (restores full 2048 shared window; 1024/slot before) | bench/native_sweep.py, native | 15 | 1495-token prompt → 400 / 3375 MiB fp / — | accepted / 3328 MiB fp / — | ~0 | -0.05 GB | 0 | dev_host_provisional — capability fix priced at zero | keep |
| 2026-08-01 | --ctx-checkpoints 4→2 | bench/native_sweep.py full suite, native | 15 | reuse 29/33 / 3519 MiB fp stressed / 4-4 | reuse 29/33 / 3137 MiB fp stressed (combined winner) / 4-4 | 0 | -0.20 GB worst-case bound | 0 | dev_host_provisional | keep |
| 2026-08-01 | native speculation retunes: draft n-max 3 (98.8% acc) 15.75; n-max 8 25.89; ngram-4/12 21.55 — vs 29.6 draft-off | bench/native_sweep.py, native | 15 | 29.6 draft-off | best retune 25.89 | -3.7 to -13.9 | +0.52 GB (draft) | 0 | dev_host_provisional — run.sh --native now exports MUTA_RT_SPEC_TYPE=none; x86 verdict still pending | reject on native (park for x86) |
| 2026-08-04 | cactus GEMV probe: --threads 4 (T4-DECODE, vs 6 shipped) | bench/native_sweep.py, native, interleaved A/B, 2 rounds, heavy uncontrolled ambient load (load avg 3.9-20.1) | 15 | WINNER anchors 22.86/23.33 max, 13.17 floor (bracketing round 1) | 20.06 max, 8.97 floor | -2.80 to -3.27 (round 1) | ~0 | 0 | dev_host_provisional — fails both keep criteria under the exact loaded-host regime the probe targets | reject |
| 2026-08-04 | cactus GEMV probe: --threads 5 (T5-DECODE, vs 6 shipped) | bench/native_sweep.py, native, interleaved A/B, 2 rounds, heavy uncontrolled ambient load (load avg 3.9-20.1) | 15 | WINNER anchors 23.33-27.38 max, 13.16-19.31 floor (both rounds) | 24.66/25.65 max, 12.88/18.89 floor | -0.61 to +1.33 (mixed, inside noise) | ~0 | 0 | dev_host_provisional — max/floor deltas both inside the session's own noise band | inconclusive under load — re-run on quiet host |
| 2026-08-04 | cactus stream-weights probe: --no-repack (WINNER-NOREPACK, repack confirmed present at b10035 via --help) | bench/native_sweep.py full suite, native, heavy uncontrolled ambient load | 15 | WINNER full-suite fp 3236 MiB, max 22.86-27.38 pooled | fp 602 MiB, max 27.09 | -0.29 to +4.23 (no measurable regression) | -2.57 GB | 0 (accuracy 4/4 unchanged) | +7.35 (score.py exchange_rate, tps_before=27.38 — decode clamps at tps_max=15 so the gain is ~all RAM) | keep as documented lever — product-RAM-only (docs/rules-digest.md: profiler's llama-bench call is fixed/independent of RuntimeConfig, so no expected S_eff move); not wired as a RuntimeConfig default in this task |

## Why the ordering is what it is

Zero-RAM-cost speedups (n-gram / prompt-lookup speculation, prompt caching) are **strictly
dominant** — they buy `S_perf` without paying `S_eff`, so no break-even calculation is needed
and they cannot lose. They are Phase 1 (17 Jul), before anything that spends RAM.

Everything that costs RAM is a trade and needs the break-even check. A 1 GB draft model must
return ≥ 1.43 tok/s (at `TPS_max=15`) or it is net-negative — `score.py`'s
`exchange.is_worth_it(delta_tps, delta_ram_gb)` answers this directly.

## A caution on what to optimize

Per [`docs/rules-digest.md`](../docs/rules-digest.md), the official profiler measures
throughput by running **`llama-bench` against the GGUF** — it never invokes our product. So
**orchestration overhead does not cost `S_perf`**, and shaving it wins zero points here (it is
still worth doing for felt latency — log it, but score it honestly as 0). Optimizations that
move the scored number are the ones touching the **model, quantization, KV cache, threads and
engine flags**.

## Autonomous runs (`make profile`)

Appended automatically, one row per run. Two paths because they fail differently: the profiler
path is the number the audit reproduces; the product path is where an OOM kill — a
disqualification, not a deduction — would show up. Rows marked `dev_host_provisional` came
from the ARM dev box and are **not report-grade** (CLAUDE.md: benchmark numbers come from the
x86 target box).

Accuracy is held at an assumed constant (`ASSUMED_ACCURACY` in [`autotest.py`](autotest.py)),
so only the `S_perf` and `S_eff` movement in these rows is meaningful. `tps_max` is the
provisional 15.0; every row is rescorable from `bench/.artifacts/runs.jsonl` once the cohort
value is known.

| date | git sha | host | prof tok/s | prof RAM GB | prof S_total | prod tok/s | prod RAM GB | prod S_total |
|---|---|---|---|---|---|---|---|---|
| 2026-07-20 | 1f1244f9212033b8dafa7fdd2f1d147160cded45-dirty | dev_host_provisional | 18.1 | 0.58 | 73.4 | 18.1 | 0.52 | 73.5 |
