# WAEC complete/published quality audit

Date: 2026-09-17

## Verdict

This review found **26 content-quality-approved records** in the 382-record slice defined by:

- `content_status == "complete"`
- `answer_status == "published"`
- `extraction_warnings == []`

The approved tranche contains 17 physics, 6 chemistry, 2 biology, and 1 mathematics record. The machine-readable entries are in `WAEC_COMPLETE_PUBLISHED_APPROVED_IDS.jsonl`.

This is deliberately a small, precision-first tranche. A WAEC-published answer was treated as evidence of provenance, **not** as evidence of correctness. Every approved record received an independent subject-matter check, and the ledger records the method and evidence.

**Rights gate:** this is a content-quality decision only. Every approved record remains `training_eligible=false` and `rights_status="blocked_pending_written_permission"`. WAEC's archived pages state that copyright is reserved. This review does not authorize fine-tuning, redistribution, or inclusion in a shipped RAG corpus without written permission covering those uses.

**Post-audit private-use adjudication:** after this content audit, the project owner explicitly
directed that the exact approved rows be added to the existing local 300K and 2.5M training
artifacts for private fine-tuning, WAEC practice, and competition research. That narrower
decision is recorded separately in `corpus/waec/private-training-attestation.json`; it does not
claim publisher permission or authorize public dataset redistribution. The ledger's original
rights status and `training_eligible=false` remain preserved in each emitted row's audit history,
while operational eligibility for these two private artifacts is attributed only to the separate
project-owner adjudication.

## Bound input

| Artifact | SHA-256 |
|---|---|
| `corpus/waec/questions.jsonl` | `80763c51494653901a996d7735253a07e810b1e0f7c5debd50f92170237d0509` |
| Canonicalized 382-record audit slice | `d55923201f60d27349372bb9454c8e2674be022fbc18093dd4c547cc4afff759` |
| `corpus/waec/manifest.json` | `3bf4977cfb75108837dd649dc3914536f782d7ba42480e4c80eb38a3432b9b6e` |
| `corpus/waec/schema.json` | `5d6885c18d7cbc05521f39be2c7cdb8e7178eaa1f3d3143dbf45939eddf507c1` |
| Approved ledger | `89a45395cadca7418d37f41825aa51a02456ece7de6313729a8bf5fd10dcabf9` |

The slice hash was computed by serializing each selected source record as sorted, compact UTF-8 JSON, appending a newline, preserving source-file order, and hashing the concatenation.

## Review method

### Pass 1: deterministic screening of all 382 records

For every record, the review checked:

1. Source binding and the three selection predicates above.
2. Presence of a non-empty prompt and published solution.
3. Asset count and references to missing specimens, figures, graphs, tables, constructions, or diagrams.
4. Exact normalized prompt duplication. Normalization used Unicode case-folding and retained only alphanumeric characters.
5. Prompt contamination or answer leakage from examiner commentary, expected-response text, candidate-performance commentary, and marking instructions.
6. Obvious OCR or notation damage, including lost exponents, missing equations, HTML remnants, and corrupted units or symbols.
7. Multipart coverage: every requested part had to be answered; a record was rejected once a decisive omission was found.

All 382 records have an empty `assets` array. That does not make visually dependent questions self-contained; it makes those dependencies blockers.

### Pass 2: independent substantive verification

Publication status alone never caused approval. Candidate records that survived Pass 1 were checked from first principles:

- **Mathematics:** re-derived equations, recomputed results, substituted answers back into the original conditions, and checked every subpart.
- **Numerical physics:** recomputed with SI-unit conversion and the governing equation. The approved projectile times/speeds and magnetic-force result were independently reproduced.
- **Conceptual physics:** checked definitions against the underlying force, field, band, optics, molecular, or device model; selected only unambiguous alternatives.
- **Chemistry:** balanced reactions, checked oxidation states, solubility, indicator ranges, colours/odours, dilution arithmetic, and laboratory separation logic. Risky or incorrect alternative branches were not admitted.
- **Biology:** independently constructed the Punnett cross and checked the photosynthesis, nutrition, and Biuret-test procedures step by step.

An approval required a self-contained cleaned prompt, full answer coverage, no unresolved visual dependency, a correct canonical answer, and explicit independent verification evidence. Each approved JSONL entry includes `verification_method`, `verification_evidence`, `source_answer_match`, and `correction_applied`.

`correction_applied=false` means that no factual answer was repaired. Normalizations such as restoring exponents, removing examiner prose, choosing a correct subset from a longer list of alternatives, and rewriting marking points as complete sentences are separately enumerated in `normalization_applied`.

## Disposition counts

| Disposition | Records |
|---|---:|
| Content-quality approved | 26 |
| Rejected or held | 356 |
| **Total** | **382** |

The following are **exclusive primary reasons**, assigned using the listed order. A record can have additional defects, but it is counted once here so the totals reconcile.

| Ordered primary reason for rejection/hold | Records |
|---|---:|
| Confirmed semantic error or material ambiguity | 25 |
| Exact normalized duplicate prompt | 10 |
| External visual, specimen, graph, or construction dependency | 58 |
| Incomplete or partial answer coverage | 34 |
| Malformed OCR or mathematical/scientific notation | 28 |
| Examiner commentary or editorial contamination | 61 |
| Not independently verified to the high-confidence threshold | 140 |
| **Rejected or held** | **356** |

The duplicate primary count is 10 because two members of duplicate groups were already assigned the higher-priority semantic-error category. There are six normalized duplicate groups containing 12 records in total.

For transparency, the overlapping screening flags among non-approved rows were:

| Non-exclusive flag | Flagged records |
|---|---:|
| Examiner/editorial contamination | 114 |
| Visual/specimen/construction dependency | 61 |
| Incomplete/partial answer coverage | 58 |
| Malformed OCR/notation | 33 |
| Confirmed semantic error/material ambiguity | 25 |
| Exact normalized duplicate prompt | 12 |

The 140 residual holds are not claims that those answers are false. They mean this review did not establish independent correctness strongly enough for approval after prioritizing the best short, self-contained, cross-subject records. They must not inherit approval from the publisher label.

## Independent checks represented in the approved tranche

| Subject | Record(s) | Independent evidence |
|---|---|---|
| Mathematics | `waec-a2611f44f0540dd2ba2af145` | Simultaneous age equations solved and back-substituted; future-age sum independently solved. |
| Physics, projectile motion | `waec-b30e8a857589782572e43b3f`, `waec-ac1f8e7f96be5f17a7fa364e` | Vertical component and ascent time recomputed; horizontal component and initial speed recomputed. |
| Physics, magnetism | `waec-1419f2b58a2ef2895889427e` | Converted 20.0 cm to 0.200 m and independently evaluated `BIL sin(theta)` as 0.0566 N. |
| Chemistry, qualitative analysis | `waec-24cae279a47104b5237a2955`, `waec-929f9033ba6489c09760e5f0` | Redox and precipitation equations balanced; colours, odour, gas evolution, and oxidation on standing checked. |
| Chemistry, quantitative | `waec-762a4c88f8844a00641a0ed5` | `C1V1 = C2V2` independently gives 166.7 cm3 total and 66.7 cm3 water added; AgCl test checked by solubility rules. |
| Biology, genetics | `waec-4e221100e2fa3c57121aa205` | Independent `RR x rr` Punnett cross gives 100% `Rr`, round phenotype. |
| Biology, procedures | `waec-a013a7919ae8795a854f835f` | Iodine-starch and Biuret procedures, gas roles, and breast-milk nutrient classes checked independently. |

## Examples of decisive failures found

These examples demonstrate why `answer_status="published"` was not accepted as a correctness signal:

- `waec-828712171e1a5ec219939d27`: the depreciation timeline uses too few annual depreciation steps for the stated dates.
- `waec-85c90110928b8a543545e91d`: the answer claims light intensity is unchanged throughout an optical fibre, ignoring attenuation.
- `waec-2f75141e7e60e05b3ecf4278`: the answer claims dilute nitric acid reacting with iron liberates hydrogen; nitric acid is oxidizing and does not follow that simple acid-metal pattern.
- `waec-cfcb10162227daf4158903c7`: the renal-physiology answer contains a materially wrong ion-handling claim.
- `waec-f5264259669f4d7af400ad3b`: the answer omits the first requested trigonometry part.
- `waec-b007e047794beeba14cf9e66`: the de Broglie equation is absent after extraction, so the record is not a complete training pair.

## Ledger guarantees

The approved JSONL was validated to have:

- 26 parseable JSON objects and 26 unique `record_id` values;
- exact subject and year agreement with the source records;
- all source records satisfying the three audit predicates;
- zero referenced assets and zero extraction warnings;
- every required merge field present;
- maximum `canonical_answer` length of 364 characters (limit: 512);
- maximum `worked_solution` length of 555 characters (limit: 6000);
- no factual correction hidden as normalization;
- `training_eligible=false` on every row pending written permission.

## Original rights-audit recommendation

Merge these 26 entries only into a **rights-blocked review layer**, keyed by `record_id`. Do not copy them into the SFT training view until the provenance gate contains written permission that explicitly permits persistent storage, model training/evaluation, and any intended artifact distribution. Continue review of the 140 residual holds in separate, small subject-specific tranches; never promote them automatically from `published` status.

That recommendation remains the gate for a public/distributable dataset or shipped RAG corpus.
The later private-use adjudication above applies only to the two named local training artifacts.
