# Pending science pilot relocation to Oracle

Implementation and local tests only until independent review. The writer does not
cancel jobs, stage remote files or launch GPU work. This implements the standing
authorization to move pending work onto an idle Oracle GPU.

## Scope and immutable treatment

Move only P2 `muta_fresh` (CSD3 job `35822349`) and P3 `pilot_adapter`
(`35822350`) into a new `pilots-oracle-relocation-v1` release. The existing
`pilots-v1` sources/configs remain untouched. Bind the original campaign SHA256
`1e5130d7583951eadbb14fc958935a30a3638070e49bdb03c60bc8a048cb1c11`
and its two exact config hashes. Copy the reviewed `train.py`, `tokenization.py`,
`calibrate.py` and `pilot_launch.py` byte for byte. Include the new controller in
the new source seal.

Derive relocated configs by changing only `run_id`, `output`, `gpu_lock`, and
the existing Oracle paths for data/base/tokenizer/adapter. Preserve every numeric
field, model/data identity, notes, LoRA setting and tokenization setting. Rebuild
and compare this expected config at every admission, rejecting even a rehashed
modified learning rate, batch size or token budget. Frozen treatment remains
126 updates, 257,341 scheduled supervised tokens, microbatch 4 / accumulation 16,
effective batch 64, seed 3407, LR 5e-6, rank/alpha 16/16 and fresh AdamW state.

## Cancellation and duplicate prevention

The explicit `cancel-pending` CLI is for root to execute on CSD3 after review.
It checks exact user/account/job-name/command identity and PENDING state for both
IDs. It uses `scancel --state=PENDING` so a queue race cannot cancel RUNNING work.
It must then collect exact terminal accounting records showing CANCELLED, zero
elapsed time and no start time. Missing, stale, running or ambiguous records fail
closed. Preserve evidence and never automatically retry cancellation or training.

Oracle admission requires that hash-bound cancellation receipt. Fixed, exclusive
per-kind control directories prevent repeated launches across releases; existing
run outputs also reject launch. If CSD3 starts a job before conditional cancel,
relocation cannot proceed. The controller never submits a replacement CSD3 job.

## Qualification, launch and verification

The frozen qualification function is reused with an explicitly installed loader
that verifies this relocation manifest and cancellation receipt; its model,
optimizer, token-weighting and memory checks are unchanged. Each pilot gets its
own disposable child process and actual AdamW update on the longest 64 rows.
After that child exits, recheck the Oracle GPU is idle and identical, then launch
the frozen trainer in a separate fresh process. Respect UID 1000 and the existing
`/tmp/muta-round2-full-uid-1000-gpu-0.lock`. No implicit resume or fallback.

Validate terminal config/source/token/step identities, exact run inventory and
both checkpoint inventories/seals. Unexpected files, path traversal, symlinks,
tampering and partial checkpoints must fail. Keep qualification, launch logs,
failure receipts and terminal evidence. A host move can affect kernel behavior;
matched treatment is not a claim of bitwise equivalence.

## Local validation plan

CPU-only tests cover numeric-config rejection after rehash, immutable snapshots,
pending-only cancellation command and job identity, RUNNING/cancel race rejection,
terminal receipt admission, duplicate launch rejection before GPU work, and
complete/extra/tampered terminal inventories. Independent review must attempt to
break the controller before root executes it.

## Implemented interface and local results

The controller has four explicit commands. Materialization does not require a
cancellation receipt and can be reviewed/staged before queue changes:

```sh
.venv/bin/python model-development/science_tutor/relocate_pilots.py materialize \
  --original-bundle provenance/science-tutor-20260919/pilots-v1 \
  --output provenance/science-tutor-20260919/pilots-oracle-relocation-v1
```

Root then executes `cancel-pending --original-bundle <release/original>
--output <new cancellation evidence directory>` on CSD3. This operation runs as
`ein21`, requires both exact jobs to be PENDING, and preserves every bounded
accounting observation. The resulting `COMPLETED.json` and its SHA256 are passed
to Oracle's `launch` command alongside `--manifest <release/relocation.json>`,
`--manifest-sha256 <SHA>`, and `--kind muta_fresh` or `--kind pilot_adapter`.
`--cancellation <receipt>` and `--cancellation-sha256 <SHA>` are mandatory for both
`launch` and its disposable `qualify` child. Run pilots sequentially on the shared
Oracle GPU after idle verification; each has a unique fixed control directory.

On 19 September, 24 CPU tests passed with `.venv/bin/python -m pytest -q
model-development/science_tutor/test_relocate_pilots.py`; targeted Ruff checks
passed. Independent review identified that a correctly sealed checkpoint could
still lack adapter artifacts. The corrected controller requires nonempty
`adapter_model.safetensors`, `adapter_config.json`, `training-state.pt`,
`state.json`, and `COMPLETE.json` (plus optional `README.md`). It reconstructs the
frozen schedule from resolved per-row token receipts, validates all 126 metrics
steps, and compares both checkpoint state/seal token budgets. Regression tests
also reseal missing adapter, wrong halfway-token, and wrong metrics artifacts
to ensure inventory self-consistency alone is insufficient.

Candidate reviewed controller SHA256:
`f87005775153aa3fcb84ed5c2993850dc6be64ae584fd5a958af460dcaf97e30`.
The writer has not executed cancellation, staging or training. Independent final
review and root execution remain separate from this local implementation.
