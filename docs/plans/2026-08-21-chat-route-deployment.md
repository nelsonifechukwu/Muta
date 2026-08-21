# Landing → chat route migration

Date: 2026-08-21

## Outcome

The public entry point is the Muta landing page at `/`. Every “Open Muta” action opens the
working tutor at `/chat/`. Existing `/ui` links remain valid through permanent redirects to
the equivalent `/chat/` path.

## Changes

1. Canonicalize `/chat` to `/chat/`, then mount the checked-in tutor bundle there in the
   assembled FastAPI app.
2. Redirect `/ui`, `/ui/`, and `/ui/<asset>` to their `/chat` equivalents while preserving
   conversation and asset-version query strings.
3. Copy the tutor bundle to `/chat/` in the nginx frontend image and mirror the legacy
   redirects there.
4. Update the native exporter to extract the tutor bundle from the new image path.
5. Point every landing-page CTA and demo action at `/chat/`.
6. Update run output and operator documentation so the two public URLs are explicit.

## Verification

- FastAPI HTTP smoke: `/` is landing HTML, `/chat` redirects to `/chat/`, `/chat/` is tutor HTML, `/ui/` redirects to
  `/chat/`, and `/ui/app.js` redirects to `/chat/app.js`.
- Static/export regression tests cover nginx copy paths and the native exporter source.
- Browser flow: load `/`, activate “Open Muta”, arrive at `/chat/`, and see the tutor.
- JavaScript and shell syntax checks remain clean.
- GCP deploy uses `git pull --ff-only origin main`; no reset or cleanup is allowed because
  the VM owns untracked benchmark artifacts.
