# Depth pruning of Muta-Tutor Qwen2.5-1.5B — spec

**Date:** 2026-09-16. **Status:** approved direction from the user; implementation plan in
[2026-09-16-depth-pruning-qwen25-1.5b.md](2026-09-16-depth-pruning-qwen25-1.5b.md).

## Request (verbatim intent)

> Take note our base model is Qwen 2.5 1.5B. Discard the Qwen 3.5 0.8B. Create an elaborate
> plan for: Strip some model layers (Depth pruning) — see also Layer Pruning via Representation
> Angular Distance (BI-Pruning). Recent advances in structured depth pruning (ShortGPT, Block
> Pruning) reveal that adjacent hidden layers in deep LLMs have high representation similarity —
> often performing redundant transformations. Instead of naive layer dropping, compute the Block
> Influence (BI) or cosine distance between input and output representations across layers.
> Prune 25%–40% of the middle layers with the lowest angular impact. Healing: run lightweight
> parameter-efficient fine-tuning (LoRA) on the remaining layers to adapt to the pruned layer
> jumps, merge the LoRA back into the base FP16 weights, and finally quantize to GGUF. The
> result: a 32-layer 8B architecture drops to 22 layers, immediately reducing RAM weight,
> activation buffer sizes and KV memory in a single step.

## What "base model" means here

`timiiowolabi/Muta-Tutor-Qwen2.5-1.5B-ADTC-GGUF/Muta-Tutor-Qwen2.5-1.5B-Q4_K_M.gguf`
(986,048,128 bytes, sha256 `a750d00d458c6ab38925364ea1413db00648449180941e47025736d09922e1eb`),
which is `Qwen/Qwen2.5-1.5B-Instruct` @ `989aa7980e4cf806f80c7fef2b1adb7bc71aa306` + BF16 LoRA
r16, 500 steps, lr 2e-5, seed 3407 on the licence-clean `licensed-mcq` mixture
(`model-development/finetune/`), merged and exported as Q4_K_M.

Architecture: 28 decoder layers, hidden 1536, intermediate 8960, 12 attention heads / 2 KV
heads (head dim 128), tied embeddings, vocab 151,936, 1,543,714,304 parameters. Per layer:
46,797,824 parameters (≈30.5 MB in the published Q4_K_M); embedding 233,373,696 (≈131 MB).

## Why (the score arithmetic)

Semi-final re-test on the reference audit image (RESULTS.md 2026-09-16): 5.77 tok/s,
1099.5 MB peak RSS, ARC-Easy-50 0.84, judge-prompt proxy 38 %. Under the ADTC formula
`0.50·S_acc + 0.30·min(TPS/15,1)·100 + 0.20·max(0,(7−GB)/7)·100`, decode speed is the weak
term (S_perf 38.5). Exchange rates from `bench/score.py`: **1 tok/s = 2.0 points** (below the
15 tok/s cap), **1 accuracy point = 0.5 points**, **100 MB = 0.29 points**. Depth pruning
attacks the expensive term directly; its only cost is accuracy, which is what healing must
recover.

## Success criteria

A pruned+healed Q4_K_M GGUF is **promoted** over the published file only if, measured with the
reference audit image on `muta-vm` and the same evaluation battery for both:

1. `S_total` with `S_acc` = ARC-Easy-500 (profiler accuracy code) is ≥ published + 1.0;
2. `S_total` with `S_acc` = the 10-prompt judge proxy (RESULTS.md 2026-09-16 protocol) is
   ≥ published + 1.0;
3. GSM8K-40 (generative, greedy) does not drop more than 5 points;
4. the file loads, terminates, and renders the tutor template on llama.cpp b10175 and on
   llama-cpp-python; and
5. `metadata.json`'s `parameters_estimate` passes the profiler's ±15 % fraud check against the
   pruned tensor table.

Otherwise the campaign is recorded as rejected with data, and the published file stays.

## Hard constraints

- Prune only the Qwen2.5-1.5B tutor; the Qwen3.5-0.8B lane is closed.
- Prune 25–40 % of layers (7, 9 or 11 of 28); a 4-layer anchor is allowed as a low-risk point.
- Never remove the first two or the last layer.
- Layer choice comes from measured Block Influence / angular distance on a calibration set
  drawn from the healing training data, never from position alone.
- Healing = BF16 LoRA (rank 16, α 16, q/k/v/o/gate/up/down, completion-only loss, 1024
  context, seed 3407) on the licence-clean `licensed-hybrid` mixture, merged into BF16, then
  exported with pinned llama.cpp **b10175** (`convert_hf_to_gguf.py` + `llama-quantize
  Q4_K_M`), tied head.
- Nothing from ARC / QASC / OpenBookQA / GSM8K validation or test splits, the ARC-Easy-500
  evaluation set, the two submitted test prompts, or the ten Round-1 judge prompts may appear
  in training or calibration data.
- Every score-of-record number comes from `adtc-profiler run --mode audit --seed 42` inside
  the reference image (`adtc-profiler:latest`, built from upstream `ac2e137`'s Dockerfile) on
  `muta-vm`, one run at a time, with the VM otherwise idle.
- Same-day `RESULTS.md` entry for every measurement; GGUFs stay untracked and are identified
  by sha256.
