# Audit-only holdout validator implementation

Status: bounded implementation, before any fresh battery or finalist inference.
The governing design and inventory remain unchanged. This is not a benchmark
builder, semantic-cleanliness certificate, answer grader, or inference runner.

## Scope and references

Read ROADMAP's 18 July benchmark/contamination section (lines 344–354), the
full-data winner-test design and inventory, existing `campaign_io.py` manifest
verification, and `muta_dataset_v2/core.py` normalization/overlap logic.
Keep internal product evidence distinct from official ADTC scoring. Local
corpus copies, downloads, training changes and model outputs are out of scope.

Own only new `bench/round2_holdout_audit.py`, its synthetic-fixture tests and
this plan. Existing builders, current evaluations and large data stay intact.

## Implementation

1. Validate a bounded candidate JSONL schema: identifiers, stratum, subject,
   topic/difficulty/mode, prompt/reference answer, rubric, source revision,
   source-specific family identity and independent reviewer evidence. Evidence
   is a content-addressed local file plus an explicit human/agent attribution;
   its existence/hash can be checked, not the truth of a review attestation.
2. Accept a small input specification naming required source datasets and
   either an exact manifest hash or an explicit unavailable-source reason.
   Verify manifests/shards with an audit-local bounded SHA/count/byte reader,
   preserving existing campaign receipt/fingerprint conventions, then rehash
   bytes while streaming to detect between-pass mutation. Reject malformed rows and
   path/duplicate-manifest errors; never silently skip unavailable inputs.
3. Index only candidates for exact text, math-preserving normalized text,
   source-task hashes, five-gram lexical overlap and source-specific families.
   Stream manifest-listed corpus rows, retaining bounded match examples and
   aggregate counts. Audit candidate-to-candidate overlap too. Repeated family
   hits must not produce millions of output rows.
4. Write only compact metadata: hashed corpus row identities, candidate IDs,
   match kind/count, limited matching examples, input/evidence/code hashes,
   unresolved coverage and explicit semantic limitations. Never copy prompts,
   answers, reviewer prose or private row text into reports. Refuse existing
   output files. No "clean" or benchmark-ready verdict.
5. Test schema/evidence validation, exact/normalization/lexical/family matching,
   changed mathematical signs/numbers, undetected paraphrases, duplicate
   candidates, malformed source rows, hash tampering and mutation during scan,
   unavailable inputs, compact output caps and non-overwrite behavior.

## Handoff gate

Run focused offline tests and lint. A separate adversarial reviewer must inspect
the validator before using it on the real private corpora. Do not run a full
multi-gigabyte audit until a candidate pool exists and input coverage is fixed.
The proposed 2,000-item battery remains unmaterialized and unfrozen.

## Implemented input contract and CLI

Run from the repository checkout; this is repository tooling, not a packaged
desktop/runtime feature:

```sh
.venv/bin/python -m bench.round2_holdout_audit \
  --input-specification /path/to/audit-inputs.json \
  --output /path/to/new-audit-report.json
```

The input JSON object requires `schema_version: 1`, `candidates`, `datasets`,
`lexical_threshold` and `example_cap`. `candidates` names a local JSONL `path`
and its exact `sha256`. An available dataset entry requires `id`, `role`,
`manifest`, `manifest_sha256` and `row_schema` (`muta_v2`, `prompt_v1`, or the
bounded historical `incumbent_raw_v1` adapter described below). A
missing dataset instead requires `id`, `role` and `unavailable`, whose fields
are `reason_code` and `note`. The code emits the reason code and note hash,
never the note prose. Permitted reason codes are `not_located`,
`not_materialized`, `not_authorized` and `not_applicable`.

Required campaign-coverage roles are `warehouse`, `selected_train`,
`development`, `incumbent_train`, `incumbent_development` and `known_suite`.
An `other_exclusion` role is also supported. Missing or unavailable roles
remain explicit in the report; declaring a role is not proof that the source
inventory is complete. Every available source manifest uses the existing
campaign shard/count/byte/hash/fingerprint format. An audit-local bounded reader
verifies it before scan, then its bytes are rehashed during bounded streaming
to reject between-pass mutation. The shared `count_jsonl_rows` and manifest
verifier are not invoked: their unlimited line iterator would allocate an
oversized line before the audit's guard could reject it. Shared production
helpers remain unchanged. Python and Unicode database versions are retained
alongside normalization code hashes.

Candidate JSONL rows require these fields:

- `schema_version`, stable `id`, and `author_id`.
- `stratum`, `subject`, `topic`, `difficulty`, and tutoring `mode`.
- `prompt`, `source_task`, reference `answer`, and an explicit `rubric` list of
  `{id, criterion, weight}` objects.
- `source: {id, revision, license}` and
  `family: {namespace, id, basis}`. Family basis is `generator`, `template`,
  `manual` or `singleton`; family declarations are not inferred or endorsed.
- Exactly two `review_evidence` references with `{kind, path, sha256}`: one
  `answer_and_rubric` and one `family_and_provenance`.

Each referenced review is a bounded local JSON file within the candidate file's
directory tree. It requires `schema_version`, `candidate_id`,
`candidate_content_sha256`, `kind`, `reviewer_id`, `reviewer_type` (`human` or
`agent`), `method`, `decision` (`approved`, `needs_review`, `rejected`) and
`notes`. Its candidate content hash is SHA-256 of canonical sorted compact
UTF-8 JSON excluding `review_evidence`; the helper
`candidate_content_sha256()` implements that binding. Reviewers must differ
from the author ID, but those identifiers/decisions remain self-attestations.
Unapproved reviews are recorded, not converted into approvals.

`muta_v2` source rows must supply the audit-relevant prompt, answer, completion,
matching messages, provenance/source-family fields and contamination hashes.
`prompt_v1` is a small future adapter format for known suites: each row has
`id`, `prompt`, `source_id`, explicit `family` (a `{namespace, id}` object or
`null`), and optionally `source_task_sha256`. Without that optional hash, the
normalized full prompt is its task identity. Such source packs do not exist
merely because this interface supports them.

`incumbent_raw_v1` reads the four-field historical licensed-MCQ records in place:
`prompt`, `completion`, `source`, `mode`. It requires `mode=raw`, a source label
of `arc_easy_train`, `arc_challenge_train` or `qasc_train`, and the exact
`Question: ...\nAnswer:` wrapper. It retains the raw prompt for matching and
also hashes the normalized unwrapped question as a source task. Opaque row
identity is derived from canonical content. These files have no family metadata,
so family remains null and missing-family counts remain visible. See the recovery
plan for their verified remote paths/hashes; no training rows were copied locally.
This adapter does not establish that the reference answers or families are correct.

Limits: 5,000 candidates / 64 MiB candidate JSONL; 64 declared source datasets;
bounded JSONL rows; 100,000 finding groups; at most 10,000 retained match
examples globally and the smaller per-group `example_cap`. All match counts
are retained within the group bound, and omitted examples are counted. Exceeding
the group bound fails rather than silently omitting matches. Source prose,
answers and reviewer notes are not copied to the report. Existing output files
are never overwritten. The report always says benchmark readiness is
`not_assessed`, including when no implemented check produces a flag.

## Initial verification

The initial implementation passed 44 focused synthetic-fixture tests. Independent
review found an unbounded initial line-count read; the audit-local verifier now
bounds every source line in both verification and comparison passes. Three
additional tests cover oversized input, ordinary input without any shared
unbounded counter, and oversized mutation between passes. All 47 focused tests
and 87 combined audit/evaluator/compiler tests pass, as do Ruff checks.
No real candidate battery or multi-gigabyte corpus scan was run. Independent
agent reviewer `full_launch_writer` confirmed GO on the corrected code at
SHA-256 `500c12e372c3d2c23e2beb516ce369f452fa06102223612385d85bbf3c732c4f`
after inspecting both bounded passes and independently running the 47 focused
tests, Ruff and whitespace checks. This code-review GO does not certify a
candidate battery, any source rights, semantic independence or benchmark readiness.

The historical `incumbent_raw_v1` extension then added nine tests, bringing the
focused suite to 56 passing tests; Ruff passed. Independent agent reviewer
`full_promotion_audit` returned GO on validator SHA256
`cf156c43fc724f3306ec94604ef70d34da967614958777b92ac9bc23b0327c3b`,
checking strict historical fields/wrapper, source privacy, mathematical signs and
explicit missing-family counts. No candidate-versus-corpus scan was performed.
