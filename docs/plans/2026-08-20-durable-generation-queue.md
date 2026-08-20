# Durable generation queue

## Failure

The browser can keep multiple server-owned replies alive, but `GenerationManager.reserve()`
rejects the next request as soon as all llama-server lanes are occupied. The lower session layer
has a queue concept, yet the request never reaches it. The student therefore sees “all local
inference slots are busy” and must manually resend a question that the server could safely hold.

## Changes

1. Give the process-owned generation registry a bounded FIFO queue in addition to its fixed
   active-slot cap. Queued jobs consume no inference lane and are promoted automatically when a
   running job completes or is stopped.
2. Keep queued jobs replayable and cancellable like running jobs. Publish queue-position and
   start events over the existing SSE stream, and include queued jobs in refresh recovery.
3. Prepare/persist the conversation and user turn before returning `202`, so a new queued chat has
   a stable URL and history immediately. Continue to enforce ownership, duplicate-request,
   same-conversation, per-user parallel, and bounded-queue guards atomically.
4. Render a durable assistant status explaining that other responses are running and the answer
   will start automatically. Distinguish queued chats in the sidebar and replace the status as
   soon as real generation begins.
5. Add manager, API, UI, cancellation, FIFO, recovery, and saturation regressions; then run the
   full suite and a fresh adversarial review before the individual commit is pushed and synced to
   GCP.
6. Treat refresh recovery as a retried operation rather than a one-shot convenience. Mark every
   start (including an existing conversation) by `client_request_id`, adopt a server job when a
   missed recovery causes a same-conversation conflict, and retain typed follow-ups in bounded
   session storage so “continue” is sent automatically after reload instead of being lost.

## Safety

The queue is bounded independently of active inference slots. It stores only request/generator
state already needed for durability; it never increases llama-server parallelism or the model/KV
memory budget. A full queue still fails explicitly instead of growing process memory without
limit. Promotion is conditional on binding the corresponding physical SessionManager lane, and a
generation lease is freed outright at terminal state; the registry and slot mirror therefore
cannot disagree about how many replies are actually decoding.
