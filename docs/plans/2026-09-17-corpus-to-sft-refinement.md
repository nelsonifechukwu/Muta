# Corpus intake and 300K SFT refinement plan

Date: 2026-09-17

## Goal

Turn the newly added material under `corpus/` into an auditable input to the
Muta dataset pipeline, augment the existing 2.5M candidate warehouse in place,
and augment the existing 300K SFT artifact in place with the answer-verified
subset. The user explicitly rejected copied or parallel dataset artifacts
because of disk usage.

## Final scope clarification (user, 2026-09-17)

The user explicitly directed that the WAEC/Cheetah material be used for model
training and then explicitly directed that no copied dataset or backup be
created. The only authorized mutation is therefore an in-place append to:

- `data/muta-stem-v2-warehouse-20260916-v7`; and
- `data/muta-stem-v2-sft-300k-quality-first-20260917-v1`.

The instruction is recorded as a user attestation for this local/private-use
build. It does not relabel the publisher material as open licensed and does not
assert redistribution rights. The manifest must distinguish the publisher's
rights notice from the user's project-use attestation.

## Invariants

- Do not create a duplicate 300K or 2.5M dataset artifact or a backup copy.
- Append new shards rather than rewriting the existing large shards. Update
  each existing manifest atomically only after the appended shard validates.
- Record the user attestation as the local training authorization basis while
  retaining the publisher rights notice and `redistribution_allowed=false`.
- Public web access is not represented as an open training licence.
- Source rows with missing answers, broken visual dependencies, ambiguous
  marking schemes, or failed verification remain quarantined even if their
  rights status later changes.
- A published answer is evidence, not proof. Before admission, independently
  reproduce the answer from the complete prompt and record the verifier. If
  the published answer is wrong, retain the source answer in provenance,
  store the verified correction separately, and admit only the correction.
  Unanswered or unresolved rows never enter the training candidate.
- A protected exam source may contribute independently worded, non-expressive
  high-level curriculum signals (for example subject/topic frequency) only
  where the source registry explicitly allows that use.
- Every admitted SFT row must retain deterministic provenance, generation or
  verification evidence, and a stable content hash.

## Work plan

1. Inventory every corpus file and hash the normalized WAEC intake, manifest,
   schema, PDFs, and relevant local policy files.
2. Validate all normalized question rows against the corpus schema; measure
   exact and normalized duplicates, answer completeness, visual dependencies,
   warnings, source distribution, and subject/year/paper coverage.
3. Classify answer assurance separately from answer presence: independently
   re-solve machine-verifiable items, flag disagreements for correction, and
   quarantine every row whose answer cannot be reproduced confidently.
4. Review representative source PDFs visually and compare their pages with the
   normalized records to identify extraction or equation/image loss.
5. Record publisher rights and the user's private-use training attestation as
   separate provenance fields; do not describe the material as open licensed.
6. Convert only complete, self-contained, answer-bearing rows into valid SFT
   records. Retain source answer text in provenance and use a corrected answer
   whenever independent checking finds a discrepancy.
7. Append the validated rows as one small new shard to the existing warehouse
   and update its manifest, counts, receipts, fingerprint, and source registry
   snapshot in place.
8. Append only the independently checked/corrected subset as one small new
   shard to the existing SFT artifact and update its manifest and provenance
   in place. The artifact may exceed 300,000 rows after augmentation.
9. Run schema, hash, duplicate, leakage, answer-consistency, and provenance
   checks. Have a fresh reviewer try to break the result before final GO.

## Deliverables

- A reproducible corpus-intake/audit command and tests.
- An immutable intake artifact with manifests, aggregate taxonomy, quality
  statistics, and admission decisions.
- A comparison report against the current 300K artifact.
- In-place appended shards and atomically regenerated manifests for the current
  warehouse and SFT directories.
- A compact augmentation receipt containing source hashes, admitted/rejected
  row IDs, corrections, and the pre/post manifest fingerprints; no copied base
  dataset.

## Acceptance criteria

- Row counts and all reported hashes reproduce from source files.
- No source question, solution, answer, or media payload appears in the
  content-free audit artifact.
- Every source has an explicit training/evaluation/RAG decision and reason.
- Existing pre-augmentation shards remain byte-identical.
- Both augmented artifacts have unique task rows, pass schema and holdout
  checks, and receive a fresh adversarial review.
- Every appended SFT row has an explicit answer-verification receipt; missing,
  partial, visually dependent, or unresolved rows remain outside the SFT shard.
