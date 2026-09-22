# Incumbent GGUF chat-template embedding plan

## Goal

Embed `muta-iq/opt/templates/qwen35_judge_hybrid.jinja` as the
`tokenizer.chat_template` metadata value of the incumbent
`Muta-Tutor-Qwen2.5-1.5B-Q4_K_M.gguf`, while preserving the verified incumbent
and proving that model tensors are unchanged.

## Safety and compatibility gates

1. Pin the source GGUF and Jinja template by path, byte length and SHA256.
2. Inspect the source GGUF's architecture, tokenizer metadata, existing chat
   template and required control tokens.
3. Run the source GGUF with the candidate template supplied externally through
   llama.cpp. Require successful template parsing, normal server startup and
   valid single-turn and multi-turn responses.
4. Do not edit the verified incumbent in place. Rewrite metadata into one
   separately named candidate GGUF with llama.cpp's GGUF tooling.
5. Verify that the embedded template is byte-identical to the requested Jinja
   file and that every non-template metadata field remains identical.
6. Verify tensor identity independently using a tensor-only GGUF hash.
7. Run the rewritten GGUF without an external template override. Require
   llama.cpp to expose and apply the embedded template successfully.
8. Record source, template, output, tensor and runtime receipts under
   `provenance/chat-template-embedding-20260921/`.

## Output policy

The original incumbent remains untouched. The validated result is written as:

`models/candidates/Muta-Tutor-Qwen2.5-1.5B-Q4_K_M-qwen35-judge-hybrid.gguf`

Replacing the incumbent filename is a separate promotion decision because the
chat template changes prompt semantics even though it does not change weights.

## Known semantic risk

The requested template targets Qwen3.5 conventions while the incumbent uses a
Qwen2.5 tokenizer/model. ChatML control tokens are expected to be compatible,
but the template's explicit `<think>...</think>` generation prefix and optional
vision/tool branches must be treated as prompt behavior, not as proof of model
training compatibility. Runtime smoke tests establish mechanical compatibility;
quality still requires the existing matched evaluation suites before promotion.
