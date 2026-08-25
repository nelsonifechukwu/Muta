# Muta IQ experiment report and profiler

This local, offline report explains how Muta’s model and runtime choices developed from July to
20 August 2026. Its operational appendix profiles the GGUF files in `../model/` with
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

To share the report with other devices on the same trusted Wi-Fi network, use read-only LAN mode:

```bash
./dashboard/start.sh --lan --no-open
```

Open `http://<this-mac-ip>:8765` on the other device. LAN mode serves the report and its evidence
API but rejects profiling, cancellation, promotion, and deletion requests.

The report server uses only the Python 3 standard library (`http.server` and `sqlite3`). Profiling
still requires `adtc-profiler`. The launcher checks `~/miniforge3/envs/ai/bin/adtc-profiler` by
default; set `ADTC_PROFILER` to use another executable.

## What the report contains

- A chaptered account of the score, runtime baseline, model funnel, GGUF and quantisation work,
  ternary branch, weight-streaming tests, the 19 August campaign, and the 20 August overnight
  model and AVX2 extension.
- A seven-artifact paired total-score figure with scalar and portable AVX2 bars, plus a dedicated
  two-finalist figure that shows the latest direct scalar and controlled AVX2 totals. The charts
  print each total and identify the winner under each accuracy sample.
- Interactive score, disk-budget, and website-sensitivity controls. These controls are read-only:
  they do not change campaign data or stored runs.
- Native HTML and SVG figures that work without a network connection, including three hand-drawn
  mechanism diagrams: the audit binary's two kernel paths, the artifact derivation chain, and the
  submission boundary that decides which optimisations can score.
- Tufte-style margin notes in the right rail. Above 1180 px they float beside the paragraph that
  cites them; below that they fall into the flow as indented blocks (they are `<span>`s, so the
  narrow-width rule must set `display: block` or they land mid-sentence).
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

   The overview and overnight chapter use the 20 August direct finalist reports from
   `../../bench/measurements/campaign-20260820-overnight/summary.json`. The operational campaign
   table remains the dated 19 August four-model set so both complete campaigns stay inspectable.
   If an override points to a different direct campaign, the page displays a warning and leaves
   the configured rows in the operational appendix until the report itself is deliberately revised.

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

4. **Controlled AVX2 proxy.** The 19 August five-artifact campaign and 20 August two-finalist
   extension use the GCP 2C/4T proxy with AVX, AVX2, FMA, and F16C enabled; native tuning and
   AVX-512 disabled. They use the fixed/capped 15 tok/s score, but are not participant-profiler
   runs. The source artifacts are
   `../../bench/measurements/campaign-20260819/avx2-score-of-record/comparison.json` and
   `../../bench/measurements/campaign-20260820-overnight/summary.json`. The final Qwen AVX2 row
   transfers the pinned source measurement only after tensor-identity verification. The dashboard
   state API exposes the dated campaign as `campaign_avx2_score` and the extension as `overnight`.

5. **Development result.** Earlier Mac, Docker, GCP, or custom-engine evidence used to accept or
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

## Publish as a static site (GitHub Pages)

The report can be rendered without its server:

```bash
python3 muta-iq/dashboard/build_static.py --out site     # or: make pages
```

`build_static.py` copies the three page files, pre-renders the `/api/state` payload into
`api/state.json` (with every stored run and its raw report embedded, e-mail addresses
redacted), and stamps `<html data-snapshot="api/state.json">`. That attribute switches
`script.js` into **published-snapshot mode**: it fetches the file once over a relative URL (so
the site works under a `/<repo>/` project-page prefix), keeps every read-only view including
History and Raw report, shows a "Published snapshot" pill, and disables Start profile, Set as
submission, and Delete record. The build fails if any evidence lane is missing rather than
publishing "unavailable" placeholders, and it only clears an output directory it created.

`make vercel` deploys that output to Vercel (project `muta-iq`, https://muta-iq.vercel.app) as a
prebuilt upload, and `.github/workflows/pages.yml` runs the same build on pushes to `main` that
touch the dashboard, `muta-iq/metadata.json`, or `bench/measurements/` for the repository's
GitHub Pages project page. See `docs/report-hosting.md` for both, including the
private-repository caveat for Pages.

## Tests

From the repository root:

```bash
.venv/bin/python -m pytest muta-iq/dashboard -q      # app logic, report safeguards, static build
node --check muta-iq/dashboard/script.js
```
