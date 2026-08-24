# GCP share + fleet launcher

Date: 2026-08-24

## Goal

Give the operator one laptop-side command that retrieves the consent-gated fleet ingest key and
starts the existing GCP classroom relay. This remains a GCP simulation tool; packaged offline
applications never call it.

## Flow

1. Refuse to run inside Google Compute Engine before requesting a secret.
2. Read `muta-fleet-ingest-key` from Secret Manager with the laptop's authenticated `gcloud`.
3. Pin both secret lookup and VM selection to the same explicit GCP project.
4. Disable shell tracing before reading the key, then export the fleet URL and key only inside the
   launcher process.
5. Preflight non-interactive SSH before any secret is supplied on stdin.
6. Let `gcp_share_relay.sh` carry the key over SSH stdin, never in the printed command or process
   arguments.
7. Clear the wrapper's secret variable when the relay exits.

Supplying an endpoint and write-only key configures fleet availability. The application still
requires operator consent before transmitting product analytics.

## Verification

- A fake `gcloud` and relay prove the wrapper passes the configured URL/key and forwards arguments.
- Neither launcher output contains the secret.
- Explicit shell tracing cannot reveal the secret.
- The real relay receives empty stdin for its preflight and the key only for the final tunnel.
- Secret lookup and VM selection use the same GCP project.
- A simulated Google Compute Engine product name fails before Secret Manager is called.
- Existing relay address, credential-pair and secret-redaction tests remain green.
