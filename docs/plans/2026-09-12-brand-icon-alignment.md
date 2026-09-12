# Brand icon alignment — 2026-09-12

## Goal

Carry the revised Muta signature—a small terracotta square centred below the `u`—from the
in-app wordmark into the native application icon and every authored Muta brand surface, then
rebuild only the Apple Silicon and Intel macOS offline packages for review.

## Scope

- Keep `desktop/icon.svg` as the canonical native icon source.
- Replace the old lower-right circular dot with a smaller square centred below the monogram.
- Regenerate every Tauri icon derivative from that source so future Windows, Linux, Android,
  and iOS builds cannot retain the old mark.
- Align the public landing-page and Muta IQ wordmarks with the already-correct application and
  Fleet wordmarks.
- Give browser surfaces a matching SVG favicon without adding a runtime dependency.
- Update the landing-page social preview without changing its message or layout.
- Add static tests that fail if the icon reverts to a circle or a wordmark moves the mark away
  from the `u`.

## Verification

1. Inspect the canonical 512 px icon and the generated 32 px icon for legibility.
2. Run the icon/wordmark tests, the complete Python suite, all browser tests, and Rust checks.
3. Build macOS arm64 and x86-64 from one exact pushed source commit using the established manual
   packaging workflow.
4. Verify native architecture, code-signature integrity, UI/icon byte parity, model manifests,
   archive checksums, and a flat `desktop/build/final-packages` directory.

Existing Linux and Windows archives remain unchanged until the user requests those rebuilds.
