# Full-data winner-test inventory

Date: 18 September 2026. Status: read-only inventory and implementation handoff.
The proposed fresh 2,000-item battery has **not** been materialized, validated,
frozen, or run. This document does not change the winner-test design, declare
any candidate clean, or authorize use of an existing development set as a final
test. No candidate outputs were generated during this inventory.

All paths below are repository-relative unless explicitly absolute. Counts are
from existing manifests, except the WAEC JSONL line count was also checked.
This inventory did not rehash every multi-gigabyte shard or establish semantic
disjointness. Future validation must do those checks against exact input bytes.
No private question, answer, credential, or student text is reproduced here.

## Already-local material

| Artifact | Recorded coverage | Use in the proposed workflow |
|---|---|---|
| `data/muta-stem-v2-warehouse-20260916-v7/manifest.json` and its 102 listed shards | 2,500,350 rows: 1,085,000 local STEM; 1,052,000 DeepMind mathematics; 350,000 TemplateGSM; 6,500 GSM8K; 6,500 QASC; 350 private exam rows | Main exclusion corpus; stream in place |
| `data/muta-stem-v2-sft-300k-quality-first-20260917-v1/manifest.json` and listed shards | 300,350 selected training rows | Exact training exclusion and lineage |
| `provenance/dataset/round2-dev-5000/dev.jsonl` and `manifest.json` | 5,000 already-used development rows: 4,667 local STEM and 333 DeepMind | Exclude from the fresh battery |
| Warehouse rows marked `template_holdout` | 37,812 DeepMind and 8,800 TemplateGSM rows | Potential separately labelled secondary generator-OOD test, not the primary fresh test under the current whole-warehouse exclusion rule |
| `corpus/waec/questions.jsonl` and `manifest.json` | 1,906 rows; manifest marks 382 complete, 1,357 needing visual review, and 167 incomplete | Additional source-exclusion inventory, not a ready clean evaluation bank |
| `model-development/finetune/muta_dataset_v2/source_registry.json` | Source revisions, status and licence metadata | Provenance reference, not question content |

The WAEC corpus covers mathematics, physics, chemistry and biology. Its `raw/`
and `assets/` directories were absent at inspection, so references to missing
visual assets cannot be treated as usable questions. The 350 appended exam
rows remain private; do not republish their text in evaluation reports.

Known/reused local prompt sources to exclude or report only as regression suites:

- `bench/judges_prompt_suite.py`
- `bench/stem_prompt_suite.py`
- `bench/live_prompt_battery.py`
- `bench/eval_items.json`
- `bench/submission/metadata.json`
- `muta-adtc-2026/metadata.json`, when present
- Archived counterparts under the warehouse's `provenance-holdouts/` directory
- Prompt-bearing records in prior benchmark/evaluation artifacts, after a
  bounded inventory identifies the actual previously used source IDs/prompts

The current pilot judges10/STEM100 results remain known regression evidence,
not an independent unseen test. Judges10 includes a repeated prompt.

## Public-source receipts are not local test rows

The warehouse manifest records prior exclusion receipts for these pinned public
splits:

| Source | Recorded raw prompt counts |
|---|---:|
| GSM8K test | 1,319 |
| ARC-Easy validation / test | 570 / 2,376 |
| ARC-Challenge validation / test | 299 / 1,172 |
| QASC validation / test | 926 / 920 |
| AfriMGSM test | 250 per language, 18 configurations |

The inspected Hugging Face cache locations under
`/Users/elijahnelson/.cache/huggingface/` contain README metadata and lock files
for these sources, not cached Arrow/Parquet/JSONL split contents. The warehouse
archives local prompt-suite sources, but public receipts retain counts and
hashes rather than the public question/answer rows. Do not infer a usable
offline public test dataset from these receipts.

`model-development/finetune/muta_dataset_v2/adapters.py` contains
`public_evaluation_holdouts()`, which retrieves pinned public prompts. Calling
it is not an offline materialization method and would require source access.
Public reused benchmarks must be labelled separately from newly authored items;
unknown base-pretraining exposure remains unknown in either case.

## Reusable exclusion and evaluation tooling

| File / interface | Existing capability | Limit |
|---|---|---|
| `model-development/finetune/muta_dataset_v2/core.py`: `normalize_text`, `normalized_sha256`, `word_ngrams`, `HoldoutIndex` | Maths-preserving normalization, exact matching, five-gram Jaccard/containment matching; default threshold 0.82 | Lexical near-duplicate screening is not semantic-paraphrase or family-disjointness proof; current comparison returns maximum similarity rather than a complete match ledger |
| Warehouse row fields `contamination.source_task_sha256`, `normalized_prompt_sha256`, `provenance.semantic_cluster_id` | Task/prompt identities and source-specific family labels | Source-specific labels vary in meaning; singleton IDs are not independent semantic families |
| `model-development/finetune/campaign_io.py`: `verify_dataset_manifest` | Fail-closed shard existence, size, SHA-256, row-count and fingerprint checks | Integrity validation does not establish evaluation independence |
| `model-development/finetune/build_round2_dev.py` | Streaming, deterministic stratified selection and exact selected ID/task/prompt exclusion | Current development builder does not establish generator-family disjointness |
| `model-development/finetune/muta_dataset_v2/generators.py` | Deterministic problems and independently recomputable numerical answers | Its 30 formula families already occur in the warehouse; a new seed or changed operands is not a new family |
| `bench/round2_candidate_eval.py` | Frozen model identity, exact raw outputs, request/runtime receipts and output integrity | Currently accepts the hard-coded `judges` and `stem` suites; needs a reviewed frozen external-suite loader for a new battery |

Existing tests in `model-development/finetune/test_muta_dataset_v2.py`,
`test_muta_dataset_v2_selector.py`, `test_build_round2_dev.py` and
`bench/tests/test_round2_candidate_eval.py` provide useful normalization,
containment, identity, shard-integrity and evaluator regression fixtures.

## Gaps that must stay explicit

1. **No balanced fresh battery yet.** Existing local material does not establish
   500 usable independent examples in each proposed stratum, especially science
   written/tutoring. New independently verified items/families or appropriately
   labelled source acquisitions are still needed.
2. **Family coverage is narrow.** The warehouse records 30 local formula
   families, 56 DeepMind module clusters and 878 TemplateGSM clusters. Generating
   more samples from those same families cannot satisfy the current strict
   whole-warehouse family-exclusion design. This is not a reason to silently
   redefine a family as an individual row.
3. **Warehouse holdouts are still warehouse members.** The 46,612 existing
   template/module holdout rows may be useful as a secondary test, but using
   them as the primary fresh test would require an explicit design change.
4. **Old incumbent data is not locally available in the inspected locations.**
   `provenance/lineage/incumbent-recovery/training-manifest.json` points to
   `data-metric-licensed-mcq/train.jsonl` and `validation.jsonl`.
   `model-development/finetune/metric-licensed-mcq-dataset-manifest.json`
   retains hashes and source revisions for 10,756 training and 566 validation
   rows from ARC-Easy, ARC-Challenge and QASC. Those original row files were
   not found in the inspected local dataset locations. Recover an existing
   exact remote artifact if available; otherwise disclose the missing exact
   retrospective exclusion coverage. A source receipt alone is insufficient.
   **Update at 21:04 UTC:** both exact files were found on Oracle under
   `/home/ubuntu/muta-finetune/data-metric-licensed-mcq/`; their hashes and
   10,756 / 566 row counts match the prior manifest. No rows were copied.
   See `2026-09-18-incumbent-holdout-coverage.md`. Actual candidate comparison
   and family review remain outstanding.
5. **Paraphrases require more than hashes.** Five-gram screening and existing
   family labels help, but semantic-family ambiguity needs independent review.
   Define family granularity before outcomes, not after seeing model scores.
6. **Source and grading gates remain.** Preserve source/licence restrictions,
   separate generated answers from publisher answers, and require independently
   verified references/rubrics. Do not call agent review human review.

## Recommended next bounded implementation

Build an **audit-only candidate-battery validator** before running finalists:

1. Define a small candidate schema containing stable item ID, stratum, topic,
   difficulty, tutoring mode, family ID, source ID/revision, prompt, verified
   answer, rubric, and answer-review evidence. Keep private source text private.
2. Read exact manifest-listed shards in place. Verify input bytes/counts and
   capture input fingerprints; fail closed on missing or changed inputs.
   Avoid copying either large dataset or creating a full text-search mirror.
3. Index only the small candidate pool in memory. Stream the warehouse,
   selected set and development set against candidate exact/task fingerprints
   and lexical signatures. Retain compact match receipts with source row IDs,
   hashes, match reason and similarity, not duplicated private question text.
4. Check source-specific generator/template family identities separately from
   lexical similarity. Add all known prompt-suite exclusions and disclose
   unavailable incumbent inputs rather than silently treating them as clean.
5. Test changed numbers, signs, fractions, formatting-only changes, paraphrases,
   repeated templates and sibling variants. Independently adjudicate ambiguous
   family matches and review the exclusion logic adversarially.
6. Emit a compact availability/exclusion report with exact input hashes,
   candidate counts per stratum/family, unresolved cases and coverage gaps.
   This is an audit result, not permission to claim semantic independence.

After this validator is reviewed, materialize and independently verify new
items, resolve quotas and independent family counts, assess statistical power,
and freeze the executable battery/rubrics/decision rules before finalist
inference. Update the evaluator through a reviewed external-suite path only
after that freeze can be bound to exact bytes. Do not generate candidate model
outputs during inventory, battery construction or answer-key review.

## Bounded coverage updates — 19 September

These are source-role inspections, not primary-item admission. The independent
battery still has **zero admitted items/families**; no finalist inference is
authorized by these updates.

- [Incumbent source screen](2026-09-19-m02-incumbent-counterexample-screen.md):
  the exact 10,756 training and 566 development rows were reverified and scanned
  remotely without corpus copies. Broad selectors found 671 / 30 positives;
  the train locator cap saturated. Lexical screening does not clear the family.
  The separate [43-pair neighbour review](2026-09-19-m02-incumbent-neighbour-review.md)
  covers every non-coefficient-only match, with chemical-conservation adjacency
  unresolved and 658 coefficient-only positives not semantically reviewed.
  The later [four-pair boundary decision](2026-09-19-m02-conservation-boundary.md)
  distinguishes shared operations from the indispensable M02 parameter branch
  in the retained pairs only. Missing choices/source variants remain unresolved.
- [Private-source neighbour review](2026-09-19-m02-private-neighbour-review.md):
  both final warehouse private shards (350 rows) were reverified. Sixteen
  selected prompt/answer pairs were semantically inspected and independently
  cross-reviewed in that earlier limited pass.
  Abstract matrix controls expose RHS-only parameters and identically singular
  cases that a coefficient-word search can miss. No private wording is copied.
  The later [complete retained-text review](../../provenance/evaluation/winner-battery/private-m02-review/README.md)
  covers all 350 prompt/completion/answer triples, with 45 independent
  cross-reads: 347 have no observed M02 graph, and three retain unresolved
  context. This closes the unread stored-text gap only; originals, other
  source families and whole-family independence are not cleared. The preserved
  cross-review disagreement changed one WAEC row to unresolved; no answer was
  certified and no training row changed.
- [Gate 2 evidence checklist](../../provenance/GATE2_CHECKLIST.md): present
  adapters, logs, curves, dataset proof and export hashes are indexed separately
  from rights/access, submission and target-CPU qualification gaps.
- [Statistical primitives](2026-09-19-winner-statistical-primitives.md):
  synthetic-only development of globally paired family weights, the four-stratum
  estimand, 26 contrast orientations and draft threshold predicates. This is not
  an interval procedure, calibrated inferential protocol, benchmark freeze or
  promotion authority; no real model scores enter this implementation work.
