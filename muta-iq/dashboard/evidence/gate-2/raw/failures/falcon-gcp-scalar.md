# Falcon: incomplete GCP scalar judges run

`Falcon-H1R-0.6B-Q4_K_M.gguf` returned **5 of 10** judge responses before an HTTP 500 ended its run. All five returned responses reached the 1,024-token limit and contain repetitive punctuation or fragments rather than substantive answers. This is a **failed, incomplete capture**, not a completed accuracy assessment: leave its judge score and rank unset, not zero.

## Captured and missing prompts

The complete returned text is preserved in [raw responses](../raw/judges-responses.jsonl), including all repetitive content. No response was replaced with an error message or a fabricated answer.

| Prompt ID | Prompt | Raw source line | Result |
|---|---|---:|---|
| automated_01 | Two Sigma proportional model | 111 | 1,024 tokens; `finish_reason=length` |
| automated_02 | Mastery differential equation | 112 | 1,024 tokens; `finish_reason=length` |
| automated_03 | Offline LLM capacity | 113 | 1,024 tokens; `finish_reason=length` |
| automated_04 | Lagos chalk calculation | 114 | 1,024 tokens; `finish_reason=length` |
| automated_05 | Photosynthesis multiple choice | 115 | 1,024 tokens; `finish_reason=length` |

The first missing response is `human_01` (Average-speed misconception). Its identity is inferred from the runner's sequential prompt order (source path: `../../../run_judges_prompt_suite.py`; not included in the published bundle): five successful calls were appended before the sixth raised an exception. The failure event itself does not name the prompt. `human_02`–`human_05` were not reached after that exception. The malformed sixth generated output is retained in the server log, but is not a successfully returned JSONL response.

## Logged failure

The server log (source path: `../judges-server-logs/Falcon-H1R-0.6B-Q4_K_M.log`; not included in the published bundle) records a successful model load at lines 10–13. Its sixth task generated 1,024 tokens (lines 272–274), followed by `unparsed peg-native output` at lines 277–283. Line 285 gives the error:

```text
The model produced output that does not match the expected peg-native format
```

The [lifecycle events](../raw/judges-events.jsonl), lines 23–25, record start at 19:20:11 UTC and HTTP 500 failure followed by stop at 19:32:15 UTC on 14 September 2026. The runner stops this model after the exception; it does not silently count the missing prompts as incorrect answers.

The observed failure is a chat-output parsing error after generation, not a failed GGUF load. This test does not isolate whether the underlying cause is the artifact, its embedded template, runtime compatibility, or another configuration interaction. It does not establish that this quantization or the model's mathematical ability is generally defective.

## Evidence binding

All five records match the [artifact manifest](../artifacts.csv), pinned scalar server, and fixed settings: GCP N2 4-vCPU/8-GiB context, two inference threads, no GPU layers, 4,096-token context, 256-MiB cache cap, embedded chat template, no external system prompt, temperature 0, top-p 1, seed 3407, and 1,024 maximum output tokens.

- Hardware context: `x86_cloud_proxy_gcp_n2_custom_4_8192_2c4t_scalar_b10175`.
- Model SHA-256: `f41497801e96268876a681e65edc7155d15e255bd3de907b6bb29590744b6b74` (374,177,184 bytes).
- Server SHA-256: `379d824db41143559e5524bb8a84d543666fa8ccc1541bfbc0310fb698347d43`.
- Manifest SHA-256: `58df4d99502db00ff36706c6b53879dac9505f88bee4899a4c79437725a29784`.
- Response-source prefix: first 553,730 bytes / 119 complete records; SHA-256 `53ac6c55279bbed60dedc73e323defe9516ab6863cbc3fa7aeb127fbaebd37fe`.
- Event-source prefix: first 14,454 bytes / 26 complete records; SHA-256 `a07618cae7985dbf2823e63c0cb93d27f77a2aef433d336343b302aa25a60861`.
- Server log: 31,717 bytes; SHA-256 `3c0df82e4c1c6443a004d4da6bc8f78c9ecd0845bbf87065e18d16fb57169851`.

The prefix hashes bind this audit even if later models append further records. No model, raw response, runtime setting, or benchmark protocol was changed during the audit.
