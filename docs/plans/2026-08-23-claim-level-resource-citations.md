# Claim-level resource citations

## Observed problem

The citation renderer only promotes literal model output such as `[R1]`. The local tutor can
return a grounded answer and structured server-owned source records while omitting those tokens.
The Sources rail then appears, but the answer contains no numbered markers beside the claims it
supports.

## Intended behavior

- Every grounded answer shows compact numbered links beside the sentence or bullet they support.
- Explicit model references remain authoritative when present.
- If the model omits a reference, the browser anchors the corresponding server-owned citation to
  every matching rendered claim only when a source sentence has the same case-sensitive normalized text, including
  grouping, semantic punctuation, scientific units, signs, polarity, quantifiers, and numbers. One
  generic word or an ambiguous paraphrase is never enough to present a retrieval hit as evidence.
  Whitespace left beside a removed explicit marker is normalized only around closing punctuation;
  the punctuation itself remains part of the exact comparison.
- Retrieved hits that cannot be tied to an answer claim remain in the Sources panel instead of
  being presented as proof for unrelated text.
- Unknown model reference numbers remain inert text. Code, equations, existing links, controls,
  and sanitized Markdown are never rewritten.
- Live completion and restored history use the same renderer and exact PDF-page destination.

## Implementation

1. Strengthen the learner-resource prompt: every grounded factual sentence or bullet must place
   its `[R#]` marker immediately after the supported claim, never in a detached bibliography.
2. Extend the post-sanitize citation decorator to collect rendered sentence/bullet anchors and
   match any missing structured citations using meaningful lexical overlap with source excerpts.
   The same source may support multiple claims; explicit authority is tracked per claim and source.
   Leave unmatched server-owned records in the full source list rather than fabricating support.
3. Reuse the existing secure link/preview component for both explicit and fallback markers.
4. Add pure assignment regressions, DOM-safety assertions, prompt tests, a cache revision, and
   rendered desktop/mobile checks.

## Verification

- Node citation tests, focused UI/backend pytest, JavaScript syntax, Ruff, and diff checks.
- Render an answer with no `[R#]` text and five structured citations; verify numbered links appear
  beside claims, link to exact authenticated pages, and highlight the matching Sources rows.
- Verify explicit/repeated/unknown references, history replay, keyboard focus, narrow layout,
  math/code exclusions, and sanitization remain intact.
