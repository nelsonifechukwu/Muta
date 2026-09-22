# Four available GGUFs: matched known-suite evaluation

Prepared locally on 19 September; **not executed by this author**. Root reports
the clean and pilot-continuation exports complete. The clean attempt retains
its original controller failure plus a separate successful reconciliation.
The third requested full run (warm-fresh) is not silently substituted or counted
as evaluated here. Add it later only through a new frozen manifest/run.

## Scope and immutable inputs

Use `provenance/evaluation/full-four-gguf-20260919/candidate-manifest.json`.
Its frozen byte SHA256 is
`43e613dca9506e9014c190d91afaca14c19dcffaba5e26d7d3328b604cc4cfb7`.
The unchanged incumbent and unchanged warm-r16-lr5e6 pilot come directly from
the canonical nine-model manifest (SHA256
`07d98cedb2f4d0d8be5aea374844b8c7a2738cd180919eb3bb6e05c61d36cf6e`).
The new clean and continuation model hashes are root-observed export identities,
not measurements made remotely by this author. Both selected adapters are
checkpoint 4693, selected by minimum development loss; each full stage processed
300,350 rows. Continuation additionally retains its prior 20,000-row pilot
history; that is **not 320,350 distinct training rows**.

Frozen Oracle source root:
`/lambda/nfs/awf-tmp/muta/campaign-20260918/code/fullstage-v3-20260918T2035`.
No edits to that snapshot, evaluator, prompt definitions, graders or old results.
The old export-handoff opening status is historical, not current export status.

| Order | Stage | Prompts/model | Total responses | Additional gate |
|---|---|---:|---:|---|
| 1 | Normal-stop smoke, STEM M01/M02 | 2 | 8 | Nonempty; stop, not length; 0 < tokens < 1024 |
| 2 | Duplicate judges automated_01/human_04 | 2 | 8 | Identical answer/reasoning/finish/token-count signatures |
| 3 | Full known judges | 10 | 40 | Complete raw outputs; provisional rubric, not authoritative judging |
| 4 | Full known STEM | 100 | 400 | Preserve MC scores, ungraded written responses, errors and truncation counts |

Each stage uses the same four candidates in the same order, embedded model chat
template, greedy decoding, seed 3407, maximum 1024 generated tokens, context 4096,
2 server threads, GPU layers 99, no prompt cache, one server at a time.
Smoke responses are diagnostic, not additional independent test items.
The judges have 10 positions but 9 distinct texts. Existing known suites are
regression/reference tests; the independent 2,000-item winner battery is not
ready. Concurrent GPU throughput is not target-CPU speed/RSS qualification.

## Orchestration boundary

This is a shell execution handoff, not a new inference framework. Root must
review and stage the manifest, verify the identities below on the actual host,
and choose one fresh output root. Existing healthy work must never be killed or
duplicated. Stop on the first failure; no automatic retries or appended outputs.

Hold the **same nonblocking external flock for the entire sequence**:
`/tmp/muta-round2-full-uid-1000-gpu-0.lock`. Check its regular-file/UID/symlink
identity before use; never unlink it or explicitly unlock another process's FD.
Under the lock, check the selected GPU has no compute processes and that all
four candidate ports 18180–18183 are free. Recheck idle/ports before each stage.
Do not infer admission from an earlier observation or from an evaluator exit.

The shell-held lock remains held while its evaluator runs normally. This alone
does **not** promise descendant retention if both shell and evaluator die while
an orphan llama-server survives: the evaluator uses Popen's default close_fds.
If interrupted, preserve all outputs, inspect recorded processes and GPU state,
and refuse further runs while any healthy server/training/export work remains.
A descendant-retaining bootstrap would need separate review; do not claim the
export launcher's stronger bootstrap guarantees for these plain module commands.

The evaluator itself verifies model/server hashes, requires fresh stage output
directories, captures raw HTTP bodies and verifies real full GPU offload. It
does not acquire this external lock or reject a length-truncated response merely
because a stage has `COMPLETED.json`. Keep all new orchestration/inspection
sidecars outside its sealed stage directories.

## Pinned code and runtime

Verify these files inside the frozen source root before starting, and afterward.
An unchanged SHA is the authority; do not invent a clean Git claim for a copied
snapshot whose surrounding repository has changed.

| Relative file | SHA256 |
|---|---|
| bench/round2_candidate_eval.py | 6732dafdcf38901637b60fe2dcdd49904056aa7e68c6afe62d3349e6dfe84847 |
| bench/judges_prompt_report.py | b063d8c4f54a23a9e2421eeb4254bece5553427ded4fa6be2dea305182010216 |
| bench/judges_prompt_suite.py | 2b6a50269c59e458667c96ed0c5662b5a8a748c1e05ea29a9dfd8f9f27edceab |
| bench/run_stem_prompt_suite.py | f5f4cafca09e06a0c2f8c50ccdad20308a2b879ed6ba0e1ff00d8f24e2f38289 |
| bench/stem_prompt_suite.py | 9d40d48c0ce2a2484fde45dfc75fa550123d7a70f7edef5c2c7978c21ecfe4a2 |
| bench/__init__.py | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |

Use `/home/ubuntu/muta-finetune/.venv/bin/python` and the existing CUDA server
from the manifest (SHA256
`f6d78a9c69583aa8caeec785e59463bfd2783a3008291ef9fab643c8c63cb0b7`).
Verify the existing CUDA runtime gate/dependency/tree receipts listed in the
canonical manifest and their actual files afresh. Do not rebuild or substitute
the CPU server or the exporter checkout's tools. Root separately reviews actual
GGUF metadata and generation-stop semantics before treating runtime smoke as
passed; scalar/template parity does not prove complete tokenizer-vocabulary parity.

## Stage commands (only inside the admitted, lock-held shell)

Set `EVAL_CODE` to the exact source root above, `EVAL_PY` to the verified venv
interpreter, `EVAL_MANIFEST` to the staged hash-verified new manifest and
`EVAL_ROOT` to the exclusively created fresh comparison parent. Use a sanitized
offline environment (no inherited PYTHONPATH/credentials/preload variables;
CUDA_VISIBLE_DEVICES=0; HF_HUB_OFFLINE=1; TRANSFORMERS_OFFLINE=1; -B). Running
from the frozen source root makes its `bench` package authoritative.

```bash
cd "$EVAL_CODE"
"$EVAL_PY" -B -m bench.round2_candidate_eval \
  --candidates "$EVAL_MANIFEST" --output "$EVAL_ROOT/normal-stop-smoke" \
  --suite stem --prompt-id M01 --prompt-id M02 \
  --max-new-tokens 1024 --context-size 4096 --threads 2 --gpu-layers 99 --port 18180
```

Before continuing, root must verify stage completion and its sealed inventory,
then all 8 response rows: exact candidate/prompt pairs; nonempty `answer`;
`finish_reason == "stop"`; integer `generated_tokens` in 1–1023. Rehash each
referenced raw HTTP body and inspect startup/EOG/offload logs. A nonzero exit,
missing row, length/unknown stop or empty answer stops the sequence. Record this
gate outside the sealed smoke directory; never edit responses to make it pass.

```bash
"$EVAL_PY" -B -m bench.round2_candidate_eval \
  --candidates "$EVAL_MANIFEST" --output "$EVAL_ROOT/duplicate-integrity-smoke" \
  --suite judges --prompt-id automated_01 --prompt-id human_04 \
  --max-new-tokens 1024 --context-size 4096 --threads 2 --gpu-layers 99 --port 18180
```

Require eight complete nonempty responses, matching raw-output hashes and equal
`(answer, reasoning_content, finish_reason, generated_tokens)` for each model's
pair. The evaluator already enforces the duplicate signature. Raw HTTP bodies
need not be byte-identical because response IDs/timings differ. Report any length
termination here honestly; this is separate from the short normal-stop gate.

```bash
"$EVAL_PY" -B -m bench.round2_candidate_eval \
  --candidates "$EVAL_MANIFEST" --output "$EVAL_ROOT/judges" --suite judges \
  --max-new-tokens 1024 --context-size 4096 --threads 2 --gpu-layers 99 --port 18180

"$EVAL_PY" -B -m bench.round2_candidate_eval \
  --candidates "$EVAL_MANIFEST" --output "$EVAL_ROOT/stem" --suite stem \
  --max-new-tokens 1024 --context-size 4096 --threads 2 --gpu-layers 99 --port 18180
```

Run sequentially with shell `set -euo pipefail`; do not start STEM if judges
failed. Preserve separate shell argv/environment/exit and stage-gate receipts.
Record exact manifest and source-file hashes in the launch sidecar. Full-suite
prompt hashes must match canonical judges
`da2559db0f1e81a6f0d2010c17a96bb94268ee874e8030ff5f8cd11465f7b07a`
and STEM `34fa618d153470ea9094e846b24dd621beb24e5a9591888617c47dd9fb850d2c`.
For each completed suite preserve `run.json`, prompts/manifest snapshots,
identities, raw bodies, response JSONL, server/runtime logs, summaries, artifact
inventory and terminal checksums. Rehash models/server/code after the sequence.
Do not mix outputs from the older raw-completion STEM runner with this comparison.

## Local verification / independent review

Local pure-parser checks passed: four unique IDs/model hashes, exact raw control
identity/label equality, stage prompt counts 2/2/10/100 and both canonical full
prompt hashes. No model, server or runtime receipt was loaded. Absolute Oracle
paths remain literal in the JSON; do not resave a Mac-resolved manifest (macOS
resolves `/home` differently). All 18 frozen evaluator unit tests passed.

Independent reviewer `/root/full_promotion_audit` approved the bounded manifest
and manual lock-held runbook on 19 September 2026. The manifest SHA256 remains
`43e613dca9506e9014c190d91afaca14c19dcffaba5e26d7d3328b604cc4cfb7`;
the unchanged evaluator SHA256 remains
`6732dafdcf38901637b60fe2dcdd49904056aa7e68c6afe62d3349e6dfe84847`.
Review covers identities, matched settings/prompt ordering, preservation and
stated orchestration limitations. It does not grade the written STEM responses
or establish a model-quality winner. This document does not assert current GPU admission,
completed inference, final model ranking, target-CPU qualification or readiness
of the independent winner battery.
