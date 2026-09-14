# GCP scalar judges: three additional models

Provisional assistant review of the ten fixed judges prompts per model. These are local rubric points, not official judging results or ADTC composite scores.

| Exact model | Automated /50 | Human /50 | Total /100 | Finished final answers | Reasoning-only truncations |
|---|---:|---:|---:|---:|---:|
| Qwen3-1.7B-Q4_0.gguf | 18 | 10 | 28 | 3/10 | 7/10 |
| LFM2.5-2.6B-Q4_0.gguf | 20 | 0 | 20 | 2/10 | 8/10 |
| Qwen3.5-2B-Q4_0.gguf | 10 | 0 | 10 | 1/10 | 9/10 |

Each response was read in full, including its prompt, reasoning and final text. Only the delivered final answer earns points. The 24 reasoning-only responses hit the 1,024-token cap without delivering an answer; correct calculations in their separate reasoning fields do not receive final-answer credit. None of these three batches contains a partial delivered final.

## Delivered answers

Qwen3 finishes the chalk calculation, photosynthesis and DNA prompts. Chalk earns 10/10. Photosynthesis earns 8/10: the biology is correct, but the 518-character, four-sentence answer exceeds the existing 500-character concise-response bound. No new exact-sentence-count scoring rule was introduced. The DNA response earns 10/10: it identifies the misconception, places genes within DNA, describes chromosome storage, connects gene instructions to protein products, and supplies a check question with a corrective follow-up. Its storage analogy is imprecise but does not reverse those relationships. Both judgments were independently checked by a second assistant reviewer.

LFM2.6 finishes only the chalk and photosynthesis prompts, earning 10/10 on each. Qwen3.5 finishes only chalk, earning 10/10; its photosynthesis response remains in reasoning at the token limit.

## Execution and evidence

The recorded GCP scalar configuration uses two CPU threads, no GPU offload, a 4,096-token context, a 256 MiB host-cache limit, temperature 0, seed 3407 and a 1,024-token completion allowance. Each model uses its embedded chat template without an external system prompt. These results remain separate from Mac Metal results.

The [criterion ledger](second-three.json) preserves all per-prompt decisions and weights, exact model and server hashes, prompt/answer/reasoning hashes, JSONL line hashes, lifecycle events and the captured source-prefix digest. All 30 prompt texts match the fixed suite; each artifact has ten unique expected IDs, consistent settings and matching start/stop records. The source capture contains 67 JSONL records and 303,902 bytes; its hash identifies that prefix, not the potentially larger live file.

The suite includes a repeated Two Sigma prompt. These results measure answer delivery under this template and token allowance; they do not establish unconstrained model ability. No inference was rerun and no raw evidence, CSV, throughput result or RAM measurement was altered for this review.
