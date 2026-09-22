# Science tutor backward-only GPU calibration

Status: implementation/review draft. **No GPU launch has been authorized by this document or performed by its writer.** Root must inspect the final source, bind its hashes and issue a reviewed launch configuration.

## Purpose and limits

Measure a small, bounded matrix of microbatches 1/2/4 and input lengths 512/2048/4096 on Oracle's A100 40 GB. Use the already verified upstream Qwen2.5-1.5B-Instruct parent, the common upstream tokenizer and a fresh rank-16 LoRA. Each cell performs one warm-up and two timed forward/backward passes. There is no optimizer, optimizer update, checkpoint, saved adapter or accuracy claim. Repeated plain-text evidence sentences are explicitly synthetic diagnostics, never admitted training data. Actual admitted-data calibration supersedes this diagnostic before estimating end-to-end training time.

## Safety and evidence

- Validate exact config and source-manifest hashes, the reviewed trainer/tokenizer source files, known upstream parent tree, common tokenizer bytes and chat template before model loading. The source manifest identifies a working-tree source snapshot separately from its repository HEAD commit.
- Acquire only `/tmp/muta-round2-full-uid-1000-gpu-0.lock`, require UID 1000 ownership and a regular non-symlink file. Require exactly one physical A100 of approximately 40 GiB and no pre-existing compute process. Check again before every cell; no process is killed.
- Retain at least 4 GiB and 15% of total GPU memory as headroom. Project the next cell from observed peak increments and a conservative logits-memory floor. Skip anticipated non-fitting cells with an explicit reason. This heuristic reduces, but cannot eliminate, OOM risk.
- An actual failure terminates the whole diagnostic. Preserve its exception and all earlier measurements; never silently retry or continue after OOM.
- Use an exclusive, initially absent output directory. Keep exact admission/host records, cell measurements, source/config hashes and an inventory sealed by `COMPLETED.json`. Failure uses `FAILED.json`, never a success marker.
- Recommend only among actually measured passing cells, grouped by sequence length. The recommendation is a synthetic backward-only measurement, not guaranteed safe for optimizer-state memory, real dialogue lengths, full training or other GPU hardware.

## Review and launch sequence

1. CPU tests and independent/root source review.
2. Root creates a source manifest containing exact `calibrate.py`, `train.py` and `tokenization.py` hashes; separately binds a complete host-local configuration. `launcher-draft.json` is deliberately non-executable and is not a launch admission.
3. Root verifies live host processes, lock ownership and source/config joins, then explicitly runs the new diagnostic. It must not overlap healthy training/inference.
4. Inspect the terminal receipt and measured table before selecting a microbatch. Later, validate representative real admitted conversations, their optimizer budget and full effective-batch schedule under a separately reviewed run.

## Interface

`python calibrate.py --config /absolute/config.json --config-sha256 <exact SHA256>`

The bounded matrix and iteration counts are fixed in source. No configuration can enlarge the trial count, change the parent, disable headroom, choose a different GPU lock or write trained weights.
