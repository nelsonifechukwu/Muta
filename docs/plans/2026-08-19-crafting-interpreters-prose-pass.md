# Crafting Interpreters prose pass

## Objective

Refine every user-facing passage in `muta-iq/dashboard/` so the report reads as one sustained account of the Muta experiments: academically credible, written in a natural first-person-plural voice, and easy to follow from the original constraint to the current model choice.

## Reference study

Read the complete *Crafting Interpreters* site from its contents page, including all chapters, back matter, and appendices. Adapt only general craft techniques:

- open each section by locating the reader in the argument;
- move from a concrete result to its interpretation, then to the next question;
- use short pivot paragraphs between dense technical passages;
- let failed expectations and measured reversals carry the narrative;
- use “we” at decisions and discoveries, not as a repetitive sentence starter;
- make headings describe the argument’s movement rather than merely label a topic;
- end chapters by handing the unresolved question to the next chapter.

Do not copy distinctive wording, jokes, anecdotes, metaphors, or sentence structures from the reference. Muta remains an evidence-led technical report, not a tutorial or a voice imitation.

## Constraints

- Preserve every calculation, measurement, confidence interval, artifact identity, and evidence label.
- Preserve the separation between official-profiler results, profiler-parity estimates, website-relative sensitivity results, and development evidence.
- Do not change controls, data flow, or profiler functionality.
- Keep uncertainty explicit. Do not turn proxy evidence into a claim about tutoring quality or target-laptop performance.
- Retain the operational appendix and all accessibility equivalents.

## Work plan

1. Audit the complete HTML and JavaScript-generated copy for chapter-to-chapter continuity, paragraph rhythm, headings, labels, and first-person voice.
2. Rewrite the narrative spine first: hero, chapter leads, transitions, section conclusions, current-state conclusion, and appendix hand-off.
3. Refine cards, figure captions, experiment-ledger findings, FAQ progress notes, empty states, controls, and status messages.
4. Run the no-ai-slop rubric and revise until no listed tendency remains without a deliberate reason.
5. Run static tests, JavaScript syntax checks, and browser QA at desktop and mobile widths.
6. Give the finished report to a fresh adversarial reviewer who has not seen the drafting process; fix any factual, stylistic, or accessibility findings.
