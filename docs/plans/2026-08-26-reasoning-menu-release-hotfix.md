# Reasoning menu v0.1.449 in-place release hotfix

## Scope

Repair the desktop reasoning-effort popup so Instant, Thinking, and Extended remain visible and
operable at both the ordinary and expanded composer heights. Rebuild the existing four offline
targets as version `0.1.449`, then replace the existing friendly-named assets in both GitHub
releases and the established Google Drive folder without creating a new release or duplicate.

## Confirmed cause

`#think-menu` is absolutely positioned inside `.think-select`, which is nested below both
`#composer` and `#composer-wrap`. Those containers deliberately use `overflow: hidden` to bound
large attachment, queue, and mobile-keyboard layouts. The popup opens upward outside the normal
composer rectangle and is therefore clipped by both ancestors.

## Implementation

1. Move the menu to the document overlay layer outside `#app`, while keeping the trigger in the
   composer and linking it with `aria-controls`/`aria-expanded`.
2. Position the menu against the current trigger rectangle with fixed viewport coordinates,
   prefer the space above, fall back below, and clamp it inside the visible viewport.
3. Reposition while open on window and visual-viewport movement. Preserve click-away, Escape,
   focus, menuitemradio selection, localization, and reduced-motion behaviour.
4. Add static and JavaScript regression coverage proving the menu is outside the clipping
   ancestors, uses the fixed overlay layer, positions against current geometry, and remains
   keyboard operable.

## Verification and release safety

- Run focused UI tests, the complete Python/Node UI suites, build `ui/dist`, and verify authored
  source and built output agree.
- Adversarially review the containment, keyboard, RTL/viewport, and hidden-state behaviour.
- Commit and push the source fix without staging unrelated workspace changes.
- Build all four targets through `make final-package ARGS="--version 0.1.449"`; reuse unchanged
  model, native, and frozen-gateway layers while rebuilding UI/Tauri/archive layers.
- Verify archive checksums, manifest commit identity, package inspectors, both Mac embedded UI
  styles/markup/scripts, architecture, and macOS signing.
- Resolve exact current remote asset IDs before replacement. Upload and read back the four
  friendly archives, their checksums, and `Muta-V3-Packages.json` on both existing GitHub
  releases. Keep the existing description and tag.
- Replace the same nine names in the supplied Drive folder, verify bytes/hashes, and leave exactly
  one current file per name.
