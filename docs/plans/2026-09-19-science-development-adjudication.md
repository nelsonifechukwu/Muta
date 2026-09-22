# Development adjudication protocol (before generation)

This implements the selection plan and four-parent amendment. No response has
been generated or inspected for this development comparison. It does not alter
the question keys, teaching criteria, scoring weights, checkpoint tie-breaks or
maximum two advancing initializations.

## Complete and blinded review

Compile a review packet only after all twelve candidate invocations have 72
hash-verified, ordered responses and complete terminal inventories. Preserve
failures, caps and raw batch transport. Do not selectively regenerate responses
or compare partial candidates. Candidate identities, checkpoint step, training
loss and model paths are excluded from reviewer packets; retain their mapping
separately. Linguistic style/reasoning markers may reveal model characteristics,
so this is identity-masked agent review, not guaranteed human double-blinding.

Review all 768 multiple-choice outputs and all 96 tutoring outputs against the
pre-frozen keys/rubrics. Give reviewers the exact model-facing messages, raw
response through EOS (or full capped response), and the applicable key/rubric.
Do not substitute keyword scores. Record response hashes, reviewer identity,
explicit judgments and quoted evidence. A second independent reviewer checks
every tutoring assessment and every ambiguous/incorrect MC assessment. Also
independently review the same eight fixed MC items for all twelve candidates,
regardless of the primary judgment: the eight lowest SHA256 values of
`3407:science-mc-audit:<item-id>` over the frozen 64 MC IDs. Primary-correct MC
items outside that fixed audit remain single-reviewer judgments; report this
limit. Preserve
both ledgers and resolve disagreements with response-specific evidence, not by
changing the test or silently averaging judgments.

## Multiple choice

Correctness requires an unambiguous committed choice or scientifically matching
answer text. A merely mentioned correct option, a conditional hypothesis, a list
of possibilities or unreconciled competing final choices is not a correct
answer. Reasoning may discuss and reject alternatives without becoming
ambiguous. Judge meaning across the whole response; do not require a particular
terminal tag. Record selected option (or null), correctness, format adherence,
ambiguity and any material explanatory falsehood separately. A capped response
can earn answer correctness only if it actually makes a clear commitment before
the cap; being the right model or appearing likely to reach it earns no credit.
Internal reasoning is not deleted to conceal errors, but a clearly rejected
intermediate conjecture is not an affirmed final claim. No extra continuation
budget is granted to any model.

Report delivered-final-answer separately from semantic correctness. In the
DeepSeek native profile, a commitment inside still-unclosed reasoning may earn
semantic correctness under the rule above but is not a delivered final answer.
Preserve this distinction in the review ledger and table; do not mislabel an
unfinished thinking trace as successful answer delivery or hide its token cap.

## Tutoring

Use the eight v2 case rubrics verbatim: four science and four teaching criteria.
Assess the added response against the actual learner history; do not attribute
the learner's quoted misconception to the tutor. Affirmed listed critical errors
or additional material scientific falsehoods cap science at one of four, with
specific response evidence; tutoring remains separately scored. A relevant
check question must leave its answer to the learner to satisfy that criterion.
Zero/partial scores, refusals and token caps remain in the denominator. Use the
existing `heldout_curriculum.score_assessment` validation for evidence-backed
criteria/caps where its schema applies.

## Exact selection arithmetic and guards

For each candidate, let M be correct MC answers out of 64, S science points out
of 32, and T tutoring points out of 32. The predeclared index equals
`100 * (M + S + T) / 128`; report M, S, T and caps alongside it. Compare exact
integer numerators before display rounding. Within each pilot lineage select
the half/end checkpoint by index, then M, then S, then earlier step. Apply the
guard to that selected checkpoint; do not rescue a failed guard by searching
other settings or changing tests.

For clarity, the predeclared 'losing more than two MC items' guard counts paired
losses: items correct under its unchanged control but incorrect under the
candidate. Newly correct items do not erase those regressions for this guard.
Introducing more critical tutoring errors means more of the eight cases with
an affirmed material scientific falsehood than under its own control. Show
paired gains, losses, net change and critical-case counts explicitly. At most
two eligible different lineages advance, sorted by the same index/M/S rules;
cross-lineage exact ties retain the fixed P1,P2,P3,P4 ordering. No eligible
lineage means no refinement training, followed by the planned unchanged-control
final comparison. This diagnostic index is not an ADTC hardware score or a
statistical proof of universal superiority.
