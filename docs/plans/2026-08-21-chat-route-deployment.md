# Landing → chat route migration

Date: 2026-08-21

## Outcome

The public entry point is the Muta landing page at `/`. Every “Open Muta” action opens the
working tutor at `/chat/`. No alternate tutor route is exposed.

## Changes

1. Canonicalize `/chat` to `/chat/`, then mount the checked-in tutor bundle there in the
   assembled FastAPI app.
2. Remove the previous tutor route entirely rather than exposing a compatibility alias.
3. Copy the tutor bundle to `/chat/` in the nginx frontend image and make unknown landing or
   chat paths return 404 instead of falling through to the wrong surface.
4. Update the native exporter to extract the tutor bundle from the new image path.
5. Point every landing-page CTA and demo action at `/chat/`.
6. Update run output and operator documentation so the two public URLs are explicit.

## Verification

- FastAPI HTTP smoke: `/` is landing HTML, `/chat` redirects to `/chat/`, `/chat/` is tutor
  HTML, and removed or unknown routes return 404.
- Static/export regression tests cover nginx copy paths and the native exporter source.
- Browser flow: load `/`, activate “Open Muta”, arrive at `/chat/`, and see the tutor.
- JavaScript and shell syntax checks remain clean.
- GCP deploy uses `git pull --ff-only origin main`; no reset or cleanup is allowed because
  the VM owns untracked benchmark artifacts.
