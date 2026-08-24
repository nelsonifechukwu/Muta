# Consented product observability client

**Date:** 23 August 2026
**Scope:** the offline Muta application only

## Product decision

Muta remains fully functional without an account or network. Optional product observability is
installation-level and pseudonymous: it identifies a randomly generated installation, not a named
child. The laptop operator makes an informed choice before the first transfer. A refusal is durable
and quiet; Settings can later grant or withdraw permission.

Location is coarse and network-derived by the separately operated processor. The laptop requests
no browser/OS geolocation and sends no GPS coordinates. Conversations, prompts, files, voice,
usernames, email, hostname, and account identities never enter the heartbeat.

The owner-only dashboard and online processor are a separate private control plane. Their source,
read APIs, schema, assets, credentials, and deployment details do not live in or ship with Muta.

## Application architecture

1. `orchestrator/product_analytics.py` owns a mode-0600 SQLite consent record, random installation
   UUID, aggregate recent activity, and best-effort background sync worker.
2. The worker is inert unless an HTTPS processor URL, a write-only credential, and granted consent
   all exist. Loopback HTTP is permitted only for local QA.
3. `/v1/product-analytics` is an operator-only status/consent surface. LAN learners cannot view or
   change installation consent.
4. `ui/product-analytics.js` shows the one-time disclosure and persistent Settings switch using
   Muta's existing modal and design tokens. It never invokes browser geolocation.
5. Revocation stops heartbeats and durably queues remote erasure. The old installation UUID rotates
   only after deletion succeeds, so retry/re-opt-in cannot cancel an outstanding erasure.

## Activity and sync semantics

- Only successful activity from the loopback operator or an authenticated Host-mode member counts.
  Health/readiness probes, public auth routes, rejected tokens, and consent polling do not.
- In-memory subjects are process-keyed hashes, time-pruned on every interaction, and defensively
  capped. No local account identity leaves the process.
- Granted installations send the latest compact state at a bounded interval. Offline failure is a
  normal no-op; there is no growing event queue and no tutoring request waits for delivery.
- Payload: durable random installation UUID, app version/build, OS and processor family, last-use
  time, aggregate registered/active local-user counts, and send time.
- The remote processor derives approximate location from the connection; the laptop sends neither
  IP fields nor coordinates in the JSON payload.

## Acceptance checks

- Unknown/declined consent sends nothing and survives restart.
- Repeated decline and re-grant cannot clear pending erasure; confirmed deletion rotates identity.
- Network failure never fails startup or tutoring and is retried.
- Collector URL is HTTPS except explicit loopback QA.
- Health checks and failed/legacy bearer requests neither forge activity nor grow subject state.
- LAN members cannot mutate installation consent.
- UI names the telemetry pseudonymous, lists every payload category, and makes erasure behavior clear.
- Public Muta build/wheel/container contains no private dashboard, admin read API, online schema, or
  control-plane runbook.

## Shipping inputs

Laptop builds receive only the externally supplied `MUTA_FLEET_URL` and write-only
`MUTA_FLEET_INGEST_KEY`; both remain unset by default. The private service URL, credentials, and
deployment are managed outside this repository.
