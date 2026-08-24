# Desktop media, model controls, and PDF composer hotfix

## Scope

Repair four regressions reported in the signed desktop releases without changing the existing model packs or the offline-first architecture:

1. allow the laptop operator to select any verified, compatible GGUF discovered in the model pack;
2. keep microphone capture producing PCM frames in WebKit/Tauri as well as Chromium;
3. render offline visualizations immediately instead of depending on an intersection callback;
4. move the PDF upload entry point from Settings to the chat composer file control.

## Confirmed causes

- The packaged gateway never sets `MUTA_ALLOW_MODEL_SWITCH=1`, so `/v1/models` intentionally marks every alternative model as non-selectable.
- The AudioWorklet capture node is not connected to an output graph. WebKit may stop pulling an unconnected worklet, so no voice frames reach the local WebSocket.
- Visualization iframe `src` is assigned only after `IntersectionObserver` reports an intersection. That callback is unreliable for the sandboxed iframe inside the Tauri/WebKit chat scroller.
- The hidden PDF file input is connected only to the Settings upload button even though the composer is the primary file workflow.

## Implementation

- Set the packaged model-switch flag before importing the gateway and cover it in the desktop entrypoint tests.
- Route the capture worklet through a muted gain node to the audio destination, then disconnect the full graph on stop.
- Assign visualization iframe sources synchronously and use visibility observation only to pause animation work, never to unload the source.
- Add a labelled SVG PDF attachment button to the existing composer icon row, wire it to the hidden PDF input, remove the Settings upload action, and keep Settings only for managing already uploaded resources.
- Improve recorded-audio upload errors and authenticated requests while touching that path.

## Verification

- Run focused desktop entrypoint, UI asset, visualization, audio, and resource-upload tests.
- Run the complete UI JavaScript/Python suites and the relevant Python desktop/gateway suites.
- Exercise the built UI through the local browser: selectable model menu, PDF control placement, and rendered visualization.
- Rebuild all supported release targets through the cached `final-package` pipeline and verify checksums/manifests.

## Release safety

- Do not modify or repackage the existing model-pack contents.
- Keep all inference and visualization assets local; no CDN or network dependency is added.
- Stage only files belonging to this hotfix so unrelated worktree changes remain untouched.
