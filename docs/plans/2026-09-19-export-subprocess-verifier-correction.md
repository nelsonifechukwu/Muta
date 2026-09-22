# Correct export subprocess verification, preserve the first attempt

The clean full-stage exporter exited zero and produced its GGUF at 00:19 UTC.
The v1 controller then failed with `child_invocation_bound`: its bootstrap
records all direct Popen calls, including Torch import-time CPU discovery and
compiler-pool startup, but its verifier assumes only Git/converter/quantizer.
All five recorded direct PIDs and the exporter/controller were absent at
00:20:19; GPU idle was observed. That does not prove historical transitive-child
exit statuses. Original FAILED.json and all output bytes must remain unchanged.

## Bounded implementation

1. Review actual installed source for the observed `lscpu` and Torch compile
   worker calls. Preserve small source/hash receipts separately. Do not claim
   their current bytes were individually authenticated before the first export.
2. Correct the mutable local launcher with a strict, externally hash-bound
   auxiliary-process profile; the remote frozen v1 bundle remains unchanged.
   Admit the original three-call pattern or the exact reviewed five-call pattern
   only. Check ordered argv/types, parent/unique positive PIDs/common lock FD,
   exact interpreter/worker/pickler/kind/count and distinct bounded pipe FDs.
   Future launches must verify added executable/source identities before spawn.
   Do not weaken the remaining artifact/runtime/result checks.
3. Add a narrowly scoped read-only reconciliation CLI for the existing attempt.
   Bind original launch/start/exit/failure/invocation/admission/preflight/manifest
   hashes externally; require the exact verifier defect and child exit zero.
   Acquire the existing nonblocking GPU lock, observe current idle/process state,
   rerun artifact preflight/runtime and all corrected result checks, then write
   one exclusive external reconciliation receipt. Never alter the export tree,
   relaunch its exporter or create a retroactive COMPLETED.json.
4. Independent review and focused negative tests must pass. Stage a new v2
   snapshot only afterward, with exact source hashes. The next continuation
   export is a new first attempt, not a retry of the preserved clean attempt.
5. After successful reconciliation, continue GGUF metadata/load/stop tests,
   matched regression suites and single-copy Mac delivery. Byte verification
   does not prove semantic quality or target-CPU qualification.

## Tests / scope

Test exact actual five-call acceptance; unknown sixth/duplicate/reordered calls;
wrong flags/source/parent/FDs/PIDs; duplicate JSON keys; changed GGUF/tree/logs;
nonzero child exit; immutable original failure; outside-tree exclusive receipt;
lock contention; runtime identity drift. Reuse reviewed functions, not a new
export engine. No training configuration/source, private data, model weights,
canonical comparison or existing frozen evidence may be edited to pass checks.

Root and two independent agents diagnosed the mismatch. The new review must
distinguish current metadata measurements from missing historical dependency
coverage; do not retroactively claim a hermetic first export.

## Reviewed implementation

Root and independent reviewer passed 175 launcher/reconciliation/preflight/
collector tests; Ruff passed. Final reviewed launcher SHA256 is
`44be7b159af96d12c99005cc0fe3ab829556070b8352369c83b77c780ef108cd`;
reconciler SHA256 is
`72bcab5162d5316579e615ea1e39dd3876ff06cfcac55e9344b1b908aeb9ac87`.
The unique hash-bound original preflight source is loaded from the already
externally pinned receipt, so a new v2 code directory preserves all original
gate/exporter paths and requires no changes/additions to frozen v1. A dedicated
new-directory/wrong-sibling regression guards this previously caught staging bug.

The unchanged collector still binds v1; its tests use the one preserved original
v1 launcher proof copy instead of silently repinning production to v2. Actual
auxiliary profile SHA256 is
`c068eb257c66adb87ae72757fcae3a5cff945c484dbde23ca2357b02677cc221`;
clean attempt authority SHA256 is
`cff0df3b72b066b6c00d11423cce8b69eb49b9593e18c706d7d1a3d14548e21c`.
These bind current source observations and the ten original small evidence
files plus original admission respectively. At that pre-execution review,
reconciliation still needed to run the actual checks; source review alone did
not clear the export.

## Executed outcome, 2026-09-19 00:49 UTC update

The actual clean reconciliation passed. Its separate
[receipt](../../provenance/exports/full-v3/clean-reconciliation-v1.json) has SHA256
`134ba5d1a206c4348a9964494d88e41fd8fcc89faead7fbdf8a13c1231da9964`
and status `export_artifacts_verified_after_controller_verifier_defect`.
It records `original_attempt_modified=false`, `reexported=false` and
`inference_tested=false`. The original `clean-bestdev-v1/FAILED.json` remains
unchanged at SHA256
`b60b9b0fa1fde94ba62450b8f787e884eadbbebe18c5c26c482e6b3ab223ef51`;
no retroactive v1 `COMPLETED.json` was created.

The reconciled clean Q4_K_M is 986,047,968 bytes, SHA256
`720fcc69f1ec1b83d601d7406756e44b0ae96b96ba626b97d5fb5ac874108530`.
One Mac delivery copy has been independently rehashed. The continuation's
separate first export subsequently completed and was delivered once, with SHA256
`426640b0f4089d63ba8328c6d7fd2b201aeb7e92dd552492f1be594d9f385352`
and the same byte count. Historical auxiliary/transitive process and non-hermetic
runtime limitations remain disclosed; successful reconciliation does not
authenticate previously unmeasured historical bytes. Neither export has received
GGUF inference/quality qualification yet.
