# M18 private-source crosswalk

18 September 2026. Scope: local, bounded source inspection only. No question
authoring, new model outputs, corpus modification or benchmark admission.
The completed abstract marginal solver is not evidence of family independence.

## Inspection plan

1. Resolve the exact private append partitions from both existing manifests.
   Verify their bytes, SHA256, parsed row counts, source counts and row-ID bindings
   in place; do not scan arbitrary portions of the 2.5M warehouse.
2. Inspect existing topic/review/provenance evidence for all 350 appended rows.
   Locate possible set-count/table/probability neighbours without printing private
   question text. Record only source/row IDs, hashes and abstract task graphs.
   Keyword absence is not a negative semantic verdict; unresolved rows remain so.
3. Read complete relevant local generator functions and known-suite definitions.
   Distinguish fixed/interpretable counts from M18's unknown-joint feasible range,
   endpoint witnesses and non-identifiability target.
4. Report exact coverage and gaps. Seek parent review of the evidence note;
   do not approve M18 or any item for the proposed fresh benchmark.

## Outcome

Subsequent decision, 19 September: root adopted conservative exclusion of M18
from the fresh primary battery based on this positive neighbour, without needing
negative clearance of the other 307 rows. See
`2026-09-19-m18-primary-family-decision.md`. The bounded coverage and evidence
below remain unchanged; the earlier pending-authoring wording is historical.

**M18 remains unadmitted; item authoring should wait for family adjudication.**
All 350 private rows were exactly located and metadata/keyword screened. Actual
prompt/completion semantics were read for **43 rows** (17 initial set/probability
matches plus 26 broader table/bounds/probability matches); **307 rows were not
semantically cleared**. The 43 inspected tasks do not request M18's complete
unknown-joint feasible range plus two witnesses/non-identifiability explanation.
That bounded observation is not a claim of absence across all 350 or the warehouse.

A three-set survey neighbour has a genuine prompt/answer-assumption ambiguity:
its stored unique singleton counts require an unstated exhaustive-union assumption.
Independent parent review confirmed this finding and the two feasible-table
witnesses below. It is **not a generic arithmetic error**: the stored result is
conditionally valid when the outside region is zero. The question's existing
counts/constraints expose latent non-identifiability closely related to M18,
even though it asks different targets and supplies no range/witness rubric.
Record it for a future dataset revision and conservative family review. **No
frozen input, current training artifact, training run or source row was changed.**

## Exact partition and coverage receipts

The two manifests independently list the same private append IDs and shard
identities. All four actual shard files were rehashed; corresponding warehouse
and selected shard hashes match byte-for-byte. Only these approximately 2 MB
private partitions were inspected, not arbitrary warehouse ranges.

| Source | Selected shard under `data/muta-stem-v2-sft-300k-quality-first-20260917-v1/` | Corresponding warehouse shard under `data/muta-stem-v2-warehouse-20260916-v7/` | Rows / bytes | Actual SHA256 |
|---|---|---|---|---|
| WAEC e-learning | `part-00012-private-waec-e1720e95858d.jsonl` | `part-00100-private-waec-e1720e95858d.jsonl` | 47 / 296,036 | `c165a0e0f7ede07b9e2843aef5ac714c88b45dbdfd73f99d733d3b35b115bb4e` |
| Cheetah | `part-00013-private-waec-363447d90421.jsonl` | `part-00101-private-waec-363447d90421.jsonl` | 303 / 1,716,873 | `9514e87da6237cd0f2dd9b6f73d19d7ba447ea83ecfb333cf45e8778f22648c6` |

- Append IDs: `muta_private_waec_append_v1_1b73164d0c67e1720e95858d`
  and `muta_private_waec_append_v1_c0cabc4e7db6363447d90421`.
- Parsed rows: 350; unique training IDs: 350; unique source record IDs: 350.
  Source record IDs exactly equal the selected manifest's 350 append review
  receipt IDs after removing only the explicit `private_training:` prefix.
- Subjects: 311 mathematics, 30 physics, 6 chemistry, 3 biology. Every row's
  topic is the generic `waec_exam_practice`; family labels are singleton row IDs,
  not reviewed semantic families.
- Selected manifest SHA256:
  `93b7dbcbad72350e099d8951effcbc9a253693dc364b25ffc165102a6e844f4e`.
  Warehouse manifest SHA256:
  `2cf8d2b92dc5a92b19d5d5f714e7a064912a91c215178f3b23cd2fda6fd94ab1`.
  Other manifest-listed shards were not rehashed in this task.

Initial broad prompt/completion/review-note keyword screening was noisy because
review boilerplate includes words such as “independent.” The **actual semantic
shortlist** therefore used prompt-only screening, followed by direct read-only
inspection. Initial 17 matches were all Cheetah; expansion added 19 Cheetah and
7 WAEC rows, producing 36 Cheetah + 7 WAEC = 43 distinct semantic inspections.

The initial case-insensitive selector was:

```text
venn|intersection|union|neither|\bboth\b|cardinal|two.way|contingency|marginal|
least possible|greatest possible|maximum possible|minimum possible|
cannot be determined|not enough information|independent events|
mutually exclusive|∩|∪|\bsets?\b
```

Expansion additionally used `least`, `greatest`, `minimum`, `maximum`, `range`,
`possible`, `cannot`, `insufficient`, `not enough`, and whole-word `table`,
`frequency`, `survey`, `sample`, `probability`. Substring false positives were
retained and inspected; for example, a statistical “range” or an unrelated
word containing that sequence is not a marginal-feasibility task. This method
is a recall aid, not a semantic classifier or completeness proof. Alternate
wording in the other 307 rows remains an explicit gap.

## Initial 17 semantic findings

All locations below are one-based lines in the selected Cheetah shard above
(the byte-identical warehouse shard has the same lines). Source record IDs
are shown without their common `private_training:` prefix. Hashes are the
**recorded** `contamination.source_task_sha256` values; these are not newly
claimed raw-line hashes. No private question wording is reproduced.

| Line | Source record ID | Abstract graph / distinction from M18 | Recorded task SHA256 |
|---:|---|---|---|
| 1 | `waec-00e58df358a24b85875ea276` | Enumerate two bounded integer sets; intersect their known members | `bd6c5a6b46b6814d2012a7a9e725bec47a443cc060329dda51f673d1543dce09` |
| 6 | `waec-08762f0c5e58f0aa205105cc` | Integer interval and divisibility-defined set; deterministic intersection | `615639791122f9cc7fea2f9b417d9d57decd405106f126897f6c98d74392def4` |
| 7 | `waec-09b77ac26b7416db539887f9` | Geometric progression constraints; quadratic candidates and associated ratios; unrelated bounds keyword | `2e907b0da4d88b973f891f4d07a593b644bd66a292e1cb66c11e4a2e4b508885` |
| 10 | `waec-0ca1434d9bf23cb0cf42dc1b` | Disjoint categories with known total/counts; complement probability is fixed | `e7eb59fdbd4f561211c4a0c419c4924c338e6e7d32a1ad31fd35c3190c16d441` |
| 11 | `waec-0cc1180ea95aa366ffb5a311` | Explicit independent-event assumption determines joint probability; do not reuse this independence assumption in M18 | `d7513fce9703fac7e463f01c86a1118a112868587c471113f2a00db7f9f96ead` |
| 35 | `waec-2164a75b7d287a4333087ce1` | Rectangle dimension scaling; unrelated “both” match | `c988cb0504ae49cdb924cea224a75ecf172e2fc7d9045868c55f7a4d826fd76c` |
| 75 | `waec-3ab815409172d759058195b8` | Unknown category count constrained by supplied two-draw probability; solve quadratic then reject nonphysical root | `dc8718d2007f3b5686ed0e9435f86f405dd52b27ca546828dfee60220d2186af` |
| 89 | `waec-46b9d47ed6f270399ba75c50` | Union of fully enumerated sets; no unknown joint counts | `1f886a8a03ed333bbdcf54737ce78b6fb2d290c707f90134e79d9920da2e7501` |
| 138 | `waec-6f36a4bfff2a94f1732e5b84` | Concrete finite-set De Morgan identity checked on enumerated universe; separate algebra subpart | `e13e9c9ade1aedf26327fc86cc84405309ce8f3ac0a0d394b88b7197e9f9ad26` |
| 173 | `waec-916a1c2ff7e07fdc6478562b` | Closed-cylinder surface area; unrelated “both” match | `b06735782f7788eb1771b30dbc1758fd54f87115a74fa7fcb7f9b3ffc3ede344` |
| 189 | `waec-a3df58c0a601649ad623f8db` | Finite universe, threshold and factor predicates; deterministic intersection | `7e06d8665119aad7f967562ece0040954d3ea0bfb842808dbd4359e407b9b86f` |
| 190 | `waec-a4662c30f56b974a66e5e917` | Geometric intersection of two lines plus unrelated polygon subpart; not set cardinality | `df9e407c3ef6ddd04fb27e7033efe60117172d7a92a0fca77682d38e50ea72d9` |
| 203 | `waec-acdb2edb5ccd843ae60f2062` | Two marginal counts plus explicit neither count determine union, intersection and one exclusive region uniquely | `2d7f37b421188f95a0c9bf114aa9822ee7a8324f6c45790c8e2ea83d27d66f87` |
| 233 | `waec-c7f826bf683959f3037636b4` | Three predicate-defined finite sets; complement/intersection; separate price subpart | `133e341d3e341372e2a658b6a36b5dd192698d1aa4531ba47da2a918df610a12` |
| 249 | `waec-d787bc940d8f4742e770e98b` | Shared unknown added to numerator/denominator; fixed rational equation | `cf6b550a02562a050ea273cd71501268014ee6d834e4e9c8bf25311b66c385e3` |
| 290 | `waec-f4822742c8053774ac9d1cd4` | Known event marginals **and joint probability** determine union probability by inclusion–exclusion | `c51aa6e8dd88897cc595f1232120b99109baf2cad92844c447fa16aadcf70a9b` |
| 301 | `waec-fe5648cd582611e32acf2b61` | Known set marginals **and intersection size** determine union count | `77d95262781d9951d5f415469bab6515a7ae8461d1b691a6a985d324ed3127bc` |

Breakdown: six concrete set-enumeration/identity tasks, three fixed
inclusion–exclusion tasks, three other probability/count tasks, five unrelated
keyword matches. This is graph classification, not reapproval of their answers.

## Expanded shortlist: closer table neighbours

| Source / line | Source record ID | Abstract graph | Recorded task SHA256 |
|---|---|---|---|
| WAEC / 42 | `waec-bd58df1f9049d663ea632871` | Frequency total and supplied weighted mean provide two equations for two unknown frequencies; unique solution, not feasible-set target | `083ef7cad3a592e5d398279548a8247e38020641aa8d6b4c0c758e6f7504397f` |
| Cheetah / 17 | `waec-1326f6923d262774f0f1aad2` | Total frequency plus given parameter ratio resolves frequency table; then mean | `0fcf08c3ec83a0c589f1129f76d899934084ea44c93f24947e6d384134a41fff` |
| Cheetah / 172 | `waec-8fd1d0da89d03e8506572297` | Given single-draw probability and other counts determine missing category count, then another probability | `08136d412512acd577d97af04f874ecebd0af4d4e9f83299c2e0a44bb3af1856` |
| Cheetah / 175 | `waec-94052b4e433f12030e4a7431` | Three overlapping sets, partial margins/intersections, singleton ratio, total surveyed; unique singleton claims depend on unstated outside-region condition | `09d6948b50c904b60caf862c52bdfbeb5b26842c4db1584ce51fe823cc22c3c8` |

The other 22 expanded matches concern ordinary fixed sample spaces and disjoint
categories, statistics/order summaries, inequalities/congruences, ratios,
geometry/kinematics, calibration or lexical false positives. None of their
inspected targets requires all feasible joint counts and two distinct witnesses.
They were inspected, not treated as irrelevant solely from their keywords.

### Three-set ambiguity: independent confirmation

Training ID: `muta2_748b4e3a0125d1ab903f5a8f`. Exact source locator is
`part-00013-private-waec-363447d90421.jsonl:175` in the selected directory, or
`part-00101-private-waec-363447d90421.jsonl:175` in the warehouse directory.
Actual SHA256 of the raw selected JSONL line **including its terminal newline**:
`cb49bf61e8b3e8190cfb47a3743bc16349370f0617b8acd912ca0a9f504f49b4`.

Abstract regions use A/B/C only; no subject names or question wording are copied.
The tuple order is (A-only, B-only, C-only, AB-only, AC-only, BC-only, ABC, outside).

| Feasible witness | Eight cell counts | Total | B-only | Exactly one | Exactly two |
|---|---|---:|---:|---:|---:|
| Stored solution's extra outside-zero convention | (13, 10, 5, 2, 5, 2, 3, 0) | 40 | 10 | 28 | 9 |
| Another table compatible with the stated numerical constraints | (13, 8, 4, 2, 5, 2, 3, 3) | 40 | 8 | 25 | 9 |

Both preserve A=23, inclusive AB=5, AC=8, BC=5, ABC=3 and the B-only:C-only
ratio 2:1. Thus the singleton targets change while the exactly-two probability
remains fixed. Parent independently reread the exact row and checked these
invariants. The text does not explicitly supply the exhaustive-union condition.
The stored unique result is conditionally valid only when that convention is
added; interpreting an implicit exam convention requires separate source review.

This is strong evidence for a **related feasible-count/non-identifiability
graph**, not a finding that the complete proposed M18 prompt already appears.
The family mapper must decide whether the missing-constraint variant and M18
belong to the same exclusion family or at least the same conservative cluster.
Do not achieve “novelty” merely by deleting a supplied constraint or exposing an
ambiguity already present in a trained question. Conversely, do not call every
set operation the same family without examining targets and dependencies.

## Complete local related functions and known suites

Read complete relevant bodies in
`model-development/finetune/muta_dataset_v2/generators.py` (SHA256
`5e6a4ebe19a8de8c85dba45327cbc743ce7b19048b224eb9198b8dcbc9384631`),
its active/quarantined function lists, related exact recomputation branches and
the inheritance Socratic scaffold:

| Function | Existing dependency graph | M18 relation |
|---|---|---|
| `_probability` (quarantined) | Given disjoint category counts → total → fixed single-draw fraction | No unknown overlap or feasible range |
| `_ratio` (quarantined) | Given whole and ratio → unit size → fixed partition count | Determined partition, not arbitrary joint table |
| `_inheritance` (active) | Stated heterozygous cross → equally weighted Punnett cells → fixed genotype probability/expected count | A 2×2 diagram is present but its cells are governed by the genetic model, not unknown margins alone |
| `_population_density` (active) | Given count / area | No joint table |
| `_germination` (active) | Given success / total count → percentage | Known numerator, no intersection uncertainty |
| `_pulse_rate` (active) | Given count / time → scaled rate | No joint table |
| `_mean` (active) | Four given observations → sum / count | No joint table |

Known-suite definitions were reviewed in the earlier crosswalk and their source
hashes rechecked unchanged here: `bench/stem_prompt_suite.py` (100),
`bench/judges_prompt_suite.py` (10 positions), `bench/live_prompt_battery.py` (4),
`bench/eval_items.json` (18), `bench/submission/metadata.json` (2).

- STEM M12/M21/M40 are determined ratio/single-draw/complement tasks; M41 is
  a missing score fixed by a supplied mean; M50 tests a false converse using
  a counterexample. They do not contain M18's complete graph.
- Judges `automated_03` and its existing rubric explicitly test recognition
  of an underdetermined model-size calculation. It is not a set-count family,
  but “say the information is insufficient” is already a known evaluation
  behaviour, not a new capability unique to M18.
- Namespaces, numeric resampling and tutoring/MC wrappers do not provide
  additional family independence.

## Remaining gate

Parent has independently confirmed the row-175 ambiguity and witnesses.
Root reviewed this note, independently rehashed all four private shards and the
exact row-175 bytes, and checked both witnesses with integer assertions.
This confirms the receipts and the positive ambiguity finding; root did not
independently reread all 43 agent-reviewed prompts. The exact partition lookup is complete;
semantic coverage is 43/350, not 350/350. No standalone row correction is made
during the frozen campaign. Review the identified neighbour for the next data
revision and adjudicate M18's family mapping before authoring items. DeepMind,
TemplateGSM, other warehouse sources, old incumbent inputs and unknown base
pretraining are not cleared by this task. Neither M18 nor the private corpus
has a “clean” verdict.
