# VibeThinker 1.5B Q4_K_M — Mac STEM review

Provisional assistant grading: **16/100 strict passes; 22/100 correct core answers**. This is the raw-completion STEM battery, not ARC accuracy, the chat judges suite, or an official ADTC score.

| Category | Strict pass | Core correct | Responses |
|---|---:|---:|---:|
| Math multiple choice | 6 | 6 | 25 |
| Math written | 1 | 1 | 25 |
| Science multiple choice | 8 | 14 | 25 |
| Science written | 1 | 1 | 25 |

All 100 responses were read in full. There were 85 token-limit finishes and 28 whitespace-only responses. Many remaining failures contain repeated punctuation or instructions rather than a solution. A token limit alone was not counted as failure: completed calculations in M06, M13–M15, M17 and M25 received credit.

Strict grading requires every requested substantive component and no unresolved material error. Correct option values can pass without a letter; wrong explicit letters cannot. Clear self-corrections are accepted. A requested check needs a distinct numerical method, not a repeated derivation. Formatting and repetition alone do not invalidate a complete answer.

Science examples distinguish incomplete or faulty support from a correct core: S06 identifies roots but falsely gives leaves pith; S19 selects H₂O without explaining its atomic composition. S42 supplies a workable experiment and treatment repeats, despite imprecise replication wording. Lead review changed S13 to a strict pass: its correct second-law explanation is complete, and an immediate zero-force/constant-velocity statement clarifies the awkward first-law wording. Additional review verified all 100 source bindings and read 22 selected responses in full; this was not a second full regrade.

## Source and execution

- Model: `VibeThinker-1.5B-q4_k_m.gguf`
- Model SHA-256: `3df5dae7a65dfd426c8dc58d97ed1247af4b669bc2674c5f9b2b34103b01e164`
- Responses SHA-256: `f956a2cad801afbe48a25dff4c9bc11900908adbaecb201dbff4a9b2f92f5c34`
- Hardware: Apple M4 Pro, 24 GiB; Metal-enabled llama.cpp from source revision `60bccc3763395e01b039aa1ddeacc8cc0ea69f70`.
- Raw completion: context 2,048; 2 CPU threads; GPU layers 99; cache 256 MiB; temperature 0; seed 42; limits 256 tokens for multiple choice and 512 for written responses. No embedded chat template or external system prompt.
- These Mac results supply an accuracy comparison only. They do not replace GCP throughput, RSS, or composite-score measurements.

[Every decision and source hash](vibethinker-1b.json) · [Complete saved responses](../mac-accuracy/VibeThinker-1.5B-q4_k_m.gguf/stem/responses.jsonl)
