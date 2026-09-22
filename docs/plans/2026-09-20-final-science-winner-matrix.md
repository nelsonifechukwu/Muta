# Final science-tutor winner decision matrix

Status: prepared before the remaining aggregate evidence is sealed. No winner is
selected here. This is an aggregate-only record: do not paste prompts, model
responses, private candidate mappings, answer keys, or item-level rubric
evidence into this file.

## Decision question

May `p2-half-finalist` replace `incumbent-muta` for the science-tutor campaign?
The candidate may replace the incumbent only when all required evidence is
terminally sealed and identity-matched, the frozen practical and known-suite
regression guards pass, and P2-half has a strict advantage on the combined fresh
tutoring score. Ties, missing or mismatched evidence, and unresolved materiality
default to retaining the incumbent. This is a practical recommendation, not an
official ADTC score, universal superiority claim, or target-CPU qualification.

## Frozen authorities

Record the exact file SHA256 before signing the final matrix.

| Authority | Rule used | SHA256 |
|---|---|---|
| `docs/plans/2026-09-19-science-tutor-selection.md` | Final priority; source-heldout, STEM and tutoring metrics; tutoring is separate from MC correctness | `30c8e3fa5ce5afa886c883d3fcab4c7500bdcf2728c10014613492b068d057ad` |
| `docs/plans/2026-09-19-science-r1-refinement-and-final.md` | Matched five-GGUF final evaluation; retains the frozen decision priority | `b1d96241f7af262ad92304a2afe433478179781d4b56877bfb2bb461a4155ecb` |
| `docs/plans/2026-09-19-final-science-holdout-evaluation.md` | Sealed MC capture/scoring protocol and source-keyed limitation | `1b55ca9d6fbae8fd761d126fe684a7872d7e9c460d3ffdbf80c739b38f4832d1` |
| `docs/plans/2026-09-19-final-tutor-gguf-evaluation.md` | Eight-case final tutoring capture and blinded two-dimension rubric | `e18bcaf56552ec22db0db9e3747a5582725d2a5f5384a2bbaca4553a6edfd600` |
| `docs/plans/2026-09-19-practical-winner-decision.md` | Practical-2000 and known-regression promotion limits | `f288d32c891e829ab1f6cbefc6c839da4b3df11acc6fe22fce8a88ae69808356` |
| `docs/plans/2026-09-19-full-five-gguf-evaluation.md` | Fixed known-suite scoring/review fields and limitations | `0834a65d6000799ec4586afb2124f9d499976b87188814289ec9d5cb5ad02e31` |

## Evidence register

For each pending source, enter only a sealed aggregate path, terminal seal or
completion digest, aggregate digest, row counts, and the candidate identity
join. Do not source values from a live run or partial output. An absent result is
`PENDING`; an invalid or unsealed result is `INVALID` and blocks promotion.

| Evidence | State / terminal receipt SHA256 | Aggregate SHA256 | Required identity and completeness checks | P2-half | Incumbent Muta |
|---|---|---|---|---:|---:|
| Final source-heldout science MC | `SEALED`; `COMPLETED.json` SHA256 `9774acb0c79194d124050e97279bdaeab1fa7fbcc11a1258a2f32035688a2dd9` | `summary.json` SHA256 `61f071e6afa16a7777b58475f1102f5c2f8ab4b2f178793f041b6c8c61a3904e` | Completion says complete; 7,910/7,910 graded rows; join alias and GGUF SHA256 to frozen roster | Correct 1,322/1,582 (83.57%); strict bare-letter 658/1,582; unparsed 2; truncated 0 | Correct 1,322/1,582 (83.57%); strict bare-letter 567/1,582; unparsed 2; truncated 0 |
| Practical winner battery (2,000) | `PENDING` | `PENDING` | Sealed completed result; exactly 2,000 source rows; its frozen authority explicitly includes these exact candidates/model hashes; all four strata and paired-cluster intervals present | `PENDING` | `PENDING` |
| Final tutor review aggregate | `PENDING` | `PENDING` | All eight final cases reviewed for all five masked candidates; mapping joined only after review; science/pedagogy criteria and review receipts valid | `PENDING` | `PENDING` |
| Known-suite addendum | `PENDING` | `PENDING` | Sealed complete known-suite aggregates and frozen review ledger; exact five-model roster/model hashes match | `PENDING` | `PENDING` |

The sealed science result is `provenance/science-tutor-20260919/results/final-science-mc-v2-five-20260919T2308-score/summary.md` and its matching `COMPLETED.json`. Its receipt records capture completion digest `7b351a3251e3873212db2692286233904acbd872097c0613480bada7e49708c8`, 7,910 expected and graded rows, and terminal tree digest `7c7bc2039eed24e404e06e4e99458c060e3a1457072195651e1ed3437c267d38`. The 1,582 MC denominator is per candidate. The keys are source-keyed and are not independently certified for every row.

## Comparison fields to fill from sealed aggregates

### Practical 2,000

Record P2-half minus incumbent for each frozen stratum: maths MC, science MC,
maths structured written, and science structured written; the equal-weight macro;
paired-superfamily bootstrap lower bounds versus incumbent and every contender;
and the frozen interval protocol/receipt. Record known written-core correctness,
complete counts, and semantic MC for each model separately.

First confirm that the sealed practical-2000 protocol and candidate manifest
explicitly cover these exact P2-half and incumbent GGUFs. The separately frozen
`practical-winner-decision.md` rules apply only if that battery's roster and
protocol are the same; do not transfer its thresholds to a different candidate
set or stage. If no frozen authority covers this pair, mark the practical gate
`UNRESOLVED` and retain the incumbent. When applicable, the practical
replacement gate passes only if the frozen rule passes in full: the simultaneous
lower macro bound versus incumbent is greater than +2 points; the lower macro
bound versus every other contender is greater than zero; all four lower stratum
bounds versus incumbent are greater than −3 points; and the known written-core/
complete-count and semantic-MC regression guards pass. Keep the original
denominators and report truncations or failures; do not recompute a new composite.

| Practical guard | Frozen limit | Observed P2-half vs incumbent | Pass? |
|---|---|---|---|
| Lower macro bound vs incumbent | `> +2` points | `PENDING` | `PENDING` |
| Lower macro bound vs each other contender | `> 0` points | `PENDING` | `PENDING` |
| Lower bound in each of four strata vs incumbent | `> −3` points | `PENDING` | `PENDING` |
| Known written core / complete count | No regression | `PENDING` | `PENDING` |
| Completed semantic MC | No decline greater than 3 percentage points | `PENDING` | `PENDING` |

### Known suites

Enter the frozen known-suite columns separately; do not average their different
scales into a new score. Confirm the known-suite addendum binds this exact
candidate roster and suite before applying an allowance from another plan.
Include 50 STEM MC, 50 written STEM with core-correct and instruction-complete
results, judges reviewed `/96`, judges deduplicated `/86`, semantic-MC scores,
and all fixed review-ledger status fields. Report known STEM MC losses as a
count against incumbent.

| Known-suite check | Frozen limit or treatment | Observed P2-half vs incumbent | Pass? |
|---|---|---|---|
| Known STEM MC lost answers | No more than 2 | `PENDING` | `PENDING` |
| Completed written core and complete count | No regression | `PENDING` | `PENDING` |
| Completed semantic MC | No decline greater than 3 percentage points | `PENDING` | `PENDING` |
| Reviewed /96 and deduplicated /86 judges evidence | Fixed rubric/weights; no frozen allowable-decline threshold | `PENDING` | `PENDING` |
| Serious science or tutoring regression in reviewed evidence | Apply the frozen rubric and expose individual dimension/subject results; no new cutoff | `PENDING` | `PENDING` |

For any reviewed known-suite measure without a frozen allowable-decline
threshold, a decline is unresolved rather than silently treated as immaterial;
under this conservative rule it blocks promotion. Preserve agent-based/unblinded
review limitations and exclude the unverified Yorùbá-dependent points as the
known-suite plan specifies.

### Fresh tutoring

From the completed, blinded eight-case aggregate, record the total awarded
science-criterion points and pedagogy-criterion points for each model, each out
of 128 (eight cases × four criteria × four points). Also record the four subject
breakdowns, critical-science-error count/caps, rubric validity, missing
assessments, and whether the blinded review and mapping joins are complete.

Derive the combined score from the frozen equal weights in the development
selection index:

```text
science %  = 100 × science points / 128
pedagogy % = 100 × pedagogy points / 128
combined tutoring % = (science % + pedagogy %) / 2
advantage = P2-half combined tutoring % − incumbent combined tutoring %
```

No minimum effect size or significance claim is added. The tutoring gate passes
only when the full valid aggregate has `advantage > 0`; an exact tie, incomplete
review, or invalid identity join defaults to the incumbent. Keep science and
pedagogy scores, per-subject results and critical-error caps visible beside the
combined value.

| Fresh tutoring measure | P2-half | Incumbent Muta | Difference / status |
|---|---:|---:|---:|
| Science criterion points / 128 | `PENDING` | `PENDING` | `PENDING` |
| Pedagogy criterion points / 128 | `PENDING` | `PENDING` | `PENDING` |
| Combined tutoring percentage | `PENDING` | `PENDING` | `PENDING` |
| Physics / chemistry / biology / Earth science breakdowns | `PENDING` | `PENDING` | `PENDING` |
| Critical-error caps; missing/invalid assessments | `PENDING` | `PENDING` | `PENDING` |
| Strict combined tutoring advantage | — | — | `PENDING`; requires `> 0` |

## Deterministic decision

1. If any required aggregate is not terminally sealed, incomplete, has invalid
   review evidence, or does not bind the same exact P2-half and incumbent GGUF
   hashes, mark `NOT READY`; do not make a winner declaration.
2. If the practical replacement gate fails, any frozen known regression guard
   fails, a material known-suite decline is unresolved, or the combined fresh
   tutoring advantage is not strictly positive, recommend **retain incumbent
   Muta**. Report P2-half as the challenger and show every failed or unresolved
   field.
3. Recommend **P2-half replaces incumbent Muta** only if all evidence is valid,
   the practical replacement gate passes, all known-suite guards pass without an
   unresolved decline, and the combined fresh tutoring advantage is strictly
   positive. Describe this as a practical campaign recommendation; do not claim
   universal superiority or statistical certainty from the eight tutor cases.

## Gaps to disclose

- The frozen science-selection plan prefers higher source-heldout MC accuracy,
  but the sealed result is an exact correctness tie. The current directed final
  rule is no material practical/known regression plus a tutoring advantage; it
  does not say that a source-heldout tie vetoes replacement. This matrix treats
  the tie as no regression and reports it, rather than adding a new MC margin.
- Eight final tutoring cases are diagnostic. The plans define separate science
  and pedagogy scales and call for a combined comparison, but do not define an
  uncertainty method or minimum practically meaningful advantage. The strict
  positive equal-weight difference above follows the frozen selection weights;
  it is not a significance test.
- “Serious” or “material” declines in known judges/tutoring evidence do not have
  a numeric allowance in the frozen plans. Any decline on such an unbounded
  measure remains unresolved and defaults to incumbent.
- Model alias equality is insufficient: every sealed source must independently
  join to the exact same five-roster model hashes and role mapping. If a source
  lacks that join, no cross-source winner decision is valid.
- The existing `practical-winner-decision.md` binds a named five-GGUF roster;
  its thresholds cannot be assumed to govern a different science-tutor roster.
  The pending practical-2000 artifact must identify its own frozen rule and
  include P2-half plus incumbent by exact GGUF hash. The known-suite addendum
  must do the same. Without those bindings, materiality is unresolved and the
  default is incumbent.
- Hardware qualification is separate; this matrix does not turn GPU/Mac
  measurements into target-CPU evidence.

## Final sign-off (leave blank until all three pending sources are sealed)

- Evidence status: `NOT READY`
- Recommendation: `NOT DECIDED`
- Practical gate: `PENDING`
- Known-suite gate: `PENDING`
- Fresh-tutoring gate: `PENDING`
- Decision date / reviewer: `PENDING`
- Final matrix SHA256: record in the delivery message after all edits.
