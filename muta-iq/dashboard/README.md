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

- Displays the provenance-complete 19 August GGUF campaign from
  `../../bench/measurements/campaign-20260819/summary.json`: exact model and binary hashes,
  interleaved rounds/internal samples, task sample counts and confidence intervals, and the
  official profiler-capped score at `TPS_REFERENCE = 15`. Override the path with
  `MUTA_CAMPAIGN_SUMMARY`.

- Preserves the conflicting public-webpage interpretation in a second, non-blended panel loaded
  from `avx2-website-relative-summary.json`. It shows the same-host AVX2 deployment measurements
  under cohort-relative `100 × TPS/TPS_max` at every recorded pre-entry cohort floor. Because
  the candidate joins the cohort, the effective denominator is `max(floor, candidate TPS)`.
  Override that path with `MUTA_CAMPAIGN_ALTERNATIVE`.

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

## Scores and the historical archive

The executable official profiler implements:

```
S_total = 0.50·S_acc + 0.30·S_perf + 0.20·S_eff − P_thermal
S_perf  = min(TPS / 15, 1) × 100
S_eff   = max(0, (7 GB − peak RSS) / 7 GB) × 100
P_thermal = 10 if throttled or core temp > 85 °C
crash / OOM ⇒ disqualified (S_total = 0)
```

The competition webpage separately describes a cohort-relative denominator. No public dated
clarification resolves that contradiction; this dashboard follows the code that will execute.
`S_acc` remains an ARC-Easy proxy; the real score also includes judging-panel quality.
Campaign RSS cards add a clearly labelled 45 MiB estimate for the profiler Python root to the
measured llama-bench child-tree peak; consequently the displayed efficiency and composite are
estimates, while throughput is directly measured.

The SQLite chart/table below it is deliberately labelled **Historical profiler archive**.
It retains the dashboard's old capped local-reference calculation for reconstructing past
runs, including records from different Macs and engine regimes. Its fastest stored run is
not a defensible competition denominator, so archive totals must not be used to rank the new
campaign. The African-language and budget-laptop badges are also shown only as claims; their
judging-panel multipliers are not folded into local totals.

## Tests

```bash
cd dashboard && python3 test_app.py
```
