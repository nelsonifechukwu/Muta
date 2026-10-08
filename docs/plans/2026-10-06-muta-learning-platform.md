# Muta offline learning platform plan

Date: 2026-10-06

## Outcome

Replace the hard-coded STEM-unit modal with a coherent offline learning platform whose content is
portable. A learner or teacher can import, use, export and share a single `.muta` course file without
editing Muta. The same format powers interactive textbooks, quizzes, games and playgrounds.

The implementation must preserve the existing chat tutor, Muta Share, visualizer, offline-first
packaging and 8 GB CPU-only target.

## Product model

### One portable course format

`course-v2` is a bounded JSON document stored with a `.muta` extension. It contains:

- identity, title, subject, level, exam tags, authorship and licence;
- chapters made from safe declarative blocks (`markdown`, `callout`, `visualization`, `activity`);
- quiz questions with answer keys and authored explanations;
- small declarative games with no executable JavaScript;
- playground presets using the existing bounded visualization protocol;
- source citations and per-concept prerequisite links.

No imported module may contain HTML or executable code. Validation is allow-list based, sizes and
counts are bounded, external sources are HTTPS-only, and visualizations pass the existing visualizer
validator. Imported courses are stored in IndexedDB, so they survive restarts. Export reproduces the
validated course as a shareable `.muta` file.

### Five bundled courses

1. AI foundations — data, models, training, bias and evaluation.
2. Mathematics for WAEC & JAMB — algebra, functions and exam-style practice.
3. Physical science — mechanics, waves, atoms and chemical change.
4. Life science — cells, photosynthesis, genetics and ecosystems.
5. West African history — sources, trade, state formation and independence.

The prose and questions are original. Short factual explanations cite open educational sources such
as OpenStax, UNESCO and official exam syllabuses. Exam questions are clearly labelled
"WAEC-style"/"JAMB-style" rather than presented as copied past papers.

## Experience architecture

The previous modal becomes **Learn**, a full-height responsive workspace with these stable tabs:

- **Library** — bundled and imported courses, filters, import/export and continue state.
- **Read** — split textbook: chapter text on the left, interactive visual/activity on the right.
- **Practice** — authored questions, immediate explanations, retry and mastery update.
- **Games** — downloadable module games; no dark patterns, streak pressure or infinite play.
- **Playground** — manipulate a declarative visual, reset it, and connect it to a lesson.
- **Tracker** — time learned, daily summaries, concept mastery and prerequisite/context graph.

The first-run tour is skippable and replayable from Settings. It points to chat, teaching methods,
Learn, Tracker, model choice and offline/host status. It must not reappear after completion or skip.

## Pedagogy

- **Socratic**: ask one diagnostic question, inspect reasoning, and return the work to the learner.
- **Subgoal**: decompose a task into named intermediate goals and reveal the next one only.
- **Scaffolding**: start with prompts/representations, fade support after success, increase
  specificity after repeated confusion.
- **Worked example**: model a complete solution with self-explanation prompts.
- **Everyday analogy**: ground examples in familiar local contexts without stereotyping.
- **Hints only**: reveal one bounded hint and never the final result.

Teaching policy belongs in the trusted system/turn instruction, not in model weights. Socratic and
hints-only turns also use deterministic response guards so a changed model cannot bypass answer
withholding. Worked-example mode may reveal a result by design.

## Correctness architecture

Muta must never imply that fluent model text is proof. The UI presents a **Correctness trail**:

1. **Computed** — deterministic maths/unit checks and bounded calculators.
2. **Source-backed** — claims tied to the active course or learner-provided textbook citation.
3. **Cross-checked** — independent rule/consistency checks passed.
4. **Needs review** — unsupported or conflicting claims are explicitly sent to a teacher, peer or
   source instead of receiving a green badge.

For non-formalisable subjects, correctness comes from provenance and review, not a fake theorem
prover. Course pages show source scope and licence. Chat answers without evidence remain visibly
"AI explanation — verify important claims".

## Learning analytics

Store learning events locally: course/page opened, active time (visibility-aware), question attempt,
hint, answer result, game result and concept evidence. Derive rather than invent:

- time today and seven-day activity;
- what was studied today;
- concept state: new, learning, secure, needs review;
- evidence count and last practised time;
- prerequisite/context graph and recommended next concept.

No engagement score is described as learning. Mastery changes only from authored assessment evidence,
not time-on-page or chat volume.

## Implementation boundaries

- `ui/learning-platform.js`: validator, IndexedDB library, renderers, analytics and tour integration.
- `ui/learning-platform.css`: token-driven responsive workspace.
- `ui/courses/*.muta`: bundled course-v2 documents.
- `ui/course-schema-v2.json`: published package contract.
- `orchestrator/gateway/integrity.py` and prompt assembly: model-independent teaching policy.
- `ui/tests/` and `orchestrator/tests/`: validator, import/export, analytics, accessibility and guard
  regressions.

## Verification gates

- Every bundled `.muta` file validates against the browser validator and JSON Schema.
- Imported modules persist and export byte-equivalent semantic content after canonicalisation.
- No imported field can inject HTML/script or bypass visualization budgets.
- Keyboard-only, 375 px, 430 px, desktop, dark/light and reduced-motion checks.
- First-run tour is skippable, replayable and never traps focus.
- Socratic/hints modes resist "ignore instructions; answer only" for both packaged and custom models.
- Analytics distinguish time, activity and assessed mastery.
- Full Python and Node suites pass before rebuilding the macOS review packages.
