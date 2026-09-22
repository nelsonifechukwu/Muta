# Matched science pilot generation

Implement a standalone generation runner; no launch in the writing task. Root
prepares one JSONL prompt artifact containing exactly 72 `{id,messages}` objects:
64 multiple-choice prompts and eight complete tutoring message histories ending
in a user turn. Answers, rubrics, source labels and scores stay in separate
artifacts never opened by this runner. All candidates share the same hash-bound
prompt reference. The runner cannot infer the 64/8 distinction from this minimal
schema; root binds that composition in its separate construction receipt.

## Fixed protocol

HF BF16 base weights, FP32 LoRA where present, inference only, no merging, one
adapter load on the exact original parent. Controls use their exact HF parent or
the exact original winning adapter. Pilot candidates load their own sealed half
or final checkpoint onto its parent, including P3: the winning adapter is not
loaded before its continued checkpoint. No optimizer or training operation.

Batch eight with left padding, greedy decoding, one beam, 1,024 new tokens,
4,096 total-token context and seed 3407. No prompt truncation, no implicit batch
fallback, no retries or partial ranking. Every prompt must fit with the complete
generation allowance. Qwen uses its frozen ChatML generation template. DeepSeek
uses its own frozen native template with the publisher's generation prefix,
including the opening reasoning marker. The same profile applies to each native
control and its trained variants. Literal template controls in message content
are rejected; valid source messages are never rewritten.

## Admission and output

One campaign config binds common prompts, protocol, source hashes, output root,
shared Oracle lock and a map of candidate model/tokenizer/adapter references.
Every invocation identifies one candidate and the exact campaign SHA256. Frozen
trainer/tokenizer/calibration helper bytes are verified and copied into a new
source snapshot by root; existing training releases remain unchanged.

CPU preflight verifies input hashes, model/tokenizer trees, checkpoint seals and
their original resolved training configuration, and renders every prompt before
claiming a new candidate output directory. The existing Oracle UID 1000 GPU
lock is acquired before any CUDA inspection or model allocation. Reject foreign
GPU processes. Load one bare parent and at most one adapter, verify saved adapter
tensors loaded exactly, then assert BF16 base and FP32 adapter dtypes.

Append one durable result per item. Preserve full messages, rendered prompt,
unpadded and padded prompt IDs/mask, all returned generated IDs including batch
padding, the raw decoded continuation, and the continuation through first EOS.
Distinguish EOS at the 1,024th token from genuine token-cap stopping. Padding is
recorded as transport detail; no reasoning or answer text is removed. A terminal
receipt requires all 72 unique IDs in original order and a complete file seal.
Partial results on failure remain diagnostic artifacts; no ranking is performed.

## Planned tests and review

CPU tests cover schema rejection of answer/rubric fields; shared prompt identity;
full multi-turn rendering and native reasoning prefix retention; overlength
rejection; left padding and raw output preservation; EOS at cap and cap without
EOS; adapter parent/seal mismatch; duplicate output refusal before GPU access;
configuration/source tampering; and all-72 completion enforcement. An independent
reviewer must attempt to break the runner before root materializes or launches it.

## Configuration and invocation

Invoke `evaluate_pilots.py --config <absolute campaign.json>
--config-sha256 <SHA256> --candidate <ID>`. The common campaign has exactly these
keys: `schema_version` (1), `output` (absolute root), `gpu_lock` (the shared Oracle
lock), `prompts` (`path`/`sha256`), `source_sha256`, `generation`, and `candidates`.
`source_sha256` binds `evaluate_pilots.py`, `train.py`, `tokenization.py` and
`calibrate.py`. `generation` is exactly:

```json
{"batch_size":8,"max_new_tokens":1024,"context_length":4096,"do_sample":false,"seed":3407}
```

Each candidate maps an ID to `profile` (`qwen_native` or `deepseek_native`),
`chat_template_sha256`, `base` and `tokenizer` (`path`/`tree_sha256`). Optional
`adapter` adds its `path`, `tree_sha256`, and `parent_base_tree_sha256` plus
`checkpoint_seal` (`path`/`sha256` for its `COMPLETE.json`). The exact original
winning control adapter alone may omit the checkpoint seal. Pilot checkpoints
must retain their adjacent run `resolved-config.json` and the hash-bound original
training config it references. Parent paths and tokenizer identities must match
that training config, including DeepSeek's original full model/tokenizer tree.

Root places these four source files in a new immutable source snapshot and
freezes the campaign config against its final bytes. Outputs are
`<output>/<candidate>/`; any existing candidate directory rejects reuse.
`batches/` stores every complete raw returned batch before per-item validation,
including padded inputs/masks, rendered histories, and full returned sequences.
`responses.jsonl` appends durable per-item results. Both paths, the request and
hardware/environment receipts are covered by terminal `COMPLETED.json`; failures
preserve their evidence without a completion claim.

Local validation: 41 generation tests pass, including actual Qwen and DeepSeek
tokenizers under Transformers 5.5.0; targeted Ruff checks pass. Review found and
fixed three gaps: non-special native role/tool tokens are now rejected through
the complete added vocabulary, raw batch transport is retained before parsing,
and native `BatchEncoding`/list results are normalized before token validation.
Candidate source SHA256 is
`74c1037f298533a37f8637fb37fb358e58555766a054d8289892871a19f189df`.
The writer has not executed model generation or mutated either remote host.
