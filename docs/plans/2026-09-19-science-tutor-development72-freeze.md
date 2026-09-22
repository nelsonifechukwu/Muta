# Reviewed development72 materializer

Implement a fail-closed, CPU-only materializer for the four-parent selection
amendment. No inference is part of this work. Preserve the original proposed
development64 and all heldout final cases; write only a new development72-v1
directory after independent code review authorizes execution.

## Admission and construction

1. Pin the exact independent MC64, heldout-v2 content and bounded-overlap review
   receipts, original selection plan and four-parent amendment. Verify every
   small source/data binding in the reviews before parsing or selecting rows.
2. Recompute SHA256(3407:science-dev-v1:<id>) ordering. Consume every reviewed
   row in each bucket in order, rejecting explicitly rejected items and refusing
   an unreviewed gap. Require exactly the independently reviewed 64 IDs and keys,
   with source-row and model-message canonical hashes verified. Reproduce the
   initial 64 proposal independently as a preservation/selection check.
3. Join all 16 heldout cases to both independent receipts, then select exactly
   the eight development cases. Preserve the full user/assistant/user context;
   do not truncate the intentionally provided prior assistant utterance. Never
   include a final case. MC inputs omit the teacher's final assistant message.
4. Produce 72 minimal `{id,messages}` rows, a separate MC key file, and separate
   development tutoring rubrics. The inference file carries no keys, review
   commentary or grading metadata. The manifest binds all inputs, outputs,
   builder source, test source and this implementation plan. Review provenance
   is bounded agent review and lexical screening, not human certification or
   proof of semantic/family independence.

## Fail-closed output

Validate and serialize completely before creating the new output directory.
Refuse existing output, symlinked inputs/output ancestors, malformed JSON,
duplicate keys/IDs, changed inputs, and missing or non-affirmative reviews.
Recheck all input and builder/test/plan identities before publication; create
files exclusively and publish the manifest last. Never replace or remove an
existing directory. Preserve partial files plus a failure marker on failure;
no automatic retry or cleanup.

## Verification and release gate

CPU tests use temporary output only and cover the actual reviewed 72-item
construction plus adversarial hash, rank, key, role, review, output-existence,
symlink and mutation failures. Root independently reviews the exact tested
source before the real development72-v1 artifact is materialized. This plan
does not admit additional items, alter selection rules, or authorize inference.
