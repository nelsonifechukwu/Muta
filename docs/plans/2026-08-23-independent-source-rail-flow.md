# Independent source-rail conversation flow

## Observed problem

On wide screens, the Sources disclosure is positioned as a right-margin rail. Expanding it also
sets the owning assistant turn's `min-height` to the rail height. That makes the next user turn
wait below the last source even though the source rail and conversation occupy separate columns.

## Intended behavior

- The main conversation remains normal document flow: the next turn starts after the answer.
- Source disclosures remain aligned in the right margin and never determine a chat turn's height.
- The source disclosure nearest the reading position owns the wide margin; focusing a citation
  makes its disclosure current.
- At narrower widths the disclosure remains in flow and collapsed by default.
- A rail re-layout follows the bottom only when auto-follow is already active.

## Implementation

1. Remove the assistant `min-height` reservation from source layout.
2. On the wide breakpoint, place one contextual panel with fixed viewport positioning beside its
   live citation anchor. Bound its height to the chat viewport and scroll the source list inside
   the panel, so it can never enlarge the transcript's scroll range.
3. Recompute the anchor from live rectangles during scroll and breakpoint changes. At narrower
   widths, keep every disclosure in flow with its existing accessible state.
4. Update the cache revision and native UI export, then add regressions that reject any future
   coupling between source height and central turn height.

## Verification

- Run focused UI Python/Node tests, JavaScript syntax, Ruff, and `git diff --check`.
- Inspect a wide conversation with an expanded five-source answer followed by another user turn;
  the user turn must begin immediately after the answer, not after source five.
- Load consecutive cited replies and confirm the contextual rail changes without adding blank
  transcript scroll space.
- Confirm laptop/mobile disclosure behavior and paused auto-follow remain unchanged.
- Have an independent adversarial reviewer try to break wide layout, responsive transitions, and
  auto-follow behavior before committing.
