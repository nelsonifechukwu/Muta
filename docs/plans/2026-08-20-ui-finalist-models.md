# Native UI finalist model options

## Goal

Expose the two current submission finalists in the native Linux `/chat` model selector:

- Muta Tutor Qwen3.5 0.8B Q4_0, the risk-adjusted recommendation.
- Qwen3 0.6B Math-Expert Q4_K_M, the raw fixed-15 Scalar and AVX2 leader on ARC-Easy-50.

Keep the existing historical comparison models available. Model selection remains an operator-only,
loopback action and continues to replace the single supervised `llama-server` child without
restarting the gateway.

## Changes

1. Add the exact Math-Expert artifact to the hash-verified runtime catalog.
2. Correct the Qwen3.5 finalist byte size in the catalog to match its recorded SHA-256 artifact.
3. Add a pinned Math-Expert download recipe and check its hash against the catalog in tests.
4. Update the model-selection documentation with the current evidence and provisioning command.
5. Install both exact GGUFs on the GCP VM, launch native Linux mode, and verify the selector and a
   model switch through the loopback API.

## Acceptance

- `/v1/models` reports both finalists as installed and selectable.
- Qwen3.5 0.8B is active after startup and remains marked recommended.
- Selecting Math-Expert starts it successfully while the gateway PID remains unchanged.
- Selecting Qwen3.5 again restores the default, with exactly one `llama-server` process throughout.
- Focused catalog, route, UI, shell, and full test suites pass.
