# UI stream lifecycle, parallel chats, and navigation plan

## Context

The browser currently owns the lifetime of `/v1/chat/stream` through one `fetch` and one
global `AbortController`. Switching conversations keeps that fetch alive, but refreshing the
page disconnects the response and causes the gateway to close the inference generator. The
same global `generating` flag also blocks a new turn in every other conversation. Finally,
every streaming render writes `scrollTop = scrollHeight`, so reading earlier work is
impossible until generation ends, and the selected conversation exists only in memory.

The target laptop already launches `llama-server` with a fixed `--parallel` slot budget. The
UI must not create unbounded engine capacity; it may only decide whether one learner is
allowed to occupy more than one of those already-budgeted slots.

## Changes

1. Make transcript following conditional. Track whether the scroll container is within a
   small threshold of its bottom. Streaming renders follow only while that state is true;
   manual upward scrolling pauses following until the student returns to the bottom.
2. Move generation ownership into the gateway process. A process-local generation registry
   consumes the inference iterator on a worker thread, buffers SSE events for reconnecting
   clients, persists output through the existing `ChatEngine` writer, and exposes additive
   start/list/subscribe/stop endpoints. A browser disconnect only removes a subscriber.
3. Track active generations per conversation in the browser. Reconnect to the gateway's
   active jobs after reload, keep replies running while another conversation is displayed,
   and scope Stop/queue behaviour to the conversation on screen.
4. Add a Settings panel with a persisted `Generate in multiple chats` switch. Keep the
   gateway's fixed inference-slot/RAM ceiling authoritative; the switch controls whether the
   UI may submit into another conversation while a reply is active and warns that parallel
   decoding can slow each reply.
5. Put the selected conversation id in the `/ui/` query string and restore it after auth on
   startup. Use history navigation for conversation selection and clear the parameter for a
   new chat.
6. Harden the lifecycle after adversarial review: reserve capacity atomically per generation,
   reject duplicate turns in one conversation, enforce the learner setting on the server,
   verify conversation ownership in the runtime, and serialize model switching against live
   generation admission.
7. Give a brand-new-chat start a client request id and provisional URL so a refresh between
   clicking Send and receiving the persisted conversation id can recover the exact job. Guard
   conversation loads with a navigation sequence so stale A responses cannot overwrite B.

## Compatibility and safety invariants

- Keep `POST /v1/chat/stream` as a request/response-compatible SSE endpoint, but require the
  same learner bearer identity as the durable generation API before launching background work.
- New data endpoints require the existing bearer identity and never reveal another
  student's job or conversation.
- A deliberate Stop cancels the server-owned job; navigation, tab backgrounding, connection
  loss, and refresh do not.
- Completed output remains the source of truth in the conversation store. The in-memory job
  registry is only a live replay buffer and may be lost on a gateway process restart.
- Parallel generation never changes `MUTA_RT_N_PARALLEL`, the KV-cache budget, or the memory
  ladder.
- Model switching and new-job admission share one lock; a model process is never stopped while
  a reply owns or is reserving an engine slot.

## Verification

- Unit-test job replay, disconnect survival, cancellation, ownership, and registry cleanup.
- Extend gateway tests for start/list/reconnect/stop and keep legacy stream tests green.
- Add static UI assertions for conditional following, URL persistence, settings controls,
  and per-conversation generation state; run `node --check ui/app.js`.
- Run focused UI/gateway tests, then the full test and lint suites.
- Review the final diff in a fresh adversarial context before pushing.
