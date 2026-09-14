# LFM2.5-1.2B Thinking Q4_0: Mac STEM review

Provisional assistant grading of the complete 100-prompt Mac/Metal raw-completion set. **41/100 satisfy the substantive instructions; 53/100 contain the correct core answer.**

| Category | Core answer correct | Instruction-complete pass |
|---|---:|---:|
| Mathematics MC | 19/25 | 18/25 |
| Mathematics written | 16/25 | 10/25 |
| Science MC | 13/25 | 10/25 |
| Science written | 5/25 | 3/25 |
| **All prompts** | 53/100 | 41/100 |

The 41 instruction-complete passes include answers present in raw planning text even when the model never reaches its separately formatted final. This treatment is deliberately different from final-only chat judging.

Some outputs differ materially from GCP: M39 now verifies 10² = 64 + 36, while M13 ends with an unresolved percentage error, M34 returns to an incorrect next term, and M33/S42 are empty. S50 gives mosquito-bite prevention but omits the parasite cause. Exact-match decisions remain traceable separately from these new judgments.

## Method and evidence

The full returned text is eligible for grading. A required calculation, explanation or check must actually be present. Correct values with an explicitly wrong option letter fail strict grading; clear self-corrections are accepted. Unresolved scientific errors or unsafe added advice fail strict grading. Repetition, formatting and a token-limit finish do not alone invalidate an already complete answer.

47 responses exactly match previously reviewed GCP answers and reuse only those semantic decisions. The remaining 53 responses were read in full and adjudicated separately. All 100 Mac source lines, IDs and hashes are retained in [the decision file](lfm-1b-thinking.json). Original GCP grades are unchanged.

- Hardware: Apple M4 Pro, 24 GiB, Metal; two CPU threads and 99 requested GPU layers.
- Runtime: pinned b10175 source; binary identity recorded in the decision file.
- Raw completion, no embedded chat template or external system prompt; context 2,048, temperature 0, seed 42.
- Limits: 256 generated tokens for MC, 512 for written; prompt-cache ceiling 256 MiB.
- Completion: 33 token-limit finishes, 67 end-of-sequence finishes, 39 empty outputs.
- Source: [Mac responses](../mac-accuracy/LFM2.5-1.2B-Thinking-Q4_0.gguf/stem/responses.jsonl), SHA-256 `57b4caa58681b392739efe0ecbb8126e96458c000c79dc1ca58b48e2545bb6fd`.
- GGUF: `LFM2.5-1.2B-Thinking-Q4_0.gguf`, SHA-256 `cbabfbf76fdb35f0fc9bc8bf175cbb25173060bc8ff14b9b7d81d3c7a84fc16f`.

These figures measure this Mac raw-completion treatment, not an official competition score or the model's chat-template performance. Mac response times and memory are not used as laptop performance measurements.
