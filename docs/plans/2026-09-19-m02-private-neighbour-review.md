# M02 private-neighbour screen and abstract scanner controls

19 September 2026. **Independent bounded review completed; no family admitted.** This records an executed
350-row private-source screen and 16 prompt/answer semantic inspections, not
another warehouse-wide scan, fresh question authoring, family admission or model
inference. No private wording or corpus copy is included in this document.

## Executed scope and byte identities

Root for all shard paths below:
`data/muta-stem-v2-warehouse-20260916-v7/`.
Manifest SHA256, rechecked when preserving this record:
`2cf8d2b92dc5a92b19d5d5f714e7a064912a91c215178f3b23cd2fda6fd94ab1`.

| Exact shard | Rows | Bytes | Actual in-pass SHA256 |
|---|---:|---:|---|
| `part-00100-private-waec-e1720e95858d.jsonl` | 47 | 296036 | `c165a0e0f7ede07b9e2843aef5ac714c88b45dbdfd73f99d733d3b35b115bb4e` |
| `part-00101-private-waec-363447d90421.jsonl` | 303 | 1716873 | `9514e87da6237cd0f2dd9b6f73d19d7ba447ea83ecfb333cf45e8778f22648c6` |

The executed scan read all 350 prompts and metadata in place. Both shards'
actual byte lengths, parsed counts and SHA256 matched their manifest entries.
It searched **prompt text only**; the suggestion to search prompt *and*
completion is a future improvement, not a description of this execution.
Source line locators are one-based; raw-line hashes below include the original
JSONL newline. Completion prose and the private review history were not read
for the 16-row semantic pass: it inspected the full stored prompt and `answer`.

| Rule | Matched rows (rules overlap) |
|---|---:|
| coefficient_value | 15 |
| symbolic_coefficient | 26 |
| conditional_target | 3 |
| line_relation | 15 |
| linear_system_language | 1 |

These are feature-hit counts, not semantic classifications. The `conditional_target`
rule alone did not place a row in the retained locator list. Every one of the
15 `line_relation` matches was manually inspected, plus the one
`linear_system_language` match, Cheetah line 210. The groups do not overlap,
giving **16 distinct prompt/answer reviews**. The other **334 rows were not
manually semantically read or cleared**. Other coefficient-feature hits remain
unreviewed, not excluded by their lower priority.

## All 16 reviewed locators and abstract findings

Every row below belongs to
`part-00101-private-waec-363447d90421.jsonl` (Cheetah). Findings concern the
essential task graph, not a fresh correctness certification of the stored answer.
No reviewed row was found to require parameter-dependent zero/one/infinite
classification of a real linear system. This is a bounded positive-counterexample
search, not proof of M02's absence in the remaining corpus.

| Line / training row ID | Raw-line SHA256 | Abstract graph / reason it is not an observed M02 branching task |
|---|---|---|
| 67 / `muta2_b63eb2b6e420702e59364686` | `6e904810b73442d456ccf363e263d9035a60767d8e1f63c6fe75ccb034bd9b72` | Parallel-line transversal angles and angle bisectors determine a geometric angle; no free coefficient or solution-count branch. |
| 78 / `muta2_3ad37d1bff030b64b8f47fbd` | `5df04d34995ddfee46f367dfcfb89dfc138ec1a35aeac1d19c92626fd9191ae1` | One fixed point and fixed slope determine one line equation. |
| 106 / `muta2_818e8ea5c3c150c90f0ca66d` | `5dcf13f8ca26faddf629961439d6456395acd94fbd2f51ca254b72ff114470c6` | Equidistance from two fixed points identifies a locus; parallel appears as a distractor. |
| 111 / `muta2_c76e447c4ff3e63a9b9c67e3` | `5d80fd097e9a48ee5069ea86d1d74cd74387e28e8cf8c257facf172b8b9873d5` | Read slope from a single numeric line equation. |
| 116 / `muta2_ed80602bac1ccd66d6da615a` | `608c9f20553f8f512b5567521d1d9d543fa6c413d122de338880a8c28e39cc4f` | Fixed parallelogram length geometry plus distance along a geographic parallel; no linear-system classification. |
| 144 / `muta2_74a853d37ac8a01edc74253b` | `583f903c57370139b60ae000fce34135ee6f12f04a4ea7e0a88c7416311ac7f2` | Construct the parallel to a fixed line through a fixed point; output coefficient labels do not create a free family parameter. |
| 155 / `muta2_71916ebb0f1e3c50a84161d7` | `be5c2ec81ee32d13544f63c84017c4be4a098630399f66c8e3592e7450efdb58` | Another fixed-slope/point parallel-line construction; no rank-boundary target. |
| 190 / `muta2_4de0bb68e516c01f0cd037a5` | `7c8202625746adf85d463dd8c6ff92000c3cfa473c8c2e2068b7ccce655b22ac` | Solve a fixed nonsingular pair, then construct a line through its intersection and the origin; separate regular-polygon calculation. No parameter-dependent ranks. |
| 207 / `muta2_1a7ae87ee7efb061102698b5` | `c4d23b168cff9c4da577daef484238965edcc790c39f7c7fd01bd6cbe5836f06` | Recover one unknown slope from a fixed point; the symbol is a single target unknown, not a domain over which consistency varies. |
| 210 / `muta2_1e63cc88825d08fbfaafab62` | `f23b766e3f6360e5f1bc0dfe188bbd051b643d0477dd3292f7fee54194fc5829` | Match a coefficient between quadratics with the same roots; nonlinear polynomial identity, not two real-linear constraints. |
| 236 / `muta2_ce9fad238bb0f29392c89657` | `4977cee17281eee94732c5e9ad3107588a3016ece5df9e6b81cdc3f1709eedf2` | Infer a fixed slope from two points and construct a parallel through another point. |
| 240 / `muta2_6b059ee39bf9ebe503bf543f` | `7468265ceda87c9c58df72d4fa6d5407af3892332e3fffde14c055eb6fa4b28c` | Known intercepts determine one rational-coefficient line; output numerator/denominator labels are not free parameters. |
| 241 / `muta2_6b50f993e3156d6aa68773a9` | `f8392e382a814af9f636ef635b35cf3981a98e4efd71651a89a82d5d49252633` | Known slope and one partially specified point determine one coordinate. |
| 275 / `muta2_02e69d00a4f2d0003ced1d80` | `781eb5fc5d972120ecc7267d10a15b8411e4bc4e52bd41323919086096304bcf` | Fixed trapezium area and bases determine its height; parallel is geometric vocabulary. |
| 285 / `muta2_36791939b7bf8e49cbf9bf76` | `edec2832cae63d01468b3a795bbee9cf2632621b8f35d3683cfd22d6e5601d84` | Direct slope between two fully specified rational-coordinate points. |
| 296 / `muta2_c0c2d7a67052f4f1314c7438` | `54f63cefde84d8299433ff32f5c0df7cee0a5323f61ea6e9a515cfc74fcab449` | Trapezium diagonal intersection and similarity determine a fixed length; no line-equation parameter/rank branch. |

## Exact executed prompt selector and integrity loop

The following is the actual selector/integrity portion submitted to
`.venv/bin/python -` during this pass. Initial schema-key printouts from four
first rows preceded this portion but did not contribute to selection or
semantic findings. It wrote no files. The semantic read that followed used
the explicit 16 line numbers listed above and printed each selected row's
`prompt` and `answer` for review; it did not execute publisher code.

```python
import json,re,hashlib,collections
from pathlib import Path
root=Path('data/muta-stem-v2-warehouse-20260916-v7')
m=json.loads((root/'manifest.json').read_text())
patterns={
'line_relation':r'\b(?:parallel|coincident|coincide|intersect|intersection|intercepts?|gradients?|slopes?)\b',
'coefficient_value':r'\b(?:value|values|constant|constants)\b[^\n.]{0,55}\b[a-zA-Z]\b',
'symbolic_coefficient':r'\b(?:[abckmnp]x|[abckmnp]y|[abckmnp]\s*\\times\s*[xy])\b',
'linear_system_language':r'\b(?:simultaneous|linear|equations|matrix|matrices|determinant)\b',
'conditional_target':r'\b(?:possible|impossible|cannot|any|every|all|depends|unique|infinite|none)\b',
}
counts=collections.Counter(); locators=[]
for shard in m['shards']:
 if '-private-waec-' not in shard['path']:continue
 p=root/shard['path'];sha=hashlib.sha256();num=0;size=0
 with p.open('rb') as h:
  for i,raw in enumerate(h,1):
   sha.update(raw);size+=len(raw);num+=1;r=json.loads(raw);text=r['prompt'];matches=[name for name,exp in patterns.items() if re.search(exp,text,re.I)]
   for name in matches:counts[name]+=1
   if any(name in matches for name in ('line_relation','coefficient_value','symbolic_coefficient','linear_system_language')):
    locators.append({'path':shard['path'],'line':i,'row_id':r['id'],'source':r['provenance']['source_id'],'task_sha256':r['contamination']['source_task_sha256'],'raw_sha256':hashlib.sha256(raw).hexdigest(),'matched':matches})
 assert sha.hexdigest()==shard['sha256'] and size==shard['bytes'] and num==shard['rows']
 print('private_partition_verified',shard['path'],num,sha.hexdigest())
print('rule_counts',dict(counts));print('candidate_locators',json.dumps(locators))
```

Observed rule counters:

```json
{"coefficient_value":15,"symbolic_coefficient":26,"conditional_target":3,"line_relation":15,"linear_system_language":1}
```

### Actual selector limitations

- This exploratory code has no line-length/resource guard, general strict JSON
  schema, manifest-path containment guard or duplicate-key check. The actual
  input is the two approximately 2 MB combined, hash-verified private shards;
  this is not a reviewed general-purpose production scanner.
- Raw prompt regexes receive no HTML/LaTeX normalization. The broad
  `symbolic_coefficient` pattern can match ordinary words such as `by`; an
  apparent coefficient feature is not a parsed mathematical expression.
- `coefficient_value` may match prose or displayed answer labels; `parallel`
  covers geography and fixed geometry. These false positives were retained.
- Prompts can express rank degeneracy without these words, or through a diagram,
  implication or answer-only reasoning. The earlier zero-hit warehouse scan
  and this positive shortlist together still do not establish semantic absence.
- Only the 16 reviewed rows have the limited graph findings above. No template,
  source or family is cleared by these findings. Unknown pretraining remains
  unknown, and no source-rights decision is made.

## Concrete next-screen controls: abstract matrices, not questions

These controls were authored for scanner development, not rendered benchmark
items. Rows are written `[coefficient of x, coefficient of y | RHS]` over real
unknowns. Expected outcomes were manually derived and checked with exact
Fraction elimination using `bench/winner_battery/m02_oracles.py`, SHA256
`302afd99cdaaac1b455d53101766a7b5e142b85967af58b6d030bdb1b4e22b35`.
This check used the already-written oracle; it is not a new independent reviewer.
Independent review verified the displayed matrix cases with both exact oracles
and direct determinant/consistency reasoning. One negative-control guard was
added after review: slope recovery from a fixed point requires nonzero abscissa.

| ID | Abstract input / target | Expected outcome and screen obligation |
|---|---|---|
| P01 | `[k,2|1]`; `[2,k|1]`, k = −2, 0, 2; classify solution count | Inconsistent / unique / infinite; must shortlist. |
| P02 | `[1,1|3]`; `[k,k|3]`, k = −1, 0, 1, 2; classify consistency | Inconsistent / inconsistent / infinite / inconsistent. Determinant is identically zero: a scanner must not require a nonzero determinant polynomial. |
| P03 | `[1,−1|2]`; `[3,−3|t]`, t = 0, 6 | Inconsistent / infinite. Parameter is only in the RHS; searching symbolic coefficients alone misses it. |
| P04 | `[k−2,0|0]`; `[0,k−2|0]`, k = −1, 0, 2 | Unique / unique / infinite. At k=2 both coefficient and augmented ranks are zero. |
| P05 | `[1,t|4]`; `[3,6|5]`, t = 1, 2, 3; select coefficient making distinct lines parallel | Unique / inconsistent / unique; scalar key t=2 still flags a rank-boundary neighbour requiring family review, not automatic exclusion or clearance. |
| N01 | `[1,1|t]`; `[1,−1|1]`, t = −6, 0, 6 | All unique, and determinant is −2 independently of t. Parameter presence alone is not the M02 essential branch. |
| N02 | Fixed `[1,1|7]`; `[1,−1|1]` | Ordinary nonsingular numeric solve; no parameter family. |
| N03 | In y=mx+b, recover slope m from a fixed point with nonzero abscissa and a fixed y-intercept b | Symbolic coefficient may flag it; these guards make the target ordinary unique coefficient recovery, not a count-of-solutions branch. If the abscissa is zero, do not use this negative control: the slope can be inconsistent or unrestricted. |
| N04 | Construct a parallel to a fixed line through a fixed point | Geometry selector may flag it; parallel vocabulary alone is not a rank-boundary classification task. |
| N05 | Match one coefficient of two quadratics having the same roots | Nonlinear polynomial task, not a two-variable real-linear system. Keep other-family ambiguity explicit. |
| N06 | Prose token `by` in `paid by Mary` | Must not be interpreted as b×y by a proposed mathematical tokenizer. |

Additional rendering controls must cover renamed unknowns u/v with parameter t,
Unicode minus/multiplication, HTML entities/line breaks, and LaTeX fractions.
Equations occurring only in a completion must remain discoverable in the next
prompt-plus-completion pass. Unsupported parsing must produce `unresolved`,
never a no-overlap verdict. None of those future rendering/scanner controls was
executed by the raw regex code above.

Executed mathematical control-check output (parameter, coefficient rank,
augmented rank, outcome):

```text
P01: (-2,1,2,inconsistent), (0,2,2,unique), (2,1,1,infinite)
P02: (-1,1,2,inconsistent), (0,1,2,inconsistent), (1,1,1,infinite), (2,1,2,inconsistent)
P03: (0,1,2,inconsistent), (6,1,1,infinite)
P04: (-1,2,2,unique), (0,2,2,unique), (2,0,0,infinite)
P05: (1,2,2,unique), (2,1,2,inconsistent), (3,2,2,unique)
N01: (-6,2,2,unique), (0,2,2,unique), (6,2,2,unique)
```

## Retained-source constraint for subsequent implementation

The TemplateGSM adapter in
`model-development/finetune/muta_dataset_v2/adapters.py` reads publisher
`solution_code` while building, but stores only cleaned `solution_wocode`, a
numeric answer and `verification.solution_code_present`. Actual program text
is not retained in the inspected warehouse schema. The archived static filter
also says it does not parse or execute publisher solution code. Therefore a
generator-AST semantic audit cannot be claimed from those retained fields.
Numeric-only answer filtering does not exclude a parameter-boundary question
whose requested answer is a single coefficient value, as P05 demonstrates.

This note does not change M02's unadmitted status. It creates no corpus copy,
question, benchmark key, source licence claim, training alteration or model result.

## Independent review record

The separate `five_manifest` reviewer verified the exact manifest and both
shards' bytes, counts and SHA256; reproduced all five selector counters; checked
all 16 row IDs/raw-line hashes and selector memberships; and read all 16 stored
prompts and answers in place. The abstract descriptions match that bounded
evidence. All 18 displayed parameter instances plus N02 agreed with both exact
oracles and independent algebra. Review caught the omitted nonzero-abscissa
guard in the original N03 abstract control; the corrected specification above
does not change any observed private-row finding (row 207 already has nonzero
abscissa). No source wording was added to this note. The other 334 private rows,
completion reasoning and whole-family contamination remain unreviewed here.
