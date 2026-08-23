# Visualization invocation reliability

## Problem

The explicit learner request “explain vector addition with a diagram example” was recognized as
visual, but the renderer selector sent it to the generic D3 line-chart grammar. The 0.8B model
then exhausted the constrained completion budget and the gateway silently degraded to prose. The
prose itself claimed that Muta could not provide visuals. A follow-up such as “animate it” also
selected a generic one-element animation because visualization selection saw only the latest turn,
not the subject established by the preceding learner message.

Learners must not need a hidden command. Natural requests containing words such as “diagram”,
“plot”, “interactive”, or “animation” are the invocation.

## Implementation

1. Route visual vector requests to Three.js instead of the default Cartesian plot adapter.
2. Recognize vector addition as a canonical semantic visual:
   - a diagram uses three labelled head-to-tail vectors in a rotatable Three.js scene;
   - an animation uses labelled SVG arrows driven by the requested GSAP, Anime.js, or Motion
     adapter, with the second vector moving head-to-tail before the resultant appears;
   - use A = (2, 1), B = (1, 2) as the teaching example when the learner supplies no operands;
     when two 2D/3D tuples are supplied, compute and display their exact sum deterministically.
3. Resolve anaphoric visual follow-ups (“animate it”, “rotate that”, “make this interactive”) with
   the most recent preceding learner turn in the same conversation. Keep complete standalone
   requests unchanged.
4. Strengthen the prose-only turn instruction: explain the requested subject accurately and never
   claim that Muta cannot draw or display the visual. The trusted renderer still owns all JSON.
5. Keep arbitrary model-authored HTML/JavaScript forbidden. Deterministic specs use the existing
   declarative schema, browser validator, opaque iframe sandbox, offline libraries, and CSP.

## Verification

- Unit-test natural-language intent, vector renderer selection, exact vector arithmetic, default
  example geometry, anaphoric history resolution, and the no-refusal prose instruction.
- Validate deterministic Three.js and all three animation-library specs with the browser parser.
- Run the focused Python/Node suites and the full repository suite.
- Chat with the shipped Qwen3.5 0.8B model through the public browser flow. Confirm that the exact
  reported prompt renders the Three.js diagram without a special command, then send “animate it”
  and confirm a replayable animation is persisted and survives conversation reload.

## Local verification record

- Full Python suite completed with no failures; environment integrations skipped only where their
  existing markers declared them unavailable. All 36 browser-client tests passed.
- The exact Python-generated Three.js, GSAP, Anime.js, and Motion specs passed the browser's strict
  validator. Direct canvas inspection showed the three labelled vectors in the rotatable scene.
- Direct Anime.js inspection found and fixed an adapter defect where untracked/static SVG elements
  remained at (0, 0). After the fix, A, B, the resultant, and all labels had their declared base
  transforms; Replay moved B from the origin to A's head before settling at the final position.
