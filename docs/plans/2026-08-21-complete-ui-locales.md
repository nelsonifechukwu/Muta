# Complete visible UI language catalogs

## Outcome

Every language shown in Muta's Settings selector must have a complete interface catalog. The
Africa-54 registry remains the backend/source-of-truth inventory, but a language that cannot be
translated reliably enough for a complete catalog is not exposed as a learner-facing choice.
The selected language continues to control both the interface (when explicitly selected) and the
next response-language instruction without modifying persisted learner messages.

## Translation workflow

1. Extract the canonical English catalog and its placeholders from `ui/i18n.js`.
2. Retain the six existing complete packs as reviewed inputs rather than overwriting them.
3. Translate each remaining registry language with a source cascade:
   - use Google Translate where the requested language is supported;
   - use a local multilingual model for language/script variants Google does not support;
   - use a documented nearest written standard only when the selector label truthfully names that
     standard; never silently substitute an unrelated or merely neighbouring language.
4. Mask interpolation placeholders before translation and restore them exactly afterwards.
5. Publish generated output only when it passes every mechanical quality gate. Keep failed tags in
   the internal registry, record the reason, and omit them from the visible selector.

## Quality gates

- Exact key parity with English and exact placeholder parity per message.
- No leaked masking sentinels, missing values, decoder truncation, or excessive repetition.
- Valid BCP 47 tag and declared writing direction.
- No catalog that is byte-identical to another language unless the two selector entries explicitly
  share the same written standard.
- Script sanity checks for Arabic, Ethiopic, and Tifinagh targets.
- Browser smoke tests for persistence, refresh, dynamic text, selector visibility, and RTL.
- Translation provenance and readiness remain machine-readable in the generated manifest.

These gates establish technical completeness, not native-speaker certification. Community review
can improve a visible pack without changing the locale contract.

## Product changes

- Generate a static offline catalog asset and load it before application startup.
- Derive the pre-paint ready-locale manifest from the same accepted catalog inventory.
- Populate Settings from interface-ready languages only; keep unsupported registry entries
  available to the backend for later enablement.
- Update learner-facing copy so every visible explicit choice promises an interface translation.
- Add repeatable generation/validation tooling and regression tests.

## Delivery

Run the focused UI/export suites, the full relevant Python suite, and a live browser refresh check.
Have a fresh adversarial localization review probe language substitution, placeholder corruption,
truncation, visibility mismatches, startup flash, and RTL. Group the localization changes into one
functional commit, push it to GitHub, pull it on GCP, rebuild the native UI overlay, restart the
gateway, and verify readiness.
