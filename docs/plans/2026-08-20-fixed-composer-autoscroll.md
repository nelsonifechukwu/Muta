# Fixed composer and bounded autoscroll

## Failure

The app shell has a viewport height, but its nested flex column does not allow the chat pane to
shrink (`min-height: auto` remains in force). A long streaming response can therefore make the
whole document scroll instead of `#chat-scroll`. The sidebar and composer then move upward with
the document, leaving a large blank area below the composer even though token following still
updates the inner chat scroll position.

## Changes

1. Make the document itself non-scrollable and bound the app/main flex chain to the viewport.
2. Give `#chat-scroll` the only transcript scrolling responsibility with an explicit zero minimum
   height; keep the header and composer bounded siblings. Queue rows and attachment chips receive
   their own capped scroll regions so they cannot push the send controls outside the viewport.
3. Request content-viewport resizing from mobile Chrome and mirror `visualViewport.height` into
   the shell for Safari/iOS keyboard and browser-chrome changes. Anchor every fixed surface to
   the same visual-viewport top/height so navigation and overlays move with the composer.
4. Make any upward scroll pause following—even inside the former 96 px tolerance—and resume only
   after the reader returns to the tail. Track directional wheel/touch/drag intent so browser
   resize clamping cannot pause or resume following on the student's behalf.
5. Add stylesheet invariants and browser regression checks for a long conversation at desktop and
   phone/keyboard sizes.

## Verification

- Run focused UI tests, the math parser suite, JavaScript syntax checks, the full Python suite, and
  `git diff --check`.
- In a browser, prove that only `#chat-scroll` changes scroll position while the composer stays at
  the same viewport-bottom coordinate during appended reply content; also prove manual scroll-up
  pauses following.
- Obtain a fresh adversarial review, commit once, push GitHub, synchronize the identical commit to
  GCP, restart the persistent service, and repeat the live GCP browser check.
