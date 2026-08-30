# Visualization dimensionality and zoom defect plan

## Problem and invariant

The V2 compiler currently routes every non-contour relation containing `z` away from the 2D
compiler. Consequently, `z=x^3` becomes an explicit surface sampled redundantly over `y` and the
Three.js renderer displays a thin, nearly edge-on ribbon. The representation must instead follow
effective dimensionality: one independent variable produces a 2D curve; a surface requires two
independent variables. The model still supplies only typed declarative data and never executable
renderer code.

## Implementation

1. Generalize explicit-curve compilation for dependent axes `x`, `y`, or `z`. Infer the independent
   axis from the typed expression AST, reject unbound or self-referential dimensions, and preserve
   the true dependent/independent labels. Keep two-independent-variable `z=f(x,y)` relations on the
   existing Three.js surface path.
2. Sample explicit curves over a bounded adaptive domain. Prefer a useful conventional window, but
   contract it for explosive functions until enough finite points fit a defensible numeric range.
   Split discontinuities rather than drawing across them. Include the selected domain and range in
   the accessible fallback.
3. Add trusted renderer-owned view controls for Cartesian curves and 3D scenes: Zoom in, Zoom out,
   and Reset view. Support buttons, wheel, two-pointer pinch, and `+`/`-`/`0` keyboard shortcuts;
   retain arrow-key rotation in 3D. Keep controls at least 44 px, visibly focusable, responsive,
   available under reduced motion, and fully removed with renderer cleanup.
4. Make 2D axes expose numeric scale labels and recompute their visible domain while zooming. Keep
   geometry clipped to the plot viewport so fast-growing curves and labels do not overflow.
5. Extend deterministic evidence with view scale/revision so interaction tests verify an actual
   visual-state change rather than only event delivery.

## Verification

- Python regressions: `z=x^3` and `y=x^3` compile as SVG explicit curves with correct axes and
  sampled invariants; fast-growing explicit curves remain finite/readable; `z=f(x,y)` remains a
  Three.js surface.
- Node regressions: named 44 px controls; zoom button/reset, wheel, pinch, and keyboard change and
  restore view state; numeric tick labels, clip path, listener cleanup, reduced-motion visibility,
  and responsive layout.
- Real browser: render the exact report prompt in dark and light themes at desktop and 375 px;
  exercise buttons, wheel, keyboard, and touch/pinch; render a two-variable surface and verify its
  3D interaction remains intact. Capture screenshots and console/evidence output.
- Run focused Python/Node tests, then the complete relevant visualization suites. Freeze a clean
  candidate commit and ask a fresh adversarial reviewer to inspect dimensionality, safety,
  interaction cleanup, responsive behavior, and prompt-specific cheating before handoff.
