# GCP STEM response inventory

These are separate executions of the same 100-prompt battery. Counts describe captured
responses, not correct answers. Every captured record retains its full prompt and returned text.
Do not combine interrupted attempts, substitute vector responses for scalar responses, or pool
these records with the [matched Mac assessment](stem-report.md).

| Model | Original scalar | Scalar restart | Vector remainder |
|---|---:|---:|---:|
| Muta Tutor Qwen2.5 1.5B Q4_K_M | 100 | — | — |
| LFM2.5 1.2B Thinking Q4_0 | 100 | — | — |
| MiniCPM5 1B pure Q4_0 | 100 | — | — |
| Qwen3.5 2B Q4_0 | 100 | — | — |
| Qwen3 1.7B Q4_0 | 100 | — | — |
| LFM2.5 2.6B Q4_0 | 100 | — | — |
| MiniCPM5 2B Q4_K_M | 100 | — | — |
| LFM2.5 2.6B QAD-Q4_0 | 100 | — | — |
| MiniCPM5 1B Q4_K_M | 100 | — | — |
| Qwen3.5 2B Q4_K_M | 35 | 28 | 100 |
| VibeThinker 1.5B Q4_K_M | — | — | 100 |
| Falcon-H1-Tiny-R 0.6B Q4_K_M | — | — | Failed; no response |
| OpenReasoning Nemotron 1.5B Q4_K_M | — | — | Not reached |

An em dash means no captured response in that attempt. The two partial Qwen3.5 scalar
attempts overlap and are not a 63-question sample.

## Full records

- [Original scalar: 935 responses](raw/stem-responses.jsonl) and [lifecycle events](raw/stem-events.jsonl).
- [Separate scalar restart: 28 responses](raw/stem-responses-gcp-remainder.jsonl) and [lifecycle events](raw/stem-events-gcp-remainder.jsonl).
- [Vector remainder: 200 responses](raw/stem-responses-vector-remainder.jsonl) and [lifecycle events](raw/stem-events-vector-remainder.jsonl).
- [Three original scalar semantic assessments](manual-stem/). Other original GCP STEM sets do not yet have complete semantic assessments.

Each file has unique model/prompt pairs. The retained prompts, reference answers, categories and
model hashes were checked against the canonical battery and artifact manifest. Parser-generated
`correct` fields are option-extraction diagnostics, not judgments of the whole explanation.

## Execution differences

The recorded GCP launch commands use four CPU threads, no GPU offload and a 2,048-token context.
They do not explicitly set a host prompt-cache ceiling. The later Mac STEM screen uses two CPU
threads, Metal offload and a 256 MiB host-cache ceiling. Both use raw completion, not normal chat.
The older scalar records lack an explicit hardware-context field; their saved launch commands
and server hashes identify the scalar runtime. That missing field has not been backfilled.

These runs therefore share prompts and GGUF artifacts, not an identical execution configuration.
The separate Gate 1 replay uses chat templates and a different output budget; its grades belong
in the [GCP judges comparison](gcp-judges-responses.md), not this capture inventory.
