# Muta brand-system production rollout

## Objective

Apply the approved `branding/` identity consistently to the shipped Muta desktop product and its
authored companion surfaces, then produce fresh Apple Silicon and Intel macOS offline packages for
review. The brand kit is the visual source of truth; production must use its supplied artwork rather
than approximating the wordmark with live text.

## Invariants

- Preserve the open-book symbol, ivory/terracotta pages, forest field, and speaking square-dot.
- Use the supplied outlined logo SVGs so the wordmark geometry and under-`u` placement cannot drift.
- Use the dedicated optical favicon at small sizes and the opaque app master with a macOS mask.
- Bundle Libre Baskerville and Instrument Sans locally; no network font dependency.
- Keep status, danger, syntax, and accessibility colors distinct where the six-color brand palette
  alone is not sufficient. Maintain readable contrast and visible keyboard focus in both themes.
- Add only the small runtime subset of the brand kit to product bundles, not source boards, social
  collateral, references, or generators.
- Do not rebuild Linux or Windows and do not replace GitHub, Drive, or GCP release artifacts.

## Implementation

1. Create a minimal checked-in runtime brand subset for the chat application, landing page, legacy
   fallback splash, and Muta IQ static report.
2. Replace authored text approximations of the Muta wordmark with the approved light/dark SVG pair;
   use the stacked lockup for the generous startup state.
3. Map product theme tokens and typography to the brand guide, including the forest dark theme and
   correct theme-color metadata.
4. Replace the browser favicon and native application icon from the brand masters; regenerate all
   Tauri platform icon derivatives.
5. Update brand, offline-build, and static-report checks so stale or partial branding cannot pass.
6. Render and inspect representative light/dark UI and small/native icons, run targeted and full
   regressions, commit and push the exact source, then build both macOS targets from that immutable
   commit.
7. Verify package signatures, architecture, source identity, UI/brand byte parity, model-pack
   integrity, and checksums. Keep only the newest macOS test-package directory.

## Pre-package acceptance

- The brand manifest verifies 70 artwork exports, 105 local links, and 84 inventoried source files.
- Runtime surfaces carry only ten shared assets (three fonts, two licences, four logo variants, and
  one optical favicon), adding about 1.3 MiB across all four independently deployable surfaces.
- Desktop and 390 × 844 mobile renders were inspected in the real application shell in dark mode.
- The complete Python suite passed with 1,934 selected tests; all 148 Node UI tests and all 10 Rust
  shell tests passed. Focused brand, startup, landing, visualization, and static-report tests were
  rerun after the final typography adjustment.
