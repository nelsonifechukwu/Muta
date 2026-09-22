# M02 bounded abstract verifier

19 September 2026. Plan written before implementation. This is a mathematical
development check, **not question authoring, family admission, inference, or a
change to the proposed 2,000-item winner-test decision rule**.

## Decision and scope

The mathematics/science blueprints, feasibility/source crosswalks, audit-only
validator and exact M02 warehouse lexical receipt do not presently admit a
single fresh family. The lexical scan's zero hits are not evidence that all
semantic or implicit parameter-system neighbours are absent. In particular,
TemplateGSM, private exams, the incumbent datasets and composed sources still
need reviewed essential-graph comparisons. Science additionally needs pinned
factual evidence and independent scientific/rubric review. A balanced pilot
cannot truthfully be called admitted on this evidence.

Implement the smallest next executable mathematical gate for M02 only:

1. Represent two real-variable linear equations by a 2×3 augmented integer
   matrix, with optional affine integer coefficients in a finite parameter.
   Abstract inputs contain no question prose, options or grading rubric.
2. Oracle A computes ranks from exact integer minors. Oracle B independently
   performs Fraction row elimination, never calling A or its classification
   helper. Both must correctly distinguish inconsistent, unique and infinitely
   many solutions, including entirely zero coefficient rows.
3. Enforce the blueprint's finite bounds: affine offsets/slopes −4…4 and
   distinct parameter values in −6…6. For an eligible *abstract graph fixture*,
   require at least two outcome classes and a singular instance. This graph
   condition says nothing about corpus independence or curriculum fit.
4. Exhaustively compare all 15,625 numeric 2×3 matrices over −2…2, plus targeted
   boundary, rational-pivot, zero-row, dependent-row and mutation checks.
   A deterministic bounded affine sample is supplemental, explicitly not
   exhaustive over all affine systems. Do not confuse cases with independent
   families or benchmark items.
5. Emit compact development metadata to stdout only: tested scope, counts,
   source-code hashes, no-admission flags and limitations. Preserve a small
   receipt through apply_patch after executing. No corpus reads/copies are
   needed for this mathematical verifier.

Own only new files in `bench/winner_battery/`, a small receipt in
`provenance/evaluation/winner-battery-development/`, and this plan. Leave the
frozen evaluator, all existing artifacts, remote processes and other agents'
files untouched. Focused offline tests, Ruff, and an independent root review
are required before describing the implementation as reviewed.

## Remaining admission gates

- Cross-source semantic graph mapping and independently reviewed whole-family
  exclusions over warehouse/selected/dev/incumbent/known suites.
- Original candidate wording, parameter-instance uniqueness, unique MC keys
  and checked distractors, independently reviewed mode-aware tutoring rubrics.
- Hash-bound real candidate audit against all required input roles using
  `bench/round2_holdout_audit.py`; lexical success alone remains insufficient.
- Balanced admitted strata, independent family-count/power assessment, and
  executable pre-inference statistical rule/rubric freeze.
- Actual target-CPU qualification remains separate from quality testing.

Until those gates pass, the fresh primary battery remains unmaterialized;
known-suite performance supports only a provisional regression comparison.

## Executed bounded development verification

New files: `bench/winner_battery/m02_oracles.py` and
`bench/winner_battery/test_m02_oracles.py`. The CLI writes JSON to stdout only;
its exact parsed output is preserved in
`provenance/evaluation/winner-battery-development/m02-numeric-oracle-check-20260919.json`.

- 45 focused tests passed; 101 passed with the unchanged audit-validator tests.
- Ruff lint and formatting passed after formatting the two new Python files.
- The complete 15,625 numeric-matrix grid agrees: 12,400 unique, 577 infinite,
  2,648 inconsistent. Ordered result hash:
  `42b7aad20c6f9b407d2f424564fd859602efedab05c91e8111a621a2db1b6917`.
- Tests additionally cover 1,300 parameter-instantiated matrices from 100
  deterministic affine samples, bounds, malformed inputs, exact rational
  elimination, equation-operation invariance, all three classes in one abstract
  fixture and the `determinant zero => infinite` mutation.
- The two algorithms share only input validation and the immutable result shape,
  not a solver or classification helper. They were authored by the **same agent**;
  algorithmic diversity is not an independent human/agent review attestation.
- No corpus or model was read, no question was rendered, and zero items/families
  are admitted. Independent root adversarial review is still required.

Reproduction:

Root independently read both full solver implementations and their tests and
reproduced all 101 combined passing tests. Integer minor ranks and exact
row-reduction contradiction checks correctly distinguish the zero-coefficient,
dependent, inconsistent and unique cases; no shared classification implementation
was found. This closes the bounded code-review gate only. It does not admit any
questions or certify semantic corpus independence.

```sh
.venv/bin/python -m pytest -q bench/winner_battery/test_m02_oracles.py bench/tests/test_round2_holdout_audit.py
.venv/bin/ruff check bench/winner_battery
.venv/bin/ruff format --check bench/winner_battery
.venv/bin/python -m bench.winner_battery.m02_oracles
```
