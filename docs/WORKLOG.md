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

## Phase 5 — Streaming

### Task A1 (S0.1)

- D (disk bandwidth): plan said bind mounts are virtiofs, "wrong IO class for gates" (`docs/STREAMING_IMPL_PLAN.md:30`, worded as O_DIRECT not being viable there) -> measured: `dd iflag=direct` actually **succeeds** on the repo bind mount (virtiofs), at 2901.9 MB/s cold (post `drop_caches`), vs 2977.0 MB/s cold on the `muta-models` named volume + `iflag=direct` -> the two numbers are close to each other and far below the buffered/cached-ceiling number (7188.3 MB/s), which is evidence the virtiofs read genuinely bypassed cache rather than silently falling back to buffered I/O against an already-warm host-side cache -> kept the plan's conclusion (gates use the named volume) but corrected the reason logged in `docs/DISCOVERY.md` S0: it's not that O_DIRECT is rejected on virtiofs in this Docker Desktop version (29.1.3), it's that the volume is the VM-native block path with no host-macOS caching layer to reason about. Full D table (page size, THP, kernel) in `docs/DISCOVERY.md` S0.

### Task A2 (S0.2)

- gguf import: `docs/STREAMING_IMPL_PLAN.md:93` and `task-A2-brief.md:13` both specify `sys.path.insert(0,'llama.cpp/gguf-py')` **unconditionally** — neither has any "only if import fails" or other conditional wording. Confirmed this unconditional form is load-bearing, not merely tidy: `.venv/lib/python3.12/site-packages/gguf/` already has a plain, non-editable `gguf==0.19.0` install (`pip show gguf`; no `direct_url.json`/`.egg-link` in its `dist-info`, so not an editable install; neither `pyproject.toml` nor `Makefile` declares an explicit `gguf` dependency, so its presence here is most likely a transitive pull by some other installed package), and a bare `import gguf` in this venv **succeeds** against that stale package rather than raising `ImportError`. A conditional "insert the path only if the bare import fails" strategy would therefore have silently used the wrong, older `gguf-py` every time. The two versions differ in `gguf_reader.py`: this tree's copy (`llama.cpp/gguf-py/gguf/gguf_reader.py:270-271`) added a `GGML_MAX_DIMS` bounds check and (`:332-335`) switched `n_elements` from `np.prod(dims)` (silently overflow-prone on `uint64`) to a pure-Python-int accumulation; the pip-installed package has neither. `scripts/layer_sizes.py:24-30` implements the plan's unconditional form as written: it prepends `llama.cpp/gguf-py` to `sys.path[0]` before ever importing `gguf`, so this tree's copy always wins regardless of what else is installed (verified via `gguf.__file__` resolving into the worktree, not `site-packages`). No numeric difference for this task's tensors either way (all well within the safe integer range), but the unconditional form is the only one that reliably reads "this tree's version" — recorded here as ground truth for later tasks reusing this import pattern.

### Task A3 (S0.3)

- Instructions said step 4 (`madvise(C, MADV_WILLNEED)` from a second thread, main thread polls mincore every 50 ms / 10 s timeout) should "report effective prefetch bandwidth and whether the madvise CALL itself blocked" (`task-A3-brief` resolutions, step 4) — implicitly assuming `WILLNEED` succeeds within the window. Measured (`scripts/stream_probe.c` step 4, container run): the call itself is non-blocking (0.12 ms, confirming R10's "does not block" expectation) but mincore **never reached 95%** within the full 10 s timeout — only 0.5% resident. A follow-up diagnostic (ad hoc Python `mmap.madvise(MADV_WILLNEED)`, same `cgrun 3g` container class, not committed — throwaway `/tmp` script, deleted after) confirms this is not a slow-ramp effect that just needed more time: `memory.current` rose ~1.09 MB in the first ~1 s after the call and then flatlined for a further 20+ s of polling; a subsequent explicit touch of the same region still paid the full cold-read cost (195 ms for 256 MiB ≈ 1.3 GiB/s, i.e. disk speed, not RAM speed) — proof the region was genuinely never warmed beyond that small initial burst.
- **Task review (post-A3) caught a wrong-attribution bug**, Important: `docs/DISCOVERY.md`, this file, and `task-A3-report.md` all stated step 4 added "+663,552 B to `memory.stat`'s `file` counter" — that number is actually the row's `memory.current` delta (the gate metric, correct in the table's own delta column), not `file`'s. The real `file` delta, computed from the previous row's `cg_file` reading (27,881,472 B) to step 4's own (29,257,728 B in the fix run; 29,360,128 B in the original), is **+1,376,256 B** — reproduced byte-identically across both runs despite `memory.current`'s delta differing (663,552 B originally, 811,008 B in the fix run). Fixed all three documents to attribute each number to its correct counter. Newly-visible observation, recorded rather than glossed over: `memory.current` rising less than `file` in the same window means some non-file charge (565,248 B in the fix run) was concurrently released — most likely because `record_row()` samples `rss_kb`/`stat_file` *after* it has already captured the row's own `memory.current` "after" value (and, for step 4, after one extra `mincore_percent()` call in between), so the two readings are not simultaneous snapshots. The gap's own size varying run-to-run while `file`'s step-4 delta reproduces exactly supports "sampling-timing skew", not a real accounting conflict between the two counters.
- **Task review flagged the single-`WILLNEED` finding as under-evidenced**, Important: one 256 MiB `WILLNEED` call going nowhere is also consistent with an untested competing hypothesis — a per-call readahead cap (`force_page_cache_ra` chunking against `bdi->io_pages`/`ra_pages`, reset on every fresh `madvise()` call) — under which *chunked*, repeated `WILLNEED` calls would work, a materially different conclusion for the residency manager's prefetch verb than "`WILLNEED` is inert". Also: a 0.12 ms return for a 256 MiB call (submitted in the caller's context on Linux) is itself evidence of a cap/short-circuit, not evidence readahead "continued async" as the original write-up implied. Added `scripts/stream_probe.c` step 4b: evict C to a clean 0.0%-resident baseline, then `WILLNEED` it in 128 calls of 2 MiB from a second thread, polling mincore exactly as step 4. Result (container run): **62.5% resident after the same 10 s window** — a ~120x improvement in `file`-counter-based prefetch rate (0.131 MiB/s single-call vs ~15.9 MiB/s chunked) and ~209x in raw `memory.current` growth (0.077 MiB/s vs ~16.1 MiB/s), confirming the per-call-cap hypothesis. But chunked `WILLNEED` still didn't reach 95% in 10 s, and its ~16 MiB/s rate is still ~150x slower than an explicit touch (2453.5 MiB/s this run). Rewrote the DISCOVERY §S0.3 WILLNEED paragraphs to the accurate middle conclusion — neither "works" nor "fully inert": chunking measurably helps, but touch/read remains the residency manager's actual prefetch mechanism, not chunked `WILLNEED`.
- **Task review flagged step 5's confound as a live wrong-verdict risk**, Important: had step 3 failed, the verdict logic would have fallen through to step 5's number, which — before this fix — was confounded by region C being only 0.5% resident going in (step 4's `WILLNEED` failure), so a real primary-primitive failure could have silently printed `VERDICT: NONE`/`BLOCKED` off bad step-5 data instead of a fair fallback test. Fixed `scripts/stream_probe.c`: an unconditional warm guard (`if (mincore(C) < 95%) touch(C)`) now runs right before step 5's own before/after window, placed after step 4b so the WILLNEED measurements stay intact; step 5's row and the verdict block both now print the pre-step residency alongside the reclaimed fraction, and the verdict block prints step 5's fraction unconditionally (not only when step 3 fails), closing the silent-wrong-verdict path. Re-run (container, fresh `drop_caches`+`cgrun 3g`): step 4b only reached 62.5%, so the guard's touch fired, bringing C to 100.0% resident before step 5 — step 5 then reclaimed exactly -268,435,456 B (100.0%), matching step 3 byte-for-byte. The `MAP_FIXED` fallback is now genuinely, independently validated (previously only asserted "not needed, untested"). Go/no-go unchanged (still `PRIMARY`, decided by step 3).
- `-Wformat-truncation=` (gcc 11.4.0, not raised by AppleClang 21.0.0 on macOS): a `char rss_s[16]` buffer passed through a shared `fmt_ll()` helper that formats an arbitrary `long long` via `%lld` was flagged as theoretically truncatable (worst case up to 20 chars for `LLONG_MIN`) even though no value in this program's actual range (RSS/cgroup byte counts) would ever hit it. Fixed by widening `rss_s` to 24 bytes (matching the other `fmt_ll` buffers in `print_table()`, `scripts/stream_probe.c`) rather than suppressing the warning — zero-warnings-on-both-platforms was a hard requirement, and the fix is a correct, not cosmetic, size increase.

### Task B1 (S1a)

llama.cpp branch `streaming`, forked from `master` tip `01f58cd`: `2a42d67` (S1a-pre) + `c528ee2` (S1a).

- **cstdarg fix (COMMIT 1, carried finding from Task A1):** `tools/duo/duo.cpp`'s `jtrace()` uses `va_list`/`va_start`/`va_end` (lines 168-171) without including `<cstdarg>`. AppleClang pulls the declarations in transitively (macOS `build-noblas` never showed the failure); GCC in the streaming container does not. One-line fix, inserted alphabetically between `<cinttypes>` and `<cmath>`.
- **Bundle-wide suppression rationale (COMMIT 2, adversarial finding B3, task-B1-brief.md item 3), corrected in the post-review fix round below:** the no-populate/no-WILLNEED path applies to *every* load with `bundle_prefix` set, not only loads that also pass `--stream-weights`. A non-streamed tier (e.g. front or easy loaded from the trio bundle without streaming) that let its `llama_mmap` ctor `MAP_POPULATE`/`WILLNEED` the whole file would charge the cgroup for every other tier's bytes, not just its own. `llama_model_loader::stream_no_populate()` (`stream_weights || !bundle_prefix.empty()`) governs this suppression (the `prefetch` argument to the `llama_mmap` ctor) and also gates `load_all_data()`'s post-load sweep. It does **not** also govern the mmap ctor's `stream` argument (the `POSIX_MADV_RANDOM`/`MADV_NOHUGEPAGE`/skip-`POSIX_FADV_SEQUENTIAL` access-pattern policy) — see the fix round: that policy is scoped to `stream_weights` alone, since it actively hurts a plain (non-streamed) bundle load's sequential read pattern, which the first-pass code got wrong.
- **Discovery not in the brief — `-fit`'s no_alloc probe collides with the guard:** `common/fit.cpp:57` (`common_get_device_memory_data_impl`, driven by `common_params::fit_params`, default `true`) does a preliminary `llama_model_load_from_file` call on a **copy** of `mparams` with `load_mode` forced to `LLAMA_LOAD_MODE_NONE` and `no_alloc=true`, purely to read back a memory-breakdown estimate before the real load. Since the copy inherits `stream_weights=true` from the real `mparams`, the brief's guard as literally specified ("if `stream_weights` and `load_mode != MMAP`") fired on this probe on every default `--stream-weights` invocation — `common_fit_params` catches the resulting exception and degrades silently (so functionally harmless: the real load still succeeds with byte-identical output, verified below), but it printed a spurious `E`-level `stream_weights requires LLAMA_LOAD_MODE_MMAP...` line every time and silently skipped `-fit`'s memory-breakdown pass whenever streaming was requested. Fixed by exempting `no_alloc` loads from the guard (`src/llama.cpp` ~:311, `!params.no_alloc &&` added to the condition): a `no_alloc` load never reaches `use_mmap`'s populate/prefetch path regardless of `load_mode`, so the guard's own rationale doesn't apply to it. Confirmed the genuine-misuse path still fails cleanly (`--stream-weights --no-mmap` -> clean `E` log + `unable to create context`, no crash).
- **Line-number drift vs the brief's recon (all minor, tree is still b10331+16 basis):** `llama-model-loader.h`'s used-range member is `mmaps_used` (plural), not `mmap_used` — the brief's own text uses the plural form as `mmap_used` in one place; the per-call local reference `auto & mmap_used = mmaps_used[weight->idx]` (singular) inside `load_all_data` is the likely source of the shorthand. Its min/max update is at `llama-model-loader.cpp:1587-1589`, one line earlier than the cited `:1588-1590`. `get_mapping_range` (`llama-model-loader.cpp:1395-1410`) and `init_mappings` -> `ml.init_mappings(true, ...)` call site (`llama-model.cpp:1538`) matched exactly. `common_init_from_params`'s warmup `if` (`common/common.cpp:1428`) and `common_init_result`'s ctor (`:1234`) also matched exactly.
- **Verification (first pass, numbers superseded by the fix round below):** baseline captured pre-patch (`build-noblas`, macOS, BLAS-off, tip `01f58cd`) for (i) `models/Qwen3.5-4B-Q4_K_M.gguf -no-cnv --temp 0 --seed 42 -n 64` and (ii) `bundle/muta-duo-q.gguf --bundle-prefix m1.` (same args), then rebuilt after both commits and diffed. All stdout-vs-stdout comparisons (stderr, which carries timings, was never diffed). Gate b (no new flags, byte-identical stdout): PASS for both (i) and (ii). (ii)'s single-run eval throughput reading (31.4 -> 17.9 tok/s) turned out to be two things conflated: a real regression (root-caused and fixed below, finding 2) plus ordinary single-run noise — see the fix round's 3-rep remeasurement. Gate c (`--stream-weights --max-ram-mib 2048` on (i)): PASS — byte-identical to baseline, `stream_weights is enabled, disabling warmup` log line present, no spurious errors after the no_alloc fix. Gate d (`scripts/stream_env.sh build`, GCC container): PASS — all four targets (`llama-completion`, `llama-duo`, `llama-bench`, `llama-speculative-simple`) built clean, `llama-duo` compiling proves COMMIT 1. Gate e: `git -C llama.cpp status` clean, exactly 2 commits over `01f58cd`.

### Task B1 fix round (post-review, adversarial findings 1-3)

Task review on the first-pass `S1a` commit found 1 Critical + 2 Important defects, all in the sweep/madvise machinery, none in the flag-plumbing or guard work. Fixed in one commit, `c528ee2` remains the base; the fix lands as a new commit on `streaming`.

- **Finding 1 (Critical) — the sweep reclaimed zero bytes on both platforms.** `discard_range()` used `posix_madvise(POSIX_MADV_DONTNEED)` alone. Two independent problems: (a) POSIX defines `POSIX_MADV_DONTNEED` as advisory-only (it must not discard data), which is a different contract from Linux's destructive `MADV_DONTNEED` — `scripts/stream_probe.c`, the actual instrument that validated the eviction primitive in Task A3, uses the raw `madvise(2)` syscall, never `posix_madvise`, specifically because of this; (b) even the correct primitive is only half the story — `docs/DISCOVERY.md` S0.3 step 2 measured `madvise(MADV_DONTNEED)` **alone** (before any `fadvise`) at Δ=0, uncharging nothing; the KEY measurement (step 3) is `fadvise(DONTNEED)` issued *after* `madvise(DONTNEED)`, and step 3b independently proves the ordering is required, not incidental (`fadvise` before `madvise` also uncharges nothing). The `fadvise` half was entirely absent from the first-pass code, and `llama_mmap` had no `fd` to make the call with. Fixed: `discard_range()` now issues the raw `madvise(addr, len, MADV_DONTNEED)` syscall under `#ifdef __linux__` (an honest no-op elsewhere — Darwin's `MADV_DONTNEED` is advisory-only per S0.3's own macOS run, mincore stayed 100% resident through every step there); a new sibling `llama_mmap::fadvise_discard(int fd, size_t first, size_t last)` issues `posix_fadvise(fd, first, len, POSIX_FADV_DONTNEED)`, also Linux-only. The `load_all_data()` call site is restructured to the validated order: `discard_range()` (madvise) -> `unmap_fragment()` (the pre-existing unconditional munmap, further belt-and-suspenders PTE removal) -> `fadvise_discard()` (fd from `files.at(idx)->file_id()`, already in scope) -- fadvise strictly after the PTEs are gone, mirroring S0.3 step 3b-iv.
- **Finding 2 (Important) — the RANDOM/NOHUGEPAGE/skip-SEQUENTIAL policy was applied to every bundle load, not just streamed ones.** A plain `--bundle-prefix` load with no `--stream-weights` (llama-duo's default, product path) wants ordinary sequential readahead for its load and its own demand-paged decode; forcing `POSIX_MADV_RANDOM` (which tells the kernel *not* to read ahead) onto that load actively hurt it. This is what a chunk of the first pass's own "31.4 -> 17.9 tok/s" WORKLOG entry was really measuring (see remeasurement below), not merely noise. Fixed: `init_mappings()`'s `llama_mmap` ctor call now passes `stream_weights` (not `stream_no_populate()`) as the `stream` argument. The populate/`WILLNEED` suppression (the `prefetch` argument) is unchanged and still keyed on `stream_no_populate()` -- that half of B3's rationale (don't `MAP_POPULATE` a shared bundle file for a non-streamed tier) is untouched by this fix.
- **Finding 3 (Important) — the sweep's own gate disagreed with `stream_no_populate()`.** The sweep was gated on `!bundle_prefix.empty()` alone, so a `--stream-weights` load of a plain single-file model (gate (c)'s own configuration) never got swept, contradicting the WORKLOG/report's claim that it keyed off `stream_no_populate()`. Fixed: the gate is now literally `stream_no_populate()`. No separate magnitude-based "almost the whole file" check was added -- `discard_range()`/`fadvise_discard()` already collapse to a zero-length, page-aligned no-op internally (the same `align_range()` idiom `unmap_fragment()` already used) whenever the "outside" range is empty or sub-page, which is what naturally happens for a genuine single-model load whose used range already covers ~the whole file.

**Re-verification after the fix (stdout-only comparisons throughout; stderr, which carries load/eval timings, is never part of any identity diff):**

- Gate b, (i) no flags: byte-identical to baseline. Gate b, (ii) no flags, 3 serialized reps (macOS `build-noblas`, same seed/prompt): eval throughput **32.86 / 32.74 / 32.14 tok/s**, all byte-identical stdout to baseline (baseline was 31.42 tok/s single-run) -- the earlier "17.9 tok/s" reading is now explained: finding 2's RANDOM-policy-on-a-plain-bundle-load bug was the dominant real cause, and the "31.4 -> 30.4" figure that had appeared in `task-B1-report.md` (a *different* single run, from a rebuild in between the two WORKLOG/report writeups) was consistent with the fixed behavior mostly by accident -- both pre-fix single-run numbers undersold how bad and how noisy the bug was; the fix removes the effect entirely and 3 reps land within 2% of each other and slightly above the (single-run, colder-cache) baseline.
- Gate c: byte-identical to baseline, `stream_weights is enabled, disabling warmup` present, 0 `E`-level lines.
- Container rebuild (`scripts/stream_env.sh build`): all 4 targets clean, exit 0.
- **Direct sweep observation** (new, closes the "no direct measurement" gap): `scripts/stream_env.sh drop_caches` then `cgrun 3g /build/bin/llama-completion -m /models/muta-trio.gguf --bundle-prefix m0. -no-cnv --temp 0 --seed 42 -n 1 -p "Hi"` (front = SmolLM2-135M, the trio's smallest tier; front's own tensor payload per S0.4's table is `[23,721,280, 103,668,480)` = 79,947,200 B = 76.2 MiB). Result: `memory.peak=418,635,776 B` (399.2 MiB), `memory.stat`: `anon 397,312 B`, **`file 117,268,480 B` (111.8 MiB)**. This matches the review's expectation ("front's used range (~100 MB) + overhead, NOT the whole 3.4 GB bundle") almost exactly: 111.8 MiB is ~29x smaller than the 3.4 GB (3,396,095,296 B) bundle. The ~35.6 MiB gap above front's own 76.2 MiB tensor payload is consistent with ordinary process/shared-library overhead (resident code/rodata pages of `libllama`/`libggml`/`libc`/`libstdc++`/`ld.so`, which are themselves cgroup-charged as `file` memory and are not something the weight sweep touches or should touch) rather than any bundle leakage; a before/after (broken-sweep-vs-fixed) contrast run was not taken as it would have required reverting and rebuilding, and the review only asked for one post-fix observation.

### Task B2 (S1b)

llama.cpp branch `streaming`: `e7b853e` (`S1b: llama-residency module, verbs, ledger, selftest`), 4 commits over `01f58cd`.

- **Ring/window split decision (recorded because the brief left it open between B2 and B3):** the ring and its window state machine live in **B2**, as `llama_residency_on_gate_post(res, unit)` declared in `src/llama-residency.h` (internal header, not `LLAMA_API`). It evicts every resident streamed unit outside `[u, u+W]` in ring-index arithmetic and queues prefetches for the window ahead of the cursor; it runs on the *caller's* thread, taking only the manager's mutex and appending to its FIFO — no syscall ever leaves the compute thread. What stays for **B3** is purely the graph seam: `llama_residency_sched_eval_cb` is a deliberate stub in this commit (`ASK -> false`, `POST -> true`, i.e. `return !ask`), so no node is observed and no graph is ever aborted. B3 adds node->unit resolution and calls `on_gate_post` from the real callback. The selftest drives `on_gate_post` directly for 2 full ring cycles, so the state machine is verified before any graph work exists — that is the whole reason for splitting it this way.
- **Discovery, blocking, not in the brief — `use_extra_bufts` (weight repacking) makes streaming impossible.** The first `--stream-weights --residency-selftest` run refused with `residency: tensor 'token_embd.weight' is not backed by the model mapping`. Root cause: `llama_model_base::load_tensors` builds its buffer-type list with `params.use_extra_bufts` (default `true`), which admits the CPU repack buffer type; `llama-model-loader.cpp`'s per-tensor loop then takes the `ggml_backend_tensor_set(cur, data, 0, n_size)` branch instead of `ggml_backend_tensor_alloc(buf_mmap, cur, data)` for every tensor in the repack context, i.e. it **copies** the weights into a freshly allocated anonymous buffer. Measured on the 4B model (macOS `build-noblas`, `-v`): `CPU_Mapped model buffer size = 2603.50 MiB` **plus** `CPU_REPACK model buffer size = 2599.83 MiB` — the model charged twice, with 2599.83 MiB of it in memory that is neither evictable (no file behind it) nor faultable-back-in. This is not macOS-specific: the aarch64 gate container repacks the same q4_K/q5_K/q6_K/q8_0 tensors, and x86 has its own repack/AMX paths. Streaming and repacking are mutually exclusive by construction. Fixed at `src/llama-model.cpp:1277-1290`: `use_extra_bufts` is forced off (with an `LLAMA_LOG_INFO` line) when `params.stream_weights` is set — same shape as B1's forced-off warmup. Non-streamed loads keep repacking, which is why the no-flag regression stays byte-identical.
- **Discovery, blocking, not in the brief — `-fit` sizes the KV cache to *host* free memory and OOM-killed the gate.** First gate attempt: `exit_status=137 OOMKilled=true`, `memory.peak` exactly 3,221,225,472 B (the 3g cap). The residency ledger itself was correct and had already printed (`R_pin 1126.7 MiB`, `pinned 1094.7 MiB`); what blew up was `llama_context`: `n_ctx = 113408` -> `CPU KV buffer size = 3544.00 MiB`. `common_params::n_ctx` defaults to `0` ("the context the model was trained with" = 262144 for this model, an 8 GiB KV cache), and `common_fit_params` — whose own header says it "assumes system memory is unlimited" and fits to *free device memory*, which inside a cgroup is the VM's free RAM, not the cap — only grew it to 113408. Neither knob has any idea `--max-ram-mib` exists. Fixed at `common/common.cpp:1234-1246`: when `stream_weights` is set and `n_ctx == 0`, `n_ctx` is pinned to `params.fit_params_min_ctx` (4096, the `--fit` floor) with an explanatory log. This also stops `-fit` touching the context at all, since `common_fit_params` only rewrites a context size of exactly `0` (`common/fit.h:19`) — so one assignment fixes both halves without disabling `-fit`. Result: `n_ctx = 4096`, `KV buffer 128.00 MiB`, gate passes. **Left open for B4:** the 640 MiB default `reserve_mib` does not actually cover this context's non-weight memory — KV 128 MiB + compute 504 MiB = 632 MiB is only just inside it, and nothing enforces the relationship; the manager cannot check it because it is built before the context exists.
- **Measured defect in the prefetch verb, fixed and quantified — B1's whole-mapping `POSIX_MADV_RANDOM` costs the touch loop 14.6x.** A3 measured the touch loop at ~2.4 GB/s, but `scripts/stream_probe.c` mmaps with default advice, whereas a streamed load sets `POSIX_MADV_RANDOM` over the whole mapping (S1a). `VM_RAND_READ` suppresses both readahead and fault-around, so a whole-unit sweep degenerates into one synchronous single-page fault per page. First gate run measured the verb at **341.6 MiB/s** (64.5 MiB in 188.89 ms) with a 46-step ring walk taking 10.23 s. Fix (`res_prefetch_hint`, `src/llama-residency.cpp:647-678`): issue `posix_madvise(POSIX_MADV_NORMAL)` over the unit's own outward-aligned ranges immediately before the touch loop, ahead of the chunked `MADV_WILLNEED` hints. RANDOM stays the mapping-wide default (nothing may read ahead into a range the manager did not ask for); it is only lifted range-by-range for the range being prefetched. Re-measured, same container, same `drop_caches`: **4991.5 MiB/s** (64.5 MiB in 12.93 ms), ring walk 10.23 s -> 1.83 s, and — the thing that had to be checked — **no residency regression**: ring-walk peak mincore-resident stayed at exactly 211.0 MiB (== 3 window units) in both runs, `memory.peak` 1,681,932,288 -> 1,681,686,528 B (0.01% lower). The re-admitted readahead overshoot past a range end is bounded by one readahead window and is invisible next to the ring's own slack.
- **Log-visibility deviation:** the ledger table and the selftest report are `LLAMA_LOG_INFO`, which is correct llama.cpp style, but `common_log_default_callback` maps `GGML_LOG_LEVEL_INFO` to `LOG_LEVEL_TRACE` (`common/log.cpp:441-459`) against a default threshold of `LOG_LEVEL_INFO` — so every llama-side INFO line, including all of llama.cpp's own load banner, is invisible without `-lv 4`. Two targeted fixes rather than distorting log levels: (1) `--residency-selftest` raises the threshold to `LOG_LEVEL_TRACE` before building the manager (an explicit diagnostic run should be readable without a second flag, and it always `exit()`s straight after); (2) a one-line `COM_INF` summary built from `llama_residency_get_info()` after a successful init, so an ordinary `--stream-weights` run is not told nothing at all. Refusals were already visible (`LLAMA_LOG_ERROR` -> `LOG_LEVEL_ERROR`).
- **Ledger inputs vs the brief:** `mlock_front_mib`/`resident_other_mib`/`mlock_pins` are in the API and in the solver's arithmetic but have no CLI flag yet — they are the S3 cross-model inputs and there is nothing to fill them from until a second tier exists. `pin_budget "auto"` maps to `-1`; a non-numeric value warns and falls back to auto rather than `atoi`'s silent `0`.
- **b_layer_max fixed point:** the brief specifies the window term over the *streamed* layers' max, which depends on how many layers are pinned, which depends on the window term. Solved by iterating (bounded at 16 passes); each pass can only shrink `b_layer_max`, so it terminates. For the 4B model it converges immediately — 70.3 MiB both before and after, since blk.28/29/30 are all 70.3 MiB and always streamed.
- **Verification.** (a) both builds clean, zero warnings attributable to this task (macOS `build-noblas` + `scripts/stream_env.sh build`, all 4 container targets, exit 0). (b) macOS informational: table sanity, pins 100.00% resident, touch and prefetch >= 95% all PASS; evict warn-only (`blk.20` stayed 100.00% resident — Darwin's `MADV_DONTNEED` is advisory, A3); ledger table printed; ring walk peak *tracked* 211.0 MiB vs limit 281.3 MiB PASS, peak *resident* informational; `residency selftest: PASS`, exit 0. (c) **PHASE B GATE (container, `cgrun 3g`): `residency selftest: PASS`, exit 0, `OOMKilled=false`** — evict `100.00% -> 0.00%` resident (hard assert on Linux), prefetch 4991.5 MiB/s at 100.00% resident, ring walk 46 steps with peak tracked == peak resident == 211.0 MiB against a 281.3 MiB limit, `memory.current` 1,668,591,616 B, `smaps_rollup Rss 1,616,064 kB`. `memory.peak = 1,681,686,528 B (1604 MiB)` against the 3g cap and under the declared 2048 MiB budget; `memory.stat file = 1,368,436,736 B (1305.0 MiB)` == pinned 1094.7 + window 211.0 MiB **exactly**, i.e. the cgroup's file charge is precisely the plan the ledger printed. (d) no-flag regression: stdout byte-identical to B1's `/tmp/baseline_i.txt`, 0 `E`-level lines. (e) refusal at `--max-ram-mib 600`: both inequalities printed with numbers (`head-pinned -251.0 MiB < 497.3 MiB`, `head-streamed -678.0 MiB < 0.0 MiB`, plus the `--max-ram-mib >= 1348.3 / 1278.0` each config would need), clean exit 1, no crash.

### Task B2 fix round (post-review, findings 1-4)

Task review of `e7b853e` found 1 Critical + 3 Important defects. Fixed in one commit, `ae76ab0`.

- **Finding 1 (Critical) — the ring ran at the REQUESTED window, not the ledger's CHOSEN one.** `res_solve()` reduces W on a tight budget and recorded that only in `r->info.window`, while all four runtime consumers read `r->params.prefetch_layers`: init's first-window enqueue, `resume_async`, `on_gate_post`, and the selftest's own ring-walk bound. On any budget where the solver drops W 2 -> 1 the state machine therefore kept one whole `b_layer_max` more resident than the plan the ledger printed — and because the selftest computed its `(W+2)*b_layer_max` limit from the same wrong W, the limit inflated in lockstep and the assert could not fire. Fixed: all four sites read `info.window`; `params.prefetch_layers` is now documented at the struct as the *requested* value, read only by `res_solve()`. **New coverage, computed from the ledger's own constants** (head 497.3, `b_layer_max` 70.3, misc 0.010, reserve 640 MiB): head-pinned needs `max_ram >= head + misc + (W+2)*b + reserve` and head-streamed `>= misc + (W+1)*b + head + reserve`, so the four thresholds are 1418.5 (pinned W=2), 1348.2 (streamed W=2 and pinned W=1, coincidentally equal) and 1277.9 (streamed W=1) — i.e. the solver reduces W 2 -> 1 exactly on **`--max-ram-mib` in [1277.9, 1348.2)**. Ran the container selftest at **1300**: `no plan fits at W = 2, reduced to W = 1`, config head-streamed, 0 pinned layers, 33 ring units, and the 66-step ring walk holds **peak tracked == peak mincore-resident == 567.6 MiB == head 497.3 + one layer 70.3, i.e. exactly W+1 units at the CHOSEN W**, against the chosen-W bound 708.3 MiB. `memory.peak` 906,473,472 B (864.5 MiB), well inside the 1300 MiB budget. Under the bug this walk would have held three units (up to 637.9 MiB) against an inflated 778.5 MiB limit and still "passed".
- **Finding 2 (Important) — `POSIX_MADV_RANDOM` was lifted permanently.** `res_prefetch_hint()` set `POSIX_MADV_NORMAL` per range and nothing put RANDOM back, so after one ring cycle every streamed range was NORMAL for good: B3's compute-path demand faults would read ahead into pages the manager had just evicted, and S1a's mapping-wide RANDOM policy would quietly cease to exist. The code also contradicted its own comment and this WORKLOG, both of which claimed the lift was per-sweep. Fixed: new `res_rearm_random()` restores RANDOM over the same outward-aligned ranges immediately after `res_touch()` returns — the pages are already resident at that point, so `madvise` only governs *future* faults and the restore costs nothing that was just paid for. **Re-measured with the re-arm in place: 4018.2 MiB/s (at 2048) and 4461.1 MiB/s (at 1300), vs 341.6 MiB/s with RANDOM left in force — ~12x, not the 14.6x this WORKLOG previously claimed.** The earlier 4991.5 MiB/s figure was measured with NORMAL latched on from an earlier sweep and is superseded; the honest number for the shipped code is ~4.0-4.5 GiB/s, and it remains an upper bound on disk speed for the reason already recorded (`drop_caches` clears the linuxkit VM's page cache, not the host macOS cache behind the volume).
- **Finding 3 (Important) — PIN's completion could clobber an eviction.** PIN settled its unit state with an unconditional `store(RES_RESIDENT)` while PREFETCH used `compare_exchange_strong(QUEUED -> RESIDENT)`. `suspend()` enqueues an EVICT for pinned units too and marks them EVICTED at enqueue time, so a PIN already in flight could land afterwards and flip EVICTED back to RESIDENT with nothing to correct it — precisely the bookkeeping S3's tier switch has to trust. Fixed: PIN uses the same CAS.
- **Finding 4 (Important) — the `memory.stat file` headline was wrong three ways, and is withdrawn.** The previous entry claimed `file = 1,368,436,736 B (1305.0 MiB)` == pinned 1094.7 + window 211.0 MiB "**exactly**". It is not exact (1094.7 + 211.0 = 1305.6-1305.7 vs 1305.04), it is not the right reading (`cgrun` prints `memory.stat` *after* the process exits, which is why the same run's in-process `smaps_rollup Rss` is 1578 MiB while `file` is 1305 MiB and `anon` is 384 KiB — the KV and compute buffers were allocated and then freed at exit, not "never touched" as claimed), and it leaves no room for the ~30 MiB of shared-library file charge B1 measured in the same cgroup. **The evidence that actually proves residency, all in-process and all from the fixed code:** ring-walk peak mincore-resident == peak tracked across every step (211.0 MiB over 46 steps at 2048; 567.6 MiB over 66 steps at 1300), evict measured `100.00% -> 0.00%` resident as a hard Linux assert, and `memory.peak` 1,681,256,448 B (1603.4 MiB) at 2048 / 906,473,472 B (864.5 MiB) at 1300, both under cap and under the declared budget. **Caveat that belongs with it:** the selftest gate exits before decoding, so `reserve_mib` versus live KV+compute at peak is still untested — Milestone A is the first run that will test it.
- **Re-verification after `ae76ab0`:** macOS selftest at 2048 **PASS** (peak tracked 211.0 MiB, evict warn-only as before); macOS at 1300 **PASS** (reduced-W path, `pins resident not measurable` reported rather than failed); container at 2048 **PASS**, exit 0, `OOMKilled=false`; container at 1300 **PASS**, exit 0, `OOMKilled=false`. Container build clean, 0 errors, 0 warnings.

### Task B3 (S2) — the cb_eval gate

llama.cpp branch `streaming`: `c86da62` (`S2: cb_eval gate - sliding-window evict/prefetch`), 5 commits over `01f58cd`. **This is the commit that makes streamed decode actually work**: B2 built the ring and drove it from a selftest, B3 drives it from real graph execution.

- **Gating design — why POST-anchored, and why no graph-start signal is needed.** The scheduler's contract (`ggml/src/ggml-backend.cpp:1730-1767`, read, not assumed) is a coalescing loop: `ASK(t, true)` is called on node after node; returning false lets the scheduler swallow the node into the current chunk, returning true ends the chunk **at** `t`, so nodes `[j0..j1]` — `t` included — are computed, the backend is synchronized, and `POST(t, false)` follows; returning false from POST aborts the graph, so POST here always returns true. The gate anchors on **POST** because that is where the ordering is free: at the POST of the first node touching unit N, every node ahead of it in the graph has already run, so all of unit N-1 is provably finished and safe to evict, while unit N itself is inside the window `[N, N+W]` and stays. **ASK is the filter, not the event** — the scheduler's lookahead means ASK can probe far ahead of what has executed, so the only sound test there is "is this a streamed unit this graph has not already gated on", which is exactly the rule that produces one gate per unit. There is deliberately **no per-graph reset**: `llama_residency_on_gate_post()` is *absolute rather than incremental* — it evicts every resident streamed unit outside `[u, u+W]` and prefetches everything missing inside it, computed from `u` alone, never consulting the previous gate. A missed boundary, a graph that starts mid-ring, a prefill ubatch that stops early, a KV-shift graph that gates not at all: none can leave the ring in a state the next gate does not correct. `gate_unit` carries across graphs on purpose, so the first gate of graph G+1 fires iff its unit differs from the last one graph G gated on — the normal case, since a graph ends on the last ring unit and the next starts on the first. The one degenerate case is a ring of exactly one unit, where the window is the whole ring anyway and there is nothing to move. **Nothing new blocks**: `on_gate_post` still only takes the manager mutex to append to the FIFO (`res_worker` unlocks around `res_exec`), so no syscall ever leaves a compute thread.
- **Node -> unit without string parsing.** `res_build_units` now also builds `unordered_map<const ggml_tensor *, int32_t> unit_of` over every mapped weight tensor, keyed on pointer. The callback tries each of a node's `src[i]` and each source's `view_src` against it; one level of `view_src` suffices because ggml collapses a view of a view onto the ultimate base at creation (`ggml/src/ggml.c:1777-1779`). Each map entry is cross-checked against its unit's own `[off_min, off_max)` extent at build time, so a unit id space that ever stopped agreeing with the table is a load-time error, not a silent mis-gate at decode speed.
- **The GET_ROWS / MUL_MAT head split.** With tied embeddings `token_embd.weight` **is** the output matrix — `src/models/qwen35.cpp:52` creates the head with `TENSOR_DUPLICATED` and the loader returns the tensor that already exists — so one pointer appears twice in every graph: in the `GGML_OP_GET_ROWS` embedding lookup at the very start, and in the `GGML_OP_MUL_MAT` logits projection at the very end. Only the matmul is the head's real use, so for the head unit anything that is not a matmul resolves to **no unit**. Gating on the lookup would fire the head's window logic at the wrong end of the graph: the head sits last in the ring, so its window wraps to `ring[0]`, and that wrap would happen *before* the first layer instead of after the last one — evicting most of the ring on the way in and again on the way out, every token. The suppressed lookup is then served by ordinary demand faults over the rows it reads (2100 B/token at `n_embd` 2560, q6_K), which is correct and cheap. Note this only bites when the head is *streamed*; in the 2048 MiB config it is pinned, so the split is insurance rather than a live path there.
- **KV-shift / defrag graphs: no gates, verified by reasoning as the brief asked.** `llama_kv_cache::build_rope_shift` (`src/llama-kv-cache.cpp:1836-1886`) touches only K-cache views, the I32 `shift` input, a hadamard `rot` matrix built in the kv-cache context, and `factors` from `llama_model::get_rope_factors` — and `src/models/qwen35.cpp` creates no `rope_freqs`/`rope_long`/`rope_short` tensor at all, so `factors` is NULL for this architecture. None of those pointers is in `unit_of`, so every node resolves to -1, ASK is always false, and the graph runs as one coalesced chunk with zero effect on the ring. (Generalizing: an architecture that *did* carry a per-layer rope weight would gate there and walk the ring pointlessly — wasteful, still correct, because the next real graph's first gate re-anchors the window.)
- **Prefill note, now printed by the ledger.** One graph is built and executed per ubatch and the gate walks the whole ring in each, so `prefill reads ~= ceil(n_prompt/n_ubatch) x streamed_bytes`. That is the design, not a leak — the window is what bounds RAM and holds W+1 units whether the walk runs once or a hundred times — but it does mean prefill is read-bound at the same rate decode is. Logged once at init (llama-side INFO, so `-lv 4` to see it, per B2's log-visibility finding).
- **`MUTA_CB_NOOP` debug hook** lives in `common/common.cpp` where cb_eval is installed, not in the residency module: it swaps in a no-op callback (ASK false, POST true) so the scheduler still walks its per-node callback loop but never chunks the graph and never advances the ring. It warns loudly that `--max-ram-mib` is not enforced in that mode.

**Verification.**

- **Builds:** macOS `build-noblas` and `scripts/stream_env.sh build` (all 4 targets), both exit 0, **0 `error:` lines and 0 compiler warnings** (the 2 "warning" hits in the container log are pre-existing cmake configure notices: ccache absent, cpp-httplib).
- **macOS functional identity:** streamed (`--stream-weights --max-ram-mib 2048 --stream-disk-gbps 2.977`, temp 0 seed 42, `-n 32`) stdout **byte-identical** to the non-streamed run of the same build. Re-confirmed after the final comment-only rebuild. No-flag regression also **byte-identical to B1's `/tmp/baseline_i.txt`** (sha256 `aa7456ec...`), i.e. the B1-era baseline has not drifted.
- **Gate actually fires — direct trace** (macOS, `-lv 5`, `-n 4`): **94 prefetch + 91 evict** verbs. Predicted exactly: 2 (init window) + 4 graphs x 23 ring units = 94 prefetches; 4 x 23 = 92 gates minus the one first gate with nothing yet resident to evict = 91. The wrap is visible in the trace — after `prefetch blk.31` comes `prefetch blk.9`, `prefetch blk.10`. One gate per streamed unit per graph, exactly as designed. Pinned `blk.0..8`, the pinned head and misc never gate.
- **THE FIRST REAL STREAMED DECODE (container, `cgrun 3g`, after `drop_caches`, binary rebuilt from `c86da62`):** exit 0, `OOMKilled=false`. Output **byte-identical (sha256 `fc290ef7...`) to the container non-streamed `--no-repack` control**. **`memory.peak = 1,719,185,408 B = 1639.6 MiB`** against the declared 2048 MiB budget (408 MiB headroom) and the 3g cap; `time -v` Max RSS 1,663,812 kB. Decode **536.65 ms/token (1.86 tok/s)**, prompt eval 246.28 ms/token. Three drop_caches-preceded streamed runs gave `memory.peak` 1,722,572,800 / 1,719,042,048 / 1,719,185,408 B — within 0.2% of each other — and decode 654.08 / 612.28 / 536.65 ms/token (the spread is host noise; the Docker Desktop VM sits at ~200% CPU on this Mac).
- **The ledger's prediction was right to 1.1%:** predicted `s/token = 0.531` (1508.8 MiB / 2.977 GB/s), measured best **0.537**. Effective read rate 2811 MiB/s vs A1's O_DIRECT `D` of 2977 MB/s.
- **Identity is NOT a streaming artifact — the divergence hunt.** The streamed container output differs from the *default* container baseline. That is **repack**, not the gate: `--no-repack` alone, non-streamed, reproduces the streamed text byte-for-byte (sha256 identical), which isolates the cause to B2's Discovery 1 (streaming forces `use_extra_bufts` off; repacked q4_K/q6_K kernels are numerically different on aarch64/GCC). macOS did not show the split within 32 tokens, aarch64-Linux does. **The correct control for every future streamed-identity gate is `--no-repack`, not a bare baseline.**
- **Ordering / read-bytes evidence.** `/usr/bin/time -v` on the streamed run: **File system inputs 51,867,840** (x512 B = 26,556,334,080 B = **25,325.9 MiB**), Major faults 143,719, Minor 520,453. Prediction: 16 graphs (1 prefill ubatch + 15 decode) x 1508.8 MiB streamed + 1094.7 MiB pinned read once at load = 25,235.5 MiB, plus ~30 MiB of shared-library/metadata charge = **~25,265 MiB predicted vs 25,325.9 measured, +0.24%** (tolerance was +/-40%). Two independent runs read 51,867,832 and 51,867,840 sectors — 4 KiB apart. **This is the eviction proof**: if eviction were a no-op the pages would stay in page cache and reads after the first ring walk would be ~0; instead the process reads the full streamed set once per graph, 16 times over. Note `majflt x page_size` = 561.4 MiB is only 2.2% of the bytes read and is **not** the byte measure — under the per-range `POSIX_MADV_NORMAL` the prefetch verb installs, readahead brings ~185 KiB per major fault and fault-around maps ~9.8 pages per fault. `ru_inblock` ("File system inputs") is the byte measure, and it is the one that matches.
- **Callback overhead A/B** (SmolLM2-135M resident, macOS, `--ignore-eos`, serialized, interleaved rounds so drift cancels). The host is noisy (Docker VM ~200% CPU), so best-of-N is the estimator — noise is one-sided. Best-of-8 at `-n 512 -t 4`: base (repack on, no callback) **389.96**, `--no-repack` (no callback) **378.73**, `MUTA_CB_NOOP=1 --stream-weights` **385.49**, real gate forced on with `--stream-reserve-mib 0 --max-ram-mib 60` (21 streamed units, so 21 gates/graph) **356.05** tok/s. **The brief's A/B — noop callback vs no `--stream-weights` at all — is -1.15%**, corroborated by best-of-5 at `-n 1024` (-2.0%) and best-of-9 at `-n 128` (+4.0%, i.e. wrong sign, pure noise). **Callback overhead is under the 5% target and under this host's measurement floor.** The worst case — *real* gating on a resident 135M model whose whole graph is ~1.3 ms — is **-6.0% vs the same-kernel `--no-repack` baseline**; on the 4B streamed target where a token costs 537 ms the same fixed cost is ~0.1%. All 5 arms produce byte-identical output except `base`, which differs for the repack reason above.
- **B2's Concern 2 (`reserve_mib` untested against live KV+compute) is now answered, and the answer is "conservative, not too small."** This is the first run in the project that decodes under the cap. `memory.peak` 1639.6 MiB minus the plan's weights (pinned 1094.7 + window 211.0 = 1305.7 MiB) leaves **~334 MiB of non-weight charge against a 640 MiB reserve** — ~306 MiB of slack. The reason is that `reserve_mib` has to cover *touched* memory, not *allocated*: the compute buffer is sized for `n_ubatch` 512 but a decode graph writes a small fraction of it. **Caveat that must carry into Milestone A:** this prompt is 10 tokens, so no ubatch ever ran full. A 512-token prefill ubatch touches far more of the compute buffer and is still untested against the 640 MiB reserve. Per the brief, reserve was not retuned in this task.

### Task B3 fix round (post-review, findings 1-4)

Task review of `c86da62` verified the protocol independently (traced the coalescing loop, re-derived the 94/91 verb counts) and approved the code, with 4 Important findings. Fixed in one commit, `9a0bc06`. Two of the four are pure documentation; the code changes are the `MUTA_CB_NOOP` placement and the two assumption guards.

- **Finding 1 (Important) — the overhead headline was the confounded pair, and the no-op arm was unreachable without `--stream-weights`.** Confirmed on all three counts. (a) The `-1.15%` headline compared `MUTA_CB_NOOP=1 --stream-weights` against a plain run, which differ by repack as well as by the callback — the same confound the extra arms were added to avoid. (b) Worse, the hook was installed **inside** the `if (params.stream_weights)` block (`common/common.cpp:1340` at the time), so it could not be reached without also getting the manager, the pins, the first window and the mapping-wide `POSIX_MADV_RANDOM`. (c) With ASK always false the no-op computes the whole graph in **one** chunk, so it measures callback *invocation*, never the real gate's 23-chunk splitting. **Fixed:** `MUTA_CB_NOOP` now sits outside that block (`common/common.cpp:1348-1366`) with `cb_eval_user_data = nullptr`, so `MUTA_CB_NOOP=1` on an ordinary load produces an arm differing from base by the callback and **nothing else**; the warning text adapts to say whether the ring is also parked. **Re-measured with that clean pair** (SmolLM2-135M, `-n 512 -t 4`, `--ignore-eos`, 8 interleaved rounds, best-of): base **383.60** vs no-op **383.57** tok/s = **-0.008%**. Median-of-8 puts the no-op *ahead* by 5.6%, first-3-reps median -0.67%: every estimator lands on zero, so the honest claim is **callback-invocation overhead is below this host's measurement floor**, not a number. The superseded same-kernel figure from the old confounded arm was +1.78% (`noopcb`/`norepack`), which was also never the headline it should have been. **What the gate itself costs** is `gatecb` vs `noopcb` = **-7.64%** on a resident 135M model, i.e. 0.215 ms per graph for 21 gates; scaled to the 4B's 23 gates and more nodes that is ~0.3 ms against a 537 ms token = **~0.06%, under 0.1%**. The split cost is otherwise visible only in the 0.537-vs-0.531 s/token agreement.
- **Finding 2 (Important) — two load-bearing assumptions were unstated.** Confirmed. The gate protocol assumes (1) **one split on one backend** — `gate_unit` persists across the scheduler's per-split `j0` restarts, so a second split would re-see units already passed and silently multiply read-bytes while leaving output correct (clean file pages: a wrong evict costs a re-fault, never a wrong answer); and (2) **layer-sequential topology** — "all of unit N-1 is finished at unit N's gate" is a property of this graph builder (blocks emitted in order, each feeding the next through the residual chain, so layer N-1's nodes are all ancestors of layer N's first weight node), not of the callback contract. **Fixed** with the comment naming both at the callback (`src/llama-residency.cpp:1078-1100`) plus two cheap one-time warnings: `llama_context::graph_compute` (`src/llama-context.cpp:2481-2497`) warns once if `ggml_backend_sched_get_n_splits`/`get_n_backends` report more than one while the gate is installed (split counts are only valid after a graph has run, which is why the check lives there); and `res_check_ring_step` (`src/llama-residency.cpp:1078-1119`) warns once if consecutive gates are not ring successors. The second is the stronger guard and is why it exists: **a backend count cannot detect assumption (2)**, but a non-successor ring step detects a broken assumption of either kind, whatever caused it. Both are diagnostics, not failures, because the consequence is IO and not wrong output. **Both verified silent** on the real path, macOS and container — which upgrades "one CPU split" from an assumption to a measured fact for this configuration.
- **Finding 3 (Important) — deviations belonged in this WORKLOG, not only in the task report.** Correct; the house rule is plan said -> found -> did, with file:line. The four:
  - **(i) The container non-streamed baseline OOMKills at `cgrun 6g`.** Plan said run it at 6g "so it fits"; found `exit_status=137 OOMKilled=true` with `memory.peak` sitting at exactly the 6,442,450,944 B cap, because B2's `n_ctx` pin is **streamed-only** (`common/common.cpp:1248-1253` fires on `params.stream_weights && n_ctx == 0`), so `-fit` sized the KV cache to the VM's free RAM as in B2 Discovery 2; did add `-c 4096`, which also matches the streamed run's context and is the correct comparison anyway.
  - **(ii) The prefill log cannot name `n_prompt`/`n_ubatch`.** Plan said log `prefill reads ~= ceil(n_prompt/n_ubatch) x streamed_bytes`; found the manager is constructed before `llama_context` exists (`common/common.cpp:1311`, before context creation — the same ordering B2 Discovery 2 established), so neither quantity is knowable at that point; did print the rule with `streamed_bytes` substituted and the other two left symbolic (`src/llama-residency.cpp:699-708`).
  - **(iii) The first gate of a graph races its own wrap-prefetch.** Not in the plan; found by reasoning over the trace: at the last gate of graph G the window wraps and enqueues the ring's first units, then graph G+1 computes the pinned prefix (fast) and can reach `blk.9` before the manager thread has finished touching it, demand-faulting under `MADV_RANDOM`. Correct but it is the one structural stall in the design. Quantified here for the first time: the achieved 2891.9 MiB/s is **72.0% of B2's isolated sweep rate of 4018.2 MiB/s**, so **~28% is wrap-stall/serialization headroom** — a Milestone-A tuning candidate (deeper wrap-ahead, or W+1). Not changed in this task.
  - **(iv) A suspended manager still chunks graphs.** Not in the plan; found by inspection: ASK gates on unit identity without consulting `suspended`, and `on_gate_post` only early-returns after taking the lock (`src/llama-residency.cpp:1200-1206`). Harmless and unreachable today (nothing calls `suspend()` yet), but it is dead cost that S3's tier switch must remove. Not changed in this task.
- **Finding 4 (Important) — `--no-repack` is the identity control and must not silently become the accuracy reference.** Agreed, and this is Milestone-A-facing, so it is recorded here rather than only in the task report. B2 Discovery 1 forces `use_extra_bufts` off for streamed loads because repacking copies weights out of the mapping; B3 measured that this is not only a throughput tradeoff but a **numerical** one — on aarch64/GCC the repacked q4_K/q6_K kernels reach a different sampled token within 16 tokens (`--no-repack` alone, non-streamed, reproduces the streamed text byte-for-byte, sha256 `fc290ef7...`, while the default baseline gives `4de304e3...`). Consequences that bind Milestone A: **(1)** accuracy must be measured on the streamed / no-repack configuration, because that is what ships; **(2)** any accuracy number taken on a repacked build is **not comparable** and must not be carried forward; **(3)** MA must record a **quantified delta between the two kernel sets** (perplexity, or a small accuracy set run both ways) so that "streaming costs repack" carries an accuracy-axis number and not only a throughput one. B2 recorded the tradeoff as throughput-only; that is now known to be incomplete.

**Corrections to the B3 numbers above** (both would have misled Milestone A):

- **Read-bytes prediction omitted the init window.** The manager prefetches the first W = 2 ring units at init (`blk.9` 70.3 + `blk.10` 64.5 = 134.8 MiB) before any graph runs. Corrected prediction: 1094.7 (pins) + 134.8 (init window) + 16 x 1508.8 (graphs) + ~30 (shared libraries/metadata) = **25,400.3 MiB vs 25,325.9 measured = -0.29%** (previously stated as +0.24% against a prediction that left the init window out). The residual is **-74.4 MiB, almost exactly one layer unit (70.3 MiB)** — consistent with the final graph's wrap-prefetch being enqueued and then cut short when the process exits, which is the expected end-of-run behaviour.
- **"2811 MiB/s vs 2977 MB/s" mixed units, and the timing headline now comes from the final binary.** Four `drop_caches`-preceded streamed container runs measured **654.08 / 612.28 / 536.65 / 521.73 ms/token**; the last is the rebuilt tree at `9a0bc06` and is the number of record. Corrected arithmetic on it: 1508.8 MiB / 0.52173 s = 2891.9 MiB/s = **3032.4 MB/s**, i.e. **+1.9% against A1's O_DIRECT `D` of 2977 MB/s** — not the -5.6% the mixed-unit comparison implied, and *above* `D` rather than below, which is exactly the caveat B2 already recorded: `scripts/stream_env.sh drop_caches` clears the linuxkit VM's page cache but not the host macOS cache behind the `muta-models` volume, so these rates are an upper bound and not a disk number. Against the ledger's own prediction of **0.531 s/token** the best measured is **0.522 s/token, within 1.7%**, which is the claim that matters (the earlier entry said 0.537 / +1.1% from the pre-fix binary). Against B2's isolated per-sweep rate of 4018.2 MiB/s it is 72.0%, the wrap-stall headroom recorded under (iii) above. `memory.peak` for that run: **1,721,262,080 B = 1641.5 MiB**, still under the 2048 MiB budget, `OOMKilled=false`, output byte-identical to the `--no-repack` control, and both new guards silent.
- **Citation checked, not changed:** the review suggested `qwen35.cpp:51` for the `TENSOR_DUPLICATED` head. `grep -n "TENSOR_DUPLICATED" src/models/qwen35.cpp` returns **`52:`**; line 51 is `if (output == NULL) {`. The existing `:52` citation is correct and stands.

### Task B4 (S1c) — ledger polish + flag validation

llama.cpp branch `streaming`: `84c4f11` (`S1c: ledger polish + flag validation`), 8 commits over `01f58cd`. This is the closing task of the engine phase: verify the S1c checklist against what B2 already shipped, close three small carried review findings, correct a carried arithmetic error, and re-export `patches/`.

- **Checklist verification against B2's shipped code -- all three items were already shipped, nothing re-implemented:**
  - **(a) Refusal inequality print** -- shipped in B2 (`e7b853e`): `res_log_infeasible()` (`src/llama-residency.cpp:534-549`) prints both the `head-pinned:`/`head-streamed:` `R_pin = ...` arithmetic and the `--max-ram-mib` threshold each config would need, called from `res_solve()` on `REFUSED` (`:598-601`). Re-ran at `--max-ram-mib 600` (macOS `build-noblas`, post-fix binary) to confirm this task's edits didn't disturb it: `head-pinned: R_pin = max_ram 600.0 - mlock_front 0.0 - resident_other 0.0 - window 211.0 - reserve 640.0 = -251.0 MiB < required 497.3 MiB` / `at W = 1 this needs --max-ram-mib >= 1348.3`; `head-streamed: ... = -678.0 MiB < required 0.0 MiB` / `>= 1278.0` -- identical to B2's original measurement.
  - **(b) Startup plan log** -- shipped in B2 (`e7b853e`), `src/llama-residency.cpp:662-720`: model/mapping/`b_layer` stats, the `ledger:` arithmetic line, `config`, `pinned`, `streamed` (W + window MiB), `predicted s/token` (gated on `disk_gbps > 0`), and the prefill-reads note, all `LLAMA_LOG_INFO`.
  - **(c) `--pin-budget MIB` override** -- shipped end-to-end in B2 (`e7b853e`): flag at `common/arg.cpp:2857-2865` (this task adds parse-time validation, see below), threaded through `common/common.h:580` and `common/common.cpp:1312-1321` into `llama_residency_params.pin_budget_mib`, applied as a `min()` cap on `r_pin` inside **both** solver candidates at `src/llama-residency.cpp:491-493`. Ran the brief's exact command on macOS (`build-noblas`, `models/Qwen3.5-4B-Q4_K_M.gguf`, `--max-ram-mib 2048 --pin-budget 700 --stream-disk-gbps 2.977 --residency-selftest -no-cnv -p x -n 1`):
    ```
    residency: ledger: max_ram 2048.0 - mlock_front 0.0 - resident_other 0.0 - window 708.3 - reserve 640.0 = R_pin 699.7 MiB
    residency: config = head-streamed
    residency: pinned   = 667.7 MiB in 11 units (10 blk + misc)
    residency: streamed = 1935.8 MiB in 23 ring units (22 blk + head), W = 2, window 708.3 MiB, b_layer_max 70.3 MiB
    residency: predicted s/token = 0.682 (streamed 1935.8 MiB / 2.977 GB/s)
    ```
    vs. the identical command **without** `--pin-budget` (auto): `config = head-pinned`, `R_pin 1126.7 MiB`, `pinned = 1094.7 MiB in 11 units (9 blk + head + misc)`, `streamed = 1508.8 MiB`. The cap doesn't just clamp the winning candidate's own r_pin to ~the requested number; because it applies inside `res_solve_one` to *both* the head-pinned and head-streamed candidates before `res_solve` compares them by streamed-byte count, capping at 700 pushes the head-pinned candidate's `r_pin` down from 1126.7 to 700 MiB (too little room to pin the head, `need = 497.3`), which flips the winner to head-streamed and cuts total pinned bytes from 1094.7 to 667.7 MiB -- proof the override changes the chosen plan, not just a number nobody reads.

- **Carried code fixes (all in the one `84c4f11` commit):**
  - **Flag validation (B1 review minor, `progress.md:29`).** `--max-ram-mib`, `--prefetch-layers`, `--stream-reserve-mib` are `uint32_t` in `common_params` (`common/common.h:578-581`) fed from a plain `int` CLI callback with no check, so a negative value wrapped silently into a huge budget. Added a `value < 0` guard at each callback (`common/arg.cpp`) that throws `std::invalid_argument`, matching the existing precedent at `-cms/--checkpoint-min-step` (`common/arg.cpp:1641-1643`, `"checkpoint-min-step must be non-negative"`). `--pin-budget` took any string -- only checked downstream by `std::stoi` inside a try/catch that silently falls back to `auto` on a parse failure, and does not reject a negative number that *does* parse (e.g. `"-5"`, `pin_budget_mib = -5`, which then fails the `>= 0` cap check at `llama-residency.cpp:491` and is silently treated as unset). Added a parse-time check (`"auto"`, or non-empty and every character a digit) at `common/arg.cpp`, same throw style; needed `<cctype>` for `std::isdigit`, added to the include block. Verified (macOS, `build-noblas`): `--max-ram-mib -1`, `--prefetch-layers -1`, `--stream-reserve-mib -5`, `--pin-budget -5`, `--pin-budget abc123` all now exit 1 before the model is even opened, each with `error while handling argument "--X": <flag> must be non-negative` (or `pin-budget must be "auto" or a non-negative integer`); `--pin-budget 700` still parses and behaves as measured in (c) above.
  - **Repack-off notice visibility (B2 review minor, `progress.md:36`).** `src/llama-model.cpp:1283-1291`'s "stream_weights is enabled, disabling extra buffer types" notice was `LLAMA_LOG_INFO`. `common_log_default_callback` (`common/log.cpp:441-459`) maps `GGML_LOG_LEVEL_INFO` to `LOG_LEVEL_TRACE` (4) against the default threshold `LOG_LEVEL_INFO` (3, `LOG_DEFAULT_LLAMA`, `common/log.cpp:29`/`common/log.h:24-32`) -- invisible without `-lv 4`, so a user silently lost repack kernels with no way to notice. B1's cited precedent ("disabling warmup", `common/common.cpp:1535`) is `COM_INF`, i.e. `common/log.h`'s `LOG_INF` macro (`common/common.h:32`) -- a *different* code path (common-side, not the ggml/llama-side log-callback bridge) that sets verbosity `LOG_LEVEL_INFO` (3) directly and so is already visible by default; that macro isn't reachable from `src/llama-model.cpp` (common/ links against llama, not the reverse), so the equivalent fix on the src/ side of that boundary is raising `LLAMA_LOG_INFO` to `LLAMA_LOG_WARN`, whose `GGML_LOG_LEVEL_WARN` maps to `LOG_LEVEL_WARN` (2), also under the default threshold -- same visibility outcome as B1's fix, different macro because it's a different layer. Verified (macOS): a plain `--stream-weights` run with no `-lv` and no `--residency-selftest` now prints `W load_tensors: stream_weights is enabled, disabling extra buffer types (repacked weights cannot be streamed)` -- silent in that configuration before this fix.
  - **O_CLOEXEC on the residency fd (B2 review minor, `progress.md:36`).** `src/llama-residency.cpp:994`: `open(path_model, O_RDONLY)` -> `open(path_model, O_RDONLY | O_CLOEXEC)`. The fd is process-lifetime (closed only in `llama_residency_free`, `:1047-1049`) and exists solely for `fadvise_discard()` (`fadvise_discard(r->fd, ...)`, `:828`); without `O_CLOEXEC` it would leak into any child process across `exec`.

- **Doc correction -- B1-fix-round's sweep-observation arithmetic (dated 2026-08-13, found while re-reading the task for this checklist).** The "Task B1 fix round" section's "Direct sweep observation" bullet read the DISCOVERY S0.4 table's `m0.` row, `[file_off, len] = [23,721,280, 103,668,480]` (`docs/DISCOVERY.md:508`), as if it were `[start, end)`, and computed the front's tensor payload as `103,668,480 - 23,721,280 = 79,947,200 B = 76.2 MiB`. The table's own header is `[file_off, len]`, not `[start, end)`, and `docs/DISCOVERY.md:506` carries a *separate* `end offset` column (`127,389,760` for this row) specifically because `len` is not `end - start`. The correct payload is the `len` field taken directly: **103,668,480 B, approx 98.9 MiB**. The measured total (`memory.stat file 117,268,480 B`, 111.8 MiB) was already correct in that entry; only the payload/overhead split under it was wrong. Corrected: payload 103,668,480 B (approx 98.9 MiB) + overhead `117,268,480 - 103,668,480 = 13,600,000 B` (approx 13.6 MB) = 117,268,480 B -- not "76.2 MiB payload + approx 35.6 MiB overhead". The qualitative conclusion is unchanged (the gap is ordinary process/shared-library overhead, not bundle leakage); the corrected ~13.6 MB is, if anything, a closer order-of-magnitude match to B3's independent ~30 MiB shared-library/metadata estimate (see "Corrections to the B3 numbers above") than the original's overstated 35.6 MiB was, though the two measurements are from different binaries/contexts and aren't expected to match exactly. Per house style this is an append-only correction; the original B1-fix-round bullet is left as written.

- **Patches export (phase-gate obligation, pending since S1a).** `ls patches/` before this task showed only the duo series, `0001`-`0016`, ending at `0016-Q1-support-hybrid-append-only-front-models.patch` -- no `0017`+ existed, so no collision risk. `git -C llama.cpp format-patch 01f58cd..streaming --start-number 17 -o ../patches/` produced 8 new files, `0017`-`0024`, one per streaming-branch commit in the same order as `git log --reverse 01f58cd..streaming` (`2a42d67`->`0017`, `c528ee2`->`0018`, `876504a`->`0019`, `e7b853e`->`0020`, `ae76ab0`->`0021`, `c86da62`->`0022`, `9a0bc06`->`0023`, `84c4f11`->`0024`) -- verified 1:1 by diffing each patch's `Subject:` line against the commit's own subject. `patches/` now holds 24 files total: the 16-patch duo series untouched plus the 8-patch streaming series, coexisting without renumbering anything.

- **Build + gate re-verification after `84c4f11`.**
  - macOS `build-noblas`: full rebuild, exit 0, 0 `error:` lines, 0 warnings in the changed files.
  - Container (`scripts/stream_env.sh build`, all 4 targets): exit 0, 0 `error:`/warning lines beyond the pre-existing ccache/cpp-httplib cmake configure notices.
  - **Phase B gate re-run** (`scripts/stream_env.sh drop_caches` then `cgrun 3g /build/bin/llama-completion -m /models/Qwen3.5-4B-Q4_K_M.gguf --stream-weights --max-ram-mib 2048 --stream-disk-gbps 2.977 --residency-selftest -no-cnv -p x -n 1`): **PASS**, exit 0, `OOMKilled=false`. Ledger unchanged from the B2/B3 baseline (`config = head-pinned`, `pinned 1094.7 MiB` in 9 blk + head + misc, `streamed 1508.8 MiB`, `predicted s/token = 0.531`); selftest `pins resident 100.00% (1094.6 / 1094.6 MiB)`, evict `100.00% -> 0.00%` (hard Linux assert), prefetch `3584.5 MiB/s`, ring walk 46 steps, peak tracked == peak resident == `211.0 MiB` against limit `281.3 MiB`, `end (all asserts held)`, `PASS`. `memory.peak = 1,681,481,728 B` (1603.6 MiB) under both the 2048 MiB budget and the 3g cap; `memory.stat`: `anon 393,216 B`, `file 1,368,109,056 B`. Also newly visible in this run (item 2b's fix, at default `--residency-selftest` verbosity which was already raised, so this run doesn't by itself prove default-verbosity visibility -- that was checked separately below): `W load_tensors: stream_weights is enabled, disabling extra buffer types ...`.
  - **Repack-notice default-verbosity check, separate from the gate run above** (macOS, `--stream-weights` alone, no `-lv`, no `--residency-selftest`): `W load_tensors: stream_weights is enabled, disabling extra buffer types (repacked weights cannot be streamed)` printed before any other output -- confirms the fix holds without the selftest's verbosity override.
  - **Validation smoke** (macOS, parse-time, no model ever opened): `--max-ram-mib -1` -> `error while handling argument "--max-ram-mib": max-ram-mib must be non-negative`, exit 1.

### Task MA (Milestone A checkpoint) — the run matrix, and the headline answer

Engine unchanged from B4: llama.cpp `streaming` @ `84c4f11`, tree clean, never touched in this
task (`scripts/stream_env.sh build` re-run at the top of every arm confirms current, no-ops
fast). New: `scripts/milestone_a.sh`, the reproducibility harness for MA-1/1b/2/3, and this
entry. **Headline: yes, Qwen3.5-4B stream-decodes under a 2 GiB cgroup cap** — 2.44 tok/s
observed (`cgrun 3g`), 2.26 tok/s under a real kernel-enforced 2048m hard cap (within 15% of
observed, `OOMKilled=false`). Full numbers, ledger blocks, and the environment/caveats header
are in `bench/results.md` §5; this entry covers what plan said vs. found vs. did, per house
style.

- **`scripts/milestone_a.sh` design.** One subcommand per arm (`ma1`/`ma1b`/`ma2`/`ma3`,
  plus `all` and `table`), each writing fixed-name `bench/.artifacts/milestone_a/<arm>.log`
  (raw, `2>&1`-captured) and `<arm>.env` (parsed `KEY=VALUE`, sourced by `table` to render the
  markdown results table) — overwritten on re-run, so any single arm is independently
  re-runnable without disturbing the others, per the brief's "idempotent, safe to re-run
  single arms." Every measurement is preceded by `scripts/stream_env.sh drop_caches`, per the
  "drop_caches before each cap-relevant run" discipline. MA-1/MA-1b run a `bash -c` compound
  command inside the `cgrun` container that backgrounds `scripts/memwatch.sh 1 > /tmp/memwatch.csv`,
  runs `llama-completion`, then kills the sidecar and `cat`s the CSV (delimited by an
  `=== memwatch.csv ===` marker) so the 1 Hz trace rides inside the same captured log as the
  cgrun/ledger output — no `docker cp` or extra container needed. MA-2/MA-3 skip the sidecar
  (per the brief, memwatch is specified only for MA-1/1b) and pass args straight through
  `cgrun` without an extra `bash -c` layer.
- **Bug found + fixed during MA-3's naive-default arm (this task, not a carried finding):**
  the script's `set -euo pipefail` combined with several `grep`-based perf-line parsers
  (`perf_decode_line`, `perf_load_ms`, etc., `scripts/milestone_a.sh:95-108` before the fix)
  aborted the whole harness with a bare `exit 1` and no diagnostic the moment a `grep` found no
  match — which is the *expected* outcome for any OOMKilled arm, since a killed process never
  reaches llama.cpp's `common_perf_print` block at all. Root cause is a `pipefail` subtlety:
  `grep 'foo' | grep -v 'bar'` returns pipefail's exit status from the *first* failing stage
  (grep #1, "no match" = exit 1) even when a later stage (grep #2) exits 0, so `local x;
  x="$(...)"` assignments built from these helpers aborted under `set -e` even though the
  pipeline "worked" in the sense of correctly producing empty output. First reproduced live: the
  naive-default arm's log correctly showed `OOMKilled=true` on inspection (the container-level
  data collection was never the problem), but the harness itself died with exit 1 before
  writing `ma3_naive.env`. Fixed by appending `|| true` to every helper function that greps for
  an optional line, plus the few remaining standalone `var="$(grep ... | cut ...)"`
  assignments reading from already-written `.env` files (`scripts/milestone_a.sh`, all
  `perf_*`/`line_*`/`cgrun_*`/`majflt`/prompt-token-count helpers). Re-ran MA-3 after the fix;
  both arms now complete and write their `.env` files regardless of outcome. Not logged as a
  llama.cpp deviation because no llama.cpp code was touched — recorded here per the "discovery
  beats the document" rule since it changed the harness's own behavior mid-task.
- **MA-1 (observed).** `memory.peak` 1,720,438,784 B = 1640.7 MiB, memwatch max sampled
  `memory.current` 1,704,964,096 B = 1626.0 MiB — both under 2048 MiB throughout (**PASS**).
  Decode 410.33 ms/token = 2.44 tok/s vs. the ledger's own predicted 0.531 s/token = ratio
  0.773, inside ±30% toward the fast edge (**PASS**) — expected, since `D = 2.977 GB/s` is an
  upper bound rather than a floor (bench/results.md §5's Environment header), not evidence the
  band is loose. Ledger unchanged from B2/B3/B4 (`config = head-pinned, pinned
  1094.7 MiB, streamed 1508.8 MiB, W = 2`) — Milestone A reconfirms it rather than discovering
  a new one, as expected since neither the model nor the flags changed.
- **MA-1b (full-ubatch prefill, first ever) — closes B3 Concern 1.** Prompt: `bench/prompts/hard.txt`
  (20 lines, 493 tokens) plus its own first 5 lines repeated (25 lines total) = **623 tokens**,
  verified with `llama.cpp/build-noblas/bin/llama-tokenize --show-count` (host macOS build; no
  container `llama-tokenize` target exists and none was added, to keep this task's changed-file
  list to what the brief specified — `scripts/milestone_a.sh`'s `ensure_ma1b_prompt` re-verifies
  this count on every run when the host binary is present, and falls back to the last-verified
  count with a loud warning when it is not). `llama-completion`'s own prefill counted 622
  tokens for the identical file — a 1-token discrepancy attributed to a BOS-counting difference
  between the two binaries, not a construction bug. `ceil(622/512) = 2` ubatches (512 + 110):
  the first full-512-token ubatch prefill this project has run. Cap held: `memory.peak`
  1,770,143,744 B = 1688.1 MiB (**PASS**). **Reserve verdict: still conservative, not too
  small.** Memwatch's max sampled `anon_bytes` (the non-weight charge `--stream-reserve-mib
  640` exists to cover) peaked at 374,874,112 B = 357.5 MiB — 282.5 MiB of slack, comparable to
  (slightly less than) B3's 306 MiB of slack at a 10-token prompt. B3's open Concern 1
  ("the compute buffer is sized for `n_ubatch` 512 but was never more than fractionally
  touched") is now answered by direct measurement rather than reasoning. **Finding: prefill
  time is compute-bound, not read-bound, once the ubatch is full.** Measured prefill 14,716.48
  ms = 14.72 s (23.66 ms/token); the read-only analytical lower bound `ceil(622/512) x 1508.8
  MiB / 2839.5 MiB/s` (2.977 GB/s expressed in MiB/s) = 1.063 s undershoots by ~13.8x. The
  streamed-bytes-per-ubatch term is constant regardless of ubatch token count (the ring walks
  the same weight units once per graph either way), but FLOPs are not — a 512-token ubatch does
  roughly 512x a 1-token decode step's compute while reading the identical 1508.8 MiB, so on
  this `GGML_BLAS=OFF` build (no vectorized gemm) compute dominates prefill even though it is
  negligible for decode. This is why MA-1's decode ratio (0.773) tracks the ledger's formula
  tightly while prefill does not — the formula has no `+ compute` term, by design (it predicts
  decode, where compute is genuinely negligible).
- **MA-2 (enforced).** `exit 0`, `OOMKilled=false`, `memory.peak` 1,721,245,696 B = 1641.5 MiB
  — under the *hard* 2048m cgroup cap this time, not the looser 3g container MA-1 ran in
  (406.5 MiB headroom). Decode 442.95 ms/token = 2.26 tok/s, -7.4% vs. MA-1's 2.44 tok/s, inside
  ±15% (**PASS**). This is the run that actually answers the headline question under real
  kernel enforcement, not just a software budget inside a loose cap.
- **MA-3 (unmanaged A/B, G12 preview).** Kernel-fair arm (`--no-repack -c 4096`, no
  `--stream-weights`, the correct control per B3 Finding 4): `exit 0`, `OOMKilled=false` — ran
  to completion, but reclaim-thrashed rather than decoding cleanly. `memory.peak`
  2,147,483,648 B = 2048.0 MiB **exactly the cap**, held there rather than killed, because
  every byte in play is a clean `MAP_SHARED` file page — reclaimable by simple eviction and
  refault, so the OOM killer (reserved for memory that cannot be reclaimed) never fires. Decode
  1701.11 ms/token = 0.59 tok/s, **3.83x slower than MA-2's managed 2.26 tok/s**. `/usr/bin/time
  -v`: 975,286 major faults, `File system inputs` 352,386,776 sectors (x512 B = 168.0 GiB) read
  over the measured 115.68 s wall-clock run (GNU `time`'s `Elapsed`, `1:55.68`) — about 65.8x
  the model's own 2.6 GiB size, direct evidence of sustained
  reclaim thrash (the kernel evicting and re-faulting the same weight bytes repeatedly because
  nothing pins a stable working set the way the residency manager's ring does). Naive-default
  arm (no flags beyond `-c 4096`, repack left at default ON): **OOMKilled**, `exit 137`. The log
  shows exactly why — `load_tensors: CPU_Mapped model buffer size = 2603.50 MiB` immediately
  followed by `load_tensors: CPU_REPACK model buffer size = 2599.83 MiB`: the default path
  holds the *mmap* and a *separate repacked copy* simultaneously, ~5203 MiB of model-only
  footprint against a 2048 MiB cap before KV/compute are even counted — the "default repack
  would double-charge anyway" prediction in the brief, confirmed exactly. It survived long
  enough to generate a handful of tokens (visible in the raw log as literal `.` characters, a
  known Qwen3.5-at-temp-0 degenerate-greedy artifact on this prompt, unrelated to streaming)
  before being killed at wall-clock ~16 s. Managed/unmanaged ratio: 2.26 / 0.59 = **3.83x**
  (MA-2 vs. the kernel-fair arm; the naive-default arm never reached steady-state decode so has
  no rate to compare).
- **MA-4.** Satisfied by reference to `task-B3-report.md`'s fix round (Finding 1) / this
  file's "Task B3 fix round" section above — no new runs, per the brief. Callback-invocation
  overhead best-of-8 = -0.008% (under the host's measurement floor); the gate's own cost
  (`gatecb` vs `noopcb`) = -7.64% on the resident SmolLM2-135M scale (0.215 ms/graph, 21
  gates), which scales to ~0.3 ms/graph at the 4B's 23 gates and heavier graph — ~0.07% at
  worst against this run's own 410-443 ms/token (MA-1/MA-2 above), under 0.1%.
- **The `--no-repack` accuracy reference.** Every run in this matrix that decodes on the
  non-repacked kernel set is meant to be compared only against others on that same set, per B3
  Finding 4 — not against a bare/default baseline. MA-1/MA-1b/MA-2 get there via
  `--stream-weights` itself (B2 Discovery 1: streaming forces `use_extra_bufts` off because
  repacking would copy weights out of the mmap); MA-3's kernel-fair arm gets there by passing
  `--no-repack` explicitly, since it deliberately does **not** pass `--stream-weights` and so
  needs the flag to land on the same kernel set for a fair comparison. B3 measured that
  repacked vs. non-repacked kernels diverge numerically within 16 tokens on aarch64/GCC greedy
  decode, not just in throughput. MA-3's naive-default arm (repack ON) is deliberately the odd
  one out, reported in one sentence precisely because its failure mode (the repack double-buffer)
  has nothing to do with streaming. A quantified perplexity/accuracy delta between the two
  kernel sets remains **deferred to the G-gates**, per B3 Finding 4 — Milestone A claims no
  accuracy numbers on either kernel set, only throughput and memory.
- **Deliverables.** `bench/results.md` §5 (full table, per-arm detail, environment header,
  MA-4-by-reference note, `--no-repack` note); `docs/POC_REPORT.md` `## Streaming (Milestone A)`
  stub (verdict paragraph + condensed table + pointer to `bench/results.md` §5, full
  `## Streaming` deferred to E2); this entry.

### Task C1 (S3.1) — duo tier registry + bundle-manifest auto-discovery

Pure refactor of `tools/duo/duo.cpp`'s hardcoded front/expert pair into a tier registry, the
first task of Phase C (weight-streaming into `llama-duo`). Single commit `84c4f11..<C1>` on
`streaming`; no other file touched (`git diff --stat` shows exactly `tools/duo/duo.cpp`,
+369/-50 lines).

- **What moved.** `enum tier_role {FRONT,EASY,MID,TOP}`, `enum tier_policy
  {MLOCK,RESIDENT,STREAMED,AUTO}`, `enum tier_state {UNLOADED,LOADING,READY}` (the last as
  `std::atomic<tier_state>`); `struct duo_tier {role,prefix,file,policy,n_ctx,temp,top_p,
  duo_model m,state,residency*}` (`duo.cpp:191-224` post-refactor). `duo_state` traded its two
  `duo_model front;`/`duo_model expert;` members for `std::vector<duo_tier> tiers` plus raw
  `front`/`easy`/`mid` pointers into it (`duo_state` grows `struct duo_tier` as a *movable*
  type: `std::atomic` has no move constructor, so `duo_tier` needed one hand-written --
  `state.load()`/`state.store()` instead of moving the atomic itself -- or
  `std::vector<duo_tier>::resize()` would not have compiled). `s.front`/`s.expert`
  (`duo_model&`) became `s.front->m`/`s.mid->m` (`duo_tier*`) at every call site, exactly as
  the brief specified; `run_verify_turn`'s existing `fr`/`ex` local-alias pattern was extended
  to `run_router_turn`/`run_codraft_turn` (`duo_model & front = s.front->m; duo_model & expert
  = s.mid->m;`) so the bodies of those two functions needed almost no further edits beyond the
  two alias lines. Registry population (`build_tier_registry()`, called once in `main()` right
  after `duo_state` construction, before any model load): bundle-manifest auto-discovery first
  (`discover_bundle_tiers()`, `gguf_init_from_file(no_alloc=true, ctx=NULL)` on `p.bundle`,
  reads `bundle.count`/`bundle.{i}.prefix`/`bundle.{i}.role`, `gguf_free`d immediately after --
  metadata-only, confirmed sub-millisecond even on the 3.4 GB `muta-duo-q.gguf` and 3.2 GB
  `muta-trio.gguf` files used below), legacy role string `"expert"` mapped to `TIER_MID`
  in `tier_role_from_str()`; explicit `--tier NAME=PREFIX`, `--tier-file NAME=PATH`,
  `--tier-ctx NAME=N`, `--tier-policy NAME=mlock|resident|streamed|auto` (repeatable, `NAME=
  VALUE` split by `parse_tier_kv()`) layer on top per-role, and can *add* a role the manifest
  never carried (this is the mechanism the plan wants for a future top/27B tier: pure data,
  zero code change). `--front-prefix`/`--expert-prefix` are now literally sugar for `--tier
  front=X`/`--tier mid=X` (`parse_args`, `duo.cpp:363-364`) -- they populate the same
  `tier_prefix_ovr` map instead of separate `duo_params` fields, so `duo_params::front_prefix`/
  `expert_prefix` were deleted rather than left as dead duplicate storage. Sampling defaults:
  front tier keeps `--temp-front`/`--top-p-front`, every other role (mid, and easy/top by
  extension since neither has dedicated flags yet) keeps `--temp-expert`/`--top-p-expert` --
  matches the brief's "temp_expert/top_p_expert -> mid tier" instruction exactly for the roles
  that matter this task (front, mid); easy/top's values are unused until C2/C3 give them a
  sampler. `n_ctx`: `-1` sentinel resolves via `tier_ctx_resolved()` to `p.ctx_front`/
  `p.ctx_expert` for front/mid (so the legacy `--ctx-front`/`--ctx-expert` flags keep working
  unchanged, not just "8192 hardcoded") and a flat `8192` default for easy/top, matching
  "front 4096, easy/mid 8192" once `p.ctx_front`/`p.ctx_expert`'s own defaults are substituted
  in. `load_duo_model()` gained an explicit `file` parameter (previously always read
  `p.bundle` internally) so a tier's `--tier-file` override is honored end-to-end; every call
  site this task still passes `p.bundle` (no `--tier-file` exercised), so this is
  forward-compatible plumbing with no behavior change yet.

- **The registered-not-loaded easy decision.** Per the brief, `main()` still loads exactly
  front then mid, unchanged order/semantics; if a discovered/registered tier has role `easy`,
  `main()` logs one line, `tier easy registered (loading lands in S3.3)`, and does not call
  `load_duo_model()` for it -- `s.easy->m` stays a default-constructed `duo_model` with
  `state == TS_UNLOADED` for the rest of this task's runs. This is the only place a 3-tier
  bundle's control flow differs from a 2-tier bundle's, and it differs by *doing less*, not by
  a different code path: the front/mid load calls are byte-for-byte the same statements
  whether or not `s.easy` is non-null.

- **Drift from the brief.** None worth calling out beyond what's already folded into "what
  moved" above -- `duo_params::front_prefix`/`expert_prefix` deletion (brief only said "become
  aliases", didn't mandate keeping or dropping the backing fields; dropping them removed what
  would otherwise have been dead, never-written storage) and the `load_duo_model()` `file`
  parameter (brief's struct spec already implied per-tier files via `duo_tier::file`; wiring
  it through was the only way to make that field do anything, still zero behavior change since
  no run exercises `--tier-file` yet).

- **Regression gate.** Baselines captured *before* any edit, from the then-current
  `llama.cpp/build/bin/llama-duo` (arm64, BLAS on, this tree's macOS duo regression binary):
  router/codraft/verify on `bundle/muta-duo-q.gguf`, `-n 128 --temp-front 0 --temp-expert 0
  --seed 42 --no-stream -q`, verify additionally `--draft 8 --draft-max 8`. Rebuilt
  `llama-duo` after the refactor (`cmake --build llama.cpp/build -j --target llama-duo`, exit
  0, 0 `error:`/`warning:` lines including in `duo.cpp` itself), re-ran all three with
  identical flags:
  | mode | pre-refactor sha256 (stdout) | post-refactor sha256 (stdout) |
  |---|---|---|
  | router | `4bbb514f...` | `4bbb514f...` (identical) |
  | codraft | `f726b586...` | `f726b586...` (identical) |
  | verify | `eb906de6...` | `eb906de6...` (identical) |
  All three: **byte-identical**, confirmed by both `sha256sum` match and `diff -q` (silent =
  no difference). Only stdout is gated per the brief; stderr differs cosmetically (the new
  registry-building log lines) and was not compared.
  - **Trio auto-discovery smoke (d).** `--bundle bundle/muta-trio.gguf --mode router -p
    "hello" -n 16 --temp-front 0 --temp-expert 0 --seed 42 --no-stream`: stderr shows `loading
    front  ('m0.') from bundle/muta-trio.gguf`, `tier easy registered (loading lands in
    S3.3)`, `loading expert ('m2.') from bundle/muta-trio.gguf` -- three tiers discovered from
    the manifest (`bundle.count=3`), and mid correctly resolved to prefix `m2.` (the bundle's
    third model), not `m1.` (easy's prefix) -- proof the manifest walk is actually reading
    per-index roles rather than coincidentally reusing the 2-tier bundle's `m1.` default. Exit
    0, answered "i'm glad you asked. i'm here to help with any math or science" (truncated at
    `-n 16`), no crash.
  - **Alias check (e).** Router baseline re-run with `--front-prefix m0. --expert-prefix m1.`
    appended: stdout sha256 `4bbb514f...`, identical to baseline (a) and to the plain
    post-refactor re-run -- confirms the alias flags reach the same `tier_prefix_ovr` entries
    `--tier front=m0.`/`--tier mid=m1.` would.
  - **Shared-code / other builds.** `build-noblas` `llama-completion` target: full rebuild
    (this pulled in `libllama`/`libllama-common` too, both unaffected since only `duo.cpp`
    changed), exit 0, 0 `error:`/`warning:` lines -- confirms `duo.cpp`'s changes stayed
    contained to its own translation unit despite touching `gguf.h`/`llama.h` APIs already
    used elsewhere. Container build (`scripts/stream_env.sh build 2>&1 | tail -3`, all four
    `BUILD_TARGETS`: `llama-completion`, `llama-duo`, `llama-bench`,
    `llama-speculative-simple`): exit 0 (`set -euo pipefail` in the script means a non-zero
    exit here would prove a compile failure somewhere in the four targets); the container's
    fresh `llama-duo` binary timestamp matches this task's rebuild.

- **Known limitation, not hardened this task.** `discover_bundle_tiers()` checks
  `gguf_get_kv_type()` before calling `gguf_get_val_u32`/`gguf_get_val_str` (added defensively
  beyond what the brief asked for, since those getters abort the process on a type mismatch
  per their own doc comments) for `bundle.count` and each `bundle.{i}.prefix`/`.role`, but
  does not otherwise validate manifest well-formedness beyond "skip this index" on a missing
  key. Not exercised by either real bundle (both have well-formed manifests, confirmed via
  `gguf-py` dump before this task), so out of scope for a pure-refactor regression gate; noted
  here rather than silently assumed safe for a hypothetical malformed bundle.

### Task C1 fix round (post-review, findings 1-2), 2026-08-13

Task review of `84c4f11..50cac21` (the actual commit range this entry's earlier "`84c4f11..
<C1>`" line left as a placeholder -- corrected here rather than edited in place, per
append-only style; the range now extends to `50cac21..1cdcdc2` for this fix round) approved
the refactor with two Important findings, both fixed in one follow-up commit,
**`1cdcdc2`**, `S3.1: pointer-stable tier container + help text`.

- **Finding 1 -- undocumented pointer-stability invariant.** `duo_state::front/easy/mid` are
  raw `duo_tier *` into `s.tiers`, safe only because `build_tier_registry()` resizes the
  container exactly once, before any pointer is taken, and is never called again for the rest
  of the process's life. Nothing said so anywhere -- and C3 (staged/incremental tier loading)
  is precisely the kind of task that might later `push_back()` a tier onto an already-built
  registry, which on a `std::vector` would silently relocate every existing element on
  reallocation and dangle all three pointers with no compiler diagnostic. Fixed by swapping
  `std::vector<duo_tier> tiers` for `std::deque<duo_tier> tiers`: a deque's `push_back()`/
  `resize()` never relocates existing elements (that guarantee is why deque forgoes
  contiguous storage in the first place), so references and pointers into it survive future
  growth -- only a middle insert/erase would invalidate neighbors, and nothing in this
  codebase does that. Documented the invariant directly on the `duo_state::tiers` member.
  `<deque>` was already included (used by `gen_segment`'s `lp_window`), so this needed no new
  include. Re-ran the router regression (baseline (a) from the original C1 entry) against the
  rebuilt binary: stdout sha256 `4bbb514f...`, unchanged -- confirms the container swap is
  behavior-neutral, as a pure storage-strategy change should be.
- **Finding 2 -- "zero code change" framing was overstated.** The original entry's "What
  moved" section said a future top tier could be registered "as pure data, zero code change."
  That is only true for *parsing and discovery*: `--tier top=X`/`--tier-file top=Y` already
  flow through `build_tier_registry()`'s override maps and `tier_role_from_str()`'s `"top"`
  case with no code change, and `discover_bundle_tiers()` would pick up a manifest
  `bundle.{i}.role="top"` entry the same way. *Using* a top tier -- actually loading it and
  dispatching turns to it -- needs at minimum a `duo_state::top` pointer (there is currently
  none; only `front`/`easy`/`mid`) plus a new `case TIER_TOP:` wherever the code switches on
  role today (the pointer-assignment loop at the end of `build_tier_registry()`,
  `tier_policy_default()`, `tier_ctx_resolved()`'s `default:` branch currently doubles as
  "easy/top role default" and would need to actually distinguish them once top has real
  values, and any future turn-driver logic that dispatches by tier). Registering a top tier is
  free; *using* one is C-series follow-on work, same as easy's S3.3 load path. Recorded here
  as a correction rather than editing the original claim in place.
- **Minor:** `--tier-policy`'s `print_usage()` help text listed `mlock|resident|streamed` but
  never mentioned `auto` even though `tier_policy_from_str()` has always accepted it; folded
  into the same `1cdcdc2` commit as a one-line fix (help text only, no parsing change --
  `auto` already worked, it just wasn't documented).

### Task C2 (S3.2) — three-tier routing, conf escalation easy->mid, `--ttft-opener`

First behavioral change of Phase C (C1 was a pure refactor). Single commit `1cdcdc2..2609120`
on `streaming`, `S3.2: three-tier routing + conf escalation easy->mid + --ttft-opener`; one
file, `tools/duo/duo.cpp`, +228/-39.

- **Deviation from C1's note: easy loads NOW, not in S3.3.** C1 left the easy tier
  registered-but-not-loaded and logged `tier easy registered (loading lands in S3.3)`. C2
  cannot route to a tier that has no context, so `main()` now loads synchronously in registry
  order **front -> easy -> mid** and frees in reverse (`duo.cpp:1683-1700`, free at `:1783`).
  Easy is loaded with `checkpoint_seq=true` unconditionally — it is hybrid, therefore
  append-only, and the checkpoint sequence is precisely what makes its answer provisional
  enough to escalate (see below). `duo_tier::state` is set to `TS_READY` after each load
  (`front`/`easy`/`mid`), which is the flag C3 will flip from a background loader thread; the
  code comment at `:1683` says so explicitly so C3 does not have to rediscover the intent.
- **Router mapping.** The front stays the router in every case (verdict logits A=49/B=50,
  unchanged). `route=easy` now picks the **easy tier** when one is loaded and falls back to the
  front otherwise (`duo.cpp:1065`, a one-line ternary) — that fallback is exactly what keeps
  2-model bundles byte-identical. `route=hard` still goes to mid with `hard_mode expert|verify`
  semantics untouched.
- **Confidence escalation easy->mid is checkpoint-provisional.** Q1's rule was "conf monitor
  off for append-only authors" because a conf cut truncates the text buffer while the tokens
  past the boundary have already been decoded — illegal for a model whose recurrent state
  cannot partially rewind. C2 narrows that rule instead of removing it: the monitor is armed
  for an append-only author **iff the caller holds a checkpoint** (`gen_opts::conf_checkpoint`,
  `duo.cpp:661`; the gate itself at `:723`). The protocol is (`duo.cpp:1077-1103`):
  `checkpoint_save(easy)` -> `gen_segment` with the monitor armed -> on a `conf` cut
  `gen_segment` **does not commit** and raises `seg_stats::needs_ckpt_restore`
  (`duo.cpp:255`, set at `:775`) -> caller does `checkpoint_restore(easy)` and re-ingests the
  boundary-truncated text through `sync_to` (canonical delta tokenization, prefill speed at
  0.8B) -> hand off to mid through the existing carry-draft machinery. **Invariant to preserve:
  `needs_ckpt_restore` is a debt.** A caller that arms `conf_checkpoint` and then ignores the
  flag leaves the model's memory ahead of its `committed_tokens` with no diagnostic; the only
  caller today is the router easy path, and both of its exits (restore-and-re-ingest, or
  `checkpoint_drop` on any non-conf cut) are in the same block.
- **`--ttft-opener` defaults ON only for a 3-tier registry.** The brief's own gate exposed the
  conflict: baseline (a) *is* a router run, so a default-on opener would have changed it. Rule
  as implemented (`opener_enabled()`, `duo.cpp:1017`): explicit `--ttft-opener`/
  `--no-ttft-opener` win; otherwise on iff `s.easy != nullptr`. Registry *presence*, not
  `TS_READY`, is the auto test on purpose — under C3 the opener is the thing that covers easy's
  load, so it must arm before easy is ready. Documented in `print_usage()` as
  `[auto: on with a 3-tier bundle, off with 2]`. The opener runs on the first turn only
  (`s.history.empty()`, `duo.cpp:1038`), reuses the ordinary `--seg-min/--seg-max` budgets
  (24/96) and the seam rule, and its text is carried as a draft by whichever tier continues —
  including into `--hard-mode verify`, which gained a `seed_draft`/`n_seed` parameter pair and
  a local `budget` (`duo.cpp:1283`) so opener tokens are charged against `-n` instead of
  silently exceeding it. Without a seed both default to empty/0 and verify is bit-for-bit the
  old function.
- **Sampling defaults for easy, decided.** C1 flagged its `default:` branch (easy reusing
  `--temp-expert`/`--top-p-expert`) as a placeholder for C2 to settle. Settled as: easy keeps
  the **expert-style** values (0.6/0.95 by default) rather than the front's 0.7/0.9 — it is a
  competent 0.8B answerer, not a 135M drafter — and *inherits the flags*, not just the numbers,
  so `--temp-expert 0` still makes the whole run greedy (which is what every determinism gate
  below depends on). New `--temp-easy`/`--top-p-easy` (sentinel `<0` = inherit) override it
  (`duo.cpp:980-986`).
- **`--codraft-tiers A,B`** (`duo.cpp:1637-1671`, consumed at `:1164`) selects the codraft/
  random author pair; resolved **before** any model load so a bad pair fails in milliseconds,
  not after a 3 GB load. Rejects unknown names, a tier the bundle does not have (`easy,mid` on a
  2-model bundle -> `this bundle has no loaded 'easy' tier`), the same tier twice, a malformed
  spec, and `top` (registered-only, never loaded — the C1 fix round's point that *using* a top
  tier is not free). With `easy,mid` the slot-A author is append-only, which is Q1's
  hybrid-front support reached through the tier indirection: `gen_segment` commits instead of
  rewinding and the conf monitor stays off (no checkpoint is taken in codraft). Verified below.
- **Behavior change NOT covered by the C1 baseline set, found while self-reviewing.** The
  narrowed conf rule also arms the monitor for a *hybrid front* on a 2-model bundle
  (`muta-duo-q`'s front is the 0.8B, loaded with a checkpoint since Q1) — previously it was
  silently disabled there. The three C1 baselines are a hard-prompt router run plus codraft and
  verify, so **none of them enters the easy path**; the byte-identity gate could not have
  caught a change there. Closed by rebuilding the C1 binary (`git checkout 1cdcdc2 --
  tools/duo/duo.cpp`, rebuild, run, restore) and diffing an easy-prompt router run on both
  2-model bundles: `muta-duo-q` (hybrid front) `08b884af...` and `muta-duo` (dense SmolLM2
  front) `70426c90...`, **identical on both binaries** — the default `--conf-threshold -2.5`
  never triggers there. The newly-reachable path does work when forced: `muta-duo-q`,
  `--route-threshold 99 --conf-threshold -0.3 --carry-draft`, hard prompt -> front cut at 30
  tokens, `[esc] author=front restore+redecode chars=111`, expert continued for 162 tokens,
  coherent single answer.
- **Gates (all serialized, macOS `llama.cpp/build` BLAS-on arm64).**
  - (a) Regression: the three C1 baselines re-run on the C1 binary first (sha256 `4bbb514f...`
    / `f726b586...` / `eb906de6...`, all three matching `task-C1-report.md` exactly, so the
    baselines are regenerated-and-confirmed, not merely quoted), then on the C2 binary:
    **byte-identical, all three** (`diff -q` silent). No `[opener]` line in the 2-tier router
    run, confirming the defaulting rule.
  - (b) Trio routing: easy prompt -> `route=easy ... author=easy`; hard prompt ->
    `route=hard s=1.030 author=expert`. Both coherent.
  - (c) Escalation: trio, `--route-threshold 99 --carry-draft`, hard prompt. At the brief's
    `--conf-threshold -0.9` the 0.8B never triggers (its mean logprob on this prompt is ~-0.21,
    an order of magnitude above the threshold that SmolLM2 needed in Phase 3) — recorded rather
    than papered over. Swept to `-0.4`/`-0.3`, both trigger cleanly: `[seg 0] author=easy ...
    cut=conf` -> `[esc] author=easy restore+redecode chars=352` -> `[seg 1] author=expert ...`,
    coherent single answer. A 2-turn run proves the restored state is not desynced: turn 1
    escalates, turn 2 has easy author correctly from the restored context and no opener (first
    turn only).
  - (d) Opener: trio + default opener -> `[opener] author=front tokens=28 ... cut=eos` then
    `[seg 0] author=easy`; `--no-ttft-opener` -> no opener line, easy answers alone.
  - (e) `--codraft-tiers easy,mid`, trio, hard prompt: 6 segments alternating easy/expert,
    `[selftest] front: OK (0 tokens) / easy: OK (262) / expert: OK (321)`, 0 resyncs, coherent.
    Also 5 codraft turns with the default `front,mid` pair on the trio: **15/15 selftests OK**,
    `resync_front=0 resync_expert=0` on every turn (`selftest_seams` now covers easy too when
    it is loaded).
  - (f) Builds: macOS `llama-duo` (BLAS-on), `build-noblas` `llama-completion` *and*
    `llama-duo`, and the 4-target GCC container build (`scripts/stream_env.sh build`) — all
    exit 0 with **0 `error:`/`warning:` lines**; the container log shows `duo.cpp.o` actually
    recompiling (the binary timestamps are container-UTC, one hour behind host WAT — not a
    stale build).
- **Known cosmetic artifact, not fixed.** Forcing `--ttft-opener` on a 2-model bundle where the
  front both opens *and* continues can join the two spans without a space (`...today?A bit
  more...`) when the opener ends at EOS rather than at a seam-rule boundary: the front has
  declared its turn over and then resumes itself. Seam-exact (the delta tokenization still
  composes; `--closer expert` treats a front EOS as a handoff by design), but the join reads
  awkwardly. Not a default configuration — the opener is off by default for 2-tier bundles, and
  in the 3-tier case a different tier continues and the join is clean. Injecting whitespace no
  model generated would be worse, so it stands as documented behavior.

### Task C2 fix round (post-review, findings I1-I5), 2026-08-13

Task review of `1cdcdc2..2609120` confirmed the escalation protocol correct, leak-free and
canonically re-decoded, with five Important findings — all small, all localized. Fixed in one
commit, **`23fb79d`**, `S3.2: fix routing-state leak, opener attribution + escalation carry`
(1 file, +93/-40).

- **I1 — the routing decision read context it should not see (a real bug, older than C2).**
  `route_score()` decoded its few-shot on top of whatever was resident on the front's seq 0. The
  opener put this turn's rendered prompt (and, for a hybrid front, the committed opener text) in
  front of the few-shot — which is what the C2 report's "opener shifts the routing score"
  concern (`s=-1.798` vs `-2.098`) was actually measuring. The same class of pollution existed
  **before C2** on every turn >= 2, where the previous turn's committed transcript preceded the
  few-shot; nobody had looked. Fixed with `front_reset()` (`duo.cpp:819`) called before and
  after the routing decode (`:852`, `:863`): it drops seq 0 **and** `committed_text`/
  `committed_tokens` together — mandatory, because `committed_tokens` is the record of what is
  resident and `sync_to()` only ingests the delta past it, so wiping one without the other would
  have the front decode a fragment against an empty context (silent garbage, not a crash). The
  old append-only checkpoint round-trip inside `route_score` is gone: with the sequence emptied
  first, the trailing cleanup is a *full* removal, which recurrent/hybrid state supports (it is
  the PARTIAL rewind those models cannot do).
  - **Behavior correction, measured pre/post.** Turn 1 is unchanged — the sequence was already
    empty there, and clearing empty bookkeeping is a no-op — which is why all three 2-tier
    byte-identity baselines still hold (verified, not assumed: `4bbb514f...`/`f726b586...`/
    `eb906de6...`, `diff -q` silent). Turn >= 2 verdicts **do** change, and that is the fix:
    a 2-turn 2-tier router session gives `muta-duo-q` turn-2 `s=1.290 -> 2.084` and `muta-duo`
    `s=0.818 -> 1.064`, both still routing hard, **stdout identical on both bundles**. The
    post-fix turn-2 score `2.084` is exactly what a *fresh single-turn* run scores for that same
    question on that front — i.e. routing is now a function of the question alone. On the trio
    the opener-on score becomes `-2.098`, matching opener-off exactly (was `-1.798`), and the
    hard prompt's `1.064` matches `muta-duo`'s clean score for the same SmolLM2 front.
  - Consequence worth knowing: the front now re-ingests its prompt after every routing decode
    (it no longer keeps a committed prefix across the call). At 135M/0.8B prefill speeds this is
    negligible, and it makes the front's committed tokens the *canonical* tokenization of its
    committed text by construction — which is why the trio's `--hard-mode verify` numbers moved
    (`tokens=75 acc=0.62` -> `tokens=144 acc=0.71`): the front's draft context is now tokenized
    in one piece rather than as prompt+opener deltas. Not a regression; a different and more
    canonical starting state.
- **I2 — opener tokens were credited to the routed tier.** `[turn] ... author=easy tokens=35`
  where 28 of those 35 were the front's. The author label now names the front when an opener ran
  and the front is not already the author (`duo.cpp:1177`), matching the existing `front+expert`
  escalation convention: `front+easy`, `front+expert`, `front+easy+expert`. Same string feeds
  the jtrace turn event.
- **I3 — the default escalation threw away text the user had already watched stream.**
  `--carry-draft` defaults *off*, and the `!carry_draft` branch did `transcript.clear()`, which
  discarded the opener along with the low-confidence draft — the exact failure class that was
  refused on the verify path with `seed_draft`. Fixed by exempting the opener span
  (`duo.cpp:1142`, `transcript = opener_text`): `--no-carry-draft` discards the *draft*, and the
  expert's fresh answer continues from the opener. Gated on the trio (forced-easy, conf trigger,
  no `--carry-draft`): the returned answer begins with the committed 69-char opener, the
  discarded easy draft is absent from it, and the expert's continuation follows — while the
  `--carry-draft` run keeps both.
- **I4 — the riskiest new path had no automated seam check.** `run_turn` gated
  `--selftest-seams` on `p.mode != "router"`, so the conf-escalation seam was never verified.
  Exclusion dropped (`duo.cpp:1799`); no scoping was needed — the round-trip holds. Escalation
  gate re-run with `--selftest-seams`: **`front: OK (0 tokens)` / `easy: OK (186 tokens)` /
  `expert: OK (248 tokens)`**, i.e. the append-only easy tier's committed state re-tokenizes
  canonically after the checkpoint restore and re-decode. That is the strongest available
  evidence the escalation protocol is seam-exact, and it is now automated.
- **I5 — `--codraft-tiers` dereferenced tiers without a readiness check.** `run_codraft_turn`
  took `s.cd_a->m` unconditionally; under C3's background loading that is a null-ctx crash.
  Use-site `TS_READY` check added (`duo.cpp:1204`), mirroring the router's own test. The
  pre-load error string was also inaccurate ("no loaded 'easy' tier" when nothing is loaded yet)
  -> "this bundle has no 'easy' tier".
- **Minors folded in:** M1 two stale comments (`conf_monitor`'s "front only";
  `n_seq_max`'s "(verify mode)"); M2 verify's turn line now counts the seeded span's tokens and
  time via a `turn_seed` struct (`duo.cpp:1027`) that replaced the loose `seed_draft`/`n_seed`
  pair; M6 the C2 report's free-order citation `:1783` -> `:1789-1794`, corrected in the report's
  fix-round section rather than in place.
- **Re-run matrix, all serialized:** 3 byte-identity baselines (PASS, unchanged hashes); 2-turn
  2-tier pre/post on both 2-model bundles (turn-1 identical, turn-2 corrected, stdout identical);
  trio easy/hard routing with and without the opener (scores now match, authors correctly
  attributed); escalation with `--carry-draft` and at the default, both with `--selftest-seams`
  (all clean); `--codraft-tiers easy,mid` unchanged through the readiness guard (6 segments,
  3/3 selftests OK); all five `--codraft-tiers` error paths; `llama-duo` rebuild 0 errors/
  0 warnings.

### Task C3 (S3.3) — staged startup: mlocked front first, background tier loader, 2026-08-13

Commit **`be69fef`** (`llama.cpp`, branch `streaming`), `S3.3: staged startup - mlocked front
first, background tier loader` (1 file, +374/-59). `main()` now loads **only** the front tier
and starts answering; one background thread loads easy then mid, serialized, and publishes each
tier. This is the foundation of the TTFT mechanism — measured **first token 431-545 ms** on the
trio versus **11 247 ms** for the same prompt with `--no-ttft-opener` (macOS, warm cache,
`llama.cpp/build` BLAS-on arm64), a 26x cut that comes entirely from taking the two 248k-vocab
parses off the critical path. The formal G11 gate (cold cache, in-container, under the cap) is
still C4/Phase-gate work; these are the measurement hooks and the mechanism.

- **Front-first + mlock.** `POL_MLOCK` (the front's default policy) is now acted on at load
  time: `mparams.load_mode = LLAMA_LOAD_MODE_MMAP_MLOCK` (`duo.cpp:537`). This is the load-time
  half of tier policy; C4 still owns the residency half.
  - **Measured mlock size: 127 389 760 B = 121.5 MiB** for the trio front (`muta-trio.gguf`),
    of which 98.9 MiB is SmolLM2's own tensor span and **22.6 MiB is the shared bundle
    header/KV** in front of it — B1's loader grows the lock from the mapping base
    (`grow_to(weight->offs + n_size)`, `llama-model-loader.cpp:1594`), so a bundle member locks
    its own range *plus everything before it in the file*. For `muta-duo-q.gguf` (0.8B hybrid
    front) the same figure is 560 670 336 B = 534.7 MiB. C4's `mlock_front_mib` cross-term
    should use these numbers, not the model's tensor span.
  - Verified three ways rather than assumed: (1) no `failed to mlock` warning at default
    limits; (2) `ulimit -l` bracketing — at 116 MiB llama.cpp reports `failed to mlock
    606208-byte buffer (after previously locking 121602048 bytes)` and at 128 MiB it succeeds
    silently, bracketing the true total at 121.5 MiB; (3) the per-prefix byte ranges read out
    of the bundle with the tree's `gguf-py` agree exactly. System-wide `vm_stat` wired-page
    deltas were tried first and **discarded as evidence**: background activity on this machine
    moved wired memory by ±400 MiB, swamping the signal.
  - Degradation confirmed, not theorised: the forced-failure runs above load and answer
    normally after the warning. Note `-q` suppresses that warning (only ERROR passes the quiet
    callback), so a silently-unlocked front is possible in gate runs — check without `-q` when
    residency matters.
- **The loader thread.** `tier_loader_main` (`duo.cpp:1221`) → `tier_load_bg` (`:1178`) per
  tier: `TS_LOADING` → `load_duo_model` (unchanged) → publish. Publication is a release store
  **under** `tier_mu` plus `notify_all` (`tier_publish`, `:993`); consumers block in
  `tier_acquire` (`:1004`), which fast-paths an acquire load, prints one `[tier] waiting for
  <name> (loading) reason=...` line, and then sleeps on the cv — no spinning, one line per
  wait. Single-writer discipline is what makes the models lock-free: main writes front's state
  before the thread exists, the loader is the only writer of every other tier's state *and* of
  that tier's `duo_model`, and main touches a `duo_model` only after an acquire load has
  observed `TS_READY`. Audited every `->m` dereference in the file against that rule.
- **`TS_FAILED` added to the tier_state enum** (`duo.cpp:177`) — a deviation from the brief's
  three-state enum, and a necessary one: a background load that fails must wake its waiters,
  or `tier_acquire` would sleep on a predicate that can never become true. It is also the
  "skipped at teardown" state. A failed background load now sets the process exit code to 1.
- **Fallbacks (the G11 overlap).**
  - *easy not ready* → the front answers conf-monitored, **without blocking** (`duo.cpp:1317`,
    trace `[tier] easy not ready, front answers (conf-monitored)`). Gated with a 3-turn run
    under the slow-load hook: turn 1 `author=front` in 232 ms while easy loaded, turn 3
    `author=easy` once it had.
  - *mid not ready on a hard route* → the front keeps extending its opener with committed,
    seam-cut, conf-monitored segments, polling `TS_READY` at segment boundaries only (no
    cv-wait inside generation), then blocks on `tier_acquire`. With the opener off it is a
    plain blocking acquire — the deterministic path the identity gates run on.
  - **Deviation:** the brief also names the *escalation* target (easy→mid conf escalation) as
    an overlap site. Not implemented there, deliberately: front text appended after a draft
    that `--no-carry-draft` is about to discard would be re-ordered against what the user
    already watched stream, and the escalation's checkpoint-restore + canonical re-ingest
    assumes the author's own text is the only thing past the boundary. By escalation time a
    whole easy answer has been generated, so mid is loaded in practice. Reasoning recorded at
    `duo.cpp:1352-1359`.
- **Extension budget — plan said `3*seg_max`, tree needed more (measured).** With the plan's
  cap alone, the first trio gate run at `-n 128` produced `[opener] 62 + [seg 0..2] 66` front
  tokens and handed the routed expert **a zero budget** (`[seg 3] author=expert tokens=0
  cut=limit`): the 135M wrote the entire hard answer. The cap is now
  `min(3*seg_max, n_predict/2)`, with a segment started only when `seg_min` tokens still fit
  (`duo.cpp:1411`). After the fix the same run gives opener 62 / expert 66.
- **Determinism under overlap — measured, and better than the brief expected.** Extension
  segment *count* depends on load timing, so hard-prompt answers under the opener are not
  guaranteed byte-identical across machines. On this machine they were: at `-n 512` two runs
  whose mid load times differed by 2.1 s (5 785 ms vs 7 917 ms) produced **byte-identical
  answers** (`d648b1cc…`), because the extension terminates on the *budget cap* (256 tokens:
  62+27+33+38+40+27+29), never on mid-ready — the front's whole budget is ~0.8 s of generation
  against a 4-9 s mid load, so the cap always binds first. What did vary is where the
  `[tier] easy ready` line lands in the trace (between `[seg 3]` and `[seg 4]` in one run,
  between `[seg 4]` and `[seg 5]` in the other) — real interleaving evidence with no effect on
  text. The non-deterministic case is real but unreachable here; it needs mid to turn READY
  *mid-extension*. **`--no-ttft-opener` is the deterministic path** and is what the identity
  gates use.
- **Quality finding, reported not papered over.** In that `-n 512` overlap run the front wrote
  256 of 260 tokens and the expert closed with 4 tokens and EOS, because the front's text
  *looked* finished. The answer is seam-clean and coherent but mathematically worse than the
  expert-alone answer (it wanders into "solve for y" and "3x = 17"). The conf monitor does not
  catch it — the front's mean logprob stayed at -0.09..-0.29, nowhere near the -2.5 threshold:
  it is confidently wrong. G11 wants the overlap; whoever owns the TTFT-vs-quality trade-off
  should know it currently costs answer quality on hard prompts at long `-n`. **Corrected in the
  fix round below (I1): this bullet originally claimed `--hard-mode verify` "re-verifies the
  seeded span" and was the lever against this. That is false** — `run_verify_turn` only ingests
  the seed as context (`duo.cpp:1694`) and never judges it against the expert. There is no
  existing lever; the overlap extension is now disabled under verify instead.
- **Test-only hook: `MUTA_SLOW_LOAD_MS=<n>`** (`duo.cpp:1166`) sleeps n ms before each
  *background* load so the not-ready fallbacks can be exercised deterministically. Deliberately
  an env var and not a flag, absent from `--help`; it exists to make gate evidence
  reproducible. Never set it in a benchmark run.
- **Join discipline (no detached thread, no use-after-free).** The normal path sets
  `loader_stop` and joins explicitly *before* any tier is freed (`duo.cpp:2148`). Every other
  path is covered structurally: `duo_state`'s **last** member is a `loader_joiner` whose
  destructor joins (`:980`), and members are destroyed in reverse declaration order, so the
  thread is joined while `tiers`/`tier_mu`/`tier_cv` are still alive. The thread is started
  only after every fail-fast check (`:2076`), so no argument-validation error can leave a
  loader running. `loader_stop` lets a *not yet started* load be skipped; a load already inside
  `llama_model_load_from_file` cannot be aborted and is joined to completion.
- **Two races the second thread introduced, closed in the same commit.** `jtrace()` was three
  stdio calls, so the loader's `[tier]` event could land between a turn event's payload and its
  newline — now mutex-guarded, atomic as a *line* (`duo.cpp:344`; verified: 8/8 JSON lines
  parse in a concurrent run). The `-q` log callback's `static ggml_log_level prev` (CONT-level
  carry) is now `std::atomic` (`:1940`) — it runs on both threads.
- **Gates (all serialized, macOS `llama.cpp/build` BLAS-on arm64).**
  - (a) **Byte-identity, PASS, three times.** The three C1/C2 baselines on `muta-duo-q`
    (`4bbb514f…` / `f726b586…` / `eb906de6…`) reproduced exactly after the first commit, after
    the extension-budget fix, and again after the race fixes. Staged loading does not move a
    single output byte; the `[tier]`/`[ttft]` lines are stderr, stdout is untouched.
  - (b) **Trio overlap, PASS.** `-n 512`, hard prompt, opener on: `[opener] author=front` +
    `[seg 0..5] author=front` with `[tier] easy ready load_ms=…` interleaved among them, then
    `[tier] waiting for mid (loading) reason=hard route` → `[tier] mid ready load_ms=5784.8` →
    `[seg 6] author=expert`. TTFT 430.9 ms vs 11 247.3 ms for the `--no-ttft-opener` control.
  - (c) **easy-not-ready fallback, PASS** (3-turn run above, `MUTA_SLOW_LOAD_MS=4000`).
  - (d) **Teardown, PASS, four ways.** `--route-only` on the trio exits in 2.99 s with mid
    skipped; the same under the slow-load hook exits in 5.42 s with both tiers skipped;
    immediate EOF on the trio exits in 1.24 s; immediate EOF on `muta-duo-q` exits in 9.51 s
    because mid's load was already in flight and is joined to completion. All exit 0, no hang,
    no crash. ASAN was skipped as agreed — the argument is structural (single-writer tiers,
    join-before-free, joiner as last member) and the four teardown races above exercise it.
  - (e) **Builds clean:** macOS `build` (BLAS-on) and `build-noblas`, and the 4-target GCC
    container build (`scripts/stream_env.sh build`, exit 0, 0 `error:`, the only `warning:`
    being cmake's ccache notice; `duo.cpp.o` visibly recompiled).
  - Extra: `--codraft-tiers easy,mid` on the trio now **waits** where C2's I5 guard errored —
    `[tier] waiting for easy … / waiting for mid …`, 3 segments, `[selftest] front/easy/expert:
    OK`, 0 resyncs.

### Task C3 fix round (post-review, findings I1-I5), 2026-08-13

Task review of `23fb79d..be69fef` found the threading core sound (cv protocol, join discipline and
single-writer tier ownership all verified; `TS_FAILED` and the extension budget cap called
exemplary) with five Important findings. Fixed in one commit, **`c8aeb9e`**, `S3.3: cap opener
budget, handle conf in extension, verify-seed gating` (1 file, +101/-38).

- **I1 - `--hard-mode verify` had silently become an overlap site, and the seed is not verified.**
  Two defects, one of them in the C3 report. The *code* defect: the extension loop ran before the
  `hard_mode == "verify"` dispatch, so the extended front span became `run_verify_turn`'s seed.
  The *reporting* defect: the report (and the WORKLOG bullet above, both now corrected in place)
  claimed verify "re-verifies the seeded span" - it does not. `run_verify_turn` only ingests the
  seed as context (`sync_to(ex, expert_prompt + seed.text)`, `duo.cpp:1694`); verification starts
  with the drafts generated *after* it. Extending the seed multiplied **unverified front text**
  inside the one mode whose promise is that the expert approved what you are reading. Fixed by
  gating the extension on `p.hard_mode != "verify"` (`duo.cpp:1453`) rather than by implementing
  seed verification: the latter is a real feature (re-score the seed against `prev_row` in round
  1, with a rejection path that must rewrite text the user already saw) and does not belong in a
  staged-startup task. **Declared deviation:** under `--hard-mode verify` the opener still runs
  (C2 behavior, unchanged) but the C3 overlap extension does not. Gated: trio + `--hard-mode
  verify` + opener -> one `[opener] tokens=62`, zero `[seg k] author=front` lines, then
  `[turn] mode=verify rounds=6 rejects=2 acc=0.73`.
- **I2 - the "routed tier owns the majority" invariant was still breakable through the UNCAPPED
  opener.** `oopts.n_predict` was `p.n_predict`, so at `-n 64` the opener *alone* could consume the
  whole answer and hand the expert a zero budget - the same symptom the extension cap was added
  for, with no extension involved. The cap is now computed once as
  `front_cap = min(3*seg_max, n_predict/2)` (`duo.cpp:1319`) and applied to the opener **and** the
  extension, so it bounds everything the front writes in a turn; the comment now states what the
  code guarantees (the routed tier gets at least `n_predict/2`). Gated at the size that used to
  break it: trio hard `-n 64` -> `[opener] tokens=32 cut=limit` / `[seg 0] author=expert
  tokens=32`.
- **I3 - the extension armed the confidence monitor with no handler.** A fired monitor truncated
  the segment back to the seam boundary, emitted a visible `[[conf-cut -Nch]]` stream marker, and
  then changed nothing. Now handled (`duo.cpp:1482`): `cut=="conf"` breaks the overlap and falls
  through to the blocking acquire - the right escalation, since the front has declared itself
  unsure. Traced as `[tier] overlap stopped: front conf-cut mean_lp=..., escalating to mid`. The
  caveat is documented where it bites (`:1471-1479`): an append-only front never conf-cuts here
  (no checkpoint is taken on the opener path, so `gen_segment`'s `(!append_only ||
  conf_checkpoint)` guard disables the monitor), exactly as for the opener segment itself.
- **I4 - the mlock comment understated the locked range.** `duo.cpp:549` claimed a bundle member
  locks "its own ~100 MiB". It locks from the **mapping base**, so the range is header-inclusive.
  The comment now carries both measured figures (trio front 127,389,760 B = 121.5 MiB = 98.9 MiB
  weights + 22.6 MiB header; `muta-duo-q` front 560,670,336 B = 534.7 MiB), the note that C4's
  `mlock_front_mib` must use the LOCK RANGE, and the `-q`-hides-the-warning caveat.
- **I5 - TSAN run, done, CLEAN.** The C3 threading argument covered `duo.cpp` but said nothing
  about llama/ggml global state under concurrent load+decode, and ASAN had been skipped. A scratch
  build (`/tmp/c3-tsan`, RelWithDebInfo + `-fsanitize=thread`, arm64, `GGML_BLAS=OFF`, llama + duo
  only) built with 0 warnings; the exercise was trio router, hard prompt, opener on, `-n 64` - the
  front decoding its opener while the loader thread loads easy and then mid. **0 `WARNING:
  ThreadSanitizer` reports, exit 0.** The trace confirms the overlap really happened under
  instrumentation (`[opener] tokens=32` at 4.8 tok/s, `[tier] easy ready load_ms=11829.4`,
  `[tier] mid ready load_ms=26876.2` - TSAN's ~10x slowdown widens the concurrency window rather
  than hiding it). So concurrent load+decode is **verified for this workload**, not assumed; scope
  caveat: one run, one bundle, one mode, CPU backend only. (The TSAN binary is BLAS-off, so its
  route score reads `s=1.008` where the BLAS-on build reads `s=1.064` - different kernels, same
  verdict.)
- **Minors folded in:** M1 the `[tier] ... ready load_ms=` trace now prints *before* the
  `tier_publish` that wakes waiters (`:1244`), so cause precedes effect in the overlap traces G11
  is read from (visible in the re-run: `mid ready load_ms=2620.8` then `mid acquired
  wait_ms=1941.1`); M2 `tier_acquire` re-checks under the lock before announcing a wait (`:1043`),
  killing the phantom `waiting for ...` line when a tier arrives in the gap; M3 `loader_joiner`
  sets `loader_stop` before joining (`:1004`), so early returns skip not-yet-started loads instead
  of sitting through them (`--route-only` on the trio now exits in **1.75 s**); M4
  `ttft_note_first_token()` moved above `llama_decode` (`:835`) - that decode is prefill for the
  NEXT token and was inflating G11's headline number by a decode step.
- **Re-run matrix, all serialized:** 3 byte-identity baselines (**PASS**, `4bbb514f`/`f726b586`/
  `eb906de6`, a 4th consecutive verification); trio hard `-n 64` expert-budget floor (32/32);
  trio hard `-n 512` overlap trace (front segments with `[tier] easy ready` interleaved; answer
  **byte-identical to the pre-fix run**, `d648b1cc`); trio `--hard-mode verify` + opener
  (seed-only); trio codraft `easy,mid` (3/3 selftests OK, 0 resyncs, output unchanged);
  easy-not-ready 3-turn fallback (turn 1 front @242 ms, turn 3 easy); `--route-only` teardown
  (exit 0 in 1.75 s, mid skipped); TSAN run (0 warnings); `build` + `build-noblas` + container
  builds (0 errors, 0 compiler warnings, `duo.cpp.o` recompiled); comments still ASCII-only.

### Task C4 (S3.4) — residency wiring, ledger, tier-switch choreography, 2026-08-13

llama.cpp `streaming` **`5134e20`** `S3.4: residency wiring, ledger log, tier-switch
choreography, sticky demote` (6 files, +793/-20). Patches re-exported (`patches/0025..0031`,
the C1-C4 backlog). Nothing pushed.

- **`mlock_front_mib` source: the accessor won.** Added `LLAMA_API uint64_t
  llama_model_mlock_bytes()` (`include/llama.h:634`, `src/llama-model.cpp:1734` via a public
  `llama_model::mlock_bytes()`, backed by a new `llama_mlock::size()` at
  `src/llama-mmap.cpp:877`). Three lines of real code against the bundle-manifest
  alternative's offset arithmetic, and it reports what is ACTUALLY locked rather than what
  was requested: a refused lock reads back 0, so duo falls back to the tensor span with the
  reason logged (`duo.cpp:1440`). Measured: trio front returns 127,389,760 B = 121.5 MiB,
  matching S3.3's three-way-confirmed lock range exactly.
- **The KV estimator is metadata-based, and it is exact.** `tier_read_facts()`
  (`duo.cpp:641`) opens each tier with `gguf_init_from_file(no_alloc)` and reproduces
  llama.cpp's own sizing: attention layers x n_ctx_seq x (n_embd_k_gqa + n_embd_v_gqa) x 2
  (F16), recurrent layers x n_seq_max x (n_embd_r + n_embd_s) x 4 (F32), with the
  qwen35 `(il+1) % full_attention_interval` recurrence rule and `n_layer = block_count -
  nextn_predict_layers`. It has to be metadata-based, not read off a live context: **mid's
  ledger charges easy's KV and easy's ledger charges mid's**, and at solve time one of the
  two does not exist. Verified against llama.cpp's own log lines, same run:

  | tier | n_ctx base -> effective | duo estimate | llama.cpp reported |
  |---|---|---|---|
  | front | 4096 (no checkpoint) | 90.0 MiB | `kv_cache 90.00` (4096 cells, 30 layers) |
  | easy | 4096 -> **8192** | 134.5 MiB | `kv_cache 96.00` + `recurrent 38.53` = **134.53** |
  | mid | 4096 -> **8192** | 356.5 MiB | `kv_cache 256.00` + `recurrent 100.50` = **356.50** |
  | easy | 8192 -> **16384** (duo default ctx) | 230.5 MiB | `kv_cache 192.00` + `recurrent 38.53` = **230.53** |

  (The first three rows are the G8 configuration of record, `--ctx-expert 4096 --tier-ctx
  easy=4096`; the fourth is the default-ctx run, so easy is verified at BOTH context sizes.
  mid at 16384 is never measured -- the ledger refuses before its context is created.)

- **The checkpoint doubling is not just easy's problem.** `load_duo_model` forces
  `checkpoint_seq` on any recurrent/hybrid model, and BOTH qwen35 tiers are hybrid, so mid's
  n_ctx is doubled too whether or not the mode asked for a checkpoint. `--ctx-expert 8192`
  therefore buys a 16384-cell cache. Itemized as its own `[checkpoint-doubled]` ledger line
  for exactly this reason.
- **Deviation, and the biggest finding: the compute buffer had to join the ledger.** The
  brief's cross-terms are weights + KV. Measured, that under-counts a trio by ~1.1 GiB: the
  scheduler reserves its graph buffer for the worst-case ubatch (n_ubatch positions all
  producing logits), so the final projection's `n_vocab x n_ubatch` f32 output dominates it,
  and this bundle's vocab is 248,320. Measured at n_ubatch 512: front 98.25 MiB, easy
  **505.02 MiB** -- and each is allocated at context creation and held for the process
  lifetime whether that tier decodes or not. Estimated in duo as
  `n_ubatch * 4 * (n_vocab + 12 * n_embd)`. Measured margins, all HIGH (the safe direction)
  but **not uniformly**: front@512 +11.5% (109.50 est vs 98.25), **easy@512 +0.79%** (509.00
  vs 505.02), front@128 +11.5% (27.38 vs 24.56), easy@128 +3.67% (127.25 vs 122.75), mid@128
  +8.35% (136.25 vs 125.75). The thin one is easy@512: **0.8% of cushion, ~4 MiB**, so the
  estimator is only just conservative at the large-ubatch end and must not be assumed to
  carry margin there. mid@512 was never measured -- the default-ctx ledger refuses before
  that context exists -- so the ~545 MiB previously quoted for it is the estimator's own
  output, not evidence. **The formula has no n_ctx term, which is only valid with flash
  attention ON**: without FA the graph also materializes KQ as `n_kv x n_ubatch x n_head`
  f32, which grows with the context and would be charged to nobody. llama's default is
  `LLAMA_FLASH_ATTN_TYPE_AUTO` and there is no API to read back what AUTO resolved to, so
  duo now sets it **ENABLED explicitly under `--stream-weights`** rather than assuming
  (`duo.cpp:824`). AUTO had already resolved to enabled on both measured builds
  (`resolve_fused_ops: Flash Attention enabled`, macOS arm64 and the aarch64 container), and
  forcing it leaves the streamed trio answer byte-identical. `--stream-reserve-mib` is now pure slack (default **256**: in-RAM
  vocab/tokenizer structures, the output buffer, non-mapped model buffers, allocator slop).
- **Consequence: `-ub/--ubatch` added** (`duo.cpp:78`, applied only when given so no-flag runs
  are untouched). It is the single largest non-weight RAM lever in this process -- 512 costs
  ~505 MiB per 248k-vocab tier, 128 costs ~123 MiB. **The trio cannot fit 2048 MiB at duo's
  default `--ctx-expert 8192` + n_ubatch 512**: the fixed non-weight cost alone is ~2.6 GiB
  before one weight byte of mid. The ledger says so and refuses (exit 1, inequality printed,
  no OOM, no crash) -- degradation, not errors, working as designed. The G8 preview
  configuration of record is therefore `--ctx-expert 4096 --tier-ctx easy=4096 --ubatch 128`.
- **Occupancy serialization is what makes the cross-terms add up.** At most one STREAMED tier
  is ACTIVE; `duo_switch_to()` (`duo.cpp:1637`) suspends the outgoing one, and suspend bulk-
  evicts *including its pins*. So a streamed tier charges another streamed tier's ledger for
  its KV + compute buffer and **nothing** for its weights. Enforced at both ends: a manager is
  parked (`llama_residency_suspend`) the moment it is built (`duo_residency_park`,
  `duo.cpp:1554`), so two tiers' pins are never installed at once, and `tier_activate()`
  (`duo.cpp:1663`) pairs every acquire with a switch -- a streamed tier that is decoded
  without being resumed still produces correct tokens (demand faults) but its window logic is
  parked, i.e. its RAM is no longer bounded, which is the one thing a cap run must not lose.
- **Deviation: streamed tiers load FIRST under `--stream-weights`** (`tier_loader_main`,
  `duo.cpp:1876`), inverting C3's easy-then-mid order. A tier's policy is fixed at load time
  (`llama_model_params::stream_weights`), so the sticky demote -- decided by *mid's* ledger --
  has to happen before *easy* is loaded, or easy would have to be loaded twice. Cheap: a
  streamed load suppresses populate, so mid is mapped rather than read (740 ms in the
  container vs 8.9 s unstreamed on macOS).
- **Declared deviation (narrowing): the demote is feasibility-driven, not min-s/token.** The
  plan says the solver "evaluates easy-resident+HEAD-streamed vs easy-demoted+HEAD-pinned and
  picks min predicted s/token". What is implemented is narrower: duo demotes **only when
  `llama_residency_init` refuses** the easy-resident configuration -- feasibility -- and never
  compares two feasible plans' predicted s/token. (Within one configuration `res_solve` does
  still pick min streamed bytes across W and head placement; the narrowing is purely the
  cross-tier easy-resident-vs-demoted choice.) The 2048 MiB outcome is unaffected: there
  easy-resident is INFEASIBLE, not merely slower, so both rules agree on every number recorded
  here. They would diverge at a larger `--max-ram-mib` where both fit and keeping easy resident
  is the slower one. Not implemented because it needs a predicted-s/token probe of a
  configuration the process will not adopt, i.e. a dry-run entry point the residency API does
  not expose.
- **Sticky demote observed at 2048, every run.** With easy resident the ledger refuses
  (`R_pin` negative at W=1 both configs); `[ledger] DEMOTE easy resident->streamed` fires
  once, mid re-solves feasible, and easy then gets its own manager whose solve pins its
  entire 500.8 MiB (0 streamed) because a suspended mid only charges it KV + compute.
  Stickiness is structural: the policy field is overwritten in place and the ledger is never
  re-solved. `--tier-policy easy=resident` refuses to start instead, naming the flag.
- **Ledger of record, trio @ 2048 MiB, ctx 4096, ubatch 128** (identical macOS and container):
  mid = **head-pinned**, head 497.3 MiB pinned, 0 blk pinned, **2106.2 MiB streamed** over 32
  ring units, W = 2, predicted **0.742 s/token** at D = 2.977 GB/s. Container measured
  **1.3-1.7 tok/s** on the streamed segments -- the prediction is good to ~10%.
- **Cap runs.** *Environment (results.md section 5 convention): container `muta-stream`
  (`scripts/Dockerfile.streaming`, `ubuntu:22.04`), llama.cpp branch `streaming` @ `7593921`,
  `GGML_BLAS=OFF GGML_NATIVE=OFF -DGGML_CPU_ARM_ARCH=armv8.5-a+dotprod+i8mm+fp16`, Docker
  Desktop's native **aarch64** linuxkit VM, cgroup v2, 7.653 GiB VM RAM, metric
  `/sys/fs/cgroup/memory.peak` via `scripts/stream_env.sh cgrun`. **These are
  aarch64-Linux-on-Apple-Silicon numbers, NOT the x86-64 ADTC target** -- architecture-
  comparative, to be re-measured on target hardware, the same caveat results.md section 5 and
  POC_REPORT.md already carry. The macOS figures elsewhere in this entry are arm64 Darwin
  (`llama.cpp/build`, BLAS-on) and are machinery evidence only: Darwin eviction is advisory.*
  All runs exit 0, OOMKilled=false:

  | run | cgroup `memory.max` | `memory.peak` | vs 2048 |
  |---|---|---|---|
  | (i) easy prompt, easy answers | 3 GiB (observed mode) | 1,486,786,560 B = **1417.9 MiB** | -630 |
  | (ii) hard prompt, mid streams (-n 96) | 3 GiB (observed mode) | 1,720,262,656 B = **1640.7 MiB** | -407 |
  | (iii) forced easy->mid escalation | 3 GiB (observed mode) | 1,737,383,936 B = **1656.9 MiB** | -391 |
  | (d) 3-turn alternating easy/hard/easy | 3 GiB (observed mode) | 1,734,234,112 B = **1653.8 MiB** | -394 |
  | **(iii) re-run under G8's own condition** | **2048 MiB (enforced)** | 1,840,775,168 B = **1755.2 MiB** | **-293** |

  The last row is the one that answers G8: with the cgroup limit set AT 2048 MiB rather than
  merely observed under a looser 3 GiB, the escalation run of record still completes -- exit 0,
  OOMKilled=false, 292.8 MiB of headroom, `[tier] switch easy->mid reason=conf` intact. Its
  peak is ~98 MiB HIGHER than the same run at 3 GiB, the expected direction for page-cache
  accounting under a tighter limit, not a regression.

  Control: the same trio **without** `--stream-weights` is **OOM-killed at 3 GiB** (exit 137).
- **Switch evidence** (gate d, one process): `switch none->easy reason=route-easy` ->
  `switch easy->mid reason=route` -> `switch mid->easy reason=route-easy`, each followed by
  `[ledger] active=<tier> pinned=... streamed=... W=2 config=head-pinned`. Gate (c)(iii)
  produces `[tier] switch easy->mid reason=conf` after a real conf cut + checkpoint restore.
- **PRE-EXISTING DEFECT FOUND, not C4's, and it blocks G8's answer-quality half: the SmolLM2
  front produces garbage in the container build.** Its opener is
  `staking solicitarith\`):` repeated (mean_lp -1.47/-1.65) and every route score is shifted
  strongly positive (`Say hello.` scores **+2.35** in the container vs **-3.16** on macOS), so
  the router sends everything hard at the default threshold 0.0. Proved pre-existing with a
  no-flag control at an 8 GiB cap: byte-identical garbage, `s=4.158` vs `4.170` streamed.
  Not mlock (`--tier-policy front=resident` gives identical scores). The easy and mid tiers
  are fine in the same binary (coherent answers, mean_lp -0.05). Suspect the aarch64-Linux
  `GGML_BLAS=OFF` CPU kernels / Q4_K repack on this 135M llama-arch model. C4's gates use
  `--route-threshold 3.0` to separate easy from hard on the container's shifted scale; the
  RESIDENCY machinery under test is unaffected, but **G8 cannot claim answer quality on the
  trio until this is diagnosed**.
- **Free order, stated and enforced** (`duo_tier_free`, `duo.cpp:288`): sampler -> context ->
  residency manager -> model. The context's `cb_eval` points at the manager, so the manager
  must outlive the context; the manager evicts through the model's mapping, so it must die
  before the model. Same ordering `common_init_result` gets from member declaration order.
- **Self-review catches (fixed before the amend):** (1) `duo_residency_park` read
  `duo_state::active_streamed` from the LOADER thread while main writes it -- a real data
  race; the read is gone, the park is unconditional, and it is provably equivalent (a tier
  that has not been published cannot be the active one). (2) `duo_switch_to` now gates on an
  ACQUIRE load of `TS_READY` before touching `duo_tier::residency`, which the loader writes --
  pairing with `tier_publish`'s release; the early hard-path switch is simply a no-op until
  mid is ready. (3) dead `demoted_easy` state removed (stickiness is structural).
- **Gates:** (a) byte-identity **PASS, verified three times** (`4bbb514f`/`f726b586`/
  `eb906de6` on `muta-duo-q`, plus the trio no-flag router run `d648b1cc` unchanged) --
  the wiring is inert without `--stream-weights`; (b) macOS streamed trio **PASS** (coherent
  128-token algebra answer, full ledger block, `switch none->mid`, 15/15 `--json-trace` lines
  parse, 7 of them ledger events); (c) container G8 preview **PASS** (table above);
  (d) switch hygiene **PASS**; (e) builds **clean** -- macOS `build` (BLAS-on),
  `build-noblas`, and the container (`stream_env.sh build`, 0 errors, 0 compiler warnings).
- **Trace-string change (cosmetic, stderr only):** `tier_acquire`'s reason strings are now the
  plan's vocabulary (`route`, `conf`, `verify`, `codraft`) instead of C3's `hard route` /
  `conf escalation`, so acquire and switch lines share one reason space.

### Task C4 fix round (post-review, findings I1-I7), 2026-08-13

Task review of `c8aeb9e..5134e20` confirmed the machinery (occupancy serialization enforced,
switch coverage complete for the shipped policies, teardown correct, the compute-buffer
discovery credited) with seven Important findings. Three were code, four were the record.
Code fixed in one commit, **`7593921`**, `S3.4: fatal unknown-facts + refusal, FA guard`
(1 file, +74/-10).

- **I1 - an unreadable tier charged the ledger ZERO.** `duo_tier_resident_bytes` returned
  `facts.weight_bytes` unguarded and the KV/compute terms were `facts.known`-gated, so a tier
  whose metadata could not be read vanished from the budget entirely (and for the tier being
  solved, `reserve` collapsed to slack with a giveaway `own kv 0.0 MiB (n_ctx 0 x 0 seq)`
  line). Chose **fatal over pessimistic-charge**: a pessimistic charge needs a defensible
  worst case for a file we could not parse, which is a guess wearing a number, whereas the
  honest statement is "the ledger cannot account for a tier it cannot measure". Under
  `--stream-weights` an unreadable tier now refuses to start, naming the tier, the prefix and
  the file (`duo.cpp:2760`); the invariant that establishes is stated where
  `duo_tier_resident_bytes` relies on it. Gated: `--tier-file mid=/nope/missing.gguf` ->
  one-line error, exit 1, nothing loaded.
- **I3 - a refusal did not stop the process.** After `llama_residency_init` returned NULL the
  loader carried on. Two concrete bad outcomes, both reachable: with an explicit
  `--tier-policy easy=resident` the REFUSAL was followed by loading easy RESIDENT -- exactly
  the allocation the ledger had just declared unaffordable -- and a double refusal left easy
  mutated to STREAMED and ran the whole session with no mid tier, exiting 1 only at the very
  end. A refusal is now **fatal at the point of refusal** (`duo_mark_fatal`, `duo.cpp:1583`):
  `loader_stop` so every not-yet-started tier publishes a terminal state instead of loading,
  plus a `duo_state::fatal` flag the turn loop checks, so `main` stops instead of degrading
  and exits 1 with the inequality. This is the degradation contract's *clean refusal*: the
  contract says a student never sees a crash, not that a refused budget should be
  half-served. Gated: `--tier-policy easy=resident` at 2048 MiB -> REFUSED line, exit 1,
  **zero `loading easy` lines** (was: easy loaded resident anyway). Stale
  "caller frees the model" comment corrected while there.
- **I4 - the estimator margin was over-claimed, and it silently assumed flash attention.**
  Both corrected in place above: real per-term margins (+0.79% at easy@512, not "4-12%
  across all three"), mid@512 relabelled as estimator output rather than measurement, and
  `--stream-weights` now sets `LLAMA_FLASH_ATTN_TYPE_ENABLED` explicitly (`duo.cpp:824`)
  because llama's default is AUTO and nothing reads back what AUTO chose. Verified: the
  streamed trio answer is **byte-identical** with FA forced, and all three contexts now log
  `flash_attn = enabled` instead of `auto`.
- **I2, I5, I7 - record corrections** (the deviation list, the KV-verification table labels,
  and the architecture header), applied in place above.
- **I6 - the 2048 MiB row.** Every earlier container run used `cgrun 3g`, which observes the
  peak under a looser limit rather than testing G8's actual condition. Added; see the cap-run
  table. **exit 0, OOMKilled=false, 1755.2 MiB under an enforced 2048 MiB cap.**
- **Cosmetic, noted not fixed:** duo's `fprintf(stderr, ...)` traces and llama's `common_log`
  (which writes from a background worker thread) can interleave *within* a line, so a
  `[ledger]` line adjacent to a llama-side log line can appear with a `0.01.019.423 E` prefix
  glued to it. It makes the human-readable block occasionally ragged; `--json-trace` is the
  machine-readable channel and is unaffected (`jtrace` is mutex-guarded and writes its own
  FILE).
- **Re-run matrix:** byte-identity **PASS** (`4bbb514f`/`f726b586`/`eb906de6`, a fourth
  consecutive verification -- the wiring stays inert without the flag); macOS streamed trio
  smoke **PASS** (answer byte-identical to the pre-fix streamed run, DEMOTE + `switch
  none->mid` intact); I1 smoke **PASS**; I3 smoke **PASS**; I6 2048 MiB run **PASS**; macOS
  `build` + `build-noblas` **clean, 0 warnings**; container build **clean, 0 errors**.
