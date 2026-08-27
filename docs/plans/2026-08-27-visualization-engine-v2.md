# Visualization engine V2: typed scenes and 200-case release gate

## Problem

Muta's current `muta-viz` protocol is safe and useful, but intentionally narrow. It can render
basic D3 plots/diagrams, simple Three.js scenes, one explicit `z = f(x, y)` surface, and small
allow-listed animations. Requests outside those families fall back to a concept map or a second
small-model decode, which can be structurally valid while being semantically wrong. It also lacks
one reproducible release corpus that proves intent, specification, rendering, interaction,
accessibility, lifecycle, and resource limits together.

The V2 goal is a compact general engine, not 200 prompt-specific branches. Supplied prompts are
versioned QA fixtures only. Production code resolves an intent into parameterized educational
primitives, validates a typed declarative scene, and renders it deterministically with bundled
offline libraries. No model-authored JavaScript, HTML, CSS, shader source, URL, `eval`, or
`new Function` crosses the boundary.

## Inputs and corpus

1. Preserve the 50 supplied cross-STEM prompts as raw fixture text plus normalized intent/oracle
   metadata. They cover maths, mechanics, electromagnetism, optics, thermodynamics, chemistry,
   biology, computer science, signals, controls, robotics, and neural networks.
2. Preserve all 100 supplied mathematical cases. The source really contains 100 intended cases:
   65 explicit surfaces followed by 35 implicit/unusual surfaces. Retain malformed delimiters and
   raw equations in the fixture. Record normalization decisions rather than silently repairing
   them. In particular, the two separated Gaussian terms in the "hills and valleys" case are
   normalized as a difference while the untouched source remains available in `raw_prompt`.
3. Add 50 genuinely held-out, progressively harder prompts. These must exercise distinct
   relationships and interactions rather than paraphrase supplied strings.
4. Give every case a stable ID, domain, expected intent, renderer, scene kind, controls, and
   machine-checkable semantic oracles. Production modules may not import the corpus.

## Architecture

### 1. Intent and conversational state

- Add an ordered resolver with explicit negative intent first (for example "text only" and
  "show the proof"), then visual verbs/nouns in supported localized variants. Topic names alone
  do not force a visual; the existing gateway may infer one only when an explanatory verb and a
  spatial topic occur together, avoiding surprises such as drawing on "teach projectile motion".
- Represent the result as a typed intent containing a family, renderer preference, interaction,
  and extracted parameters. Bare "animate", "animate it", "make it move", and localized
  equivalents reuse the preceding validated visualization artifact; they do not start an unrelated
  generation.
- Keep the ordinary tutor completion prose-only. A deterministic planner runs before the existing
  constrained-model fallback. The fallback may only fill fields in the same strict grammar and is
  rejected when semantic checks fail.

### 2. Versioned safe specification

- Keep V1 validation/rendering for saved conversations. Introduce V2 as a closed schema with:
  `version`, `renderer`, `kind`, title/description, coordinate system, bounded parameters,
  allow-listed layers/primitives, optional finite timeline, and declared resource budget.
- Reuse one typed expression AST for explicit, parametric, polar, vector-field, and implicit
  relationships. Extend it conservatively for multi-argument allow-listed functions and named
  variables; enforce maximum source length, tokens, nodes, depth, result magnitude, and operation
  work. Evaluation exists in Python and JavaScript with no dynamic code execution.
- Define reusable primitives for axes/grid/ticks, points/polyline/curve/area/bars, arrows/rays,
  shapes/labels/measurement, nodes/links, sampled particles, bounded scalar heatmaps, vector
  fields, contours, meshes, and 3D axes. Define
  higher-level compositions as data templates made from those primitives, not renderer code.
- Enforce hard budgets for layers, values, samples, contours, implicit grid cells/triangles,
  fixed Three.js primitive geometry, particles, animation duration/frame rate, WebGL draw calls,
  and concurrent active frames. Validators must reject a declared triangle budget below the
  deterministic geometry cost; implicit meshing consumes only its remaining declared allowance.
  Surface wireframes are line geometry, and transparent double-sided surfaces render in one pass,
  so actual GPU triangle submissions remain within the same declared cap.

### 3. Deterministic planning

- Use an ordered family selector and parameter extractors rather than exact prompt comparison.
  Families cover mathematical plots/geometry; vectors, forces, projectiles, waves, optics,
  circuits and controls; atoms/bonds/reactions/pH; cells/processes/pathways; data structures,
  algorithms and computer architecture; signals/sampling; robots; and neural flows.
- Select SVG for crisp 2D teaching diagrams and most plots, Canvas for dense dynamic systems, and
  vendored Three.js/WebGL for 3D. Animation libraries are optional transition adapters, never the
  representation itself.
- For unsupported or ambiguous relationships, return an explicit accessible fallback explaining
  what could not be drawn. Never substitute a visually plausible but semantically different chart.

### 3a. Bounded local-model semantic planner

- Preserve deterministic expression and recognised-family planning as the first, low-latency path.
  Invoke a local-model semantic planner only for a genuinely requested visual that remains an
  unseen `concept_process` composition after those routes.
- Give that planner a closed catalogue of the existing V2 primitives, coordinate systems,
  relationships, layouts, controls, renderer hints, and animation modes. Its output is JSON data
  for the existing versioned specification only. The prompt explicitly forbids source code, and
  the runtime independently rejects HTML, JavaScript, CSS, shader text, URLs, event handlers,
  prototype keys, unknown fields, and every expression outside the typed AST.
- Validate the candidate with `validate_v2_spec`, then run bounded semantic checks: concrete
  request terms and explicit entity lists must be represented across distinct labelled geometry;
  graph/process requests require directed links with validated endpoints; and every non-transport
  control must be a numeric control carrying a typed binding to one unique compatible labelled
  layer. The deterministic renderer owns the allow-listed translation, scale, and radius effects
  inside a stable, unbound coordinate frame, so auto-fitting cannot cancel a visible change. An
  inert or renderer-incompatible control is invalid. On failure, return
  a structured list of validation codes to one repair attempt. The repair sees only the original
  learner request, the allow-list catalogue, and those codes—not rejected source text. It never
  sees or emits renderer source.
- Revalidate and recheck the repaired candidate. If it still fails, return the deterministic,
  accessible concept fallback and record the planner rejection; never render partially valid data.
  Cap proposal/repair bytes, attempts, timeout, AST work, layer/control counts, and total model
  tokens under the same 8 GB CPU constraints.
- Test this boundary with previously unseen compositions and paraphrases, code-shaped proposals,
  unknown primitives, oversized candidates, dangling relationships, and a repairable missing-label
  case. Forward cancellation into both blocking constrained-model streams so Stop does not wait
  for a socket timeout. Prove that no production path dynamically executes authored source,
  injects markup, accepts a network/file/data resource token, or imports QA prompt fixtures.

### 4. Geometry and sampling

- Explicit and parametric plots sample bounded domains while splitting undefined/discontinuous
  segments instead of bridging poles. Polar and vector-field coordinates are normalized before
  rendering.
- Explicit 3D surfaces use bounded grids with holes for undefined samples. Parametric surfaces use
  bounded `(u, v)` grids. Implicit surfaces use an offline marching-tetrahedra implementation over
  a capped grid, with finite interpolation and deduplicated vertices. Preserve disconnected
  components and surface topology within the declared resolution.
- Geometry metadata records finite samples, components/segments, bounds, triangle counts, and
  oracle probes so browser QA can prove more than canvas existence.

### 5. Rendering and interaction

- Add a V2 renderer that consumes only validated data. Load D3/Three/animation assets lazily and
  remain CSP/offline safe. Use offline KaTeX only for trusted text rendering already supported by
  Muta; formulas in the scene remain text data.
- Native Play/Pause/Restart/Step and parameter controls have accessible names/states, visible
  focus, keyboard and pointer/touch behavior, and adequate touch spacing. Auto-motion is finite and
  user-controlled; reduced motion starts static.
- Use the visualization container and `ResizeObserver`, never window dimensions. Provide a textual
  summary/table for every scene and an accessible canvas description. Pause when hidden/offscreen;
  cancel RAF/listeners/observers and dispose buffers, materials, textures, and WebGL contexts on
  unmount.
- Keep a small active-frame LRU so long conversations do not retain unlimited WebGL/library realms.
- Count renderer-owned Three.js geometry in the same declared triangle cap as scene geometry.
  Surface label sprites and parametric path markers are reserved before implicit meshing, and
  every accepted implicit layer retains room for at least one triangle.

## Release-gate implementation

1. Add versioned fixture files and a loader that asserts exactly 50 + 100 + 50 unique cases and
   retains every supplied raw case.
2. Add a deterministic case compiler used only by tests/reporting to feed each raw prompt through
   production intent/planning/validation. It must fail if production code imports fixture IDs or
   strings.
3. Add per-case semantic oracles: numeric probes and domains; component/topology/segment counts;
   units/labels; arrow, force, ray, current, and flow direction; algorithm state transitions;
   parameter-control effects; and singularity/undefined handling.
4. Add a browser harness that mounts every validated spec through the real sandbox frame and
   records actual visible SVG geometry, Canvas pixel variance, or WebGL pixel/geometry evidence,
   plus console/lifecycle/accessibility/performance results. A present `<canvas>` is not evidence.
5. Generate and check in machine-readable JSON and a human Markdown table with ID, domain, intent,
   renderer, spec type, controls, invariants, browser evidence, frame time, and pass/fail. The gate
   is exactly 200/200 with no skips or waivers.

## Verification order

1. Parser/schema/property/fuzz/security tests, including prototype keys, unsafe names, oversized
   ASTs, non-finite arithmetic, singularities, mesh budgets, and corpus-string routing checks.
2. Planner/oracle tests for all 200 cases, V1 compatibility, the shipped damped-sine surface,
   heart/ethane/orbit visuals, and bare-animation artifact reuse.
3. Node renderer tests and real browser runs at desktop, 375 px and 430 px portrait, phone
   landscape, light/dark, keyboard/touch, reduced motion, hidden/offscreen, multiple visuals,
   resize, regeneration, and follow-up animation. Require no overflow, stale controls, console
   error, leaking frame, or retained WebGL context.
4. Record source/dist bundle bytes, vendored/package contribution, cold-start delta, peak browser
   memory where available, representative SVG/Canvas/WebGL frame times, and worst-case geometry
   counts. Quality may degrade only by declared resolution, never by changing the relationship.
5. Run full relevant Python and Node suites plus any repository Rust/Tauri suites that exist, Ruff,
   generated-asset verification, and `git diff --check`.
6. Hand the clean committed branch to an independent adversarial reviewer. The reviewer searches
   for fixture-string cheats, independently samples rendered cases and interactions, attacks
   schemas/CSP/lifecycle/budgets, and verifies the checked-in 200/200 report is reproducible.
7. Freeze the pre-user-holdout candidate before opening the sealed 50-case attachment. Preserve
   its first-run result immutably. Generalise only reusable primitives/planning gaps, rerun the
   original 200 plus the 50 holdout cases, add fresh metamorphic and reviewer-created probes for
   affected families, and repeat the independent review. The final gate is 200/200 + 50/50 with
   no waiver and no holdout strings or IDs in production routing.
8. A separate 15-case bearings/navigation holdout remains sealed beyond this task checkpoint. Do
   not locate, inspect, or ingest it until the user explicitly unseals it after the post-first-
   holdout checkpoint is committed and independently approved. At unseal, preserve immutable
   first-run per-case evidence before any general refinement; production routing may never contain
   its prompts, IDs, or exact answers.

## Handoff boundary

This task ends with clean local commits on `codex/visualization-engine-v2` and an immutable SHA.
It does not push, merge, package, deploy, replace artifacts, or modify the primary checkout. A
separate macOS Apple-silicon packaging task may consume only the reviewed SHA after this gate.
