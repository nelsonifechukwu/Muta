# Release localization completeness workstream

## Isolation and dependency gate

- Branch: `codex/release-i18n-completeness`
- Frozen integrated base: `b9909fe9d84ee3e3959e5ccd6580eb7604537da1`
- Worktree: isolated from the shared checkout; this branch does not modify `main`, packages, or
  releases.
- The dependency gate is satisfied by the integrated UI, Host-mode, and power SHAs recorded in
  `ui/i18n-release-gate.json`; the frozen base already contains them.

The foundation checkpoint contained only the source inventory, extraction rules, and automated
completeness tests. The final release pass below runs those gates against the integrated product.

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

After the three SHAs arrived:

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

## Release result

- The canonical runtime contains 366 keys and covers chat, startup, Host/mobile, power, resources,
  syntax, privacy/analytics, access, theme, and visualization copy.
- Twenty-seven interface locales are visible and pass exact key/placeholder parity, browser-residue,
  script, repetition, semantic-collapse, and reviewed-English-equivalence gates. The remaining 59
  registered locales stay in backend metadata but are hidden until a defensible complete catalog is
  available; Afar was removed from the visible selector because its integrated release delta was
  incomplete.
- Generated packs are recorded as machine-assisted and spot-reviewed, never native-reviewed. The
  validator strips and rejects browser UI contamination and the checked-in inventory rejects
  unlocalized visible literals.
- The authored shell and visualization frame both opt out of browser translation while retaining
  runtime `lang` and `dir` switching.

## Delivery boundary

Commit only this branch. Do not merge to `main`, create packages, publish releases, deploy, or push
over the network. Report the final local SHA and isolated worktree path for integration.
