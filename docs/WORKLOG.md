# DUO PoC — Worklog

Deviations format (ground rule 1): what the plan said → what the tree/host has → what was done, with file:line where relevant.

## Phase 0

- D1: plan said fetch master if Qwen3.5 absent → clone already at `7ba604f1cb` (2026-08-09) with `LLM_ARCH_QWEN35` → `"qwen35"` (`src/llama-arch.cpp:41`) and Gated-DeltaNet (`src/models/{qwen35.cpp,delta-net-base.cpp}`) → no fetch; R1 retired.
- D2: plan's plain cmake invocation → host CLT toolchain is broken: `/Library/Developer/CommandLineTools/usr/include/c++/v1/` is a stale partial skeleton (no `cstdio`/`mutex`/…) that shadows the complete SDK libc++, so ALL C++ compiles fail with "'cstdio' file not found" → added `-DCMAKE_CXX_FLAGS="-nostdinc++ -isystem /Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/include/c++/v1"`. (Machine-level fix would be removing the stale dir / reinstalling CLT — needs sudo, not done.)
- D2: host is arm64 macOS but the only cmake is x86_64 (Intel-Homebrew, runs under Rosetta), so first configure produced an x86 build (`GGML_SYSTEM_ARCH: x86`) → forced `-DCMAKE_OSX_ARCHITECTURES=arm64` (top-priority in `ggml/cmake/common.cmake:29`) for a native build.
- D2: plan targets CPU-only to match the x86-Linux deployment box; on this Mac cmake auto-enabled Metal → `-DGGML_METAL=OFF` so all numbers are CPU-only. Note: all local perf numbers are arm64-macOS, comparative only; absolute ADTC numbers must be re-measured on the target box.
- Plan said speculative tool under `tools/` → this tree has `examples/speculative{,-simple}` → use those as the dual-model reference.
- Plan said gguf scripts possibly at `gguf-py/scripts/` → actual `gguf-py/gguf/scripts/{gguf_new_metadata.py,gguf_dump.py}`.
- Plan said `/usr/bin/time -v` for peak RSS → macOS uses `/usr/bin/time -l` ("maximum resident set size", bytes).
- Repo hygiene: added `llama.cpp/` and `bundle/` to `.gitignore` (CLAUDE.md mandate; bundle output is ~2.8 GB regenerable).
- D2 (second failure): with `CMAKE_OSX_ARCHITECTURES=arm64` under the Rosetta cmake, ggml's `-mcpu=native` probe (`ggml/src/ggml-cpu/CMakeLists.txt:114-138`) runs the compiler WITHOUT `-arch arm64`; the probe process inherits x86_64 via Rosetta, yields no usable flag, and the code falls back to a literal `-mcpu=native`, which AppleClang rejects at compile time ("unsupported argument 'native'") → set `-DGGML_NATIVE=OFF -DGGML_CPU_ARM_ARCH=armv8.5-a+dotprod+i8mm+fp16` (explicit `-march` branch at `ggml-cpu/CMakeLists.txt:169-170`; host is Apple M2 Pro: FEAT_DotProd=1, FEAT_I8MM=1, FEAT_SME=0). Bonus: non-native flags make the build reproducible.
- gguf-py editable install lands in v1's venv (`.venv` here resolves to `../Muta/.venv` per pip's own paths — matches CLAUDE.md's warning about the shared venv); `import gguf` works, which is all Phase 1 needs.
- llama.cpp has its own CLAUDE.md/AGENTS.md: private-fork work is exempt from its upstream-contribution rules, but its code style applies (ASCII-only comments, concise, blend in); commits on `bundle-poc` use the plan's `<task-id>: <summary>` format with `Assisted-by:` trailer, and nothing is ever pushed or PR'd upstream.

## Phase 1

- P2/G1: identity repack of SmolLM2 is **bit-for-bit identical** to the source file (same sha256 `ed5fa30c...`), stronger than the required same-greedy-output. Copy loop is provably lossless.
- P3: `bundle/muta-duo.gguf` = 2,846,394,944 bytes vs source sum 2,846,392,032 -> +2,912 bytes overhead (spec allowed +5 MB). 698 tensors, 91 KVs, manifest correct per dump.
- Negative test: unpatched `llama-completion` on the bundle fails fast with `unknown model architecture: 'bundle'` (the spec's deliberate fail-fast design confirmed).

## Phase 2

- Patched files and roles (6 commits on `bundle-poc`, exported to `patches/`):
  - `include/llama.h` + `src/llama-model.cpp` (default): `bundle_prefix` in `llama_model_params` (L1)
  - `common/{common.h,common.cpp,arg.cpp}`: `--bundle-prefix` flag threading (L1)
  - `src/llama-model-loader.{h,cpp}`: prefix member + `resolve_key()` helper; tensor ingest filter+strip in both load paths; split-GGUF guard; empty-filter error (L2); all 6 string-key lookup sites route through `resolve_key` while kv_overrides still match the caller's unprefixed key (L3)
  - `src/llama-vocab.cpp`: 7 direct `gguf_find_key` sites wrapped with `ml.resolve_key` (L4)
  - `src/llama-model.cpp` `load_hparams`: `model->gguf_kv` copy filters+strips by prefix (feeds `llama_model_meta_val_str` -> chat template retrieval) (L4)
  - `tools/llama-bench/llama-bench.cpp`: file-scope `--bundle-prefix` (L6)
- **Bug found during G2b** (one-line fix, would bite anyone doing name-mapped loading): `create_tensor` named model tensors from the on-file tensor struct (`ggml_get_name(&t_meta)`) instead of the requested name (`tn.str()`). Identical in stock loads; with a prefix, `load_all_data`'s `get_weight(name)` then missed every tensor and SILENTLY skipped them (the "split experts" `continue` at `llama-model-loader.cpp:1553`), producing a loaded-but-uninitialized model that generated garbage. Diagnosed via stock-vs-bundle verbose log diff (missing `repack:`/`CPU_Mapped` lines + prefixed name in `done_getting_tensors`).
- G2b run both as raw completion (`-no-cnv`, 64 tokens) and through the chat-template path (exercises stripped `gguf_kv`): byte-identical stock vs bundle for BOTH models; no-prefix path byte-identical to pre-patch output.
- G2c same-binary same-session comparison: front tg -1.6%, expert pp -4.1%, expert tg -3.6% (all within +/-5%). Front pp512 is measurement noise on the 135M model (stock 2260+/-300 vs bundle 2672+/-191 vs D6 baseline 2596+/-210; overlapping intervals, bundle faster) - pass on no-regression intent.

## Phase 3

- `tools/duo/duo.cpp` (+CMake wiring), single commit T1-T15, exported as patch 0007. Design deviations/decisions vs plan, all correctness-preserving:
  - **Peek-token cuts**: the active model samples the next token but does NOT decode it when it starts with whitespace and the buffer ends at a boundary - the segment is cut there and the peeked token discarded. This is what lets the append-only expert stop its recurrent state EXACTLY at the seam (plan T12's requirement) with zero rewinds.
  - **Front full-segment rewind + canonical re-ingest**: instead of keeping sampled-token KV up to the boundary, the front rewinds its whole segment (`llama_memory_seq_rm`) and re-ingests committed text canonically on its next activation (~40ms per segment at prefill speed). Guarantees `committed_tokens == tokenize(committed_text)` for the front by construction.
  - Verdict tokens: bare `A`=49/`B`=50 (not D5's `" A"`/`" B"` 330/389) because the verdict position follows `assistant\n` where the canonical next token has no leading space; few-shot examples use bare letters.
  - Expert renders with `enable_thinking=false` (tree supports it natively) so Qwen3.5's auto-`<think>` block is pre-closed in the prompt; the shared transcript stays think-free.
  - `--prompts-file` (one user message per line) drives multi-turn runs for G5.
  - Chat rendering via `common_chat_templates_apply` with manual-ChatML fallback on exception (R4); fallback not needed in practice so far.
- Smoke results: router easy s=-2.34 (greeting)->front; hard s=+1.06 (equation)->expert correct step-by-step solution. Codraft: 10-14 segments, expert share ~0.45, effective 34-42 tok/s vs 26.6 expert-alone; visible course-correction (front misnames the law, expert's segment corrects). Seam self-test: front OK, expert OK (both canonical on first tries). Confidence escalation demonstrated: `--conf-threshold -0.9` triggers at token 121; carry-draft finishes in 131 expert tokens vs 903 answering fresh.
- T16 overlap: deferred until after G3-G7 per plan ordering (sequential mode proves the architecture).

## Phase 4

- G3: 40 WAEC/JAMB-flavored prompts (20 easy / 20 hard), routed once each via `--route-only` (scores are tau-independent, so the sweep is post-hoc thresholding). Accuracy: tau=-2 70%, tau=-1 75%, **tau=0 87.5%** (easy 16/20, hard 19/20), tau=1 80%, tau=2 57.5%. Default stays tau=0. Misroutes: 4 science/math factoids over-escalate (cheap: costs speed, not accuracy); 1 history-essay prompt under-routes (s=-0.75).
- G4 (first run): 5 codraft turns of 390-1024 tokens. Front selftest strictly canonical on ALL turns; expert 4/5 OK plus one NON-CANONICAL self-segment case (equal token counts, identical text; the documented allowed case - expert never re-encodes its own spans).
- G4 exposed a multi-turn perf bug: expert ingest grew O(history) per turn (5s -> 33s) because the Qwen jinja template drops think blocks from PAST assistant turns, breaking prefix extension -> full expert re-sync every turn. Fix: expert view rendered with manual prefix-stable ChatML (history assistant turns keep the closed think block byte-identical to live generation). After fix: resync_expert=0, per-turn expert ingest ~2.5s flat, throughput steady ~35 tok/s across turns. Committed as T14 fix; front keeps the jinja path (naturally prefix-stable).

## Optimization session (branch duo-verify, 2026-08-09)

Question: best config/architecture for max+average tok/s WITHOUT reducing accuracy. Method: fixed-prompt fixed-seed one-change-at-a-time experiments (borrowed from karpathy/autoresearch's keep-or-revert loop).

- User's rapid-random setting (`--mode random --p-front 0.3 --seg-min 1 --seg-max 2`): 205 segments for 335 tokens, 28.2 tok/s (SLOWER than expert alone) with locally-fluent but globally muddled text (self-contradictions, repeated claims). Switching overhead eats the entire front-speed advantage; a throughput pessimum. Great stress test though: 205 seams, zero crashes.
- Built `--mode verify`: speculative-style expert verification of front drafts with seq-1 checkpointing over the hybrid's unrewindable recurrent state (`seq_cp` is copy-on-write; rollback = whole-seq rm + cp-back + re-decode accepted prefix). Deterministic, seam-exact (selftests pass), correct rollback across 40+ rounds.
- Experiments (water-cycle 256-token prompt, seed 42): acceptance ~0.42 is INSENSITIVE to the threshold (tau -5/-3/-2 identical) - front/expert disagreement is bimodal (agree, or lp << -5). Greedy drafts do NOT help (0.39): divergence is content-level, not sampling noise. Acceptance is domain-dependent: 0.54 on equation math, 0.32-0.42 on prose.
- Break-even analysis: verify beats plain expert decode only at acceptance >= ~0.55 (accepted tokens cost ~12ms vs 33ms, but failed rounds burn draft+verify+redo overhead). This 135M-SmolLM2/4B-Qwen3.5 pair sits below break-even on most content (cross-family, 30x size gap) -> `--hard-mode` default = expert; verify stays opt-in and pays off with a better-aligned draft (e.g. a Qwen-family 0.5B) - first next step.
- Bugs found and fixed during the loop: (1) router+verify loaded the expert WITHOUT the checkpoint sequence; recurrent seq_cp to a nonexistent seq is a SILENT no-op, so the first rejection wiped the expert state and produced garbage continuations - fixed + loud GGML_ASSERT; caught by finally READING the answer text, not just the tok/s number. (2) A correction token could be EOS and was decoded blindly, letting generation continue past it; EOG corrections now end the turn, and the expert also gets an end-of-turn say after every accepted span (fixes answers running to the 1024 cap).
- Environmental lesson: one "0.6 tok/s catastrophe" was fully explained by concurrent model processes contending for cores (clean rerun: 28.0 tok/s, identical deterministic trace); serialize all measurements.

## Same-family front (branch duo-qwen-front, 2026-08-09)

- Downloaded `unsloth/Qwen3.5-0.8B-MTP-GGUF` Q4_K_M (550 MB, sha256 ac7c9d7a1b3e...) -> `models/Qwen3.5-0.8B-MTP-Q4_K_M.gguf`. Same `qwen35` arch and SAME 248k tokenizer as the expert; MTP head present (`nextn_predict_layers=1`), loads fine with load_mtp off. Smoke + bundle identity PASS; new bundle `bundle/muta-duo-q.gguf` (3.29 GB).
- duo changes (commit Q1): hybrid fronts auto-detected (`llama_model_is_recurrent/hybrid`) and treated as append-only with their own checkpoint seq; verify drafts run provisionally (save -> draft -> restore); routing decodes on a checkpoint with a closed think block; conf monitor disabled for append-only authors; forced front resync narrowed to word-word/punct-punct correction joins (the review's verifier had shown those are the only risky ones - the broad trigger was costing ~1 s per reject at the 0.8B's 574 t/s prefill).
- Results: acceptance on math 0.32 -> 0.75 (0.80 with draft 24/32); verify beats expert-alone there (26.9 vs 25.4 tok/s) - first outright drafting win. Prose still trails (greedy drafts diverge stylistically; temp 0 helps math, hurts prose). The 0.8B also routes better than SmolLM2 (classifies explain-y prompts as hard).
- Next levers, in order: use the MTP head to halve draft cost; domain-aware verify-vs-expert dispatch; T16 overlap.

## Extensive benchmark (2026-08-09)

- ADTC profiler pinned at `7adbe08f` (v1's SHA), isolated at `bench/.venv-profiler/` per CLAUDE.md GPL rule; llama-cpp-python needed the full mac toolchain flag set PLUS `-DLLAMA_OPENSSL=OFF` (same x86 Homebrew OpenSSL trap as the main build). Submission schema rejects `domain: education`; Muta's track is `math_scientific_reasoning`.
- 39-config serialized sweep (scripts/sweep_duo.py) + 14-question accuracy suite (11 configs, one process per question) + official profiler runs on all 3 raw models. Official vs harness generation rates agree within ~10% - the two instruments cross-validate.
- Scoring per the profiler README formulas exactly (scripts/score_bench.py); S_acc imputation for unmeasured variants is dagger-flagged. Headline: qwen/front-alone wins S_total 83.0; ALL 39 configs saturate S_perf=100, so the official formula is decided by S_acc and S_eff. Official per-model scores: 0.8B 79.6 > 4B 72.6 > 135M 70.3.
- Full analysis in docs/BENCHMARK_REPORT.md (6 plots, bench/plots/). Key measured curves: verify acceptance 0.26-0.39 (SmolLM2) vs 0.55-0.72 (Qwen0.8B) across ALL setting variants; accuracy floor 0.571 (135M alone) lifted to 0.86-0.93 by every duo mode; expert's sole accuracy miss is a token-cap artifact on its verbose derivation.

## Gate results

- G1 (identity repack, greedy byte-identical): PASS (2026-08-09)
- G2a (byte-level bundle verification, all KVs + 698 tensors sha256): PASS (2026-08-09)
- G2b (bundle+prefix identity vs stock, x2 models x2 modes): PASS (2026-08-09)
- G2c (perf parity within +/-5%, same-binary comparison): PASS (2026-08-09; front-pp noisy but favorable)
- G3 (router quality, tau sweep): PASS - tau=0, 87.5% (2026-08-09)
- G4 (seam self-test, 5 turns >= 390 tokens): PASS - front strictly canonical 5/5; expert 4/5 + 1 benign self-segment case (2026-08-09)
- G5 (co-draft liveness, 10 turns): PASS - 20/20 selftests OK, 0 resyncs, no crash/stall (2026-08-09)
- G6 (perf matrix + predicted-vs-measured): DONE - bench/results.md (2026-08-09)
- G7 (peak RSS < 6.5 GB all rows): PASS - max 5.74 GiB; duo ~= expert-alone + 0.4 GiB (2026-08-09)
- Patches exported to patches/: DONE (re-exported after T-series commits)
- T16 overlap: deferred with quantitative justification (see POC_REPORT known-limits)
