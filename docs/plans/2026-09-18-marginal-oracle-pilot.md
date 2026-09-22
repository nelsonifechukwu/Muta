# M18 abstract solver pilot

Status: bounded mathematical implementation, not question authoring or benchmark
admission. Read the winner-test design, math-family blueprint and independently
reviewed feasibility crosswalk. Live training and all existing data stay intact.

## Scope and contract

Implement only `bench/round2_marginal_solver.py` and its focused test file.
`solve_marginals(total, row, column)` accepts built-in integer values with
2 ≤ total ≤ 40 and 1 ≤ row,column < total; reject booleans, nonintegers and all
out-of-domain values. Type violations raise `TypeError`; integer domain violations
raise `ValueError`. Return a dictionary with exactly these immutable values:

- `intersection_values`: tuple of every feasible integer intersection, sorted.
- `lower_table` and `upper_table`: four-cell tuples in the fixed order
  (both, row-only, column-only, neither).

One agent writes the algebraic solver: nonnegative cell constraints imply the
lower/upper intersection bounds; substitute the endpoints to construct witnesses.
The parent independently writes the exhaustive test oracle by enumerating all
nonnegative four-cell tables with total at most 40 and grouping by margins. The
test oracle does not call the solver or use its interval-bound formula.

## Verification

Compare exact feasible sets and endpoint tables for all 20,540 proper-margin
inputs. The enumeration includes 135,751 total tables before restricting to
proper margins. Check swapped margins, nonnegative cell sums, distinct witnesses
and input validation. Mutation tests must reject an independence-imputed singleton,
an incorrect lower-bound sign, dropped constraints and wrong witness orientation.
Explicitly handle equal margins and asymmetric margins. Use integer arithmetic;
probability variants, rendered prose/options/rubrics and model output are out of
scope. No corpus scans, downloads, inference or training changes.

A separate agent reviews the code and tests. Passing means the bounded abstract
mathematics was checked; it does not demonstrate new-family status, curriculum
fit, source rights, item validity, statistical power or benchmark readiness.

## Implemented verification

48 focused tests pass. The independently authored enumeration checks all 20,540
proper-margin cases against 135,751 nonnegative four-cell tables, plus invalid
inputs, witness orientation and five intended wrong-answer mutations. Ruff and
whitespace checks pass. Independent agent reviewer `full_promotion_audit`
re-ran the tests/lint and returned GO for the bounded abstract solver only.

| Artifact | SHA256 |
|---|---|
| Algebraic solver | `556ce34b2af7e63d09baec11db851ff917bf6d3dd36b29c6acb456cad357b703` |
| Independently written oracle/tests | `f4b8fb4dca2d3e5499f5e50f81d81d8b7f8f238e5bbb332d721353361bf484ed` |

No prose questions, answer options, tutoring rubrics, candidate responses or
training rows were created. M18 remains unadmitted pending semantic-family and
item-level gates; these 20,540 inputs are test cases, **not new dataset rows**.
