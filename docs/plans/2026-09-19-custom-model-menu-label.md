# Custom GGUF menu-label correction

## Problem

The portable launcher correctly imports operator-added GGUF files, but some merge/export tools
write generic metadata such as `general.name = "Merged Bf16"`. The model catalog currently trusts
that value, so the model appears under an unrecognizable name and looks absent from the chooser.

## Change

1. Keep meaningful embedded model names as the preferred label.
2. Treat known generic merge/export labels as non-identifying and use the GGUF filename stem.
3. Add a regression test using the exact `Merged Bf16` metadata pattern.
4. Reproduce catalog discovery against the user's installed pack, run focused tests, and rebuild
   the Apple Silicon portable app from the corrected source.

## Invariants

- Custom GGUF discovery, path confinement, symlink rejection, and integrity checks do not change.
- Existing curated labels remain unchanged.
- The custom model remains outside the signed base-model manifest by design.
