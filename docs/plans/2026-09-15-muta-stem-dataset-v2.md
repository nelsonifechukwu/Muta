# Muta STEM dataset v2 execution plan

## Goal and boundary

Construct and independently audit a reproducible 2,500,000-row candidate warehouse for the next
Muta Tutor Qwen2.5 1.5B experiment. Do not fine-tune in this task. Freeze a smaller 300,000-row SFT
view only after exact-row receipts whose decision is `approved` authorize every non-native
candidate row.

Public visibility is not treated as a training licence. Under this dataset policy, without an executed grant, WAEC,
CheetahWAEC, and MySchoolGist/JAMB contribute only independently worded high-level topic,
broad-format, rubric-structure, and error-category taxonomy. No protected question, answer,
explanation, marking scheme, report prose, figure, screenshot, OCR, or close paraphrase enters the
warehouse, SFT view, or evaluation store. Permissioned items default to a separate evaluation-only
store; training requires an explicit additional grant.

The same zero-row boundary applies to ALOC Station under its Developer Terms v2.3.0. Ordinary API
keys and credit purchases do not override the terms' permanent-mirroring, automated-cursor, and
AI-training prohibitions. ALOC can be reconsidered only after a signed bespoke bulk-export and
AI-training agreement documents both the permitted Muta uses and ALOC's authority over the
underlying exam content.

## Frozen warehouse recipe

| Allocation | Rows | Default status |
|---|---:|---|
| Original Muta verified STEM | 1,085,000 | native eligible candidates |
| DeepMind Mathematics, pinned train-regime generation | 1,052,000 | native eligible candidates; module holdout respected |
| TemplateGSM, conservatively filtered and capped per template | 350,000 | audit required |
| QASC train anchors | 6,500 | audit required; upstream validation/test sealed |
| GSM8K train anchors | 6,500 | audit required; upstream test sealed |
| **Total** | **2,500,000** | candidate warehouse, not training set |

The proposed first SFT view is 300,000 rows: 260,000 local, 20,000 DeepMind, 10,000
TemplateGSM, and 10,000 anchors. It must solve the global subject margins 50/18/14/14/4 and
pedagogy margins 40/20/20/10/10 rather than sampling warehouse proportions. Audit-gated rows are
not selectable without immutable exact-row approvals. This means the proposed view requires at
least 20,000 individual approvals: 10,000 TemplateGSM, 5,000 QASC, and 5,000 GSM8K. Rejections
increase the number of decisions and trigger deterministic ranked refill batches.

The TemplateGSM allocation was reduced from 430,000 after the first complete warehouse exposed
publisher-supplied reasoning with exact arithmetic contradictions, unsupported targets, and float
artifacts. A pinned-source, no-code-execution audit showed that 350,000 conservative candidates
remain practical after filtering. Entire templates with any high-confidence semantic defect are
quarantined, and the displaced 80,000 rows are replaced with independently recomputed original
Muta STEM rows. The rejected first warehouse remains failure evidence and is not a training input.

The release build must not depend on a long-lived remote TemplateGSM stream. It requires
`--templategsm-snapshot` and authenticates the pinned local snapshot before creating the output
directory: exactly 2,000 JSONL files across the `0000-0999` and `1000-1999` path ranges, exact
template IDs 0–1999, 2,403,438,064 aggregate data bytes, inventory SHA-256
`9100d9daa8214a5018124e2e44dc1ee0378ecd0a992f4c450430d76f95801132`, and README SHA-256
`20b70e0f0d41021e54e4a73b1972fde7f6355f405bd67eef00472e4ce711ba7a`. The inventory folds
`relative-path`, byte count, and per-file SHA-256 in lexicographic relative-path order within the
first range and then the second. Materialization uses the local streaming JSON builder in that
canonical input order, archives the snapshot README as source evidence, and records that no
network was used for TemplateGSM rows. A complete post-materialization rehash must match the
preflight receipt before a manifest can be issued.

## Implementation and evidence

1. Archive exact executable code, schema, recipe, registry, dependency input and full hash-locked
   dependency graph, Muta licence, and local holdout source files inside every build.
2. Pin and archive licence/readme/source-card evidence for each acquired external source. Validate
   the DeepMind checkout revision and require a completely clean worktree. For TemplateGSM, use
   the authenticated snapshot README rather than refetching source evidence during release.
3. Build an exact holdout index from local judge/STEM/metadata prompts plus upstream validation/test
   and AfriMGSM prompts before accepting external rows.
4. Generate 30 active original curriculum families across five tutoring modes. Regenerate the
   entire problem, prompt, completion, answer, metadata, identity, and canonical source-task hash
   during validation. Keep five evaluation-shaped prototypes quarantined at zero rows.
5. Apply exact normalized, mathematical-equivalence-aware five-gram, and structured numerical-core
   contamination guards. Reject cross-source canonical-task collisions.
6. Attach exact Qwen2.5 chat-template token counts at the pinned tokenizer revision; reject instead
   of truncate above 1,024 tokens.
7. Stream to `.partial`, fsync, atomically promote complete shards, hash every shard, and issue a
   manifest only when every requested allocation is met. Any touched failed build gets
   `FAILED.json` and no valid manifest; resume is deliberately unsupported.
8. Assign TemplateGSM templates and DeepMind modules wholly to train or `template_holdout`.
   Preserve local families and singleton QASC/GSM8K anchors as train-pool candidates while sealing
   all official upstream holdouts.
9. Revalidate every shard and row before deterministic review sampling. Support source filters so
   cluster audits do not explode on singleton anchors.
10. Select SFT rows only through a deterministic selector that verifies the warehouse, requires
    valid exact-row approved decisions plus rubric artifacts for ineligible rows, preserves hashed
    rejected decisions without authorizing them, enforces
    source/subject/pedagogy quotas and
    external-template caps, and caps variants grouped by canonical source-task hash.
11. Materialize external audit/refill batches deterministically before review, using the same
    train-only restriction, source-task cap, TemplateGSM cap, and seed-based rank as selection.
    Continue through the ordered candidate stream until the three approval quotas are full;
    statistical diagnostic samples do not authorize rows.
12. Mark the artifact explicitly as a candidate warehouse, publish joint source × split ×
    eligibility counts and source-specific verification semantics, and never infer train-usable
    volume from marginal eligibility counts.

## Verification gates

- Unit/property suite: all local families and pedagogies, full-record regeneration, schema,
  identity, licence/status/split gating, answer visibility, notation normalization, grouped
  numbers, holdout collision guards, sharding/failure receipts, sampler tamper detection, and
  oversized-source preflight. TemplateGSM snapshot tests cover same-size tampering, missing and
  extra files, wrong path ranges, canonical load order, pre-output failure, and manifest receipts.
- Capacity: exhaustively prove local 1,085,000-row capacity; exhaust QASC/GSM8K train splits;
  measure filtered TemplateGSM template yield; prove the DeepMind seed stream cannot wrap at target
  volume.
- Determinism: compare independent local builds byte-for-byte; for DeepMind, compare fresh
  subprocess digests under different hash seeds and verify the checkout stays clean across
  easy/medium/hard imports.
- Mixed smoke: materialize all five enabled sources with exact tokenization, remote holdouts,
  archived source evidence, zero invalid rows, and zero cross-source canonical collisions.
- Full build: exactly 2,500,000 rows, no `.partial`/`FAILED.json`, exact requested/source/shard
  totals, reproducible aggregate fingerprint, no split-crossing semantic cluster, and no protected
  source content.
- Review packs: active local topic × pedagogy coverage plus targeted DeepMind module,
  TemplateGSM template, and anchor source/topic/difficulty diagnostic samples; separately, an
  selector-equivalent audit/refill batches until 20,000 exact rows are approved.
- Fresh adversarial review: another context independently verifies code, shard hashes/counts,
  records, tokenization, source evidence, leakage controls, and final claims.

## Training handoff

After user review, freeze the approved SFT receipt set and materialize the 300,000-row view in the
separate fine-tuning task. That task must preserve exact base/adaptor/merge/quantization hashes,
scripts and logs, and full unedited outputs for at least two identical prompts against the base and
each tuned candidate, as required by Gate 2.

## Completed v7 evidence (16 September 2026)

- Warehouse: `data/muta-stem-v2-warehouse-20260916-v7`, exactly 2,500,000 rows in 100 × 25,000-row
  shards; fingerprint `0197679d767281c26537e388b6c1f703bdfcf032e02f19b1b2d2b435bf572941`;
  manifest SHA-256 `3743901055c075a9ec8fd75414343620608c0426649bc4aa95f6b7211a5cf0e4`.
- Independent shard check: all 100 SHA-256 values matched; no partial or failure marker remained.
- Exhaustive review-pack rescan: all 2.5M rows and archived schema/registry bindings passed; 20,000
  audit-gated exact rows were materialized, but no approval decision was issued.
- Independent split replay: 2,453,388 train and 46,612 template-holdout rows, 13,964 semantic
  clusters, zero split mismatch, and zero cluster overlap.
- Balanced local review sample: 750 rows, five in every one of 150 topic × pedagogy cells; SHA-256
  `bc17072e0aec58ce7234d73ad543abc37a2a7a0dbcdbde2eeec9453206d3cb8b`.
- ALOC: zero requests, zero credits consumed, zero rows stored. User-supplied credentials were not
  tested, printed to logs, written to disk, or committed.
