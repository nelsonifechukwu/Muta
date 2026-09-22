# Relocate the pending fresh-warm treatment to idle Oracle

User explicitly authorized using the free GPU instead of waiting for CSD3.
This changes **placement only**, not the frozen treatment. No remote action was
taken while preparing this plan.

## Admission: root owns these live checks

1. Inspect CSD3 job **35801870**. Only if still pending, use
   `scancel --state=PENDING 35801870`. This filter must not be dropped.
2. Confirm its terminal cancellation, no start/allocation/training evidence,
   no candidate launch/output, and no duplicate active fresh-warm job. Preserve
   the submission, pending and cancellation/accounting evidence. If it started
   during the race, leave healthy work alone and do **not** start Oracle.
3. Preserve these actual observations in an externally reviewed admission file;
   supply its absolute path and SHA256 to the shell supervisor. The supervisor
   authenticates the approved bytes, not live Slurm semantics. A claim written
   without checking actual CSD3 state is not admission.
4. Oracle's two short evaluation smokes finished; no full judges/STEM run was
   started. Root must confirm their children exited and GPU is idle before
   closing **only its own** evaluation shell's FD9 (PID 166103/session 6530).
   Do not kill a server, trainer, controller or unrelated lock owner to make room.
5. Use the new durable one-run shell below, not the completed clean/continuation
   queue. Preserve all existing queue, training, export and evaluation receipts.

## Frozen treatment / paths

| Field | Unchanged value |
|---|---|
| Candidate | `full-best-warm-private-enriched` |
| Initialization | Fresh r16 adapter on original recovered Muta v1; no pilot initializer |
| Learning rate / global batch | 5e-6 / 64 (one GPU, accumulation 1) |
| Rows / steps / epoch | 300350 / 4693 / 1 |
| Development set / milestones | 5000 / 1174,2347,4693 |
| Config SHA256 | da828b9146415ca822fecf1961808b914e9666cf7452de34e7704b97f83675da |
| Warm-parent tree | 02add79d0a5d451c7b75a986a4d3154bf6a98e23f12d9f913f00036c1909fec8 |

The script's exact arguments are copied from the successful Oracle stage-1
receipt, changing only candidate ID to the already frozen fresh-warm treatment.
It uses the original clean tokenizer and original warm parent, eight dataloader
workers, and the identical data/validation manifests. No `--initial-adapter`,
checkpoint resume, batch override or new config is supplied.

Frozen code remains at
`/lambda/nfs/awf-tmp/muta/campaign-20260918/code/fullstage-v3-20260918T2035`.
New candidate output:
`/lambda/nfs/awf-tmp/muta/campaign-20260918/runs/full/full-best-warm-private-enriched`.
New supervisor receipt directory:
`/lambda/nfs/awf-tmp/muta/campaign-20260918/queues/warm-fresh-relocation-20260919-v1`.
Existing paths are a hard refusal; no automatic reuse/retry or deletion.

## Durable execution handoff, after independent review

Stage `provenance/scripts/launch_warm_fresh_oracle_20260919.sh` outside frozen
code; verify its reviewed SHA256. Root records that source hash, admission hash,
command, safe environment and returned supervisor PID. From a separate shell
after the old evaluation lock is released:

```bash
set -o noclobber
nohup /usr/bin/env -i \
  PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 \
  CUDA_VISIBLE_DEVICES=0 PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
  HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1 \
  TOKENIZERS_PARALLELISM=false PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  /bin/bash "$VERIFIED_SUPERVISOR_SCRIPT" "$REVIEWED_RELOCATION_ADMISSION" "$ADMISSION_SHA256" \
  > /lambda/nfs/awf-tmp/muta/campaign-20260918/queues/warm-fresh-relocation-20260919-v1.nohup.log \
  2>&1 < /dev/null &
WARM_SUPERVISOR_PID=$!
printf '%s\n' "$WARM_SUPERVISOR_PID"
```

Check the PID, receipt directory, GPU-idle record and candidate launch receipt;
do not infer successful startup merely from a background PID. The existing
launcher verifies all source/config/data/base/tokenizer joins and the trainer
records its normal RUNNING/resolved-config/metrics/checkpoints/terminal evidence.

The shell holds the stable per-user GPU flock nonblockingly while its one
launcher runs. GPU query failure or any compute process prevents launch. It
atomically claims the candidate output before calling the existing launcher,
which otherwise permits an existing output directory. `nohup` survives SSH
disconnect; it is not automatic retry or a new scheduler.

**Limitation:** the unchanged launcher closes inherited FDs when it starts its
trainer. If the supervisor and launcher both fail while the trainer survives,
the global flock may be released. Preserve failures and inspect recorded PIDs,
GPU processes, candidate RUNNING/checkpoint state and the trainer's per-run lock
before any further action. Never automatically restart or force-unlock. The
script records controller exit, not a semantic training/export verification;
terminal manifests must still pass the existing full-stage artifact preflight.

Postpone full judges/STEM evaluation while this training owns Oracle. After
completion/export/runtime checks, use a **new five-model manifest/evaluation**
including fresh-warm; do not alter the already frozen four-model manifest or
reuse its sealed smoke output directories. CPU qualification and independent
winner tests remain separate.

## Verification status

Local Bash syntax and ShellCheck pass. Static expansion of the command array
matches the preserved Oracle stage-1 argv exactly except for the intended
candidate ID and Python `-B`; no initializer or resume is supplied. All 66
existing promotion/launcher/v3 tests pass. No synthetic or real shell training
run was executed. Independent review is required before execution.
No host relocation or training completion is claimed by this document.
