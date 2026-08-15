# MUTA-IQ profiler dashboard

Local dashboard for profiling the GGUF models in `../model/` with
[adtc-profiler](https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler) —
no more hand-editing `metadata.json` or copying `submission.json` around.

## Launch

```bash
./dashboard/start.sh          # serves http://127.0.0.1:8765 and opens your browser
./dashboard/start.sh 9000     # custom port
./dashboard/start.sh --no-open
```

Zero dependencies — plain Python 3 stdlib (`http.server` + `sqlite3`). The
profiler itself runs from the `ai` conda env; the dashboard finds it at
`~/miniforge3/envs/ai/bin/adtc-profiler` (override with the `ADTC_PROFILER`
env var).

## What it does

- Lists every `*.gguf` in `model/` with size, quant, and param count parsed
  from the filename. Models whose file was deleted but that still have runs in
  the database stay listed (marked "file deleted — runs kept", profiling
  disabled) — deleting a model never deletes its profile records.
- **Profile** button per model: rewrites the repo's `metadata.json`
  (`_runtime.model_path` + model block) for that model, then runs
  `adtc-profiler run --submission . --mode participant` with live log output.
  One run at a time; cancel any time.
- **Quick run** toggle adds `--skip-accuracy` for fast throughput/memory
  smoke tests (no S_acc / S_total for those runs).
- Every run is stored in `dashboard/profiler.db` (SQLite, persistent). Raw
  profiler reports also land in `dashboard/runs/` (gitignored).
- Per-run **History**: view the full report JSON, delete bad runs, or
  **→ submission.json** to promote a run's report to the repo root
  (also re-points `metadata.json` at that model).

## Scores

Computed from the ADTC 2026 rules (profiler README):

```
S_total = 0.50·S_acc + 0.30·S_perf + 0.20·S_eff − P_thermal
S_perf  = min(TPS / TPS_max, 1.0) × 100     TPS_max = fastest tok/s among all stored runs
S_eff   = max(0, (7 GB − peak RSS) / 7 GB) × 100
P_thermal = 10 if throttled or core temp > 85 °C
crash / OOM ⇒ disqualified (S_total = 0)
```

`S_acc` is proxied locally by the arc_easy benchmark score × 100 — the real
S_acc adds a judges' panel component that only exists at audit time.
`TPS_max` follows the official site's formula (`100·TPS/TPS_max`, TPS_max =
the fastest submission) rather than the profiler README's fixed 15 tok/s: the
fastest run in the database — quick runs and deleted models' kept runs
included — stands in for the fastest submission. That run scores S_perf = 100
and every other run, including the same model's other runs, is scored
relative to it (so a model's full run can sit below 100 when its own quick
run was faster). The legend under the chart shows the current TPS_max and
which run set it; S_perf values shift whenever a faster run lands. The
African-language and budget-laptop claims are shown as badges; their +15% /
+10% multipliers apply to the judges' panel score, so they are not folded
into the local S_total.

## Tests

```bash
cd dashboard && python3 test_app.py
```
