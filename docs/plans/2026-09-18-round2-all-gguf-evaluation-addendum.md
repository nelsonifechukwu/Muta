# Round-two matched all-GGUF evaluation addendum

Date: 2026-09-18

## Objective

Compare the incumbent Muta Q4_K_M artifact with all eight completed 20K pilot
Q4_K_M exports on the exact same frozen prompts and runtime, retaining full raw
outputs and enough provenance to identify the winning pilot without mixing
BF16/PEFT and GGUF execution paths.

## Frozen comparison

- Candidate manifest:
  `provenance/evaluation/all-gguf-20260918/candidate-manifest.json`.
- Candidates: the incumbent plus `clean-r16-lr1e5`, `clean-r32-lr1e5`,
  `warm-r8-lr5e6`, `warm-r16-lr5e6`, `warm-r16-lr1e5`,
  `warm-r16-lr2e5`, `warm-r32-lr5e6`, and `warm-r32-lr1e5`.
- Evaluator: immutable hardened snapshot
  `/lambda/nfs/awf-tmp/muta/campaign-20260918/configs/round2_candidate_eval_no_prompt_cache.py`
  at SHA-256
  `17b5eb630369313020150e338c43de87982b1a4b041679fa9a16153dc1ffbf12`.
  It is derived from the committed `bench/round2_candidate_eval.py` at
  SHA-256 `e8d8344029ea2db281791241b16e754c01d0c3a8d96f63038698abaf2f335192`
  on the still-clean Oracle checkout at commit
  `07df66bb26da69da69242aac34ee6b588d7f2d4a`.
- Server: `/home/ubuntu/.unsloth/llama.cpp/llama-server` at SHA-256
  `6a749492e30e2e360bc76f9be018a56588b2df5f03a437ec27b39a1f2434fdd4`.
- Judges: all ten prompts from `bench/judges_prompt_suite.py`; canonical
  prompt-set SHA-256
  `da2559db0f1e81a6f0d2010c17a96bb94268ee874e8030ff5f8cd11465f7b07a`.
- STEM: all 100 prompts from `bench/stem_prompt_suite.py`; canonical
  prompt-set SHA-256
  `34fa618d153470ea9094e846b24dd621beb24e5a9591888617c47dd9fb850d2c`.
- Decoding: greedy, temperature 0, top-p 1, seed 3407, thinking disabled,
  maximum 1,024 generated tokens, context 4,096.
- Runtime request: 99 GPU layers, two host threads, one server slot, 256 MiB
  server cache cap, Jinja chat rendering, and server-level prompt caching
  disabled with `--no-cache-prompt`. The run receipt must also record
  `gguf_prompt_cache: false`. The pinned Unsloth server binary accepted the
  GPU-layer argument but exposed no CUDA backend on Oracle: server logs show no
  offload and the A100 remained at 4 MiB with no compute process. The matched
  GGUF run is therefore CPU inference on Oracle; `--n-gpu-layers 99` is the
  recorded request, not a claim that 99 layers were actually offloaded.

The fixed STEM suite is a protected regression/reference battery: 25 math MCQ,
25 math written, 25 science MCQ, and 25 science written prompts. It is not
sampled from the training artifact at evaluation time, and exact/near-duplicate
checks against the 300,350-row selected training corpus passed. Its generator
families were nevertheless informed by the judges' topic families, so it is not
described as a fully independent blind test set.

## Preflight and execution

1. Refuse launch unless the Oracle checkout is clean at commit
   `07df66bb26da69da69242aac34ee6b588d7f2d4a` and no training or inference
   process is active.
2. Verify all nine GGUF byte counts and SHA-256 values, the shared server hash,
   and the eight quantization-manifest bindings.
3. Extract and hash each GGUF's embedded `tokenizer.chat_template`. Preserve all
   observed hashes; do not override a model template. Require the eight pilots
   to agree because they were exported with the same pinned clean tokenizer,
   and record the incumbent template separately if it differs.
4. Snapshot the manifest, prompt objects, runtime receipt, raw HTTP bodies,
   response JSONL, per-candidate identities/logs, summaries, inventories, and
   terminal checksum receipt via the audited evaluator.
5. Before the scoreable run, require a two-response runtime smoke of the exact
   duplicate judge prompts `automated_01` and `human_04`. Equality means the
   generation signature `(answer, reasoning_content, finish_reason,
   generated_tokens)` is identical; raw HTTP bodies are not expected to be
   byte-identical because response IDs, timestamps, and timing fields vary.
   The passing smoke is
   `evaluation/all-gguf-nocache-integrity-smoke-20260918T112129Z`; its
   external receipt is
   `evaluation/all-gguf-nocache-integrity-smoke-20260918T112129Z-receipts/duplicate-determinism-check.json`
   with SHA-256
   `007c5c9408ef75c22eeeeb7f8ce32d0a43faf55dfb53ddab5495f3ca10d0be66`.
   Post-run receipts and launch sidecars remain outside sealed evaluation trees
   so their terminal inventories continue to describe every in-tree file.
6. Run at most two queues: judges on base port 18480 and STEM on base port
   18580. Their output roots are respectively
   `evaluation/all-gguf-judges-20260918T112331Z` and
   `evaluation/all-gguf-stem-20260918T112331Z`. Concurrent wall time is
   diagnostic only and is not used to select the winner.
7. A completed evaluation requires 90/90 judge responses and 900/900 STEM
   responses, identical prompt hashes/settings for every candidate, no empty
   output, verified raw-output hashes, and `COMPLETED.json` in both trees.

The initial `evaluation/all-gguf-{judges,stem}-20260918T111526Z` trees were
stopped as soon as the missing prompt-cache control was discovered. They are
preserved with `INTERRUPTED-INTEGRITY.json`, have no valid terminal completion
receipt, and are diagnostic evidence only; none of their outputs may be scored.

## True-CUDA rerun gate

The `T112331Z` run uses the originally pinned CPU-only Unsloth server and is
retained as matched CPU evidence. A separate true-CUDA run is required for the
user's maximum-GPU execution request. It must use fresh
`evaluation/all-gguf-cuda-{judges,stem}-<UTC>` roots and may not launch until
all of the following are preserved outside those sealed roots:

1. exact CUDA server binary/source/build identities and a successful
   `--list-devices` receipt;
2. a single-candidate smoke whose server startup log proves a positive
   `offloaded X/Y layers to GPU` observation, with `X = Y` for the frozen
   `--n-gpu-layers 99` request; the server runs at `--verbosity 4` because the
   pinned b10175 default verbosity omits this load-time proof;
3. concurrent `nvidia-smi` process/memory evidence while generation is active;
4. the no-prompt-cache duplicate smoke passing on the generation signature;
5. the hardened evaluator's CPU-ready rejection, partial-offload rejection,
   full-offload acceptance, and CPU-request allowance tests passing.

The next evaluator records the startup proof in each sealed candidate
`backend-runtime.json`, copies it into each response's `backend_details`, and
writes a sealed run-level `backend-runtime-observations.json`. HTTP health alone
is never evidence of GPU execution.

## Selection rule

Use STEM multiple-choice correctness as the automatic correctness screen and
the complete ten-prompt tutoring outputs for manual/adversarial adjudication.
Keyword judge scores are screening aids, not the final tutoring verdict.
Prefer a pilot over the incumbent only when the matched GGUF evidence improves
correctness/tutoring without relying on concurrent latency. Preserve every
candidate's unedited output regardless of rank.
