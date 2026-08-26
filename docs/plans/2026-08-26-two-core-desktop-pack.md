# Ship Qwen2.5 and Qwen3.5 as desktop core models

## Goal

Replace the single-core v0.1.449 desktop model pack in place with a verified two-core pack on all
four targets. Qwen2.5 1.5B is the fresh-install default; Qwen3.5 0.8B remains selectable and keeps
its image projector.

## Invariants

1. The exact packaged GGUF names are
   `Muta-Tutor-Qwen2.5-1.5B-Finetuned-Q4_K_M.gguf` and
   `muta-tutor-qwen3.5-0.8b-q4_0.gguf`, both below `model-pack/models/core`.
2. Qwen2.5 must match the fine-tuning artifact record: 986,048,128 bytes and SHA-256
   `a750d00d458c6ab38925364ea1413db00648449180941e47025736d09922e1eb`.
3. Qwen3.5 must retain its existing 512,977,376-byte/SHA-256 pin and verified F16 projector.
4. A new data directory starts Qwen2.5. A successful explicit model switch is persisted and may
   override that default on later starts; invalid/stale preferences fail back to the packaged
   default.
5. Core models remain governed by the signed pack manifest. They are never treated as mutable
   custom imports, and a pack update preserves user-added `models/custom` files.
6. The model-input cache key changes, while unchanged native-engine layers remain reusable.

## Verification

- Unit tests bind catalog IDs, filenames, default/recommended metadata, persistence, installer
  upgrades, cache classification, and both manifest hashes.
- The release inspector rejects a package missing either core file or selecting Qwen3.5 by
  default.
- Each final archive is independently extracted and checked for both files, manifest hashes,
  source commit, packaged UI, and platform signing/native architecture.
- A clean temporary data root reports Qwen2.5 as the active startup model; a persisted Qwen3.5
  choice survives a restart.
