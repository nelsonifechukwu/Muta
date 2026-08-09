# DUO PoC — Two Models, One GGUF, One Process

Implementation plan for Claude Code. Repo root contains `llama.cpp/` (shallow clone, patchable) and `models/` with:

- `models/SmolLM2-135M-Instruct-Q4_K_M.gguf` — "front" model (fast, always-on)
- `models/Qwen3.5-4B-Q4_K_M.gguf` — "expert" model (hard tasks)

## 0. Mission, scope, ground rules

**Mission.** Prove, end to end, that (1) both models can be packed into ONE valid GGUF file, (2) llama.cpp can load both from that single file in one process, (3) a front→expert **router escalation** works, and (4) **interleaved co-drafting** works: the two models alternately author segments of one answer over a shared transcript, with no draft/verify rollback.

**Non-goals.** No frontend, no HTTP server, no product packaging, no quant experiments, no GPU. CLI + traces + benchmark tables ARE the deliverable.

**Ground rules for the agent.**
1. **Discovery beats this document.** llama.cpp moves fast; where the tree's file names, API names, or CMake layout differ from this plan, follow the plan's *intent*, use what the tree exposes, and record the deviation in `docs/WORKLOG.md` (one line each: what the plan said → what the tree has → what you did, with file:line).
2. Never modify or move anything in `models/`.
3. All llama.cpp edits happen on branch `bundle-poc` inside `llama.cpp/`; one commit per task ID (e.g. `L3: filter+strip tensor ingest by prefix`); after Phase 2 and after Phase 3, export `git format-patch` output to `patches/`.
4. Every phase ends only when its gates (G-checks) pass; log gate results in `docs/WORKLOG.md`.
5. Keep diffs minimal. Do not refactor llama.cpp beyond what the patch needs.
6. Network use: only `git fetch` for llama.cpp and `pip install -e llama.cpp/gguf-py`. No model downloads.

**Repo layout to create (root level, alongside `llama.cpp/` and `models/`):**

```
scripts/      pack_bundle.py, verify_bundle.py, bench_duo.sh
bundle/       output: muta-duo.gguf
patches/      exported git patches for llama.cpp
bench/        baseline.md, results.md, prompts/easy.txt, prompts/hard.txt
docs/         DISCOVERY.md, WORKLOG.md, POC_REPORT.md, meta-front.txt, meta-expert.txt
```

---

## Phase 0 — Discovery & baseline

Goal: verify the clone can run both models at all, and record the ground truth every later phase depends on. **Do not write any new code before D6 is done.**

**D1 — Tree recency & Qwen3.5 support.**
`git -C llama.cpp log -1 --format='%H %cd'`. Then check the architecture is implemented:
`grep -rni "qwen3.5\|qwen35" llama.cpp/src/llama-arch.* llama.cpp/src/ | head` and `grep -rni "gated_delta\|delta_net\|gdn" llama.cpp/src llama.cpp/ggml/src | head`.
If absent → shallow-update: `git -C llama.cpp fetch --depth 1 origin master && git -C llama.cpp checkout FETCH_HEAD`, re-check. Record commit hash in `docs/DISCOVERY.md`. (Qwen3.5's hybrid uses Gated-DeltaNet layers; support is recent — this check is the go/no-go for everything.)

**D2 — Build (CPU-only).**
```
cmake -S llama.cpp -B llama.cpp/build -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF
cmake --build llama.cpp/build -j --target llama-cli llama-bench llama-tokenize llama-quantize
```
Binaries land in `llama.cpp/build/bin/`. If a target name doesn't exist, build all and find equivalents (`ls build/bin`).

**D3 — Smoke both models.** For each model:
`llama-cli -m <model> -p "Explain photosynthesis in one sentence." -n 48 --temp 0 --seed 42` — add `-no-cnv` or `--single-turn` (whichever the build accepts) to avoid interactive mode. Both must load and generate coherent text. Save outputs to `docs/DISCOVERY.md`.

**D4 — Metadata dump.**
`pip install -e llama.cpp/gguf-py`, then dump each model (`gguf-dump --no-tensors <model>` if the console script installs, else `python3 llama.cpp/gguf-py/gguf/scripts/gguf_dump.py --no-tensors <model>`; the script path may also be `llama.cpp/gguf-py/scripts/`). Save full dumps to `docs/meta-front.txt` / `docs/meta-expert.txt`, and extract into `docs/DISCOVERY.md`:
- exact `general.architecture` strings (expect `llama` for SmolLM2; record the exact Qwen3.5 string — do not assume its spelling)
- `general.alignment` for each (offset padding is recomputed at pack time, so a mismatch here is a non-issue — just record it)
- `tokenizer.ggml.model`, `tokenizer.ggml.pre`, presence of `tokenizer.chat_template`, EOS/EOT/im_end token ids
- block counts, context lengths, tensor counts

**D5 — Verdict-token probe (needed by the router in Phase 3).** The router compares logits of two single tokens. Using `llama-tokenize -m models/SmolLM2... -p "<candidate>"`, find a pair of strings that each encode to exactly ONE token in SmolLM2's vocab. Try in order: `" A"` / `" B"`, `"A"` / `"B"`, `" 1"` / `" 2"`, `" yes"` / `" no"`. Record the winning pair and their token IDs in `docs/DISCOVERY.md`.

**D6 — Baselines.** `llama-bench -m <model> -p 512 -n 128` for each model; also record peak RSS of a `llama-cli` run (`/usr/bin/time -v`, `Maximum resident set size`). Write a small table to `bench/baseline.md`: model, pp tok/s, tg tok/s, RSS. These are the reference numbers all Phase 4 comparisons use.

**Phase 0 gates:** both models generate (D3); `DISCOVERY.md` complete (D1–D5); `bench/baseline.md` exists (D6).

---

## Phase 1 — The bundle packer (Python)

Goal: `scripts/pack_bundle.py` producing `bundle/muta-duo.gguf`, a single **valid GGUF** containing both models under name prefixes.

**Bundle format spec (normative).**
- Top-level: `general.architecture = "bundle"` (deliberate: unpatched llama.cpp fails fast with unknown-arch instead of a confusing tensor error), plus manifest keys:
  - `bundle.count` (u32) = 2
  - `bundle.{i}.prefix` (str) = `"m0."` / `"m1."`
  - `bundle.{i}.role` (str) = `"front"` / `"expert"`
  - `bundle.{i}.arch` (str) = copy of that model's `general.architecture`
  - `bundle.{i}.source` (str) = source filename; `bundle.{i}.sha256` (str) of source file
- For each source model *i*: every metadata KV `k → m{i}.k` (including its `general.architecture`, tokenizer arrays, merges, chat template — everything), **except** structural pseudo-fields whose name starts with `GGUF.` (version/counts; the writer regenerates those).
- Every tensor `t → m{i}.t`, payload copied as **raw bytes** in its original quant type (Q4_K/Q6_K blocks pass through untouched; never dequantize/requantize). Offsets are writer-generated.
- Single data section, writer-default alignment (32).

**P1 — Implementation base.** Model the copy loop on the in-tree script `gguf_new_metadata.py` (in `llama.cpp/gguf-py/...`): it already does reader→writer pass-through of typed KV fields *and* raw tensor re-add (`add_tensor(name, tensor.data, raw_shape=..., raw_dtype=tensor.tensor_type)`), handling field decoding and endianness. Copy its patterns; do not reinvent them. CLI:
`pack_bundle.py --out bundle/muta-duo.gguf --model models/SmolLM2-135M-Instruct-Q4_K_M.gguf:m0.:front --model models/Qwen3.5-4B-Q4_K_M.gguf:m1.:expert`

**P2 — Identity-repack gate first (before any prefixing).** Add `--identity <model> --out x.gguf`: pack ONE model with empty prefix and its original arch. **Gate G1:** stock `llama-cli` on the repacked file produces byte-identical greedy output to the original file (`--temp 0 --seed 42 -n 64`, same prompt). This isolates copy-loop correctness from everything else. Run G1 for SmolLM2 (fast); if it fails, fix the packer before proceeding.

**P3 — Full bundle.** Produce `bundle/muta-duo.gguf`. Sanity: file size ≈ sum of sources + small KV overhead (< +5 MB); `gguf-dump --no-tensors` on it shows the manifest and both prefixed key families.

**P4 — Byte-level verification.** `scripts/verify_bundle.py`: open sources and bundle with `GGUFReader`; assert (a) every source KV appears prefixed with equal typed value, (b) every source tensor appears prefixed with equal `tensor_type`, shape, and byte-identical payload (sha256 per tensor), (c) manifest correct. Print a pass/fail table. **Gate G2a:** all pass.

**Phase 1 gates:** G1 (identity repack) and G2a (byte verification).

---

## Phase 2 — llama.cpp loader patch: `bundle_prefix`

Goal: `llama_model_load_from_file` can load one sub-model out of the bundle, selected by prefix, with zero behavior change when the prefix is unset. Two calls with two prefixes on the same path = two models, one process, one file.

**API surface (L1).**
- `include/llama.h`: add `const char * bundle_prefix; // NULL = normal load` to `llama_model_params`; default NULL in `llama_model_default_params()`.
- `common/`: add `--bundle-prefix STR` (arg parsing lives in `common/arg.cpp`; param in `common_params`; thread into model params where common builds them).

**Patch mechanics (L2–L5).** The choke point is the model loader class (`src/llama-model-loader.{h,cpp}`, class `llama_model_loader`) — all metadata reads and tensor lookups for model construction and vocab loading flow through it. When `bundle_prefix` is set:

- **L2 — Tensor ingest, filter+strip.** In the loader's constructor where it iterates the GGUF tensor table into its internal name→info map (`weights_map` or equivalent): skip tensors whose name doesn't start with the prefix; strip the prefix from the stored key. Downstream `create_tensor`/`get_tensor_meta` then work on unprefixed names untouched, and per-arch tensor-set validation passes because the view contains exactly one model's tensors. Adjust any "n_tensors mismatch" consistency check to compare against the *filtered* count.
- **L3 — KV reads, prefix at resolution.** Route the loader's key resolution (the helper under `get_key`/`get_arr` that ultimately calls `gguf_find_key`) through one function that prepends the prefix. `general.architecture` is read through this same path, so the loader sees the sub-model's true arch (`llama` / the Qwen3.5 string), and everything downstream (hparams, vocab, chat template retrieval) follows.
- **L4 — Audit stragglers.** `grep -rn "gguf_find_key\|gguf_get_val\|gguf_get_arr" llama.cpp/src | grep -v "gguf.c"` — any direct GGUF reads on the *model's* gguf context in the model/vocab load path must go through the L3 helper. Print/log-only uses may stay.
- **L5 — Things that must NOT change.** `general.alignment` and data-offset handling live in the ggml GGUF layer and are per-file, not per-model — leave untouched. mmap: two `llama_model_load_from_file` calls on the same path create two mappings of one file; the page cache shares the physical pages, so RAM is not doubled — do not "optimize" this in the PoC (G-check via RSS in Phase 4). `kv_overrides` operate on requested key names post-resolution — verify they still apply, don't redesign.

**L6 — Gates.**
- **G2b (identity through the patch):** `llama-cli -m bundle/muta-duo.gguf --bundle-prefix m0. --temp 0 --seed 42 -n 64` output token-identical to stock SmolLM2 file, same flags. Same for `m1.` vs stock Qwen3.5. (Greedy determinism makes this exact; any divergence = a wrong/missed lookup.)
- **G2c (perf parity):** `llama-bench` via bundle+prefix within ±5% of Phase 0 baselines for both models.

**L7 — Export.** `git format-patch` the branch into `patches/`; note patched files+roles in `docs/WORKLOG.md` for future rebases.

**Phase 2 gates:** G2b, G2c, patches exported.

---

## Phase 3 — The `duo` tool (C++, links libllama)

Goal: one binary, `llama-duo`, loading front+expert from the bundle in one process, implementing router escalation and interleaved co-drafting with full per-segment tracing. Place it where the tree puts tools (`llama.cpp/tools/duo/` mirroring `tools/main`'s CMake wiring; if this tree still uses `examples/`, use `examples/duo/`). Reference in-tree code that already runs two models in one process: the speculative-decoding tool — copy its dual-model load/teardown patterns, not its verify loop.

### 3.1 Shared infrastructure (T1–T6)

**T1 — Flags** (defaults in brackets):
```
--bundle PATH            bundle file [bundle/muta-duo.gguf]
--front-prefix [m0.]  --expert-prefix [m1.]
--mode {router|codraft} [router]
--ctx-front [4096]  --ctx-expert [8192]
--threads N (sequential-mode threads for whichever model is active) [nproc]
--temp-front [0.7] --top-p-front [0.9]  --temp-expert [0.6] --top-p-expert [0.95]
--route-threshold τ [0.0]        (logit-difference threshold, router)
--conf-window W [16]  --conf-threshold τc [-2.5]   (mean logprob trigger)
--seg-min [24] --seg-max [96]    (co-draft segment budgets, tokens)
--closer {expert|either} [expert]
--carry-draft [off]              (router: expert continues front's partial draft)
--overlap [off]  --threads-front [2] --threads-expert [nproc-2]   (3.4 only)
--seed [42]  --n-predict cap per answer [1024]
--trace [on]  --json-trace FILE [off]
--selftest-seams [off]           (gate G4)
```

**T2 — Loading.** Two `llama_model_load_from_file(bundle, params)` calls differing only in `bundle_prefix`; one `llama_context` each (`llama_init_from_model`). Sampler chain per model via the tree's `common_sampler`. Free in reverse order on exit.

**T3 — Templates & prompts.** Read each model's chat template from its own (prefixed) metadata via the tree's chat-template helpers (`common_chat_templates_*`). Both are ChatML-family. Per model, render `(system_i, history…, user)` **with** the generation prompt (i.e. ending at `<|im_start|>assistant\n`), then append the shared in-progress assistant text raw. System prompts are asymmetric (Appendix B): front = "continue", expert = "continue and correct course". Fallback if template helpers fight continuation: construct ChatML manually from the metadata special tokens (record in WORKLOG if used).

**T4 — Per-model committed state.** For each model keep: `committed_text` (its rendered prompt + shared answer so far), `committed_tokens` (its tokenization of that), its context positions in lockstep. `ingest(model, delta_text)`: `llama_tokenize(delta, add_special=false, parse_special=false)`, batch-decode (n_batch 512), extend `committed_tokens`. **Invariant:** delta boundaries always fall before whitespace (see 3.3 seam rule), so per-model delta tokenizations compose exactly.

**T5 — Detokenization buffer.** Accumulate `token_to_piece` output per model in a byte buffer; only run boundary regexes over the valid-UTF-8 prefix (byte-fallback tokens can emit partial UTF-8 — never split inside a codepoint).

**T6 — Token logprob.** After each decode, compute the sampled token's logprob with a stable log-sum-exp over the logits row (vocab ≤ ~152k floats — negligible). Maintain a ring buffer of the last W values per active generation; `mean < τc` ⇒ confidence trigger. (Restrict softmax to two ids and P(hard)=σ(z_h−z_e); that's why the router below thresholds the raw logit difference — no normalization needed.)

### 3.2 Router mode (T7–T10)

**T7 — Pre-turn route.** Build the routing prompt (Appendix B) around the user message; decode it on the FRONT context; read last-position logits; `s = z[HARD_ID] − z[EASY_ID]` using the D5 token pair; route hard iff `s ≥ τ`. Then clear the routing tokens from front's sequence (`llama_memory_seq_rm` on the routing range — front is dense-attention, partial removal is supported; older API name `llama_kv_self_seq_rm`/`llama_kv_cache_seq_rm`, use what the tree has). Deterministic: no sampling anywhere in routing.

**T8 — Easy path.** Front answers under its template, streaming, with the T6 confidence monitor armed. On trigger: stop front; if `--carry-draft`, expert continues the draft (ingest draft text, continue open assistant turn); else expert answers the user fresh. Emit a trace line naming the trigger and the mean-logprob value.

**T9 — Hard path.** Expert answers directly (lazy sync first: ingest any history it hasn't seen — track `expert_synced_upto`).

**T10 — Multi-turn.** Append each final assistant message to BOTH models' histories (front stays cheap to sync; expert syncs lazily on next use). Trace per turn: `route=(easy|hard) s=<val> author=<model> tokens=<n> ms=<t> tok/s=<r> [trigger=conf]`.

### 3.3 Co-draft mode (T11–T15)

Shared-transcript alternation; full pseudocode in Appendix C. The load-bearing rules:

**T11 — Seam rule (correctness).** Every committed segment ends immediately **before** a whitespace character; the whitespace opens the next segment. Byte-level BPE pre-tokenizers split at whitespace and attach the space to the following word, so merges cannot cross such a seam — delta tokenization equals joint tokenization, caches stay valid, nothing is ever re-encoded. Assert at every commit: next delta starts with whitespace (or transcript empty).

**T12 — Asymmetric rewind (correctness).** FRONT may over-generate and rewind: it buffers emitted text, commits only up to the last boundary, and rolls its KV back to the committed position with `llama_memory_seq_rm` (dense attention supports partial removal). EXPERT is strictly append-only: Qwen3.5's Gated-DeltaNet layers keep a recurrent state that cannot be partially rewound — so the expert only ever ingests committed text and stops its own segments exactly at boundaries. If any code path would need an expert rewind, the fallback is a full expert re-ingest from scratch (clear seq, re-decode rendered prompt+transcript); log every occurrence — the design goal is zero.

**T13 — Handoff conditions.** Active model decodes until: (a) `seg-min` reached AND boundary matched — regex `([.!?])["')\]]*\s` or `\n\n` on the T5 buffer — cut at the punctuation, whitespace goes to the next segment; or (b) hard cap: past `seg-max`, extend to the next whitespace (≤ +16 tokens) and cut there (never mid-word — T11); or (c) FRONT ONLY, uncertainty: T6 trigger fires ⇒ commit to last boundary, rewind the tail (T12), hand to expert early (this is the "expert takes the hard span" behavior). EOS/im_end: under `--closer expert` (default), a front EOS is treated as a handoff (prevents the 135M ending a hard answer prematurely); expert EOS at a boundary ends the turn. `--closer either` lets both end it.

**T14 — Loop.** `while turn open: M = active; ingest(M, delta since M's committed); decode M until handoff; commit; swap.` First segment: front (flag-able later; not needed for PoC). End of turn: both models' committed streams equal the full transcript by construction; append assistant message to both histories.

**T15 — Trace.** Per segment: `[seg k] author=<front|expert> tokens=<n> ms=<t> tok/s=<r> mean_lp=<v> cut=(boundary|cap|conf|eos)`; per turn summary: total tokens, wall time, effective tok/s, %tokens by expert (=f), ingest overhead ms per model. `--json-trace` mirrors this as JSON lines. **This trace is the PoC evidence — treat its correctness as a feature.**

### 3.4 Optional overlap milestone (T16)

Only after 3.2/3.3 gates pass. `--overlap`: a background `std::thread` ingests committed-but-unsynced text into the expert context while the front decodes, front on `--threads-front`, expert on `--threads-expert` (set via `llama_set_n_threads`). Two different contexts may decode concurrently (independent states/threadpools); NEVER decode one context from two threads. Mutex the transcript; the background thread only reads committed text. Measure with/without: the point is hiding expert catch-up prefill (`t_ingest_expert`) under front decode. If the tree's threading makes this flaky, document and leave the flag off by default — sequential mode already proves the architecture.

---

## Phase 4 — Validation & benchmarks

**G3 — Router quality.** Author `bench/prompts/easy.txt` (20) and `bench/prompts/hard.txt` (20) — WAEC/JAMB-flavored: easy = greetings, single-fact recall, one-line definitions; hard = multi-step math, physics word problems, essay questions, code. `bench_duo.sh` sweeps τ ∈ {−2,−1,0,1,2}, reports a routing-accuracy table; pick the τ that maximizes accuracy, record as the new default.

**G4 — Seam self-test.** `--selftest-seams`: run co-draft ≥200 tokens on 5 prompts; at end, for each model tokenize its full rendered prompt+transcript from scratch and assert equality with `committed_tokens`. Any mismatch = seam-rule violation; fix before proceeding.

**G5 — Co-draft liveness.** 10 consecutive turns, mixed prompts, no crash/stall/runaway; transcript decodes to identical bytes from both models' views.

**G6 — Perf matrix → `bench/results.md`.** Rows: front alone, expert alone (from baseline), router-easy, router-hard, router-escalated, co-draft at seg budgets giving f≈{0.25, 0.5, 0.75}, each ± `--overlap`. Columns: end-to-end tok/s, expert-share f, ingest ms, wall per answer. Add predicted-vs-measured: `T̄ ≈ f·t_expert_decode + (1−f)·max(t_front_decode, t_expert_ingest_per_tok)` with overlap, vs the sequential sum without — the measured deltas should track the model.

**G7 — RAM.** Peak RSS for every G6 row (`/usr/bin/time -v`); require < 6.5 GB (target box is 8 GB). Confirms the two-mmap-one-file page-cache sharing claim empirically.

**Report.** Fill `docs/POC_REPORT.md`: commit hashes, gate results table, bench tables, three annotated trace excerpts (one escalation, one confidence trigger, one co-draft turn), deviations list from WORKLOG, and a "known limits / next steps" section (HTTP serving, batch/classroom mode, bundle mmap sharing, grammar-forced tool tag).

---

## Risks & fallbacks

| # | Risk | Detection | Fallback |
|---|------|-----------|----------|
| R1 | Clone predates Qwen3.5 support | D1 grep empty / D3 load fails | shallow fetch master (D1) |
| R2 | gguf-py API drift (fields/add_tensor) | packer errors | mirror in-tree `gguf_new_metadata.py` exactly; it is version-matched |
| R3 | No single-token verdict pair | D5 probe fails all candidates | compare logits of the FIRST token of each multi-token verdict |
| R4 | Template helper can't leave assistant turn open | T3 | manual ChatML from metadata special tokens |
| R5 | Partial `seq_rm` unsupported where assumed | runtime false return | front: full re-ingest of its (small) prompt+transcript; expert: designed append-only already |
| R6 | Loader refactor moved patch points | grep in L2–L4 misses | patch by role: (a) tensor-map ingestion site, (b) key-resolution helper — find them via the L4 greps |
| R7 | Overlap threading flaky | T16 instability | ship sequential; overlap stays experimental flag |

## Definition of done

- [ ] G1 identity repack; G2a byte verify; G2b bundle identity ×2 models; G2c perf parity
- [ ] Router: deterministic routes, G3 table, escalation + confidence trigger demonstrated in traces
- [ ] Co-draft: G4 seam self-test clean, G5 liveness, `--closer` policies work
- [ ] G6 perf matrix + G7 RSS recorded; POC_REPORT.md complete; patches/ exported; WORKLOG.md current

---

## Appendix A — Bundle manifest (worked example)

```
general.architecture      = "bundle"
bundle.count              = 2
bundle.0.prefix="m0."  bundle.0.role="front"   bundle.0.arch="llama"
bundle.1.prefix="m1."  bundle.1.role="expert"  bundle.1.arch=<exact Qwen3.5 arch string from D4>
m0.general.architecture   = "llama"
m0.tokenizer.ggml.tokens  = [...49k strings...]        m0.blk.0.attn_q.weight = <Q4_K bytes>
m1.general.architecture   = <qwen3.5>                  m1.tokenizer.ggml.tokens = [...151k strings...]
...
```

## Appendix B — Router & system prompts (initial text; tune during G3)

Routing prompt (front model, `--temp` irrelevant — logits only), with `{A}`/`{B}` the D5 pair:
```
<|im_start|>system
You classify questions by difficulty. Reply with exactly one letter.
{A} = simple: greeting, chit-chat, a single fact, a one-line definition.
{B} = hard: math with steps, physics/chemistry problems, essays, code, anything multi-step.
<|im_end|>
<|im_start|>user
Q: "Hello, how are you?" →<|im_end|><|im_start|>assistant
{A}<|im_end|><|im_start|>user
Q: "Solve 3x + 5 = 20 and explain each step." →<|im_end|><|im_start|>assistant
{B}<|im_end|><|im_start|>user
Q: "<USER MESSAGE>" →<|im_end|><|im_start|>assistant
```
Front system prompt (answering/co-draft): `You are a helpful tutor. Continue the answer naturally and concisely.`
Expert system prompt (co-draft): `You are the senior tutor. Continue the answer; if the draft so far has errors or drifts, correct course and steer it right, then continue.`

## Appendix C — Co-draft loop (normative pseudocode)

```
transcript = ""                      # shared answer text, always seam-aligned
for each model M: M.committed = render_prompt(M) tokenized & decoded
active = front
while turn_open:
    ingest(active, transcript_delta_for(active))          # exact by T11
    buf = ""                                              # detok buffer (T5)
    while true:
        tok = decode_and_sample(active)
        if tok is EOS: handle per --closer; break
        buf += piece(tok); lp.push(logprob(tok))
        if active==front and lp.mean(W) < τc and has_boundary(buf):
            cut = last_boundary(buf); break                # conf handoff (c)
        if len_tokens(buf) >= seg_min and has_boundary(buf):
            cut = last_boundary(buf); break                # normal handoff (a)
        if len_tokens(buf) >= seg_max:
            extend to next whitespace (≤16 tok); cut there; break   # cap (b)
    commit = buf[:cut]                                    # ends before whitespace
    if active==front: rewind front KV to committed length # T12
    transcript += commit; trace_segment(...)
    active = other(active)
emit transcript; append to both histories
```

## Appendix D — Command catalog

```
# build
cmake -S llama.cpp -B llama.cpp/build -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF && cmake --build llama.cpp/build -j
# pack + verify
python3 scripts/pack_bundle.py --out bundle/muta-duo.gguf \
  --model models/SmolLM2-135M-Instruct-Q4_K_M.gguf:m0.:front \
  --model models/Qwen3.5-4B-Q4_K_M.gguf:m1.:expert
python3 scripts/verify_bundle.py bundle/muta-duo.gguf models/*.gguf
# identity gates
llama.cpp/build/bin/llama-cli -m bundle/muta-duo.gguf --bundle-prefix m0. --temp 0 --seed 42 -n 64 -p "<probe>"
# duo
llama.cpp/build/bin/llama-duo --bundle bundle/muta-duo.gguf --mode router  -p "Solve 3x+5=20"
llama.cpp/build/bin/llama-duo --bundle bundle/muta-duo.gguf --mode codraft -p "Explain Newton's second law with an example"
bash scripts/bench_duo.sh   # G3 sweep + G6 matrix
```
