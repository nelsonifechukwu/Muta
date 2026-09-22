# First mathematics-family feasibility crosswalk

18 September 2026. **Design/inspection only; zero newly authored questions,
zero admitted families, zero new model outputs.** This is not a corpus-wide
contamination clearance, a frozen benchmark, or a finding of statistical power.
No downloads, remote access, training changes or large dataset copies were used.
Paths are repository-relative unless stated otherwise.

Update, 19 September: the M18 solver prototype was completed and independently
tested, but M18 itself is now conservatively excluded from the fresh primary
authoring queue. The earlier priority recommendation below is superseded by
`2026-09-19-m18-primary-family-decision.md`. This does not admit any other family.

## Decision and next bounded action

| Blueprint family | Decision at this checkpoint | Reason / next gate |
|---|---|---|
| M02: parameter-dependent linear systems | **Needs review before item authoring** | Local solver is narrower; the DeepMind matrix sampler now has an independently reviewed intended-nonsingularity finding (19 September addendum), not whole-source clearance |
| M08: capped ordered state updates | **Needs review before item authoring** | A sampled TemplateGSM task already has ordered proportional then fixed losses; uncapped composition is not novelty. Require essential clipping and compare ordered trajectories |
| M12: subgroup/aggregate reversal | **Needs review before item authoring** | Weighted aggregation is distinguishable from the inspected single mean/ratio tasks, but the 878 TemplateGSM families and science-table sources remain unmapped |
| M18: marginal totals and non-identifiability | **Provisional solver-spec authoring only; priority 1** | Small complete domain and independent exhaustive oracle are feasible; source-family review and item admission remain blocked |
| M20: noncommuting coordinate maps | **Needs review before item authoring** | DeepMind polynomial composition is a plausible graph neighbour. Changing dimension alone is not independence; orientation alone cannot distinguish reversed affine-map order |
| M25: universal modular claims | **Provisional solver-spec authoring only; priority 2** | Finite residue coverage has a checkable proof obligation, unlike a numerical factor check; composed number/polynomial and known proof sources still require semantic review |

“Provisional” permits a separately planned, independently reviewed mathematical
oracle/property-test prototype on abstract inputs—not rendered questions,
training data, candidate answers or benchmark admission. All six remain
**needs-review for primary-test family independence**. Do not silently change
the whole-warehouse exclusion rule to make these proposals admissible.

Recommend implementing **only M18's two abstract solvers and boundary/mutation
tests next**, after the parent approves the bounded implementation scope. It is
not necessary to produce the proposed 48-question six-family pilot to learn
whether its mathematics is sound. Existing frozen training inputs stay untouched.

## Exactly what was inspected

| Evidence | Scope read in this pass | What it establishes / does not establish |
|---|---|---|
| `docs/plans/2026-09-18-full-data-winner-test-design.md`, `2026-09-18-winner-math-family-blueprint.md`, winner-test inventory and incumbent-coverage note in the same directory | Current design, graph definition, coverage status and next-action boundaries | Target remains 2,000 overall / 1,000 maths, not materialized. Incumbent files were located remotely by the parent; not inspected remotely here |
| `ROADMAP.md` evaluation section, lines 346–358 | Temporal exclusion, MC/written distinction and contamination cautions | Background constraints, not new empirical contamination evidence |
| `model-development/finetune/muta_dataset_v2/generators.py` | Function/family inventory; bodies of `_simultaneous`, `_sequence`, `_mean`, `_ratio`, `_probability`, `_water_tank_volume` | Direct graph evidence for six relevant local generators; not a re-audit of all generated rows |
| `data/muta-stem-v2-warehouse-20260916-v7/manifest.json` | Source counts; all 56 DeepMind module names; 878 TemplateGSM IDs/counts; source-cache receipts | Names/counts, not semantic definitions. Manifest inspected/hashed; 102 shards not rehashed |
| `model-development/finetune/muta_dataset_v2/adapters.py` | TemplateGSM adapter, lines 562–686; DeepMind loading/adapter, lines 1132–1289 | Template IDs become family labels; DeepMind labels are flattened training-module names. Neither is an inferred canonical reasoning graph |
| `templategsm_full_audit.json` and `templategsm_filter_audit.json` beside the adapter | Keys, configurations, counts, rule/limitation fields, template-ID classifications | Prior static audit describes 2,000 templates / 2M upstream rows; 1,638 passed its narrow static rules and 362 failed. This pass did not rerun that audit, and its labels are not semantic clearance |
| Warehouse `provenance-source-evidence/template_gsm/README.md` | Configuration/schema sections and source description | Template-ID semantics; publisher correctness claims are not adopted as independent verification |
| Warehouse `part-00086.jsonl` through `part-00099.jsonl` | **First row only of each: 14 TemplateGSM rows / 14 IDs**, task structure inspected without copying prose into this note | Deterministic boundary sample, not random/representative; 864 of 878 warehouse template IDs have no task-structure inspection here. Even each sampled ID has only one inspected instance |
| Warehouse `part-00000.jsonl` | First 1,000 rows' source/family metadata only; first-row schema | All 1,000 belong to one local family; not 1,000 semantic inspections. Also inspected first-row metadata only of parts 00044 and 00085, both DeepMind |
| `bench/judges_prompt_suite.py`; `bench/stem_prompt_suite.py`; `bench/live_prompt_battery.py`; `bench/eval_items.json`; `bench/submission/metadata.json` | All prompt definitions: 10 judges positions (9 unique), 100 STEM, 4 live, 18 eval fixtures, 2 submission positions | Known local suites, with duplicates across sources. No inference or model-response review performed |

Both manifest-recorded local source-cache directories are absent:
`data/source-cache/deepmind-mathematics` and
`data/source-cache/templategsm-2000-1k-0c8ed6b`. A repository filename inventory
also found no vendored DeepMind module implementation. No source recovery was
attempted. The DeepMind revision receipt is
`427f45075f84b8b9774950196ad63867ca20ffb3`; TemplateGSM's is
`0c8ed6b60fea0a84f25ddb1b8b761db695df2e19`.

### Small TemplateGSM structure sample

Every location is line 1 of the indicated warehouse shard. These are abstract
task dependencies, not copied wording, validated answers or a template taxonomy.
No sampled task is approved for correctness by this inspection.

| Shard suffix | Template ID | Observed task graph |
|---|---|---|
| 00086 | 1208 | Infer second quantity by a ratio; apply common proportional growth; sum |
| 00087 | 1740 | Add an offset to one quantity; sum the two quantities |
| 00088 | 642 | Listed travel distances; target described ambiguously as halfway through tasks; no graph clearance |
| 00089 | 218 | Chained additive offsets between three quantities; sum |
| 00090 | 1654 | Rectangle perimeter minus two gaps |
| 00091 | 1461 | One dimension and aspect ratio determine area |
| 00092 | 1085 | Equal-group product plus additional quantity |
| 00093 | 1241 | Square cross-section and height determine volume, then density determines mass |
| 00094 | 523 | Weekly consumption to annual demand, then package count; calendar/rounding assumptions need review |
| 00095 | 1658 | Chained multiplicative conversion factors |
| 00096 | 802 | Nominal capacity minus loss, then per-unit yield |
| 00097 | 193 | Invert a proportional increase |
| 00098 | 1162 | Subtract consumption; divide remainder by equal share |
| 00099 | 1976 | Proportional loss followed by fixed loss |

In particular, “two sequential updates” or the word “capacity” cannot establish
M08's novelty. Neither the capacity-minus-loss sample nor this tiny boundary
sample proves presence/absence of a genuinely clipped state-machine family.

## Canonical graphs and nearest neighbours

These are proposed graph specifications, not question instances. Canonicalize
names, units, coefficients, option permutations and presentation modes away.
Retain domains, targets, essential branches and dependency edges. An additional
step counts only if removing it changes the task's required reasoning.

### M02 — parameter-dependent system classification

- **Inputs/domain:** two real unknowns; a 2×2 coefficient matrix and RHS vector
  whose entries are affine integer functions of a parameter; a finite stated
  parameter set initially contained in −6…6. Coefficients bounded in magnitude
  by 4. Output is the zero/one/infinite-solution classification for each allowed
  parameter, not merely a solution at one nonsingular value.
- **Graph:** substitute parameter → coefficient/augmented matrices → rank or
  equivalent elimination case → inconsistent / unique / non-unique. Require
  at least two distinct classifications including a singular case; treat zero
  rows correctly rather than dividing by a possibly zero coefficient.
- **Nearest direct evidence:** `_simultaneous` explicitly resamples until its
  determinant is nonzero, then uses Cramer's rule. `bench/eval_items.json:q07`
  is an ordinary fixed-system solve. These omit parameter-dependent singular
  consistency. Follow-up inspection of the pinned `algebra__linear_2d` and
  `algebra__linear_2d_composed` paths found intended nonsingular numeric solves:
  the matrix sampler explicitly rejects zero determinants; composed handles
  replace fixed constants, not freely varying parameters. See
  `2026-09-19-m02-deepmind-source-gap-closure.md` for the exact source hash,
  physical lines, numerical/runtime limits and completed narrow root review.
  This narrow update does not admit M02 or clear other source families.
  The subsequent `2026-09-19-m02-warehouse-lexical-inventory.md` reports a
  hash/count-verified prompt-only scan of all 2,500,350 warehouse rows, with
  zero explicit lexical candidates and no semantic row inspections. Its
  negative result and matcher controls do not establish graph absence;
  M02 remains unadmitted.
  New bounded source-role work is recorded in
  [the incumbent counterexample screen](2026-09-19-m02-incumbent-counterexample-screen.md)
  and [private-neighbour review](2026-09-19-m02-private-neighbour-review.md).
  These include positive lexical matches and limited semantic inspections,
  not a corpus-wide graph clearance or permission to author admitted items.
  The [four retained conservation-pair boundary decision](2026-09-19-m02-conservation-boundary.md)
  distinguishes shared constraint operations from M02's indispensable changing
  consistency branch under the existing definition. Missing original choices
  and broader source families remain unresolved; M02 is still unadmitted.
- **Reject reductions:** every permitted parameter is nonsingular; change only
  numbers or names; append a determinant statement without a genuine branch.
  Distinguishing “determinant zero means infinite” from inconsistent systems is
  a required mutation test. Symbolic minors versus exact elimination can form
  independent oracles, but graph admission waits for broader family review.

### M08 — bounded, clipped, ordered state transitions

- **Inputs/domain:** integer state 0≤s≤C, 1≤C≤40; fill amount a and drain amount
  b in 1…C; 2–6 periods. Define F(s)=min(C,s+a) and D(s)=max(0,s−b), with clipping
  at **each** substep, not once after a combined net update. Compare trajectories
  under D∘F and F∘D from the same initial state.
- **Graph:** state → first update/active clipping branch → second update/active
  clipping branch → next period; compare specified terminal states. Require
  active clipping and a nonzero order effect on the requested output. A declared
  capacity that is never reached adds no essential branch.
- **Nearest evidence:** `_sequence` has constant increments; `_water_tank_volume`
  computes geometry/unit conversion, not dynamics; STEM M27/M30 are constant-rate
  depletion and M32 successive fractional remainders. Sampled TemplateGSM 1976
  has ordered proportional/fixed loss, and 802 nominal capacity minus loss.
  DeepMind sequence and composed arithmetic labels remain unresolved.
- **Reject reductions:** ordinary progression, cap-free loss calculation, or
  only changing update order with no effect. Test the mutants “net update then
  clip,” swapped order and omitted floor/cap. Inspect additional state-process
  TemplateGSM/GSM8K families before any question authoring.

### M12 — subgroup comparison versus pooled comparison

- **Inputs/domain:** two alternatives across two subgroups; integer successes
  0≤x≤n with subgroup denominators 1≤n≤40. All four denominators are given.
  Require strict same-direction comparisons within both subgroups and a strict
  reverse comparison after pooling; no ties or zero denominators.
- **Graph:** four rates → two within-subgroup comparisons; separately pool
  successes and denominators → aggregate rates → opposite comparison → explain
  different subgroup weights. It is a descriptive aggregation result, not a
  causal conclusion or proof that either alternative is universally better.
- **Nearest evidence:** `_mean`, `_ratio`, STEM M12/M14/M41 and judges
  `human_01` already involve denominators/weighting in other structures.
  DeepMind comparison/arithmetic module names cannot rule out this composition.
  None of the 14 sampled TemplateGSM structures has this full graph, which says
  nothing about the other 864 IDs or unseen instances.
- **Reject reductions:** single mean/weighted average, denominator change only,
  no actual ranking reversal, or a fabricated causal explanation. Rational-rate
  and cross-product oracles are feasible; curriculum fit and semantic-family
  review are unresolved before item authoring.

### M18 — fixed marginals do not fix an intersection

- **Inputs/domain:** total N in 2…40, two set counts r,c in 1…N−1, otherwise
  unconstrained joint membership. Target is the complete integer range of the
  intersection x and two distinct compatible tables demonstrating that a unique
  intersection cannot be inferred. A later conditional-probability variant
  divides by an explicitly nonzero, specified margin; it is the same family.
- **Graph:** fixed margins → nonnegative four-cell constraints → feasible range
  max(0,r+c−N)≤x≤min(r,c) → two endpoint table witnesses → non-identifiability.
  The cells are x, r−x, c−x, N−r−c+x. No independence assumption is supplied or
  inferred. Proper margins give more than one possible integer intersection.
- **Nearest evidence:** quarantined `_probability`, STEM M21/M40 and DeepMind
  `probability__swr_p_level_set` / `probability__swr_p_sequence` involve probability,
  but the directly inspected local/suite tasks use a determined sample space.
  The DeepMind module semantics and private table questions remain unresolved.
  Blueprint M15 is a declared close family: a reviewer may merge them if its
  conditional-table graph already includes unknown-joint feasibility.
- **Reject reductions:** all four cells already supplied, a unique feasible
  joint table, or independence introduced only in the solution. The novel
  proposed target is the set of compatible answers, not a changed denominator.
- **Smallest solver pilot:** A derives the bound interval algebraically. B
  independently enumerates all nonnegative four-cell tables with total at most
  40, groups them by total/row/column margin and collects intersection values.
  There are 20,540 proper-margin (N,r,c) cases and at most 135,751 tables including
  unused boundary cases. Compare full feasible sets and witness constraints;
  do not let B call A's bounds. Test swapped margins, wrong lower-bound sign,
  omitted nonnegativity, and a fabricated independence assumption. These are
  abstract solver tests, not evaluation-question generation or family clearance.

### M20 — noncommuting two-dimensional affine maps

- **Inputs/domain:** an explicit translation and a nonidentity reflection or
  quarter-turn rotation, with small integer/rational coordinates. Require a
  map that couples coordinates and a translation vector not fixed by it. State
  composition order unambiguously; require at least one stated point for which
  the two orders give different coordinates.
- **Graph:** point → first map → second map; repeat reversed order → compare
  coordinates/map difference → explain why the order matters. Exact affine
  matrices versus independent coordinate substitution are feasible oracles.
- **Nearest evidence:** DeepMind `polynomials__compose` is a serious unresolved
  composition neighbour; a new dimension is not automatically a new graph.
  Directly read local/suite geometry tasks do not compose coordinate maps, but
  private geometry and the unsampled TemplateGSM families were not inspected.
- **Reject reductions:** one map, commuting maps, a chosen fixed point that
  hides the order effect, or an orientation-only target. For nonsingular affine
  maps, det(AB)=det(BA): the orientation sign and area scale are the same in both
  orders. Signed-area checks can verify implementation, **not** supply a novel
  order-discrimination branch. The restricted class is a specification to review,
  not clearance from generic function-composition training.

### M25 — universal divisibility via complete residue coverage

- **Inputs/domain:** integer polynomial P of degree at most three and modulus
  2…12. Require the target “for every integer n, the modulus divides P(n)” with
  a proof if true or explicit counterexample if false. Reject constant or
  coefficientwise-trivially-divisible forms for the proposed reasoning pilot.
- **Graph:** integer-polynomial periodicity modulo m → all residue classes
  0…m−1 → exact residue evaluations → universal proof / violating residue.
  The proof that n and n+m give equal residues is indispensable: checking a
  convenient finite list of integers is not a universal proof.
- **Nearest evidence:** DeepMind `numbers__is_factor[_composed]`,
  `numbers__div_remainder[_composed]`, polynomial evaluation/expansion; STEM M24
  numerical gcd, M50 converse/counterexample, and live `sqrt2_proof` quantified
  proof reasoning. None is a demonstrated exact graph match from the inspected
  definitions; module names cannot exclude a universal-claim variant.
- **Solver-only follow-up:** Horner modular evaluation plus residue table versus
  a separately implemented binomial-expansion periodicity certificate and direct
  power evaluation. Include negative integers in certificate tests, true and
  false claims, missing residues and invalid “many examples imply all” mutations.
  Canonicalize coefficient residues so congruent polynomials do not inflate
  family/instance counts. School-level suitability of the proof demand needs
  explicit curriculum review before any primary-test quota is assigned.

## Limits and promotion gates

1. **Metadata is not a graph audit.** The 56 DeepMind names and 878 TemplateGSM
   IDs are not 934 reviewed graph specifications. The 14 boundary samples are
   deliberately bounded and cannot estimate prevalence or absence. No negative
   match statement here applies to all 2,500,350 warehouse rows.
2. **Other exposure still matters.** No row-level semantic scan of selected
   300,350, development 5,000, private exam rows, GSM8K/QASC, prior output archives
   or all archived prompt sources was performed here. Exact incumbent 10,756/566
   inputs were located/validated by the parent, but remain unexamined in this
   local crosswalk. Unknown base pretraining overlap remains unknown.
3. **Review graph equivalence across namespaces.** M08/M20 share an order-of-
   composition concept; M12/M18 share tables but different targets. Review both
   fine family assignments and coarser dependency clusters before power analysis.
   Neither differing source IDs nor added coefficients prove independence.
4. **Then author a small pool, not the quota.** After graph/solver review, separately
   authorize a small item pilot; validate visible wording, independent reference
   answers, unique MC options and mode-aware tutoring rubrics. At most six initial
   mathematical families are under consideration—not 48 independent observations.
5. **Only later run exclusion tooling.** Bind candidate hashes and reviewer
   evidence, then stream exact manifest inputs through `bench/round2_holdout_audit.py`.
   Its lexical/declared-family findings do not perform this semantic graph review.
   Follow any source-access gap honestly; do not mark the benchmark ready.

## Inspection identities

SHA-256 of the small inspected files; these are receipts, not revalidation of
their historical claims or of the multi-gigabyte corpus:

| File (paths above) | SHA-256 |
|---|---|
| `generators.py` | `5e6a4ebe19a8de8c85dba45327cbc743ce7b19048b224eb9198b8dcbc9384631` |
| `adapters.py` | `bd50a2c4967c32af7427b1f01de36a4b245cd891b6619b7f36aab68973fd3562` |
| Warehouse `manifest.json` | `2cf8d2b92dc5a92b19d5d5f714e7a064912a91c215178f3b23cd2fda6fd94ab1` |
| `templategsm_full_audit.json` | `b5d59434b340132f3d149dc74603d5c289a6ababc5ff2979f39d4c9fb17969e0` |
| `templategsm_filter_audit.json` | `b978547bb908320ac0097785a17e016c81ce9a5cc77b39054390e6ccab5e4cbd` |
| `bench/stem_prompt_suite.py` | `9d40d48c0ce2a2484fde45dfc75fa550123d7a70f7edef5c2c7978c21ecfe4a2` |
| `bench/judges_prompt_suite.py` | `2b6a50269c59e458667c96ed0c5662b5a8a748c1e05ea29a9dfd8f9f27edceab` |
| `bench/live_prompt_battery.py` | `1636d940f145a50ac21c3ecf656c8b336673bbf3e617d44d10f30d36f50dc65b` |
| `bench/eval_items.json` | `bb176fa7bb2162348f5fd2cab5008b2d375594d2f630647ca9031666ffc54869` |
| `bench/submission/metadata.json` | `75e8a225fba9fd2c1c6c3ca0fbe655fc2c1f1211854e730468bda5bc72b2784e` |

Independent agent reviewer `full_promotion_audit` returned GO as solver-spec
feasibility only. They independently checked the 20,540 margin-case / 135,751
table counts, proper-margin non-identifiability and affine-orientation correction,
and checked local generator/suite neighbours. They did not re-read all sampled
corpus prose or certify semantic disjointness. This note changes no frozen
winner-test criteria.
