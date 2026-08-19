# Muta IQ experiment report and profiler

This local, offline report explains how Muta’s model and runtime choices developed from July to
19 August 2026. Its operational appendix profiles the GGUF files in `../model/` with
[adtc-profiler](https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler), stores each run,
and can promote a completed report without hand-editing `metadata.json` or copying
`submission.json`.

## Start the report

Run these commands from `muta-iq/`:

```bash
./dashboard/start.sh          # serve http://127.0.0.1:8765 and open it
./dashboard/start.sh 9000     # choose another port
./dashboard/start.sh --no-open
```

The report server uses only the Python 3 standard library (`http.server` and `sqlite3`). Profiling
still requires `adtc-profiler`. The launcher checks `~/miniforge3/envs/ai/bin/adtc-profiler` by
default; set `ADTC_PROFILER` to use another executable.

## What the report contains

- A chaptered account of the score, runtime baseline, model funnel, GGUF and quantisation work,
  ternary branch, weight-streaming tests, and the 19 August model decision.
- Interactive score, disk-budget, and website-sensitivity controls. These controls are read-only:
  they do not change campaign data or stored runs.
- Native HTML and SVG figures that work without a network connection.
- A filterable experiment ledger covering adopted, rejected, inconclusive, and deferred work.
- A progress check against the Africa Deep Tech Challenge FAQ.
- The original profiler dashboard as an operational appendix, including live logs, run history,
  raw reports, promotion, and deletion.

## Evidence labels

The report never treats all benchmark rows as interchangeable.

1. **Official profiler result.** A complete participant run produced by the official executable.
   Throughput and peak RSS over the profiler root and child tree are direct measurements. The
   dashboard loads these rows from
   `../../bench/measurements/campaign-20260819/official-profiler/summary.json`. Override the path
   with `MUTA_CAMPAIGN_SUMMARY`.

   The narrative and headline figures are a dated 19 August snapshot. If an override points to a
   different direct campaign, the page displays a warning and leaves the configured rows in the
   operational appendix until the report itself is deliberately revised.

2. **Profiler-parity estimate.** A controlled reconstruction of the no-AVX profiler environment.
   Throughput is measured; profiler-root RSS is estimated by adding the documented 45 MiB offset
   to the child-tree measurement. The source is
   `../../bench/measurements/campaign-20260819/summary.json`. Override it with
   `MUTA_CAMPAIGN_PARITY`.

3. **Website-relative sensitivity.** Same-host AVX2 deployment measurements rescored with the
   public webpage’s cohort-relative formula. The effective denominator is
   `max(cohort floor, candidate TPS)` because the candidate joins the cohort. These rows come from
   `../../bench/measurements/campaign-20260819/avx2-website-relative-summary.json`. Their RSS column
   uses the same documented 45 MiB profiler-root estimate as the parity screens. Override the path
   with `MUTA_CAMPAIGN_ALTERNATIVE`.

4. **Development result.** Earlier Mac, Docker, GCP, or custom-engine evidence used to accept or
   reject an engineering idea. It explains the decision history but is not ranked against the
   direct profiler campaign.

## Profiler workflow

- The workspace lists every `*.gguf` in `model/` and parses its size, quantisation, and parameter
  count from the filename. Removing a model file does not remove its stored run records; the row
  remains visible with profiling and promotion disabled.
- **Start profile** rewrites the repository’s `metadata.json` model block and
  `_runtime.model_path`, then runs `adtc-profiler run --submission . --mode participant`. Only one
  run can execute at a time.
- **Quick diagnostic run** adds `--skip-accuracy`. It measures throughput and memory but cannot
  produce `S_acc` or `S_total`.
- Each run is stored in `dashboard/profiler.db`. Raw profiler reports are written to
  `dashboard/runs/`, which is gitignored.
- **History** opens every stored run for an artifact. From there, inspect the raw report, remove a
  run record, or set a successful run as the submission candidate. Promotion writes the report to
  the repository root and points `metadata.json` at the same model artifact.

## Scores and the historical archive

The executable profiler implements:

```
S_total     = 0.50·S_acc + 0.30·S_perf + 0.20·S_eff − P_thermal
S_perf      = min(TPS / 15, 1) × 100
S_eff       = max(0, (7 GB − peak RSS) / 7 GB) × 100
P_thermal   = 10 when throttled or core temperature exceeds 85 °C
crash / OOM ⇒ disqualified (S_total = 0)
```

The public competition page describes a different, cohort-relative performance denominator. No
dated public clarification currently resolves the mismatch. The direct campaign therefore follows
the executable that performs the run, while the alternative formula remains a separate sensitivity
analysis.

`S_acc` in these tables is an ARC-Easy proxy, not the unavailable judging-panel tutoring score.
GCP did not expose package temperature, so the direct campaign reports temperature as unavailable;
“no throttling reported” is not treated as a temperature measurement.

The **Historical profiler archive** retains the dashboard’s earlier local-reference calculation so
past records remain reconstructible. Those rows mix machines and engine regimes, and the fastest
stored run is not a defensible competition denominator. Do not use archive totals to rank the
19 August campaign. African-use-case and budget-laptop badges are metadata claims only; their
judging-panel multipliers are not included in local totals.

## Tests

From the repository root:

```bash
.venv/bin/python -m pytest muta-iq/dashboard/test_app.py -q
node --check muta-iq/dashboard/script.js
```
