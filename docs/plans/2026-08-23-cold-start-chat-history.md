# Cold-start chat history plan

## Problem

On the first application load, the model catalogue remains in a loading state and existing
conversation history does not appear until model startup completes. Conversation metadata and
messages are database-backed and should remain usable while inference warms independently.

## Investigation

1. Measure cold and warm response times for the page, readiness, model catalogue, conversation
   list, and selected-conversation messages.
2. Trace the browser bootstrap sequence and the gateway dependencies behind those endpoints.
3. Compare the current ordering with recent `main` changes to identify the regression.

## Intended contract

- Render the application shell immediately.
- Authenticate before private requests, but do not make chat history wait for model discovery.
- Load the conversation list and the URL-selected conversation as soon as the database is ready.
- Discover/model readiness independently and keep only inference-dependent controls unavailable
  while the engine warms.
- Report model warm-up explicitly without blocking navigation or hiding already stored content.

## Verification

- Add a deterministic bootstrap-order regression test that makes model discovery slow and proves
  conversations render first.
- Run the focused UI tests and backend tests for the touched endpoints.
- Exercise a real cold start in a browser and record request timings.
- Run the full test/lint suite, then verify the deployed GCP instance after rollout.

## Delivery safety

The worktree contains pre-existing analytics/configuration changes. Stage and commit only files
created or changed for this cold-start fix; preserve every unrelated modification.

## Result

The regression came from `cad9a0a`: model discovery was correctly moved after authenticated
identity setup, but changed to `await refreshModelCatalog()`. `GET /v1/models` calls
`ModelManager.status()`, whose lock is held by the initial `ensure()` call while `llama-server`
maps and initializes the model. The browser therefore postponed settings, resources, generation
recovery, selected-message history, and the conversation sidebar until inference was ready.

The fix keeps identity as the required barrier; then it starts model discovery, sidebar history,
settings, and resources independently. Generation recovery remains the only ordered precursor to
selected-chat attachment because it prevents duplicate in-flight assistant rows. Inference
controls stay disabled until initial routing and model discovery are safe, while the composer
continues to accept a draft. A transient selected-chat history failure keeps routing locked until
its scheduled retry succeeds (or a definitive 404 clears it), while a recovered live reply always
retains its Stop control.

A browser harness delayed `/v1/models` by four seconds: the saved conversation was visible after
750 ms while the header still said “Loading models…”, and the model label updated independently
when the delayed request finished. The permanent Node regression test also leaves model, settings,
and resource promises unresolved and proves bootstrap still completes. GCP engine logs showed
roughly 1.4–1.7 seconds to map the selected 507 MB core and 5.3 seconds for the current 1.5B core,
so decoupling removes a real, model-size-dependent delay from database-backed chat history without
pretending the engine itself is ready earlier.
