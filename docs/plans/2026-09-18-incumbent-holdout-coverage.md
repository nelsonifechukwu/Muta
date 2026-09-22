# Recover incumbent training exclusions without copying data

The exact incumbent input files were located read-only on Oracle on 18 September
2026. Their SHA256 and row counts match the existing licensed-MCQ manifest:

| Existing remote file | Rows | Bytes | SHA256 |
|---|---:|---:|---|
| `/home/ubuntu/muta-finetune/data-metric-licensed-mcq/train.jsonl` | 10,756 | 1,880,336 | `0d1b52db8dc0785fe8c0b62cbe374e79c35192b9ccd7fe86480c998808c3734c` |
| `/home/ubuntu/muta-finetune/data-metric-licensed-mcq/validation.jsonl` | 566 | 99,510 | `fd48e23f20afb5ae8986730b19cb42523610cd0620e71021e9e2e8aa99dbf69b` |

No rows were downloaded or displayed. This closes a source-location gap, not a
contamination audit: there is no finalized candidate battery to compare yet.

## Bounded implementation plan

1. Extend only the new audit-only validator with `incumbent_raw_v1`, matching
   the exact four-field `{prompt, completion, source, mode}` output of
   `build_dataset._record` used by `build_metric_dataset._raw_mcq`.
2. Require raw mode, the three licensed source labels, nonempty bounded fields,
   and the exact `Question: ...\nAnswer:` wrapper. Derive an opaque row identity
   from canonical content; never emit the source prompt or answer.
3. Audit both the original raw prompt and a normalized source-task hash of its
   unwrapped question. No family metadata exists in these inputs: leave family
   missing and retain the missing-family count. Do not infer semantic families.
4. Add synthetic tests for exact/question-task overlap, private-safe receipts,
   invalid fields/wrappers/sources/modes, and meaningful mathematical signs.
   Require independent adversarial review before any real-corpus use.
5. Later run candidate comparisons against these existing files in place on
   Oracle using small hash-bound sidecar manifests, outside the live training
   snapshot. Combine coverage honestly with the separate local warehouse audit;
   no big corpus copies and no changes to the live trainer/configuration.

This change does not create a new benchmark, approve references, or establish
family disjointness. Unknown pretraining contamination remains unknown.

## Verification record

The in-place bounded schema scan found zero invalid rows in either file. Training
source counts were 2,105 ARC-Easy / 1,061 ARC-Challenge / 7,590 QASC; development
counts were 120 / 48 / 398 respectively. Largest raw JSONL lines were 775 and
799 bytes. No source prompt or answer was displayed or copied. The metadata-only
receipt is `provenance/dataset/incumbent-input-availability-20260918.json`.

The adapter implementation passed 56 focused tests and Ruff. Independent agent
reviewer `full_promotion_audit` returned GO after inspecting fail-closed parsing,
wrapper normalization, private-safe output, signed values, and missing-family
reporting. Reviewed validator SHA256:
`cf156c43fc724f3306ec94604ef70d34da967614958777b92ac9bc23b0327c3b`.
This is source-availability/schema and code evidence, not a completed overlap scan.
