# Resource citation interface refinement

## Observed problem

Resource citations currently render as a stack of full-width bordered cards below every
grounded answer. A long document title is repeated in each card, excerpts are forced onto one
line, and the visual weight competes with the answer rather than supporting it. The source
number also reads as an internal retrieval identifier (`R1`) instead of a quiet citation.

## Reference pattern

ChatGPT's documented search interface uses inline citations that preview on hover and open the
source on click, plus a compact Sources control that reveals the complete source list. The user
also supplied book and article examples where numbered references sit beside the supported text
and explanatory notes occupy the right margin.

Muta should combine those patterns without copying ChatGPT's branding:

- turn model-authored `[R1]`, `[R2]`, and similar references into numbered inline source links;
- show a compact, readable source rail in the right margin when the viewport has room;
- collapse the same source list behind a Sources control at narrower widths;
- keep exact PDF-page links, excerpts, and durable history behavior unchanged.

## Interaction and accessibility invariants

1. An inline citation is a real link to the authenticated PDF page, not a scripted imitation.
   It has a descriptive accessible name and visible keyboard focus.
2. Hovering or focusing an inline citation previews the title, physical page, and excerpt, and
   highlights the matching margin source. The source remains available without hover through
   the full source list.
3. The Sources control exposes `aria-expanded`, has a minimum 44-pixel target, and never traps
   focus. On wide screens the rail starts expanded; on smaller screens it starts collapsed.
4. Document titles clamp rather than overflow. Excerpts wrap to a small bounded preview instead
   of becoming a dense underlined line.
5. Content remains usable at phone width, high zoom, right-to-left document titles, and with
   reduced motion enabled. No horizontal page scrolling is introduced.
6. Only `[R<number>]` references in rendered prose are linked. Code, existing links, buttons,
   form controls, and source UI are never rewritten.
7. Server-owned citation records remain the authority. A model cannot create a clickable source
   merely by emitting an unknown reference number.

## Implementation

1. Refactor `renderResourceSources()` into a source component with a compact header/trigger and
   a semantic list of exact-page links.
2. Post-process the answer prose after safe Markdown rendering, replacing only references that
   map to server-provided resource citations. Add a small hover/focus preview and reciprocal
   highlighting between inline markers and full source rows.
3. Add responsive CSS: a quiet book-note rail beyond the answer measure on sufficiently wide
   screens, a collapsed in-flow list on desktop/tablet, and a phone-safe full-width disclosure.
4. Add feature-local copy for Sources, citation counts, page metadata, and accessible labels.
5. Add regressions for safe reference matching, semantic markup, keyboard state, responsive
   containment, and the direct PDF-page destination.

## Verification

- Run focused UI Node/Python tests, JavaScript syntax, and `git diff --check`.
- Exercise history and live-completion rendering with one, several, missing, and repeated inline
  references.
- Inspect at wide desktop, ordinary laptop, and 375-pixel phone widths; check keyboard focus and
  reduced-motion behavior.
- Have an independent adversarial reviewer attempt to break citation authority, safe Markdown,
  responsiveness, and keyboard interaction before integration.
