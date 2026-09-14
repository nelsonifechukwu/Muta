# STEM response adjudication

The 100-prompt battery is separate from ARC-Easy and the ten-prompt Gate 1 replay. It uses
raw completion without a chat template. Each model receives 50 mathematics and 50 science
questions, split equally between multiple-choice and written responses.

This note describes the policy applied in the manual review ledgers. It is an assistant-defined
assessment with documented refinements, not a preregistered rubric or an official ADTC grade.

## Complete pass and core correctness

A complete pass requires a correct main answer, all substantive requested explanations and
checks, and no unresolved material error. Core correctness records the central result separately
when its supporting explanation is incomplete or faulty. Neither field is the extracted-option
parser score.

For multiple choice, a correct value or concept that uniquely identifies an option can pass
without its letter. An explicitly wrong option label fails the complete-pass assessment even
when its numerical value is correct. A clear self-correction can pass; an unresolved conflicting
answer cannot.

For written questions, equivalent correct methods are accepted. A requested check must actually
verify a substantive result through inverse arithmetic, substitution or a distinct numerical
method. Repeating the same derivation or saying that it checks out is insufficient. The response
does not need to recheck every intermediate step.

Level-appropriate simplifications and weak supplementary wording are not automatically treated
as material errors. Incorrect explanations or unsafe recommendations can fail the complete-pass
assessment even if the central answer is correct. Borderline decisions and their review are
retained in the ledgers.

## Returned text and output limits

The entire raw completion is assessed, including planning and literal thinking markers. Repetition,
word-count deviations and token-limit finishes do not by themselves fail an already complete,
correct answer. Missing requested content or an unresolved wrong conclusion still fails.

This differs from the Gate 1 chat rubric, which credits delivered final text only and excludes
separate reasoning and all thinking-block content. The two grades do not measure the same output
behavior and must not be compared as interchangeable accuracy percentages.

## Clarifications from the initial draft

The initial methods note required an explicit option letter and treated repetition or unfinished
reasoning as failures. The applied review accepts uniquely identifying correct values and assesses
substantive completeness rather than those formatting conditions alone. The accepted numerical
check methods were also clarified during review. Per-response decisions and review notes retain
these judgments; raw model responses have not been edited.

## Reporting and evidence

ARC-Easy-500 supplies the accuracy proxy in the estimated performance composite. The STEM
complete-pass and core-correctness counts remain separate, with four 25-question category totals.

- [Matched Mac assessments](manual-stem-mac/) and [full returned text](prompt-responses.md).
- [Original GCP scalar assessments](manual-stem/) and [raw responses](raw/stem-responses.jsonl).
- [Separate GCP vector responses](raw/stem-responses-vector-remainder.jsonl).
- [GCP scalar Gate 1 replay](gcp-judges-responses.md), using its own final-output rubric.

Do not pool hardware contexts, combine interrupted attempts, or replace missing assessments with
zeros. Model identities, prompts and response hashes are checked before joining a grade to its
source. The reviews are provisional assistant judgments; independent reviewers examined selected
disputed answers, not a second complete copy of every model's response set.
