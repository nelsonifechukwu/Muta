# Proposed full-data winner test

Status: design recorded before the three full-data runs. The fresh battery,
answer keys and evaluator are not yet materialized or frozen. Do not present
this as completed evaluation or as an official ADTC grading protocol.

## Five contenders

1. Previous Muta Tutor Qwen2.5-1.5B (incumbent).
2. Unchanged 20K warm-r16-lr5e6 pilot.
3. New clean-base full-data candidate.
4. New Muta-v1 full-data candidate.
5. New full-data continuation of the selected warm pilot adapter.

Select one checkpoint per new treatment using the frozen development criterion,
before opening final-test outputs. Do not choose best/final checkpoints using
the locked test. Every model is evaluated as its final Q4_K_M artifact with the
same prompts, template, runtime, token budget and deterministic sampling.

## Independent quality battery

Target 2,000 new held-out questions: 500 each in mathematics MC, science MC,
mathematics written/tutoring, science written/tutoring. Freeze topic, difficulty
and tutoring-mode quotas before model inference. Verify answers and rubrics
independently. Exclude exact, paraphrase and generated-family overlap with all
accessible training and development sources, including the 2.5M warehouse and
pilot-selection suites. Document exclusions and unknown base-pretraining
contamination; this cannot establish freedom from unknown pretraining exposure.

This size is a starting design, not a guarantee of statistical power. Assess
independent family counts and power before unblinding. Do not keep adding
questions after seeing which model is ahead until a preferred result appears.

Proposed internal primary score: an equal-weight macro-average of the four
strata, on a 0–100 scale. MC answer correctness and explanation/format are
separate; written mode-aware scores distinguish incorrect central reasoning,
correct but incomplete help, and complete correct help. Socratic responses
must not be penalized simply for appropriately withholding the final answer.
Freeze exact rubric credits and aggregation before outputs; do not retrofit
weights to favor a candidate. This internal score is not official S_acc.

Mask model identity, shuffle presentation order, verify objective answers with
appropriate arithmetic/symbolic/unit checks, and independently review grading
disagreements plus a randomized sample of agreements. State whether reviewers
are agents or humans. Unverified language criteria remain explicitly unscored
unless a qualified language reviewer is available.

## Evidence for a clear winner

- Predeclare a practically useful primary-score gain and unacceptable regression
  margins for the major skill strata before inference. Proposed starting values
  are +2 primary points versus incumbent and at most 3 percentage points of
  regression per major stratum; feasibility/power must be assessed before freeze.
- Use paired differences on identical questions, with family-cluster resampling
  so variants are not treated as independent evidence. Account for all planned
  finalist comparisons. Freeze the confidence-interval procedure, multiplicity
  correction and resampling seed/count in the executable protocol.
- A clear quality winner must have an uncertainty-supported primary advantage
  over the other contenders, the practically useful gain over the incumbent,
  and bounds ruling out the predeclared material regressions. Failure to detect
  a significant regression is not proof of non-inferiority.
- If the evidence cannot separate finalists, report an inconclusive comparison
  or unresolved trade-off, not equivalence unless an equivalence test supports
  that claim. Retain the incumbent by default; do not manufacture
  certainty or redefine the metric after seeing results.

The known judges10/STEM100 suites remain secondary regression reports. Judges10
contains a repeated question and four previously unverified language points;
report deduplicated and language-verification status. Existing ARC-Easy results
and reused public questions are labelled separately, not called fresh holdouts.

## Deployable winner

Run final GGUFs on the target CPU path: repeated throughput, TTFT, whole-process
RSS, crash/OOM, context/stop behavior and available thermal measurements. Use
the repo's pinned score-of-record profiler separately from product-level tests;
do not substitute the internal tutoring score for official profiler accuracy.
Report missing target hardware or sensors as unmeasured, not a pass. GPU quality
screening and Mac timings cannot establish target-laptop qualification.

Choose a deployment replacement only when it passes the hardware constraints
and the frozen quality decision rule. Report quality and the profiler score
separately if their rankings disagree. A highest numerical score is not by
itself a clear, generalizable overall win.

## Statistical implementation references

- [SciPy paired bootstrap](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html)
- [statsmodels multiple-test corrections](https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html)

These support implementation mechanics; neither establishes the proposed sample
size, task weights or practical margins as universal standards.
