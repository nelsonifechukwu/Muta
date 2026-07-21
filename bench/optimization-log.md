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
| _(first row lands 17 Jul — the zero-RAM-cost wins)_ | | | | | | | | | | |

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
