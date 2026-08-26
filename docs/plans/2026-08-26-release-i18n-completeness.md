# Release localization completeness workstream

## Isolation and dependency gate

- Branch: `codex/release-i18n-completeness`
- Base: `origin/main` at `ff0207aa3aa6ee40e5b56b0bceaba3802548d913`
- Worktree: isolated from the shared checkout; this branch does not modify `main`, packages, or
  releases.
- Translation is deliberately gated on the committed UI, Host-mode, and power SHAs. Merge or
  cherry-pick those commits here before changing the canonical English catalog or any locale.

The first checkpoint contains only the source inventory, extraction rules, and automated
completeness tests. It must be safe to re-run after each dependency lands and must make newly
introduced untranslated UI copy visible as a test failure.

## Inventory boundary

Inventory the learner/operator-facing application surfaces under `ui/`:

- authored HTML text and accessible attributes in the chat shell and visualization frame;
- static translation keys referenced by HTML and JavaScript;
- literal JavaScript assigned to visible/accessibility sinks, including status, toast, error,
  title, label, placeholder, dialog, Host/mobile, power, analytics, and fleet-adjacent copy;
- the canonical English message catalog, every visible locale catalog, placeholders, and the
  interface-ready manifest.

Brand names, model/user content, server data, telemetry units, file names, protocol identifiers,
and purely developer-facing text may remain literal only through a checked-in exception with a
specific reason. Existing untranslated debt is inventoried explicitly during this foundation
phase; final localization removes every translatable exception or hides the affected locale.

## Automated contract

1. A deterministic extractor writes a checked-in JSON inventory containing source locations,
   referenced keys, literal UI strings, and their classification.
2. A test regenerates the inventory in memory and fails on drift. New literal UI copy therefore
   cannot enter through HTML or JavaScript without either an i18n key or an explicit reviewed
   inventory decision.
3. Tests require exact key parity for every visible locale, reject extra keys, and require exact
   placeholder parity with English.
4. Tests reject silent English fallback in visible non-English locales, with narrowly documented
   exceptions only for genuine shared spellings, proper nouns, and technical tokens.
5. Runtime tests cover saved-locale switching, LTR↔RTL direction, multibyte text, long labels,
   desktop/mobile DOM application, and representative accessible attributes.

## Dependency integration and final copy

After the three SHAs arrive:

1. Merge/cherry-pick them into this branch and regenerate the inventory.
2. Add keys for startup/progress, delete/pin, Host/mobile errors, model descriptions, disclaimer,
   settings, power, analytics, and fleet-adjacent app copy.
3. Apply the exact English copy changes:
   - `Muta can make mistakes. Check important info.`
   - `Auto mode detects your language and replies in it.`
   - `Help us improve Muta by sharing your analytics.`
4. Remove the Appearance helper and fixed inference-slot/memory-limit helper from markup and every
   locale catalog.
5. Translate every complete visible locale, preserving placeholders, markup, punctuation, locale
   names, and writing direction. Hide any pack that cannot pass structural validation and a
   reasonable spot review while retaining its backend registration.
6. Verify desktop/mobile runtime switching plus representative long, RTL, and multibyte locales.

## Delivery boundary

Commit and push only this branch. Do not merge to `main`, create packages, publish releases, or
deploy. Report the foundation SHA, then wait for the dependency SHAs.
