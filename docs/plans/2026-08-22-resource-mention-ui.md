# Resource mention presentation

## Problem

Selecting a learner PDF currently exposes the transport token (`@{full document name}`) in the
textarea while also drawing a second chip above it. The same transport syntax is stored as the
user message and therefore appears as ordinary text in chat history. Long bibliographic filenames
make both states especially noisy.

## Desired interaction

1. Typing `@` still opens the keyboard-accessible ready-resource picker.
2. Choosing a resource removes the typed query from the visible textarea and leaves one compact
   document chip in the composer. An invisible, single-character placement marker remains at the
   selected `@` position, and the resource remains selected by its server-owned ID.
3. At send time, Muta replaces that placement marker with the canonical mention token in place.
   This keeps current retrieval and durable history compatible without showing implementation
   syntax while the student writes or moving the document reference to the end of the sentence.
4. User bubbles parse canonical tokens into an inline PDF reference that continues the sentence:
   a small PDF badge followed by a naturally wrapping filename, without a chip border, card
   background, or separate attachment row. The complete name remains exposed to assistive
   technology. A live turn links only an unambiguous server-owned ID; historical name-only
   mentions stay inert rather than guessing after a deletion or same-name re-upload.
5. Old conversations containing raw mention tokens immediately receive the same presentation.
6. Removing a composer chip removes the selected resource; typed legacy tokens remain supported.

## Safety and compatibility

- Build mention DOM with `textContent`; resource names never become HTML.
- Normalize brace delimiters and bidi controls at upload and again in the browser; even a name
  that normalizes to nothing receives the stable visible fallback `resource.pdf`.
- Only the exact canonical `@{...}` form becomes a mention. Ordinary `@` text and email addresses
  remain text.
- The request still sends `resource_ids`; the canonical token is added once and never duplicated.
- Placement markers are chosen from a fixed allow-list, persisted with queued/draft resource
  records, and removed with their composer chip. Deleting a marker directly also deselects the
  corresponding resource.
- Queueing, draft restoration, history rendering, attachments, and RAG preflight share the same
  message/resource state.
- Composer chips wrap as a collection, keep each label on one line, and retain a non-shrinking
  remove target. Sent mentions are prose-level inline references and wrap with the surrounding
  sentence instead of truncating the document name.

## Verification

- Parser tests for mixed prose, several mentions, ordinary `@`, and malformed tokens.
- Static UI tests for raw-token removal from selection, canonical request composition, safe DOM
  construction, live/history parity, SVG icons, truncation, and touch/focus targets.
- Visual checks at wide desktop, laptop, and phone widths.
- Independent adversarial review before commit, push, and GCP sync.
