# MiniCPM5-1B pure Q4_0: Mac STEM review

Provisional assistant grading of the complete 100-prompt Mac/Metal raw-completion set. **6/100 satisfy the substantive instructions; 16/100 contain the correct core answer.**

| Category | Core answer correct | Instruction-complete pass |
|---|---:|---:|
| Mathematics MC | 7/25 | 3/25 |
| Mathematics written | 2/25 | 0/25 |
| Science MC | 4/25 | 1/25 |
| Science written | 3/25 | 2/25 |
| **All prompts** | 16/100 | 6/100 |

The six instruction-complete passes are M03, M04, M20, S05, S31 and S42. S42 now supplies the experimental variables, controls and reason for repeats. The remaining outputs frequently repeat numbers, prompts or option lists.

Correct results still fail full instructions in cases such as M11 (₦300 with the wrong option A), M36 (correct interest and total with invalid supporting calculations), S10 (correct red-cell answer but plasma/plasma-cell conflation) and S47 (correct altitude trend with a false vapour-pressure account).

## Method and evidence

The full returned text is eligible for grading. A required calculation, explanation or check must actually be present. Correct values with an explicitly wrong option letter fail strict grading; clear self-corrections are accepted. Unresolved scientific errors or unsafe added advice fail strict grading. Repetition, formatting and a token-limit finish do not alone invalidate an already complete answer.

56 responses exactly match previously reviewed GCP answers and reuse only those semantic decisions. The remaining 44 responses were read in full and adjudicated separately. All 100 Mac source lines, IDs and hashes are retained in [the decision file](minicpm-1b-pure.json). Original GCP grades are unchanged.

- Hardware: Apple M4 Pro, 24 GiB, Metal; two CPU threads and 99 requested GPU layers.
- Runtime: pinned b10175 source; binary identity recorded in the decision file.
- Raw completion, no embedded chat template or external system prompt; context 2,048, temperature 0, seed 42.
- Limits: 256 generated tokens for MC, 512 for written; prompt-cache ceiling 256 MiB.
- Completion: 63 token-limit finishes, 37 end-of-sequence finishes, 7 empty outputs.
- Source: [Mac responses](../mac-accuracy/MiniCPM5-1B-Q4_0.gguf/stem/responses.jsonl), SHA-256 `1081da57ea75c263e66d66a241f84fa93bb333a5aa589ce38a2167c83cee1690`.
- GGUF: `MiniCPM5-1B-Q4_0.gguf`, SHA-256 `1e92f54e9255240420fc8756fc90c75556aea43ca76237d36f2b77f10d3771b2`.

These figures measure this Mac raw-completion treatment, not an official competition score or the model's chat-template performance. Mac response times and memory are not used as laptop performance measurements.
