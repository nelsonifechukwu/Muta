# Mac accuracy pilot

- Host: Apple M4 Pro, 24 GiB unified memory, macOS.
- Runtime source: llama.cpp b10175, 60bccc3763395e01b039aa1ddeacc8cc0ea69f70.
- Source obtained from the existing local Git object with `git archive`; no runtime patch.
- Build: Release, Metal and Accelerate enabled, native CPU tuning disabled.
- Executable SHA-256: f497d6b948174173f8159b6fa46c7b4816e2ecfd306ae9c0f7f11e6a7a79af88.
- Control GGUF SHA-256: a750d00d458c6ab38925364ea1413db00648449180941e47025736d09922e1eb.
- Requests: the ten fixed judges' prompts, embedded chat template, no external system prompt;
  context 4096, two CPU threads, GPU layers 99, temperature 0, top-p 1, seed 3407,
  maximum 1024 output tokens. Settings are retained in every raw response.

This is a separate Metal accuracy screen. It does not replace GCP scalar or vector throughput,
RSS, or the ARC-Easy-500 records. Generated answers may differ across numerical backends.
The archive build has no Git metadata, so its compiled version string alone cannot identify
the source revision; use the source revision and executable hash recorded here.

The control completed all ten requests. Their wall times sum to 42.837 seconds, excluding
model startup; the median request took 5.204 seconds. No response had `finish_reason=length`
or an empty final answer. These are completion checks, not correctness grades or ADTC
performance measurements. Raw answers are in `raw/judges-responses-mac-pilot.jsonl`.

A separate load-only check with the same settings and verbosity 4 confirmed `offloaded 29/29
layers to GPU`, selected `MTL0 (Apple M4 Pro)`, and allocated the KV buffer on MTL0. That
diagnostic server was stopped without generating another prompt response.

The pilot used the server's default host prompt-cache ceiling (8192 MiB). Subsequent Mac
screens and the queued GCP judges' comparison explicitly cap it at 256 MiB. The pilot is
therefore a feasibility check, not a row to pool into that matched comparison.
