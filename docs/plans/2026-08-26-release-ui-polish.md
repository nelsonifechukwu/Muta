# Release UI polish implementation plan

**Branch:** `codex/release-ui-polish`
**Base:** current `origin/main` (`ff0207aa3aa6ee40e5b56b0bceaba3802548d913`)
**Scope boundary:** UI, additive conversation metadata/API, and desktop startup presentation only.
Host/power copy and Host-mode scrolling are owned elsewhere and will not be changed. No package
build, publication, or merge to `main` belongs to this workstream.

## Product invariants

1. **The shell is useful before inference is ready.** Tauri loads the checked-in browser UI as
   its bundled frontend immediately. Model-pack verification, gateway launch, database probe,
   llama-server warm-up, and model load remain on a background thread. The composer stays
   unavailable until the existing authoritative readiness checks pass.
2. **Progress reports milestones, not elapsed-time guesses.** Percentages advance only when a
   real milestone is observed: UI painted, pack verification started/completed, gateway spawned,
   database reachable, inference reachable, and `/v1/ready` true. A retry never pretends the
   tutor is ready, and a failure exposes a retry action while retaining the last truthful value.
3. **Browser and desktop share one readiness component.** Browser exports derive the same
   milestone state from `/v1/ready`; the desktop bundle reads the Tauri launcher snapshot. The
   component is a labelled progressbar with `aria-live`, `aria-busy`, a reduced-motion path, and
   a compact header form after the initial welcome state.
4. **Conversation actions are owner-scoped and deliberate.** Pin state is stored beside the
   conversation in SQLite/Postgres and updated only through an authenticated owner-scoped API.
   Delete performs no stop, queue discard, navigation, or HTTP deletion until the student
   confirms in the modal.
5. **Dialogs do not strand focus.** Delete opens on the safe Cancel action, traps Tab in the
   dialog, closes on Escape/Cancel, restores focus to the invoking control when possible, and
   gives the destructive action an explicit accessible name. Touch targets are at least 44 px.
6. **Code rendering remains inert.** Highlighting runs only after Marked and DOMPurify, creates
   spans with `textContent`, never evaluates code, never loads a CDN, and falls back to literal
   code for an absent/unknown language. Copy uses the original literal text.
7. **Branding is text-first.** The Muta wordmark remains selectable, crisp HTML/CSS; a small
   square under the “u” supplies the mụ/learn mark. Visible variants have an explicit “Muta”
   accessible label, while decorative letter shapes are hidden from assistive technology.
8. **Existing transcript behavior is preserved.** No code in the near-bottom auto-follow state
   machine or Host-mode scrolling changes. Layout additions must remain bounded at 375 px,
   large mobile, landscape, and desktop widths.

## Implementation

### 1. Immediate desktop UI and readiness

- Point Tauri `frontendDist` at the verified, self-contained `ui/dist` export instead of the
  standalone splash directory; the normal desktop staging pipeline creates that export before
  compilation, including every pinned offline vendor asset.
- Add a serializable launcher snapshot and commands to read/retry it. Update it at verified
  startup milestones and keep progress monotonic through automatic retries.
- Keep the existing background process supervision and navigate the already-visible shell to
  the loopback `/chat/` origin only after readiness is true, restoring normal same-origin API,
  EventSource, attachment, and resource URLs.
- Add `ui/startup.js` plus welcome/header markup and styles. HTTP builds poll `/v1/ready`;
  desktop builds poll the launcher snapshot. Three consecutive transport failures become a
  retryable failure; dependency-not-ready remains an honest loading state.
- Replace the fallback splash copy with the Muta wordmark and exactly: “the personal education
  companion for every student at every level. powered by AI.”

### 2. Terse English copy

- Change the English composer placeholder to “Ask anything”.
- Change the disclaimer exactly to “Muta can make mistakes. Check important info.”
- Replace model-registry prose in option rows with short localized capability labels; keep
  dynamic model names and availability reasons.
- Shorten the English empty-state/model/settings helpers without changing Host/power strings.
- Add every new visible/action string to the i18n source catalog and use `data-i18n` or `t()` at
  each call site. Existing translated packs continue to fall back through the catalog contract.

### 3. Confirmed deletion

- Add a top-level delete dialog with the exact title “Delete chat?” and body “This will delete
  <chat name>.”, populated with `textContent`.
- Replace the sidebar’s direct deletion handler with a request step. Only the modal Delete path
  may stop a generation, discard its queue, call DELETE, or navigate away.
- Add modal focus/Escape/backdrop behavior and automated controller/integration assertions.

### 4. Pinned chats

- Add append-only migration 4 (`pinned`, false by default) to both stores.
- Add `pinned` to conversation output and an authenticated `PUT /conversations/{id}/pin` request.
- Order storage results by pinned then recent, and render a “Pinned” group first only when it has
  members. Keep ordinary chats in a “Chats” group when the pinned group exists.
- Add accessible Pin/Unpin controls, visible focus, coarse-pointer/mobile affordances, reload and
  owner-isolation tests.

### 5. Offline fenced-code highlighting

- Add a small, local `ui/syntax.js` highlighter for common declared languages and aliases
  (JavaScript/TypeScript, Python, shell, JSON, HTML/XML, CSS, SQL, C/C++, Java, Rust, YAML).
- Token output uses DOM text nodes/spans only. Unknown or missing languages remain plain.
- Decorate sanitized fenced blocks with a language label and localized Copy button; copy the
  original code, preserve dark/light token contrast, and prevent toolbar copy contamination.
- Include authored/dist/native-export parity and common/unknown/malicious-code tests.

### 6. Wordmark and responsive polish

- Use one semantic HTML wordmark structure on desktop startup and chat surfaces, with a CSS
  square positioned beneath the “u”. Avoid images/canvas and preserve labels at mobile sizes.
- Validate the readiness indicator, sidebar actions, modal, and code toolbar at 375 px, large
  mobile, landscape, and desktop in both themes and with reduced motion.

## Verification and review

- Regenerate the OpenAPI contract and verify browser/native UI export discovery; do not build
  packages.
- Run focused store/route/contract/UI/desktop tests, Node behavior tests, JS syntax, Ruff, Rust
  unit tests when the cached toolchain permits, and `git diff --check`.
- Exercise cold, warm, transport-failure/retry startup; pin/reload; delete keyboard/touch; code
  copy/highlighting; light/dark; reduced motion; 375 px, large mobile, landscape, and desktop.
- Give the completed diff to a fresh adversarial reviewer. Resolve every release blocker before
  committing and pushing only `codex/release-ui-polish`.
