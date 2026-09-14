# MiniCPM5-1B pure Q4_0: manual scalar STEM review

Provisional assistant grading of all 100 original GCP raw-completion responses. This is not an official competition score or a chat-template test.

| Category | Core answer correct | Instruction-complete pass |
|---|---:|---:|
| Mathematics, multiple choice | 6/25 | 3/25 |
| Mathematics, written | 1/25 | 0/25 |
| Science, multiple choice | 3/25 | 1/25 |
| Science, written | 2/25 | 1/25 |
| **All prompts** | **12/100** | **5/100** |

Core correctness records the main result separately from explanatory or verification failures. Strict passes require the requested working, explanation and checks, without unresolved substantive contradictions. A correct value and valid working can pass without an option letter; an explicitly wrong letter fails. Formatting and repetition alone do not overturn a complete correct answer.

The five strict passes are **M03, M04, M20, S05 and S31**. M20 repeats the same correct speed calculation under every option label; the numerical answer is unambiguous. S31 correctly distinguishes bacterial infections from viral colds. Its repeated “not effective against both” phrasing is ambiguous, but the surrounding explicit explanation resolves the intended distinction.

Seven further responses have correct core results but fail the complete instruction:

| Prompt | Correct core | Reason for strict failure |
|---|---|---|
| M01 | ₦3,000 | Explicitly selects A instead of C. |
| M05 | 40 m² | Conflicting A/D labels remain unresolved. |
| M21 | B, 3/10 | No calculation showing the total number of counters. |
| M39 | 10 m | No Pythagoras check; appended 45° ladder answers are false. |
| S01 | Photosynthesis | No explanatory sentence. |
| S19 | H₂O | Names formulas but does not explain the water composition. |
| S47 | Lower pressure lowers boiling temperature | Incorrect mechanism and temperature conversions; no vapour-pressure condition. |

Many failures are incomplete raw continuations rather than finished explanations: repeated option lists, number sequences, copied prompts and unrelated questions. All returned text was read. A correct value merely occurring in a list was not treated as a selected answer. The run produced 58 token-limit finishes, 42 end-of-sequence finishes and seven empty responses.

## Evidence and configuration

- Exact artifact: `MiniCPM5-1B-Q4_0.gguf`, the manifest's **pure Q4_0** conversion from MiniCPM5-1B F16; not the separate Q4_K_M artifact.
- Source: [original scalar responses](../raw/stem-responses.jsonl), lines 201–300. Source SHA-256: `5996240435fb63674cf60173756bdb2926b54654d5d752871fa8ab1daa158294`.
- Artifact SHA-256: `1e92f54e9255240420fc8756fc90c75556aea43ca76237d36f2b77f10d3771b2`.
- Saved lifecycle command: 2,048 context tokens, four CPU threads, zero GPU layers. The raw `/completion` protocol uses temperature 0, seed 42, 256-token multiple-choice and 512-token written limits, without an embedded chat template.
- Original rows omit a hardware-context/settings object. GCP scalar provenance is retained from the campaign and lifecycle evidence; the original command has no explicit prompt-cache RAM cap. Later Mac settings are not applied retrospectively.
- The historical option parser marked 6/50 MC responses correct. Those marks are not this manual review: they omit explanation requirements and include incorrect or ambiguous outputs.

[Per-prompt decisions and provenance](minicpm-1b-pure.json) contain all 100 IDs, source line numbers, answer hashes, reasons and flags. This low raw-completion result does not establish the model's performance under its intended embedded chat template.
