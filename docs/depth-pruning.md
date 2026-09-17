# Depth pruning — design notes and campaign record

This file starts as a record of one build-time finding from Task 4; later tasks in the
depth-pruning campaign (healing, evaluation, the final ladder decision) expand it.

## llama-quantize --prune-layers cross-check (Task 4, 2026-09-17)

Task 4 built the byte-exact pruning tool (`model-development/prune/prune_gguf_layers.py`)
and tried to cross-check one candidate against upstream llama.cpp's own layer-pruning path,
per plan Step 7:

```
sudo $L/build/bin/llama-quantize --prune-layers 9,10,11,12,13,14,15 \
  ~/adtc-semis/subs/qwen25-1.5b/model/Muta-Tutor-Qwen2.5-1.5B-Q4_K_M.gguf \
  /tmp/xcheck-21L.gguf copy 2
```

(`$L` = `llama.cpp` b10175 built fresh on `muta-vm` for this check; this is
`unhealed-21L-contiguous`'s drop list.)

**Result: refused**, partway through the streaming tensor copy (on `blk.10`, before
pruning logic would even apply, since tensors are validated in original order regardless of
the drop list):

```
ggml_validate_row_data: found nan value at block 32
llama_model_quantize: failed to quantize: tensor 'blk.10.attn_v.weight' has invalid data
llama_quantize: failed to quantize model from '.../Muta-Tutor-Qwen2.5-1.5B-Q4_K_M.gguf'
```

Retrying with `--allow-requantize` added gave the **identical failure**, same tensor, same
line.

**This is not bad tensor data in the published GGUF.** Controller-run evidence: in the same
reference image (`adtc-profiler:latest`, llama.cpp b10175), `llama-cli --check-tensors`
loads the published `Muta-Tutor-Qwen2.5-1.5B-Q4_K_M.gguf` and generates, and does the same
for all eight `unhealed-*.gguf` candidates. The refusal is specific to
`llama-quantize --prune-layers ... copy`'s own row-data validator rejecting this
already-quantized (Q4_K_M) input on its copy/prune path — not a defect in the source model
or in `prune_gguf_layers.py`'s output.

**Verification of record instead** (per the plan's fallback for this exact scenario):

- the synthetic-GGUF round-trip unit test
  (`test_prune_gguf_roundtrip_drops_layers_and_rewrites_block_count` in
  `model-development/prune/test_prune_helpers.py`), and
- the eight load-and-generate checks against all `unhealed-*.gguf` candidates in the
  reference image (Task 4 Step 6 — every candidate loaded and produced text).

## llama-cli non-interactive flag gotcha (reference image, for later tasks)

In this same reference image's `llama-cli` (build `b1-60bccc3`), `-no-cnv` /
`--no-conversation` alone do **not** prevent interactive mode from hanging after a single
`--prompt` turn — it drops into its REPL waiting on stdin, which spins indefinitely (and
burns CPU) when stdin isn't attached, e.g. under `docker run` without `-i`. Add
`-st` (`--single-turn`) to get a clean one-shot run that exits after generating.
