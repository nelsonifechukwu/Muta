# M02 incumbent-neighbour semantic review

19 September 2026. Bounded follow-up to the incumbent lexical screen, not
family admission or clearance of that screen's complete positive population.

## Pre-execution plan

Run the exact reviewed `bench/winner_battery/m02_incumbent_screen.py` source
over SSH stdin in a namespace whose `__name__` is not `__main__`. Require its
SHA256 to be `0b2bde7827c4727bd74970b380a410e4184f415f590c53e4aceef9f198155c74`.
Replay both complete `scan_file` outputs and require equality with the saved
receipt's `files` entries. The receipt is
`provenance/evaluation/winner-battery/m02-incumbent-counterexample-screen-20260919.json`,
SHA256 `79b23685d7f87711d1b31fa31be74f2d5c1a9535fff67e059cfb53123a33d83c`.

Re-read both pinned source files using the same strict parser and selectors;
independently reverify complete byte, row and SHA256 identities. Select only
rows having any rule other than `coefficient_value`. Retain prompt, completion
and pair rule lists separately. Require at most 64 selected rows across both
files before emitting any source text. The whole pass must succeed first.
Source text is for transient semantic inspection only: no local or remote
question/answer file, quotation in this report, inference or dataset mutation.

Record actual reviewed line hashes, counts and abstract task graphs below.
Unreviewed coefficient-only matches remain unreviewed. Inspecting this subset
cannot establish absence among all rows, hidden graphs, or other input roles.

## Execution and findings

Executed successfully at **2026-09-19 04:21:15.683585 UTC**, exit 0, by
`warm_export_review`. Transport: `ssh -T -o BatchMode=yes -o ConnectTimeout=15
ubuntu@129.213.31.157 /usr/bin/python3 -` with the program supplied on stdin.
No source text was written to a local or remote file. Prompt/completion text
was returned only to the transient review tool output, after the complete
identity/count/rule/cap checks succeeded; this is separate from the original
screen's text-free output. The original screen receipt is unchanged.

| Executed identity | SHA256 |
|---|---|
| Reviewed scanner source | `0b2bde7827c4727bd74970b380a410e4184f415f590c53e4aceef9f198155c74` |
| Extraction wrapper | `1aee3467e329bb8b20f8535aadf575f3f791874b5c3aeacf4d47d336b1ea0c31` |
| Complete stdin program, including exact source and prior-file entries | `5fa24fc661a42c7ddfa5a4ad1d76de587ab796689a140ab8db529701b55eb6cb` |
| Original lexical receipt | `79b23685d7f87711d1b31fa31be74f2d5c1a9535fff67e059cfb53123a33d83c` |

The wrapper executed only the locally reviewed scanner, under
`__name__ = 'm02_review_inert'`; no code was taken from dataset fields. It
required exact equality of the complete replayed file reports to the original
receipt, then independently re-read the bounded lines and checked full-file
identities and rule totals before emitting any selected text. Its selected
population was the union of all non-`coefficient_value` rules, not the original
screen's truncated first-64 locator list. The whole-pass cap was 64 rows across
both files; the actual union was 43, with none omitted from this subset.

| Role | Rows / bytes | File SHA256 | All lexical positives | Pairs reviewed | Coefficient-only positives not reviewed |
|---|---|---|---:|---:|---:|
| Incumbent train | 10,756 / 1,880,336 | `0d1b52db8dc0785fe8c0b62cbe374e79c35192b9ccd7fe86480c998808c3734c` | 671 | 42 | 629 |
| Incumbent development | 566 / 99,510 | `fd48e23f20afb5ae8986730b19cb42523610cd0620e71021e9e2e8aa99dbf69b` | 30 | 1 | 29 |

Replayed rules exactly: train `algebra_vocabulary=13`,
`coefficient_value=636`, `geometric_relation=5`,
`solution_classification=9`, `variable_denominator=15`; development
`coefficient_value=29`, `variable_denominator=1`. Neither file had a
`zero_division` or `two_symbolic_equalities` hit. The seven train matches with
both a coarse coefficient rule and a non-coefficient rule are included among
the 42 reviewed rows. Counts are lexical selections, not neighbour counts.

**Bounded semantic conclusion:** all 43 complete stored prompt/completion
pairs were read. None explicitly asks for parameter-dependent classification
of a two-real-variable linear system into unique, inconsistent or infinite
solutions. This is not an essential-graph exclusion certificate. In
particular, train 4871 and 9925 ask for reaction-balance selection: conservation
of atom counts can be represented by coupled linear constraints. They remain
**cross-family graph-adjacency cases requiring a separate decision**, rather
than being cleared merely because their surface subject is chemistry. Train
3392 also selects a reaction equation; train 5355 uses a fixed stoichiometric
proportion. Neither establishes the target parameter-degeneracy graph, but
both belong in a broader chemical-conservation overlap review if that family
boundary is proposed. No candidate family or item was admitted.

The retained raw-MCQ schema does not preserve the original options or all
referenced context. For example, train 1612 refers to absent comparative
vehicle data; 2935 and 6480 make comparisons whose alternatives are absent.
The graph notes below concern the **retained pair only**, not a reconstructed
complete source exam. They are also not an answer-correctness audit: train
3100 contains a visibly unrelated phrase, and the stored answer at 8572 appears
inconsistent with the fixed-mass momentum-conservation calculation. Those
data-quality concerns were not corrected or fed into model evaluation.

## Reviewed-row ledger

Rules: A = `algebra_vocabulary`; C = `coefficient_value`;
G = `geometric_relation`; S = `solution_classification`;
V = `variable_denominator`. `P` and `Cpl` indicate the actual positive prompt
and completion rule lists; a dash means no rule on that side. Every row's
`pair_rules` list was empty. E = `arc_easy_train`, H = `arc_challenge_train`,
Q = `qasc_train`. Lines are one-based in the exact role-specific file above.
Descriptions are abstract task graphs, not copied questions or answers.

| Role / line | Source | Raw line SHA256 | P / Cpl rules | Retained-pair graph or limitation |
|---|---|---|---|---|
| train / 214 | E | `55c47712f9a286ffc4011828c60c9d2c2ff520e10642731076f05e409ea48973` | G / — | Physiological demand and transport adaptation; ordinary-language relation hit. |
| train / 370 | Q | `587a78f320a819b7732a9b03059953443f35f2777a86573c1f12dbdb5a6c380b` | — / S | Ecological descriptor; underspecified stored answer, not solution multiplicity. |
| train / 647 | E | `10cd06cd4beffff29e7bdffc26695128508d966166055dfe68bd5308c08bf453` | G / — | Regional resource suitability; ordinary-language relation hit. |
| train / 689 | H | `c46b7eb3187bec2cc11c60521db9fee81da294d3efb97615781186d3dce846c7` | — / V | Fixed-force, fixed-mass acceleration; scalar division, units trigger. |
| train / 719 | Q | `c0e4df44a7fe61d8a5b8c58df77f7c94c66f295155a5ce33ef3a4a910af22ee2` | S,C / — | Taxonomic anatomy identification; biological distinctiveness, not multiplicity. |
| train / 794 | H | `197b987a164c331520357175181095ff81808054ecb4ee1825d32eb7e878dd8c` | C / V | Distinguish measurement from opinion; units trigger. |
| train / 1151 | E | `4c392e779650ce692538e21123f19994ce0541a50458ccd137c8d2e2e7345e31` | V / V | Fixed one-dimensional relative velocity; numeric vector composition. |
| train / 1203 | Q | `2a7b426b2b9ded08695ec6cb088f0bb39a6d92f0e71d7389483c8de2f30b1068` | S / — | Taxonomic anatomy recall; biological distinctiveness. |
| train / 1422 | H | `ec243141bc78638cefdd857f92ca356b824f1d1772a25bd1bd05fcc3527822cd` | V / — | Fixed-distance travel duration from speed; scalar ratio. |
| train / 1612 | E | `a46e99f7bbe0fe0222afbb7aede8f6ea0d78f8722f799125d1c3f897930ed90b` | C,V / — | Acceleration ranking under common force; comparative data absent. |
| train / 1615 | E | `e10d08ede2c3b699643668645ed83d1a285dda55b92d40d3ecd31fa128478dbb` | A / — | Interpret rearrangement of atoms in a supplied reaction, not coefficient classification. |
| train / 1890 | H | `3fbaf3cad702636d3d1a5fd85e8639c5132fa9fe175875dfa09a3696ea97a2b4` | C / V | Identify a motion measurement; dimensional/unit recognition. |
| train / 1895 | E | `a8e05025feecc37610551e151033225484ad4c91790c934deb110ff5b735c335` | A / — | Interpret reaction energy direction from a supplied expression. |
| train / 1980 | Q | `393588e49944278beb4a8bdafd49a1f3370676f575654870ea18702c6d8c0306` | S / — | Distinctive anatomical trait; no algebraic solution set. |
| train / 2504 | E | `4942b6bbdbe22da8a365aa766fe2ddf12391b1c9bf05a755026dbfd3d11cdb42` | V / — | Recognize inertia from qualitative motion; units trigger. |
| train / 2935 | H | `784954dd9109c1c3a6935ef35411a3fc4f433f159b5ecb274aa3d92e319cddee` | — / V | Compare fixed momenta; omitted alternatives prevent complete comparison reconstruction. |
| train / 3019 | E | `c2b8ef8bb173a9d71a10b2cdebd0c51fbd49d7111254910a4bdd0444d6af57ab` | C / A | Choose a notation for a chemical process; no numeric constraint solving requested. |
| train / 3038 | H | `415b5a40e03c302a7cba311b9d20724fe0e859869191e0156a77f49dc12f40e9` | C / V | Recognize magnitude-plus-direction representation; units trigger. |
| train / 3100 | E | `69e916bf07ed075456902de69444db6e3934eb16d001afa6a7082243f2c5c1ce` | V / — | Fixed wave-frequency ratio; unrelated source phrase is a quality caveat. |
| train / 3392 | H | `4b4bcb9509e0d52a04adc1eafd94949479e463ec9c3be53614428a900e6f1470` | A / — | Reaction-equation selection; retain chemical-conservation adjacency caveat. |
| train / 3877 | H | `b6bb01959a366cb5b25b7cde3511d18676b192db39c8ddd394e4c7e329dd0f19` | G / — | Regulation-to-environment causal effect; ordinary-language relation hit. |
| train / 3963 | H | `2f87959236882de04132eed52006961ab2b1cf8c6d1999a12618e73b00d1df39` | — / V | Elapsed-time conversion followed by fixed average-speed ratio. |
| train / 3977 | H | `5716595c597c2c79c66b11513a1432a31499fef6bd134e8017fc3d1f4d75da6b` | A / — | Classify the product in a supplied chemical reaction. |
| train / 4232 | Q | `6a7af803a20c99263f61b70ea9a79d183a9e6bca9ef6f8a9a6eaec91040e1551` | S / — | Plant adaptation and environment; biological distinctiveness. |
| train / 4871 | H | `ed6ecb1b958c79bf6d1fa806c470c40adf7a683a9fdb5fcc565bcc541a3f3846` | A / — | Reaction-balance selection; coupled linear conservation is unresolved cross-family adjacency. |
| train / 5035 | H | `09641ca75955473614b4ff68b223997c04ff4862769680e071a0ef0d40f57f4b` | S / — | Evidence-driven explanation revision; inconsistency is scientific, not rank-based. |
| train / 5355 | H | `2f9a36e5a3cf17e8992863516727645df440374fe260dbb30b11ea5b1a3eef14` | A / — | Fixed stoichiometric mass proportion; conservation adjacency but no parameter branch shown. |
| train / 6476 | H | `982ba74a325ef3534a421f49addbfb59e3f298db59d97b685cafdc564c708343` | V / V | Momentum from fixed mass and speed; multiplication. |
| train / 6480 | H | `cf199854b7421755f918ee1516dfe0b0956f3b5f8fa08fb92de3f19152ac3bbc` | V / — | Density-volume mass comparison; original alternatives absent. |
| train / 6877 | E | `ebc0aebe74ab24b102f89f36bdbc3699c0d3871bdfde5709e2ed145d3dd42b07` | A / — | Identify reaction output roles in supplied notation. |
| train / 7215 | H | `64069a37f64dbb627569a885b9de9909ea8d453c4ebd959fe3104d45803fb815` | V / V | Fixed velocity change divided by elapsed time; scalar acceleration. |
| train / 7522 | H | `a78bd9a9eed2a2aff2b33db0938efb1a0d33ec19e59218b4de42e6ddbcd8db1d` | G / — | Density-dependent fluid transport and nutrient dispersal. |
| train / 7827 | Q | `c70ff84b4a1adc241362d902127f77dbd457293e74cd132f043d2a983df03f46` | S / — | Anatomical-system recall; biological distinctiveness. |
| train / 8572 | H | `3140c2372176e863c09ea4fca3db7bdf8157ad0aba765a68371f724e5a3e0782` | V / V | Fixed-mass momentum conservation with one unknown; stored answer appears inconsistent. |
| train / 8770 | E | `ffe1025d231cc1a81232585f72f764d2a22de11cbce130b0668b09e722ca7168` | — / A | Choose chemical reaction notation; no coefficient solving requested. |
| train / 9104 | E | `f24e7f2dc531df3990adcab52377b5327f13181c9624542d726dd626b1121245` | A / — | Identify the quantity in a supplied calorimetry product formula. |
| train / 9403 | Q | `9f21e7ecf57bc467762a247d23293396f6ba636c148e26871aba19d1de6b39b4` | — / A | Activation-energy terminology; answer quality not certified here. |
| train / 9512 | H | `b4f3ed7f4a531472c625043f1a4d1a21f91f2a74b11cdbf8714e80a3c0073895` | G,C / — | Circuit pathway topology; no geometric line-system constraint task. |
| train / 9810 | E | `633f4b6f875dc810b2e4d6c97c20f7166e6120502693d722338cfc3c7e4d2514` | S / — | Distinguish empirical investigation practices. |
| train / 9925 | H | `b3d58075ba14af5fa202cab4afdc90ee810194730d98f5d14f480d69cca352a4` | A / — | Reaction-balance selection; coupled linear conservation is unresolved cross-family adjacency. |
| train / 10445 | E | `cc417f5b50ca76da63047e203ec4b7bbd8732424f9a351c5cc236facec748abe` | S / — | Match an evolutionary mechanism to theory; scientific consistency. |
| train / 10728 | E | `77ec90851ff87ccfffa41f70351fc55a72a020ae0b68a6912f551377ccbf1738` | A / — | Name supplied reaction products; symbolic-to-name lookup. |
| development / 359 | H | `1f6ac38b763d4901dae12f74d6d7d3ccd2454a1bc8cdbc753fbc5dfb8821ebde` | V / — | Fixed wave speed-to-wavelength ratio. |

## What remains unreviewed

- 658 coefficient-only lexical positives: 629 train and 29 development.
- All lexical negatives as potential implicit or differently worded neighbours.
- Original omitted choices/visuals/context and complete source-family boundaries.
- Cross-source whole-family exclusions and a real candidate contamination audit.

Subsequent [four-pair boundary review](2026-09-19-m02-conservation-boundary.md)
applies the existing definition: the retained conservation tasks are shared
suboperation neighbours, not demonstrated M02 graph equivalents. This resolves
only the retained-pair comparison. Missing choices, source variants and the
other coverage gaps above remain unresolved; it is not whole-family clearance.

The independent winner battery remains at **0 admitted items and 0 admitted
families**. The prior 550 known-suite responses and scores are unchanged.

## Independent cross-review

The root reviewer independently rehashed the complete incumbent train file
and transiently read train 4871 and 9925. Both raw-line hashes matched the
ledger above. The reviewer agreed that chemical conservation is a genuine
constraint-graph adjacency requiring an explicit family-boundary decision,
while neither retained pair explicitly performs varying-parameter/rank
classification. Missing original options prevent complete source-task
reconstruction. This cross-review covers those two graph-adjacency decisions,
not a second semantic review of all 43 pairs or broader family clearance.

## Exact replay/extraction launcher (code only)

The following local launcher constructs the exact approved stdin program.
It can be reused from the repository root for independent transient review;
it writes no files. The leading/trailing newlines in the raw wrapper literal
are intentional and part of the wrapper and complete-stdin hashes above.
Do not redirect its output to a file: successful stdout contains the bounded
source text for inspection, which is deliberately absent from this document.

```python
from pathlib import Path
import hashlib,json,subprocess
source=Path('bench/winner_battery/m02_incumbent_screen.py').read_text()
assert hashlib.sha256(source.encode()).hexdigest()=='0b2bde7827c4727bd74970b380a410e4184f415f590c53e4aceef9f198155c74'
p=Path('provenance/evaluation/winner-battery/m02-incumbent-counterexample-screen-20260919.json')
assert hashlib.sha256(p.read_bytes()).hexdigest()=='79b23685d7f87711d1b31fa31be74f2d5c1a9535fff67e059cfb53123a33d83c'
prior=json.loads(p.read_text())
wrapper=r'''
import hashlib,json,sys
from collections import Counter
from datetime import datetime,timezone
ns={'__name__':'m02_review_inert'}
try:
 if hashlib.sha256(SCANNER_SOURCE.encode()).hexdigest()!='0b2bde7827c4727bd74970b380a410e4184f415f590c53e4aceef9f198155c74':
  raise ValueError('source_mismatch')
 exec(compile(SCANNER_SOURCE,'m02_reviewed_scanner','exec'),ns)
 actual=[ns['scan_file'](entry) for entry in ns['FILES']]
 if actual!=EXPECTED_FILES:raise ValueError('receipt_replay_mismatch')
 selected=[]
 counts={}
 for entry in ns['FILES']:
  sha=hashlib.sha256();count=size=0;matching=0;rules=Counter()
  with open(entry['path'],'rb') as handle:
   while raw:=handle.readline(ns['MAX_LINE']+1):
    if len(raw)>ns['MAX_LINE']:raise ValueError('oversize')
    count+=1;size+=len(raw);sha.update(raw)
    row=ns['parse'](raw)
    pr=ns['signals'](row['prompt']);cr=ns['signals'](row['completion']);pair=[]
    if ns['normalize'](row['prompt']).count('=')+ns['normalize'](row['completion']).count('=')>=2:
     pair=['two_symbolic_equalities']
    hits=sorted(set(pr+cr+pair));rules.update(hits);matching+=bool(hits)
    if set(hits)-{'coefficient_value'}:
     selected.append({'role':entry['role'],'line':count,'raw_line_sha256':hashlib.sha256(raw).hexdigest(),'source':row['source'],'prompt_rules':pr,'completion_rules':cr,'pair_rules':pair,'prompt':row['prompt'],'completion':row['completion']})
     if len(selected)>64:raise ValueError('review_cap_exceeded')
  if (count,size,sha.hexdigest())!=(entry['rows'],entry['bytes'],entry['sha256']):raise ValueError('re_read_identity_mismatch')
  expected=next(x for x in EXPECTED_FILES if x['role']==entry['role'])
  if dict(rules)!=expected['rules'] or matching!=expected['matching_rows']:raise ValueError('rules_mismatch')
  counts[entry['role']]={'rows':count,'bytes':size,'sha256':sha.hexdigest(),'all_lexical_positive_rows':matching,'selected_review_rows':sum(x['role']==entry['role'] for x in selected),'rules':dict(sorted(rules.items()))}
except Exception:
 print(json.dumps({'status':'failed_before_text_emission'}));sys.exit(1)
print(json.dumps({'status':'bounded_review_extraction_complete','executed_utc':datetime.now(timezone.utc).isoformat(),'receipt_replay_exact':True,'source_sha256':hashlib.sha256(SCANNER_SOURCE.encode()).hexdigest(),'counts':counts,'selected_rows':selected},ensure_ascii=False))
'''
prefix='SCANNER_SOURCE='+repr(source)+'\nEXPECTED_FILES='+repr(prior['files'])+'\n'
program=prefix+wrapper
print('EXTRACTION_WRAPPER_SHA256',hashlib.sha256(wrapper.encode()).hexdigest())
print('EXACT_STDIN_SHA256',hashlib.sha256(program.encode()).hexdigest())
argv=['ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=15','ubuntu@129.213.31.157','/usr/bin/python3','-']
p=subprocess.run(argv,input=program,text=True,capture_output=True,timeout=50)
print('EXIT',p.returncode)
if p.returncode:
 print('Remote extraction failed; no source text retained.')
else:
 result=json.loads(p.stdout)
 print(json.dumps({k:v for k,v in result.items() if k!='selected_rows'},ensure_ascii=False,indent=2))
 for row in result['selected_rows']:print(json.dumps(row,ensure_ascii=False))
```
