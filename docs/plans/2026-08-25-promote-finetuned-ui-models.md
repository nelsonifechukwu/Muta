# Promote the fine-tuned finalists into the UI catalog

## Goal

Replace the untuned Qwen3.5 0.8B and Qwen2.5 1.5B UI choices with the exact merged,
quantized finalists published in the private `timiiowolabi` Hugging Face repositories.

## Invariants

1. The browser continues to select opaque catalog IDs and never supplies a filesystem path.
2. A promoted model is selectable only when its local byte size and SHA-256 match the
   fine-tuning artifact record.
3. The Qwen3.5 projector remains paired because the campaign disabled vision-layer fine-tuning;
   Qwen2.5 remains text-only.
4. Clean-clone provisioning obtains the exact private Hub artifact through an authenticated
   `hf` CLI and fails closed when the account lacks access.
5. Historical benchmark rows and prior submission artifacts remain unchanged.
6. GCP replacement is atomic and recoverable from the retained campaign model directories.

## Work

1. Update the runtime catalog labels, hashes, sizes, accuracy, and matched scalar throughput.
2. Replace the two provisioning recipes with authenticated, SHA-verified Hub downloads.
3. Align desktop packaging checks and the current model-selection document.
4. Add focused tests tying the catalog to the fine-tuning artifact and summary records.
5. Promote the exact GCP files, restart the native stack, and prove both choices are available.

## Acceptance

- The catalog identifies Qwen3.5 SHA `552de22f…ff26` and Qwen2.5 SHA `a750d00d…e1eb`.
- Both fetch scripts reject an incorrect size or hash.
- Focused and full tests pass.
- GCP `/v1/models` reports both promoted models available and the running default is the
  fine-tuned Qwen3.5 artifact.
