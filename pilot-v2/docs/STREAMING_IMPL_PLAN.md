# Weight Streaming under a RAM Cap — Implementation Plan (pilot/v2)

> **STATUS (2026-08-14, final): the plan is COMPLETE.** Phases A, B, Milestone A, C, D,
> and E all executed; gates G8–G12 all run (G8/G9/G11 PASS, G10 curve → default K=16,
> G12 managed 1.69×); C5 diagnosed AND properly fixed (S3.5 `--no-repack`). Engine tip =
> `patches/0035`. An earlier same-day wrap-up had descoped D/E — that note is superseded.
> Results of record: `bench/results.md` §5 ("The formal gates") and
> `docs/POC_REPORT.md` §Streaming; per-task entries in `docs/WORKLOG.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. On execution start, copy this plan to `docs/STREAMING_IMPL_PLAN.md` in the worktree (house convention: plans live in `docs/`).

**Goal:** Implement `docs/STREAMING_PLAN.md` (Phase 5) on `pilot/v2` with the three existing models (no downloads): no streamed model's weights ever fully resident, total charged memory held under `--max-ram-mib` (default **2048**, configurable), verified by cgroup v2 — and answer the headline question: **can Qwen3.5-4B (2.61 GiB Q4_K_M) stream-decode under a 2 GiB cap, and at what tok/s?**

**Architecture:** A residency manager inside llama.cpp (`src/llama-residency.{h,cpp}` + small public C API) builds per-layer page-aligned range tables post-load and executes pin/evict/prefetch verbs on a background thread; a `cb_eval` scheduler callback gates on layer transitions to slide a W-layer window; llama-duo grows a 3-tier registry (front=SmolLM2 mlocked, easy=0.8B resident/demotable, mid=4B streamed) with staged startup, ledger-logged tier switches, and a speculative-decoding amortizer (easy drafts K tokens; one batched verify pass reads the streamed region once per round). Gates run inside a native arm64 Linux container (Docker Desktop, cgroup v2); macOS is the dev loop.

**Tech stack:** llama.cpp @ b10331+16 (local branch with bundle/duo patches), C++17, madvise/posix_fadvise/mincore/mlock, Docker (ubuntu:22.04 arm64), gguf-py, bash/python harnesses.

## Global constraints

- `MAX_RAM` default **2048 MiB**, configurable via `--max-ram-mib`. Gate metric = cgroup v2 `memory.current`/`memory.peak` (anon + mapped file + page cache charged to the scope).
- **No model downloads.** Tiers: front=`models/SmolLM2-135M-Instruct-Q4_K_M.gguf` (105,454,144 B), easy=`models/Qwen3.5-0.8B-MTP-Q4_K_M.gguf` (549,698,976 B), mid=`models/Qwen3.5-4B-Q4_K_M.gguf` (2,740,937,888 B). **Top (27B) tier deferred** — registry must accept it later as pure data (`--tier`/`--tier-file`), zero code change.
- **GGML_BLAS=OFF for every cap-relevant build** (Accelerate F32-dequants the 2560×248320 tied head ≈ 2.5 GiB transient — blows any 2 GiB cap). Keep existing `llama.cpp/build` (BLAS on) untouched for duo regression baselines.
- House rules (DUO_POC_PLAN §0): **discovery beats this document** — deviations logged in `docs/WORKLOG.md` (what plan said → what tree has → what was done, file:line); one commit per task ID; never modify `models/`; llama.cpp commits on a new branch **`streaming`** (fork of current `master` tip `01f58cd`), `<task-id>: <summary>` + `Assisted-by:` trailer, ASCII-only comments; patches re-exported to `patches/` after each phase; gates close phases.
- Every gate/bench run is **serialized** (WORKLOG's "0.6 tok/s catastrophe" lesson); scripted runs use `llama-completion` (this tree's `llama-cli` busy-spins on EOF stdin).
- macOS builds need: `-DCMAKE_OSX_ARCHITECTURES=arm64 -DGGML_NATIVE=OFF -DGGML_CPU_ARM_ARCH=armv8.5-a+dotprod+i8mm+fp16 -DCMAKE_CXX_FLAGS="-nostdinc++ -isystem /Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/include/c++/v1" -DLLAMA_CURL=OFF -DGGML_METAL=OFF -DLLAMA_OPENSSL=OFF`.

---

## Context

The DUO PoC (Phases 0–4) is fully green: bundle packing, `bundle_prefix` loader patch, `llama-duo` router/co-draft/verify modes, same-family 0.8B front (G1–G7 PASS, 2026-08-09). `docs/STREAMING_PLAN.md` is Phase 5. The user asked for this plan, capped RAM at 2 GiB (configurable), forbade model downloads, and (asked-and-answered) chose: **(1)** Linux-container gate environment + macOS dev loop; **(2)** full S0–S5 scope, ordered so **Milestone A** (single-model streamed 4B under the cap) lands early and is reported as a checkpoint before multi-tier/spec-dec work proceeds.

### Verified ground truth (recon + audit, 2026-08-12 — do not re-derive)

**Models (read directly from the GGUFs):** all three have **tied output heads** (no `output.weight` anywhere). 4B: `token_embd.weight` = **497.3 MiB** (Q6_K) — the logits matmul reads all of it **every token**, so the spec's "embeddings excluded from the hot set" is wrong here: `token_embd` becomes a **HEAD pseudo-layer**, pinned first whenever the ledger allows. 4B blk: 32 layers, 57.7–70.3 MiB each (b_layer_max = 70.3, avg 65.8), 2106 MiB total; 24 GDN + 8 full-attention layers (`full_attention_interval=4`; GDN state cannot partially rewind). 0.8B: embd 198.9 + blk 314.8 MiB (25 layers, incl. 1 MTP nextn layer); same 248,320-token vocab as the 4B. SmolLM2: embd 28.7 + blk 70.2 MiB, 49,152 vocab (never a token-level draft for Qwen).

**Environment:** host = M2 Pro, 16 GiB RAM, 16 KiB pages, no cgroups/systemd-run/posix_fadvise/`iostat -x`/GNU-dd/`timeout`; 22.6 GiB disk free. Docker Desktop runs a native **aarch64** linuxkit VM (kernel 6.12.54), **cgroup v2**, 7.653 GiB VM RAM; enforcement = `docker run --memory=X --memory-swap=X`, metric = `/sys/fs/cgroup/memory.{current,peak,stat}` in-container. Bind mounts are virtiofs (wrong IO class for gates) — models go on a named volume.

**llama.cpp tree (b10331+16, clean, branches bundle-poc→duo-verify→duo-qwen-front stacked; patches/0001–0016 mirror it):**
- `llama_mmap` is **MAP_SHARED + PROT_READ**, whole file at offset 0 (`src/llama-mmap.cpp:447-457`). Ctor already has `prefetch` arg; full-file `posix_madvise(WILLNEED)` is unconditional today via `llama_model::load_tensors` → `init_mappings(true,…)` (`src/llama-model.cpp:1538`, `llama-model-loader.cpp:1378`) — must be suppressed for streamed models. `unmap_fragment` is munmap-based (destructive) — copy only its `align_range` idiom (`:478-488`).
- **The loader's fd is closed after load** (loader is a stack local, `src/llama.cpp:307`; only `mappings` move into `llama_model::impl::mappings`). `weights_map` (per-tensor file offsets) dies too. Post-load: enumerate via `tensors_by_name` (`src/llama-model.h:635`); file offset = `t->data − mapping->addr()`. The residency manager **re-opens the model path** with its own fd for fadvise.
- `cb_eval` exists (`include/llama.h:379-380` → `ggml_backend_sched_set_eval_callback`, `src/llama-context.cpp:1350`; sticky across graph reuse). **ASK phase runs ahead of compute** (coalescing loop, `ggml/src/ggml-backend.cpp:1730-1767`): eviction must anchor on **POST** (ask=false) of a gate node — at POST of the first node touching layer N, all of layer N−1 is provably complete. Returning true from ASK splits the graph + syncs (no-op on CPU backend); be selective. Reference: `tools/imatrix/imatrix.cpp:225-243,1135-1137` (inspects `t->src[0]`, sets `warmup=false`).
- `llama_model_params` has **`load_mode` enum** (not use_mmap/use_mlock bools): streaming requires `LLAMA_LOAD_MODE_MMAP`; front mlock = `LLAMA_LOAD_MODE_MMAP_MLOCK`. `llama_mlock::grow_to` is monotonic whole-mapping — use raw `mlock()`/`munlock()` per range instead.
- In-tree speculative decoding is a **pluggable multi-impl system** (`common/speculative.{h,cpp}`: draft_simple/eagle3/dflash/**mtp**/ngram; `--spec-type`, `-md`; per-seq begin/draft/accept). **`llm_arch_supports_rs_rollback()` includes qwen35** (`src/llama-arch.cpp:993-996`) — the in-tree path may work on the hybrid target natively. duo's own `--mode verify` (seq_cp checkpointing) is the proven fallback: 0.8B→4B acceptance 0.55–0.75 measured. Both mechanisms verify K tokens in **one** `llama_decode` → one streamed-region read per round.
- duo has **no tier concept** (hardcoded front/expert), loads models at exactly one site (`tools/duo/duo.cpp:274-325`), stays on public headers. `scripts/pack_bundle.py` is already N-model capable. duo verify's reject path re-decodes the accepted prefix in a second full `llama_decode` (`duo.cpp:963-989`, unavoidable — GDN can't rewind) → **a rejected round costs ~2 streamed-region reads**; and `repair_min=0` does NOT skip the repair span (`seg_min==0` degenerates to a ~16-token cap run, `duo.cpp:437,484,1040-1043`) — D2 patches this explicitly.
- **Bundle loads parse the whole file's KV section regardless of prefix** (prefix filtering is tensor-side only, `llama-model-loader.cpp:578-582`) — a front-tier load from the trio bundle parses both 248k-token vocab arrays on the critical path; and stock loads `MAP_POPULATE` + WILLNEED the **entire** bundle (`init_mappings(true,…)` unconditional), installing PTEs over other tiers' regions — which would make their `fadvise(DONTNEED)` permanently unable to drop page cache (`invalidate_mapping_pages` skips mapped pages). Both are addressed by design below (B1 suppression for all bundle loads; G11's `--tier-file` lever).
- `src/` is a PRIVATE include dir — the residency manager lives **inside** libllama with a public C API; tools never reach into `src/`.

### Deviations from STREAMING_PLAN.md (log each in WORKLOG at execution)

| Spec says | Reality | Decision |
|---|---|---|
| 4 tiers incl. 27B; S0.1 dd's the 27B | absent; no downloads; 22.6 GiB disk | 3 tiers; G10 runs on **mid**; dd uses the 4B |
| `systemd-run --scope -p MemoryMax` backstop | no systemd on host or in VM | `docker run --memory=X --memory-swap=X`; metric `/sys/fs/cgroup/memory.{current,peak}` |
| evict = madvise **and** fadvise (R8: MAP_PRIVATE nuances) | mapping is **MAP_SHARED**: madvise(DONTNEED) drops PTEs only; **fadvise(DONTNEED) is the uncharging call** (PTEs must drop first) | S0 probe verifies order + uncharge; MAP_FIXED re-mmap is plan-B evict |
| embeddings excluded (rows fault per token) | **tied head**: token_embd read fully every token | HEAD pseudo-layer, pinned first (497.3 MiB); if unpinnable, streamed last + loud log |
| ledger window term `W·b_layer` | instantaneous residency = current + trailing-unevicted + W prefetched; HEAD may itself be streamed | **(W+1)·b_layer_max + max_streamed_unit** (= 70.3 MiB normally; = 497.3 when HEAD is streamed) |
| `t_verify ≈ (S−R)/D`, one read per round | reject path re-decodes accepted prefix → 2 reads on ~P(reject)≈0.9 of rounds at K=8 | amortizer model ≈ `(1+P(reject))·(S−R)/D/(a·K+1)`; G10 measures reality |
| "wire the tree's draft/verify path", b10035 flag lore | tree is b10331+16 with pluggable spec + qwen35 rollback support | S4.0 probe decides in-tree path vs duo verify mode |
| gate: `memory.current < MAX_RAM` under the enforcing scope | an enforced cap clamps the metric trivially | two cap modes: **observed** (memory.max=3g, manager must hold <2048 alone — the honest gate) + **enforced** (memory.max=2048m, no OOM) |

### Ledger sketch (planning envelope, verified by G9)

Milestone A (4B alone, c=4096, reserve=KV~130+compute+slack≈640 default, W=2): R_pin ≈ 1127 MiB → HEAD (497) + ~9 layers; streamed ≈ 1.47 GiB/token → at D≈2–3 GB/s ≈ **1.3–1.9 tok/s** raw (adversarially re-checked). Multi-tier under 2048: front(mlock, measured ~100–120) + easy resident(524) + reserve leave HEAD **unpinnable** — the solver evaluates both configs (easy-resident + HEAD-streamed vs easy-demoted + HEAD-pinned) and picks min predicted s/token; with the amortizer, easy-resident is forced and HEAD streams. Amortizer economics (honest model): a K=8 round costs 1 streamed read on full accept, ~2 on reject (redo decode); at a≈0.6–0.75 → effective ≈ **550–750 MiB read/token** — ~2× better than draftless streaming, not the naive 300–400. Streamed break-even acceptance is still ~0.1, so even prose (a≈0.4) wins. All of this is planning envelope; G9/G10 measure.

---

## File map

| Path | Role |
|---|---|
| `scripts/Dockerfile.streaming` | Create — ubuntu:22.04 (ADTC target OS) + build-essential cmake git sysstat time python3 |
| `scripts/stream_env.sh` | Create — image build, container llama.cpp build, `cgrun CAP CMD…` wrapper (always dumps memory.peak/stat), `drop_caches`, volume provisioning |
| `scripts/memwatch.sh` | Create — in-container 1 Hz CSV: memory.current/peak/stat(file,anon) |
| `scripts/layer_sizes.py` | Create — per-layer/head byte tables, tied-head + contiguity assertions (models + bundle) |
| `scripts/stream_probe.c` | Create — standalone madvise/fadvise/mincore semantics probe |
| `scripts/milestone_a.sh` | Create — Milestone A run matrix |
| `scripts/stream_gates.sh` | Create — G8–G12 orchestration + results-table emitter |
| `scripts/spec_accept.py` | Create — per-domain acceptance harness (json-trace parser, modeled on sweep_duo.py) |
| `scripts/verify_bundle.py` | Modify — add S0.4 contiguity + S0.5 vocab-identity assertions |
| `llama.cpp/src/llama-residency.{h,cpp}` | Create — range tables, verbs, bg thread, ledger, selftest, cb_eval impl |
| `llama.cpp/include/llama.h` | Modify — `stream_weights` in model params; `llama_residency_*` API |
| `llama.cpp/src/llama-mmap.{h,cpp}` | Modify — `stream` ctor arg (kill WILLNEED/MAP_POPULATE, MADV_RANDOM + MADV_NOHUGEPAGE) |
| `llama.cpp/src/llama-model-loader.{h,cpp}`, `src/llama.cpp`, `src/llama-model.{h,cpp}` | Modify — threading + `mappings()` accessor (mirror patch-0001/0002 shape) |
| `llama.cpp/common/{common.h,common.cpp,arg.cpp}` | Modify — flags, residency init in `common_init_result` (:1234-1259), warmup=false |
| `llama.cpp/tools/duo/duo.cpp` | Modify — tier registry, staged startup, residency wiring, ledger log, amortizer |
| `bench/results.md` §5, `docs/{DISCOVERY,WORKLOG,POC_REPORT}.md`, `patches/` | Modify — reporting per house rules |

---

## Phase A — S0 discovery & environment (no llama.cpp changes; A1–A3 parallelizable)

### Task A1 (S0.1): container env + builds + D measurement
- [ ] `scripts/Dockerfile.streaming` (ubuntu:22.04; packages above) + `scripts/memwatch.sh` + `scripts/stream_env.sh` with subcommands: `image`, `build` (configure+build `llama-completion llama-duo llama-bench llama-speculative-simple` — note speculative-simple lives under `examples/`, keep `LLAMA_BUILD_EXAMPLES=ON` — into named volume `muta-build` from ro-bind-mounted `llama.cpp/`, `-DGGML_BLAS=OFF -DGGML_NATIVE=OFF -DGGML_CPU_ARM_ARCH=armv8.5-a+dotprod+i8mm+fp16`), `models` (cp 4B + `bundle/muta-trio.gguf` when it exists → volume `muta-models`), `cgrun CAP CMD…` (`--memory=$CAP --memory-swap=$CAP --cpus=6 --cgroupns=private`, dumps memory.peak + memory.stat + OOMKilled on exit), `drop_caches` (privileged `sync; echo 3 > /proc/sys/vm/drop_caches`).
- [ ] macOS BLAS-off build: `llama.cpp/build-noblas` (mandatory flag set; verify `GGML_BLAS: OFF` in cmake log).
- [ ] Measure **D**: in-container `dd if=<4B on volume> of=/dev/null bs=1M iflag=direct` after drop_caches (= the ledger's D); also virtiofs-bind variant and non-direct cached ceiling; record `getconf PAGESIZE`, THP mode, `uname -r`.
- [ ] Write `docs/DISCOVERY.md` §"S0 — streaming ground truth" (D table, page size, THP, versions). Commit (pilot/v2): `S0.1: streaming container env + disk bandwidth ground truth`.

### Task A2 (S0.2): geometry tables
- [ ] `scripts/layer_sizes.py` (gguf-py via `sys.path.insert(0,'llama.cpp/gguf-py')`, run with `.venv/bin/python`): per-layer bytes, b_layer_max/avg, head/embd bytes + quant, tied-head detection, per-layer contiguity assertion (extent ≤ 1.05× byte-sum), layer-order monotonicity, token_embd file position — for all 3 models **and** `bundle/muta-duo-q.gguf` (prefixed names). Paste tables into DISCOVERY. Commit: `S0.2: per-layer size tables + tied-head + contiguity ground truth`.

### Task A3 (S0.3): eviction-semantics probe — **the go/no-go for the whole design**
- [ ] `scripts/stream_probe.c`: mmap 4B MAP_SHARED; steps: (1) touch region A, report Δmemory.current + mincore + fault bandwidth; (2) `madvise(A,MADV_DONTNEED)` alone → expect Δ≈0; (3) `posix_fadvise(fd,offA,len,POSIX_FADV_DONTNEED)` → expect Δ≈−len (order matters: PTEs first, else `invalidate_mapping_pages` skips mapped pages); (4) `madvise(B,WILLNEED)` from a second thread, poll mincore → prefetch bandwidth + does-WILLNEED-block (R10); (5) plan-B evict: `mmap(base+offC,len,PROT_READ,MAP_SHARED|MAP_FIXED,fd,offC)` + fadvise → Δ; (6) smaps_rollup + memory.stat at each step.
- [ ] Run in container (gate-grade) + informationally on macOS (steps 1–2, 4; no fadvise — document Darwin eviction as advisory-only). Record which evict primitive wins → DISCOVERY + WORKLOG. Commit: `S0.3: madvise/fadvise semantics probe + verdict`.

### Task A4 (S0.4+S0.5): trio bundle + verification gates
- [ ] Extend `scripts/verify_bundle.py`: per-prefix payload-interval contiguity assertion (print `[file_off, len]` per model — S1 range tables spot-check against these) + vocab-identity gate (easy tokens/merges/pre/special ids == mid; front != mid; print verdict lines).
- [ ] `pack_bundle.py --out bundle/muta-trio.gguf --model SmolLM2:m0.:front --model 0.8B:m1.:easy --model 4B:m2.:mid`; run verify. (~3.4 GB; fits. Delete `bundle/muta-duo.gguf` only if space gets tight — regenerable.) Commit: `S0.4: trio bundle + contiguity/vocab verification gates`.

**Phase A gate:** DISCOVERY has D, page size, geometry tables, probe verdict (evict verb uncharges memory.current), trio bundle verified. → WORKLOG entries for every spec deviation confirmed so far.

---

## Phase B — S1 residency manager + S2 hook (llama.cpp branch `streaming`)

### Task B1 (S1a): load-path opt-out + flags
- [ ] `include/llama.h`: `bool stream_weights` in `llama_model_params` (default false). Guard in `llama_model_load`: requires `LLAMA_LOAD_MODE_MMAP` + single-file model, else clear error.
- [ ] `llama_mmap` ctor gains `bool stream = false`: forces prefetch=0 (kills WILLNEED :462-467 + MAP_POPULATE :455), then `posix_madvise(addr,size,POSIX_MADV_RANDOM)` + `#ifdef MADV_NOHUGEPAGE madvise(...)` (R9). Thread through `llama_model_loader` (new member, mirror patch-0002 shape) and `init_mappings`.
- [ ] **Bundle-wide suppression (adversarial finding B3):** the stream/no-populate path applies to **every load with `bundle_prefix` set** (front and easy included, not just streamed models) — otherwise non-streamed tiers MAP_POPULATE/WILLNEED the whole 3.4 GB bundle, charge it to the cgroup, AND install PTEs over mid's region that block its fadvise eviction forever. After a bundle-member load completes, issue one `madvise(MADV_DONTNEED)` sweep over the mapping **outside that model's own payload interval** (intervals known from `mmap_used`/S0.4 tables) so no foreign PTEs remain. Mlocked front still touches only its own region (mlock covers `mmap_used` range, ~+15–20 MiB header — use the *measured* mlock size as the ledger term, not file bytes).
- [ ] `common_params`: `stream_weights=false, max_ram_mib=2048, prefetch_layers=2, pin_budget="auto", stream_reserve_mib=640, stream_disk_gbps=0.0f, residency_selftest=false`; `arg.cpp` flags `--stream-weights --max-ram-mib --prefetch-layers --pin-budget --stream-reserve-mib --stream-disk-gbps --residency-selftest` (add_opt style next to `--bundle-prefix`; all common-parser tools including llama-completion get them free). `common_model_params_to_llama` threads it; `common_init_from_params` forces `warmup=false` when streaming (log line).
- [ ] Verify: stock behavior byte-identical without the flag (greedy fixed-seed llama-completion run vs pre-patch). Commit: `S1a: stream_weights load-path opt-out + common flags`.

### Task B2 (S1b): the residency module
- [ ] `src/llama-residency.{h,cpp}` (added to `src/CMakeLists.txt`); one new internal accessor `const llama_mmaps & llama_model::mappings() const` (impl in llama-model.cpp where pimpl is visible).
- [ ] Public API in `include/llama.h`:
```c
struct llama_residency;                    // opaque
struct llama_residency_params {
    uint32_t max_ram_mib; uint32_t prefetch_layers; int32_t pin_budget_mib; /* -1=auto */
    uint32_t reserve_mib;                  // KV+state+compute+slack term
    uint32_t mlock_front_mib;              // cross-model ledger inputs (S3)
    uint32_t resident_other_mib;
    float    disk_gbps;                    // measured D; 0 = skip prediction print
    bool     mlock_pins; bool verbose;
};
LLAMA_API struct llama_residency_params llama_residency_default_params(void);
LLAMA_API struct llama_residency * llama_residency_init(const struct llama_model *,
        const char * path_model, struct llama_residency_params); // NULL = ledger refusal (prints inequality)
LLAMA_API void llama_residency_free(struct llama_residency *);
LLAMA_API bool llama_residency_sched_eval_cb(struct ggml_tensor *, bool ask, void *); // install as cb_eval
LLAMA_API void llama_residency_suspend(struct llama_residency *);       // bulk evict all, quiesce (tier switch out)
LLAMA_API void llama_residency_resume_async(struct llama_residency *);  // re-pin + first-W prefetch on bg thread (tier switch in)
LLAMA_API bool llama_residency_selftest(struct llama_residency *);
struct llama_residency_info { uint64_t pinned_bytes, streamed_bytes, head_bytes, b_layer_max;
    uint32_t n_pinned_layers, n_streamed_layers, window; bool head_pinned, head_tied; };
LLAMA_API struct llama_residency_info llama_residency_get_info(const struct llama_residency *);
```
- [ ] Internals: unit tables from `tensors_by_name` (assert single mapping; offset = `t->data − base`; `sscanf("blk.%d.")`; `token_embd.weight`→HEAD unit; `output_norm`/`rope_freqs`→tiny always-pinned misc); interval sort+merge per unit; runtime `sysconf(_SC_PAGESIZE)`; **inward** alignment for evict, **outward** for prefetch (align_range idiom). Verbs run only on the manager's thread (FIFO deque + cv; unit state atomic {EVICTED,QUEUED,RESIDENT} for dedupe): `evict` = madvise(DONTNEED) then Linux-only fadvise(DONTNEED) on the module's own re-opened `O_RDONLY` fd (page cache is per-inode — any fd works); `prefetch` = madvise(WILLNEED) then touch 1 byte/page (major faults land on this thread, not compute); `pin` = prefetch + flag (+ ranged `mlock` when `mlock_pins`, degrade on ENOMEM with log). Plan-B evict (if A3 said so): MAP_FIXED re-mmap + fadvise.
- [ ] Ledger solver — **two-step, head-aware** (adversarial finding B1: a one-shot `3·max(b_layer, head)` refusal term would refuse Milestone A itself):
  1. *Head-pinned config:* `R_pin = max_ram − mlock_front − resident_other − ((W+1)·b_layer_max + b_layer_max) − reserve`; feasible iff `R_pin ≥ head_bytes` → pin HEAD, then blk.0,1,… greedily (streamed remainder stays one contiguous run).
  2. *Head-streamed config* (only if 1 infeasible): window term becomes `(W+1)·b_layer_max + head_bytes`; `R_pin` = leftovers → pin blk.0,1,… ; HEAD streams as the ring's last unit, loud log (`+head_bytes/D per token`).
  Solver computes both, picks min predicted s/token among feasible ones; **refuse only if neither fits at W=1** → print the failing inequality with numbers, return NULL. Startup log: config chosen, pinned/streamed MiB, W, `predicted s/token = streamed_bytes(/round)/D`.
- [ ] `common_init_result` (:1234-1259): between model load and context creation — init residency, install `cparams.cb_eval = llama_residency_sched_eval_cb` + user_data; result holds a unique_ptr (freed before model). `--residency-selftest` runs the selftest post-context and exits PASS/FAIL (precedent: `--selftest-seams`).
- [ ] Selftest asserts: table sanity (≥1 streamed unit, no overlaps, byte totals match `ggml_nbytes` sums); touch→evict→mincore ≤5%; prefetch→mincore ≥95% + bandwidth log; simulated ring walk holds total streamed-resident ≤ (W+2)·b_layer_max at every step; pins ≥99%; logs smaps_rollup/memory.current where readable. Commit: `S1b: llama-residency module, verbs, ledger, selftest`.

### Task B3 (S2): execution hook
- [ ] In `llama-residency.cpp`: `unordered_map<const ggml_tensor*, int32_t> unit_of` built from tensor pointers (check `t->src[i]` and `src->view_src`; no string parsing at runtime). `token_embd` resolves to HEAD **only** for `GGML_OP_MUL_MAT` (logits); `GGML_OP_GET_ROWS` → no unit (embedding lookup must not gate).
- [ ] Callback: ASK returns true only on first node touching a **new** unit (else false → scheduler coalesces); POST (`on_gate_post(u)`, compute thread, lock only to push): evict every RESIDENT streamed unit outside ring window `[u, u+W]` (self-healing catch-up — covers pinned holes, ubatch boundaries, wrap), enqueue PREFETCH for `u+1…u+W` not RESIDENT/QUEUED. Graph end = HEAD gate POST → window wraps to ring start (trailing evicted, first W prefetched for next token). Prefill: identical walk per ubatch (log `prefill reads ≈ ceil(n_prompt/n_ubatch)·(S−R)` at startup); non-final ubatches without logits catch up at next graph's first gate (accepted, noted). KV-shift/defrag graphs have no blk weights → no gates, no effect. Debug hook `MUTA_CB_NOOP=1` (no-op callback force-registered) for the overhead A/B.
- [ ] Verify (macOS, functional): streamed greedy output byte-identical to non-streamed (temp 0 seed 42, 64 tokens) — catches graph-split bugs. **Note (adversarial): identity cannot prove evict-before-compute ordering** (clean MAP_SHARED pages re-fault identically); the ordering evidence is the selftest ring-walk residency bound plus per-token majflt/read-bytes staying ≈ streamed_bytes (checked in MA). Commit: `S2: cb_eval gate — sliding-window evict/prefetch`.

### Task B4 (S1c): ledger polish
- [ ] Refusal inequality print, plan/prediction table logging, explicit `--pin-budget MIB` override path (MA is unblocked by B2/B3 even if this slips). Commit: `S1c: ledger solve/refusal/prediction logging`.
- [ ] Re-export `patches/` (0001..00NN now includes streaming series). WORKLOG entries.

**Phase B gate:** container selftest PASS: `stream_env.sh cgrun 3g … llama-completion -m /models/Qwen3.5-4B… --stream-weights --max-ram-mib 2048 --residency-selftest` exits 0.

---

## Milestone A — the headline answer (checkpoint; report before Phase C)

`scripts/milestone_a.sh` runs (fixed: `-no-cnv --temp 0 --seed 42 -c 4096 -t 6 -n 64`, fixed physics prompt, fresh container per run, memwatch sidecar):
- [ ] **MA-1 observed:** `cgrun 3g` + `--max-ram-mib 2048 --stream-disk-gbps <D>`: PASS iff max(memory.current) and memory.peak < 2048 MiB throughout AND decode s/token within ±30% of the printed `(S−R)/D` (G9 preview). Tune `--stream-reserve-mib` from measured anon floor if needed (WORKLOG).
- [ ] **MA-2 enforced:** `cgrun 2048m`: PASS iff exit 0, `OOMKilled=false`, tok/s within 15% of MA-1 (kernel reclaim should find nothing to do).
- [ ] **MA-3 unmanaged A/B** (G12 preview): `cgrun 2048m` **without** `--stream-weights` (stock load under the cap → reclaim thrash): record load time, tok/s, majflt, managed/unmanaged ratio.
- [ ] **MA-4 overhead A/B:** SmolLM2 resident ± `MUTA_CB_NOOP=1` → callback cost (expect 1–3 ms/token ≈ <0.5% of streamed decode).
- [ ] Emit `bench/results.md` §5 first rows (mode/cap/peak/load-s/tok/s/predicted/measured/ratio) + POC_REPORT §streaming stub + WORKLOG. Commit: `MA: milestone-A harness + 4B@2GiB verdict`.

**Deliverable to the user at this checkpoint:** "4B streams under 2 GiB: yes/no, at X tok/s raw (predicted Y), unmanaged baseline Z tok/s" — before S3/S4 build-out proceeds.

---

## Phase C — S3 multi-tier duo (C1–C3 have no Phase-B dependency; parallelizable with B)

### Task C1 (S3.1): tier registry (pure refactor)
- [ ] `duo.cpp`: `tier_role {FRONT,EASY,MID,TOP}`, `tier_policy {MLOCK,RESIDENT,STREAMED,AUTO}` (defaults by role: front=mlock via `LLAMA_LOAD_MODE_MMAP_MLOCK`, easy=resident, mid/top=streamed), `tier_state` atomic; `duo_tier {role,prefix,file,policy,n_ctx,temp,top_p,duo_model,state,residency*}`; `duo_state.tiers` + raw ptrs front/easy/mid.
- [ ] Registry population: flags `--tier NAME=PREFIX`, `--tier-file NAME=PATH`, `--tier-ctx NAME=N`, `--tier-policy NAME=…` override **bundle-manifest auto-discovery** (`gguf_init_from_file(no_alloc=true)` on `p.bundle` → `bundle.count`, `bundle.{i}.prefix/role`; legacy role `expert`→mid). Old 2-model bundles keep working; `--front-prefix/--expert-prefix` become aliases.
- [ ] **Regression gate:** fixed-seed router/codraft/verify runs on `bundle/muta-duo-q.gguf` byte-identical to pre-refactor. Commit: `S3.1: duo tier registry + bundle-manifest auto-discovery`.

### Task C2 (S3.2): mode→tier mapping
- [ ] Router: front (mlocked SmolLM2) stays the router; `route=easy` → **easy tier** authors (was front), `route=hard` → mid. Confidence escalation easy→mid via existing carry-draft machinery: easy is hybrid/append-only, so allow the conf monitor for append-only authors when a checkpoint seq exists (checkpoint_restore + re-decode committed prefix at 0.8B prefill speed, then hand off). Easy always loads with `checkpoint_seq=true`.
- [ ] `--ttft-opener` (default on): on turn 1 the front immediately streams an opening segment (existing gen_segment, seam rule, conf monitor armed) while routing/tier-loads proceed — whichever tier continues ingests it as carry-draft. This is the G11 mechanism.
- [ ] `--codraft-tiers front,mid|easy,mid`. Commit: `S3.2: three-tier routing + conf escalation easy->mid + --ttft-opener`.

### Task C3 (S3.3): staged startup
- [ ] Main thread loads front first (mlock; 49k vocab parses fast) → prompt appears, turn 1 can start. One background loader thread (serialized loads, bounds RAM spikes) loads easy then mid, publishing `TS_READY` via atomic+cv; both 248k-vocab parses are off the TTFT path by construction. `acquire(state, role)` blocks on cv only when a mode actually needs the tier; fallbacks: easy-not-ready → front answers conf-monitored; mid-not-ready → opener streams until READY then carry-draft. No context ever decoded from two threads. Commit: `S3.3: staged startup — mlocked front first, background tier loader`.

### Task C4 (S3.4): residency wiring + switch choreography (DEPENDS Phase B)
- [ ] duo flags mirroring common: `--stream-weights --max-ram-mib --prefetch-layers --pin-budget --tier-policy --disk-gbps`. Per-tier at load: STREAMED → `llama_residency_init` (cross-terms `mlock_front_mib` [measured mlock size] / `resident_other_mib` from the registry) + `cb_eval` install; RESIDENT/MLOCK → counted into cross-terms **exactly once** (adversarial M2: D2's draft reservation adds only `ctx_draft` KV, never easy's weights again). Ledger table **itemizes per-context KV/state** (checkpoint seqs double n_ctx for easy and mid — `duo.cpp:300-304` — this must appear as its own line, not vanish into `reserve`). **Ledger solved once at startup** (policy static per session): solver evaluates easy-resident+HEAD-streamed vs easy-demoted+HEAD-pinned (per B2's two-step solver) and picks min predicted s/token; demotion is **sticky** (loud `[ledger] DEMOTE` log; explicit `--tier-policy easy=resident` refuses instead) — kills oscillation by construction. Deviation note: spec says re-solve each switch; we re-log the plan + state at each switch (inputs are static).
- [ ] `switch_to(in)`: `llama_residency_suspend(out)` (instant bulk evict; idle tier keeps KV/GDN state — weights only) → log `[ledger]` table → `llama_residency_resume_async(in)` **called at route/conf-decision time while front/easy still streams** (no barrier before first decode — pages fault correctly regardless; activation is latency optimization). Trace lines (the G8/G11 evidence): `[tier] switch easy->mid reason=conf …` / `[tier] mid ready pins=…MiB prefetch_wait_ms=… overlap_tokens=…`.
- [ ] Commit: `S3.4: residency wiring, ledger log, tier-switch choreography, sticky demote`. Re-export patches.

---

## Phase D — S4 amortizer

### Task D1 (S4.0): mechanism probe (docs only)
- [ ] Build `llama-speculative-simple`. Leg A (host, resident): for 3 perf.txt prompts (prose/math/physics) × `--spec-type draft-simple | draft-mtp | draft-simple,draft-mtp` with `-m 4B -md 0.8B --draft 8 --temp 0 --seed 42 -n 128`: PASS = no assert/crash, **greedy output byte-identical to 4B-alone baseline** (any divergence = qwen35 rollback broken = in-tree path dead), math acceptance ≥0.50. Leg B: same prompts through `llama-duo --mode verify --draft 8` on muta-duo-q. **Decision:** in-tree Path A iff leg A fully passes AND math acceptance ≥ (duo verify − 0.05); else Path B (proven). → DISCOVERY + WORKLOG. Commit: `S4.0: spec-mechanism probe verdict`.

### Task D2 (S4.1): wiring
- [ ] Flags: `--draft-tier none|easy` (implies easy policy=resident; **never silently demote the draft — refuse with "use --draft-tier none"**), `--draft-k K` (default 8 until G10; fixes round size, adaptivity off for a clean curve). **Vocab gate at activation** (hard error): `llama_vocab_n_tokens` equal AND probe-string tokenizations identical; `--draft-tier front` rejected naming the mismatch (49,152 vs 248,320) — R12 enforcement.
- [ ] Path A: construct `common_params_speculative` directly (types from probe winner, `draft.n_max=K`); easy gets a **second context** `ctx_draft` on the same `llama_model` (weights shared; extra KV/GDN state is a ledger reservation) so spec machinery never clobbers easy's answering context; accepted tokens flow through existing seam/UTF-8 discipline. Guard RS8: run `common_context_can_seq_rm`'s capability probe (it decodes 2 tokens!) **before** residency activation, or hardcode the known qwen35 answer (log deviation).
- [ ] Path B: `run_verify_turn` drafts on easy (`--draft-tier easy` selects it); under `--stream-weights` the repair span is **skipped explicitly** — adversarial B2: `repair_min=0` does NOT do this (`seg_min==0` degenerates to a ~16-token cap run of single-token streamed mid decodes ≈ 10–15 s per rejection). New branch: when streaming, on reject take the correction token from the redo batch's last logits row (already requested at `duo.cpp:981`), skip `gen_segment` entirely, hand the pen back to the draft. Plus adaptive k-growth `k=min(2k,draft_max)` after full accepts.
- [ ] Ledger interaction: draft-tier forces easy resident (already a C4 cross-term — **no double count**); adds only `ctx_draft` KV as a new itemized line: `[ledger] term easy.ctx_draft_kv=… (draft-tier)`. Commit: `S4.1: --draft-tier/--draft-k amortizer + vocab gate + ledger reservation`.

### Task D3 (S4.2): acceptance harness
- [ ] `scripts/spec_accept.py`: one process per prompt over `bench/prompts/{easy,hard,perf}.txt`, parse `--json-trace` turn lines → per-domain acceptance mean/min/max + tok/s → `bench/.runs/stream/acceptance.tsv`. Run resident (host, advisory) + streamed (container, gate-grade). Commit: `S4.2: per-domain acceptance harness`.

---

## Phase E — S5 gates & report (`scripts/stream_gates.sh` orchestrates; all in-container, serialized)

All duo runs: `--bundle bundle/muta-trio.gguf --stream-weights --max-ram-mib 2048 --prefetch-layers 2 --disk-gbps $D -q --json-trace …`.

- [ ] **G8 (cap):** per mode {router-easy, router-hard (escalates to mid), forced conf-escalation easy→mid w/ carry-draft, codraft, 10-turn perf.txt run} × {observed `cgrun 3g` — PASS iff all memory.current samples + memory.peak < 2048; enforced `cgrun 2048m` — PASS iff exit 0 + OOMKilled=false + coherent output}. Log peak per mode.
- [ ] **G9 (latency model):** enforced, forced-hard, `--draft-tier none`, `-n 64`: mid-segment decode s/token within **±30%** of the run's own printed `streamed_bytes/D`. On miss: rerun with `iostat -x 1` sidecar + `/proc/<pid>/smaps_rollup` snapshots every 2 s → WORKLOG diagnosis (wrong pages vs THP vs double-charge; R8/R9).
- [ ] **G10 (amortization, mid tier):** K=0 row = `--draft-tier none` plain streamed decode (duo clamps `draft_init` to ≥4, `duo.cpp:861` — K=0 through verify mode is impossible); K ∈ {4,8,16} × the **mechanism D1 chose** (Path A in-tree or Path B verify) with `--draft-tier easy -n 128` over perf.txt; record tok/s, acceptance, memory.peak per K; **default K = argmax tok/s subject to G8 holding**; commit the default (`S4.3`); plot via plot_bench.py extension; per-domain acceptance at chosen K via spec_accept.py.
- [ ] **G11 (TTFT):** cold start (drop_caches) inside enforced container; python wrapper measures exec→first stdout byte; `--ttft-opener` on. PASS iff < 300 ms AND trace shows `[tier]` activate/ready lines interleaved with front `[seg]` lines (prefetch concurrent with generation). **Known risk (adversarial M3):** a bundle load parses the WHOLE file's KV section — including both 248k-token vocab arrays — on the front's critical path regardless of prefix. Fallback ladder: (1) `--tier-file front=models/SmolLM2-135M-Instruct-Q4_K_M.gguf` (standalone 33-KV file; registry already supports it; bundle still ships all three); (2) shorter opener prompt; (3) report the measured floor with load/KV-parse/prefill/decode breakdown (gate documents, never fudges).
- [ ] **G12 (A/B):** enforced cap, mid tier, same prompt, `-n 32`: duo without `--stream-weights` vs with; record both tok/s + ratio, whatever it is (a managed loss = S6 trigger).
- [ ] Emit `bench/results.md` §5 table (gate / tier-mode / cap-mode / K / acceptance / tok/s / memory.peak / predicted s/tok / meas÷pred); POC_REPORT §Streaming (commit hashes, env header incl. VM RAM + D **+ the honesty caveat: `drop_caches`/`iflag=direct` act inside the linuxkit VM only — the macOS host still caches the VM disk image, so D and streamed tok/s are VM-IO-class numbers, internally consistent for G9 but not representative of a cold physical SSD; optional host `sudo purge` for one genuinely cold reference run**, one verbatim `[ledger]` table, one annotated tier-switch trace, G10 curve + chosen K, deviations list); WORKLOG per gate; final `patches/` re-export. Commits: `S5.1: stream gates harness`, `S5.2: results + report + patches`.

**S6 fallback (only if G9/G12 fail):** O_DIRECT double-buffered ring streamer — tree already has O_DIRECT plumbing (`llama_file(...,use_direct_io)`, Linux-only). Documented, not default. Do not build unless triggered.

---

## Verification summary

1. **Phase A:** probe proves evict verb uncharges `memory.current`; D measured; geometry tables committed.
2. **Phase B:** container selftest PASS (ring-walk residency bound holds); streamed greedy output byte-identical to resident (temp 0, seed 42).
3. **Milestone A:** 4B under 2 GiB observed + enforced + unmanaged A/B + overhead A/B → user checkpoint report.
4. **Phases C/D:** C1 regression gate (byte-identical old-bundle behavior); D1 probe decides mechanism; vocab gate hard-errors on SmolLM2-as-draft.
5. **Phase E:** G8–G12 recorded in bench/results.md §5 + POC_REPORT §Streaming; ledger table logged at startup and every tier switch; spec-dec default K chosen from G10; patches/ + WORKLOG current (STREAMING_PLAN "definition of done", minus deferred 27B items, each marked deferred in the report).

## Risks (merged; detection → fallback)

| # | Risk | Detection | Fallback |
|---|---|---|---|
| R-A | fadvise(DONTNEED) doesn't uncharge (order bug / linuxkit quirk) | A3 step-3 Δ≈0 | MAP_FIXED re-mmap evict (A3 validates; **must re-apply MADV_RANDOM/NOHUGEPAGE after every re-mmap** — new VMA loses them); else S6 |
| R-P | Foreign PTEs from other tiers' bundle mappings block fadvise eviction | G8-observed `memory.stat` file ≫ pinned+window despite evictions | B1's bundle-wide suppression + post-load DONTNEED sweep is the designed fix; if insufficient → per-tier files (`--tier-file` for all tiers; streaming is per-fd) |
| R-B | Evict fires pre-compute → garbage | B3 byte-identity check vs resident | POST-anchored design; gate on next layer's 2nd node if a backend POSTs late |
| R-C | Per-gate split/sync overhead | MA-4 A/B > 5 ms/token | gate every 2nd layer transition |
| R-D | WILLNEED blocks synchronously (R10) | A3 step 4 | chunk into 8 MiB pieces on bg thread |
| R-E | Prefetch thread steals decode cores | tok/s at W=0 vs W=2 resident | IO-bound by design; else nice(10) / `-t 5` |
| R-F | Page-cache charged to another cgroup → metric lies | A3 step-1 Δ < touched bytes; memory.stat file split | fresh container per run (already designed); enforced mode is ground truth |
| R-G | THP / page-size coarsening | A1 getconf + smaps FilePmdMapped | MADV_NOHUGEPAGE at map (B1); runtime sysconf everywhere |
| R-H | BLAS accidentally on | cmake-log grep in A1 | dedicated build dirs; never reuse `llama.cpp/build` for cap work |
| R-I | HEAD not pinnable at tight caps | ledger log head_pinned=false | degraded mode: HEAD streamed last (+~0.2 s/token at D=2.5), printed in plan |
| R-J | In-tree spec wrong on hybrid target | D1 leg-A divergence | Path B (duo verify, proven) |
| R-K | Background tier load steals decode threads | G11 front tok/s drop >20% during overlap | load after first segment commit; SCHED_IDLE on loader |
| R-L | Router misroutes inflate mid usage | G8 10-turn route counts (G3: ~4/20 over-escalate) | τ sweep is free post-hoc; costs speed not cap-safety — document |
| R-M | Demote oscillation | >1 DEMOTE line per session | startup-solved sticky demotion (designed out) |
| R-N | Capability probe decodes on streamed ctx at init (RS8) | 1 s startup stall in trace | probe before residency activation / hardcode qwen35 answer |
| R-O | TTFT floor > 300 ms | G11 breakdown | opener already removes routing from path; shorter opener; report floor honestly |
