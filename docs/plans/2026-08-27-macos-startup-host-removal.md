# macOS startup and Host removal corrective release

Date: 2026-08-27
Branch: `codex/macos-startup-host-remove`
Base: reviewed `origin/main` at `807072071596a7777ccf9f11fa7d9029d4f20b0f`

## Observed release evidence

The actual v0.1.449 Apple-silicon package started its frozen gateway and Qwen2.5 engine. The
backend log records llama-server becoming healthy at 03:52:57, and the package's loopback
`/v1/ready` returned a fully-ready response. The WebView nevertheless retained the 64% startup
surface and eventually announced `startup.failed`.

The packaged `ui/dist/startup.js` is byte-identical to the reviewed source. It captures
`globalThis.__TAURI__.core.invoke` at load time and treats that function as the sole readiness
transport. After Tauri navigates from its asset origin to the loopback `/chat/` origin, an
unavailable or rejected `startup_snapshot` command therefore prevents the healthy same-origin
readiness endpoint from being consulted. Three command failures are incorrectly presented as a
backend startup failure.

The Host roster's backend removal saga and DELETE/CSRF boundary are already correct. The release
UI still gates that mutation with `window.confirm`, an interaction that is neither reliably
rendered nor controllable in WKWebView. The existing in-app chat-deletion dialog provides the
right visual and accessibility precedent.

## Invariants

1. Tauri commands are an optional fast path. A missing or rejected command immediately falls
   back, in the same sample, to same-origin `GET /v1/ready`.
2. A successful Tauri terminal snapshot remains authoritative; only command transport failure
   triggers HTTP fallback. A healthy HTTP snapshot can never be converted into `startup.failed`.
3. Readiness states distinguish shell transport failure, gateway failure, database opening,
   model-pack verification failure, engine loading/failure, and an unexpected terminal failure.
4. The initial startup watcher has one live request/timer. Page teardown cancels both. Retry
   clears failure state and genuinely re-samples; when Tauri commands remain available it also
   requests a shell relaunch.
5. Once startup becomes ready, the overlay is hidden and the composer can become enabled through
   the ordinary identity/routing gates. A normal temporary engine/model switch does not reopen
   the initial-startup overlay.
6. Unexpected post-ready backend child exit is observed by the shell, the old process handle is
   cleared, and one new launch cycle is scheduled unless the application is shutting down.
   Closing the app never races an automatic relaunch.
7. Duplicate launch continues to focus the one existing window and never creates a second model
   tree. Port races and pre-ready child exits remain bounded by the existing five-attempt loop.
8. Host removal opens an in-app `role=dialog` surface. Cancel is focused first and is the safe
   default. Escape, backdrop activation, and Cancel close without mutation. Tab/Shift+Tab remain
   inside the dialog, and focus returns to the invoking Remove control when possible.
9. Confirm names the account and destructive scope, disables both actions while deleting, calls
   the canonical id-addressed DELETE with Host auth/CSRF, updates the roster immediately, and
   exposes a recoverable inline error on failure.
10. Account revocation, durable deletion, and re-registration-as-pending remain backend
    invariants. The modal never weakens authorization or performs deletion client-side.
11. Authored `ui/` entry assets and `ui/dist/` remain byte-identical.

## Implementation

### Startup transport and state

- Refactor `ui/startup.js` around a testable snapshot reader. Try `startup_snapshot` when it is
  available; on rejection mark that fast path unavailable for the current origin and fetch
  `/v1/ready` immediately.
- Add an abort-bounded same-origin readiness fetch, generation-token stale-result protection,
  teardown cleanup, truthful transport failure state, and retry behavior that works whether or
  not Tauri invocation survives the origin transition.
- Preserve the pure snapshot helpers so Node tests can execute the exact packaged-origin
  transition: `__TAURI__` exists, command rejects, HTTP readiness succeeds.
- Classify Rust launch failures from the stage at which they occur. Retain the detailed error in
  the shell event/log while showing a localized category in the startup surface.
- Add post-ready child monitoring with a shutdown guard and bounded automatic relaunch. Do not
  treat normal inference 503-to-200 warmup as failure.

### Host removal confirmation

- Add a Host removal modal beside the existing chat confirmation modal, reusing Muta's card,
  scrim, danger, focus, and 44px-control styling.
- Reuse existing localized Host removal/scope, Cancel, Delete, and error strings; no browser
  confirm remains.
- Keep Settings visible but inert behind the confirmation. Reconcile polling and locale changes
  without losing the pending account, error, or focus contract.
- Execute the existing `hostUserAction` only after explicit dialog confirmation. Keep optimistic
  deleting state, authoritative response handling, quiet persistence refetch, and row-level
  failure recovery.

## Verification

- Node: pure milestones, invoke rejection → healthy `/v1/ready`, slow 503/false → ready,
  transport failure → Retry → ready, stale request suppression, and cleanup.
- Rust: readiness parsing, stage-to-failure classification, shutdown/relaunch guard behavior,
  child/process lifecycle, model-pack and path tests, and duplicate-launch configuration.
- UI: no `window.confirm`, dialog semantics, account/scope copy, safe Cancel/backdrop/Escape,
  focus trap/restore, pending state, DELETE endpoint/auth headers, immediate roster update, and
  recoverable error state.
- Backend: Host-only/CSRF boundary, session revocation, durable erasure, and same-name rejoin
  returning to pending approval.
- Run the relevant Python, Node, and Rust suites, build the verified UI export, assert authored /
  dist parity, run lint/diff checks, and inspect the UI through the in-app Browser.
- If source-level and browser gates are insufficient, assemble only a disposable arm64 `.app`
  with isolated data/cache/model roots for cold/warm startup and Host-modal QA. Do not make a
  release archive or touch any published artifact.
- Finish with a fresh adversarial review, fix blockers, commit locally, and report the immutable
  reviewed SHA without pushing.

## Verification result

- 132 Node tests passed, including the retained-Tauri-command rejection, failure/Retry recovery,
  modal safe-default/focus-trap behavior, failed deletion, and successful retry.
- 136 selected Python UI, desktop, Host sharing, removal, and security tests passed.
- 10 Rust launcher/model-pack tests passed; `cargo fmt --check`, focused Ruff, and
  `git diff --check` passed.
- The offline UI export verified byte-identical to authored assets. The new confirmation module
  is included in the deterministic export inventory and cache-revision check.
- A disposable, ad-hoc-signed Apple-silicon `Muta.app` built with the isolated
  `com.muta.tutor.qa` identifier. Its executable is arm64 and its packaged `startup.js`,
  `app.js`, and `confirm-dialog.js` are byte-identical to the reviewed sources.
- The required fresh-context adversarial review reported no release-blocking finding.

The managed workspace denied local socket binding and macOS LaunchServices refused to execute
the disposable task-built app (`kLSNoExecutableErr`). The in-app Browser also correctly refused
the local `file:` fallback. Consequently, cold/warm GUI launch and live WKWebView interaction
could not be observed in this task; they remain a packaging-machine acceptance check and are not
represented here as passed.
