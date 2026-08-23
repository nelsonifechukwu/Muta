# Conversation-list resource titles

## Problem

The conversation list renders its title as one raw text node. Resource-backed opening turns are
stored with the canonical `@{document name}` transport syntax, so the sidebar exposes that syntax
instead of the inline PDF reference used by the composer and sent message bubble. The gateway also
cuts first-turn titles at 80 characters without respecting mention boundaries; a long filename can
therefore lose its closing brace before the browser sees it.

## Change

1. Build first-turn titles with a bounded helper that never cuts through a complete resource
   mention. Long document names receive a compact, still-complete mention token.
2. Render conversation titles from the canonical resource-mention parser, using the same PDF icon,
   accent, and safe text-only DOM construction as other resource references.
3. When listing a historical title with an unmatched trailing mention at the old 80-code-point
   boundary, rebuild it from a one-row query for that conversation's first user message. The
   browser keeps its strict parser, so malformed ordinary text remains ordinary and sidebar refresh
   never materializes full transcripts.
4. Keep the row a single ellipsized line, expose the complete cleaned title to pointer and assistive
   technology, and keep the PDF icon decorative.

## Safety and compatibility

- Conversation-list document references are presentation only; they never become resource links or
  retrieval authority.
- Filenames enter the DOM only through `textContent`.
- Existing ordinary, malformed, email-like, RTL, and untitled conversation titles retain their
  current behavior.
- The active/generating/delete controls and narrow mobile drawer keep their existing layout and
  keyboard semantics.

## Verification

- Parser tests cover complete, malformed, long, and historical truncated titles.
- Gateway tests prove the 80-character title limit never splits a generated mention.
- Static and browser checks cover DOM safety, accessible names, ellipsis, narrow sidebars, and
  absence of visible `@{...}` syntax.
- Independent adversarial review runs before commit, push, and GCP sync.
