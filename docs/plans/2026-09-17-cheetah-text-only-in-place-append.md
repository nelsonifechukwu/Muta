# Cheetah PDF text-only in-place append plan

## Objective

Recover every self-contained mathematics question/answer pair that can be verified from the
2019-2025 Cheetah question and solution PDFs, and append the accepted rows directly to the
existing 2.5M warehouse and 300K SFT artifact. Do not copy either dataset. Exclude any row that
needs a diagram, graph, table, drawing, missing notation, or an unresolved answer.

## Admission contract

- The prompt is non-empty, self-contained, and retains every numbered part.
- The answer covers every requested part; a scalar answer key alone is insufficient for a
  multipart question.
- A worked solution is present and internally consistent with the canonical answer.
- The question and solution contain no unresolved PDF/OCR/rendering artifact.
- The question can be answered without seeing a diagram, graph, table, construction, or other
  omitted asset.
- The exact source row and review decision are content-addressed.
- Rows that fail any check remain excluded; they are not guessed or silently repaired.

## Work sequence

1. Fix and test the Cheetah parser's multipart and 2025 solution-boundary defects for future
   reproducibility. Do not regenerate the corpus snapshot used by the current append until the
   append provenance is sealed.
2. Build a conservative candidate set from the existing 452-row corpus snapshot, excluding all
   explicit or inferred visual dependencies and malformed prompts/solutions.
3. Review each candidate's prompt, complete canonical answer, and worked solution. Correct
   incomplete scalar answer keys from the verified worked solution where possible; otherwise
   exclude the row.
4. Extend the append validator so a `needs_visual_review` PDF source may enter only when its
   ledger entry records an explicit completed text-only review and no required asset.
5. Dry-run the content-addressed Cheetah ledger against both current artifacts, check collisions,
   schema, token limits, hashes, holdouts, and manifest deltas.
6. Have a fresh reviewer adversarially inspect the selected rows and mutation plan.
7. Apply one deterministic shard to each existing artifact, then re-read and hash every listed
   shard and verify exact row/source counts. Re-run apply to prove idempotence.

## Mutation boundary

Only the two existing manifests plus one new shard and one rollback receipt per artifact may be
created by the apply operation. Existing shards remain byte-identical. Review/provenance files
may be added or updated; no duplicate dataset directory or base-shard backup is allowed.

## Completion record

- Reviewed all 452 Cheetah source rows exactly once: 303 approved and 149 excluded.
- Approved by year: 2019=45, 2020=36, 2021=34, 2022=41, 2023=44, 2024=51,
  2025=52.
- Seven approved rows carry explicit correction provenance: five prompt-only repairs and two
  publisher-answer corrections. The remaining 296 are independently verified without repair.
- Append ID: `muta_private_waec_append_v1_c0cabc4e7db6363447d90421`.
- Appended shard SHA-256: `9514e87da6237cd0f2dd9b6f73d19d7ba447ea83ecfb333cf45e8778f22648c6`.
- Warehouse changed in place from 2,500,047 to 2,500,350 rows via
  `part-00101-private-waec-363447d90421.jsonl`.
- SFT artifact changed in place from 300,047 to 300,350 rows via
  `part-00013-private-waec-363447d90421.jsonl`.
- Both appended shards are byte-identical, contain exactly 303 unique records, and are listed in
  their manifests with exact byte, row-count, and SHA-256 receipts.
- A second apply returned `already_applied`; full target verification, inverse-manifest recovery,
  focused/broad tests, lint, token limits, and the independent adversarial review all passed.
