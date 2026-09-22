# Five-model matched known-suite evaluation — conditional plan

Documentation only: **no manifest, inference, admission or result was created**.
Fresh-warm training is not declared complete here. Follow the
[fresh-warm export gates](2026-09-19-warm-fresh-export-addendum.md) first.
Keep the [four-model manifest and sealed smokes](2026-09-19-full-four-gguf-evaluation.md)
unchanged; its manifest SHA256 is
`43e613dca9506e9014c190d91afaca14c19dcffaba5e26d7d3328b604cc4cfb7`.
Use a new frozen five-model manifest and exclusively new evaluation directories
only after all five real GGUF identities are verified. Never write an executable
manifest containing `UNKNOWN`, a guessed hash, or a placeholder digest.

## Frozen roster and artifact mapping

Keep the first four models in their existing order; append fresh-warm fifth.
The four known hashes are existing receipt facts, not fresh remote measurements
by this document. Rehash actual files before and after execution.

| Order / exact candidate ID | Model SHA256 | Exact Oracle path (fresh-warm path conditional on successful planned export) |
|---|---|---|
| 1 `incumbent-muta` | `a750d00d458c6ab38925364ea1413db00648449180941e47025736d09922e1eb` | `/home/ubuntu/muta-finetune/runs-metric/qwen25-bf16-r16-licensed-mcq-lr2e5-500/gguf_gguf/Qwen2.5-1.5B-Instruct.Q4_K_M.gguf` |
| 2 `pilot-warm-r16-lr5e6-q4km` | `ebb09067e78692168d4ee328498faebb2b662966c24c8f23d944b48a905ac62c` | `/lambda/nfs/awf-tmp/muta/campaign-20260918/exports/pilot-warm-r16-lr5e6/Muta-Round2-Pilot-warm-r16-lr5e6-20k-Q4_K_M.gguf` |
| 3 `full-best-clean-private-enriched-q4km` | `720fcc69f1ec1b83d601d7406756e44b0ae96b96ba626b97d5fb5ac874108530` | `/lambda/nfs/awf-tmp/muta/campaign-20260918/exports/full-v3/clean-bestdev-v1/Muta-Round2-Full-clean-r16-lr1e5-300350-bestdev-Q4_K_M.gguf` |
| 4 `full-best-warm-pilot-continuation-q4km` | `426640b0f4089d63ba8328c6d7fd2b201aeb7e92dd552492f1be594d9f385352` | `/lambda/nfs/awf-tmp/muta/campaign-20260918/exports/full-v3/continuation-bestdev-v1/Muta-Round2-Full-warm-pilot-cont-r16-lr5e6-300350-bestdev-Q4_K_M.gguf` |
| 5 `full-best-warm-private-enriched-q4km` | **UNKNOWN until verified export** | `/lambda/nfs/awf-tmp/muta/campaign-20260918/exports/full-v3/warm-fresh-bestdev-v1/Muta-Round2-Full-warm-fresh-r16-lr5e6-300350-bestdev-Q4_K_M.gguf` |

All use backend `gguf` and server
`/lambda/nfs/awf-tmp/muta/campaign-20260918/runtime/llama.cpp-b10175-cuda-sm80-no-ui/bin/llama-server`,
SHA256 `f6d78a9c69583aa8caeec785e59463bfd2783a3008291ef9fab643c8c63cb0b7`.
For a later manifest, retain the four original identity/label fields exactly;
attach fresh-warm's actual training/selection/preflight/export receipt hashes.
Do not assume fresh-warm selected step 4693. Clean and continuation selected
4693; each completed full stage processed 300350 rows. Continuation retains
prior 20000-row pilot exposure, not 320350 distinct examples. Fresh-warm adds
no pilot exposure, and its cancelled unallocated CSD3 submission adds no training.

## Admission and lifecycle

Wait for actual training and export completion, independent artifact review and
fresh-warm GGUF metadata/load readiness. No current healthy process is interrupted
to make room. Root must verify that all recorded training/export supervisors,
launchers and children exited; examine process/GPU state for surviving descendants.

Create one new persistent sanitized shell/controller and hold the same existing
nonblocking shared flock `/tmp/muta-round2-full-uid-1000-gpu-0.lock` for the entire
sequence. The four-model evaluation shell (PID 166103/session 6530) is closed;
never reuse its PID/FD receipt as current ownership evidence. Verify
existing regular-file/UID/symlink and opened-inode identity; never unlink it or
close another owner's FD. Under the lock, require a successful bounded GPU query
with no compute processes and free ports **18180–18184** (five candidates).
Recheck immediately before every stage. A busy/query-failed state means defer,
not kill, force-unlock, share the GPU or launch elsewhere automatically.

Record shell PID/FD, evaluator PID, argv, safe environment, stage gates and exit
status outside sealed stage directories. Preserve healthy work and all failures;
no automatic retry or appending. The unchanged evaluator starts its own server
process group and normally stops that group on context exit. It uses default
`close_fds`, so the external shell lock does **not** promise retention by an
orphan server after controller/evaluator death. Before resuming any work after
interruption, reconcile recorded PIDs, GPU use and ports; never infer idle from
an evaluator exit alone. A timeout is not authorization to kill other work.

## Exact existing code/runtime authority

Inherit the six source SHA256 entries and runtime-gate identity from the
four-model plan's **Pinned code and runtime** section (document SHA256
`093c947d93adced001f745045884f1bfd0d6640fa693b870680980e46ce9c3e1`).
In particular the unchanged evaluator is
`6732dafdcf38901637b60fe2dcdd49904056aa7e68c6afe62d3349e6dfe84847`.
Frozen source root is
`/lambda/nfs/awf-tmp/muta/campaign-20260918/code/fullstage-v3-20260918T2035`;
interpreter is `/home/ubuntu/muta-finetune/.venv/bin/python`.
Recheck source/interpreter/package identities, server and runtime gate/dependency/
tree receipts **against actual files** before/after, not only receipt hashes.
The evaluator does not itself validate all external runtime sidecars. Preserve
startup/EOG/full-offload evidence; scalar/template metadata is not complete
vocabulary parity. Never substitute mutable source or invent a clean Git claim.

## Sequential stages and executable CLI templates

Before running, root supplies the newly reviewed manifest and its externally
recorded actual SHA, and claims a new parent output path. `EVAL5_MANIFEST` and
`EVAL5_ROOT` below are future paths, not existing admitted artifacts. Use
`set -euo pipefail` in the persistent lock-held shell, offline sanitized environment
without credentials/PYTHONPATH/preload variables, `CUDA_VISIBLE_DEVICES=0`,
`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, and `-B`. Set `EVAL5_CODE` to the
frozen source root above, `EVAL5_PY` to the stated interpreter, and
`EVAL5_CAMPAIGN=/lambda/nfs/awf-tmp/muta/campaign-20260918`.

| Order | Stage | Responses/model | Total | Gate before next stage |
|---|---|---:|---:|---|
| 1 | STEM M01/M02 normal-stop smoke | 2 | 10 | All nonempty, `stop`, integer tokens 1–1023 |
| 2 | Judges automated_01/human_04 duplicate smoke | 2 | 10 | Per-model generation signatures exactly equal |
| 3 | Full known judges | 10 | 50 | Complete sealed outputs and duplicate integrity |
| 4 | Full known STEM | 100 | 500 | Complete sealed outputs; preserve caps/errors |

The full known-suite comparison has 550 responses; 20 additional smoke responses
are diagnostics, not extra independent evidence. Judges have ten positions but
nine distinct texts. Full STEM contains 50 MC and 50 written prompts per model.

```bash
cd "$EVAL5_CODE"
"$EVAL5_PY" -B -m bench.round2_candidate_eval \
  --candidates "$EVAL5_MANIFEST" --output "$EVAL5_ROOT/normal-stop-smoke" \
  --suite stem --prompt-id M01 --prompt-id M02 \
  --max-new-tokens 1024 --context-size 4096 --threads 2 --gpu-layers 99 --port 18180
```

Require exact ten candidate/prompt pairs and nonempty normal-stop responses,
terminal/inventory hashes, raw bodies resolved **relative to each candidate
directory**, and startup/full-offload proofs. Stop on any missing/empty/length/
unknown-stop response. Earlier four-model smoke success does not waive this gate.

```bash
"$EVAL5_PY" -B -m bench.round2_candidate_eval \
  --candidates "$EVAL5_MANIFEST" --output "$EVAL5_ROOT/duplicate-integrity-smoke" \
  --suite judges --prompt-id automated_01 --prompt-id human_04 \
  --max-new-tokens 1024 --context-size 4096 --threads 2 --gpu-layers 99 --port 18180
```

Require ten complete nonempty rows; compare each model's exact
`(answer, reasoning_content, finish_reason, generated_tokens)` pair. HTTP IDs and
timing can differ, so do not require raw-body byte equality. Retain cap counts;
this duplicate gate is distinct from the short normal-stop gate.

```bash
"$EVAL5_PY" -B -m bench.round2_candidate_eval \
  --candidates "$EVAL5_MANIFEST" --output "$EVAL5_ROOT/judges" --suite judges \
  --max-new-tokens 1024 --context-size 4096 --threads 2 --gpu-layers 99 --port 18180

"$EVAL5_PY" -B -m bench.round2_candidate_eval \
  --candidates "$EVAL5_MANIFEST" --output "$EVAL5_ROOT/stem" --suite stem \
  --max-new-tokens 1024 --context-size 4096 --threads 2 --gpu-layers 99 --port 18180
```

Do not start STEM after a failed judges stage. Each stage uses all five candidates
in the same order, one server at a time, embedded model chat template, greedy
temperature 0/top-p 1, seed 3407, thinking disabled, no prompt cache, 1024-token
cap, 4096 context and two server threads. Keep all raw outputs, manifest/prompt
snapshots, identities, logs, runtime observations, summaries, inventories and
terminal checksums; keep orchestration/manual review outside sealed trees.
Full prompt-set SHA256 must remain judges
`da2559db0f1e81a6f0d2010c17a96bb94268ee874e8030ff5f8cd11465f7b07a`
and STEM `34fa618d153470ea9094e846b24dd621beb24e5a9591888617c47dd9fb850d2c`.
A completed evaluator stage can still contain truncations: report them, never
silently retry only a favored model or increase only its token budget.

## Frozen manual review, not post-result criteria

Reuse these exact pilot review authorities before seeing new responses:

| Authority | SHA256 |
|---|---|
| `docs/plans/2026-09-18-pilot-comparison-review-protocol.md` | `4869c977f857853e0d6db885750eb6d3f0e9a4ba8f3232989a372f6542523eed` |
| `provenance/evaluation/all-gguf-20260918/math-written-rubric-v1.json` | `82750faf766705aafb57bf636b9b79156fde2df9e984779687058611d34c2969` |
| `provenance/evaluation/all-gguf-20260918/science-written-rubric-v1.json` | `1e842bfb72cff63512d0f1872b3e1c019a7f35f2870496535a1394d90a83fa91` |
| `provenance/evaluation/all-gguf-20260918/mc-semantic-rubric-v1.json` | `1389a208dd27ba4f73faf0f475a63f148dc010846ad87f2662b6dd3d4ad7f6dd` |

The unchanged automatic grader gives strict MC and provisional keyword-judge
scores; **written STEM is ungraded until separate semantic review**. Apply the
frozen MC choice/explanation/format/contradiction criteria and binary written
core-correct/instruction-complete criteria. For judges, retain fixed semantic
criterion weights; exclude the four unverified Yorùbá-dependent points until
qualified review, reporting reviewed /96 and deduplicated /86 separately from
automatic /100. Preserve exact-response hashes, reasons, uncertainties and
paired gains/regressions against incumbent; do not copy earlier control grades
without joining the actual new responses.

Keep ledgers separate from raw artifacts. Review all five models consistently,
including errors/truncations; independently cross-check the recommended model's
scores and regressions. Disclose agent-based/unblinded review; it is not official
judging or blinded human evaluation. Do not tune rubrics, choose checkpoints,
invent a weighted composite or change prompt sets to favor observed results.

These known suites support a provisional regression comparison, not the separate
independent 2000-item winner battery or target CPU speed/RSS qualification. A100
timings do not establish an ADTC total score. No overall winner is declared here.

## Independent local review

Root reviewed the complete conditional plan against the four-model manifest,
fresh-warm export mapping, actual evaluator settings/parser and process lifecycle,
and rehashed the four frozen review authorities. The author separately parsed all
four CLI templates and checked the 10/10/50/500 counts and prompt identities.
This approves the bounded handoff only; it is not a live runtime admission,
manifest freeze, completed evaluation or approval of any future model output.
