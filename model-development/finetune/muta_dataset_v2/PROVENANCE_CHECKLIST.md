# Gate 2 provenance checklist for the next Muta fine-tune

The dataset package solves only the data-construction portion. The training task must preserve the
following evidence before a tuned model is treated as a Gate 2 candidate.

## Model provenance section in the report

- Exact repository for local generators and build code:
  `https://github.com/nelsonifechukwu/Muta`, exact Git commit, MIT licence, and repository snapshot
  hash. Do not replace MIT with a custom or private licence label.
- Exact base repository: `Qwen/Qwen2.5-1.5B-Instruct` unless the reviewed experiment changes it.
- Exact base revision and the Git SHA embedded in model metadata.
- Fine-tuning method and all hyperparameters.
- Every dataset/source, immutable revision, accepted row count, licence, transformation, and audit
  result.
- Base-model and tokenizer licence names, URLs, immutable text snapshots, and SHA-256 hashes.
- At least two identical prompts run against the unmodified base and each tuned candidate.
- Full, unedited outputs saved under identical prompt template, context, generation settings, and
  runtime conditions—not just scores or excerpts.

## Required `provenance/` artifacts

- `adapter_model.safetensors`
- `adapter_config.json`
- exact training script, resolved config, and notebook (if used)
- per-step or per-epoch training/evaluation logs
- frozen warehouse and SFT manifests, shard hashes, source registry, schema, recipe, complete
  warehouse provenance-code/provenance-holdouts/provenance-source-evidence directories, review
  decisions, and a distributable sample/link/description as each source licence permits
- hashed mixed-source attribution inventory: creator/title, source ID, revision/config/split,
  selected count, licence text/hash/URL, transformation/change notice, synthetic flag,
  verification/audit result, and evidence receipt
- SHA-256 for base artifacts, adapter, merged model, and final GGUF
- exact merge/export script
- exact GGUF conversion and quantization script, including pinned llama.cpp revision
- hosted-notebook link if training used a hosted notebook

## Before training

- Copy the final dataset manifest and code/config hashes into `provenance/dataset/`.
- Verify every shard hash and record the aggregate dataset fingerprint.
- Treat the candidate warehouse as an audit pool, not as the training dataset. A registry entry,
  warehouse allocation, or candidate manifest is not authorization to train.
- Materialize and hash a separate SFT view; report its actual per-source row counts independently
  of the 2.5M warehouse and 300K selection targets.
- Preserve the state transition explicitly: recipe target → completed candidate warehouse →
  reviewed/authorized SFT selection → examples and tokens actually consumed during training. None
  of these counts implies the next.
- Confirm every SFT row has warehouse `split: train`, comes from an enabled source and allowed
  original source split, matches the registered licence/revision, and passes
  provenance/schema/verifier/deduplication/holdout gates. Authorization
  must be either immutable native `training_eligible: true` metadata or a matching exact-row
  receipt whose decision is `approved`; never edit the warehouse row or approve an entire source
  by assertion.
- Save original source-split and template/semantic-cluster assignments. Require immutable approval
  receipts keyed to each exact row, reviewer attestation, method, version, content hash, and a
  supplied rubric artifact hash before an audit-gated row can enter SFT; never authorize it by
  editing a Boolean or blanket-approving a template/cluster.
- Group all prompt/pedagogy variants by `contamination.source_task_sha256`; cap their multiplicity
  in SFT weighting and never allow one canonical base task to cross train/development/evaluation.
- Run the deterministic SFT selector rather than copying rows ad hoc. Preserve its resolved quotas,
  exclusion counts, approval/rejection decision inventory, output shard hashes, and aggregate
  fingerprint.
- The earlier proposal for 20,000 approved audit-gated rows is superseded for this SFT version.
  Preserve all 20,000 exact-record rejection receipts and the frozen rubric, select zero
  TemplateGSM/QASC/GSM8K rows, and use the documented native verified replacement quotas. A later
  dataset version may reconsider those sources only after a new exhaustive audit with independent
  semantic evidence; statistical source sampling does not authorize rows.
- Treat the warehouse `template_holdout` as an imbalanced template-OOD challenge, not the
  representative development set or official evaluation. Keep its clusters out of the SFT view.
- Solve the final 300K subject × pedagogy quotas globally after source audit. Do not assume a
  proportional local or external sample meets the target.
- Freeze the judge prompts, STEM-100, ARC-Easy-500, and upstream validation/test holdouts.
- Export at least two unmodified-base full outputs before loading any adapter.
- For any DeepMind-generator build, retain the archived determinism overlay/version/hash and the
  passing two-subprocess stream-digest receipt. Launch with `PYTHONHASHSEED=3407` as an additional
  fixed startup condition and retain the recorded seed/hash probe.
- Preserve a per-holdout-source receipt containing repository/config/split/revision, prompt count,
  and normalized-set digest without exposing sealed prompt text. A combined holdout digest alone is
  insufficient for offline reproduction.

## Protected-exam boundary and permission evidence

- Under this dataset policy, without written permission WAEC, CheetahWAEC, MySchoolGist/JAMB, and ALOC contribute only
  independently worded high-level topic, skill, broad-format, rubric-structure, and error-category
  labels. No question, answer, explanation, marking scheme, report prose, figure, screenshot, OCR,
  close paraphrase, or source-derived row may enter the warehouse, SFT, or evaluation.
- Permissioned source items default to a separate quarantined, temporally held-out evaluation-only
  store. Evaluation permission does not imply training permission, and evaluation-only rows must
  never appear in the SFT manifest.
- For WAEC material, retain an executed WAEC grant. For CheetahWAEC, retain Cheetah permission for
  explanations/automated access and separate WAEC or underlying-exam-rightsholder clearance. For
  MySchoolGist/JAMB, retain MySchoolGist permission for its content/access and separate JAMB or
  underlying-rightsholder clearance.
- For ALOC, ordinary API credentials and credit purchases are insufficient. Retain a signed bespoke
  amendment that expressly permits systematic server-side export, permanent offline storage,
  evaluation, fine-tuning, derived transformations, and adapter/merged-weight distribution despite
  the standard caching, cold-mirroring, cursor-traversal, and AI-training prohibitions. Require a
  representation of ALOC's authority to license each included exam corpus and record any separate
  exam-body clearance. Never store API credentials in the repository or provenance bundle.
- Each grant must explicitly state countries, years, subjects, papers, solutions, figures,
  retrieval/OCR, storage, evaluation, training, derived-dataset, adapter/model-weight distribution,
  territory, duration, and attribution rights. Store the grant, correspondence, source snapshot,
  and hashes before changing a source status or enabling an adapter.

## After training

- Save full tuned outputs for the identical prompts and inference configuration.
- Compare correctness, pedagogy, hallucination, refusal behaviour, latency, and memory—not only
  exact answer accuracy.
- Keep failed candidates and logs; do not overwrite them with the winner.
- Record merge and quantization hashes and verify the submitted GGUF reproduces the evaluated
  candidate.
- Do not claim a stock model or indistinguishable adapter as fine-tuned evidence.
