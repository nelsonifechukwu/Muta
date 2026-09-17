# Private WAEC in-place append plan

## Objective

Add independently reviewed rows from `corpus/waec/questions.jsonl` to the existing 2.5M
candidate warehouse and 300K SFT artifact without copying either dataset or rewriting an
existing shard. The append is private-study-only: publisher licence text remains unchanged,
and the user's private-use attestation is recorded as a separate, narrower fact.

## Invariants

- Dry-run is the default. Mutation requires the explicit `--apply` flag.
- Existing `part-*.jsonl` files remain byte-identical.
- Each target receives exactly one new, deterministic JSONL shard.
- A manifest is replaced only after the corpus, ledger, attestation, both target manifests,
  all base shard receipts, every emitted SFT row, and all staged outputs validate.
- Only exact rows whose decision is `approve_verified` or `approve_corrected_verified` are
  emitted. Every decision is bound to the corpus SHA-256 and exact source-row SHA-256.
- Missing, doubtful, incomplete, or visual-dependent material stays out until the ledger
  records an independently verified answer and resolves every required visual dependency.
- Publisher licences are never rewritten as permission. The user attestation is stored under
  private-use metadata and explicitly says that it is not a publisher licence. Its scoped
  project-owner adjudication allows the exact content-approved rows in these private training
  artifacts while preserving any earlier rights-blocked flag as audit history.
- The attestation binds the exact ledger hashes, row counts, review-bundle hash, and the one
  explicit overlapping-review adjudication. An arbitrary replacement ledger cannot inherit it.
- Rows use the truthful `model_assisted_reviewed` verification status; none is represented as
  human-reviewed or as having an executable programmatic verifier.
- Repeating the same append is idempotent. Conflicting partial state fails closed.
- Rollback needs no shard backup: remove the one appended shard and use the receipt's inverse
  manifest patch. The tool proves before commit that the inverse patch recreates the exact
  pre-append manifest bytes.

## Implementation

1. Add `private_waec_append.py` with:
   - strict JSONL corpus/multiple-review-ledger and JSON attestation readers;
   - content-addressed ledger decisions and attestation validation;
   - deterministic SFT-v2 adaptation, sealed-holdout check, schema validation, and exact Qwen
     token accounting;
   - streaming verification of every receipted base shard while checking ID/prompt collisions;
   - deterministic staged shard, manifest, and rollback-receipt bytes;
   - a two-target prepare/commit sequence with cleanup on ordinary failures;
   - `--dry-run` and `--apply` modes.
2. Add focused tests using tiny artifact fixtures and a deterministic token-counter double.
3. Run the focused tests and lint. Ask a fresh reviewer to attack mutation safety and provenance
   semantics before the real ledger is used.

## Real apply command (only after the review ledger is complete)

```sh
PYTHONPATH=model-development/finetune .venv/bin/python -m muta_dataset_v2.private_waec_append \
  --corpus corpus/waec/questions.jsonl \
  --review-ledger corpus/waec/private-training-review-ledger.jsonl \
  --review-ledger model-development/finetune/muta_dataset_v2/WAEC_COMPLETE_PUBLISHED_APPROVED_IDS.jsonl \
  --attestation corpus/waec/private-training-attestation.json \
  --warehouse data/muta-stem-v2-warehouse-20260916-v7 \
  --sft data/muta-stem-v2-sft-300k-quality-first-20260917-v1 \
  --apply
```

Omit `--apply` (or pass `--dry-run`) to perform the complete validation and print the proposed
append without changing either artifact.

## Completion record

Applied in place on 2026-09-17 after the final dry run and adversarial review.

- Append ID: `muta_private_waec_append_v1_1b73164d0c67e1720e95858d`
- Approved rows: 47 (physics 30, mathematics 8, chemistry 6, biology 3)
- Warehouse: 2,500,000 → 2,500,047 rows; 101 shards; fingerprint
  `1bb15078878864924a555a18d5872445fee3bb19dacb7466e71d2200468472af`
- SFT: 300,000 → 300,047 rows; 13 shards; fingerprint
  `288d08a273db77eca8d3e82be7835e3d9365eda0d042ccb76e4691cd39fcdefb`
- Appended shard SHA-256 (same bytes in both artifacts):
  `c165a0e0f7ede07b9e2843aef5ac714c88b45dbdfd73f99d733d3b35b115bb4e`
- Second `--apply` returned `already_applied` for both targets.
- The post-commit verifier re-read and re-hashed all 114 listed shards, reconciled all manifest
  totals/fingerprints, confirmed 47 unique appended IDs, and proved that both inverse patches
  reconstruct the exact pre-append manifest hashes.
- No existing shard was rewritten and no duplicate dataset artifact or base-shard backup was
  created.
