# Four-parent science pilot selection amendment

This is a pre-inference roster and transport amendment to
`2026-09-19-science-tutor-selection.md`. No development-generation outputs have
been inspected. The original selection index, regression guards, checkpoint
tie-breaks, maximum two advancing initializations, and final-suite reservations
remain unchanged.

## Roster

Evaluate four unchanged initializations and both saved checkpoints (63/126) for
each of their science pilots: 12 candidates, 72 common prompts each. Controls
are C1 upstream Qwen2.5-1.5B-Instruct, C2 original recovered Muta, C3 the exact
historical warm-r16-lr5e6 adapter on its original Muta parent, and C4 untouched
DeepSeek-R1-Distill-Qwen-1.5B. P3 checkpoints already contain the continued
adapter and are loaded once on the original Muta parent; never stack C3 first.

## Native transport

The original common-tokenizer clause applies to the three Qwen/Muta lineages.
C4/P4 use the exact acquired DeepSeek native tokenizer/template, including its
generation reasoning prefix. Each control and its own pilots share the same
native profile. The user messages, eight-way batch, greedy decoding, seed 3407,
4,096 total context cap and 1,024 total new-token cap are otherwise common.
DeepSeek reasoning tokens consume this same generation allowance. Preserve all
raw continuations/tokens and caps; do not strip reasoning before preservation,
grant an extra hidden budget, or compare cross-tokenizer loss as accuracy.
These constrained deployment-oriented comparisons do not reproduce publisher
long-generation benchmarks. Native behavior differences remain visible in the
report and do not authorize post-result prompt changes.

## Development admission

Before inference, apply the independent question/key review to the deterministic
64-item MC sample: exclude ambiguous questions and consume the next acceptable
same-bucket hash-ranked row. Preserve the initially proposed set and every
rejection/replacement. Use the reviewed heldout16 v2 development cases; v2 fixes
one grading-only mineral-clock caveat and leaves all model inputs unchanged.
Freeze a minimal 72-row `{id,messages}` artifact separately from all keys and
rubrics. Reviewers receive blinded outputs and the pre-frozen per-item rubrics;
the inference runner never opens answer/rubric files.

## Execution placement

P1/P4 finished on Oracle. CSD3's still-pending P2/P3 jobs were cancelled with the
pending-only filter and independently verified never to have started. Run the
same frozen P2/P3 numerical treatment sequentially on idle Oracle under the
separately reviewed relocation release. Host placement is recorded, not treated
as evidence of bitwise equivalence. Completed old experiments are not repeated.
