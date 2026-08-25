# Fast competition fine-tuning

This directory builds two BF16 LoRA candidates without changing the verified GGUFs:

- Qwen3.5 0.8B → Q4_0 for the profiler's scalar lane;
- Qwen2.5 1.5B Instruct → Q4_K_M for the vector-enabled lane.

The dataset builder uses pinned training splits and writes a manifest containing source
revisions, row counts and output hashes. Evaluation splits and submitted prompts are excluded.

```bash
./setup_gpu_env.sh .venv
.venv/bin/python build_dataset.py --output data
.venv/bin/python train_lora.py \
  --model Qwen/Qwen3.5-0.8B \
  --revision 2fc06364715b967f1860aea9cf38778875588b17 \
  --train data/train.jsonl \
  --validation data/validation.jsonl \
  --output runs/qwen35-full \
  --gguf-method q4_0
```

The exported GGUF is a candidate, not a promoted model. Apply the existing Muta metadata-only
tutor template, then run the exact artifact through the bundled profiler, scalar/vector
throughput harness and live-prompt battery before changing the model roster.

`export_base.py` exports an untouched pinned checkpoint through the same quantizer. Use that
control whenever a fine-tuned artifact differs in size from the existing third-party GGUF so a
training effect is not confused with an export-recipe effect.

`run_sweep.sh` extends the two full BF16 controls with rank-8 and rank-32 pilots, a lower learning
rate, a reasoning-heavy data profile and a 4-bit QLoRA branch for each architecture. Each branch
writes its own log, adapter, merged checkpoint, GGUF and training manifest; a failed branch does
not suppress the remaining experiments.

The first sweep showed that lower validation loss did not reliably transfer to the profiler's
ARC prompt. `build_metric_dataset.py` therefore provides two second-phase datasets:

- `mcq`: training-only ARC, OpenBookQA and QASC in the profiler's exact raw prompt shape;
- `hybrid`: the same data plus 2,000 GSM8K solutions, 2,500 short OpenR1 traces that passed
  Math Verify and completeness checks, and the verified African arithmetic set.
- `licensed-mcq`: the profiler-shaped MCQ profile without OpenBookQA, whose current dataset card
  does not specify a licence;
- `licensed-hybrid`: the hybrid profile with the same exclusion. The remaining licences are
  explicit but still carry their own attribution and share-alike obligations.

Both profiles reject exact and near-duplicate overlaps with every source validation/test split.
`run_metric_sweep.sh` compares lower learning rates, ranks, BF16 LoRA and QLoRA on these corrected
profiles. No source validation/test record is used for training.
