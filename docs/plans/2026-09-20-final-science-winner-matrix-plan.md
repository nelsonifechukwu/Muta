# Final science-tutor winner matrix — implementation plan

## Objective

Prepare a private-safe Markdown decision matrix for the final comparison of
`p2-half-finalist` against `incumbent-muta`. Do not inspect partial inference
outputs or decide a winner. The matrix will bind only terminally sealed
aggregate evidence and use the user's conservative promotion rule alongside
the already-frozen plan guards.

## Authorities to preserve

- Science development selection and its final comparison priority:
  `2026-09-19-science-tutor-selection.md`.
- R1 refinement and matched final evaluation:
  `2026-09-19-science-r1-refinement-and-final.md`.
- Source-heldout capture/scoring protocol:
  `2026-09-19-final-science-holdout-evaluation.md`.
- Eight-case blinded tutoring rubric and capture protocol:
  `2026-09-19-final-tutor-gguf-evaluation.md`.
- Practical 2,000-item winner gate:
  `2026-09-19-practical-winner-decision.md`.
- Read only the completed/hash-bound final science MC summary and completion
  receipt for prefilled science evidence. The practical-2000 result, final tutor
  review aggregate and known-suite addendum remain pending inputs.

## Matrix behavior

Record artifact hashes, terminal completion status, roster/model-hash joins,
candidate-versus-incumbent metrics, and rule outcomes. Keep per-item prompts,
responses, private mappings, answer keys and rubric evidence out of the matrix.
Apply the frozen practical promotion limits and known-suite regression guards;
require a strict equal-weight combined tutoring advantage using the frozen
science and pedagogy dimensions. Missing, incomplete, mismatched or unresolved
evidence defaults to retaining the incumbent. Record decision-rule gaps instead
of inventing thresholds or significance claims.

## Deliverable and verification

Create one Markdown template under `docs/plans/`, prefilled only with the
already sealed science-holdout aggregates. Inspect it for inadvertent private
content and calculate exact SHA256 hashes for the plan, template and referenced
authorities. No model-result execution or test code is needed.
