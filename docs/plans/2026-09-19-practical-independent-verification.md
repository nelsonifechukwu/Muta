# Independent verification of the practical prospective battery

Pre-implementation plan, 19 September 2026. Implements the reviewer lane of
[the practical protocol](2026-09-19-practical-winner-decision.md). Historical
whole-family-disjoint admission remains unfulfilled; these are fresh-instance
checks, not a retrospective claim that the research battery was completed.

1. Read all maths/science family renderers and typed parameter contracts.
   Independently derive both requested numeric targets, using inverse,
   conservation, enumeration or alternative formulas where feasible. Do not
   import a writer's answer-calculation helpers into the independent checker.
2. Validate all generated instances, parameter domains, finite numeric targets,
   fixed tolerances, distinct MC choices and the unique correct label. Bind
   the rendered statement's data/units and requested intermediate to its typed
   parameters; numeric agreement alone cannot detect a misrendered problem.
3. Add adversarial mutations covering each family, intermediate/final answers,
   parameters, duplicate/equivalent MC choices, malformed schema and invalid
   domains. Check the complete candidate pool before freezing its manifest.
4. Compare indispensable graph structure across declared families and propose
   coarser canonical clusters before inference; names or subject namespaces
   cannot create statistical independence.
5. Independently review the fixed runner, grader and bootstrap implementation.
   Require explicit quantile interpolation and empty-stratum handling; report
   nominal coverage, small cluster support, extreme-tail Monte Carlo noise,
   deterministic-generator sampling limits and lack of universal validity.

Own only `bench/winner_battery/practical_independent_check.py` and its focused
test module, plus this plan. Writers retain their generators; root retains the
protocol/builder/runner/grader. Report required fixes to their owners. No fresh
model output or partial ranking is consulted during this review.

## Executed pre-inference answer and rendering review

All 50 generator branches were read completely, including statements, units,
intermediate labels, typed parameters and domain restrictions. Both exact
targets of all 2,000 raw instances were recomputed by the independent checker
without importing generator calculation helpers. The final rendered pool
also passed: 500 items per stratum, distinct prompts, exact metadata/key/hash
joins and one correct numeric choice per MC item. Correct letters and sorted
numeric ranks each have 250 occurrences globally and five per family.

The writer metadata round-trip checks remain required: they bind literal
problem text to the reviewed renderer. The independent checker supplies a
separate arithmetic/domain derivation and binds final prompts to those raw
records; its numeric agreement alone is not a statement-correctness proof.

| Reviewed source | SHA256 |
|---|---|
| `practical_math.py` | `c00c139b6b5b4aed4790b06d07dc4620f9d8f9fab048427ea876c6abccbf9391` |
| `practical_science.py` | `06d3799b76d16785bc7f722f77b803ac1a76fd5de78d8ebb16435baa5b851795` |
| `practical_common.py` | `75dc94321b143fc2b6e6f70dc32dd07b4bd98a4cb627bf6d63ca364915b2c2fb` |
| `practical_independent_check.py` | `2261328e9ea2e278a5b2983632c908340d8254d9377f62a3326c083d34729ba8` |
| `test_practical_independent_check.py` | `2a79020fdfecdf61cbd07e23be6b3caefa6be044aa5cb7779ad62275818b012d` |

The 149 focused independent tests pass. They include 50 hand-derived first
instances; intermediate and final mutations for every generated instance;
parameter/schema/domain mutations; duplicate instances; option, tolerance,
cluster and hash tampering; and strict grader/partial-credit boundaries.
An initial Ruff run found one import-order error in the new test file; this
was corrected. Formatting, Ruff and the full focused tests then passed.

Review caught and root corrected a constant-rank MC shortcut: the earlier
distractors always placed the correct value third when sorted. The accepted
scheme balances correct numeric rank and letter separately, uses uniform
scientific formatting, and has distinct choices under the scoring tolerance.
These are generic numerical distractors, not validated misconception probes.
The final written-record instruction now explicitly requires a single line,
matching the strict JSON grader. The builder also now respects the science
author-checker's None-on-success interface rather than treating it as failure.

## Conservative clusters and statistical qualification

`CLUSTER_GROUPS` defines 13 deliberately broad pre-inference superclusters,
including cross-subject merges for weighted mixtures/means, mean trip speed,
harmonic work/circuit rates and multiplicative growth. They are not a claim
that 13 independent reasoning families have been established. The largest
group contains 13 generators / 520 items; report this concentration and
effective stratum support, not just the raw question count.

Root accepted a pre-output design amendment: production resampling is
stratified by cluster subject-coverage pattern, with five maths-only, two
science-only and six shared clusters. Draw each group's original cluster
count with replacement and combine into one multiplicity vector used for
every stratum and model. Shared clusters must not be drawn separately for
each subject. This avoids empty strata by conditioning on the fixed design,
not by discarding unfavorable draws; it differs from the earlier global
bootstrap proposal and leaves the synthetic primitive unchanged.

Freeze ordering, seed, RNG, quantile interpolation and this sampling law
before inference. With 10,000 replicates and Bonferroni adjustment for 26
two-sided comparisons, each extreme tail contains only about 9.62 expected
draws. Bands are nominal approximate bootstrap intervals with substantial
tail Monte Carlo uncertainty, not guaranteed simultaneous coverage, proven
power or universal generalization. Production statistics and runner review,
source-overlap screening and the final freeze remain separate gates.
