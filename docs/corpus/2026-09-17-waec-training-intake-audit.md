# WAEC/Cheetah corpus training-intake audit

Date: 2026-09-17

## Decision

Keep all 1,906 newly normalized rows outside the SFT dataset and outside any
shipped RAG index. Preserve the approved 300K v1 dataset unchanged.

This is not a claim that the material has no educational value. The corpus is
useful as a private study snapshot and as a source of non-expressive,
independently normalized curriculum signals. It fails two independent SFT
gates today:

1. neither source has supplied a written model-training and artifact-handling
   grant; and
2. no source answer has been independently verified, while direct inspection
   found missing, truncated, mispaired, and incorrect answers.

The reproducible, content-free audit artifact is
`data/muta-corpus-training-intake-audit-20260917-v2`.

The top-level `corpus/chunks.jsonl` is a separate, pre-existing RAG reference
file rather than an instruction/answer dataset. It contains 25 unique chunks
(13 mathematics, 5 physics, 4 chemistry, 3 biology) and has SHA-256
`b1fd5cd2f7c044b40d23b3db94105714bde35f425981541ccf1eaa4637992f91`.
It remains in the retrieval path and was not duplicated into SFT; converting 25
formula notes into repeated training pairs would add little task diversity and
would blur their currently incomplete source/licence provenance.

## Immutable input anchors

| Input | SHA-256 |
|---|---|
| `corpus/waec/questions.jsonl` | `80763c51494653901a996d7735253a07e810b1e0f7c5debd50f92170237d0509` |
| `corpus/waec/questions.json` | `021f0dcf03306ad8c5a6e5d8e3e2b38d3e0fc8cbf805cc790c179ed49fc65d2e` |
| `corpus/waec/schema.json` | `5d6885c18d7cbc05521f39be2c7cdb8e7178eaa1f3d3143dbf45939eddf507c1` |
| `corpus/waec/manifest.json` | `3bf4977cfb75108837dd649dc3914536f782d7ba42480e4c80eb38a3432b9b6e` |

The audit inventoried 10,371 corpus files. The source manifest's final coverage
correctly reports 1,906 rows, but `sources.waec.records` reports 1,522 while the
normalized data contains 1,454 WAEC HTML rows. The audit records this 68-row
pre-deduplication/counting discrepancy rather than silently correcting the raw
source manifest.

## Corpus condition

| Measure | Count |
|---|---:|
| Total schema-valid rows | 1,906 |
| WAEC HTML rows | 1,454 |
| Cheetah PDF rows | 452 |
| Complete | 382 |
| Needs visual review | 1,357 |
| Incomplete | 167 |
| Publisher-labelled answer | 1,703 |
| Missing answer | 203 |
| Independently verified answer | 0 |
| Rows with extraction warnings | 1,524 |
| Rows with assets | 921 |
| Asset references | 2,528 |
| Unresolved asset references | 110 |

All 2,418 locally resolved asset references exist and match their recorded
SHA-256 values. Asset integrity does not establish permission to train on the
asset, and 110 references have no local payload.

The answer fields do not provide independent corroboration: every one of the
1,642 non-empty `worked_solution` values is byte-identical to its
`marking_scheme`. Only 55 of the 124 records labelled multiple-choice have four
non-empty option entries with unique labels and an answer label present among
those labels; only 52 also have four unique option texts.

A conservative mechanical funnel leaves at most 285 unique, self-contained
records before source permission and before full semantic review. That is only
0.095% of a 300,000-row SFT artifact and is not a reason to weaken the
provenance or correctness gates.

## Semantic answer findings

A deterministic diagnostic review covered 40 complete WAEC rows (10 per
subject) and 20 Cheetah rows. It found 17 definite defects in 60 reviewed
records. This was a diagnostic sample, not a population estimate.

Examples are recorded by ID without reproducing the protected question text:

- `waec-8019b8f3cfa657dec84c75ea`: the stored response belongs to a different
  genetics/chromosome problem.
- `waec-41328f0290fccb48592cab1d`: the stored response covers only one of three
  required sections.
- `waec-67172ddff8719c05905d99b8`: the stored response omits the logarithm
  section.
- `waec-828712171e1a5ec219939d27`: the source stops the repeated depreciation
  calculation three years early. Independent exact-decimal recomputation gives
  `900000 × 0.70 × 0.78^6 = 141875.74844352`, hence ₦141,900 to the nearest
  hundred—not the stored ₦299,000.
- `waec-af994cd547cdf7752183c713`: the stored lead-acid charging response swaps
  the gas/electrode assignments; oxygen belongs at the positive lead-dioxide
  electrode and hydrogen at the negative lead electrode.

These findings prove that `answer_status=published` means “attributed to the
publisher,” not “independently correct.” No correction above is admitted to
training because its source row remains blocked at the rights gate.

## PDF and visual audit

The corpus contains 28 physical PDFs but only 14 unique payloads: seven years
(2019–2025), each with one question and one answer PDF, duplicated once in the
HTTP cache. The unique set has 607 pages and 22,924,135 bytes. Every page has a
non-empty text layer, but mathematical completeness is poor:

- all 452 PDF-derived rows require visual verification;
- 15 have blank question text;
- 87 refer to a diagram, graph, table, or figure but retain no asset;
- the 2025 mathematics layer drops expressions and options, and all 61 rows
  lack a worked solution;
- the 2025 answer PDF contains two literal math-rendering error placeholders;
- fractions, powers, subscripts, vector diagrams, option boundaries, and page
  continuations are frequently damaged by plain-text extraction.

The PDFs therefore require page-level, math-aware visual extraction followed
by independent solving. Text-layer presence alone is not a quality signal.

## Rights and provenance decision

The official [WAEC e-learning archive](https://www.waeconline.org.ng/e-learning/)
marks its pages as all rights reserved and provides study access but no model-
training licence. [Cheetah's terms](https://cheetahwaec.com/terms) reserve its
original explanations and leave third-party rights with their owners; Cheetah
alone cannot clear the underlying WAEC material. Nigeria's
[Copyright Act 2022](https://www.copyright.gov.ng/wp-content/uploads/2023/04/CopyrightAct2023FinalPublication1.pdf)
reserves reproduction and adaptation and provides context-dependent fair-
dealing exceptions, not a blanket whole-corpus ML licence.

Current decisions:

| Source | SFT | Private internal review | Shipped RAG |
|---|---|---|---|
| WAEC e-learning | Blocked pending written WAEC grant | Conditional and access-controlled | Blocked |
| Cheetah PDFs/explanations | Blocked pending Cheetah plus WAEC/rightsholder grants | Conditional and access-controlled | Blocked |

Any permission request should expressly cover automated retrieval/OCR,
storage, evaluation, model training, derived datasets, adapter/weight
distribution, competition use, later distribution, territory, duration, and
attribution.

## Safe coverage contribution

The audit emits hashes and independently named, high-level topic/skill/error
labels only. It does not emit source questions, answers, solutions, marking
schemes, examiner prose, or media. The aggregate signals confirm that the
current native generators are reliable but narrow.

Highest-priority independently authored additions are:

- mathematics: circle arcs/sectors, trigonometric heights and bearings, set
  cardinality, coordinate geometry, grouped statistics, and logarithmic
  equations;
- physics: constant-acceleration motion, calorimetry, lenses/mirrors,
  series-parallel circuits, radioactive half-life, and transformers;
- chemistry: empirical formulae, gas-law transformations, pH,
  electrolysis stoichiometry, and reaction energetics;
- biology: food-chain energy transfer, expanded genetic probability, and
  capture-recapture sampling.

Descriptive biology, qualitative chemistry, classification, nomenclature, and
practical-method rubrics need an independently authored fact/rubric bank and
dual subject review rather than bulk generated prose.

## Answer and correction admission gate

Before any future source row enters SFT:

1. resolve every visual and recover every subpart;
2. independently solve the item rather than accepting a publisher/model key;
3. verify exact arithmetic, units, ranges, rounding, and option membership;
4. record the original-answer hash, corrected answer, correction reason,
   verifier version, and reviewer decisions;
5. require two reviewers for descriptive or practical rubrics;
6. reject any unresolved disagreement or missing answer;
7. run exact, normalized, fuzzy, OCR-aware, canonical-task, and holdout leakage
   checks; and
8. issue `training_eligible=true` only after both the rights and correctness
   gates pass.

## 300K result

The existing artifact was rescanned in full:

- rows: 300,000;
- all 12 declared shard hashes and row counts pass;
- dataset fingerprint:
  `ee1a31f2cfef256fda86166f6d420811c27ae0656728b7ef582327074e82340e`;
- manifest SHA-256:
  `f3c5c6f66a194603cdc9f3e05a96b09338fc9c90437b95689014c1adb167eabe`;
- new source rows merged: 0;
- unanswered or unverified rows admitted: 0.

The correct refinement decision for this intake is therefore to preserve the
300K v1 unchanged and use the safe aggregate gap analysis to build a separately
versioned, independently authored future candidate.

## Reproduction

```bash
.venv/bin/python corpus/audit_training_intake.py \
  --corpus-dir corpus/waec \
  --source-registry model-development/finetune/muta_dataset_v2/source_registry.json \
  --sft-dir data/muta-stem-v2-sft-300k-quality-first-20260917-v1 \
  --output-dir data/muta-corpus-training-intake-audit-20260917-v2
```

The command refuses to overwrite an existing output directory.
