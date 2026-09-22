# Original science tutoring holdout — 16-case construction

## Scope and boundaries

Create exactly 16 new, original evaluation cases, separate from the 32 authored training candidates: four subjects (physics, chemistry, biology, Earth science) by four capability groups (concept/causal, quantitative, experimental/misconception, adaptive/judgment). Fix eight development and eight final cases, with two of each split per subject. These are never training data. This is a modest diagnostic set, not a statistical estimate of broad tutoring ability.

No actual judges, STEM100 or existing practical-battery prompts will be copied or consulted during authoring. Exclude known disallowed families (falling objects, photosynthesis multiple-choice, DNA metaphors, 40/80 average-speed variants) and the 32 authored scenario topics. Root must screen the exact finished text against campaign and historical prompts before admission; distinct IDs and lexical dissimilarity do not establish family independence.

## Construction and executable interface

Write `model-development/science_tutor/heldout_curriculum.py` and `test_heldout_curriculum.py` only; do not modify training or the previous authored source. Each case contains a short learner/tutor/learner context ending in an explicit misconception or partial answer, a model-facing tutoring request, expected core science, acceptable semantic responses, critical errors, four science criteria and four tutoring criteria. Model input contains only the messages, never references, expected answers or rubric text.

Scoring is two independent 0–4 scales, not keyword matching. A qualified human or separately validated semantic judge supplies criterion judgments with response evidence and rationale. The executable scorer validates the assessment schema and evidence, sums the four criteria in each dimension, and caps science at one when a specified critical scientific error is affirmed. It does not pretend to infer correctness from strings. Numeric checks independently derive exact answers from problem givens and validate explicitly extracted value/unit pairs; unit errors fail rather than silently matching a number. Rubric judgments and numeric diagnostics remain separate records.

## Evidence and verification

Read reliable primary science references through the web tool and store dated URLs plus original factual notes, not copied passages. Use original scenarios and quantities. Store all 16 complete cases in a review packet, source-content and pipeline hashes, and counts/split integrity. Run focused tests, including numeric wrong-answer/unit tests, score boundary/error/evidence tests, deterministic serialization and prevention of answer leakage into inference input.

Data go only under `data/muta-science-tutor-20260919/sources/muta_authored_science_heldout/`; evidence under `provenance/science-tutor-20260919/sources/heldout*`. All case statuses remain pending independent review and overlap screening. Root assigns separate all-case review and explicit admission before any inference. Do not launch inference or training.
