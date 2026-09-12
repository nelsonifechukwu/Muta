# Foothold production rollout — 2026-09-12

## Goal

Promote the reviewed Foothold identity into Muta's production application icon and browser
favicon, then replace only the two macOS test packages for user review.

## Decision

- Use the asymmetric open `u` and terracotta foothold selected in the Muta logo review.
- Keep the full-bleed 512-unit vector as the canonical icon artwork.
- Use a rounded platform presentation for the Tauri desktop icon so the macOS bundle receives
  appropriate transparent corners.
- Use the separately drawn 32-unit optical master for browser and small-size contexts instead of
  mechanically shrinking the desktop artwork.
- Preserve the existing `Muta.` wordmark treatment; this pass changes the standalone icon only.
- The owner explicitly authorised production implementation after reviewing the documented name
  and device-mark clearance warning. That warning remains in the design review record.

## Verification

1. Parse the production SVGs and compare their geometry and palette with the reviewed masters.
2. Regenerate every Tauri icon derivative and inspect both 512 px and 32 px output.
3. Include SVG assets in the content-addressed UI cache so a changed favicon can never reuse stale
   packaged UI output.
4. Run brand, UI-build, browser, Python, and packaging regression tests.
5. Commit and push the exact source revision used for packaging.
6. Build only macOS arm64 and x86-64 offline archives; verify signatures, architectures, embedded
   source identity, icon parity, model manifests, and checksums.
7. After both new archives pass, move the superseded Mac test-build directory to Trash. Do not
   rebuild Linux/Windows or modify GitHub releases, Google Drive, or GCP.
