# API client notes

## Live visual replies

When a text turn explicitly asks for a graph, diagram, animation, or 3D explanation, the
assistant's existing `reply`/SSE `delta` text may end with one fenced `muta-viz` JSON object. This
keeps the frozen `/v1` contract and durable conversation replay intact. The checked-in browser
client validates that declarative object, removes it from rendered prose, and passes it to an
opaque sandbox that uses pinned offline renderers.

There is no slash command or library syntax for learners to memorize. Natural requests such as
“explain vector addition with a diagram”, “plot y = x²”, “make that interactive”, and “animate it”
invoke the capability. A short follow-up referring to “it”, “this”, or “that” inherits the subject
from the preceding learner turn. Advanced callers may still name Three.js, D3, GSAP, Anime.js, or
Motion when they want a specific compatible renderer.

Non-visual clients may display the fence as ordinary Markdown or remove a validated block before
presentation. They must never execute it as JavaScript or treat model-authored fields as HTML.
Voice deliberately does not opt into this protocol, so text-to-speech never reads the JSON.
