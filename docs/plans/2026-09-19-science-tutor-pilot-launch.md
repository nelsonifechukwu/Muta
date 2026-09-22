# Matched science-tutor pilot launch design

Implementation/review draft only: the writer must not launch, submit, modify live sources or spend GPU time. Root independently reviews the new wrapper before materializing or executing anything.

## Frozen experiment

Three initializations: untouched upstream Qwen on Oracle; original recovered Muta and the unchanged winning pilot adapter on its original Muta parent on two separate one-GPU CSD3 allocations. All use the admitted whole-conversation artifact, common upstream tokenizer, one shuffled epoch with the trainer's disclosed repeated tail, seed 3407, effective batch 64, rank/alpha 16/16, zero dropout, LR 5e-6, zero weight decay, 3% warm-up, maximum length 4096 and assistant-only loss. After the real artifact measured at most 755 training tokens and 689 development tokens and the synthetic diagnostic admitted batch 4 at length 2048, root selected microbatch 4 with accumulation 16, conditional on actual-data qualification. Any later host-specific change must be separately frozen and qualified, never silently adapted after results.

The initial target was 20–40K conversations, but the actual admitted artifact may be smaller. Counts, token budgets and paths are read from actual admitted files, never copied from the planning target. No final holdout is read by the trainer or launch wrapper.

## Materialization and staging

`pilot_launch.py materialize --spec <absolute JSON> --spec-sha256 <SHA> --output <new local bundle>` validates actual local train/dev/admission files and the common tokenizer, tokenizes complete conversations, calculates the exact one-epoch schedule and supervised-token budget, and produces three host-mapped trainer configs. The supplied host descriptor provides real staging/base/adapter/python paths; the materializer does not assert those remote paths exist. It copies only small executed source files, never dataset text or model weights. Root transfers each bundle to the declared release directory and stages each input once, then remote preflight re-verifies every source/config/input/base/adapter hash.

The source manifest identifies a working-tree snapshot separately from repository HEAD. Its executable modules include the unchanged trainer/tokenizer and previously reviewed calibration helpers. Any source edit requires a new bundle and review. Generated CSD3 batch files are drafts, never automatically submitted.

Latest user steering also requests DeepSeek-R1-Distill-Qwen-1.5B. This three-Qwen profile deliberately does not invent or admit its model/tokenizer identities. Add a separate reviewed profile/release after official base, native template and reasoning-token masking are verified, with no Muta adapter attached. Its fresh pilot is a sequential Oracle item, not another CSD3 credit request. Match canonical rows, epoch, seed, LR and effective batch; record any native-template difference in actual supervised-token totals instead of pretending token budgets match automatically.

## Allocation and budget

Oracle must use the existing `/tmp/muta-round2-full-uid-1000-gpu-0.lock` and UID 1000. CSD3 must run inside an allocation owned by the current `ein21` user, account `mlmi-ein21-sl2-gpu`, partition `ampere`, one node/task/GPU, and at most 110 minutes. Two such jobs reserve at most 3 h 40 min of the reported remaining 4 GPU-hours. Root must freshly verify account balance and existing jobs before submission; the reported balance is not a persistent entitlement.

Slurm assigns CSD3's physical GPU. The wrapper derives it from `SLURM_JOB_GPUS`, validates the allocation, and checks only that allocated device for foreign compute processes. CSD3 uses a per-run advisory lock plus Slurm's GPU allocation; this avoids serializing two legitimate jobs on different GPUs of the same node. Global shared control directories reject duplicate attempts even on different nodes. The wrapper never resubmits old job 35801870, relocates jobs, or kills unrelated processes.

## Real-data qualification before a long run

An explicit disposable qualification child uses the longest 64 admitted conversations, the exact candidate parent/adapter and proposed microbatch, a full token-weighted effective batch, gradient clipping and one actual AdamW update. It records peak memory, full-batch timing, allocated optimizer state and changed diagnostic adapter tensors, then discards the entire disposable model without saving weights. This is not a pilot checkpoint and contributes no learned state to the pilot. No diagnostic loss is called an accuracy result.

The child acquires the declared GPU lock, checks device ownership/idle state, and stops with preserved evidence on any failure; there is no automatic retry or microbatch fallback. Passing qualification requires at least max(4 GiB, 15%) device headroom after optimizer allocation. CSD3 also needs sufficient remaining wall time for a conservative longest-batch projection plus overhead. Root must review failed qualification before any new attempt.

The parent then verifies the exact qualification receipt, waits for the child to exit, rechecks the allocated GPU is idle, and starts the unchanged trainer as a fresh process. There is necessarily a small check-to-lock interval: the trainer acquires the actual GPU lock itself. Another compliant owner causes a preserved failure, not concurrent execution. Oracle isolation requires all campaign work to respect the shared lock; CSD3 resource isolation is additionally scheduler-enforced.

## Evidence and interpretation

Unique launch directories, exact config/source/data/base identities, raw child stdout/stderr, qualification measurements, failures, trainer checkpoints/logs and terminal checksums are preserved. Completed or failed launches are not implicitly resumed. Later own-stage resume needs a separately reviewed command using the trainer's existing explicit resume interface.

Hosts may differ in GPU model, CUDA/PyTorch/kernel behavior and realized microbatch efficiency. Record actual environment and hardware; do not attribute cross-host differences solely to initialization or LR. Seed and token budget matching do not imply bitwise equivalence.
