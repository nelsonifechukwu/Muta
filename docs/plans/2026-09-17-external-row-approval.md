# External exact-row approval and refill plan

## Objective (initial allocation)

Review the 20,000 selector-ranked audit-gated rows bound to warehouse fingerprint
`0197679d767281c26537e388b6c1f703bdfcf032e02f19b1b2d2b435bf572941`; preserve an exact approved
quota of 10,000 TemplateGSM, 5,000 QASC, and 5,000 GSM8K rows; and materialize the 300,000-row SFT
view only after all gates pass.

## Quality-first outcome amendment

The review gate is allowed to reject an allocation; it is not required to manufacture enough
approvals to preserve a pre-audit source quota. The initial review and fresh adversarial passes
found systematic defects and false approvals in all three audit-gated sources. Continuing the
refill loop would therefore optimize for quota completion rather than correctness.

The final policy is fail-closed for this SFT version:

- reject and retain evidence for all 20,000 exact external rows in the initial pack;
- issue no training authorization for TemplateGSM, QASC, or GSM8K;
- leave every immutable warehouse row unchanged;
- replace the former external allocation while preserving its margins: +15,000 mathematics and
  +5,000 integrated-science rows by subject, plus +15,000 worked-solution and +5,000 concise-answer
  rows by pedagogy;
- derive the native baseline from a balanced independence matrix so all 25 subject × pedagogy
  cells remain represented, then apply the capacity-safe joint deltas: +14,757 mathematics/worked,
  +243 mathematics/concise, +243 integrated-science/worked, and +4,757 integrated-science/concise;
- preserve the declared 300,000 total and the exact global subject and pedagogy margins; and
- archive the live selection recipe separately from the warehouse-construction recipe, with a
  hash-bound explanation of the post-warehouse allocation change.

This amendment supersedes the approval-count completion conditions below. Those conditions remain
as historical evidence of the initially proposed process, not as permission to lower the audit
standard until a quota is filled.

This is an explicitly **model-assisted and deterministic** audit requested by the user. Receipts
must say so and must not claim a human manually inspected every row. Deterministic source checks,
row-specific textual checks, sampled adversarial review, and the user's authorization are distinct
facts and remain distinct in the evidence.

## Immutability rule

Never edit a warehouse row or approve a corrected string under the original row ID/content hash.
An unsuitable row receives a rejected receipt. The ranked refill mechanism then supplies another
immutable candidate. A rewritten/corrected item would require a new source row, record ID, content
hash, warehouse version, and fresh review; it is not an in-place approval operation.

## Work sequence

1. Freeze one rubric covering correctness, unique answer, prompt/answer sufficiency, units,
   reasoning consistency, language quality, secondary-school suitability, provenance, and
   contamination constraints.
2. Audit the initial pack exhaustively by source:
   - TemplateGSM: exact arithmetic/result checks plus conservative story, entity, unit, operation,
     and solution-coherence rules; reject uncertain templated substitutions.
   - QASC: option/key integrity, supporting-fact entailment, answer uniqueness, distractor
     ambiguity, grammar, and science correctness; reject uncertainty.
   - GSM8K: recompute annotations and final arithmetic, then check story-to-equation, quantities,
     units, integrality/rounding, and semantic plausibility.
3. Emit one content-addressed approval or rejection receipt for every reviewed exact row, using an
   honest model-assisted review method and the frozen rubric hash.
4. Run the deterministic audit materializer with the cumulative ledger. It counts approvals,
   reapplies canonical-task/template caps, and emits only the exact number of refill rows needed.
5. Audit each refill with the same rubric; append decisions to the cumulative ledger. Repeat until
   the manifest reports 10K/5K/5K approvals and zero refill rows.
6. Validate the complete ledger against the schema, warehouse fingerprint, exact content hashes,
   unique targets, rubric hash, source quotas, and decision counts.
7. Run `select_sft.py` to materialize the separate 300K train-only view. Verify all output hashes,
   source/subject/pedagogy margins, canonical-task cap, TemplateGSM cap, and holdout exclusion.
8. Preserve reports, scripts, rubric, ledgers, refill manifests, rejected rows, final SFT manifest,
   and an adversarial review. Do not label the resulting decisions as independent human review.

## Initial completion conditions (superseded by the quality-first amendment)

- Every emitted audit/refill row has exactly one decision receipt.
- Approved totals equal TemplateGSM 10,000; QASC 5,000; GSM8K 5,000.
- No rejected row appears in the SFT view.
- No unreviewed or non-train row appears in the SFT view.
- The 300K selected artifact meets exact source, subject, and pedagogy margins.
- Tests, lint, hashes, and fresh adversarial review pass.
