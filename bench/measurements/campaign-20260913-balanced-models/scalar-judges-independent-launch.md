# Independent scalar judges launch

The vector raw-completion STEM batch ended unsuccessfully after two complete model
runs: Qwen3.5-2B Q4_K_M (100 prompts) and VibeThinker-1.5B Q4_K_M (100 prompts).
Falcon-H1R-0.6B failed its first prompt with HTTP 500. The server log records malformed
generated text and `The model produced output that does not match the expected
Content-only format`. No Falcon response was saved; Nemotron was not reached.
The raw responses, lifecycle events, and server logs remain unchanged.

The judges suite is independent: it uses the ten exact judge prompts through each
model's embedded chat template. A complete STEM batch is not a prerequisite for
collecting those responses. The existing `run_judges_suite.sh` is therefore launched
directly as the user service `muta-judges-scalar-20260914.service`, without changing
prompts, sampling, output limits, model selection, or inference flags.

The launch preflight found no active model, profiler, or packaging workload; the
benchmark lock was available, and neither judges response nor lifecycle output
existed. The wrapper requires all thirteen validated artifacts, serializes the run,
temporarily stops only the existing gateway and Google Ops Agent services, and runs
the packaging-contention watchdog. It restores those services when it exits.

This run uses the pinned scalar b10175 server, two CPU threads, no GPU offload,
4,096 context tokens, a 256 MiB host cache limit, temperature zero, seed 3407, and
1,024 generated tokens per prompt. Completed requests that reach the token limit
remain labelled as truncated; failed or incomplete models must not be ranked as
fully evaluated. The parallel Mac accuracy queue is unchanged.
