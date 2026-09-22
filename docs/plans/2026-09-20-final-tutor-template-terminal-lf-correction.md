# Final tutor terminal-LF compatibility correction

## Preserved failure

The first `final-tutor-five-v2` capture failed before its first request and was
not retried in place.  Its preserved `FAILED.json` SHA256 is
`a9bc33700a64114c547fc1ca7175e050b7814834d42713481ce53efeef1e1bc5`.

The incumbent GGUF metadata contained a 2,507-byte native chat template ending
in exactly one LF.  The hash-verified llama-server `/props` response returned
the same 2,506 bytes with only that final LF omitted.  Model path, alias, slot
count, per-slot context, template prefix and all 2,506 returned bytes matched;
full GPU offload also passed.  The original capture correctly stopped because
it required byte identity.

## Bounded correction

`server_props_receipt` now admits only either:

1. exact template bytes; or
2. the server value equal to the independently extracted GGUF template after
   removing exactly one terminal LF from the latter.

It records which comparison occurred.  Internal changes and two or more
terminal LFs remain failures.  No prompt, model, answer, generation setting or
grading rule changes.

Patched capture SHA256:
`314b49a43e515e71163b3a1f2b543e4dedc23604784cfbc724b249b8a23b28dc`.

Focused capture, review and aggregation tests: 50 passed.  Retry requires a
fresh immutable release/config, a new output directory, an idle GPU and shared
lock, and an independent GO review.  The failed directory remains evidence.
