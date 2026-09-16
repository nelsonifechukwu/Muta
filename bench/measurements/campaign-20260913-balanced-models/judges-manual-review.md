# Manual review of completed Mac judge-prompt sets

This is provisional assistant review against the ten existing prompt-specific rubrics, not
the organisers' panel assessment. It checks arithmetic, scientific content and contradictions
rather than keyword matches. No overall numerical ranking is assigned to these two treatments.

| Model | Requests captured | Finished final responses | Token-limit truncations | Treatment |
|---|---:|---:|---:|---|
| Muta Tutor Qwen2.5 1.5B fine-tuned Q4_K_M | 10/10 | 10/10 | 0/10 | Initial Mac pilot; prior 8 GiB cache setting |
| OpenReasoning Nemotron 1.5B Q4_K_M | 10/10 | 0/10 | 10/10 | Later Mac run; explicit 256 MiB cache cap |

Every Nemotron output ends at the 1,024-token limit inside an unclosed `<think>` block.
There is correct intermediate work, but none of the ten requests reaches a distinct final answer.
Its response budget and repetition require investigation before judging its completed-answer
quality. Falcon's three captured responses are an incomplete set and are not graded here.

Both sets used the separately labelled Apple M4 Pro Metal configuration. Their answers do not
replace the GCP scalar measurements or ARC-Easy-500 results.

## Muta Tutor Qwen2.5 1.5B

Source: [raw pilot responses](raw/judges-responses-mac-pilot.jsonl).

| Prompt | Verified findings |
|---|---|
| Automated 1: proportional learning | Introduces an offset in K = αP + K₀, incorrectly identifies α as the initial rate, and claims K approaches K₀ as P grows without bound. Direct proportionality requires K = kP with k > 0, K → 0 as P → 0, and K → ∞ as P → ∞. |
| Automated 2: mastery ODE | The final expression T − (T − S₀)e⁻ᵏᵗ is correct, but its integration-constant substitution is invalid. It does not state convergence for positive k and misdescribes the Two Sigma result and scaling issue. |
| Automated 3: 4 TOPS capacity | Invents 200 tokens/s and concludes “20 parameters per second.” The information determines an operation budget of 8 × 10¹¹ operations in 200 ms, but no unique parameter count. |
| Automated 4: chalk | Gives B, ₦2,500 without a calculation. The correct answer is C, 6 × ₦500 = ₦3,000. |
| Automated 5: photosynthesis MCQ | Correct option B and correct photosynthesis mechanism. |
| Human 1: average speed | Correct segment times and total-time formula. Divides 120 by 2.25 incorrectly to obtain 48 km/h; the result is 53⅓ km/h. The second example incorrectly preserves the original total time and does not explain unequal time weights. |
| Human 2: DNA relationships | Correctly distinguishes the terms and links genes to DNA/proteins. It does not clearly explain chromosome packaging of DNA. The follow-up repeats the analogy rather than diagnosing an incorrect answer. |
| Human 3: bilingual photosynthesis | Includes the six terms and correct reaction inputs/outputs. The chlorophyll explanation contradicts absorption by describing a mirror that reflects light into the leaf. Both purported languages and both quiz sections are English. No West African everyday example is supplied. |
| Human 4: proportional learning repeat | Identical to Automated 1; the same mathematical errors apply. |
| Human 5: rice profit | Correct cost, remaining mass, reduced price, batch revenues, total revenue and profit. Rounds the percentage incorrectly to 17.2%; 12,825/74,000 × 100 = 17.331…%, hence 17.3%. The proposed check treats revenue as profit and does not verify the overall percentage. |

## OpenReasoning Nemotron 1.5B

Source: [Mac responses](mac-accuracy/nvidia_OpenReasoning-Nemotron-1.5B-Q4_K_M.gguf/judges/responses.jsonl).

All rows below review unfinished, user-visible content. None is a completed final response.

| Prompt | Verified findings before truncation |
|---|---|
| Automated 1: proportional learning | Correct proportional equation and both limits. Does not explicitly require k > 0. Repeats the draft until truncation. |
| Automated 2: mastery ODE | Uses e⁺ᵏᵗ because it drops the integration sign. Later correctly identifies attraction to T for k > 0 and recognises a sign error, but never repairs the solution or addresses tutoring scalability. |
| Automated 3: 4 TOPS capacity | Repeats dimensional confusion, including latency = 1/(tokens per character). Does not compute the operation budget or identify the missing output-length and operation-cost assumptions needed to determine model size. |
| Automated 4: chalk | Computes 6 × 500 = 3000, but calls the currency centimetres, miscopies option C as ₦3,500, and never selects the correct option. |
| Automated 5: photosynthesis MCQ | States B and the correct photosynthesis mechanism, then continues drafting until the token limit. Its unnecessary description of evaporation as releasing heat is incorrect. |
| Human 1: average speed | Correct answer, segment times and total-time formula. Does not explain the unequal time weighting; the second example is cut off and the future recognition rule is absent. |
| Human 2: DNA relationships | Gives the correct scientific relationships. The book analogy incorrectly maps proteins to the pages of the DNA book. No corrective follow-up is completed. |
| Human 3: bilingual photosynthesis | Correct English terms, inputs/outputs and chlorophyll role. The claimed Yorùbá text is mostly English with an unsupported repeated phrase. No substantive translation, local everyday example or completed bilingual understanding questions. |
| Human 4: proportional learning repeat | Identical to Automated 1; repeats correct intermediate content without reaching a final answer. |
| Human 5: rice profit | Correct cost, remaining mass, reduced price, batch revenues, total revenue and profit. Truncates while simplifying the profit fraction; no rounded percentage or independent check appears. |
