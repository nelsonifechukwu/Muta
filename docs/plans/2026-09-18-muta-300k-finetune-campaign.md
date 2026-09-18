# Muta 300K fine-tune campaign

Date: 2026-09-18

## Objective

Train and compare several Qwen2.5-1.5B LoRA candidates with the frozen
300,350-row Muta STEM artifact, select the best model on matched held-out tests,
and produce the complete Gate 2 proof-of-training bundle under `provenance/`.

## Frozen inputs

- Training artifact: `data/muta-stem-v2-sft-300k-quality-first-20260917-v1`
  (300,350 rows; dataset fingerprint
  `037edf28cccff62d90c23e2d6caf56b9998dea6928080f98af2a513f9f92910e`).
- Clean parent: `Qwen/Qwen2.5-1.5B-Instruct` at revision
  `989aa7980e4cf806f80c7fef2b1adb7bc71aa306`.
- Incumbent Muta: recovered Oracle run
  `qwen25-bf16-r16-licensed-mcq-lr2e5-500`; published Q4_K_M SHA-256
  `a750d00d458c6ab38925364ea1413db00648449180941e47025736d09922e1eb`.
- Exact Gate 1 judge suite: `bench/judges_prompt_suite.py`.
- Fixed 100-prompt STEM suite: `bench/stem_prompt_suite.py`.

## Lineages

Two lineages are required so the comparison is interpretable:

1. **Clean:** pinned Qwen base -> new 300K LoRA.
2. **Warm:** recovered, already-merged Muta v1 -> new 300K LoRA.

The warm lineage must always be labelled as two-stage training. Its earlier
ARC/QASC stage remains part of its provenance. The old adapter must never be
stacked onto weights that already contain it.

## Work plan

1. Inventory and hash the recovered incumbent adapter, merged checkpoint,
   Trainer state/logs, tokenizer files, and GGUF before any run.
2. Make the trainer manifest-aware: verify every shard path, byte count,
   row count, SHA-256, and aggregate dataset fingerprint before loading.
3. Build a deterministic 3,000-5,000-row representative development artifact
   from eligible warehouse rows not selected into the 300K artifact and not in
   any frozen evaluation/holdout set. Bind it with a manifest and hashes.
4. Record resolved config, Git state, environment, GPU, package versions,
   base/tokenizer hashes, data hashes, step logs, checkpoints, adapter hashes,
   merge hashes, GGUF hash, and exact commands for every run.
5. Add smoke tests for shard verification, deterministic selection,
   completion-only labels, warm-start lineage, hash failures, and resume.
6. Transfer only the 300K artifact, development artifact, frozen scripts, and
   required baselines to each GPU host. Never publish the private dataset.
7. Capture matched pre-training outputs from the clean base and incumbent Muta.
8. Run identical short pilots across both GPU systems. Initial grid:

   | Axis | Values |
   |---|---|
   | lineage | clean, warm |
   | rank | 16, 32 |
   | learning rate | 1e-5, 2e-5 |
   | precision | BF16 LoRA |
   | seed | 3407 |
   | context | 512, after a fresh zero-truncation tokenizer preflight |

   Pilot rows, optimizer steps, effective batch, and data order are identical.
   A QLoRA control is optional only after the BF16 grid is healthy.
9. Rank pilots using representative dev loss plus matched correctness and
   tutoring outputs. Loss alone cannot promote a model.
10. Promote the best clean and best warm pilot to one full epoch over all
    300,350 rows. Preserve the best and final checkpoints. Also retain one
    300,000-row Muta/DeepMind-only candidate as the distribution-safe ablation;
    the 350 private exam rows must stay explicitly labelled private-use.
11. Merge each promoted adapter, convert through a pinned llama.cpp checkout,
    quantize to Q4_K_M, and verify loadability and chat-template behavior.
12. Evaluate the clean base, incumbent Muta, and promoted candidates with the
    same prompts and sampling: ARC-Easy 500, the 100 STEM prompts, all ten Gate
    1 judge prompts, the secondary held-out battery, format/stop tests, and
    generated-equivalent contamination checks. Save full unedited outputs.
13. Profile promoted GGUFs on the target CPU path for TPS, TTFT, whole-tree RSS,
    temperature, throttling, and ADTC composite score.
14. Select the winner only if it improves correctness/tutoring without a
    material deployment regression. Otherwise retain the incumbent.
15. Assemble `provenance/` with adapters, configs/scripts, logs, loss CSV/JSON
    and PNG/SVG curve, dataset description and safe sample, licences, hashes,
    merge/quantization commands, host/job IDs, matched outputs, and result tables.

## Result table contract

The campaign summary is table-first. Every candidate row must include:

| Field | Required |
|---|---|
| lineage / rank / LR / steps / examples / tokens | yes |
| final train loss / best dev loss | yes |
| ARC-Easy / STEM MCQ / STEM written / judge rubric | yes |
| TPS / TTFT / peak RSS / GGUF bytes / ADTC score | promoted GGUFs |
| adapter SHA-256 / merged-tree digest / GGUF SHA-256 | yes |
| status and promotion reason | yes |

## Stop conditions

- Any shard, base, adapter, or checkpoint hash mismatch.
- Any hidden row drop, prompt truncation, empty completion mask, NaN/Inf loss,
  resume mismatch, or mixed lineage.
- Missing full-output evidence for an evaluated prompt.
- Private WAEC/Cheetah rows entering a public sample or Git commit.
- Full training before both a 20-100-step smoke and checkpoint resume pass.
