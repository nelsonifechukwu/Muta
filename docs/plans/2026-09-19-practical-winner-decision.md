# Practical prospective winner decision — pre-inference protocol

The user explicitly directed autonomous continuation to a winner decision on
19 September. The original whole-reasoning-family-disjoint research design
remains unfulfilled; its 0 admitted items must not be relabelled as complete.
This separately named prospective decision battery replaces that research gate
as the prerequisite for a practical model recommendation. No fresh outputs
have been obtained when this protocol is written. Historical known-suite
results are already visible, and that design limitation must be disclosed.

## Fixed scope

Exactly 2,000 original, deterministically generated instances: 500 each maths
MC, science MC, maths structured written and science structured written.
Use 25 declared generator families per subject, 20 independent parameter
instances per family per mode. Do not reuse an instance across modes. Canonical
superfamily clusters may merge overlapping generators before inference.
Training topic/family overlap is expected and reported, not claimed absent.
This measures fresh-instance performance, not unseen-family generalization,
WAEC cohort grades, official ADTC accuracy or universal superiority.

All prompts, answer objects, generators, independent answer checks, exact and
near-overlap audit, cluster labels, grading code, manifest and decision rules
must be frozen and hash-bound before inference. Exclude exact and strong
lexical near-matches with accessible training/development/known-suite text;
preserve metadata-only evidence, no private corpus copies. Candidate screening
may reject/resample instances using only source overlap and oracle correctness,
never model answers. Report unavailable sources and lexical-screen limitations.

## Answer format and verification

Each item has a self-contained statement and explicit units/assumptions. Science
uses stated idealized models and provided constants; no ambiguous diagrams,
medical advice, unknown physical data, subjective biology facts or copyrighted
question extracts. Cover mechanics, energy, electricity, waves, materials,
solutions/stoichiometry and quantitative population reasoning where feasible.

MC has four distinct shuffled choices and exactly one correct label. Written
asks for an intermediate diagnostic quantity and final answer, with brief
working and a final `RESULT: {"intermediate": number, "answer": number}` record.
MC ends `ANSWER: A` (or B/C/D). Primary MC score is final-label correctness;
primary written score is half intermediate correctness plus half final-answer
correctness, with exact or fixed numeric tolerance in each key. Preserve
format failures as failures; separately report semantic/format diagnostics.
This is structured reasoning accuracy, not a complete tutoring-quality score.
Independently recompute both targets from typed parameters with a different
derivation where feasible. Verify every generated key and every choice; review
all family renderers and corner cases, not only a sample of numeric answers.

## Five-model execution

Use the same five exact Q4_K_M artifacts as the sealed full-five comparison.
Do not retrain, re-export, download weights or rerun known suites. Freeze one
new runner and its runtime settings. Greedy temperature 0, top-p 1, seed 3407,
thinking disabled, no prompt cache, 1,024 generated-token limit, 4,096 context
per slot. Equal continuous-batching concurrency is allowed after a separately
reviewed synthetic transport test; avoid sharing GPU with other work and acquire
the existing Oracle GPU lock. Raw response bytes, usage, errors and caps are
retained. Do not selectively retry hard questions, change budgets or inspect
partial model rankings to change the battery. A failed infrastructure attempt
is preserved and diagnosed before an explicitly recorded whole-stage retry.

## Scores and recommendation fixed before fresh outputs

Report all four stratum scores and their equal-weight macro (0–100). Keep
historical known-suite semantic/tutoring results in separate columns; do not
regrade them or average their incompatible scales into a new composite.
Paired superfamily bootstrap: seed 20260919, 10,000 resamples. Before any fresh
inference, review merged the 50 generators into 13 conservative superclusters:
five mathematics-only, two science-only and six shared. Preserve that fixed
coverage-pattern design: sample the original number of clusters with replacement
within each coverage-pattern group, then combine them into one global weight
vector shared by all four strata and all five models. Sort pattern tuples and
cluster IDs lexicographically; use PCG64 `Generator.choice` within each group.
This explicit pre-output amendment conditions on subject coverage, avoiding an
unstratified draw that drops an entire subject; it does not redraw based on a
model's result. The earlier synthetic global-bootstrap prototype is unchanged.
Use
percentile intervals with Bonferroni adjustment for nominal two-sided 95%
simultaneous coverage over
the 26 declared comparisons (10 pairwise macro, 16 challenger/incumbent strata).
Report limited cluster count, Monte Carlo tail resolution, empirical zero
variance, and inability to infer universal or unknown-pretraining generality.
Use NumPy linear quantiles. These are approximate intervals, not guaranteed
coverage: each extreme tail has only about 9.62 expected draws. Do not claim
calibrated power or treat the number of item variants as independent families.
Any empty-stratum resample aborts the inferential procedure without redraw;
report descriptive results and retain incumbent under the fixed default rule.
Mechanics and synthetic boundary cases require independent review before use.

A quality replacement qualifies only if its simultaneous lower macro bound
versus incumbent exceeds +2 points, its lower macro bound versus every other
contender exceeds zero, and all four lower stratum bounds versus incumbent
exceed -3 points. It must additionally not regress on either completed known
written core or complete count relative to incumbent, or by more than 3
percentage points on completed semantic MC. These are fixed practical guards,
not uncertainty claims about those small known suites. If no challenger passes,
the practical winner is **retain incumbent**, with the best fresh point-score
challenger and uncertainty reported explicitly. Do not keep adding questions
or relax the thresholds after model outputs. Always provide a recommendation,
even when no challenger earns promotion; do not manufacture a clear superiority
claim from that default decision.

Hardware qualification is independent. Missing actual target CPU access does
not halt the quality decision. Never label GPU/Mac measurements an ADTC CPU
score or silently replace the user's default deployment file.

## Work partitions and review

- Math writer: `bench/winner_battery/practical_math.py` plus focused tests.
- Science writer: `bench/winner_battery/practical_science.py` plus focused tests.
- Independent reviewer: generators/answers/schema, then execution and statistics.
- Root: shared builder/schema, source-overlap audit, grading/statistics, runner,
  frozen manifest, execution, raw-artifact reconciliation and result table.

All new files are separate from historical sealed evidence. The existing
synthetic-only statistical primitives stay unchanged; production confidence
and decision code is a separate module. No source dataset text is published.
