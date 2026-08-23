# Application dark mode — implementation plan (2026-08-23)

## Goal

Add a persistent `System` / `Light` / `Dark` appearance preference to the shipped Muta
experience. The selected preference must apply before first paint and cover the public landing
page, chat shell, settings and access dialogs, citation/source UI, forms, code and tables, and
sandboxed visualizations. This completes the roadmap's adaptive-UI theme control without adding
network or backend state to an offline-first preference.

## Invariants

1. `muta-theme` is the one browser preference key. Only `system`, `light`, and `dark` are valid;
   missing or malformed values resolve to `system`.
2. Both HTML entry points resolve the preference in the blocking head before their stylesheets,
   preventing a light first-frame flash on a dark installation.
3. `System` follows `prefers-color-scheme` changes live. Explicit light/dark choices do not.
   Storage changes from another tab update every open Muta surface.
4. The settings control remains a native labelled select with keyboard and screen-reader support.
   The public landing page also exposes a labelled 44-pixel light/dark toggle in its persistent
   header, so changing appearance never requires entering chat or authenticating. Theme changes
   do not require a page refresh.
5. Theme colors are semantic CSS tokens. Dark text/background pairs meet WCAG AA contrast;
   focus indicators remain at least 3:1 against their surrounding surface.
6. The warm paper-and-terracotta Muta identity is preserved in both themes. Dark mode uses warm
   charcoal surfaces rather than pure black or a new product palette.
7. Visualization iframes receive the resolved theme from their parent and redraw theme-dependent
   Canvas/WebGL colors when it changes. Model-authored visualization data remains declarative and
   unchanged.
8. Authored `ui/` assets and `ui/dist/` stay byte-identical for native/offline exports. Landing
   assets remain entirely local.

## Implementation

1. Add identical tiny pre-paint bootstraps to `landing/index.html` and `ui/index.html` and expose a
   theme-color meta element for runtime updates.
2. Add semantic light/dark token sets to the landing and chat stylesheets, replacing hard-coded
   light-only interaction, overlay, status, code, table, shadow, and form colors where required.
3. Add Appearance to the Interface settings section and implement theme preference, OS listener,
   storage synchronization, and `muta:themechange` notification in `ui/app.js`.
4. Make the shared landing theme bootstrap react to OS and cross-tab preference changes.
   Add a compact sun/moon action to the landing header that switches the resolved theme and saves
   the explicit light/dark preference through that same bootstrap.
5. Propagate theme changes to sandboxed visualization frames and make their palette explicitly
   selectable instead of depending only on the iframe's operating-system preference.
6. Add regression tests for pre-paint boot, persistence, invalid-value fallback, System behavior,
   cross-tab synchronization, iframe propagation, theme coverage, contrast, and offline asset
   parity. Exercise both themes at desktop and phone widths in a real browser.

## Release

Run focused Node/Python/browser tests, the complete UI and landing suites, native export checks,
JavaScript syntax checks, Ruff where applicable, and `git diff --check`. Refresh `ui/dist`, commit
the cohesive feature, push `main`, then fast-forward the GCP checkout, restart the gateway, and
verify `/v1/ready` reports `ready: true` at the deployed commit.
