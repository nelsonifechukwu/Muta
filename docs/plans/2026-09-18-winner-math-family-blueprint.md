# Proposed fresh mathematics family blueprint

Status, 18 September 2026: **design only**. No questions, answer keys, generators,
model outputs, or new evaluation results were produced for this note. The
mathematics target is 500 MC plus 500 written/tutoring items within the larger
proposed 2,000-item battery. **Currently admitted: zero items and zero families.**
Neither source independence nor statistical power has been established.

Update, 19 September: M18 is conservatively **excluded from the fresh primary
battery** by the independently proposed, root-adopted decision
`2026-09-19-m18-primary-family-decision.md`. Its 20 MC + 20 written conditional
allocation is a 40-item design shortfall, not existing rows or an automatic
redistribution. Historical family/count proposals below retain their original
values; M18 is no longer eligible for their authoring queue. Other families
remain unadmitted.

This note does not alter frozen training inputs, the incumbent, existing test
suites, or `2026-09-18-full-data-winner-test-design.md`. It proposes concrete
families for independent scrutiny before any question authoring. Private corpus
text is not reproduced. All paths below are repository-relative.

## Observed generator coverage

Inspected `model-development/finetune/muta_dataset_v2/generators.py`, SHA-256
`5e6a4ebe19a8de8c85dba45327cbc743ce7b19048b224eb9198b8dcbc9384631`, and the
warehouse manifest's family/module metadata. This is a code/metadata inventory,
not a semantic scan of all 2,500,350 rows.

| Existing executable group | Functions and corresponding family IDs |
|---|---|
| Active mathematics | `_linear` / `linear_equation`; `_simultaneous` / `simultaneous_equations`; `_sequence` / `arithmetic_sequence`; `_mean` / `arithmetic_mean_four`; `_triangle_area` / `triangle_area`; `_pythagoras` / `pythagorean_hypotenuse`; `_percentage_increase` / `percentage_increase` |
| Quarantined because developed after related evaluation prompts | `_profit` / `profit_two_prices`; `_average_speed` / `equal_distance_average_speed`; `_ratio` / `ratio_share`; `_probability` / `single_draw_probability`; `_interest` / `simple_interest` |
| Active physics, also relevant arithmetic templates | `_force`, `_density`, `_ohm`, `_wave`, `_kinetic_energy`, `_electrical_power`, `_pressure`, `_work_done` |
| Active chemistry | `_moles`, `_concentration`, `_dilution`, `_gas_volume`, `_stoichiometry`, `_mass_percentage`, `_neutralization` |
| Active biology | `_magnification`, `_population_density`, `_inheritance`, `_germination`, `_pulse_rate` |
| Active integrated science | `_energy_efficiency`, `_water_tank_volume`, `_temperature_conversion` |

There are 30 active formula families in total. `_render`, `_render_socratic`
and `_socratic_scaffold` turn them into worked solutions, practice marking
guides, misconception corrections, hints and concise answers. Those wrappers
are **not additional mathematical families**.

The warehouse also contains 56 DeepMind module clusters covering linear
equations, polynomial roots/composition/evaluation, sequences, arithmetic,
comparison/order, conversion/time, number theory/rounding, differentiation and
sampling-without-replacement probability. Several are explicitly `_composed`:
adding an extra arithmetic step is not enough to establish a new family.
TemplateGSM contributes 878 declared clusters, while GSM8K and private exam
rows have predominantly singleton metadata. Existing judges/STEM prompts and
old incumbent training data create additional exclusions. No proposed family
below has yet been compared semantically against that full coverage.

## What "family-disjoint" means here

A family is an equivalence class of **essential reasoning graphs**, not an
algebra topic or a template string. Its design record must specify:

1. Input quantities/objects and their relationships, plus domains and assumptions.
2. Target assertion or unknown, required logical/quantifier structure, and the
   indispensable intermediate operations or case distinctions.
3. Canonical dependencies, invariant under names, units with equivalent
   conversion, option ordering, prose, coefficient changes and notation.
4. Supported answer forms and the actual misconception/branch being tested.

Renaming a town, resampling numbers, reversing a single formula's unknown,
changing MC to written, supplying a wrong student answer, or appending a
redundant check does **not** establish a new family. Conversely, learning an
atomic operation such as addition, multiplication or solving a linear equation
does not automatically contaminate every later task using that operation.
The question is whether the **essential dependency/case structure** was already
present—not whether the broad curriculum topic was present.

A composition is provisionally distinct only if its additional dependency or
branch is necessary to determine the answer and is not an inessential wrapper
around a trained template. Map equivalent graphs across sources to one canonical
family, rather than relying on different source namespaces to evade exclusion.
Conservative reviewers may merge several proposals below. This definition must
be agreed before outputs; it does not retroactively certify any source split.

## Twenty-five bounded proposals

Each row proposes **at most 20 MC and 20 written tasks**, with different numerical
instances across modes. Those quotas are conditional capacity targets, not
verified examples. Every row needs the common review gates below plus the
specific overlap check listed. "High" means an obvious neighbouring trained
structure needs particular scrutiny; "Unresolved" is not a low-risk clearance.

Oracle A is the reference solver; oracle B must use a separately written route,
not call A or re-render its result. Finite exhaustive checks are complete only
over the explicitly bounded domain. Use rational arithmetic wherever possible.

| ID / proposed family | Essential graph and bounded domain | Independent machine-check routes | Overlap / specific review |
|---|---|---|---|
| M01 — Cancellation with excluded inputs | Original rational expression → denominator-zero set → reduced expression → equality with preserved domain; degree at most two | A: symbolic cancellation and root sets. B: exact polynomial cross-multiplication plus independent original-denominator factor/root verification | **High:** DeepMind polynomial simplification. Reject if only cosmetic cancellation or a renamed existing domain task |
| M02 — Parameter-dependent system classification | Parameter → coefficient/augmented ranks → zero, one or infinitely many solutions; two equations, bounded parameter choices | A: symbolic determinant/rank conditions. B: exact Fraction elimination independently for every allowed parameter | **High:** `_simultaneous` and composed linear modules. Required branch is degeneracy/consistency, not solving another ordinary nonsingular system |
| M03 — Piecewise charge-plan crossover | Stated tier boundaries/fixed fees → branch costs → integer feasible quantities → cheapest-plan regions and ties; quantities bounded to 0–100 | A: solve branchwise inequalities. B: enumerate all allowed quantities and compare exact costs | **High:** TemplateGSM/GSM8K tariffs. Boundary conventions and ties must be explicit; do not confuse a compound bill with novelty |
| M04 — Rational inequality with a pole | Zero/pole set → ordered sign cells → strict/non-strict endpoint decisions → solution set; numerator/denominator degree at most two | A: symbolic inequality reduction. B: independently form exact critical points, prove sign constancy per cell, test one exact witness and each endpoint | **High:** algebra/comparison modules. A few random substitutions are not proof of an entire interval |
| M05 — Absolute-value interval constraint | Distance expression → distinct piecewise branches → intersection with a second domain condition → admissible interval/integer count; small integer bounds | A: symbolic piecewise solve. B: exact distance geometry plus exhaustive integer check where count is requested | **Unresolved:** compare against composed algebra and both training/known-suite inequalities; domain condition must be essential |
| M06 — Squaring creates inadmissible roots | Radical domain → transformed polynomial candidates → original-equation substitution → accepted roots; one radical and degree at most two after squaring | A: symbolic solve with real-domain filtering. B: independent exact root enumeration and verification in the original relation | **High:** polynomial-root/surd modules. Count rejected candidates explicitly; combine with M01/M04 if reviewers find equivalent graph structure |
| M07 — Discrete package procurement | Integer package choices → minimum quantity and budget constraints → exact waste/cost objective → unique minimizer or explicit tie set; two package types, counts at most 30 | A: bounded integer optimization. B: enumerate the complete feasible pair set with exact costs | **High:** TemplateGSM purchasing. Reject a task reducible to one ceiling operation; objective and constraints must matter |
| M08 — Ordered state updates with a cap | State → update A → update B → capacity/floor rule → next state and invariant; at most six periods, explicit update order | A: direct state-machine simulation. B: independently tabulate transition compositions and verify every intermediate state | **Unresolved:** existing tank/sequence tasks. Reject if it merely repeats a constant subtraction or arithmetic progression |
| M09 — Compatible congruences inside a bound | Residue conditions → compatibility check → common solution class → solutions in an interval; two moduli at most 20, interval span at most 300 | A: generalized CRT/gcd construction. B: enumerate every integer in the stated interval | **High:** gcd/lcm/remainder composed modules. Reverse-unknown remainder alone is not distinct |
| M10 — Bounded Diophantine feasibility/count | Two integer counts → linear resource equation → nonnegative/domain constraints → all solutions/count; total search grid at most 31 × 31 | A: extended-gcd parameterization and bound intersection. B: exhaustive integer-pair enumeration | **High:** simultaneous equations and coin/purchase word problems. Require integrality/solution-set reasoning, not an ordinary two-equation solve |
| M11 — Consistency of rounded measurements | Declared rounding rule → inverse half-open intervals → transformed/intersected feasible intervals → consistency or tight range; positive rational endpoints | A: interval arithmetic with endpoint flags. B: independent rational boundary inequalities; exact witnesses for attained extrema and convergent interior witnesses for unattained infimum/supremum bounds | **High:** rounding/conversion modules. Rounding mode/ties and endpoint attainment must be specified; simply undoing one rounding operation is insufficient |
| M12 — Aggregate comparison reversal | Two subgroup tables → within-group exact rates → weighted aggregate rates → explain why ranking reverses; bounded nonnegative counts, nonzero totals | A: rational weighted-rate calculations. B: independent cross-product comparisons of all within/pooled rates | **Unresolved:** means, ratio and science data interpretation. This is an aggregation structure, not a causal inference claim |
| M13 — Reconstruct frequencies from cumulative counts | Monotone cumulative table → difference frequencies → rank positions → median/quantile with stated convention; at most six integer categories | A: cumulative inversion and rank logic. B: explicitly expand the finite multiset and sort it | **High:** order/mean/statistics tasks. Table ambiguity, duplicate ranks and median conventions need review |
| M14 — Sensitivity of two statistics to one replacement | Ordered finite data → constrained replaced value → changed mean and median/rank branches → validity of a learner's claimed invariance; at most seven observations | A: symbolic sums and order-cell analysis. B: enumerate the bounded replacement domain and recompute each statistic | **High:** `_mean` and order modules. A new operand or asking for a median instead of a mean is not enough |
| M15 — Conditional probability from a two-way table | Joint counts → relevant conditioning population → event intersection → conditional probability and reversed-condition contrast; all cells nonnegative, denominators positive | A: exact table fractions. B: enumerate labelled finite outcomes and conditional subsets | **High:** probability families and private exam questions. Distinguish conditional direction; do not relabel a single-draw ratio as new |
| M16 — Stop-or-continue finite scoring process | Observed state → available action → stochastic transition/payoff → expected-value comparison → optimal policy; horizon at most three, at most two actions and three outcomes per action | A: exact rational backward induction. B: enumerate every admissible deterministic policy and complete outcome tree | **Unresolved:** composed probability/word problems. State must influence the decision; declare neutral classroom points and all probabilities |
| M17 — Shared-event Boolean probability | Independent primitive events → overlapping Boolean branches → target event → exact probability without double counting; at most four primitive events | A: weighted complete truth table. B: independently simplify event algebra and inclusion–exclusion calculation | **High:** DeepMind probability and series/parallel language in known suites. Use explicit abstract events; shared branches are not independent |
| M18 — What marginals do not determine | Given marginals → feasible joint-table constraints → range of target intersection/conditional value → construct distinct compatible witnesses; total at most 40 | A: exact inequality bounds. B: enumerate every feasible integer two-way table | **Excluded from fresh primary:** known training neighbour shares latent affine occupancy-feasibility structure; see adopted `finite_membership_one_free_count_v1` decision. Not a claim of identical complete prompts |
| M19 — Decision under an explicit scoring rule | Known belief probabilities and score/loss/blank rule → action payoffs → expected scores → decision threshold/tie; at most four options | A: symbolic rational expectation differences. B: enumerate outcomes and probability-weighted scores for every action | **High:** expected-value/word-problem templates. Must not assume equal likelihood or infer confidence from missing information; cluster with M16 if appropriate |
| M20 — Noncommuting coordinate transformations | Explicit reflection/translation/rotation maps → ordered composition → transformed points/orientation → compare reversed order; integer/rational coordinates, small maps | A: exact affine matrices. B: independent coordinate substitution on defining points and signed-area/orientation check | **Unresolved:** coordinate geometry/private exam templates. Order sensitivity must matter; no image-dependent diagrams |
| M21 — Polygon region with an excluded subregion | Ordered polygon coordinates and contained hole → signed boundary areas → region difference → orientation-invariant area; simple orthogonal polygons, at most eight outer vertices | A: shoelace calculation with orientation handling. B: exact axis-aligned cell/rectangle decomposition | **High:** `_triangle_area`, composition and private geometry. Prove simplicity, containment and nonintersection; do not reuse a trained subtraction-of-areas graph |
| M22 — Tangency determines an unknown length | Circle centre/radius and external point → tangency/perpendicularity constraints → admissible tangent lengths/points → geometric verification; exact rational or simple algebraic coordinates | A: symbolic coordinate constraints. B: independent dot-product/perpendicular and distance identities | **High:** `_pythagoras` and private geometry. Reject a disguised single right-triangle length calculation without an essential tangency constraint |
| M23 — Integer geometry optimization | Perimeter/partition constraints → feasible integer dimensions → area objective → maximize with boundary/tie handling; bounded dimensions at most 60 | A: quadratic reduction and exact neighbouring-integer/boundary comparison. B: exhaustive feasible geometry enumeration | **High:** rectangle/area/purchase optimization templates. Cluster with M07 if the same essential integer-optimization graph remains after interpretation |
| M24 — Coupled similarity constraints | Shared scale relation across labelled shapes → linear-size constraint → quadratic area relation → consistency or feasible scale classification; positive rational scales | A: symbolic similarity constraints with domain filtering. B: independently construct coordinates and verify corresponding ratios and areas | **High:** `_magnification`, ratio/area and private exam templates. Reject simple scale-factor substitution; both constraints must be indispensable |
| M25 — Verify or refute a universal modular claim | Integer polynomial → dependence on residue class → exhaustive residue witnesses → proof or counterexample to a universally quantified divisibility claim; degree at most three, modulus at most 12 | A: polynomial reduction modulo the modulus and full residue enumeration. B: independent binomial-expansion proof that residue cases cover all integers, then check each case | **High:** number-theory/logic suites. Finite arbitrary examples cannot prove a universal claim; the periodicity lemma is mandatory |

## Counts and modes: feasible targets, not a filled battery

| Stage | MC target | Written target | What the count means |
|---|---:|---:|---|
| Present state | 0 | 0 | No authored/admitted items |
| First bounded design/solver pilot: M02, M08, M12, M18, M20, M25 | 24 | 24 | Conditional eight distinct instances per family, four per format; validate feasibility before expanding |
| All 25 families admitted and sufficiently varied | 500 | 500 | At most 20 per format per family; not 1,000 independent reasoning families |

Those six initial proposals are chosen for an explicit branch/state/aggregation
or proof requirement that is not visible in the seven active local mathematics
generators. That observation is **not** evidence of disjointness from DeepMind,
TemplateGSM, private exam material or old incumbent data.

Within each accepted family's 20 written instances, propose eight worked
solutions, four misconception corrections, four Socratic hints and four compact
practice marking guides. This yields 200/100/100/100 written instances if all
25 families pass. Each underlying numeric/structural instance appears in only
one mode; do not count format-swapped siblings as extra independent evidence.
MC items require one mathematically unique correct option plus distinct,
machine-checked distractors; explanation quality remains separately graded.
Balance correct-option positions before inference; position shuffling does not
create additional mathematical instances or families.

An initial difficulty budget could be 100 foundation / 250 standard / 150
advanced within each format, but family reviewers must label actual reasoning
demands before it is frozen. Do not label small coefficients "foundation" when
the required conceptual structure is advanced. Curriculum fit must be reviewed;
decision-process or proof families that exceed the intended school level move
to a separately labelled extension stratum, not silently into the main quota.

If only k proposals pass and each supports 20 valid instances per format, the
maximum is 20k MC plus 20k written. A rejection creates a shortfall, not licence
to rename the same family or oversample the survivors. Parameter ranges above
make finite verification implementable; they do not prove 40 distinct useful
instances per family. Review degeneracies, distractor collisions and canonical
duplicates before claiming that capacity.

Twenty-five proposed template families imply **at most 25 mathematical clusters**
before reviewers merge structurally equivalent families; paired MC/written
observations remain clustered together. Candidate coarser dependencies include
domain validation (M01/M04/M06), bounded integer feasibility/optimization
(M07/M09/M10/M23), statistical aggregation/order (M12/M13/M14), and finite
probability/decisions (M15–M19). These are review/sensitivity groupings, not a
post-hoc way to inflate effective sample size. The proposed two-point advantage
and three-point regression margins need a power analysis with the admitted
cluster structure. One thousand rows do not guarantee adequate power.

## Required independent review and admission gates

1. **Graph review before writing instances.** Author a canonical reasoning-graph
   specification and counterexample showing why each proposed indispensable
   step matters. A separate reviewer compares it with active/quarantined local
   families, DeepMind composed modules, TemplateGSM/source-task families and
   known suites. Rename neither old graphs nor wrappers as new families.
2. **Independent exact oracles.** Different implementations of A and B must
   agree over the declared bounded parameter domain or a documented generated
   domain, including boundary/degenerate cases. Mutation tests must detect the
   intended first wrong step. No reused solver result masquerades as a second
   check. Symbolic simplifier success alone is not evidence of correct wording.
   Oracles must solve the visible instance, not rely on hidden generator state;
   independently check the rendered statement against its canonical input and
   ensure that every required datum and assumption is actually provided.
3. **Validity and communication review.** Check positive denominators, valid
   dimensions, feasible data, tie conventions, explicit assumptions, all
   requested parts, unique MC keys and correct distractors. Everything must be
   readable without figures. Instructions should not reward excessive length.
4. **Mode-aware reference rubric.** Verify the mathematical key independently.
   Worked/marking modes require essential justified steps; correction mode
   identifies an actual first invalid step; hint mode tests a valid next step
   without demanding the final answer. Natural-language tutoring quality and
   equivalent explanations still require reviewed grading: a machine-checkable
   answer key does not make free-form pedagogy fully machine-gradable.
5. **Real exclusion audit.** Once a small candidate pool exists, run
   `bench/round2_holdout_audit.py` in place against exact warehouse, selected,
   development and known-suite input receipts. Follow lexical flags with
   semantic graph adjudication; cross-source namespace differences are not
   clearance. An additional reviewed mapping is needed because current audit
   code compares declared family identities rather than inferring graphs.
6. **Missing-data honesty.** Old incumbent training/development rows were absent
   from the initially inspected local locations, but exact artifacts were later
   found and hash/schema-checked in place on Oracle; see the incumbent-coverage
   plan. They have not yet been compared against candidate items. Existing
   warehouse singleton labels do not prove family disjointness. Unknown original
   base-model pretraining overlap is not resolvable from these local checks.
7. **Freeze before finalist inference.** Record admitted/rejected family IDs,
   mode/difficulty quotas, canonical graph mappings, solver/reviewer evidence,
   item/rubric hashes, cluster definitions and statistical decision rules. If
   1,000 defensible maths items cannot be reached, report the shortfall and
   revise the design transparently before seeing any candidate answers.

## Next bounded action

Review the six-family pilot specifications above and decide whether their
reasoning graphs are genuinely different from available training templates.
Only then implement their two independent oracles and boundary/property tests.
Do not build all 1,000 questions, run models, or call the primary battery ready
on the strength of this blueprint.

Independent agent reviewer `full_launch_writer` found no blocking novelty,
capacity or machine-verification overclaim in this design. Their concrete M11
correction is incorporated: half-open intervals can have unattained bounds,
which must not be described as attained extrema. This is blueprint review,
not approval of question instances, curricular calibration, independence or power.
