# Gate 2 chapter navigation plan

## Goal

Introduce Gate 2 as a separate, chapter-based reading sequence inside the existing Muta IQ report. Preserve the approved Gate 1/Gate 2 table-of-contents hierarchy while giving every Gate 2 placeholder chapter matching previous/next controls in its header and footer.

## Interaction contract

- Keep both Gate groups collapsed on initial load and after refresh.
- Treat each Gate header as a shortcut to the first chapter in that Gate while retaining its expand/collapse control.
- Keep Gate 2 immediately below Gate 1 when Gate 1 is collapsed, and pinned above the current recommendation while Gate 1's children scroll when Gate 1 is expanded.
- Give each Gate 2 chapter a stable hash URL so browser back/forward navigation works normally.
- Show the active Gate 2 chapter in the table of contents when its group is opened.
- Provide a clear route back to the Gate 1 report and an accessible Gate 2 entry point at narrow widths where the table of contents is hidden.
- Use real links for navigation, visible focus states, descriptive labels, and no gesture-only interaction.

## Chapter scope

Create six chapters: model research, audit setup, experiments, validation, reviewer questions, and decision. The first chapter opens the Gate 2 investigation with the supplied compact-STEM model research, including its complete evidence qualifications, deployment caveats, evaluation protocol, and sources. The remaining chapters describe only the material they will eventually contain and explicitly state that Gate 2 measurements have not yet been added. No benchmark value, conclusion, or competition claim will be invented.

## Implementation

1. Add the six Gate 2 child links to the table of contents.
2. Add a sibling Gate 2 article with a chapter header, the complete compact-STEM research in chapter one, reserved-content panels for the remaining chapters, and paired header/footer navigation.
3. Route between Gate 1 and Gate 2 from the URL hash, preserving browser history and focusing the selected chapter heading after an in-page navigation.
4. Update responsive styles so the long-form layout remains readable at desktop and phone widths.
5. Extend static tests for chapter order, deep links, navigation landmarks, endpoint behavior, and placeholder evidence language.

## Verification

- Run the complete dashboard test suite and JavaScript syntax check.
- Inspect the diff for preserved profiler controls and unrelated artifacts.
- Render and exercise the report at desktop and phone widths, including keyboard focus, browser back/forward, first/last chapter controls, both Gate collapse states, and horizontal containment for every research table.
- Submit the result to the existing adversarial reviewer and resolve any functional, responsive, or accessibility findings.

The user explicitly excluded the `no-ai-slop` skill from this work, so it will not be used.
