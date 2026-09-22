# Guarded full-stage export launcher

18 September 2026. GPU-only implementation and 44 focused tests are complete;
independent code review passed for the exact source below. Root staged the
separate export bundle on Oracle and checked every hash. No real export, model
load or live-training-source modification was performed. Read
`2026-09-18-full-stage-export-handoff.md` and
`provenance/results/FULL_TRAINING_LAUNCH_STATUS.md` first.

## Scope and hard boundary

Added only `model-development/finetune/launch_full_stage_export.py` and focused
`test_launch_full_stage_export.py`. Keep the frozen trainer/config/queue,
reviewed offline preflight and exporter unchanged. Support one fresh selected
export for one of the three existing v3 candidates per invocation; no resume,
retry, checkpoint choice override, deletion or replacement of old output.

Use the reviewed offline preflight source SHA256
`79e2cd8b226aac23b64aa398a98a439096579ddd97bb38f1387e7805f1086e57`
and exporter SHA256
`ed215c907a1013b85c1b619f83dc3a3a3f75b193136bff21709e1c80c883e1be`.
Reuse only explicitly SHA-bound inspected pure functions; never import the
training queue merely to obtain its lock functions, because that brings in a
larger mutable import graph. Reproduce its short stable-lock protocol with a
compatibility test instead.

Version 1 is **GPU-only**. `--mode cpu` fails `unsupported_cpu` before any
process is created. A capacity snapshot, an artifact receipt or a user-supplied
boolean is not proof of CPU placement/resource isolation. Root is separately
investigating CPU-only feasibility; any support requires another reviewed scope.

## Intended CLI

```bash
python launch_full_stage_export.py \
  --preflight-receipt /verified/selected-export-preflight.json \
  --expected-preflight-sha256 ACTUAL_RECEIPT_SHA256 \
  --runtime-admission /verified/export-runtime-admission.json \
  --expected-runtime-admission-sha256 ACTUAL_ADMISSION_SHA256 \
  --python /verified/environment/bin/python \
  --mode gpu --gpu 0 \
  --output /new/candidate-export \
  --max-seconds 7200
```

The artifact receipt determines all source/base/adapter/tokenizer/manifests and
frozen identities; the launcher must not accept competing path overrides.
Model names are fixed by candidate ID. A separately SHA-bound runtime admission
must describe the actual host/UID, interpreter, exact conversion checkout and
dependency evidence. It is not generated opportunistically by this launcher.
The minimal admission schema is version 1, kind
`muta_full_export_runtime_admission`, with `mode="gpu"`, candidate ID,
`preflight_sha256`, host/UID/GPU and an expiry Unix timestamp. `python` binds the
logical executable path, resolved executable path, bytes and SHA256. `commands`
contains absolute hashed `git` and `nvidia_smi` paths. `dependency_files` contains
bounded absolute path/bytes/SHA256 entries covering the enumerated Python import
origins, conversion dependencies and resolved quantizer native libraries.
`llama_cpp` binds its root, pinned commit and exact clean tracked/untracked
status. `quantizer_native_libraries` is a list of `{path, resolved_path}` mappings
from observed `ldd` evidence; each resolved file appears in `dependency_files`,
and each live logical path must still resolve to it. `python_probe` records the
launcher's fixed stdlib-only probe results
(version, executable, package versions, distributions and import paths/origins).
`python_probe_source_sha256` is SHA256 of the exact module `PROBE` string.
The probe checks torch, peft, transformers, accelerate, numpy, safetensors,
huggingface-hub, sentencepiece and tokenizers distributions and import origins,
plus local gguf's origin. It does not import ML libraries, so ephemeral paths
created by torch imports are not pinned. `coverage` has
`kind="enumerated_files_and_live_import_probe_not_hermetic"` and
`all_transitive_dependencies_hashed=false`. The external
expected admission SHA is mandatory; a self-authored unpinned file is rejected.

Root approved this narrower measured-evidence contract: it is **not hermetic**,
does not hash all installed Python/stdlib/CUDA files, and does not claim bitwise
historical environment reproduction. The exact enumerated hashes, current Git
state and live import/package probe are rechecked, not trusted as static flags.

## Execution contract

1. Validate arguments, expected hashes, fixed candidate, artifact status and
   all input paths before spawning any export. Require external preflight and
   admission byte hashes, not only self-reported hashes. Reject CPU mode.
2. Acquire exactly `/tmp/muta-round2-full-uid-UID-gpu-GPU.lock` with nonblocking
   exclusive `flock`, `O_NOFOLLOW`, regular-file/owner checks. Never unlink or
   explicitly unlock the shared descriptor. A lock owner or busy device means
   refusal; preserve all existing work.
3. While holding that lock, validate runtime identities and query the selected
   GPU for compute processes; fail closed on query failure or any process.
   Rerun the exact SHA-bound offline preflight and compare its complete stable
   artifact receipt with the externally pinned receipt. Recheck immediately
   before the child so a long hashing pass cannot treat an old idle query as
   admission. This does not prevent unrelated software ignoring advisory locks.
4. Atomically claim a fresh output directory under an existing safe parent;
   never reuse a partial/completed path. Keep launch evidence and partial export
   bytes together. Do not write into any verified input/source tree.
5. Record launcher/source/toolchain/admission identities, full child argv, safe
   explicit environment, host, PID, timestamp and selection/exposure identity.
   Scrub credential-bearing and import-preload variables. Set offline Hugging
   Face/Transformers flags, disable user-site/Python bytecode, fix the chosen
   GPU. No broad environment dump and no model/data copies.
6. Start one child in a new session with stdout/stderr files and inherited lock
   descriptor. Keep a live PID receipt. Preserve running child and its inherited
   lock if the controller is interrupted or times out; never silently kill,
   retry or call a running child completed. Record this state separately from
   a child that has actually exited nonzero. Successful direct descendant starts
   record their actual PID and argv. Failures retain known descendant PIDs and
   mark descendant liveness unassessed when not checked; an exited exporter does
   not imply its converter exited.
7. On exit, record return code/log hashes. Zero alone is insufficient: rerun
   artifact checks and runtime identity checks, verify exporter manifest paths,
   original input identities, pinned tool hashes, exact recorded converter
   commands, merged tree and final Q4_K_M size/hash/header. Keep immutable
   completion/failure receipts. Do not claim loaded-tokenizer equivalence,
   GGUF correctness, winner quality or target-CPU qualification from byte checks.

## Required focused tests

Use tiny synthetic files/fake processes; no real model, export or network.

- Three fixed candidates and fixed selected-adapter input mapping.
- Wrong external receipt/source/toolchain/admission hashes; missing/unsupported
  schema and CPU mode fail before spawn.
- Shared GPU lock contention, idle-query failure/busy state and same-output race
  preserve existing work. A real short child fixture proves lock retention after
  its controller descriptor closes; no GPU access is involved.
- Changed input during preflight and stale runtime identity prevent launch.
- Sanitized offline environment, exact argv, safe cwd and inherited descriptor.
- Success requires terminal exporter receipt and exact outputs; partial output,
  nonzero exit, missing/tampered GGUF or wrong merge parent fails without retry.
- Timeout/interruption preserves child PID/lock/partial output with no success
  marker. Existing directories and receipts are never overwritten.
- Symlink/path escape and bounded malformed/oversized receipt inputs.

## Coverage limitations and local verification

The runtime admission must make its coverage honest: pinned converter and
quantizer bytes alone do not pin all dependencies. Root supplies explicit
enumerated dependency evidence; the launcher verifies it with the fixed live
package/import probe and clean Git checks. This does not prove no unenumerated
transitive library can change. Missing required origins/native entries or live
probe drift fail closed; no fully reproduced historical environment claim.

The existing exporter does not retain the GPU descriptor into converter children
by default. The implemented stdlib bootstrap executes exact hash-bound exporter/
helper bytes and propagates the descriptor into its direct subprocesses
(Git/converter/quantizer), recording successful child PID/argv. A real short
Python fixture proves the lock remains held after the controller descriptor is
closed and the exporter is terminated while its child continues. This did not
run a model, GPU command, converter or export. It does not promise preservation
through arbitrary uninspected descendant programs that deliberately close FDs.

The output's `COMPLETED.json` binds launch/start/exit/artifact receipts, logs,
runtime-admission SHA and export output hashes. It says `inference_tested=false`:
the final GGUF check is SHA/size/basic version-3 header only, not a tensor parser,
loaded-tokenizer equivalence or model-quality test. Safe fixed failure codes
are retained; arbitrary exception prose/environment credentials are not dumped.

Local verification: 44 focused launcher tests pass; combined launcher/preflight/
existing exporter/trainer/queue suite passes 155 tests. Ruff and formatting checks
pass. No real runtime admission or completed full-stage export was consumed in
this implementation task. The tests use tiny synthetic artifacts; no frozen
source or historical output was edited to make them pass.

Independent reviewer `/root/full_promotion_audit` reconfirmed the final launcher
SHA256 `16f10222dab4be4facc7e04e6f6a6215d6d0d17d312887a4308445a85df9abb0`
and tests SHA256 `951dd680146b7081d3b1d61ae9119f62ffabb2e7dac99f5a9311834f9101b5e1`.
Root's expanded regression run passed 343 tests. The separate Oracle source
bundle is `code/full-export-v1-20260918T2203` under the campaign root; its
`source-inventory.json` SHA256 is
`e224bed8fff012fe3ff651fbb8ef2da86086e374ff87281eaee856aa02b454da`.
The local identical inventory is under `provenance/hosts/oracle/` in that named
directory. Source staging/review does not replace live runtime admission or a
real completed-run preflight. Do not invoke this on a busy GPU.
