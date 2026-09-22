# M02 warehouse lexical inventory

19 September 2026. Bounded counterexample search, not a novelty/absence proof.
M02 remains unadmitted. No model inference, question authoring or corpus edits.

## Plan

Stream only warehouse manifest-listed shards in place, with bounded lines and
in-pass shard hash/count checks. Search prompt text for explicit solution-count,
consistency, dependence, singularity/rank or parameter/system language; suppress
incidental isolated uses of solution/parameter. Keep only compact row-ID/hash
locators and source/family counts, not a dataset copy or text index. Semantically
inspect at most 20 strongest candidates and report actually completed coverage.
Stop within the approximately five-minute task budget; partial coverage is valid
only when explicitly labelled. Independent root review is required.

## Result

**No positive M02 counterexample was identified by these lexical rules.** This
does not establish absence of its graph. Zero candidates matched, so **zero
rows were semantically inspected**; the at-most-20 cap was not exercised.
M02 remains unadmitted. Root independently reviewed this bounded inventory;
the scope and limitations below remain unchanged.

The in-place pass completed in 69.57 seconds: **2,500,350/2,500,350 rows across
102/102 shards**. Every shard's actual SHA256, byte length and parsed row count
matched its manifest entry. No JSON parsing error, absent required prompt or
provenance key, non-string prompt, oversized line, missing file, identity
mismatch or time-limit truncation was reported. **Empty/whitespace-only prompts
were not rejected or counted**, and source/family values were not explicitly
type-validated. This verifies the scanned bytes' identity and the listed checks,
not complete row-schema validity, correctness or semantic completeness.

Warehouse: `data/muta-stem-v2-warehouse-20260916-v7/`.
Manifest SHA256:
`2cf8d2b92dc5a92b19d5d5f714e7a064912a91c215178f3b23cd2fda6fd94ab1`.
Recorded dataset fingerprint:
`3a14a35a471b8763fd81d3e0124d861df64387a73293d8efa43526a075e5bc3d`.

| Source | Rows scanned | Candidate rows | Matching declared families |
|---|---:|---:|---:|
| `muta_verified_stem_v2` | 1,085,000 | 0 | 0 |
| `deepmind_mathematics` | 1,052,000 | 0 | 0 |
| `template_gsm` | 350,000 | 0 | 0 |
| `gsm8k` | 6,500 | 0 | 0 |
| `qasc` | 6,500 | 0 | 0 |
| `cheetahwaec` | 303 | 0 | 0 |
| `waec_elearning` | 47 | 0 | 0 |
| **Total** | **2,500,350** | **0** | **0** |

There are no candidate row IDs/hashes or positive family-count entries to report.
No private wording, corpus copy or search index was retained. Only this note was
created/updated; training, data, evaluators and other plans were untouched.

## Exact lexical scope

Python case-insensitive regular expressions operated on each parsed `prompt`,
not completions, review notes or system messages. The following five rules all
returned zero matches after their stated context condition:

```text
explicit_solution_count:
\b(?:no|zero|one|unique|multiple|many|infinite|infinitely many|exactly (?:one|two)|more than one|a unique|number of)\s+(?:real\s+|simultaneous\s+|distinct\s+)?solutions?\b

linear_consistency:
\b(?:inconsistent|consistent|consistency|inconsistency)\b

dependence:
\b(?:linearly\s+(?:in)?dependent|(?:in)?dependent\s+(?:linear\s+)?equations?)\b

singularity_rank:
\b(?:singular|nonsingular|non-singular|rank)\b

parameter_system:
\bparameters?\b
```

All rules except `explicit_solution_count` additionally required this expression
somewhere in the same prompt:

```text
\b(?:equations?|linear|simultaneous|matri(?:x|ces)|determinants?|coefficients?|systems?\s+of\s+equations?)\b
```

The explicit count rule intentionally did not demand linear context, allowing
later semantic rejection of nonlinear/incidental hits if any appeared. The
other rules suppress isolated chemical solutions, general parameter mentions,
rankings and ordinary consistency language. These heuristics are not a classifier.
Parsed binary lines were limited to 1,048,576 bytes; only counters, one current
row, running digests and a maximum-20 candidate metadata heap were retained.

## Limits and next gate

The pass does not detect all paraphrases, symbolic-only conditions, implicit
degeneracy, alternate spelling/markup, or questions asking for a coefficient
without saying "parameter." It did not normalize LaTeX/HTML, derive equation
ranks, inspect completions for latent contradictory assumptions, or classify
all existing reasoning graphs. Declared source families can be singleton labels.
The old incumbent, known suites and other separate development inputs were not
scanned in this pass. Unknown pretraining remains unknown.

The reviewed source-gap closure establishes an intended nonsingular construction
only for the two named DeepMind generator paths. Combining that limited source
finding with this negative lexical pass still does **not** satisfy M02's full
semantic source/family admission gate. Any next semantic sample or oracle pilot
requires a separately bounded decision; no such work is authorized by this note.

## Exact executed scanner

The following is the Python body submitted to `.venv/bin/python -` in the
read-only scan. Execution session `20288` completed in tool-output chunk
`7928f5`. It is preserved here as a procedure, not a new production validator.
Required fields are accessed directly in the `try` body: missing keys or a
non-object provenance value raise; a non-string prompt raises explicitly.
An empty string passes that type check. Provenance source/family labels come
directly from `provenance.source_id` and `provenance.semantic_cluster_id`; the
scanner does not infer or verify semantic family membership.

```python
import json, re, time, hashlib, collections, heapq
from pathlib import Path
root=Path('data/muta-stem-v2-warehouse-20260916-v7')
raw_manifest=(root/'manifest.json').read_bytes(); manifest=json.loads(raw_manifest)
patterns={
 'explicit_solution_count': re.compile(r'\b(?:no|zero|one|unique|multiple|many|infinite|infinitely many|exactly (?:one|two)|more than one|a unique|number of)\s+(?:real\s+|simultaneous\s+|distinct\s+)?solutions?\b',re.I),
 'linear_consistency':re.compile(r'\b(?:inconsistent|consistent|consistency|inconsistency)\b',re.I),
 'dependence':re.compile(r'\b(?:linearly\s+(?:in)?dependent|(?:in)?dependent\s+(?:linear\s+)?equations?)\b',re.I),
 'singularity_rank':re.compile(r'\b(?:singular|nonsingular|non-singular|rank)\b',re.I),
 'parameter_system':re.compile(r'\bparameters?\b',re.I),
}
context=re.compile(r'\b(?:equations?|linear|simultaneous|matri(?:x|ces)|determinants?|coefficients?|systems?\s+of\s+equations?)\b',re.I)
start=time.monotonic(); deadline=start+150
source_counts=collections.Counter(); hits_by_source=collections.Counter(); families=collections.Counter(); rules=collections.Counter(); heap=[]; seq=0; verified=[]; errors=[]; scanned=0; timedout=False
for shard in manifest['shards']:
 p=(root/shard['path']).resolve()
 if p.parent!=root.resolve(): errors.append('invalid_manifest_path'); break
 h=hashlib.sha256(); count=0; size=0
 with p.open('rb') as f:
  while True:
   if scanned%1000==0 and time.monotonic()>deadline: timedout=True; break
   raw=f.readline(1048577)
   if not raw: break
   if len(raw)>1048576: errors.append('oversized_line:'+shard['path']); break
   h.update(raw); size+=len(raw); count+=1; scanned+=1
   try:
    row=json.loads(raw); prompt=row['prompt']; prov=row['provenance']; source=prov['source_id']; family=prov['semantic_cluster_id']
    if not isinstance(prompt,str): raise ValueError('prompt not str')
   except Exception as e: errors.append(type(e).__name__+':'+shard['path']+':'+str(count)); break
   source_counts[source]+=1
   matched=[name for name,pattern in patterns.items() if pattern.search(prompt) and (name=='explicit_solution_count' or context.search(prompt))]
   if not matched: continue
   hits_by_source[source]+=1; families[(source,family)]+=1; rules.update(matched)
   score=sum({'explicit_solution_count':10,'linear_consistency':8,'dependence':8,'singularity_rank':7,'parameter_system':5}[n] for n in matched)+(3 if context.search(prompt) else 0)
   receipt={'source':source,'family':family,'id':row['id'],'source_row_id':prov['source_row_id'],'path':shard['path'],'line':count,'raw_line_sha256':hashlib.sha256(raw).hexdigest(),'recorded_task_sha256':row.get('contamination',{}).get('source_task_sha256'),'rules':matched,'score':score}
   seq+=1
   if len(heap)<20: heapq.heappush(heap,(score,-seq,receipt))
   elif (score,-seq)>heap[0][:2]: heapq.heapreplace(heap,(score,-seq,receipt))
 if timedout or errors:
  incomplete={'path':shard['path'],'rows_read':count}; break
 if count!=shard['rows'] or size!=shard['bytes'] or h.hexdigest()!=shard['sha256']:
  errors.append('shard_identity_mismatch:'+shard['path']); break
 verified.append(shard['path'])
 if len(verified)%20==0: print(json.dumps({'progress_shards':len(verified),'rows':scanned,'seconds':round(time.monotonic()-start,1)}),flush=True)
result={'manifest_sha256':hashlib.sha256(raw_manifest).hexdigest(),'elapsed_seconds':round(time.monotonic()-start,2),'rows_scanned':scanned,'manifest_rows':manifest['row_count'],'verified_shards':len(verified),'manifest_shards':len(manifest['shards']),'complete':not timedout and not errors and len(verified)==len(manifest['shards']),'errors':errors,'incomplete_shard':locals().get('incomplete'),'source_counts':dict(source_counts),'hits_by_source':dict(hits_by_source),'family_hits':[{'source':a,'family':b,'count':n} for (a,b),n in sorted(families.items())],'rule_hits':dict(rules),'candidates':[x[2] for x in sorted(heap,reverse=True)]}
print('FINAL '+json.dumps(result,sort_keys=True),flush=True)
```

Preserved final output (metadata only):

```json
{"candidates": [], "complete": true, "elapsed_seconds": 69.57, "errors": [], "family_hits": [], "hits_by_source": {}, "incomplete_shard": null, "manifest_rows": 2500350, "manifest_sha256": "2cf8d2b92dc5a92b19d5d5f714e7a064912a91c215178f3b23cd2fda6fd94ab1", "manifest_shards": 102, "rows_scanned": 2500350, "rule_hits": {}, "source_counts": {"cheetahwaec": 303, "deepmind_mathematics": 1052000, "gsm8k": 6500, "muta_verified_stem_v2": 1085000, "qasc": 6500, "template_gsm": 350000, "waec_elearning": 47}, "verified_shards": 102}
```

## Reviewer-requested controls

Nine lexical controls and six field-handling controls passed. The control run
parsed the preserved scanner with Python `ast`, compiled its actual `patterns`
and `context` assignments and `matched` comprehension, and separately compiled
the original parsing/type-check `try` body. It did not retype a replacement
matcher, rerun the corpus scan or change the executed scanner. SHA256 of the
preserved Python body, excluding fence delimiters and a terminal newline:
`254d1578a67115ef2f1df04a87583351eef279e9fd88647e9d7b10e85516dcc7`.

These are short synthetic matcher-control strings, not authored benchmark items:

| Control text | Observed rule matches |
|---|---|
| `Linear equations have infinitely many solutions.` | `explicit_solution_count` |
| `The linear equations are inconsistent.` | `linear_consistency` |
| `These are dependent equations.` | `dependence` |
| `The matrix is singular.` | `singularity_rank` |
| `A parameter changes these simultaneous equations.` | `parameter_system` |
| `The solution contains sodium chloride.` | None |
| `The solution has consistent parameters.` | None: missing equation/matrix context |
| `Nonlinearities include rankled speculation and unsolutions.` | None: word boundaries work |
| `There is no solution remaining in the beaker.` | `explicit_solution_count`: documented intentional false positive requiring semantic rejection |

The last control shows why the explicit-count rule must not be treated as a
semantic classifier. It did not occur as a candidate in the scanned warehouse.
The successful positive/boundary controls rule out accidental literal escaped
word boundaries in this implementation; they do not establish selector recall.

| Field control | Actual original scanner behavior |
|---|---|
| Missing `prompt` | `KeyError`, caught by scanner error handling |
| Integer `prompt` | Explicit `ValueError`, caught by scanner error handling |
| Empty `prompt` | Accepted; unvalidated coverage limitation |
| Whitespace-only `prompt` | Accepted; unvalidated coverage limitation |
| Missing `provenance.semantic_cluster_id` | `KeyError`, caught by scanner error handling |
| Integer source/family labels | Accepted at parsing stage; no explicit type validation |

Accordingly, this report does **not** claim every prompt was nonempty or every
provenance label was valid. No matcher defect was found by these controls and
no whole-corpus rescan was performed.

Root inspected the preserved scanner and metadata receipt, verified the actual
manifest hash and one warehouse row's required prompt field, and independently
extracted the documented regexes/context to run eight positive/negative controls.
All eight passed. Root did not repeat the full 69.57-second corpus scan. This
review accepts the reported bounded lexical inventory and its explicit empty-
prompt/semantic-coverage limitations, not M02 independence or family admission.
