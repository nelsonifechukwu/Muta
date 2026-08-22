# Resource mention presentation

## Problem

Selecting a learner PDF currently exposes the transport token (`@{full document name}`) in the
textarea while also drawing a second chip above it. The same transport syntax is stored as the
user message and therefore appears as ordinary text in chat history. Long bibliographic filenames
make both states especially noisy.

## Desired interaction

1. Typing `@` still opens the keyboard-accessible ready-resource picker.
2. Choosing a resource removes the typed query from the visible textarea and leaves one compact
   document chip in the composer. The resource remains selected by its server-owned ID.
3. At send time, Muta appends its canonical mention token only to the backend message. This keeps
   current retrieval and durable history compatible without showing implementation syntax while
   the student writes.
4. User bubbles parse canonical tokens into inline document mentions with an SVG document icon,
   a bounded one-line name, and the complete name exposed to assistive technology. A live turn
   links only an unambiguous server-owned ID; historical name-only mentions stay inert rather
   than guessing after a deletion or same-name re-upload.
5. Old conversations containing raw mention tokens immediately receive the same presentation.
6. Removing a composer chip removes the selected resource; typed legacy tokens remain supported.

## Safety and compatibility

- Build mention DOM with `textContent`; resource names never become HTML.
- Normalize brace delimiters and bidi controls at upload and again in the browser; even a name
  that normalizes to nothing receives the stable visible fallback `resource.pdf`.
- Only the exact canonical `@{...}` form becomes a mention. Ordinary `@` text and email addresses
  remain text.
- The request still sends `resource_ids`; the canonical token is added once and never duplicated.
- Queueing, draft restoration, history rendering, attachments, and RAG preflight share the same
  message/resource state.
- Chips wrap as a collection, keep each label on one line, and retain a non-shrinking remove target.

## Verification

- Parser tests for mixed prose, several mentions, ordinary `@`, and malformed tokens.
- Static UI tests for raw-token removal from selection, canonical request composition, safe DOM
  construction, live/history parity, SVG icons, truncation, and touch/focus targets.
- Visual checks at wide desktop, laptop, and phone widths.
- Independent adversarial review before commit, push, and GCP sync.
