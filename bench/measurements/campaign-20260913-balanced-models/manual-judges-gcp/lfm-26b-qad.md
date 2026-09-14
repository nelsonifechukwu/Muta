# LFM2.6 QAD: GCP scalar judges

Provisional assistant review of all ten fixed judges prompts for **LFM2.5-2.6B-QAD-Q4_0.gguf**. These are local rubric points, not an official judge score or ADTC composite score.

| Automated /50 | Human /50 | Total /100 | Finished finals | Partial finals | No final |
|---:|---:|---:|---:|---:|---:|
| 20 | 0 | 20 | 2/10 | 1/10 | 7/10 |

The chalk calculation and photosynthesis answers finish and receive 10/10 each. The ODE response begins a final answer but stops inside an incomplete derivative expression, before delivering any scored mathematical result. It receives 0/10 and remains classified as a partial final. Its correct solution appears only in separate reasoning.

Seven other prompts, including all five human-judge prompts, reach the 1,024-token completion limit without a final answer. The rice calculation is correct in reasoning but is not delivered to the student. Eight responses reach the limit in total; the non-substantive ODE fragment is included in that count.

All ten prompts, reasoning fields and final outputs were read. A second assistant independently checked the three nonempty final outputs and agreed with their scores and completion classifications. Each prompt retains the existing criterion weights; reasoning-only text receives no final-output credit.

## Configuration and evidence

The recorded scalar GCP run uses two CPU threads, no GPU offload, a 4,096-token context, a 256 MiB host-cache limit, temperature 0, seed 3407 and 1,024 completion tokens. The embedded chat template is used without an external system prompt. These results are separate from the Mac Metal run.

The [criterion ledger](lfm-26b-qad.json) binds each response to its source line, exact JSONL bytes, prompt, answer and reasoning hashes. It also preserves the model/server identities and start/stop events. Its source digest identifies the reviewed prefix of 80 records and 369,485 bytes; subsequent appends do not change that evidence.

This small suite includes a duplicated Two Sigma question. It measures answer delivery under this particular template and token allowance, not capability with an unrestricted output budget. No raw responses, CSV results or inference settings were changed during grading.
