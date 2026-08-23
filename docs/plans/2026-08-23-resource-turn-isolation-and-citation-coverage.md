# Resource-turn isolation and citation coverage

## Observed failures

- A turn selecting a newly uploaded document still replays earlier conversation exchanges to the
  model, so answers can name or quote a previously selected book.
- The model sometimes writes `(R5)` or bare `R3` instead of the required `[R5]`. Those forms leak
  implementation syntax because the browser promotes only canonical square-bracket references.
- The server returns every retrieval hit in the Sources rail even when the generated answer never
  cites it. The visible source list and inline markers therefore disagree.

## Invariants

- A learner-resource turn receives the selected document evidence, the current question, and the
  stable tutor instructions—never older user/assistant turns from another resource.
- Only server-owned resource records can become links. Known model reference variants are
  canonicalized and renumbered; unknown references never create a destination.
- Every source displayed beside an answer has at least one inline marker in that answer. Retrieval
  candidates the model did not use are not presented as cited evidence.
- The generated answer never exposes model meta-commentary such as a citation self-check.
- Streaming, non-streaming, refresh/history replay, persistence, and exact PDF-page links agree.

## Implementation

1. Add an explicit history-isolation option to `ChatEngine`; resource routes use it for both new
   turns and regeneration while ordinary chat memory stays unchanged.
2. Strengthen the resource prompt: exact `[R#]` syntax, use every relevant evidence block, no raw
   reference codes, and no printed self-check.
3. Finalize resource replies server-side: remove meta self-checks, canonicalize `[R#]`, `(R#)`, and
   bare `R#`, keep only referenced source records, renumber them by first appearance, and persist
   the same finalized reply/sources returned to clients.
4. Add a streaming replacement event so the browser replaces any raw streamed notation with the
   canonical final reply before mounting inline markers. Apply the same finalizer to legacy history
   in the browser so already-stored `(R#)` replies render cleanly.
5. Add adversarial tests for cross-document history, sparse/out-of-range references, repeated
   references, self-check removal, exact source-row ownership, history, and UI rendering.

## Verification

- Focused runtime, gateway resource, UI citation, and contract tests.
- Full UI/backend regression, JavaScript syntax, Ruff, native export parity, and diff checks.
- Render a resource reply containing sparse legacy citation forms and verify that no raw `R#`
  remains, every displayed source has a matching inline marker, and every link opens its exact page.
