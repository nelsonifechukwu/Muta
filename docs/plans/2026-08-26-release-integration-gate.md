# August 26 release integration gate

Date: 2026-08-26
Branch: `codex/release-integration-qa`
Release baseline: `ff0207aa3aa6ee40e5b56b0bceaba3802548d913`
Code-under-test HEAD: `027992ac8cb5ff6a89d1bef5b8779c8aca99d968`

This record gates the August 26 Muta changes. It does not authorize a merge to `main`, a
package rebuild, a deployment, or a release. The separately owned packaging task remains
blocked until the parent release task explicitly opens that gate.

## Integrated provenance

Only Muta-lineage commits were imported:

- Localization test foundation: `05bc6df`.
- Power and parallel-policy copy: source `504485b`, integrated by `d522b52`.
- Deterministic math visualization: reviewed source `b28f24e`, integrated by `1dbf22a`.
- UI polish: source `534939c`, integrated by `27f86cb`.
- Host mode and lifecycle fixes: source `dfcc290`, integrated by `b9909fe`.
- Final localization catalog: source `c061587`, based on `b9909fe`.
- Localization semantic/live-state follow-up: source `e11b546`, integrated as `829aa1c`.
- Host capacity-warning localization follow-up: source `2b5d5fe`, integrated as `027992a`.

Integration-only corrections are `6b7028a`, `a10a036`, and `db9e558`. They preserve the
offline UI bundle, make real streaming cancellation wake a blocked transport so a stopped chat
cannot retain the generation slot, keep the compact mobile composer usable at 375 px, and parse
the exact natural-language suffix on the requested deterministic surface prompt.

The Fleet dashboard commit `084d4c48a6fa035eb9548c3d3193ba9850ba0f59` is an independent
deliverable in its own unrelated repository. No Fleet commit is reachable from the integration
branch and no Fleet tree or source file was copied into Muta. A transient local tracking ref
created during the earlier tree/provenance check was removed after the boundary was confirmed.
Fleet must be pushed and deployed independently only after the shared release gate.

## Automated gate

All commands below were rerun on the final localization tree unless a narrower provenance is
stated explicitly.

- Full Python suite: exit 0; 1,453 selected tests collected, with the expected platform and
  optional-dependency skips. The only warning is FastAPI TestClient's upstream
  `StarletteDeprecationWarning`.
- Full browser-client JavaScript suite: 124/124 passed.
- Focused Stop/SSE/runtime and generation lifecycle suite: 94 passed, including a real TCP
  blocked-read cancellation regression.
- Focused deterministic-surface suite: 45 passed.
- Desktop/staging Python slice: 29 passed (also included in the full Python run).
- Tauri launcher: `cargo fmt --check` passed and 10/10 Rust tests passed with `--locked`.
- Ruff: every Python file changed after the integrated English-key freeze (`b9909fe..HEAD`)
  passed; `git diff --check` passed. An unscoped `ruff check .` is not a clean historical gate:
  baseline `ff0207a` has 500 existing findings and this branch has 499, largely in bundled
  `.agents` tooling and longstanding FastAPI dependency signatures. No unrelated lint rewrite
  was made.

## Desktop stage and asset parity

A clean clone of code-under-test HEAD was exported to `/tmp/muta-final-stage.H2KVxC` and staged
with the already verified macOS aarch64 native inputs and model artifacts:

- The app manifest verified all 130 declared files; the model-pack manifest verified all six
  declared files.
- The staged product identity is exactly
  `027992ac8cb5ff6a89d1bef5b8779c8aca99d968`, version `0.1.449`, active model
  `qwen2.5-1.5b-instruct-q4_k_m`.
- Source `ui/dist` and staged `resources/ui/dist` are byte-identical across all 120 files.
- The new `dynamic-localization.js`, visualization assets, locale catalogs, landing assets,
  native engine, FFmpeg, catalog, and independent model pack are present and manifest-covered.

This is staging and inspection evidence only. No installer, package asset, signature, upload,
or published release was created or replaced.

## Browser acceptance matrix

Real browser testing used the assembled gateway and real local inference engine, not only DOM
fixtures. The tested matrix covered:

- 1,440 px desktop, 375 px and 430 px mobile, and 812×375 landscape.
- Light and dark themes; keyboard focus; touch targets; reduced-motion behavior; Arabic RTL;
  Igbo and English live rerendering.
- Cold, warm, and failure-aware startup; pin/unpin; delete/cancel; syntax highlighting and code
  copy; mobile streaming autoscroll pause/resume.
- Host account creation, approval/removal, QR/copy surfaces, capacity warning, and terminal
  lifecycle state.
- A real long-running reply followed by Stop and an immediate new prompt. The stopped backend
  worker released its slot and the recovery prompt completed without queueing behind a zombie
  read.
- Exact `Plot z=4e^{−y²/4}sin(2x) as a 3D surface.` rendering as the bounded deterministic
  damped-sine mesh, followed by bare `animate` inheritance with Play, Pause, and Restart.
- The final Host RAM warning appears in Arabic and Igbo, rerenders back to English, and exposes
  no raw English fallback in either non-English locale.

## GCP Host relay

The real `muta-vm` relay path was exercised without changing firewall or deployment state:

- Operator UI at `http://127.0.0.1:18101/chat/` enabled Host mode and advertised
  `https://10.255.200.33:18443/chat/`.
- The learner TLS listener returned ready with gateway, inference, and database checks true and
  served `/chat/` with HTTP 200.
- The certificate subject was `O=Muta Local, CN=10.255.200.33`; the SHA-256 leaf fingerprint
  was `75:72:12:90:3E:12:CF:36:25:30:DD:FC:7F:53:8F:06:68:D0:49:66:05:A6:A6:C3:20:FD:86:57:9E:34:C0:4D`.
- Host mode was disabled after the check. The temporary relay gateway and child engine were
  stopped, the original `muta-gateway.service` was restored to `active/running`, and its local
  readiness returned true. Relay ports 18101 and 18443 were closed.

The TLS/HTTP learner path was verified from the relay laptop; a second physical learner device
was not available for a fresh certificate-install and account-login exercise.

## Independent Fleet gate

Fleet was tested at its exact independent SHA `084d4c48a6fa035eb9548c3d3193ba9850ba0f59`:

- 18/18 Python tests and both direct Node runtime suites passed; Ruff passed.
- A real development server received a synthetic `0.1.449` heartbeat and, after its actual
  30-second poll, updated installations, active/total users, country/location totals, and the
  live event feed.
- Desktop, 375 px mobile, 812×375 landscape, light/dark themes, globe controls, and keyboard
  interaction were checked in a real browser.

## Adversarial review

An independent read-only review of `ff0207a..027992a` found no P0/P1 release blocker. Its
focused rerun passed 239 Python tests and all 124 Node tests, reverified both stage manifests
and all 120 staged UI files, and confirmed that Fleet has no merge base or reachable ancestry
from Muta.

One non-blocking P2 residual remains: cancellation can interrupt a silent SSE socket after HTTP
response headers, including the real llama-server Stop/recovery path, but cannot interrupt a
server that accepts the connection and then stalls before returning response headers. The
ordinary request timeout still bounds that case. This is not a regression introduced by the
integration cancellation fix, which closes the real post-header deadlock, but it should receive
a transport-level pre-header cancellation design in a later hardening change rather than a
late private-httpx patch in this release gate.

The reviewer also found and this gate corrected a documentation-only 366-key count; the final
canonical runtime contains 367 localization keys.

## Gate boundary

No Muta or Fleet branch was pushed, no `main` merge was attempted, and no packaging,
deployment, asset replacement, or release operation was performed. The next permitted action is
to report the final integration SHA and evidence to the parent task and wait for its explicit
authorization.
