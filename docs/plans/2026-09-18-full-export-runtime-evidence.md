# Full-export runtime evidence collector

18 September 2026, updated 19 September. Collector implemented and independently
reviewed; root collected actual metadata-only drafts on Oracle. No export was
performed by this collector. Added
`collect_full_export_runtime_evidence.py` and focused tests separately
from the reviewed/frozen launcher, preflight, exporter and helper.

The collector loads only launcher SHA256
`16f10222dab4be4facc7e04e6f6a6215d6d0d17d312887a4308445a85df9abb0`.
It requires an external SHA256 of an existing completed artifact-preflight
receipt and uses that receipt to recover the exact candidate/source paths.
It collects the launcher's precise stdlib metadata/import-path `PROBE` under
the same sanitized offline environment, checks the pinned converter/quantizer,
measures current clean Git status/commit, and resolves `ldd` native-library
paths. It does not import ML libraries, query/claim the GPU, allocate a model,
read dataset rows, export, infer, SSH or change source files.

Dependency coverage is explicit, non-hermetic: all `.py` files found recursively
under `conversion/` and `gguf-py/` (tracked or untracked, with a clean checkout
still required), converter entry point, reported module origins, interpreter,
resolved native libraries, and the probe-command identities. Files are hashed
by streaming; walks/receipts are bounded and reject symlinks in source trees.
It does not hash every installed Python/stdlib/CUDA byte or discover all dlopen
edges. Expiry is positive and at most 24 hours; source/metadata identities are
rechecked before emitting a new exclusive small JSON receipt.

The frozen launcher's file-receipt helper rejects zero-byte files. All empty
Python sources are still enumerated with SHA256/size in
`coverage.empty_python_sources`; they are not silently discarded. This separate
empty-file evidence needs explicit review and is not rehashed by that launcher's
dependency loop. Empty module origins fail closed as incompatible. Nonempty
sources remain in `dependency_files`; clean Git is required in every case.

```bash
python collect_full_export_runtime_evidence.py \
  --launcher /verified/full-export-v1/launch_full_stage_export.py \
  --preflight-receipt /verified/selected-export-preflight.json \
  --expected-preflight-sha256 ACTUAL_RECEIPT_SHA256 \
  --python /home/ubuntu/muta-finetune/.venv/bin/python \
  --git /usr/bin/git --nvidia-smi /usr/bin/nvidia-smi --ldd /usr/bin/ldd \
  --planned-output /new/export --gpu 0 --expires-in-seconds 7200 \
  --output /new/runtime-evidence-draft.json
```

The output kind is `muta_full_export_runtime_evidence_draft`, not the admitted
kind accepted by the launcher. `review_required=true` and
`runtime_admission_granted=false` remain explicit. Root reviews measured evidence
and, only after approval, creates a separately hash-bound admission receipt with
the accepted kind. A collector success cannot silently grant launch permission.
The collector does not wait for an idle GPU or modify the queued training work.

Tests use tiny synthetic files and stubbed read-only commands: exact schema,
draft refusal by the launcher, expiry/source/hash drift, dirty Git, malformed/
unresolved ldd output, symlink/depth/count bounds, source enumeration, no secrets
or private data, no overwrite, no model/GPU/export subprocess. Independent review
and real-host evidence collection are distinct from admission.

Independent agent review passed for collector SHA256
`24ca98c0900c8e761c4d969c720e268dff504d9f910a71790a3800d17bf29f24`
and tests SHA256 `a3e542780cc863676c582154f05eaf4e12bfca7ce24350e9ed2ef935495bede3`.
All 22 focused tests, Ruff and formatting checks passed. Root separately staged
the collector at Oracle `code/full-export-evidence-v1-20260918T2227` and verified
its exact SHA, leaving the four frozen export-source files unchanged.

After the actual clean run completed, root collected a draft against real
preflight SHA256 `d61276f963180656bfa56141c36183065f2a478152dd7bfa8a07c180714b62b9`.
Draft SHA256 is `279036bd5f50238a6685d829f062169b787b999d0c9eea8ca00edd236a67b39c`;
remote location is `provenance/full-export-v1/clean-runtime-evidence-v1.json`
under the campaign root. An exact small local copy is in
`provenance/training/full-best-clean-private-enriched/`.
It measured 126 dependency files, all 105 conversion/gguf Python sources,
six native-library resolutions, and no empty Python sources. The checkout was
clean and pinned; package identities/import origins matched the earlier probe.
This remains **evidence-draft only**. The GPU is occupied by the authorized
continuation run, no export was attempted, and the later launcher must still
acquire the shared lock and make fresh idle/input/runtime checks.

Local verification: 22 focused tests pass; Ruff and formatting checks pass.
Review identified a first-read consistency gap: the implementation now rechecks
the original interpreter, command, ldd, pinned converter and pinned quantizer
receipts, not just the later dependency snapshot. Five dedicated regressions
change those identities between the two reads and assert collection fails.
No frozen launcher/preflight/exporter/helper source was edited.
