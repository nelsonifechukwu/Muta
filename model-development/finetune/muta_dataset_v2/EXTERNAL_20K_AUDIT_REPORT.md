# External 20K review and quality-first SFT audit

Audit completion date: **17 September 2026**

## Verdict

**GO for the 300,000-row dataset artifact to enter the fine-tuning workflow.**

This is a data-readiness verdict, not evidence that a fine-tuned model is better than its base.
Training, identical-prompt base/candidate comparisons, full-output retention, and the remaining
Gate 2 model provenance must still be completed in the fine-tuning task.

The external review was deterministic and model-assisted. It was not an independent human
row-by-row attestation. Because adversarial review falsified provisional approvals at source level,
the final policy rejects all 20,000 external rows fail-closed instead of silently treating uncertain
rows as correct.

## Frozen external review disposition

| Source | Rows reviewed | Provisional source result | Final training disposition |
|---|---:|---:|---:|
| TemplateGSM | 10,000 | 3,131 pass; 6,869 reject | 10,000 rejected |
| QASC | 5,000 | 0 pass; 5,000 reject | 5,000 rejected |
| GSM8K | 5,000 | 4,836 pass; 164 reject | 5,000 rejected |
| **Total** | **20,000** | — | **20,000 rejected** |

TemplateGSM and GSM8K had provisional row decisions, but fresh adversarial samples exposed false
approvals. QASC lacked exhaustive semantic evidence and contained ambiguity/quality defects. A
known-invalid GSM8K reserve row was also approved by the refill checker. These failures invalidate
source-level admission for this version even where an individual provisional decision said pass.

No reviewed source record was edited in place. The 20,000 planned slots were replaced with native,
programmatically verified rows while preserving the intended subject and pedagogy margins. The
one-row-per-canonical-task cap forced a capacity-safe 243-row paired redistribution:

- mathematics/worked solution: +14,757;
- mathematics/concise answer: +243;
- integrated science/worked solution: +243;
- integrated science/concise answer: +4,757.

### Bound audit evidence

| Artifact | SHA-256 |
|---|---|
| Frozen 20K review-pack manifest | `c64a3e24e046fe61218b8d49ac082d927ddb6ff33cb9249782ac7977e4326415` |
| Final 20K decision ledger | `2b0b60a70bf80a14824b9e2db3376ae9b5d1e26514e1bb024c7c5e395123a5af` |
| Final-ledger manifest | `907d5b8d2ad8f56a1fe05d1744916723d24a328b285e9c5e8253110a874ecb9c` |
| Final-ledger report | `b7fd9a3a8fb9068fb0f577cb6351d22ec6ff53bc257b698930c7153604fd2a9f` |
| Original-order rejection receipts | `f1b9846b6203b0fe52d4cc6810a01ee1be79a188a4f109ae2cb69b2201ca5f50` |
| Rejection-receipt manifest | `30a1861912bd602fe96eb1ec0cb50df6482a7b71ec3e8d1547e993d9609c53ba` |
| Frozen audit rubric | `3da5ff45246d09320ecf3caf5fd6668afac1b71f53642dcef3e575fc4bd0d4b3` |
| Approval-receipt schema | `f4119f7f01872a2ecdac9d41cafcad9b55db61493eea5d4141231f61671f1634` |

The selected artifact archives a canonical receipt ordering whose SHA-256 is
`20a3aeffa0aaa4033c21fc62f3556c2b32994022f4a7aa6cd502bb146224a78f`; its manifest separately
retains the original-order input hash above. The content-addressed receipt set is the same: 20,000
unique record decisions, all rejected, with zero selected-row use.

## Final 300K SFT artifact

| Property | Result |
|---|---|
| Directory | `data/muta-stem-v2-sft-300k-quality-first-20260917-v1/` |
| Size on disk | approximately 810 MiB |
| Rows | 300,000 |
| Shards | 12 × 25,000 rows |
| Dataset fingerprint | `ee1a31f2cfef256fda86166f6d420811c27ae0656728b7ef582327074e82340e` |
| Manifest SHA-256 | `f3c5c6f66a194603cdc9f3e05a96b09338fc9c90437b95689014c1adb167eabe` |
| Warehouse fingerprint | `0197679d767281c26537e388b6c1f703bdfcf032e02f19b1b2d2b435bf572941` |
| Warehouse manifest SHA-256 | `3743901055c075a9ec8fd75414343620608c0426649bc4aa95f6b7211a5cf0e4` |

### Selected counts

| Dimension | Counts |
|---|---|
| Source | 280,000 Muta verified STEM v2; 20,000 DeepMind Mathematics |
| Subject | 150,000 mathematics; 54,000 physics; 42,000 chemistry; 42,000 biology; 12,000 integrated science |
| Pedagogy | 120,000 worked solution; 60,000 exam marking scheme; 60,000 misconception correction; 30,000 Socratic hint; 30,000 concise answer |
| Split | 300,000 train |
| Authorization | 300,000 native training eligible |

The selected sources are covered by the archived attribution inventory: Muta original rows under
the repository's MIT licence and the pinned DeepMind Mathematics source evidence under Apache-2.0.
No protected exam-bank row is selected.

## Independent exact-artifact integrity check

The post-materialization audit performed a separate streaming pass over all 12 output shards and
checked the artifact rather than trusting the selector's success message. It found:

- all shard byte counts and SHA-256 values match the manifest;
- the recomputed aggregate dataset fingerprint matches;
- 300,000 parsed rows, unique IDs, and unique `source_task_sha256` values;
- exact source, subject, pedagogy, and 26 source × subject × pedagogy cell quotas;
- every row is train-only, natively training-eligible, holdout-checked, and within its recorded
  token limit;
- every `messages` value is exactly the row's user prompt followed by its assistant completion;
- zero selected IDs overlap the 20,000 rejected receipts;
- zero TemplateGSM, QASC, or GSM8K rows are selected;
- all 20,000 receipt usage counters are zero;
- 38 selected-artifact/provenance inputs match their recorded hashes; and
- no `.partial` file remains.

The independent exact-artifact verdict was **GO**, with zero failed invariants.

## Fine-tuning boundary

Use the 12 JSONL shards in this directory as the training view. The `messages` field is the
conversation-formatted SFT pair; `prompt` and `completion` are retained for transparent inspection.
Do not train on the 2.5M-row warehouse, the 20K review pack, the decision ledger, or any holdout.
Keep the manifest and the complete `selector-provenance/` directory beside the training run so the
exact consumed dataset remains attributable and reproducible.
