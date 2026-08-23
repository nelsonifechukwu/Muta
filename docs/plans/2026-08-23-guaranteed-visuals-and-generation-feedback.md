# Guaranteed visuals and generation feedback

## Problem

Visual turns currently have two silent phases: the tutor streams prose, then a second constrained
model pass attempts to produce a declarative visualization. During either wait the browser shows
only a blinking block cursor. If the second pass times out or returns invalid JSON, the gateway
quietly keeps the prose-only response. Follow-ups such as “where is the diagram?” may also lose the
subject established by the preceding user turn, allowing the prose model to claim that diagrams
are impossible even though Muta ships offline visualization runtimes.

## Product contract

1. Natural requests remain the interface; no slash command or library name is required.
2. When Muta classifies a turn as visual, the completed turn must contain one browser-valid visual
   unless the learner explicitly requests text only or cancels the turn.
3. Known scientific teaching intents use deterministic, checked constructions instead of asking
   the small model to rediscover standard geometry:
   - sine-wave phase shift and projectile motion → D3 plots;
   - heart circulation and hydrocarbon structures → D3 schematics;
   - satellite orbit and vector addition → Three.js scenes;
   - an explicit animation request may use Anime.js, GSAP, or Motion.
4. The constrained model remains a tool-like adapter for open-ended visuals. Invalid output,
   transport failure, or timeout degrades to a safe context-labelled schematic rather than to no
   visual.
5. Streaming sends an explicit visual-generation phase before the second pass. The browser shows
   one persistent, accessible busy indicator with contextual labels (“Preparing response…”,
   “Writing response…”, “Generating diagram…”), then removes it on completion, failure, or stop.
   The old blinking cursor is not used as generation feedback.

## Safety and performance

- Model output remains data-only and passes both server and browser validation; no authored
  JavaScript, HTML, SVG path strings, URLs, or network access are accepted.
- Schematics use bounded nodes, links, coordinates, labels, and enumerated shapes/bond styles.
- Animation obeys reduced-motion preferences. The loading indicator animates opacity/transform
  only and becomes static when reduced motion is requested.
- Deterministic visuals avoid a second decode for common lessons. Open-ended model generation has
  a smaller output ceiling and always has an immediate fallback.

## Verification before review

- Unit-test intent inference, anaphoric “where is the diagram?”, deterministic semantic values,
  fallback-on-invalid/timeout, phase event ordering, persistence, and browser validation.
- Render and inspect these exact examples locally before any commit:
  1. a phase-shift diagram for a sine wave;
  2. a labelled heart/circulation diagram;
  3. ethane and at least one other hydrocarbon structure;
  4. a satellite orbiting Earth with the governing orbital relationships;
  5. projectile motion with a smooth parabolic trajectory.
- Exercise ordinary text generation and a visual turn in the browser; verify the busy label,
  live-region semantics, reduced motion, final visual, replay where applicable, and reload.
- Leave the worktree uncommitted and do not merge, push, or deploy until the user reviews it.

## Verification record — 23 August 2026

- Full Python suite: passed to 100%; environment-dependent tests skipped, no failures.
- Browser parser/runtime tests: 36/36 passed; JavaScript syntax, Ruff, and diff checks passed.
- Real Qwen3.5 0.8B chat runs passed without command syntax for heart circulation, ethane,
  satellite orbit with visible equations, 90° sine-wave phase shift, projectile motion, and an
  open-ended photosynthesis network. The open-ended run visibly traversed Preparing response,
  Writing response, and Generating diagram before mounting one valid frame.
- A plain-text inertia turn used the same accessible loading component, mounted no visual, and
  left no loading status or blinking cursor after completion.
- Exact deterministic specs rendered in the sandboxed browser frame and were inspected for heart
  flow, ethane C₂H₆, ethene C₂H₄, satellite gravity/velocity/formulas, two phase-shifted sine waves,
  and a smooth projectile parabola. Saved visual replies replayed after conversation navigation.
- A live orbit run confirmed the checked explanation replaced the small model's incorrect claim:
  larger circular-orbit radius now correctly means lower speed and longer period.
- No commit, merge, push, or deployment was performed.
