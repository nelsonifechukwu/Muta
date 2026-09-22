# Practical semantic diagnostic — fixed before packet review

Diagnostic only: **no primary regrading, replacement gate, extra inference,
sample replacement or training-data use**. This supplements the
[frozen practical protocol](2026-09-19-practical-winner-decision.md); the
[transport qualification](2026-09-19-practical-transport-amendment.md) remains.
The rubric author has read the packet builder and existing protocol, but no
fresh model responses or partial rankings. Inference was already running when
this diagnostic rubric was written; do not describe it as pre-inference.

## Unchanged packet and review procedure

Use only the compiler's sealed `semantic-review-blinded.json`: within each of
the four strata, take the five lowest SHA256 values of
`practical-semantic-review-v1:` + item ID, then all five models for each item.
This is **20 distinct questions, 100 responses, 25 responses per stratum**,
not the first five generated/received responses and not 100 independent questions.
The compiler's opaque review IDs and ordering stay unchanged. Bind each ledger
to the packet SHA256 and this rubric's SHA256; reject duplicate/missing IDs.

1. Read the entire prompt, reference keys, answer and any `reasoning_content`
   for every assigned record. The reference keys guide numeric checks; verify
   explanatory claims from the stated mathematics/idealized science rather
   than assuming a matching final number proves sound reasoning.
2. Annotate independently without the model mapping, candidate names, primary
   score ledger, aggregate rankings or another reviewer's annotations. Do not
   try to reverse the deterministic aliases or infer a preferred candidate.
3. Every one of the 100 records receives a primary annotation. A second agent
   independently annotates the same packet before seeing the first ledger;
   reconcile disagreements only after both ledgers are locked. Preserve both
   original opinions, the resolution and its short reason. If cross-review is
   incomplete, report exact coverage and unresolved IDs; do not imply full
   double review or postpone the frozen primary decision to manufacture it.
4. Unmask only after annotations/resolutions are locked. Join through the
   compiler's separate mapping to original raw-response hashes. Report simple
   category counts and illustrative disagreements separately from primary
   scores. Never combine these categories into a weighted score or ranking.

Model IDs are withheld, not cryptographically hidden: deterministic aliases,
recognizable prose and previously known model behavior limit blinding. Review
is by agents, not blind human examiners. The same questions appear five times;
recognizing them is expected and does not justify copying an annotation.

## Annotation schema

One JSON object per review ID. The ledger header/sidecar binds `packet_sha256`,
`rubric_sha256`, reviewer identity, model-mapping access declaration, start/end
time and exact assigned/completed IDs. Each row contains these required fields:

| Field | Allowed values / operational rule |
|---|---|
| `review_id` | Exact opaque ID from the packet; no candidate identity in a blinded ledger |
| `intermediate_content` | `correct`, `incorrect`, `not_stated`, `conflicting`, `unresolved`, `not_requested` |
| `final_content` | `correct`, `incorrect`, `not_stated`, `conflicting`, `unresolved` |
| `explanation` | `sound`, `material_error`, `no_substantive_explanation`, `unresolved` |
| `contradiction` | `none`, `material`, `unresolved` |
| `units_assumptions` | `consistent`, `material_error`, `required_information_omitted`, `not_applicable`, `unresolved` |
| `format_observation` | `appears_compliant`, `clear_violation`, `unresolved`; diagnostic observation, not a replacement parser |
| `flags` | Zero or more controlled tags listed below; no severity weighting |
| `note` | One or two short, evidence-specific sentences explaining any error, conflict, omission or uncertainty; no model guess |

Controlled flags: `arithmetic_error`, `invalid_algebra_or_inference`,
`wrong_scientific_law`, `unstated_or_changed_assumption`, `unit_conversion_error`,
`dimensional_error`, `contradictory_targets`, `unsupported_correct_result`,
`missing_requested_work`, `missing_or_wrong_marker`, `invalid_result_record`,
`extra_text_after_record`, `wrong_record_value`, `ambiguous_notation`,
`apparent_incomplete_response`, `possible_key_or_prompt_issue`.
An empty flag list is valid. Do not invent token-cap labels from prose alone;
actual finish reasons remain in the compiler's separate evidence.

## Decision conventions

- Content categories concern the quantities/option meanings actually asserted,
  including the final record, not merely whether a reference number appears.
  For MC, check the asserted label against its option and any numeric claim.
  A correct label paired with an incompatible stated value is `conflicting`.
  Use `not_requested` for an MC intermediate the prompt never requests, even
  if the packet contains that oracle quantity for internal verification.
- Accept equivalent exact forms, stated-unit conversions and reasonable
  rounding consistent with the prompt. An unlabeled final JSON number uses
  the prompt's requested units; a wrong number there is `wrong_record_value`,
  not merely a formatting defect. Earlier correct prose cannot erase it.
- `sound` requires actual substantive reasoning with no material mathematical
  or scientific error. A bare correct answer is `no_substantive_explanation`,
  not verified reasoning. Correct final targets with a false derivation retain
  correct content categories but receive `material_error`; no primary score
  changes. Missing working is tagged only when the prompt requests it.
- A material error changes a requested quantity, validity of the method,
  scientific interpretation or stated assumptions. Harmless typography or an
  obvious grouping omission is not automatically an error when the adjacent
  correct formula and calculation make the intended operation unambiguous;
  explain the reading briefly. Do not repair a genuinely false calculation.
- Distinguish a clearly identified rejected attempt or explicit self-correction
  from an unresolved contradiction. Incompatible claims retained as valid,
  especially prose versus final record, are material contradictions.
- Missing printed units are not an error if the prompt fixes them and the
  response is unambiguous. Record `required_information_omitted` only when an
  explicitly required unit/assumption statement is absent. False units,
  dimensional inconsistency or silently replacing a stated idealization are
  material errors even when a numeral happens to match.
- `format_observation` never overrides the frozen strict grader. A semantically
  correct answer with an absent marker may still score zero; a parser-accepted
  correct numeric record may still contain a faulty explanation. Inspect both
  distinctions and preserve both results. Borderline parser questions remain
  `unresolved` here, not manually awarded credit.
- Do not infer missing reasoning or finish a truncated answer for the model.
  If the prompt/key seems defective or interpretation cannot be settled, flag
  it and retain `unresolved` on affected dimensions. Document it separately;
  do not silently fix keys, replace records or alter the frozen decision.

## Reporting limits

Report counts with the exact reviewed denominator; preserve overlapping tags
rather than summing them into a failure rate. This small deterministic,
question-clustered sample is descriptive: no population error rate, significance
test, universal tutoring claim or complete scientific-answer certification.
Disclose agent blinding/cross-review coverage and remaining disagreements.
The frozen practical recommendation remains authoritative for its stated
structured-accuracy scope; this separate diagnostic may describe weaknesses
but cannot retroactively add, relax or replace a promotion condition.
