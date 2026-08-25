# Desktop media, model controls, and PDF composer hotfix

## Scope

Repair four regressions reported in the signed desktop releases without changing the existing model packs or the offline-first architecture:

1. allow the laptop operator to select any verified, compatible GGUF discovered in the model pack;
2. keep microphone capture producing PCM frames in WebKit/Tauri as well as Chromium;
3. render offline visualizations immediately instead of depending on an intersection callback;
4. move the PDF upload entry point from Settings to the chat composer file control.

## Confirmed causes

- The packaged gateway never sets `MUTA_ALLOW_MODEL_SWITCH=1`, so `/v1/models` intentionally marks every alternative model as non-selectable.
- The first audio fix connected the AudioWorklet through a zero-gain node. Packaged-app logs then proved that WebKit still pruned the graph: the voice WebSocket connected, but Moonshine received an empty `{1, 0}` input. WebKit needs a directly connected, silent capture node that remains part of the destination graph.
- Assigning the visualization iframe `src` synchronously fixed one lifecycle bug but not the blank Mac canvas. A Safari A/B test proved that `sandbox="allow-scripts"` gives the local Three.js frame an opaque origin and leaves WebGL blank, while the same trusted local frame renders with `sandbox="allow-scripts allow-same-origin"`.
- The hidden PDF file input is connected only to the Settings upload button even though the composer is the primary file workflow.

## Implementation

- Set the packaged model-switch flag before importing the gateway and cover it in the desktop entrypoint tests.
- On WebKit, capture PCM through a directly connected `ScriptProcessorNode` whose untouched output is silent. On other engines, use an explicitly configured AudioWorklet input/output node connected directly to the destination. Disconnect the full graph on stop.
- Assign visualization iframe sources synchronously and use visibility observation only to pause animation work, never to unload the source. Give the trusted, bundled renderer same-origin access while retaining the frame's strict no-network CSP, declarative JSON validation, and prohibitions on dynamic code and HTML injection.
- Ignore empty VAD segments before invoking the native Moonshine decoder so a zero-length capture cannot trigger a native shape exception.
- Add a labelled SVG PDF attachment button to the existing composer icon row, wire it to the hidden PDF input, remove the Settings upload action, and keep Settings only for managing already uploaded resources.
- Improve recorded-audio upload errors and authenticated requests while touching that path.

## Verification

- Run focused desktop entrypoint, UI asset, visualization, audio, and resource-upload tests.
- Run the complete UI JavaScript/Python suites and the relevant Python desktop/gateway suites.
- Exercise the built UI through the local browser: selectable model menu, PDF control placement, and rendered visualization. Reproduce the visualization in Safari with and without same-origin sandboxing to verify the WebKit-specific cause.
- Inspect packaged-app logs to verify that the microphone permission and voice WebSocket paths work independently of PCM production, then regression-test empty-segment handling.
- Rebuild all supported release targets through the cached `final-package` pipeline and verify checksums/manifests.

## Release safety

- Do not modify or repackage the existing model-pack contents.
- Keep all inference and visualization assets local; no CDN or network dependency is added.
- Stage only files belonging to this hotfix so unrelated worktree changes remain untouched.
