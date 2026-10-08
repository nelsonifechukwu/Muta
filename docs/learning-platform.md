# Muta Learn: portable courses, pedagogy and evidence

## Product boundary

Muta Learn is an offline learning platform built around portable `.muta` course files. A course is
data, not executable code. It can contain chapters, concept prerequisites, declarative interactive
visualizations, authored practice with explanations, small games, playgrounds, source notes and
licensing metadata. The browser validates strict size, field and visualization budgets before an
import is stored in IndexedDB. Imported files cannot contain scripts, iframes, forms or arbitrary
HTML, and they never acquire access to the local gateway.

This replaces the original application-owned list of STEM demos. A teacher or publisher can now
author a course against `ui/course-schema-v2.json`, validate it with the same client validator,
share the resulting `.muta` file by USB, local network or messaging, and import it without rebuilding
Muta. The Export action returns the same portable course. The five included courses are normal
course files loaded through that path; they do not have a private rendering API.

## Included offline library

Muta ships five short, original introductory courses:

1. AI foundations — data, models and judgement.
2. Mathematics — functions, graphs and WAEC/JAMB-style reasoning.
3. Physical science — forces, motion and particles.
4. Life science — cells, division and inheritance.
5. West African history — evidence, trade and empires.

The prose is original. Source metadata points to open references used for authoring and review;
Muta does not bundle scraped copyrighted textbooks.

## How the learner model is built

The tracker records only observable local learning events: opening a course or chapter, time while a
course is actively open, submitted authored questions, game completion and playground use. It does
not infer intelligence, personality, socioeconomic status or demographic traits.

The knowledge graph comes from the course's declared `concepts` and `prerequisites`. A node is a
concept. A directed edge means “learn this prerequisite first.” Mastery is evidence-based: a node is
marked secure only when recent checked activities for that exact course and concept meet the local
threshold. Screen time alone never increases mastery. The daily summary is derived from the same
event log and remains on the device.

## Pedagogy

The four learner-visible teaching styles combine several established methods:

- **Guide me — Socratic guidance plus scaffolding.** Muta asks one diagnostic question, supplies the
  smallest useful support, checks the response, and gradually removes support as the learner can do
  more independently.
- **Show me how — subgoal learning and worked examples.** Muta names a short plan, solves one
  subgoal at a time, explains why each operation is valid, and hands the method back with a transfer
  prompt.
- **Everyday examples — concrete to abstract.** Muta chooses one familiar analogy, keeps its mapping
  consistent, states where it stops matching, then connects it to the formal idea.
- **Hints only — minimal scaffolding.** Muta gives one next-step hint and a question. A deterministic
  response guard prevents the final result from being exposed even when a model ignores its prompt.

The adaptation layer stores explicit preferences and observable misconception tags. If a learner
repeats the same misconception or says they are still confused, the next turn selects a different
representation rather than repeating the previous wording.

## Correctness architecture

Muta does not claim that a language model can certify every answer. It exposes four different kinds
of evidence:

1. **Computed:** bounded symbolic and numerical tools check parseable mathematics.
2. **Source-backed:** installed courses identify the sources and licences used to review their
   factual material; uploaded textbooks retain page-level citations in chat.
3. **Cross-checked:** deterministic rules detect instruction overrides, non-equivalent equation
   steps, answer leakage and agreement with checked-wrong work. These controls run outside the GGUF,
   so changing the model does not remove them.
4. **Needs review:** when no reliable check applies, Muta says so and offers the evidence trail or a
   route to a teacher or class instead of showing a verified badge.

There is no universal formal checker for history, biology or open-ended explanations. For those
subjects, traceable sources, explicit uncertainty, comparisons across evidence and human review are
the honest controls.

## Judge-ready explanation

> We do not treat a fluent model as the source of truth. For mathematics, Muta checks parseable
> working with a sandboxed symbolic engine and can prevent a final answer from leaving the server.
> For factual subjects, our portable courses expose their provenance and the app distinguishes
> source-backed claims from things it could not verify. If evidence is insufficient, Muta says
> “needs review” and routes the learner to the source, teacher or class. The controls live in the
> product harness, not inside one particular model, so a later GGUF cannot silently turn them off.

## Authoring a new `.muta` course

1. Copy one of `ui/courses/*.muta`.
2. Give the course and each concept, chapter, activity, game and playground a stable lowercase ID.
3. Declare concept prerequisites before building chapters around them.
4. Use only declarative `muta-viz` version-2 specifications. Do not add HTML or JavaScript.
5. Include authored answers, explanations, source URLs, notes and licences.
6. Validate against `ui/course-schema-v2.json` and `MutaLearning.validateCourse`.
7. Import the file from **Learn → Library → Import .muta**, complete a quiz, inspect the tracker,
   export it again, and test the exported file on a second profile.

The current format is intentionally bounded to small offline courses (maximum 2 MB per file). A
future signed catalogue can distribute these same files without changing their on-device format.
