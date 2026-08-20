# Qwen2.5 UI catalog addition

## Goal

Expose the exact benchmarked Qwen2.5 1.5B Instruct Q4_K_M artifact in the native
Linux `/ui` model selector without changing the recommended default.

## Implementation

1. Add the model's exact path, byte size, and SHA-256 to the versioned runtime
   catalog.
2. Add a pinned, fail-closed download recipe for clean installations.
3. Extend the catalog/recipe test so a displayed option cannot drift from the
   provisioned artifact.
4. Document the model's benchmark role and setup command.
5. Verify the selector tests locally, sync the commit to the VM, reuse its
   already-benchmarked artifact at the catalog path, and check the live API.

## Acceptance criteria

- `/v1/models` lists Qwen2.5 1.5B with the exact benchmarked artifact metadata.
- The option is available only when the verified file is present.
- A clean setup can fetch the exact file from a pinned source revision.
- Qwen3.5 0.8B remains the recommended default.
- The live VM reports both the default and Qwen2.5 artifacts as available.
