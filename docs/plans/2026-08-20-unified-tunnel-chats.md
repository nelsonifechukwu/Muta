# Unified chat history across tunnel ports

## Goal

Make native Linux `/ui` sessions reached through different SSH tunnel ports use one persistent
operator identity. Keep LAN classroom clients on their existing per-browser identities until the
planned user-account layer is implemented.

## Design

1. Native Linux mode enables a loopback-only identity override.
2. `POST /v1/auth/session` replaces the browser's port-scoped UUID only when the socket peer is
   loopback. It returns a persistent random UUID stored in a mode-0600 file under `data/`.
3. The UI accepts the server-returned student id and uses it for conversations, attachments,
   streaming, telemetry, and the voice loop.
4. Non-loopback requests keep the supplied per-browser UUID, so separate LAN devices do not see
   the operator's history or each other's history.
5. Existing UUID-owned operator conversations on the GCP VM are reassigned to the new operator
   UUID after making a recoverable SQLite backup. Named acceptance/smoke profiles are untouched.

## Acceptance

- Two browser origins using different local tunnel ports receive the same conversation list.
- `localhost` and `127.0.0.1` both use the persistent operator UUID when they reach the native
  gateway through loopback.
- A non-loopback peer retains its submitted student id.
- Restarting native Linux mode retains the operator UUID and history.
- Existing UUID-owned conversations are visible after migration; smoke-test profiles remain
  separate.
- Auth, route, UI, focused, and full test suites pass.
