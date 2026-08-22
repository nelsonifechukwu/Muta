# API client notes

## Live visual replies

When a text turn explicitly asks for a graph, diagram, animation, or 3D explanation, the
assistant's existing `reply`/SSE `delta` text may end with one fenced `muta-viz` JSON object. This
keeps the frozen `/v1` contract and durable conversation replay intact. The checked-in browser
client validates that declarative object, removes it from rendered prose, and passes it to an
opaque sandbox that uses pinned offline renderers.

Non-visual clients may display the fence as ordinary Markdown or remove a validated block before
presentation. They must never execute it as JavaScript or treat model-authored fields as HTML.
Voice deliberately does not opt into this protocol, so text-to-speech never reads the JSON.
