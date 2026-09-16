# Gate judge hybrid GGUF chat template

## Goal

Create one Qwen3.5-compatible Jinja chat template for the submitted GGUF that:

- treats each new judge question as independent by default;
- includes only the immediately preceding user/assistant exchange when the latest question explicitly refers back to it;
- never serializes older conversation history;
- preserves or injects a short system instruction focused on factual and arithmetic reliability;
- forces non-thinking output even when a caller requests thinking; and
- remains parseable by llama.cpp's generic Jinja/autoparser path.

## Implementation

1. Add `muta-iq/opt/templates/qwen35_judge_hybrid.jinja`.
2. Reuse Qwen3.5's ChatML control tokens and content rendering conventions.
3. Locate the latest and previous real user turns without semantic model calls.
4. Gate the previous exchange with conservative explicit-reference heuristics. Do not trigger on bare words such as `previous`, `that`, or `it`, which commonly appear in standalone STEM questions.
5. Strip any legacy `<think>...</think>` prefix from a retained assistant answer.
6. Append an unconditional empty think block at the generation boundary and never inspect `enable_thinking`.

## Verification

- Render a five-turn sequence whose latest prompt is independent; assert only that prompt appears.
- Render explicit follow-ups such as `Check your previous calculation` and `Why is that?`; assert exactly one preceding exchange appears.
- Render a third-turn follow-up; assert the oldest exchange is absent.
- Render standalone STEM prompts containing words like `previous term` and `that`; assert history stays absent.
- Verify caller-supplied and absent system messages.
- Verify assistant-ended probe input and empty input render without a Jinja failure.
- Start stock llama.cpp with the template and inspect `/apply-template` output and template capabilities.

## Known boundary

This is a deterministic text router, not a semantic classifier. Implicit follow-ups can be missed and unusual standalone prompts can match a trigger. The default therefore favors isolation, because cross-topic contamination was directly observed in Gate 1 and the recovered judge questions were otherwise self-contained.

## Result

- Added `muta-iq/opt/templates/qwen35_judge_hybrid.jinja` by retaining Qwen3.5's stock tool, tool-response, multimodal-content, and reasoning-content handling around the new gate.
- Restricted pruning to ordinary text requests that end in a user turn with `add_generation_prompt=true`. Complex paths keep the stock full history.
- Verified ten render-path assertions with stock llama.cpp b10520: independent isolation, explicit follow-up retention, one-pair maximum, historical reasoning removal, false-positive guard, system merge, runtime thinking-flag immunity, consecutive turns, tools, and assistant prefill.
- Verified a real generation with `enable_thinking=true`: direct answer, `reasoning_content=null`, and no visible `<think>` trace.
- The template is a candidate artifact only. It has not yet been baked into the submission GGUF; re-run the same battery on the exact audit llama.cpp build before promotion.
