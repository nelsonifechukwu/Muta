# Hosting the Muta IQ report

The Muta IQ experiment report (`muta-iq/dashboard/`) is published as a static site in two ways.
Both ship the same output of `muta-iq/dashboard/build_static.py` (see "The published-snapshot
mode" below); they differ only in who builds it and where it is served.

| Host | URL | Built by | Status |
|---|---|---|---|
| **Vercel** (project `muta-iq`, scope `iitimiis-projects`) | **https://muta-iq.vercel.app** | locally, `make vercel` (prebuilt upload) | live |
| GitHub Pages project page | `https://nelsonifechukwu.github.io/Muta/` | `.github/workflows/pages.yml` on push to `main` | needs Pages enabled; private repo → paid plan |

## Vercel

`make vercel` (= `scripts/deploy_report_vercel.sh`) deploys to production:

1. `vercel pull` refreshes the linked project's settings into the gitignored `.vercel/`;
2. `vercel build` runs `vercel.json`'s `buildCommand` **locally**
   (`python3 muta-iq/dashboard/build_static.py --out site`) and packages `site/` as Build
   Output;
3. `vercel deploy --prebuilt --prod` uploads only that output (~330 KiB).

No repository sources are sent to Vercel and nothing is built there — the 27 MB tracked tree,
`.env` files and model paths never leave the machine. `--preview` deploys a preview URL
instead. The one-time setup was `vercel link --yes --project muta-iq` from the repository
root, which created `.vercel/project.json` (gitignored). `vercel.json` also carries the same
build command and `outputDirectory: site`, so if the repository is ever connected to Vercel's
Git integration the project builds the same way there (the build image has `python3`).

Deploys are manual by design: the report changes when evidence is re-analysed, not on every
commit, and the Vercel account (`iitimii`) is not the GitHub repository owner, so Git
integration would need the owner to install Vercel's GitHub app on `nelsonifechukwu/Muta`.

## GitHub Pages (project page)

GitHub serves a project page at `https://<owner>.github.io/<repo>/`, so for
`nelsonifechukwu/Muta` the URL is **`https://nelsonifechukwu.github.io/Muta/`**. The report is
the site's `index.html`; nothing else in the repository is published.

**How.** `.github/workflows/pages.yml` runs `muta-iq/dashboard/build_static.py` and deploys the
resulting `site/` directory with `actions/deploy-pages` (Pages source = "GitHub Actions"; no
`gh-pages` branch). It triggers on pushes to `main` that touch `muta-iq/dashboard/**`,
`muta-iq/metadata.json`, `bench/measurements/**`, or the workflow itself, and on manual
`workflow_dispatch`. `make pages` renders the same site locally into `site/` (gitignored).

## The published-snapshot mode

The report normally polls `app.py` for `/api/state` — the evidence JSON summaries under
`bench/measurements/` plus the stored profiler runs in `profiler.db`. Static hosting has no
server, and the page also used an absolute `/api/...` path, which under a `/Muta/` prefix would
have resolved to `nelsonifechukwu.github.io/api/state` and 404'd forever ("Loading profiler…").

`build_static.py` therefore:

1. pre-renders `state_payload()` into `api/state.json`, adding `runs_by_model` (every finished
   run, newest first, with its raw profiler report embedded) so **History** and **Raw report**
   keep working with no server;
2. stamps `<html lang="en" data-snapshot="api/state.json">`. `script.js` reads that attribute
   (`SNAPSHOT_URL` / `STATIC`), fetches the file **once over a relative URL** (works from any
   prefix), never polls, shows a "Published snapshot" status pill and an explanatory note in the
   profiler appendix, hides the quick-run toggle, and disables **Start profile**, **Set as
   submission**, and **Delete record** (a click guard also refuses those actions outright);
3. fails the build if any evidence lane (`campaign`, `campaign_parity`, `campaign_alternative`,
   `campaign_avx2_score`, `overnight`, `model_extension`) is missing — a page of "unavailable"
   placeholders must never be published silently;
4. redacts every `email` field inside the embedded profiler reports (the submitter's address is
   in each `submission.json`-shaped report) because the output is meant to be public;
5. only ever clears an output directory carrying its own `.muta-iq-site` marker, so
   `--out` cannot wipe a directory it did not create.

The `model/` directory is not needed: the snapshot is built without it, so `script.js` in static
mode reports "N artifacts with stored run records" instead of "artifact removed", which is what
the live page says when a GGUF is absent from disk.

Without the attribute the page behaves exactly as before (`./dashboard/start.sh`, LAN mode,
live profiling), so the same three files serve both roles. Safeguards live in
`muta-iq/dashboard/test_build_static.py`; the workflow runs the whole dashboard test directory
and `node --check` before building.

## Enabling Pages, and the private-repository caveat

- The workflow calls `actions/configure-pages` with `enablement: true`, which asks GitHub to
  create the Pages site with source "GitHub Actions" on the first run. If that step is refused,
  enable it once by hand: **Settings → Pages → Build and deployment → Source: GitHub Actions**,
  then re-run the workflow. Enabling Pages needs repository admin rights.
- **This repository is private.** GitHub Pages on a private repository is only available on paid
  plans (Pro / Team / Enterprise); on a free plan the deploy step fails until the repository is
  made public. The alternative that keeps the code private is to push the built `site/`
  directory to a separate *public* repository (or to a public `<name>.github.io` repository),
  which the self-contained output makes trivial.
- The name `muta.github.io` would be a *user/organisation site*, which requires owning a GitHub
  account named `muta` — that login already belongs to an unrelated user — so the project page
  under the repository owner is the reachable form.

## Previewing locally under the project-page prefix

```bash
make pages
mkdir -p /tmp/pages && ln -sfn "$PWD/site" /tmp/pages/Muta
python3 -m http.server 8790 --directory /tmp/pages --bind 127.0.0.1
# open http://127.0.0.1:8790/Muta/
```

The `/Muta/` prefix is the part a plain `python3 -m http.server site` would not exercise.
