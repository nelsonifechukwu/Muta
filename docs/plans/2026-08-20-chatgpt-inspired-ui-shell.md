# ChatGPT-inspired UI shell and live-asset coherence

## Outcome

Give Muta the familiar interaction structure of ChatGPT without copying its branding or
assets: model selection lives in a compact chat-header button with a contextual menu, while
Settings remains a compact sidebar row. Deploy the authored UI as one coherent revision so a
browser cannot combine new HTML with stale JavaScript or CSS.

## Constraints and invariants

- The browser remains a client of the existing `/v1` contract; model availability,
  recommendation, selection permission, and switching state continue to come from `/v1/models`.
- A model switch is unavailable while any text generation is active and keeps the existing
  operator-only and unavailable-model protections.
- The selector is keyboard accessible: button/menu semantics, focus movement, Escape/outside
  dismissal, disabled states, an active-model checkmark, and readable status text.
- The sidebar remains useful on narrow screens and the menu cannot widen or escape the viewport.
- Authored HTML, CSS, and JavaScript must not be retained between loads; the local bundle is
  small enough that cache coherence is more valuable than avoiding a conditional request.
- The portable `ui/dist` export must receive the exact reviewed source UI before the GCP process
  is restarted. Existing benchmark output on GCP is preserved.

## Implementation

1. Move the model control from the bottom of the sidebar into a small sticky chat header.
2. Replace the native `<select>` with a Muta-styled trigger and popover list. Show model name,
   description, evidence metrics, recommendation, availability reason, and active checkmark.
3. Harden the Settings icon with intrinsic dimensions as well as CSS and refine the sidebar row.
4. Add no-store headers and a revision query on entry-page assets so a
   stale cached stylesheet or app bundle cannot produce the giant-icon/unauthenticated-client
   failure seen on GCP.
5. Add static UI and HTTP regressions for structure, model switching states, accessibility,
   responsive containment, and cache policy.
6. Run focused Python, JavaScript syntax, lint, and diff checks; then exercise desktop and mobile
   interactions in a real browser.
7. Ask a fresh adversarial reviewer to try to break model switching, accessibility, and live
   asset coherence. Apply any release-blocking findings.
8. Commit and push this cohesive UI change, sync the identical commit and authored UI export to
   GCP, restart the live service safely, and verify the served revision and untouched benchmark
   directories.
