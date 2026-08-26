# Host-mode and mobile release hardening

Date: 2026-08-26
Branch: `codex/release-host-mode-fixes`

## Evidence

- The Host-mode control is a native checkbox with `role="switch"`, but its dedicated
  `.host-switch` treatment collapses the visible affordance to a checkbox-like mark instead of
  using the same track/knob language as the other application switches.
- The sidebar presents the operator identity and runtime as separate, partly hard-coded labels.
  Settings also retains the obsolete fixed-slot/memory footnote.
- The server already exposes the canonical id-addressed deletion endpoint and a revoke-first,
  resumable erase saga. The client waits for a later roster refetch, has no row-local failure
  state, and the assembled security suite does not prove that a removed browser is rejected,
  that data stays gone after restart, or that the same name must re-enter approval.
- The durable generation registry correctly owns work across subscriber disconnects. A browser
  relay interruption should therefore reconnect from its SSE frame cursor; only an explicit
  job error/terminal failure is evidence that the tutor itself stopped. Today all error frames
  collapse to the same terminal copy and a partial answer offers no recovery action.
- `visualViewport` and bounded auto-follow already exist, but the viewport origin/height is not
  converted into bottom/safe-area composer clearance, sent turns can inherit a paused follow
  state, and Stop depends entirely on a later SSE terminal frame to unlock the composer.

## Invariants

1. Host administration remains loopback + host session + CSRF only. Learner removal addresses
   the stable server user id; display names never select authority or deletion targets.
2. Removal revokes all sessions before draining work and deleting owned state. A rejoin creates a
   new pending identity and cannot inherit the removed identity or its data.
3. Fixed model slots, RAM limits, per-student live limits, bounded FIFO ordering, and the
   operator/member route firewall remain authoritative.
4. Subscriber loss does not cancel a server job. Stop is the sole ordinary browser action that
   does cancel it, and a confirmed Stop settles the local view exactly once.
5. Valid streamed content is never discarded. A terminal incomplete reply is explicitly marked
   and offers a deterministic Continue action; an interrupted relay subscription only shows
   reconnecting feedback and resumes from the last processed frame.
6. Auto-follow is opt-in state: a sent turn follows only when the reader was already near the
   tail; manual upward motion pauses it; only deliberate return to the tail resumes it.
   Viewport/browser-chrome clamps do not count as user intent.
7. Fixed controls clear the visual viewport, software keyboard, and safe areas. All release
   actions remain keyboard operable, visibly focused, announced where needed, and at least
   44 × 44 CSS px.
8. All new visible copy and accessible names use i18n keys. Existing generated locale packs may
   fall back to the English catalog until their next intentional translation regeneration.

## Changes

1. Reuse the application switch styling for Host mode while retaining the native checkbox,
   `role="switch"`, checked state, Space activation, focus ring, and a 44 px hit area.
2. Render the host sidebar sentence exactly as “Muta Host: This device. Running locally.”; retain
   member identity/logout behavior; remove the obsolete settings footnote; key Host/People/error
   strings through the English catalog and fallback path.
3. Make roster mutations update from the mutation result immediately, keep periodic polling as
   reconciliation, and expose row-local pending/error state. Extend backend tests through the
   canonical DELETE route for CSRF, remote/member denial, session revocation, durable erasure,
   and fresh pending approval on rejoin.
4. Separate subscriber reconnect state from terminal generation failure. Keep partial content,
   annotate it as incomplete, and add a Continue button that creates a normal auditable learner
   turn. Ensure reattachment/history restoration keeps the same terminal treatment.
5. Make Stop idempotent in the client, confirm the DELETE request reached the owned server job,
   locally settle the bubble/composer once cancellation is accepted, and allow the replayed
   terminal frame to reconcile without duplicating UI. Preserve retry/error behavior when the
   cancellation request itself is not known to have arrived.
6. Compute visual-viewport bottom clearance and safe-area-aware shell/composer insets, restore
   near-tail follow for a sent turn, preserve pause on manual upward scroll, and keep
   the resume-at-tail path working through keyboard/browser-chrome resizing.

## Verification matrix

- Static/client tests: switch semantics/copy/i18n, viewport metrics, manual-scroll state,
  partial/reconnect/Continue behavior, Stop before first token/during stream/repeated Stop,
  navigation, and disconnect/reconnect.
- Gateway tests: direct subscriber disconnect survival, replay cursor continuity, terminal
  partial failure, queued/running cancellation, next turn after Stop, two learners over one/two
  slots, and removal while work is queued/running.
- Security lifecycle: loopback host DELETE with CSRF succeeds; missing/wrong CSRF, remote host
  token, member token, and anonymous callers fail; removed sessions fail immediately; restart
  keeps data absent; same username returns as pending and needs host approval.
- Browser: 375 px phone, 430 px large phone, and phone landscape; software-keyboard-sized visual
  viewport; touch and keyboard switch/Stop/Remove/Continue; safe-area and obscured-content checks;
  multi-client queue, removal, relay-like SSE interruption, cancellation, and recovery.
- Quality gates: focused Node/Python tests, `node --check`, ruff, full pytest, `git diff --check`,
  then a fresh adversarial review whose findings are fixed before commit and push.

## Delivery boundary

Commit only `codex/release-host-mode-fixes` for local integration handoff. Per the final handoff
instruction, do not push. Do not merge `main`, build release packages, publish, deploy, or
synchronize a runtime host.

## Verification result

- Focused lifecycle, gateway, removal, persistence, UI-asset, and contract tests passed.
- Full Python suite passed; the only diagnostic was the existing Starlette `httpx` deprecation
  warning.
- All 103 Node tests passed; `node --check`, changed-file ruff, and `git diff --check` passed.
- In-app browser checks passed at 375 × 812, 430 × 932, and 812 × 375. The composer cleared the
  visual viewport with zero chat overlap, primary controls measured at least 44 × 44 CSS px,
  the Host switch exposed switch semantics/state, and the settings panel remained in bounds.
- The first fresh-context adversarial pass found late-Stop persistence and multi-client deletion
  races. The job registry now owns terminal persistence and atomically arbitrates its final SSE
  frame; conversation deletion now installs a server-side stop/drain/admission barrier. Focused
  tests force both former race windows.
- The second pass found that legacy tutor SSE and voice streams also needed the new durable
  terminal callback. Primary chat, strict/legacy tutor SSE, and voice now share the same mapping;
  route/WebSocket tests cover complete, failed, stopped, and barge-stop outcomes. The final
  fresh-context verdict reported no blocking findings.
