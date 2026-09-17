# Muta STEM SFT Dataset v2

This package defines a reproducible, provenance-first candidate warehouse for the next Muta
fine-tune. It is designed for **Muta Tutor Qwen2.5 1.5B**, but it does not start a training run.
The dataset must be reviewed and frozen first.

## What exists

- `recipe.json`: an exact 2,500,000-row candidate-warehouse recipe and a separate 300,000-row
  first-SFT selection target. Neither number is an authorization or claim that those rows are
  training-eligible.
- `source_registry.json`: allowlisted, candidate-only, evaluation-only, and prohibited sources,
  each with its immutable revision or dated rights review.
- `schema.json`: the per-row contract, including curriculum era, provenance, verification, and
  contamination evidence.
- `generators.py`: 30 active original Muta maths/physics/chemistry/biology problem families with
  independent answer recomputation and five tutoring response modes. Five evaluation-guided
  families are explicitly quarantined. These locally generated rows are MIT licensed under the
  [Muta repository](https://github.com/nelsonifechukwu/Muta).
- `adapters.py`: opt-in adapters for pinned open sources. There is intentionally no WAEC, JAMB,
  CheetahWAEC, ALOC, or other proprietary-site scraper/OCR path.
- `build.py`: deterministic sharding, exact source quotas, source receipts, artifact hashes,
  cluster-level train/template-holdout assignment, canonical-task deduplication, contamination
  gates, and unambiguous failure receipts.
- `sample.py`: deterministic, source-filterable review sampling that revalidates every warehouse
  row and shard before selecting a sample.
- `select_sft.py`: deterministic 300K materializer with exhaustive shard/row integrity checks,
  exact global quotas, train-only selection, canonical-task/template caps, and atomic output.
- `audit_review_pack.py`: deterministic exact-row review-pack materializer for the 20K
  audit-gated external allocation. It uses the selector's warehouse trust boundary and caps, but
  emits no approval or rejection decisions.
- `approval-receipt.schema.json`: content-addressed exact-row review decisions for otherwise
  ineligible candidates. Each decision records the review method and binds a supplied, archived
  rubric file. The method must state whether review was human or model-assisted. Rejections remain
  evidence and never authorize selection; reviewer IDs are attestations, not cryptographic
  signatures.
- `review-sample.jsonl` and `review-sample-manifest.json`: final-build outputs, intentionally absent
  until a warehouse has a successful manifest. Any sample from an earlier schema/build is
  historical evidence, not a current review artifact.
- `SOURCES.md`: the research and rights decision log.
- `ALOC_PERMISSION_REQUEST.md`: a ready-to-send request for a bespoke bulk-export and AI-training
  licence; no supplied API credential is recorded in the package.
- `V7_AUDIT_REPORT.md`: the completed warehouse receipts, independent gates, adversarial verdict,
  semantic findings, and remaining training blockers.
- `EXTERNAL_20K_AUDIT_REPORT.md`: the final fail-closed disposition of the frozen 20,000-row
  external review pack and the independent integrity result for the replacement 300K SFT view.
- `PROVENANCE_CHECKLIST.md`: the Gate 2 evidence package to complete alongside training.

Large generated artifacts live under ignored `data/`; the package stores the recipe and code now,
then adds the small review sample and its cryptographic manifest only after the finalized warehouse
passes verification. No pre-final sample is current evidence.

## Completed v7 candidate artifacts

The completed 16 September 2026 v7 warehouse is stored at
`data/muta-stem-v2-warehouse-20260916-v7/`. It has 2,500,000 rows in 100 shards of 25,000 rows,
dataset fingerprint
`0197679d767281c26537e388b6c1f703bdfcf032e02f19b1b2d2b435bf572941`, and manifest SHA-256
`3743901055c075a9ec8fd75414343620608c0426649bc4aa95f6b7211a5cf0e4`. Every shard hash was
independently rechecked, and the review-pack materializer revalidated all 2.5M rows against the
archived schema and registry.

The balanced local review sample is
`data/muta-stem-v2-review-local-750-20260916-v7.jsonl`: five deterministic examples for every one
of 30 topics × five pedagogy modes, SHA-256
`bc17072e0aec58ce7234d73ad543abc37a2a7a0dbcdbde2eeec9453206d3cb8b`. The external exact-row
review pack is `data/muta-stem-v2-external-audit-review-20k-20260916-v7/`: 10,000 TemplateGSM,
5,000 QASC, and 5,000 GSM8K rows, manifest SHA-256
`c64a3e24e046fe61218b8d49ac082d927ddb6ff33cb9249782ac7977e4326415`. These are review artifacts,
not training authorization. ALOC and every other protected source contribute zero v7 rows.

## Exact-row audit outcome and corrected SFT allocation

The 17 September 2026 model-assisted audit did not validate the planned external allocation.
QASC lacked exhaustive semantic evidence and had deterministic ambiguity/quality defects.
TemplateGSM and GSM8K each produced provisional approvals that fresh adversarial review falsified;
the GSM8K refill checker also approved a known-invalid reserve row. The final decision is therefore
fail-closed: all 20,000 packed external rows are retained as rejected audit evidence, and
TemplateGSM, QASC, and GSM8K contribute zero rows to this SFT version.

The corrected recipe replaces those slots while preserving their margins: +15,000 native
mathematics and +5,000 native integrated-science rows by subject, and +15,000 worked-solution and
+5,000 concise-answer rows by pedagogy. It still selects exactly 300,000 rows and keeps the original
50/18/14/14/4 subject and 40/20/20/10/10 pedagogy margins. The warehouse is unchanged.
Its native quota matrix starts from the nearest-integer subject × pedagogy independence table for
the former 260,000-row native residual. The one-row-per-canonical-task cap leaves only 4,892 safe
integrated-science/concise candidates, so the joint-cell additions are +14,757 mathematics/worked,
+243 mathematics/concise, +243 integrated-science/worked, and +4,757 integrated-science/concise.
This 243-row paired redistribution preserves every margin and all 25 positive native cells without
weakening the deduplication gate.
The selector permits only documented SFT-allocation, native-cell-quota, and training-note overrides;
it rejects changes to the seed, warehouse recipe, target count, target margins, caps, or generation
settings and archives both recipe hashes in the selected artifact.

## Completed quality-first SFT artifact

The corrected train-only view is now materialized at
`data/muta-stem-v2-sft-300k-quality-first-20260917-v1/`. It contains 300,000 rows in 12 shards of
25,000 rows, with dataset fingerprint
`ee1a31f2cfef256fda86166f6d420811c27ae0656728b7ef582327074e82340e` and manifest SHA-256
`f3c5c6f66a194603cdc9f3e05a96b09338fc9c90437b95689014c1adb167eabe`.

An independent post-materialization scan rehashed every shard and 38 archived provenance inputs,
parsed every JSONL row, and confirmed 300,000 unique row IDs, 300,000 unique canonical source-task
hashes, exact global and joint-cell quotas, valid two-message training pairs, recorded token limits,
holdout checks, and native training eligibility. It found no selected rejected-review ID, no
TemplateGSM/QASC/GSM8K row, and no partial file. The exact evidence and limitations are in
`EXTERNAL_20K_AUDIT_REPORT.md`.

The 2026-09-17 intake of `corpus/waec/` is separately audited at
`data/muta-corpus-training-intake-audit-20260917-v2/` and documented in
`docs/corpus/2026-09-17-waec-training-intake-audit.md`. All 1,906 records are schema-valid, but only
382 are marked complete, 1,524 carry extraction warnings, 203 lack an answer, and zero answers have
independent verification. The audit therefore admits zero source rows and re-confirms the same
300K fingerprint and manifest hash above. Its content-free taxonomy counts may guide future
original generators; its source wording and media remain quarantined.

## Why this is not a scrape of past papers

Free viewing or downloading is not an open-data licence. WAEC marks its e-learning archive as
copyrighted and all-rights-reserved. CheetahWAEC's terms prohibit scraping, harvesting, or mass
downloading when it harms the site or other users; separately, they reserve its explanations and
acknowledge third-party rights, without granting model-training reuse. MySchoolGist calls its JAMB
PDFs free to download for study, but also carries a copyright notice and supplies no bulk-training
grant. ALOC exposes exam questions through an API, but its standard Developer Terms prohibit
permanent wholesale synchronization, systematic cursor crawling, and using API content to train,
fine-tune, evaluate, or benchmark an AI model. API availability or paid credits therefore do not
authorize a Muta ingest.

Accordingly, the no-permission boundary is **independently worded taxonomy only**: high-level
skills, topic labels, broad item formats, rubric structure, and error categories may guide original
generation. No source question, answer, explanation, marking scheme, report prose, figure,
screenshot, OCR, close paraphrase, or source-derived row enters the candidate warehouse, the SFT
view, or an evaluation set. A screenshot is another representation of the same content; it does
not change its licence.

Under this dataset policy, protected items are excluded unless covered by a written grant. This is
a conservative project rule, not a legal conclusion about every fact-specific statutory exception.
The default permissioned route is a
separate, quarantined, temporally held-out **evaluation-only** store, excluded from the warehouse
and every SFT selection. Training requires a further explicit grant covering training and the
intended artifact distribution. For WAEC, obtain that grant directly from WAEC. For CheetahWAEC,
obtain Cheetah's permission for its explanations and automated access plus WAEC/other underlying
rightsholder clearance for the exam content. For MySchoolGist/JAMB, obtain MySchoolGist's permission
for its content/access plus JAMB/other underlying rightsholder clearance for exam items.
For ALOC, obtain a signed bespoke agreement that expressly overrides the relevant storage,
automated-retrieval, and AI-training restrictions and identifies ALOC's authority to license the
underlying exam content. The enterprise bulk-data option mentioned in the standard terms is not,
by itself, an AI-training grant.

Each executed grant must identify the authorized countries, years, subjects, papers, solutions,
figures, automated retrieval/OCR, storage, evaluation, training, derived datasets,
adapter/model-weight distribution, territory, duration, and attribution. Store the grant and
artifact hashes before enabling an adapter or changing a registry status.

## Previous Muta fine-tune, briefly

The earlier finalist trained a BF16 LoRA on
`Qwen/Qwen2.5-1.5B-Instruct@989aa7980e4cf806f80c7fef2b1adb7bc71aa306`:

- rank 16, alpha 16, dropout 0;
- attention projections plus MLP gate/up/down projections;
- completion-only loss, context length 1,024;
- micro-batch 4 × gradient accumulation 4 = effective batch 16;
- learning rate 2e-5, cosine schedule, 5% warm-up, AdamW 8-bit, seed 3407;
- 500 steps (0.74377 epoch) on an A100 40 GB;
- merged 16-bit, then converted to Q4_K_M GGUF.

The dataset was 10,756 train + 566 validation MCQs from ARC Easy/Challenge and QASC, formatted as
short answer-text continuations. It improved ARC-Easy-500 from 74.4% to 77.8%, but did not teach
worked solutions, tutoring dialogue, or broad scientific reasoning. The next run therefore keeps
the good provenance discipline while changing both the data shape and the evidence package.

## Candidate warehouse versus training-eligible SFT

The 2.5M warehouse is a reproducible, mathematics-heavy diversity pool, not a balanced training
dataset. 1,085,000 rows come from the original Muta generator, deliberately weighted 25% maths
and 75% across physics, chemistry, biology, and integrated science; open symbolic/word-problem
sources supply most remaining volume. A source's appearance in
`source_registry.json`, a warehouse allocation, or a manifest is not permission to train on it.
Prohibited and evaluation-only sources are registry records only: their content is not acquired and
they contribute zero warehouse rows.

Candidate rows in the warehouse have three tiers:

1. **Eligible candidates**: original Muta rows with independently recomputed answers and fresh
   rows from the pinned DeepMind symbolic generator. Eligibility never overrides split:
   `template_holdout` rows remain forbidden for SFT.
2. **Audit required**: TemplateGSM, QASC, and GSM8K transformations. These are useful candidates,
   but real samples exposed awkward wording and occasional semantic defects. TemplateGSM is first
   passed through a conservative no-code-execution semantic filter and whole-template quarantine;
   this reduces its warehouse allocation to 350,000 and replaces 80,000 rows with independently
   recomputed original Muta STEM rows.
   `templategsm_filter_audit.json` binds the pinned 2M configuration and records 226,263 rejected
   rows, 362 quarantined templates, and 655,200 surviving capacity at cap 400; the adapter fails
   closed on its revision/config/checker/hash bindings and reapplies the row checker defensively.
   This is intentionally a high-precision static screen, not a semantic proof: its lexical
   approximation escape examines a ±120-character window and can miss a contradiction when words
   such as `about` occur nearby for an unrelated reason.
   Release warehouse builds also require `--templategsm-snapshot`: before creating the output
   directory, the builder authenticates the pinned local 2,000-file snapshot, its 2,403,438,064
   data bytes, aggregate inventory SHA-256
   `9100d9daa8214a5018124e2e44dc1ee0378ecd0a992f4c450430d76f95801132`, and README SHA-256
   `20b70e0f0d41021e54e4a73b1972fde7f6355f405bd67eef00472e4ce711ba7a`.
   It repeats the complete authentication after row consumption and before issuing a manifest.
   The remaining immutable warehouse rows remain
   `training_eligible: false`; a later selector may use one only when a
   matching exact-row audit receipt whose decision is `approved` binds the warehouse fingerprint,
   row ID, content hash, reviewer, review method, and rubric. It does not edit the warehouse row.
3. **Excluded from acquisition/default build**: protected exam banks, unclear licences,
   non-commercial material, evaluation benchmarks, sources with unresolved lineage, and Nemotron
   Science after its level filter admitted graduate medical material remain registry metadata, not
   rows.

The recommended 300K figure is a selection target, not a proportional sample or command to train.
The deterministic selector solves the declared overall 50/18/14/14/4 subject quotas and
40/20/20/10/10 pedagogy quotas after external-source audit; it must derive the residual local-row
quotas rather than reuse the local warehouse proportions. The
actual SFT view may contain only rows whose source status and split are enabled, whose licence and
revision match the registry, and which pass provenance/schema/verifier/deduplication/holdout gates.
Authorization is either native `training_eligible: true` or a matching immutable exact-row audit
receipt whose decision is `approved`; changing a warehouse Boolean or approving a whole source is
insufficient. Selection groups rows
by canonical source-task hash, caps repeated pedagogy variants, and keeps a base task out of more
than one split. The SFT view has its own immutable manifest, approval-receipt hashes, and row
counts; warehouse totals must never be reported as training totals. More rows are accepted only if
identical held-out prompts show a net improvement in correctness, tutoring quality, and robustness.

For the corrected quality-first recipe, the selector needs no external approval receipts because no
audit-gated source has a positive quota. The final build still supplies the 20,000 rejected receipts
and frozen rubric so that the selected artifact archives the complete exclusion evidence:

```bash
PYTHONHASHSEED=3407 data/muta-dataset-build-env/bin/python \
  -m model-development.finetune.muta_dataset_v2.select_sft \
  --warehouse data/muta-stem-v2-warehouse-20260916-v7 \
  --recipe model-development/finetune/muta_dataset_v2/recipe.json \
  --approval-receipt \
    data/muta-stem-v2-external-audit-rejection-receipts-20260917-v3/approval-receipts.jsonl \
  --rubric model-development/finetune/muta_dataset_v2/EXTERNAL_ROW_AUDIT_RUBRIC_V1.md \
  --output data/muta-stem-v2-sft-300k-quality-first-20260917-v1
```

It verifies every warehouse shard and revalidates every row's schema, identity, provenance,
deduplication, recorded token metadata, counts, and receipt/rubric bindings. It checks live
validators against archived code hashes, solves source × subject × pedagogy margins, and archives
its own selector, recipe, decision, rubric, and source-manifest evidence. It does not refetch or
replay remote holdout corpora and it does not retokenize all rows; those two expensive operations
are trusted from the warehouse's hashed build evidence and must remain preserved with the SFT view.

The original 300K allocation proposed 20,000 approved audit-gated rows: 10,000 TemplateGSM, 5,000
QASC, and 5,000 GSM8K. That proposal is now superseded by the quality-first allocation above. The
review-pack and refill procedure below remain reproducible diagnostic tooling for a future source
version with a stronger verifier; they do not authorize any row in the current external pack.

```bash
PYTHONHASHSEED=3407 data/muta-dataset-build-env/bin/python \
  -m model-development.finetune.muta_dataset_v2.audit_review_pack \
  --warehouse data/muta-stem-v2-warehouse \
  --output data/muta-stem-v2-external-audit-review-20k
```

The output JSONL wraps each unchanged warehouse record with its warehouse fingerprint, stable row
ID, deterministic rank, and canonical content hash. Its manifest binds every row and the current
approval-receipt schema. It also verifies, archives, and hashes both the materializer and the exact
`select_sft.py` implementation whose warehouse checks, ranks, and caps it reuses. The pack is
evidence for review only and never authorizes training.

After reviewers issue content-addressed decisions for the current pack, generate the next
deterministic refill batch with the caller-maintained cumulative ledger and its rubric artifacts:

```bash
PYTHONHASHSEED=3407 data/muta-dataset-build-env/bin/python \
  -m model-development.finetune.muta_dataset_v2.audit_review_pack \
  --warehouse data/muta-stem-v2-warehouse \
  --decision-receipt reviews/external-audit-decisions.jsonl \
  --rubric reviews/external-row-audit-rubric.md \
  --output data/muta-stem-v2-external-audit-refill-001
```

Approved rows count toward the fixed source quotas and consume the selector caps. Rejected rows
remain ledger evidence but never authorize training; they are removed before the caps are reapplied,
so the next eligible row from a rejected row's task or template can enter the refill. Undecided rows
repeat by design, preventing a missing receipt from silently skipping a candidate. Continue with the
complete cumulative ledger until the manifest reports zero refill rows and 10,000 TemplateGSM,
5,000 QASC, and 5,000 GSM8K approvals. The materializer validates and archives the supplied ledger
and rubrics, but cannot infer that the caller supplied every prior decision; an omitted decision
therefore causes that still-undecided row to reappear rather than silently skipping it.

## Per-row invariants

Every accepted row has:

- stable ID and two-message chat representation;
- answer, subject, topic, difficulty, format, and pedagogy mode;
- country, curriculum authority/version, exam era, and an honest alignment claim;
- source ID/revision/row ID, licence, synthetic flag, and transformation description;
- original source split and a semantic/template cluster ID included in immutable row identity;
- verifier status, expected/observed answer, verifier version, and eligibility gate;
- normalized prompt hash and maximum holdout five-gram similarity;
- canonical source-task hash, so differently rendered or pedagogical variants remain linked;
- exact sequence length under the pinned Qwen2.5 chat template and tokenizer revision, with a
  hard 1,024-token cap and no truncation.

The build rejects hidden-reasoning markers, mismatched answers, unregistered or disabled sources,
non-allowlisted licences/splits/statuses, mutable eligibility claims, schema failures, exact
duplicate prompts, duplicate IDs, and rendered prompts that contain or closely reproduce a
held-out question. It also rejects the same canonical task when it appears under different
sources. Common equivalent maths notation such as `x²`/`x^2`, `½`/`1/2`, and
`√16`/`sqrt(16)` is canonicalized before leakage comparison. Socratic targets stop after a question
and hint; the verified gold answer remains metadata and is not disclosed in the completion.

## Build

Use Python 3.11. The dependency environment is isolated from the runtime environment:

```bash
uv venv --python 3.11 data/muta-dataset-build-env
uv pip install --python data/muta-dataset-build-env/bin/python --require-hashes \
  -r model-development/finetune/muta_dataset_v2/requirements-build.lock.txt
```

Build a local 10K review pack:

```bash
PYTHONHASHSEED=3407 data/muta-dataset-build-env/bin/python \
  -m model-development.finetune.muta_dataset_v2.build \
  --profile review \
  --output data/muta-stem-v2-review \
  --local-rows 10000
```

Prepare the pinned DeepMind source tree:

```bash
git clone https://github.com/google-deepmind/mathematics_dataset.git \
  data/source-cache/deepmind-mathematics
git -C data/source-cache/deepmind-mathematics checkout \
  427f45075f84b8b9774950196ad63867ca20ffb3
```

Build the full candidate warehouse:

```bash
PYTHONHASHSEED=3407 data/muta-dataset-build-env/bin/python \
  -m model-development.finetune.muta_dataset_v2.build \
  --profile warehouse \
  --include-public-holdouts \
  --deepmind-checkout data/source-cache/deepmind-mathematics \
  --templategsm-snapshot data/source-cache/templategsm-2000-1k-0c8ed6b \
  --output data/muta-stem-v2-warehouse
```

External builds fail closed unless public validation/test prompts are loaded into the holdout
index. TemplateGSM warehouse rows are read only from the authenticated snapshot through the
streaming JSON builder, in lexicographic relative-path order within `0000-0999` and then
`1000-1999`; its manifest receipt states that no network was used for row materialization. The
snapshot README supplies the archived TemplateGSM source evidence, avoiding a release-time
refetch. A reviewed Muta overlay replaces upstream identity-set ordering with stable identity
deduplication, sorts symbol candidates, and seeds SymPy's private RNG per row. The builder proves
that overlay in two fresh subprocesses with different hash seeds before every DeepMind build. It
also requires `PYTHONHASHSEED=3407` at startup as defense in depth, records the seed/probe, and
refuses to overwrite a non-empty output directory. Every successful artifact has a manifest;
every failure after the output directory is touched has `FAILED.json` and no valid manifest.
Partial files retain a `.partial` suffix. Builds do not resume: restart into a fresh directory.

The warehouse's `template_holdout` is assigned by template cluster for TemplateGSM and module
cluster for DeepMind Mathematics. Local formulas and singleton QASC/GSM8K anchors remain in the
train candidate pool; their official upstream validation/test splits are sealed separately. The
template holdout is a deliberately imbalanced out-of-distribution challenge slice, not a
representative validation set or early-stopping metric. The SFT view needs a separately justified
development set while all official/judge/upstream holdouts remain sealed evaluations.

## Review protocol

1. Validate all shard hashes against `manifest.json`.
2. Regenerate and review the local topic × pedagogy `review-sample.jsonl` from the finalized
   warehouse; its sampler receipt authenticates the source warehouse and revalidates every row
   before selection. Use separately source-balanced external diagnostic samples.
3. Audit every generated family and a statistically meaningful diagnostic sample per external
   source, subject, topic, difficulty, and response mode. This diagnoses source quality but does not
   satisfy the exact-row authorization gate.
4. For the current v7 audit, retain the complete 20,000-row all-rejected final ledger and select
   the documented native replacements; do not refill or quota-force TemplateGSM, QASC, or GSM8K.
   A future source version may use selector-ranked refill batches only after its verifier and
   allocation receive a fresh review. Never edit rows silently or infer approval from a
   cluster/sample.
5. Recompute mathematics and units independently. For conceptual science, require a grounded fact
   review rather than trusting a publisher/model answer key.
6. Keep semantic/template clusters intact. Never randomly split parameter-substitution near-clones.
7. Re-run the exact judge suite, STEM-100, ARC-Easy-500, upstream validation/test sets, and the
   reserved multilingual AfriMGSM evaluation after training.
8. Save full base and tuned outputs under identical inference settings.

## Known limitations

- The original Muta generator covers quantitative STEM well but does not yet cover every practical,
  diagram, graph, and conceptual-science objective.
- Profit, equal-distance average speed, coloured-counter ratio, coloured-counter probability, and
  simple-interest families are quarantined because their semantic templates were guided by sealed
  evaluation items; five-gram distance cannot establish non-contamination.
- DeepMind rows have exact short answers, not rich worked derivations; they must not dominate the
  behavioural fine-tune.
- Silver-source rows are candidates, not correctness claims. They stay training-ineligible until
  the review record says otherwise.
- Actual WAEC/JAMB wording is absent pending a suitable licence.
