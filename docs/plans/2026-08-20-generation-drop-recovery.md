# Generation drop recovery

## Diagnosis

The student-facing “tutor dropped the connection” message conflates browser transport loss,
llama-server restarts, and context exhaustion. The GCP llama-server log contains repeated
`Context size has been exceeded` failures while the native launcher pins a 2,048-token window.
The tutor system prompt, replayed chat history, reasoning, and a 1,200-token reply can exceed
that window during an otherwise healthy stream.

## Changes

1. Raise native launchers from 2,048 to a 12,288-token total unified window after an x86 RSS
   check; retain the memory-constrained 4B Compose control at 2,048. With two unified-KV
   native lanes, fit each job to its guaranteed 6,144-token share so
   simultaneous individually-valid prompts cannot overcommit the shared window.
2. Bound replayed history by an explicit token estimate, dropping whole oldest exchanges first;
   preserve the latest question/reply boundary for “continue” and never mutate stored history.
3. Fit `max_tokens` to the hard remaining context for every streaming and non-streaming
   request, treating each UTF-8 byte as a possible byte-fallback token. When prompt material
   alone is too large, truncate only the request copy while
   preserving a safety margin so llama-server ends normally instead of failing mid-SSE.
4. Retry genuine transient transport failures inside the same durable assistant turn. Continue
   from the exact persisted prefix, update the same assistant row, and expose a temporary
   “resuming automatically” state rather than a terminal error.
5. On an opt-in cloud stream failure, resume locally. Retry only transport/time-out and selected
   retryable HTTP statuses; malformed requests and permanent 4xx responses still fail promptly.
6. Add context fitting, role-boundary, same-row persistence, transient retry, UI state, launcher,
   and API regressions. Run the full suite and fresh adversarial review before committing.

## Safety and score

The pre-change GCP process-tree RSS was 977.0 MiB at 2,048 context tokens. The same ready native
service at 12,288 measured 1,067.31 MiB (+90.31 MiB), recorded in
`bench/optimization-log.md`: 5.96 GiB remains below the 7 GiB disqualification ceiling. Retries
are bounded and hold their existing physical lane, so they cannot increase llama-server
parallelism or duplicate a stored user turn.
