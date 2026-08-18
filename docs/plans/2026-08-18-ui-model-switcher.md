# Native UI model switcher — implementation plan (2026-08-18)

## Goal

Keep the benchmark-selected Muta Tutor Qwen3-1.7B Q4_0 model as the native Linux default,
while letting a local user switch the running engine to the accuracy-max BitCPM-CANN-8B
TQ2_0 vocabulary-pruned model from `/ui` and switch back without restarting the gateway or
losing SQLite conversation history.

This implements the local-only thin slice specified by ROADMAP 2 Aug: a backend registry is
the authority; the UI never supplies a filesystem path; cloud remains visibly unavailable
offline.

## Invariants

1. Exactly one `llama-server` is resident. A switch stops the current child, verifies the
   selected GGUF, starts the replacement on the same loopback port, and leaves FastAPI alive.
2. Only model IDs from a versioned local catalog may be selected. Paths are repo-relative and
   resolved below `TUTOR_ROOT`; path traversal and arbitrary model paths are impossible.
3. A local model is selectable only when its byte size and SHA-256 match the catalog. Hashes
   are cached by `(path, size, mtime_ns, ctime_ns)` after first verification.
4. Failed activation rolls back to the prior model. The API reports the failure and the
   gateway dependency cache is refreshed only after a successful engine start.
5. Switching is serialized. The API exposes `switching`, `active`, `available`, and disabled
   reasons so the UI cannot present a stale success state.
6. The gateway and SQLite store survive a switch. In-flight generation is explicitly
   disruptive; the UI disables the selector while its own generation is active.
7. Muta Tutor remains the default and BitCPM is an opt-in accuracy experiment. UI copy makes
   the measured trade-off explicit: 0.70 vs 0.84 ARC-Easy, but much lower generic/audit-proxy
   throughput.

## Model records

- `muta-tutor-qwen3-1.7b-q4_0`: `muta-iq/model/muta-tutor-qwen3-1.7b-q4_0.gguf`,
  SHA-256 `a98ce36e9ff97e5271d90cbc429c952f99a5a966bb0195ae74661b4c054fd63e`,
  974,198,528 bytes.
- `bitcpm4-8b-tq2_0-envocab`: `muta-iq/model/bitcpm4-8b-tq2_0-envocab.gguf`,
  SHA-256 `069621f168502215839fb82db3afe35beb8e5350fb6cbf8523aa1eea6bee237d`,
  2,208,746,208 bytes.
- `cloud`: disabled entry with an offline explanation; it cannot be selected.

## Work

1. Add a typed, validated model catalog and a process-wide engine manager with serialized
   switch, verification, supervisor coordination, rollback, and dependency-cache refresh.
2. Add additive `/v1/models` GET and `/v1/models/select` POST contract models/routes and
   regenerate `contracts/openapi.yaml`.
3. Add an accessible UI selector, loading/switching/error states, benchmark trade-off copy,
   and tests for browser assets and API behaviour.
4. Add deterministic BitCPM fetch/derive provisioning with pinned source and final hashes.
5. Run focused tests, full tests/lint/contract generation, then deploy both exact artifacts
   and the new native UI to the GCP VM. Prove switch both directions with a fixed inference
   smoke and record process/RSS evidence.
6. Run the required fresh-context adversarial review, resolve findings, group commits by
   concern, and push `main` to GitHub.

## Acceptance

- `/v1/models` reports Muta Tutor active and BitCPM available with exact hashes.
- Selecting BitCPM returns only after its engine health check succeeds; `/ui` reflects it.
- A fixed UI/API prompt completes on BitCPM; switching back completes on Muta Tutor.
- At all checkpoints there is at most one `llama-server` process.
- A missing/corrupt model is disabled and cannot take down the current engine.
- A forced replacement start failure restores the previous model.
- Gateway PID and SQLite database are unchanged across both switches.
- Focused and full tests pass, native manifest verifies, and grouped commits are pushed.
