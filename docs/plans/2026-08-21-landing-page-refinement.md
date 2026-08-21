# Muta landing-page refinement

## Objective

Refine the standalone `landing/` page and connect it coherently to the tutor at `/chat/` so
Muta presents as one product: an inviting public explanation followed by a focused learning
workspace, with an obvious route in both directions.

The page remains an offline-friendly, framework-free HTML/CSS/JavaScript surface. It must
look and feel related to the product UI in `ui/`: warm cream, terracotta, quiet typography,
clear controls, and no network-loaded assets.

## Product truth distilled from the repository

### Available in the current product

- Local CPU inference with an offline-first interface.
- Persistent multi-turn conversations and background/recoverable generations.
- Maths/science chat with Socratic and subgoal prompt paths.
- Image input through the vision path, voice/audio input, and optional web grounding when a
  connection exists.
- Local model selection, adjustable reasoning effort, maths verification, and rendered plots.
- Learner settings and response-language choices across African countries/languages.
- A WAEC-oriented question bank, answer checking, a learning twin, mastery data, and a
  diagnosis endpoint.

### In development / next chapters

- The full interactive AI Laboratory (simulations and learner-authored experiments).
- Wider exam-board coverage beyond the current WAEC-first slice.
- A complete teacher dashboard, teacher content injection, assignments, and progress views.
- A polished one-laptop/many-phones classroom layer, real-peer learning, discussions, and
  resilient sync.
- Full interface localization, native phone inference, broader subject depth, and the larger
  UDO education-to-career companion.

The landing page must not flatten those two lists into a single present-tense claim.

## Strategy and references

- **Brilliant:** prove the promise with an interaction, then explain it. Borrow the rhythm, not
  the playful visual language or claims.
- **Opennote:** one concise product sentence, generous whitespace, and a small number of
  coherent feature stories.
- **Marble:** curiosity as the emotional through-line; make the learning model visible through
  a connected skill map and a hands-on demonstration.
- **Anatomy Atelier:** editorial warmth around a product-like interactive surface.
- **HeyClicky:** give the product a distinct point of view and let the interface demonstrate the
  personality.
- **Khanmigo:** articulate the boundary between direct answers and guided discovery.
- **RACHEL:** explain offline classroom value in concrete, understandable terms.
- **UDO:** Muta is the learning chapter of a broader, continuous education-to-career companion.
  Do not make the UDO vision crowd out Muta's immediate product story.

## Page architecture

1. **Hero:** retain the strongest existing proposition, “A tutor that asks before it tells,”
   paired with a product-like conversation that can switch between asking, showing a photo,
   and speaking.
2. **Trust strip:** concise, defensible proof points: local, offline-first, multimodal input,
   learner-owned progress, and checked working where verification applies.
3. **Interactive lesson carousel:** three distinct demonstrations show how Muta can teach across
   Sciences, Humanities, and Business: a draggable derivative/tangent lab, a point-of-view
   reading studio, and a live break-even model. The carousel advances only while idle, pauses
   for pointer/keyboard interaction, provides manual controls, and respects reduced motion.
4. **Teaching loop:** intuition → learner explanation → checked steps. This replaces abstract
   pedagogy cards with a sequence.
5. **Available now:** concrete current capabilities, visually grounded in the current app.
6. **Next chapters:** AI Lab, exam breadth, and classroom/teacher work, explicitly labelled as
   in development.
7. **UDO bridge:** one compact section explaining how Muta fits the broader journey.
8. **Closing call to action:** open the current local interface when deployed with Muta, or view
   the source/project in the meantime.

## Cross-surface product shell

- The Muta wordmark is a home link on both surfaces and uses the same serif face, full stop,
  ink colour, and focus treatment.
- The tutor sidebar includes an explicit “About Muta” destination above utility settings so
  returning to the landing page never depends on knowing that logos are links.
- When the sidebar becomes a drawer on phones, a compact Muta home link remains visible in the
  chat header.
- Navigation uses ordinary same-origin anchors (`/` and `/chat/`) so it works offline, without
  JavaScript, and in both native FastAPI and nginx deployments.
- The chat adopts the landing page's core paper, ink, border, terracotta, and type tokens while
  retaining its denser workspace layout.

## Visual system

- Share the core brand foundations across both surfaces: paper `#faf9f5`, ink `#302d24`,
  terracotta `#ad4f31`, paper-deep `#f1ede3`, and border `#dfddd4`.
- Add a dark aubergine/ink surface only for the interactive lesson; use a restrained green for
  verified/progress states.
- Use system fonts only so the page works fully offline.
- Prefer CSS geometry, canvas, type, and real controls over decorative SVG icon grids.
- Use larger editorial type, asymmetric layouts, and fewer bordered cards than the first
  version.
- All interactive states must work with mouse, touch, and keyboard; motion must respect
  `prefers-reduced-motion`.

## Acceptance checks

- No external asset or font requests.
- No unsupported present-tense feature claims.
- One `h1`; semantic sections and navigation landmarks; visible keyboard focus.
- Mobile menu works and closes after navigation; no horizontal overflow at 320 px.
- All three interactive lessons work with keyboard and pointer input and have textual status.
- The lesson carousel pauses during interaction, resumes when idle, exposes a manual pause
  control, and never auto-advances under `prefers-reduced-motion`.
- Desktop and mobile screenshots show the complete first viewport without invisible reveal
  content.
- All internal anchors and external links resolve as intended.
- The chat wordmark and explicit sidebar destination reach `/`; the landing CTAs reach
  `/chat/`; the mobile header keeps a visible home route while the sidebar is closed.
- Existing repository tests remain green, with a small landing asset test added if useful.
- Leave the branch uncommitted and unpushed for review.
