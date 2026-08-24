# Desktop release reliability and custom model add-ons

## Scope

The four offline applications keep the existing signed base model pack. Additional GGUF files
are independent downloads: an operator copies them into `model-pack/models/custom/` (or uses an
add-on pack published from GCP), then launches Muta through the platform wrapper. The launcher
synchronises only valid custom GGUF files into the user's versioned model store. The gateway
discovers those files at runtime and exposes them through the existing `/v1/models` contract.

This work also fixes two release-only failures reproduced on macOS:

- Host mode selected a hard-coded fallback catalog ID that the minimal release catalog does not
  contain, returning HTTP 409 and leaving the switch off.
- A chat submitted during a supervised engine replacement could surface a raw HTTP 503 instead
  of waiting for the local engine to become ready again.

Finally, production packages receive the existing fleet heartbeat URL and write-only ingest key
at build time. The key is retrieved from Secret Manager into process memory, never committed or
printed, and configuration diagnostics redact it. Heartbeats remain disabled until the operator
explicitly enables approximate network-location sharing in Settings.

## Invariants

1. A custom model path must remain below the model root, be a regular non-symlink `.gguf`, and
   have a valid GGUF header before it appears in the catalog.
2. Shipped catalog models retain exact size and SHA-256 verification. User-added models are local
   operator data and receive a stable path-derived ID; parsed metadata is cached by file identity.
3. Every model selection, including local desktop selection outside Host mode, passes the same
   RAM-capacity planner. Models that cannot fit are visible but disabled with a reason.
4. The signed base model manifest is immutable. Custom files live below `models/custom/` and are
   deliberately outside the signed manifest; launcher sync never overwrites manifest members.
5. Model add-ons are not inserted into the four application archives. GCP publishes them as
   individual GGUF downloads with checksums and a machine-readable manifest.
6. Engine replacement remains an idle, serialized operation. New generation admission waits a
   bounded interval for a supervised restart and never duplicates a submitted learner message.
7. Host mode chooses the smallest verified installed local model when a competition fallback is
   genuinely required; it never assumes a source-catalog ID exists in a release catalog.
8. Fleet telemetry stays opt-in, tutoring stays offline-first, and heartbeat failure never affects
   model startup or chat.

## Verification

- Unit tests for custom discovery, invalid/symlink rejection, stable IDs, refresh, and hash cache.
- Capacity and route tests using a release-shaped one-model catalog and low-current-headroom probe.
- LAN integration test that enables Host mode and reaches the HTTPS listener.
- Generation admission tests for transient recovery and bounded permanent failure.
- Launcher/install tests proving custom GGUF sync on macOS, Linux, and Windows wrapper paths.
- Product-manifest tests proving fleet configuration is embedded only when supplied and diagnostic
  output redacts the ingest key.
- Four-platform artifact inspection, archive checksums, packaged backend startup, model listing,
  base-model inference, Host toggle, and heartbeat-settings visibility.
