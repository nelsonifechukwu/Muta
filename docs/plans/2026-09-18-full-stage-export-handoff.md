# Full-stage GGUF export handoff

Current handoff update: **19 September 2026, 01:04:30 UTC**. Both completed Oracle full-data
training stages and selected exports are complete, with one hash-verified Mac
Q4_K_M copy each. The clean export required separate successful reconciliation
of a controller verifier defect; its original failure remains unchanged, with
no re-export or retroactive successful terminal. Continuation has its own
completed export receipt. Both new exports passed bounded four-model normal-stop
and duplicate-integrity smokes, eight responses each. Full judges/STEM quality
suites are deferred until after the third training. At the user's request,
CSD3 fresh-warm job **35801870** was cancelled while pending at 00:58:02;
00:58:55 proof confirms no allocation, zero runtime and absent run output.
The replacement launched on Oracle at 01:02:46 (supervisor 166611, launcher
166636, trainer 166638). All were live at 01:04:30; tokenization was at 50,121 /
300,350 rows, with optimizer training not yet started. The executed supervisor
proof SHA256 is `bcc54f70874bdc0b3686d5acb25d233e9dc7733d105f098dcb049d4d2cc2bfed`;
the later local hardening draft was not executed and is not historical proof.
Only our idle evaluation shell/FD was closed at 00:59:42; no healthy training
was interrupted. CSD3 keepalive and the user's SSH session remain untouched.
**No overall quality winner or target-CPU qualification is established.**
See [current status](../../provenance/results/FULL_TRAINING_LAUNCH_STATUS.md),
[single-copy delivery](../../models/round2/full/README.md), and
[executed reconciliation](2026-09-19-export-subprocess-verifier-correction.md).

Historical handoff, 18 September 2026: **Offline preflight and the separate guarded GPU-only launcher
are implemented and independently reviewed. The completed clean full run passed
artifact preflight; its small proof files and one selected adapter copy are on
the Mac. No full-data GGUF export, inference or live-training-source change has
occurred.** Root staged
and hash-checked the separate export bundle; see `2026-09-18-full-export-launcher.md`.
Live host state must be checked afresh. Code review approves the implementations,
not any specific runtime launch.
Local repository root: `/Users/elijahnelson/Desktop/PROJECTS/Muta`.

Read first: `2026-09-18-muta-300k-finetune-campaign.md`,
`2026-09-18-full-data-promotion-addendum.md`,
`provenance/configs/ROUND2_PROMOTION.md` (current v3 section), and
`provenance/results/FULL_TRAINING_LAUNCH_STATUS.md`.

## Decision: three selected exports, not arbitrary checkpoint exports

| Candidate ID | Exact merge parent | Adapter to export after validation |
|---|---|---|
| `full-best-clean-private-enriched` | Original clean Qwen, tree `ae1baefcdac4c037b545696abffc1bd07824c109572163664333b5a5c0dda892` | Completed full run's `adapter/` |
| `full-best-warm-private-enriched` | Original recovered Muta v1 merged parent, tree `02add79d0a5d451c7b75a986a4d3154bf6a98e23f12d9f913f00036c1909fec8` | Completed full run's `adapter/` |
| `full-best-warm-pilot-continuation` | **Same original Muta v1 parent**, not a pilot-merged model | Completed continuation run's `adapter/` |

The trainer uses `load_best_model_at_end=True`, `metric_for_best_model=eval_loss`,
and `greater_is_better=False`, then saves the reloaded best adapter to `adapter/`.
`adapter_selection.final_adapter_model_sha256` means the saved post-training
**selected** weights; the word `final` in this field does not mean last-step
weights. Last-step weights remain in `checkpoints/checkpoint-4693/`.

Export only the frozen development-selected adapter for each primary candidate.
Retain best and last-step checkpoints on their host. If selected step is 1,174
or 2,347, report both **full run: 300,350 rows / 4,693 steps** and **exported
checkpoint: its actual step/epoch**; do not imply the selected weights completed
the whole epoch. Continuation also retains its earlier 20,000-row/313-step
pilot history, not another 20,000 unique rows.

The continuation adapter contains the trained continuation of the pilot's LoRA
tensors, not a delta to stack on top of a pilot-merged base. Merge it exactly
once into original Muta v1. Do not add the pilot adapter again; do not reapply
Muta v1's older ARC/QASC adapter, already present in the warm parent. The old
published GGUF and unchanged warm pilot GGUF remain untouched controls.

## Export is blocked until these checks have receipts

The existing exporter is **not** an export-admission validator. Use the separate
independently reviewed GPU-only wrapper described in the launcher plan; do not
invoke the exporter CLI below directly. The offline artifact preflight described
later deliberately does not authorize a launch without fresh runtime admission.

| Gate | Required checks and exact evidence |
|---|---|
| Terminal identity | No active trainer or conflicting `RUNNING.json`/`FAILED.json`; `COMPLETED.json.run_name` equals the candidate; its `training_manifest_sha256` equals actual `training-manifest.json` bytes. Preserve failures/history, do not delete them to pass. |
| Frozen treatment | Actual `provenance/configs/full-runs-v3.json` SHA256 is `da828b9146415ca822fecf1961808b914e9666cf7452de34e7704b97f83675da`. Manifest campaign SHA, candidate ID/lineage, all frozen hyperparameters, trainer/helper hashes and actual source snapshot match it. Require `trainer_global_step=planned_steps=4693`, `pilot_rows=null`, train tokenization rows 300350, validation rows 5000, private policy include and exact data/validation fingerprints/manifests. |
| Scheduled selection | `schedule.requested_steps` and scheduled evaluation evidence are exactly 1174/2347/4693. Rehash manifest-bound `metrics.jsonl`, `metrics.csv`, PNG/SVG; verify finite scheduled losses. Read each checkpoint's `trainer_state.json`, root `checkpoints/trainer_state.json`, and histories. Best step must attain the minimum **scheduled** dev loss with Trainer's recorded tie choice, not a later test-selected choice. |
| Selected bytes | `adapter_selection.policy=minimum_eval_loss`, metric name `eval_loss`, correct best step/path/metric. Recompute full `adapter/` inventory and compare names, sizes and hashes with `manifest.adapter`. Its weight/config hashes must equal both selection receipt fields and the actual selected checkpoint's weight/config bytes. Verify safetensors layout, rank/modules/config and required checkpoint state; reject symlinks/path escapes. |
| Parent binding | Observed merge-parent inventory must equal the frozen lineage's base tree **and** manifest `base_lineage.observed` / embedded `receipt.training_base`. Actual lineage-file hash must equal both manifest `base_lineage.receipt_sha256` and frozen authority. A path string or `adapter_config.base_model_name_or_path` is not authority. |
| Initializer/resume | Fresh runs declare no initializer. Continuation static receipt binds pilot tree `4ec07d3668e9a772573c7f6553319760af00fb28cc1c8743a3c8fe5ce97a0aff`, pilot manifest `6ec33e9cbcba01c86d775977a35bf6f791f46ee110d167db1fb46c8815a3cb6c` and original warm parent. Exactly one initialization session binds the exact-copy/no-merge receipt. Version 1 explicitly rejects all own-stage resumes/retries as `unsupported_resume`; legitimate resumed runs need a separately reviewed extension, not deleted history or bypassed checks. |
| Tokenizer | Trainer receipt binds the original clean tokenizer input; saved adapter inventory binds its serialized post-training tokenizer and `chat_template.jinja`. Export with `--tokenizer RUN/adapter`, not an arbitrary warm-parent tokenizer. Verify loaded/saved tokenizer vocabulary, token IDs, template and generation/stop metadata against the approved training serialization; record exact input files and package versions. |
| Export process | Pin exporter/helper snapshot and complete llama.cpp conversion dependency state, not just a directory/tag. Claim a fresh output directory, preserve partial attempts, acquire the existing per-user GPU lock, verify idle GPU under lock, record command/environment/PIDs/logs, and rehash inputs after merge. No automatic retry/overwrite. |

Important scheduled-loss detail: after the final scheduled checkpoint the trainer
calls `evaluate()` again **on the reloaded best model**. Thus metrics can contain
two `eval_loss` entries at step 4693 with different meanings. Use checkpoint
histories/schedule to distinguish them; do not take the last loss at each step
and call that the scheduled loss. The post-training loss must match selected
best loss under the trainer's recorded tolerance (absolute 1e-12).

Preserve the final checkpoint even when it was not selected. The current exporter
rejects passing a checkpoint directory against the root adapter inventory; do
not edit the training manifest to bypass this. A separately requested final-step
GGUF would need a distinct audited checkpoint-selection receipt/export path.
If best equals final, one artifact plus both labels is enough; do not copy it.

## What existing code does and does not prove

### Bounded clean-tokenizer inspection before the GPU becomes free

Use a small one-off script preserved under `provenance/scripts/`, outside both
frozen code snapshots. Pin the real clean preflight receipt; verify its seven
base/saved tokenizer, template and generation/model-config input hashes before
and after inspection. Load only the two local fast tokenizers, with remote code
disabled, offline mode and CUDA/Torch disabled. No model weights, dataset text,
GPU query, inference or training changes are needed. Compare complete token-to-ID
maps, special-token maps, backend tokenizer configuration and chat templates;
exercise a few public synthetic serialization probes including assistant-prefix
alignment. Record source/package identities, model vocabulary bounds and declared
generation stops. Save one exclusive metadata-only result, and have a separate
agent review the script and observed results. This does not replace GGUF metadata,
tokenizer parity or actual stop-behaviour tests after conversion. Do not require
HF `bos_token_id=None` to equal the converter's possible BOS sentinel.

Executed and independently reviewed at 23:00 UTC: all 15 tokenizer-semantic
checks and five fixtures pass. The no-Torch-import control did not hold under
installed Transformers 5.5.0, so the original discrepancy receipt remains
unchanged; `USE_TORCH=0` is not a valid no-import switch in that version.
The separate scoped review records exact source/result hashes, command,
post-exit GPU observation and limitations. See
`provenance/training/full-best-clean-private-enriched/clean-tokenizer-inspection-review.md`.
No GGUF/runtime admission is implied and no dependency-level GPU-query absence
is claimed. Training continued normally.

| Local path / interface | Finding |
|---|---|
| `model-development/finetune/train_lora_round2.py`: `_selected_adapter_receipt`, final `training_manifest`/`COMPLETED` construction | Produces explicit best-checkpoint/config/weight bindings and terminal manifest hash. Final selected adapter inventory includes tokenizer files. |
| `model-development/finetune/run_round2_full_queue.py`: `completed_stage` | Checks fresh-stage terminal, rows/steps, campaign/base/trainer and initializer fields before starting the next Oracle stage. Does **not** rehash adapter/metrics or establish minimum-dev selection; deliberately rejects resumed stages. Not a general export gate. |
| `model-development/finetune/build_round2_promotions.py`: `verify_promotion_smoke_run` | Strong checkpoint/metric/selection checks are useful implementation references, but its 20–100-step smoke contract rejects a 4,693-step full run. Do not weaken it or mislabel a full run as smoke. |
| `model-development/finetune/merge_and_quantize.py`: `verify_inputs` | Checks merge base against the **supplied** lineage and adapter against the **supplied** manifest independently. Missing cross-binding permits an adapter to be paired with the wrong otherwise-valid base/lineage. No terminal, selected-checkpoint, tokenizer, external expected-hash, current-source or GPU-lock gate. `safe_merge=True` checks merge safety, not lineage correctness. |
| Same exporter: `main`, `_git_sha`, `export_commands` | Records current Git commit/converter/binary hashes but does not enforce expected ones or check dirty/dependency state. Uses `device_map="auto"` and may allocate Oracle GPU. Rejects an existing quantization manifest but accepts a pre-existing partial output directory; manifest write is not an atomic completion protocol. |
| `model-development/finetune/test_merge_and_quantize.py` | One test checks F16 conversion / Q4_K_M command flags, not the missing safety/integrity cases. It passed locally during this review; this is not an export smoke. |

Implementation boundary: the new offline preflight and tests are separate from
the unchanged live trainer, launcher, full config, canonical comparisons and
historical pilot export receipts. The separately implemented runtime wrapper and
its exact reviewed source hash are recorded in the launcher plan.

## Pinned pilot-compatible conversion inputs

All eight local `provenance/exports/pilot-*/quantization-manifest.json` receipts
agree on these identities. They are historical evidence, not a fresh remote
verification. The current local exporter hash also matches the pilot receipt.

| Component | Expected identity |
|---|---|
| `merge_and_quantize.py` | `ed215c907a1013b85c1b619f83dc3a3a3f75b193136bff21709e1c80c883e1be` |
| `campaign_io.py` | `ded88829f91109eb6664d3cf177cde7a8c9665cab731204213ab33047b8fe121` |
| llama.cpp Git revision | `60bccc3763395e01b039aa1ddeacc8cc0ea69f70` (historically `/home/ubuntu/llama.cpp-b10175`) |
| `convert_hf_to_gguf.py` | `8f1bed9466221e57e434caa7ee720abe1569deb6bc2fe5a65da950ea66c8e737` |
| `build/bin/llama-quantize` | `fd6dcbb13f2c69c29b7038436fa514721cacedec6839748f776cb3fde12beca1` |

Inspect tracked conversion imports/`gguf-py` state, untracked import shadows,
Python packages and dynamic-library dependencies too. The pilot receipt does
not contain all those environment hashes. Capture current state and disclose
any mismatch as a new conversion-environment deviation; do not claim bitwise
historical reproducibility from the four hashes above. Never silently substitute
the separate CUDA-serving/no-UI checkout for the converter checkout.

Use a new immutable export-code snapshot with these files/dependencies and a
small source manifest. The frozen full-stage config does not pin the exporter.
Do not add files to/change the live training snapshot as an export convenience.

## Conditional executable CLI handoff

**Do not execute now or until all gates above have independently reviewed
receipts.** The commands are the existing CLI contract, not a replacement for
the reviewed export-admission wrapper. Root must confirm all paths/host state.

Known Oracle paths from local launch receipts:

```bash
MUTA_CAMPAIGN=/lambda/nfs/awf-tmp/muta/campaign-20260918
MUTA_EXPORT_PY=/home/ubuntu/muta-finetune/.venv/bin/python
MUTA_LLAMA=/home/ubuntu/llama.cpp-b10175
MUTA_CLEAN_BASE="$MUTA_CAMPAIGN/bases/upstream-qwen25"
MUTA_WARM_BASE=/home/ubuntu/muta-finetune/runs-metric/qwen25-bf16-r16-licensed-mcq-lr2e5-500/merged_16bit
MUTA_CLEAN_LINEAGE="$MUTA_CAMPAIGN/provenance/clean-lineage.json"
MUTA_WARM_LINEAGE="$MUTA_CAMPAIGN/provenance/warm-lineage.json"
```

Set `MUTA_EXPORTER` to the newly staged/pinned `merge_and_quantize.py`; do not
point it at a mutable checkout. Choose **one** mapping per guarded invocation:

| Run | `MUTA_RUN` | `MUTA_BASE` / `MUTA_LINEAGE` | `MUTA_MODEL_NAME` |
|---|---|---|---|
| Clean | `$MUTA_CAMPAIGN/runs/full/full-best-clean-private-enriched` | `$MUTA_CLEAN_BASE` / `$MUTA_CLEAN_LINEAGE` | `Muta-Round2-Full-clean-r16-lr1e5-300350-bestdev` |
| Warm fresh | Completed CSD3 run, or verified direct host-to-host staging path; **not yet resolved here** | Original warm parent / matching warm receipt | `Muta-Round2-Full-warm-fresh-r16-lr5e6-300350-bestdev` |
| Warm continuation | `$MUTA_CAMPAIGN/runs/full/full-best-warm-pilot-continuation` | `$MUTA_WARM_BASE` / `$MUTA_WARM_LINEAGE` | `Muta-Round2-Full-warm-pilot-cont-r16-lr5e6-300350-bestdev` |

Set `MUTA_EXPORT_OUT` to a fresh candidate-specific path under
`$MUTA_CAMPAIGN/exports/full-v3/`. Required guarded child argv:

```bash
env CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  "$MUTA_EXPORT_PY" "$MUTA_EXPORTER" \
  --base "$MUTA_BASE" \
  --base-lineage "$MUTA_LINEAGE" \
  --tokenizer "$MUTA_RUN/adapter" \
  --adapter "$MUTA_RUN/adapter" \
  --training-manifest "$MUTA_RUN/training-manifest.json" \
  --llama-cpp "$MUTA_LLAMA" \
  --output "$MUTA_EXPORT_OUT" \
  --model-name "$MUTA_MODEL_NAME"
```

Do not add `--keep-f16` for routine exports: the existing script records F16
hash/bytes, then removes that intermediate. It retains remote `merged-bf16/`;
keep it for verification unless a later explicit cleanup is authorized.

Oracle GPU scheduling: wait for **both** queued training stages/controller to end;
clean completion alone is not a GPU-export opportunity. The controller immediately
starts continuation and retains `/tmp/muta-round2-full-uid-1000-gpu-0.lock` across
both stages. The export wrapper must use the same nonblocking lock protocol
(`acquire_gpu_lock(0)`), verify idle state (`check_gpu_idle(0)`) after acquiring
it, and retain/inherit the descriptor for the export child. Unknown external
work remains untouched; a lock failure/occupied GPU means defer, not kill/retry.
An optional CPU-only path below can run sooner only after its own gates pass.
CSD3 export or direct staging requires a fresh scheduler/budget/path
check; this plan neither submits a job nor assumes authentication now works.

### Optional CPU-only export while continuation trains

Once the **clean run itself is terminal and validated**, its export could use
the same guarded argv with `CUDA_VISIBLE_DEVICES=''` instead of `0`; this is a
separate scheduling alternative, not something launched by this plan. Do not
acquire/override the busy GPU lock for a CPU-only process or disturb its owner.
Use a separate exclusive CPU-export/output claim to prevent duplicate exports.

Before approving this alternative, verify in the actual pinned environment that
CUDA is unavailable to the child and `device_map="auto"` really places the merge
on CPU (no GPU, unexpected accelerator or silent disk offload). Establish a
measured peak CPU-RAM, thread and scratch-I/O bound from a separate completed
artifact/export smoke, not from GGUF file size. Confirm that headroom remains
after the active trainer, data workers, evaluation and checkpoint-saving peaks;
record the reserve and failure policy. CPU BF16 support/speed and package
compatibility must be observed, not assumed from GPU success.

Use verified host CPU affinity/quota and memory limits for the export process
tree, plus an I/O budget that does not starve checkpoint writes. BLAS/OMP thread
environment variables alone do not prove the quantizer is bounded: it may use
its own thread pool. The wrapper must retain the CPU-only environment for the
converter and quantizer subprocesses and record actual resource telemetry.
If those controls/headroom are not established, defer to the idle-GPU path.
Never OOM the active training job to save export latency. No CPU smoke, resource
measurement, conversion or process launch was performed here.

## Implemented separate offline preflight: independently reviewed

New file:
`model-development/finetune/preflight_full_stage_export.py`, with focused tests
in `test_preflight_full_stage_export.py`. It reads inputs only and writes one
new exclusive metadata receipt. No Torch/PEFT/model loading, network, GPU query,
subprocess execution, conversion, mutable training-source edits or automatic
repair. It supports only the three schema-v3 primary **selected-adapter** exports;
other schemas/final-step exports and own-stage resumes/retries fail closed rather
than using a broad fallback. A fresh continuation stage is supported; resuming
that stage's checkpoint is not supported in this first preflight version.

Existing CLI, with placeholder paths to be resolved on the verified artifact
host. This only audits artifacts and writes a new metadata receipt:

```bash
python preflight_full_stage_export.py \
  --full-config /verified/full-runs-v3.json \
  --expected-full-config-sha256 da828b9146415ca822fecf1961808b914e9666cf7452de34e7704b97f83675da \
  --candidate-id full-best-clean-private-enriched \
  --run-dir /verified/completed/run \
  --training-code /verified/frozen/fullstage-snapshot/model-development/finetune \
  --base /verified/original/training-parent \
  --base-lineage /verified/lineage.json \
  --dataset-manifest /verified/train-manifest.json \
  --validation-manifest /verified/dev-manifest.json \
  --exporter /verified/export-snapshot/merge_and_quantize.py \
  --expected-exporter-sha256 ed215c907a1013b85c1b619f83dc3a3a3f75b193136bff21709e1c80c883e1be \
  --llama-cpp /verified/llama.cpp-b10175 \
  --reference-export-manifest /verified/pilot-warm-r16-lr5e6/quantization-manifest.json \
  --expected-reference-export-manifest-sha256 67077e17743327aacbade27f4c497b6fd214bcf22aa07c99a45e21b5e34edc69 \
  --output /new/selected-export-preflight.json
```

The implementation loads only the SHA-pinned, inspected stdlib `campaign_io.py`
hash/inventory helper, executing the verified bytes. It validates terminal,
config/treatment/signature, all seven frozen training-snapshot source hashes,
scheduled selection, actual adapter/checkpoint bytes, parent and initializer
chains. It uses bounded JSON/header/JSONL reads and caps tree depth, count and
bytes; files are hashed by streaming. It validates exact Qwen rank-16 tensor
names/shapes, dtype and contiguous safetensors layout without model loading.
Every read input and inventory is rehashed at the end. No optimizer pickle or
tensor payload is deserialized, and tensor numerical finiteness is not checked.

Checkpoint epochs are numeric, finite and consistent with step / 4693; root
epoch is 1.0. Selection records stage-specific example exposures under the
frozen batch-64, accumulation-1, world-1, single-epoch contract: step 1174 means
75,136, step 2347 means 150,208, and step 4693 means 300,350. These are not a
claim of unique examples or a sum with continuation's prior 20,000 exposures.

The receipt fixes exporter input arguments, including `--tokenizer RUN/adapter`;
the interpreter, output claim and model name remain runtime responsibilities.
Actual saved tokenizer files are manifest-inventory bound. Loaded vocabulary,
token IDs and template semantics are explicitly pending. Dataset manifests and
fingerprints match frozen authority without reading private shards. Metric JSONL,
CSV and checkpoint histories agree numerically; CSV bytes are reconstructed.
Existing PNG/SVG are hash-bound with basic structure checks only, not recreated
or represented as numerically revalidated plots.

Keep verdicts separate: `artifact_preflight_passed` is not `safe_to_launch` or
`gguf_verified`. Runtime/environment readiness is explicitly pending, including
dirty/import-shadow/dependency checks not provable from the reference receipt
alone. If offline Git state cannot be established without a subprocess, record
that limitation for the reviewed launch wrapper; do not quietly declare it clean.
A later bounded launcher consumes the pinned preflight SHA, revalidates inputs
against it at launch, acquires the appropriate resource/output locks, captures
argv/environment/logs and verifies the output. A preflight file alone must not
authorize stale inputs or bypass a newly occupied GPU.

Current local verification: **50 synthetic tests pass; Ruff clean**. Independent
agent reviewer `full_promotion_audit` returned GO for code SHA256
`79e2cd8b226aac23b64aa398a98a439096579ddd97bb38f1387e7805f1086e57`
and tests SHA256
`0bfdfba3da676c5e1571e2465fb9cdb793e2c5715e642319c68831a80f1b8aac`.
The review found and corrected unchecked checkpoint-epoch fields; malformed
or prose-containing values now fail rather than entering the receipt.
The exact copied live clean resolved-config was inspected for
field/schema compatibility; no incomplete full run was presented as completed,
and no small smoke was relabeled as a full run. Tests cover valid tiny synthetic
clean/fresh-warm/continuation stages, explicit unsupported resume/retry, wrong
otherwise-valid parent, selected step
1174 with a distinct final-step evaluation, exact dev-loss tie, tampered marker/
manifest/weights/config/tokenizer, missing checkpoint, extra scheduled
evaluation, nonfinite loss, invalid/missing/private-prose checkpoint epochs,
initializer double-merge parent, symlink/escaping path, wrong reference/full-config
hash, oversized JSON/metrics/header inputs, mid-scan mutation and refusal to
overwrite a receipt. Test runtime locking/partial-output/converter-failure paths
separately when implementing the launcher. No large checkpoint fixture or
regrading of historical results is needed for these unit tests.

## Completion, delivery and no-duplicate policy

After exporter exit zero, independently rehash the inputs, selected adapter,
merged tree and Q4_K_M; compare actual bytes with `quantization-manifest.json`.
Validate GGUF magic/version/architecture/tensors, quantization and tokenizer/
chat-template metadata. A separate controlled load/stop smoke is still required
before any correctness comparison. An exported file is not a tested winner.

Retain an external export receipt binding terminal/manifest/config/selection,
the gate's source/version and findings, merge argv, interpreter/packages/GPU
admission, full stdout/stderr/exit code, converter dependencies, final artifact
hashes, and the export manifest's hash. Include selected step/epoch and last-step
checkpoint hash separately. The existing manifest records conversion subprocess
argv, not the complete merge invocation or a terminal training receipt.

Small local receipts belong under
`provenance/exports/full-v3/<candidate-id>/`; retain their original byte hashes
and original-host paths plus an explicit relocation map. No private row text.
Only completed verified Q4_K_Ms go once into `models/round2/full-v3/`, with a
single download inventory mapping candidate, selected checkpoint and remote/
local hashes. Before transfer, reuse any exact matching local hash rather than
copying another file under a new name. A mismatching existing path is preserved
for resolution, not overwritten. Do not copy bases, F16, merged BF16 or optimizer
checkpoints to the Mac. Preserve existing eight pilot GGUFs and their download
receipt `provenance/exports/round2-pilot-mac-downloads.json` unchanged.

Remaining runtime-implementation tests: converter/dependency drift, occupied
GPU/retained child lock, CPU-only placement/resource controls, partial output
directory and failed/partial conversion. Authenticated own-stage resume support
requires its own later scope/review; it is not an implied capability of version 1.
