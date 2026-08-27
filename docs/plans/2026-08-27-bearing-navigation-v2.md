# Bearing/navigation visualization gate

## Frozen starting point

- Approved implementation checkpoint: `b5e726ba184d49b57a4f025ada16b43881c9b2da`.
- Immutable first-run evidence commit: `f01c3ae9844f56b2820391120a60962405d9f28e`.
- The 15 exact held-out entries produced 9 generic frames, 6 non-compilations, and **0/15
  mathematically and visually correct** results.
- Source SHA-256: `9abcdc5e7c7a252eda82f0877656db78275d3bd0b4431ecd197328dca7fd9d24`.
- Frozen artifact SHA-256 values:
  - Python: `813198f1263c1ec73d3fbdbe7c605064e31c7a2388866ed814e7b80bca4cfb7f`
  - Browser: `fbc99a6ce5fda71bd3b553b211f9dd1b1160d725b66f425bbff7faa9e905e451`
  - Graded JSON: `1fabf5b7a487834017238eed562a3a2d5c403ed9059ba8988304d60212d71b5f`
  - Human report: `95fb8611694fea679662aa8f1ab99e1043cfa0e4934b903cc36f96626b0b1120`

These files are immutable. Final evidence is written to separate paths and must continue to verify
all four hashes.

## General architecture

1. Add one deterministic bearing/navigation planner module, not 15 routes. It parses natural
   navigation statements into bounded typed records: named points, east/north coordinates,
   directed legs `(distance, clockwise bearing from north)`, reverse-bearing queries, shared-origin
   observations, two-ray intersections, and constant-velocity interception.
2. Solve every scenario in one east/north coordinate convention:
   `east = r sin θ`, `north = r cos θ`, and `bearing = atan2(east, north) mod 360`. Use the same
   solver results for numeric annotations, accessible fallback, and geometry so the views cannot
   disagree. Format displayed bearings as three digits.
3. Cover reusable scenario shapes rather than wording:
   - single directed leg/cardinal direction;
   - reverse bearing;
   - coordinate-to-bearing;
   - one or more route legs and resultant;
   - distance between two rays from a common origin;
   - bearing from one computed endpoint to another;
   - two-station ray intersection;
   - earliest positive constant-velocity interception.
4. Keep the existing strict V2 boundary. The backend emits only validated JSON primitives. Add at
   most one compact typed SVG primitive for a clockwise bearing arc if existing arrows/text/circles
   cannot express it faithfully. It carries numeric geometry and inert label text only—no source,
   path string, markup, URL, style, callback, or executable expression.
5. Render a responsive SVG schematic in screen coordinates with a consistent north-up frame,
   clockwise arcs, point labels, arrowheads, distances, units, calculations, and separate styling
   for north references, route legs, resultants, and construction rays. Text fallback describes
   the same values. Use container sizing/ResizeObserver, theme tokens, visible focus where controls
   exist, and no automatic motion. The ui-ux-pro-max checks require named controls, 44 px touch
   targets, visible focus, no overflow, and independent light/dark/reduced-motion tests.

## Parser and solver constraints

- Accept three-figure/ordinary degree notation, cardinal/intercardinal directions, kilometres and
  hours, lists and prose route legs, positive/negative east/north offsets, and named point roles.
- Normalize only syntax; never import QA fixtures or compare whole prompt strings. Production must
  contain no holdout path, ID, case number, or exact expected answer table.
- Reverse bearing is `(θ + 180) mod 360`; coordinate bearing uses `atan2(east, north)` to preserve
  quadrants. Distances use coordinates or the law of cosines as a cross-check. Interior triangle
  angles and bearings are distinct fields and labels.
- Ray intersection rejects parallel rays and negative ray parameters. Interception solves the
  relative-motion quadratic, rejects non-finite/non-positive roots, and selects the earliest
  positive root.
- Bound prompt length, extracted points/legs, numeric magnitudes, layers, labels, and solver work.
  Ambiguous or unsatisfiable navigation requests fail safely rather than drawing a plausible lie.

## Evidence and regression plan

1. Add parser/solver unit tests for three-figure formatting, reverse bearings, all quadrants,
   components, route resultants, law-of-cosines agreement, interior angles, ray intersections,
   earliest-positive interception, malformed/ambiguous input, and unseen paraphrases.
2. Add schema/client parity tests for the new typed primitive, including unsafe/extra fields,
   non-finite numbers, oversized arcs, prototype keys, and inert source-shaped labels.
3. Add a versioned 15-case QA fixture preserving every raw entry plus computed semantic oracles.
   The production module may not import or contain it.
4. Run all 15 through production intent → validated spec → real SVG. Browser oracles must inspect
   north lines/labels, clockwise arcs, point labels, arrowhead geometry, route/intersection
   coordinates, visible units/results, accessibility text, and interaction state where present.
5. Test desktop, 375 px and 430 px portrait, phone landscape, light/dark, reduced motion, keyboard,
   touch, resize, hidden/offscreen, multiple visuals, and cleanup. Record screenshots or DOM/SVG
   evidence per case; a present SVG is not a pass.
6. Rerun the original 200/200 and first holdout 50/50 gates, matrices, LRU, performance, immutable
   hashes, offline export, full Python/Node/Rust/Tauri suites, Ruff, source-leak scan, and
   `git diff --check`.
7. Freeze a clean candidate and require a fresh adversarial reviewer to independently probe unseen
   routes/quadrants and rendered arrow/arc semantics. Iterate only on general failures until the
   exact SHA is approved.

## Handoff boundary

No push, merge, deployment, release upload, or package build occurs here. After exact-SHA review
approval, hand only that SHA to task `01a0326d-a423-7510-9adc-242a66893df9` for a macOS Apple
Silicon package. Windows and Linux packaging remain out of scope.
