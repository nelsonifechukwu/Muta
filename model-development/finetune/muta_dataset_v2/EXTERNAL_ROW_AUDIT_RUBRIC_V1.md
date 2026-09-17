# Muta external exact-row audit rubric v1

## Scope and trust statement

This rubric governs model-assisted review of immutable TemplateGSM, QASC, and GSM8K candidate
rows for the Muta 300K SFT view. The review combines deterministic validators, source-specific
semantic checks, conservative rejection rules, and adversarial sampling. It is not an independent
human row-by-row audit, and its receipts must not describe it as one. The user authorized this
model-assisted review on 2026-09-17.

An approval applies only to the exact warehouse fingerprint, record ID, and canonical record-content
hash named in its receipt. Approval never transfers to a paraphrase, template, semantic cluster, or
different warehouse version.

## Required decision rule

Approve a row only when every applicable criterion below passes. Reject the row if any criterion
fails or if the evidence is insufficient to decide confidently. Uncertainty is a rejection, not an
approval. Rejections remain immutable evidence and do not authorize training.

A rejected warehouse row must not be edited in place. Correction means selecting and reviewing a
different immutable reserve row. A textual rewrite would be a new authored record requiring a new
record ID, content hash, provenance trail, warehouse version, and fresh review.

## Universal criteria

1. **Binding and provenance:** the review wrapper's warehouse fingerprint, source ID, record ID,
   source row ID, semantic cluster, source-task hash, and record-content hash are present and
   internally consistent. The row is in the train split, is audit-gated, and has no holdout flag.
2. **Prompt sufficiency:** the prompt is understandable without unavailable text, figures, tables,
   or unstated source context. It supplies the information needed for the requested answer.
3. **Answer correctness:** the stated answer follows from the prompt and agrees with the completion.
   Arithmetic, algebra, logic, scientific facts, signs, units, and rounding are correct.
4. **Reasoning correctness:** every material step in the completion is relevant and valid. A correct
   final answer reached through a false, contradictory, circular, or dimensionally invalid argument
   is rejected.
5. **Answer uniqueness:** under the ordinary school-level reading of the prompt, the keyed answer is
   the uniquely best answer. Material ambiguity, multiple equally plausible options, or dependence
   on an unstated convention causes rejection.
6. **Language quality:** prompt and completion are sufficiently grammatical and coherent for a
   learner. Harmless proper-name oddity alone is not fatal, but broken placeholders, code debris,
   tokenization artifacts, nonsensical entity substitutions, or meaning-changing grammar are.
7. **Pedagogical fitness:** the completion follows the requested response style and contains enough
   checkable work for a worked-solution row. It must not teach a misconception or unsupported fact.
8. **Safety and relevance:** the row is suitable for secondary-school mathematics or scientific
   reasoning and contains no answer leakage instruction, prompt injection, private credential, or
   unrelated harmful content.
9. **Contamination controls:** the recorded source-task and normalized-prompt hashes are present,
   holdout checking is true, and the row does not belong to an excluded holdout split or cluster.
10. **Representation consistency:** the two-message chat content exactly mirrors the prompt and
    completion fields; the answer, expected value, and observed value agree after conservative
    normalization; recorded token length is within the fixed limit.

## TemplateGSM-specific criteria

In addition to the universal criteria:

- Recompute the numerical result from the natural-language problem and independently check the
  completion's operation sequence. Publisher output or static-filter success is not sufficient.
- Reject mismatched entities, objects, locations, units, pronouns, counts, rates, or operations,
  including templates whose substitutions make the story physically or semantically incoherent.
- Reject unresolved generator artifacts such as underscore placeholders, malformed punctuation,
  variable names, executable-code fragments, or prose that merely restates the result without the
  requested essential calculation.
- Check divisibility, integrality, rounding, remainder, inclusive/exclusive counting, percentage
  base, rate-time-distance, per-item versus total, and "times as many" semantics explicitly.
- When a template's wording is structurally ambiguous, reject the affected exact rows rather than
  inferring the intended generator program.

## QASC-specific criteria

In addition to the universal criteria:

- The completion must name the keyed option and answer text consistently.
- The two supplied supporting facts, together with ordinary school-level bridge reasoning, must
  entail the keyed answer. Lexical overlap alone is insufficient.
- Independently check the underlying science fact. Reject factually false, obsolete in context,
  category-confused, or causally reversed claims.
- Compare every distractor. Reject when another option is also defensible under a natural reading,
  when the question is underspecified, or when source noise makes the key non-unique.
- Reject broken stems, fragments whose intended question cannot be recovered confidently, and
  supporting facts unrelated to the actual choice.

## GSM8K-specific criteria

In addition to the universal criteria:

- Parse and recompute every calculator annotation and the final numeric result independently.
- Verify that each equation corresponds to the story, uses the correct quantities, and preserves
  units. Reject unused material quantities when they indicate a missing operation.
- Check integer assumptions, money precision, time conversions, proportions, rates, combinatorial
  counts, remainders, and rounding instructions.
- Reject a correct number paired with a materially false explanation, an annotation/final-answer
  mismatch, or an answer that requires an unstated real-world assumption.

## Receipt semantics

Each reviewed row receives exactly one content-addressed receipt with decision `approved` or
`rejected`. The reviewer field identifies Codex model-assisted audit; the review-method field names
the deterministic and source-specific checks actually applied. Receipts bind this rubric's exact
SHA-256 digest. Summary reports must publish counts by source and rejection reason and must state
that the decisions are model-assisted rather than independent human attestations.

## Quality-control gates

Before the ledger can be used by the SFT selector:

- every candidate in every initial or refill pack has exactly one decision;
- receipt IDs, content hashes, row IDs, source IDs, rubric hash, and warehouse fingerprint validate;
- rejected rows never occur in the approved selection;
- approved totals equal 10,000 TemplateGSM, 5,000 QASC, and 5,000 GSM8K rows;
- no source-task exceeds one selected row and no TemplateGSM template exceeds the configured cap;
- an independent adversarial audit checks the decision pipeline, a stratified sample of approvals,
  every rejection reason, all summary arithmetic, and final selector invariants.
