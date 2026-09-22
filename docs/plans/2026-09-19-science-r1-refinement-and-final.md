# R1 science-tutor refinement and final selection

## Objective

Continue the exact selected P2 checkpoint-63 adapter on its original recovered
Muta parent, using a fresh optimizer and a small, high-value expansion focused
on genuine tutoring interactions. Export one selected Q4_K_M contender, run the
frozen final batteries, and issue a practical deployment recommendation today.

## Token-efficient refinement treatment

- Initialization: exact P2 checkpoint-63, loaded once on its original Muta
  parent; never stack the original Muta adapter or the P2 adapter twice.
- Expansion: 128 independently reviewed MathDial dialogues and 128 independently
  reviewed ConvoLearn earth-science dialogues, excluding every pilot development,
  final-holdout, known-suite, historical-input and quarantined group.
- Stability replay: 1,280 deterministic rows from the admitted pilot training
  artifact, stratified across science MC, worked solutions and retention data.
- Total target: 1,536 rows, effective batch 64, one epoch, 24 optimizer steps.
- Optimizer: fresh AdamW/cosine schedule, rank 16 adapter continued in FP32 on
  BF16 base weights, learning rate 2e-6, no weight decay, warmup 3%.
- Preserve whole conversations and assistant-only loss. Exclude overlength rows
  before freeze; never truncate or split a conversation.
- Save step 12 and step 24. Compare both on the frozen development72 battery;
  choose with the already-frozen index and regression guard. No final-suite result
  may choose the checkpoint.

If fewer than 256 dialogue rows pass review, reduce the new-dialogue count and
the deterministic replay count to the nearest full 64-row batch; never fill a
quota with rejected material. If no meaningful expansion is admitted, stop R1
and compare the unchanged P2 checkpoint-63 as the challenger.

## Release and execution gates

1. Freeze exact JSONL bytes, row/group identities, source/licence counts,
   tokenizer-aware lengths, overlap exclusions and independent review ledger.
2. Add a separate selected-checkpoint initialization path to the trainer. Bind
   base, tokenizer, adapter tree and checkpoint seal hashes; prove exact adapter
   tensors were loaded once and that the optimizer/schedule are fresh.
3. Run local tests plus an adversarial review. Stage immutable sources/config/data
   on Oracle only after fresh host, process and GPU-lock checks.
4. Train once. Preserve failures and do not retry automatically.
5. Run development72 for R1-half/R1-end, freeze the selected checkpoint, merge
   it into the original parent, convert to F16 GGUF, then quantize Q4_K_M.

## Final matched comparison

Compare the selected R1 GGUF with unchanged upstream Qwen, original Muta, the
historical warm-r16-lr5e6 pilot and untouched DeepSeek. Use identical runtime
settings per native template and retain all raw outputs.

Run:

- the source-heldout science MC pack built only from the reserved 1,591-row pool;
- the eight already reviewed final multi-turn tutoring cases;
- the frozen 100 STEM suite;
- the frozen judges suite;
- the frozen practical 2,000-item battery.

The final decision follows the already-frozen priority: reject serious regression
against original Muta, allow at most two lost known STEM MC answers, then prefer
higher heldout science correctness and better fresh tutoring science/pedagogy.
If R1 fails the guards, retain original Muta and report R1 as the challenger.

## Evidence and delivery

Preserve dataset/source manifests, review ledgers, executed sources/configs,
loss logs/curves, adapter/base/merged/GGUF hashes, merge and quantization commands,
raw evaluation outputs and the decision table. Copy only the final selected GGUF
to the Mac; do not duplicate BF16 weights or private training data.
