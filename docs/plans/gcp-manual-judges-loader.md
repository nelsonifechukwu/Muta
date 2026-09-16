# GCP manual judges evidence loader

Add a read-only loader for the scalar campaign's two manual-review JSON schemas. Keep GCP provenance distinct from Mac evaluation. Accept additional JSONL records after a reviewed byte prefix, but reject any changed reviewed bytes, mismatched model hashes, prompts, execution settings or criterion definitions.

Validate ten canonical prompts per artifact, per-record line and content hashes, boolean decisions, awarded points, subtotals and final/truncated counts. Return the existing manual decisions for the report join; do not generate grades or alter evidence.

Test both schemas, safe appends, changed prefixes, duplicate prompts/models, mixed context, incorrect totals and source-binding failures. Parent reviews implementation independently before integration.

## Readable scalar response archive

Expose the already validated raw response records and source-prefix identity from the loader.
Generate per-model Markdown transcripts from that same in-memory snapshot, paired with existing
manual decisions. Preserve prompts, answer fields, separate reasoning, completion status and
criterion-level points verbatim. Fence generated text so model-produced Markdown cannot change
the surrounding report. Never attach a grade by rereading a potentially changed source file.

Keep a scalar-only index ordered by the reviewed local rubric, explicitly limited to the reviewed
models. Link it beside the supplementary Mac archive; neither execution context replaces the
other. Test exact text preservation, source/grade identity, incomplete coverage rejection and
unchanged raw inputs. Do not rerun inference or alter CSV/report score calculations for this step.

## Final-delivery checks

- The scalar archive now includes a separately validated capture-only view for failed or
  unreviewed models: all ten canonical prompt positions, verbatim captured outputs and failure
  events, missing responses explicit, and no score or rank. The manual-review loader's
  ten-response requirement is unchanged. Independent review and integration tests cover command
  consistency, snapshot binding, path traversal, lifecycle lag and grade/capture separation.
- Derive report and CSV completion/failure labels from scalar events and captured responses.
  Do not infer a scalar failure from a Mac or vector failure, or leave terminal results labelled
  pending. The interim export now uses validated capture states, rejects grades attached to
  incomplete or failed lifecycles, and preserves all existing non-judge CSV fields.
- Preserve the original scalar STEM run, the separate 28-response scalar restart in
  `raw/stem-responses-gcp-remainder.jsonl`, and the vector remainder as distinct attempts.
  Include each in the final response inventory and evidence links; never add their counts or
  substitute one execution context for another. `gcp-stem-attempts.md` now records all three
  attempts and the older four-thread/default-cache versus newer Mac configuration difference.
- Pull raw evidence only from the remote completion step. Its generated keyword-grade report
  must not overwrite the source-bound manual assessments or become the final ranking.

## Selection boundary

The supplied Gate 2 guideline permits explicitly disclosed prompt-only adaptation; it does not
require weight training in every case. It does require meaningful adaptation and documented
base-versus-submission differences, and warns against trivial models selected primarily for
speed or memory. Do not present a high ARC-based composite alone as submission eligibility.
The control/challenger comparison is evidence for the next model-development decision, not
proof of completed provenance, originality, thermal safety or hidden-judge performance.

Source reviewed: the user-provided Gate 2 guideline attachment
`75e0d5c7-a169-40d1-9dc7-9ce7a221c6c0/pasted-text.txt`, sections 3.1, 3.4 and 3.5.
