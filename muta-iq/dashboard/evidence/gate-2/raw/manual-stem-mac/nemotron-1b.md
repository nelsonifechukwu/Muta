# OpenReasoning Nemotron 1.5B Q4_K_M — Mac STEM review

Provisional assistant grading: **35/100 strict passes; 60/100 correct core answers**. Lead review resolved S05, S06 and S45 as strict failures. These are internal assistant assessments, not official grades. This is the raw-completion STEM battery, not ARC accuracy or the chat judges suite.

| Category | Strict pass | Core correct | Responses |
|---|---:|---:|---:|
| Math multiple choice | 18 | 20 | 25 |
| Math written | 10 | 14 | 25 |
| Science multiple choice | 6 | 21 | 25 |
| Science written | 1 | 5 | 25 |

All 100 responses were read in full. There were 84 token-limit finishes and no empty responses. Many capped outputs still contain complete correct mathematics; they receive credit even when the model never reaches a separately formatted final answer. The written-science failures frequently repeat the prompt without answering it.

Strict grading requires every substantive requested component and no unresolved material error. Core correctness is separate from explanation quality. M30 and M43 give the correct value but no distinct requested check. M35 corrects its first answer and checks proportional scaling with decimal and fractional rates; M39 and M48 explicitly substitute their results. M41 first verifies 90 but later contradicts it with 300. S01 and S13 identify the right concept but explicitly select the wrong letter.

Science failures include incorrect supporting mechanisms for evaporation, inclined planes, litmus, current units and gas conduction. S47 gives the correct altitude trend but wrongly says vapour pressure remains below atmospheric pressure at boiling. S49 replaces an immediate-vaccine-cure claim with a delayed-cure claim, which does not correct the misconception.

## Review boundaries

An earlier independent reviewer read nine selected cases. Additional review verified all 100 source bindings and totals and read 38 complete responses selected for substantive or borderline decisions; this was not a second full regrade.

- S05 fails strict: attributing Earth's Earthward attractive force partly to other celestial fields is a material causal error.
- S45 fails strict: correct later Ohm's-law reasoning leaves initial reversed current claims unretracted, and unspecified gloves are offered as protection. Valid dry-hands advice does not remove those errors.
- S06 fails strict: identifying roots' specialized uptake function and its importance for growth only restates the question; no additional explanatory basis is supplied.

## Source and execution

- Model: `nvidia_OpenReasoning-Nemotron-1.5B-Q4_K_M.gguf`
- Model SHA-256: `7c39e6fa1f335bec37e51404d104b47de0b80aafeaae534080aa8c2e11c71101`
- Responses SHA-256: `e0550f8b158fe258409e646af2331cb4bb1a9342cf59ab68d250d4d38b9fb2ef`
- Hardware: Apple M4 Pro, 24 GiB; Metal-enabled llama.cpp from source revision `60bccc3763395e01b039aa1ddeacc8cc0ea69f70`.
- Raw completion: context 2,048; 2 CPU threads; GPU layers 99; cache 256 MiB; temperature 0; seed 42; limits 256 tokens for multiple choice and 512 for written responses. No embedded chat template or external system prompt.
- These are accuracy observations for the Mac treatment, not laptop throughput, RSS or composite-score measurements.

[Every decision and source hash](nemotron-1b.json) · [Complete saved responses](../mac-accuracy/nvidia_OpenReasoning-Nemotron-1.5B-Q4_K_M.gguf/stem/responses.jsonl)
