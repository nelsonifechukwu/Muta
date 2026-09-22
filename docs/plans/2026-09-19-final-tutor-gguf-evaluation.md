# Final tutor GGUF capture and blinded review

## Scope

Run only the eight independently reviewed `final` cases from
`muta_authored_science_heldout-v2` against the frozen five-GGUF roster.  This
stage captures responses and produces an identity-masked semantic-review
packet.  It does not grade, rank, select, train, merge, quantize or mutate any
earlier artifact.

## Separation invariant

- Inference receives `final_prompts.jsonl` only.  Its exact schema is
  `{group_id,id,messages,split}` and it contains the three-turn learner/tutor
  context but no rubric, answer, expected science or acceptable response.
- `final_cases.jsonl` and the two independent review receipts are introduced
  only by the offline packet compiler after the capture has a valid terminal
  seal.
- The reviewer sees rubrics and delivered answer text but no candidate label.
  The separately retained private mapping is not placed below `reviewer/`.
- Separate `reasoning_content` is evidence, not delivered tutoring content.  It
  remains in the capture tree and is excluded from the semantic-review packet.

## Capture protocol

`bench/science_tutor_final_capture.py` requires a SHA256-bound config with:

- a standard `bench.round2_candidate_eval` manifest containing exactly five
  GGUF candidates and their exact model/server hashes;
- the exact eight-row prompt projection;
- settings (`slots`, `context_per_slot`, `max_tokens`, `threads`,
  `gpu_layers`, `port`);
- hashes for the runner, the imported runtime helper and its four local import
  dependencies; this exact six-file set is enforced and extra code/runtime
  references are rejected;
- an explicit GPU lock below `/tmp`.

The runner acquires the lock non-blockingly, refuses a busy GPU or port, starts
one candidate at a time with `--jinja`, independently extracts
`tokenizer.chat_template` from the hash-verified GGUF metadata, and requires an
exact match to the server's `/props` template.  `/props` must also identify the
expected model path/alias, eight slots and 4,096-token per-slot context; the
startup receipt must prove full GPU offload.  The runner preserves the full
command, every exact request *before* network activity, every raw HTTP body,
parsed rows, pre/post model hashes, failure evidence and terminal inventories.
Malformed or HTTP-error `/props` bodies are retained before parsing or failure.
It uses greedy seed 3407,
`cache_prompt=false`, `enable_thinking=false`, and a 768-token cap.  Eight slots
evaluate the eight cases concurrently without loading multiple models.  The
fixed cap leaves ample space for the short tutoring turns while avoiding the
1,024-token development cap's unnecessary worst-case generation cost.

Example after the final roster/config is frozen:

```bash
PYTHONPATH=. .venv/bin/python -m bench.science_tutor_final_capture \
  --config /absolute/path/final-tutor-config.json \
  --sha256 <CONFIG_SHA256> \
  --output /absolute/path/final-tutor-capture
```

## Blinded packet protocol

Retain a separately generated 32-byte mask key.  The compiler revalidates the
complete capture tree, all raw hashes, all prompt joins, the reviewed final-case
hashes and both independent-review receipts.  It authenticates the exact local
source filename→SHA256 mapping, enforces a one-to-one set of eight request and
eight raw-response files per candidate, and rechecks the embedded-template,
server-properties and full-offload receipts.  It writes 40 deterministic HMAC
review IDs, a `reviewer/tutor.jsonl`, a separate `private-mapping.jsonl`, and a
terminal seal.  Reusing identical inputs and key yields identical packet bytes.

```bash
PYTHONPATH=. .venv/bin/python -m bench.science_tutor_final_review \
  --capture-root /absolute/path/final-tutor-capture \
  --completion-sha256 <CAPTURE_COMPLETED_SHA256> \
  --prompts-path data/muta-science-tutor-20260919/sources/muta_authored_science_heldout-v2/final_prompts.jsonl \
  --prompts-sha256 c0997ca73e9ca444ffdba21cc6f00236146ab99cb9b3c8a05aa2931f391e0435 \
  --cases-path data/muta-science-tutor-20260919/sources/muta_authored_science_heldout-v2/final_cases.jsonl \
  --cases-sha256 47301bdbbd271c7a460f27aeab46b7c9e1e86fa5557de404a02a01caea7615ee \
  --content-review-path provenance/science-tutor-20260919/reviews/heldout16-independent-review-v2.json \
  --content-review-sha256 f84934cdec29db6e88af18786b37b6b9c56a5f2a9db48ebdd16c076561cbb296 \
  --overlap-review-path provenance/science-tutor-20260919/reviews/heldout16-independent-overlap-v2.json \
  --overlap-review-sha256 4af8ad06bdb5c36643a44ba5aad9eec72744d1964550b9e959f2878eaec70874 \
  --mask-key-path /absolute/private/path/final-tutor-mask.key \
  --output /absolute/path/final-tutor-review-packet
```

No partial score or candidate identity should be disclosed until all 40 packet
rows have been independently assessed and joined through the sealed mapping.
