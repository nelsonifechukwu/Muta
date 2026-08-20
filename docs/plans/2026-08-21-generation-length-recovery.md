# Complete replies that reach the generation limit

## Observed failure

A live GCP conversation contains two assistant rows that end mid-sentence (`"DNA (De"` and
`"So, in a simple"`). The engine stayed healthy and returned HTTP 200. Muta currently accepts
every non-null `finish_reason` as successful completion, and its context fitter uses a
one-token-per-UTF-8-byte safety bound even for ordinary English. That bound can reduce a
requested 1,200-token reply to a much smaller allowance.

## Invariants

- A normal reply must retain its requested output allowance when the model's actual tokenizer
  says prompt plus reply fits its guaranteed per-lane context.
- Hostile or malformed text must remain context-safe if tokenizer/template inspection fails.
- `finish_reason=length` is not a completed pedagogical answer. Resume it automatically in the
  same generation job and persisted assistant row; do not require the student to type Continue.
- A real stop/EOS stays terminal, cancellation remains immediate, and retry attempts remain
  bounded by the existing recovery policy.
- Token inspection is local loopback HTTP to the already-loaded engine and must not load another
  tokenizer or model into RAM.

## Implementation

1. Add an `InferenceClient.count_prompt_tokens()` probe using llama-server's `/apply-template`
   and `/tokenize` endpoints, including the same thinking template flag as generation.
2. Let `ChatEngine._fit_request()` prefer that exact count. Fall back to the conservative
   byte-level count on any unavailable/malformed tokenizer response.
3. Preserve the engine's finish reason in `InferenceStreamError`; convert `length` into a
   retryable incomplete stream after its emitted content has been consumed.
4. Reuse the existing resume prompt, overlap removal, durable writer, cancellation signal, and
   bounded retry loop. Use a completion-specific status and no outage backoff for length resumes.
   Force a direct answer if a thinking-only attempt spends the entire allowance.
5. Make the blocking client follow the same completion contract. Require positive answer progress
   after a length retry, preserve accumulated unstructured text across a later transport failure,
   and regenerate structured output from its root instead of concatenating invalid JSON fragments.
6. Do not report buffered structured-response replay as live decode telemetry; its chunks arrive
   after generation has completed, so they cannot produce an honest TTFT or token rate.
7. Cover exact fitting, fallback safety, length-frame classification, same-row continuation,
   zero-progress retries, structured roots, cloud/local delegation, cancellation, honest partial
   persistence, telemetry suppression, and ordinary stop completion with focused tests.

## Verification and deployment

- Run focused runtime and gateway tests, then the full relevant suite, Ruff, JavaScript syntax,
  and `git diff --check`.
- Have the separate adversarial reviewer attack context safety, retry bounds, cancellation, cloud
  wrapping, and false continuation.
- Commit once, push `main`, sync that exact commit to GCP, restart the native service, and verify
  `/v1/ready` reports `ready: true`.
