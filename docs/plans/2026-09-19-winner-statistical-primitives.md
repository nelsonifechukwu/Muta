# Winner-test statistical primitives — synthetic-only development

This is a bounded implementation step under the original winner-test design,
not a benchmark freeze or another analysis of the completed known suites.
The independent battery still has zero admitted items/families. Do not load
model responses, generate inference, change grades, select a winner, or publish
private source text during this work.

## Implementation scope

Implement and independently test `bench/winner_battery/statistical_primitives.py`
using synthetic normalized scores for five anonymous model slots. Keep this
module separate from the completed comparison compiler and the audit-only
candidate loader. There is no CLI or real-data adapter in this step.

1. Strict input validation: bounded, unique item IDs; explicit family IDs;
   exactly the existing four strata; five finite scores in [0,1] per item;
   reject booleans, missing/extra values, empty strata, and singleton-family
   support. Identifier assertions are not proof of independent families.
2. Aggregate sums/counts by the union of family IDs across all strata. Apply
   one shared family-weight vector to every stratum and every model, preserving
   both model pairing and dependence where a family occurs in multiple strata.
   Compute each stratum's item-weighted mean, then the equal four-stratum macro
   mean. Do not silently replace this with an equal-family estimand.
3. Register exactly 26 contrasts: ten unordered primary model-pair differences
   and sixteen challenger-versus-slot-zero stratum differences. Slot zero is
   an anonymous stand-in for the eventual preregistered incumbent.
4. A bounded seeded family-resampling primitive may generate synthetic contrast
   distributions. Fail explicitly if a replicate has an empty stratum; do not
   discard/redraw it, change clustering or emit a partial usable result.
   Preserve canonical item/family ordering, the RNG/version and distribution
   identity. No confidence coverage or sample-size adequacy is claimed.
5. Test draft winner predicates on supplied synthetic simultaneous intervals:
   positive lower bound versus every other slot, lower bound above the original
   +2-point incumbent gain and above the −3-point per-stratum regression margin.
   These are predicates, not a confidence-interval procedure or promotion gate.

Use independent hand-calculated / expanded-row oracles for aggregation,
unequal-family sizes, cross-stratum family coupling, permutation invariance,
all 26 contrast orientations, paired zero differences, invalid/degenerate inputs
and exact threshold cases. Have a separate agent adversarially review the code
and tests before accepting the implementation. Do not run synthetic sensitivity
experiments against real model scores or optimize settings based on them.

## Unresolved inferential gates

The confidence construction, multiplicity calibration, independent-family
counts, family-size imbalance, finite-sample coverage, Monte Carlo precision
and power are **not frozen**. In particular, a Bonferroni division by 26 cannot
repair invalid marginal bootstrap intervals or too few independent clusters.
No arbitrary minimum-family threshold is evidence that coverage/power is good.
The two-family guard above only prevents a trivial computational degeneracy.
The rubric-to-score mapping and source-family admission also remain open.

Independent design review recommended the same global shared weights, while
emphasizing that curated-family exchangeability and the fixed-quota sampling
design still need validation. A future conservative baseline could allocate
family-wise alpha 0.05 across all 26 events: ten two-sided macro intervals and
sixteen one-sided stratum lower bounds. Their endpoints could serve both the
zero and +2-point thresholds without adding hypotheses. This is a design
candidate only: no intervals, p-values, multiplicity correction or valid
coverage are implemented or asserted by this primitives module.

Before real inference, freeze and independently review the exact executable
rubrics, statistical protocol, margins, seeds/counts and family/stratum quotas,
then bind them to the admitted dataset and runtime hashes. This module cannot
certify any of those external facts or target-CPU deployability.

## Primary mechanics references checked 19 September

- [SciPy bootstrap API](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html)
  explains paired resampling with common indices and distinguishes percentile,
  basic and BCa intervals. It does not establish this campaign's cluster
  independence, coverage or sample-size adequacy.
- [statsmodels multiple-testing API](https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html)
  documents correction methods. Using a correction is separate from validating
  the underlying inferential quantities.
- [Cameron–Miller, cluster-robust inference, Section VI](https://cameron.econ.ucdavis.edu/research/Cameron_Miller_JHR_2014_July_09.pdf)
  explains why few or imbalanced clusters can undermine inference and why
  there is no universal sufficient-cluster cutoff. Its regression setting is
  not direct validation of this campaign's curated four-stratum score.

Our global-family resampling is a proposed campaign implementation, not a
direct claim that either API implements the full four-stratum design for us.

## Implemented and independently reviewed

The module is present at
[`statistical_primitives.py`](../../bench/winner_battery/statistical_primitives.py),
SHA256 `f5365b9db38f2c4dc9a6a058f82c48eabea5c3de0929c16160d6016555b1aa71`.
It has no corpus/model loader or CLI. Low-level array helpers require an exact,
unmasked NumPy ndarray, rejecting boolean/string/object dtypes and non-array
coercion; top-level score rows receive explicit scalar checks. An invalid
empty-stratum resample aborts the entire call, with no usable partial result,
rather than conditioning on successful draws. Input origin and family
independence are explicitly unverified by the primitive.

| Verification | Observed scope |
|---|---|
| Root-authored synthetic tests | 60 passing |
| Independently authored adversarial tests | 7 passing; root read and reran them |
| Exhaustive five-family weight compositions | 126 total: 113 valid, 13 empty-stratum failures correctly rejected |
| Independent contrast oracle | Exact Fraction expanded rows; all 26 orientations for each valid composition |
| Draft predicate checks | All four challenger slots, strict +2/0/−3 boundaries and immediately inside boundaries |
| Combined statistical/M02/audit regression suite | 201 passing; Ruff passed |

Initial synthetic invalid-input tests caught giant-integer `isfinite` overflow.
Independent review also caught helper coercion accepting mixed booleans and
echoing string-conversion errors. Fixed-code errors and ndarray-only low-level
contracts address these cases, including masked-array missingness. The failures
were development tests, not model runs or failed training attempts.

Separate reviewer `warm_export_review` approved the exact source hash above for
**synthetic mechanics only**, after verifying unequal family sizes, partial
cross-stratum overlap, paired weights, canonical ordering, nonmutation, sign
reversal and guards. This does not approve confidence coverage, corpus
independence, a real-data adapter, battery freeze, promotion or inference.

An anonymous 24-row / three-family fixture was run with seed 20260919 and 256
replicates. Its 256×26 contrast-distribution hash, weight hash, code/test hashes
and NumPy/Python identities are in the
[synthetic execution receipt](../../provenance/evaluation/winner-battery/statistical-primitives-synthetic-20260919.json).
An identical replay reproduced both hashes. No real model score was consumed,
no interval was estimated and no real model was evaluated by winner predicates.
These toy labels/replicates are not adequate independent-family evidence.

Next statistical gate: use an admitted, reviewed family/stratum design to
specify the target population and assumptions, calibrate a candidate confidence
procedure and multiplicity rule on synthetic null/boundary/imbalance cases,
assess power and Monte Carlo precision, then freeze everything before fresh
finalist inference. Until then this remains development infrastructure only.
