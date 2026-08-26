# Deterministic mathematical surfaces

## Problem

The live-visual protocol advertises Three.js, but its declarative grammar only accepts spheres,
boxes, points, lines, and vectors. A request for `z = f(x, y)` therefore falls into the small
model's generic scene generator. The model has no surface primitive and can return a valid but
mathematically unrelated diagram. A later “animate it” turn also loses the fact that the prior
visual was a mathematical surface.

## Design

1. Recognize an explicit `z = ...` equation as a deterministic surface intent and select the
   existing offline Three.js renderer without a second model decode.
2. Normalize a bounded subset of ordinary and LaTeX notation, then parse it with a local Pratt
   parser. Accepted values are numeric literals, `x`, `y`, `t`, `e`, `pi`, the operators
   `+ - * / ^`, implicit multiplication, parentheses, and a small function allow-list. There is
   no `eval`, authored JavaScript, property access, assignment, URL, or model-generated code.
3. Serialize the checked expression as a typed AST in a `surface` object. The browser validates
   that tree independently and evaluates it through the same finite operator/function allow-list.
   Domains, grid resolution, expression size, depth, and numeric output are capped.
4. Render the surface with indexed Three.js geometry, vertex colours, a subtle wire grid, labelled
   mathematical x/y/z axes, an equation/domain overlay, a useful camera, pointer/keyboard rotation,
   theme-aware colours, and a descriptive canvas label. Mathematical `(x, y, z)` maps to Three.js
   `(x, z, y)`, so z is always vertical.
5. For an anaphoric “animate” or “animate it” follow-up, recover the preceding equation through the
   existing conversation resolver. Preserve the original AST and add a checked animation AST that
   replaces each `sin(u)` with `sin(u - t)`. One finite phase cycle starts automatically and has
   explicit Play, Pause, and Restart controls. It pauses off-screen, stops after one cycle, cleans
   up WebGL/RAF/observers on unload, and remains static under reduced motion.
6. Keep every existing visualization kind and renderer working unchanged. The frame remains
   offline and subject to its existing no-network CSP.

## Verification

- Parser tests cover LaTeX fractions/braces, implicit multiplication, precedence, safe rejection,
  bounded depth/tokens, and representative general `z = f(x, y)` functions.
- Numeric acceptance checks prove `z(0,y)=0`, `z(pi/4,0)=4`, `z(-pi/4,0)=-4`, Gaussian decay as
  `|y|` grows, and that x/y have not been swapped.
- Gateway tests prove the exact learner prompt bypasses the model and “animate it” reuses the same
  expression while adding only the typed phase animation.
- Browser tests validate and evaluate the surface AST, reject malformed/unbounded trees, preserve
  the fragment round-trip, and assert responsive/reduced-motion/control/cleanup hooks.
- Run focused Python and Node tests, the complete Python and UI test groups, Ruff, and an
  adversarial review before committing. The adversarial pass must check malformed expressions,
  exponent precedence, swapped axes, CSP/network escape, rendering budgets, reduced motion,
  narrow portrait and landscape overflow, animation state transitions, and resource cleanup.
