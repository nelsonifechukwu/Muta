# Muta Share — LAN host mode

Date: 2026-08-22
Branch: `muta-share`

## Outcome

One laptop can turn on Host mode, show a LAN URL and QR code, approve local sign-ups, and
serve private Muta sessions to approved learners. The laptop operator remains the only host
administrator. Learner accounts and data survive logout and restart; removing a learner
revokes every session and erases their Muta-owned data, so a later return is a new sign-up and
approval.

## Constraints already present

- The browser is only a `/v1` client; no UI-only authorization decision is trusted.
- Conversations, attachments, uploaded resources, and settings have owner checks, but the
  adversarial review found legacy chat/tutor/audio/session paths that still trust client ids.
  Muta Share therefore adds one server-resolved `AuthPrincipal` and a route firewall across
  JSON, SSE, media and WebSocket paths before relying on the existing store-level checks.
- The gateway already owns a bounded FIFO `GenerationManager` and llama.cpp has a fixed
  `--parallel` slot count. Capacity changes therefore alter the admission limit and, when the
  supervised engine is available and idle, restart it with the matching physical slot count.
- The ADTC posture remains the default. Product capacity is an explicit host opt-in and never
  disables the degradation ladder, thermal policy, queue bound, or system reserve.
- Everything works without internet, an external identity provider, a Docker daemon, or a CDN.

## Security and ownership invariants

| Concern | Invariant |
|---|---|
| Host authority | Host administration requires an explicit random host session minted only on the loopback listener. Mutations additionally require its CSRF secret. Forwarded headers alone never establish host authority. |
| Passwords | Store `hashlib.scrypt` hashes with per-account random salts; never store or log plaintext. Password-manager paste/autocomplete remains enabled. |
| Sessions | Use 256-bit opaque random bearer tokens; store only SHA-256 token digests. Apply idle and absolute expiry. Logout revokes one session. Removal revokes all sessions. |
| Approval | Sign-up creates a `pending` account. Pending and rejected/removed accounts cannot call private tutor APIs. Approval is host-only. |
| Enumeration | Login failure is generic. Username uniqueness is case-insensitive. Host roster is never exposed to LAN learners. |
| Isolation | The authenticated account UUID is the existing `student_id`; every conversation/resource/twin endpoint remains owner-scoped. |
| Removal | First mark the learner `deleting` and revoke sessions, then stop/join work, erase owned stores/twin/KV, and finalize. The idempotent saga resumes unfinished deletion after restart. |
| Host-only features | Host mode, roster, capacity policy, model switching, sharing URL, and QR are hidden in the learner UI and rejected server-side. |
| Disabled sharing | Static UI may be reachable on the LAN, but enrollment/login/tutor access is closed until the host enables sharing. |

## Persistence

Add a small portable control database at `data/muta-share.sqlite3` (override:
`MUTA_SHARE_DB_PATH`). It is intentionally independent of the optional Postgres conversation
store so native/portable and Compose deployments have identical offline account behaviour.
Compose bind-mounts `/app/data`, including its WAL files, so a recreate does not erase it.
The database and parent directory use owner-only permissions.

Tables:

- `share_settings`: singleton `enabled` and `memory_mode` (`competition` or `system`).
- `share_users`: UUID, normalized/display username, scrypt salt/hash, status, timestamps.
- `share_sessions`: token digest, user UUID, created/last-used timestamps.
- `share_enrollments`: expiring, single-use random polling-secret digest for the pending
  approval screen; approval exchanges it directly for a session, so the browser never retains
  or resubmits the plaintext password.

SQLite uses WAL, foreign keys, bounded transactions, and append-only migrations.

## API additions

- `GET /v1/share/status` — public bootstrap state; returns role/state for an optional bearer.
- `POST /v1/share/signup` — create pending account and enrollment polling secret.
- `GET /v1/share/enrollments/{id}` — poll pending/approved/removed state with the secret.
- `POST /v1/share/login` — approved username/password to bearer session.
- `POST /v1/share/logout` — revoke current share session.
- `GET /v1/share/me` — current approved learner.
- `GET /v1/share/host` — loopback-only URL, capacity and pending/approved roster.
- `PUT /v1/share/host` — enable/disable and choose ADTC/system memory mode.
- `POST /v1/share/host/users/{id}/approve` — approve pending learner.
- `POST /v1/share/host/users/{id}/reject` — reject a pending request.
- `DELETE /v1/share/host/users/{id}` — revoke and erase learner.
- `GET /v1/share/host/qr` — loopback-only offline PNG encoding the LAN `/chat/` URL.

The legacy `/v1/auth/session` becomes a loopback-only host bootstrap in product mode. When
sharing is enabled it cannot mint an arbitrary LAN identity. A central policy closes every
non-bootstrap `/v1` route, `/internal/*`, docs and schema to anonymous/pending/removed clients;
WebSocket authentication is enforced at handshake and rechecked during a long voice session.

## Network transport and host authority

Password authentication and long-lived sessions are never offered over remote plaintext HTTP.
Enabling Host mode starts a second, HTTPS-only LAN listener using an offline certificate stored
under `data/share-certs/`; the QR encodes that listener, not an untrusted `Host` header. The host
panel shows the certificate fingerprint and CA-download/trust instructions. The loopback UI
stays on the primary listener and is the only place a host session can be minted. Self-signed
first-use limitations are stated honestly; a pre-installed classroom CA removes the warning.

The LAN listener binds separately, so Settings can enable/disable it without rebinding the
primary Uvicorn process. Compose publishes its fixed port and native mode uses the same port.
Multiple NICs are shown as explicit candidate URLs; `MUTA_SHARE_HOST` is the deterministic
override. No usable interface is a visible recoverable state, not a guessed URL.

## Capacity policy

Inputs:

- physical and currently available RAM from `psutil.virtual_memory()`;
- current whole-process-tree RSS;
- configured llama.cpp slots;
- model metadata through `runtime/kvmath.py`: token-growing KV, hybrid recurrent state per slot
  and checkpoint, weights, prompt cache and provisional compute buffers;
- non-negotiable gateway, repack, OS and auxiliary-inference reserves.

Policy:

- `competition`: use one ceiling—min(6.6 GiB, the existing container cap)—and reserve the full
  second vision process under the official process-tree RSS rule. Keep at most two text lanes;
  if the 4B default cannot fit, atomically select the pinned Qwen3.5 0.8B local model.
- `system`: use the existing cgroup cap, or 85% of physical RAM when native, and further bound
  it by current Muta RSS plus `MemAvailable` minus an OS reserve. Solve complete profiles while
  preserving a minimum useful context per slot, then cap by physical CPU cores and 1–32 product
  bounds. Price auxiliary inference before admitting text lanes.
- One controller owns engine `n_parallel`/`n_ctx`, `GenerationManager`, `SessionManager`,
  `ChatEngine.context_window_tokens`, and the ladder cap. It closes admission, waits for all
  running/queued/reserved work to drain, restarts, updates all dependants, then reopens. Any
  failure rolls the old profile back. Existing queued producers are never carried across a
  restart.
- At runtime, the existing degradation ladder can reduce effective admissions and queue new
  work before the static estimate is exhausted. Product mode never overrides L3/L4 safety.

Capacity status reports the calculation (RAM, ceiling, base, per-chat estimate, concurrent
limit, running and queued counts) so the host sees why Muta chose a number.

## UI flow

1. Laptop operator opens Settings → Host mode and turns sharing on.
2. The panel shows the LAN URL, Copy action, QR image, ADTC/system memory choice, calculated
   concurrent chat limit, current load, pending requests, approved members, and removal action.
3. A LAN browser sees a full-screen Login / Sign up gate. Sign-up moves to a polite pending
   screen that polls without repeated password submission.
4. Approval atomically exchanges the one-time pending credential for a session. The password is
   discarded as soon as sign-up returns; refresh can safely resume the pending flow.
5. Approved learners get normal chat/settings/resources. They do not see host controls or model
   switching. A visible account row supports logout.
6. Logout removes only the local bearer; server data remains. Login restores the same account
   UUID and its chats. Host removal invalidates the bearer and returns that browser to the gate.

The auth gate uses visible labels, `autocomplete`, inline errors, `aria-live`, 44 px controls,
keyboard focus management, mobile-first layout, and reduced-motion-safe feedback.

## Tests / adversarial cases

- Password hash/verify, normalization, duplicate names, invalid input, generic login failure.
- Pending cannot authenticate; approval enables login; logout revokes; restart persistence.
- Removed user token is invalid and data is erased; same username can sign up afresh.
- Remote requests cannot enable host mode, approve/remove, fetch roster/QR, change model, or
  mint a legacy identity by choosing a victim id.
- Host mode off closes remote signup/login and existing member access, without breaking the
  loopback operator.
- Two users cannot read/delete each other's conversations/resources/attachments/settings.
- Competition/system capacity calculations across 4/8/16/32 GiB fixtures, bounds, queues,
  active-job reconfiguration refusal, degradation safety, FIFO and queue-full behaviour.
- Host URL selection/override and QR endpoint content type/no-store behaviour.
- Signup → pending → approve → login → chat → logout → login → remove → forced reauth journey.
- UI asset/static tests, contract generation, lint, full pytest and Node browser-unit suite.

## Delivery notes

- Keep `ui/` and `ui/dist/` byte-matched because both native and nginx deployments consume the
  authored offline bundle.
- Update `RUN.md` with Host mode and the plain-HTTP LAN microphone limitation (chat works;
  browser microphone requires the existing local TLS path).
- Do not commit or push; leave the branch and working tree for review.
