# Round-two pilot training status

Eight pilots completed on 18 September 2026. Each trained for one epoch on the
same 20,000 selected rows (313 optimizer steps, effective batch 64) and evaluated
on the same 5,000 development rows. The selected-row order digest is
`82ad3609d53c84502a020b6efce030133dce1bd4d92650952f4424aa5a8bca63`.
This is 160,000 row presentations across eight models, not 160,000 distinct rows.

| Candidate | Host | Training rows | Steps | Final development loss |
|---|---|---:|---:|---:|
| warm-r16-lr2e5 | CSD3 | 20,000 | 313 | 0.2170596421 |
| warm-r32-lr1e5 | Oracle | 20,000 | 313 | 0.3398278356 |
| clean-r32-lr1e5 | Oracle | 20,000 | 313 | 0.3468289077 |
| warm-r16-lr1e5 | CSD3 | 20,000 | 313 | 0.5780092478 |
| clean-r16-lr1e5 | Oracle | 20,000 | 313 | 0.5932567120 |
| warm-r32-lr5e6 | Oracle | 20,000 | 313 | 0.6859107614 |
| warm-r16-lr5e6 | CSD3 | 20,000 | 313 | 0.9617626667 |
| warm-r8-lr5e6 | CSD3 | 20,000 | 313 | 1.1516853571 |

These are development-loss results, not answer accuracy or a winner selection.
Oracle and CSD3 used different recorded Torch/CUDA environments; this table does
not isolate a causal hyperparameter effect from a host/runtime effect.

At this snapshot, the 300,350-row full treatments had not started. No new final
full-data GGUF or final GGUF evaluation was complete.

## Completed pilot GGUF smoke test

The clean-r32-lr1e5 pilot was merged and exported to Q4_K_M on Oracle. Its
986,047,968-byte GGUF is at:

`/lambda/nfs/awf-tmp/muta/campaign-20260918/exports/pilot-clean-r32-lr1e5/Muta-Round2-Pilot-Clean-R32-LR1e5-20k-Q4_K_M.gguf`

SHA-256: `ce82fdf54bc46e737f92f90e6788b9d6f777eb3e94185d624d042763cdb533fb`.
The export receipt is `provenance/exports/pilot-clean-r32-lr1e5/quantization-manifest.json`.
The large GGUF remains remote; this receipt is not a local copy of the model.

Both GGUFs loaded successfully and returned complete responses to the same two
Gate 1 prompts with greedy decoding and CPU-only inference. Manual inspection:

| Prompt | Existing Muta | 20K clean pilot |
|---|---|---|
| Six boxes of chalk at N500 each | Incorrect: B, N2,500 | Correct option C; omitted requested calculation |
| Plants using sunlight to make food | Correct: B, photosynthesis, with explanation | Correct: B, photosynthesis, with explanation |

This two-question loading/response check is too small to establish overall model
quality. It does not replace the full judges/STEM/ARC evaluation. Literal outputs
and settings are in `provenance/evaluation/pilot-gguf-smoke-20260918/`.

The full 300,350-row tokenizer preflight also passed: 48,837,785 sequence tokens,
25,106,185 assistant tokens, longest sequence 459, zero errors at context 512.
This is an input-readiness check, not evidence that those rows have been trained.
The captured preflight stdout and method are archived in
`provenance/calibration/full-tokenization-preflight-20260918.json`.

Original adapter/checkpoint roots:

- Oracle: `/lambda/nfs/awf-tmp/muta/campaign-20260918/runs/pilots/`
- CSD3: `/rds/user/ein21/hpc-work/muta-round2/runs/pilots/`

CSD3 execution evidence is in `provenance/hosts/csd3/`; job 35754294 completed
with exit code 0. Each original run's `training-manifest.json`, `COMPLETED.json`,
metrics, adapter, and checkpoint files remain the authoritative receipts.
