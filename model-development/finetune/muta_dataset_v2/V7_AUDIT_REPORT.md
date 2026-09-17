# Muta STEM candidate warehouse v7 audit report

Audit date: **16 September 2026**

## Verdict

**GO for candidate-warehouse review. NO-GO for immediate SFT training.**

The completed artifact is a diversity/audit warehouse. It is not the 300,000-row training view,
and its audit-gated rows are not authorized merely because they appear in the warehouse.

This is the historical verdict for the warehouse at its 16 September audit. On 17 September, the
external audit rejected all 20,000 audit-gated review rows fail-closed and the replacement
quality-first 300,000-row train view was materialized and independently passed its exact-artifact
integrity audit. See `EXTERNAL_20K_AUDIT_REPORT.md`; the warehouse itself remains an audit pool and
must not be used directly for training.

## Bound artifacts

| Artifact | Receipt |
|---|---|
| Warehouse | `data/muta-stem-v2-warehouse-20260916-v7/` |
| Warehouse rows | 2,500,000 |
| Shards | 100 × 25,000 rows |
| Warehouse fingerprint | `0197679d767281c26537e388b6c1f703bdfcf032e02f19b1b2d2b435bf572941` |
| Warehouse manifest SHA-256 | `3743901055c075a9ec8fd75414343620608c0426649bc4aa95f6b7211a5cf0e4` |
| Local review sample | `data/muta-stem-v2-review-local-750-20260916-v7.jsonl` |
| Local sample SHA-256 | `bc17072e0aec58ce7234d73ad543abc37a2a7a0dbcdbde2eeec9453206d3cb8b` |
| Local sample manifest SHA-256 | `5d1a1ece883679d6547260ac99f9503ddc30422af8af11acaefd9e28fe08e2ba` |
| External review pack | `data/muta-stem-v2-external-audit-review-20k-20260916-v7/` |
| External review-pack manifest SHA-256 | `c64a3e24e046fe61218b8d49ac082d927ddb6ff33cb9249782ac7977e4326415` |

## Structural and provenance results

- Exact source quotas: 1,085,000 Muta original; 1,052,000 DeepMind Mathematics; 350,000
  TemplateGSM; 6,500 QASC; 6,500 GSM8K.
- All 100 shard SHA-256 values independently matched; no `.partial` or `FAILED.json` remained.
- All 35 checked provenance, executable-code, and source-evidence receipts matched.
- The authenticated TemplateGSM receipt binds 2,000 files, 2,403,438,064 data bytes, source
  revision `0c8ed6b60fea0a84f25ddb1b8b761db695df2e19`, and inventory SHA-256
  `9100d9daa8214a5018124e2e44dc1ee0378ecd0a992f4c450430d76f95801132`.
- The clean DeepMind checkout is pinned to
  `427f45075f84b8b9774950196ad63867ca20ffb3`, and its cross-hash-seed determinism probe passed.
- Exact Qwen2.5 tokenization spans 50–550 tokens, averages 135.863538 tokens, and reports zero
  truncated rows against the 1,024-token limit.
- Independent split replay over every row found 2,453,388 train rows, 46,612 template holdouts,
  13,964 semantic clusters, zero split mismatches, and zero clusters crossing splits.
- Training disposition is 2,099,188 natively eligible train candidates, 354,200 audit-required
  train candidates, and 46,612 non-training holdouts.

## Review artifacts

The authoritative review-pack materializer rehashed all warehouse shards again and revalidated all
2.5M records against the archived schema and source registry. It selected 20,000 unique train-only,
audit-required exact rows:

- 10,000 TemplateGSM;
- 5,000 QASC;
- 5,000 GSM8K.

The pack has unique canonical source tasks, caps TemplateGSM at no more than 23 selected rows from
one external template, has an empty decision ledger, and states `authorizes_training=false`.

The local review sample contains exactly five records in every one of 30 topic × five pedagogy
cells. All 750 rows passed schema validation and deterministic local answer regeneration and were
byte-equivalent to their warehouse records.

## Fresh adversarial semantic findings

- One worked solution from every one of the 30 local formula families plus additional pedagogy-mode
  checks was correct in the review.
- One row from each of 56 DeepMind modules was mathematically sound in the sample, although many
  answers are terse and Python-styled rather than tutor-like.
- Ten evenly spaced GSM8K review rows were correct.
- TemplateGSM still contains awkward or incoherent entity substitutions and some ambiguous story
  operations despite the high-precision arithmetic filter. One example requiring rejection is
  `muta2_9e378fbff726f9da29290501`.
- QASC retains publisher wording and answer ambiguity. One example requiring review/rejection is
  `muta2_3e980c5b7b27e6803ef57ef8`, whose keyed answer competes with other plausible choices.

These external defects do not invalidate the warehouse because every TemplateGSM, QASC, and GSM8K
row remains `verification.training_eligible=false`. They do block approval of affected exact rows.

## Protected-source result

ALOC contributes zero rows. The v7 archived registry predates the later ALOC rights review, while
the current live registry records ALOC as `prohibited_without_permission`. No authenticated ALOC
request was made, no credit was consumed, and no user-supplied API credential was used, logged,
written to disk, or committed. `ALOC_PERMISSION_REQUEST.md` defines the bespoke rights needed
before reconsideration.

## Post-audit requirements before fine-tuning

The earlier proposal to human-review/refill until 10K TemplateGSM, 5K QASC, and 5K GSM8K approvals
is superseded by the 17 September 2026 fail-closed audit. Fresh adversarial checks falsified
provisional approvals, so quota-filling those sources would lower the quality bar.

1. Preserve the 20,000 immutable exact-row rejection receipts bound to the warehouse fingerprint,
   content hashes, honest model-assisted review methods, and frozen rubric.
2. Use zero TemplateGSM, QASC, and GSM8K rows in this SFT version; preserve their +15K mathematics,
   +5K integrated-science, +15K worked-solution, and +5K concise-answer margins through the
   documented capacity-safe four-cell redistribution across a balanced all-25-cell native matrix.
3. Materialize the separate 300K SFT view through `select_sft.py`; never train on the warehouse.
4. Exclude every `template_holdout` row and preserve all official/judge/upstream evaluation sets.
5. Run the unmodified base and each tuned candidate on at least two identical prompts and retain
   full outputs plus adapter, training, merge, conversion, quantization, and model hashes for Gate 2.
6. Keep ALOC at zero unless a signed agreement expressly authorizes bulk export, permanent storage,
   model training/evaluation, derived use, and the intended adapter/model-weight distribution.
