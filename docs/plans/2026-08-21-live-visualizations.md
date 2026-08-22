# Live explanation visualizations

## Goal

Let the tutor accompany an explanation with an interactive visualization generated as part of the
same chat request. The feature must remain offline, preserve the `/v1/chat` contract, survive
conversation reloads, and never execute model-authored JavaScript in the trusted chat page.

## Design

1. Detect explicit visual requests plus a conservative set of visual explanation topics. The
   primary tutor completion stays prose-only, complete, and short enough for the 0.6B model.
2. While the same physical inference admission is held, run a second local-only completion. The
   gateway selects the renderer and visualization kind first, then gives llama-server a strict,
   request-specific JSON schema. There is no concrete example for the model to copy. Deterministic
   normalization is limited to presentation data and independently verifiable cases such as
   sampling y = x² on both sides of zero; unsupported visuals degrade honestly to prose.
3. Keep the validated protocol inside the assistant reply. This makes the visualization durable in
   existing message storage and means streaming, replay, CLI clients, and the frozen chat contract
   do not need a second persistence or transport path.
4. Parse and validate the fenced object in the browser only after a complete reply exists. Invalid
   objects remain visible as code, so a malformed small-model response loses no explanation.
5. Render valid objects in a sandboxed iframe. The iframe loads pinned, locally vendored libraries
   and a trusted adapter; it receives the validated spec in the URL fragment. It has scripts but no
   same-origin authority, forms, popups, downloads, navigation, or network API. Model output is
   data, never executable code.
6. Provide focused adapters:
   - D3: line/scatter/bar plots and force diagrams.
   - Three.js: rotatable 3D scenes made from points, vectors, lines, spheres, and boxes.
   - GSAP, Anime.js, and Motion: SVG timelines built from safe primitives and bounded tracks.
7. Add accessible titles/descriptions, reduced-motion handling, responsive sizing, failure text,
   lazy loading, off-screen frame eviction, and a text fallback: the prose answer remains complete
   without the iframe.
8. Check exact library bundles, hashes, and license notices into `ui/vendor/viz`. Native development,
   the portable export, and the frontend image all use the same offline bytes.

## Verification

- Unit-test parsing, schema bounds, renderer/library compatibility, malformed fences, and the
  generated sandbox URL.
- Unit-test prose-only turn instructions, intent/negation routing, renderer selection, constrained
  completion, local-client selection, context fitting, cancellation, persistence, and SSE order.
- Run the complete Python and browser-client test suites plus lint.
- Verify every pinned visualization asset and SHA-256 from a clean source tree. Build the frontend
  image when a Docker daemon is available.
- Start the local model stack and run semantic requests through every adapter, checking requested
  values and relationships rather than schema validity alone. Then send a real browser chat,
  reload the conversation, and verify the persisted iframe renders after its prose.
- Have a fresh adversarial reviewer try to break the parser, iframe boundary, offline build, model
  protocol, replay path, and mobile/accessibility behavior; resolve every material finding.

## Verification record — 21 August 2026

- Qwen3-0.6B through the public `/v1/chat` route: 5/5 semantic checks passed for a D3
  quadratic, Three.js vector (2, 3, 1), GSAP scale 1→2, Anime.js rotation 0→180°, and Motion
  y = 280→60. The second pass used cancellable streaming and contributed its own telemetry row.
- Browser at 360×740: a normal streamed request rendered both arms of y = x², reload restored the
  frame after its prose, and a Three.js pointer drag changed the canvas and preserved the scene.
- Full Python suite: 1,121 collected tests ran with no failures (one test deselected; environment
  integrations skipped as declared). Browser-client suite: 35/35 passed. Native UI verification
  found all 27 required assets among 106 exported files; all five renderer hashes matched.
- Native FastAPI returned the exact no-network visualization CSP and `SAMEORIGIN` frame policy.
  The Docker daemon was unavailable, so the frontend container and nginx path remain a target-host
  build check rather than a claimed local result.

## Non-goals

- No arbitrary model-authored HTML or JavaScript.
- No CDN or runtime network dependency.
- No new public endpoint or hand-edited OpenAPI output.
- No replacement for the existing deterministic Matplotlib/SVG `/v1/tutor/render` endpoint.
