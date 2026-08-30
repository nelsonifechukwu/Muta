# Visualization context normalization

## Problem

The V2 compiler accepts explicit relationships such as `y=sin(x)` but treats common learner
shorthand such as `plot sin(x)` as a generic concept request. That sends a mathematically precise
request to the semantic/fallback path and can produce prose or a concept map instead of a curve.
The bundled renderers are present; the missing boundary is a safe conversion from contextual
learner wording to the compiler's canonical relationship grammar.

## Design

1. Keep negative intent and non-visual-context checks authoritative. Text-only requests, literary
   plots, graph theory, and other existing false-positive guards must never be canonicalized.
2. After explicit-equation extraction, inspect only bounded expression candidates attached to an
   explicit visual command. Normalize presentation tails such as labels, domains, and "as a 3D
   surface" without interpreting arbitrary prose.
3. Parse each candidate with the existing closed expression tokenizer and AST parser. Never use
   `eval`, model-authored source, URLs, imports, or a permissive symbolic parser.
4. Infer the dependent axis from the parsed variables:
   - an expression in one independent symbol (`x`, `t`, `u`, `v`, or `z`) becomes
     `y=<expression>` and keeps that symbol as the horizontal-axis label;
   - an expression in `y` becomes `x=<expression>`;
   - an expression in both `x` and `y` becomes `z=<expression>` and follows the requested
     surface/3D/contour representation;
   - an expression in neither axis becomes a constant `y=<expression>`;
   - ambiguous variables or unsupported representation combinations fail closed.
5. Canonicalize conventional function definitions such as `f(x)=sin(x)` to `y=sin(x)` under the
   same typed-parser boundary.
6. Feed the canonical relationship into the existing V2 curve/surface compiler. The renderer,
   schema validation, resource budgets, animation handling, CSP, and saved-artifact protocol stay
   unchanged.

## Verification

- Prove the exact released-app request `plot sin(x)` produces an SVG explicit curve with the
  canonical label `y=sin(x)` and numerically correct samples.
- Cover cosine, exponential, logarithmic, implicit multiplication, constant functions, quoted
  expressions, annotation tails, function-definition notation, and two-variable surfaces.
- Prove explicit equations retain priority and existing 2D/3D/parametric/polar behavior remains
  unchanged.
- Attack the boundary with arbitrary prose, unsafe source-shaped text, URLs, assignment chains,
  unsupported variables, negative intent, literary "plot", graph theory, and ambiguous
  two-variable shorthand.
- Run focused Python and Node visualization tests, the 200-case and held-out deterministic gates,
  formatting/static checks, and `git diff --check` before commit.

## Verification result

- Exact gateway request `plot sin(x)`: deterministic V2 `explicit_curve`, SVG renderer,
  `y=sin(x)`, correct origin/crest samples, and zero constrained-model calls.
- Context regression cases: 22/22 passed, including lexical function names, independent-axis
  inference, prose tails, animation reuse, unsafe input, and non-visual false positives.
- Full non-integration Python suite: exit 0 with 1,920 selected tests and no failures.
- Full UI Node suite: 148/148 passed.
- Deterministic acceptance gates: original corpus 200/200, user holdout 50/50, and bearings
  holdout 15/15, with zero waivers.
- Additional adversarial generated probes: 15 unseen scalar expressions, five unseen scalar
  fields, and six unsafe/ambiguous rejection cases all passed.
- Ruff and `git diff --check`: passed.
