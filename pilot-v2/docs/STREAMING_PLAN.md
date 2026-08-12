# Phase 5 — Weight Streaming under a RAM Cap (MAX_RAM, default 2 GB)

Extends DUO_POC_PLAN.md (Phases 0–4 assumed green: bundle loads, `llama-duo` router + co-draft work). Same ground rules: discovery beats this document; deviations go to `docs/WORKLOG.md`; one commit per task; gates close phases.

**Objective.** No model's weights are ever fully resident. Weight pages enter RAM only when computed on, are evicted after use, and total charged memory stays under `--max-ram-mib` (default 2048), enforced and verified by cgroup v2. Four tiers:

| tier | file | role | Q4_K_M size (verify in S0) |
|---|---|---|---|
| front | SmolLM2-135M-Instruct | TTFT / tok-s | ~0.10 GB |
| easy | Qwen3.5-0.8B | easy tasks | ~0.55 GB |
| mid | Qwen3.5-4B | harder | ~2.7 GB |
| top | Qwen3.5-27B | hardest | ~16.8 GB |

**Definition of MAX_RAM.** The cgroup charge (anon + mapped file pages + page cache attributed to the scope) — not just RSS. Gate metric: `memory.current` of the scope. Everything below is designed to that number.

**Core design (normative).** llama.cpp with `use_mmap` already loads weight pages lazily on first touch (compute reads the mapping directly). Streaming = add three verbs on page-aligned ranges:
- `evict(range)` = `madvise(addr,len,MADV_DONTNEED)` **and** `posix_fadvise(fd,off,len,POSIX_FADV_DONTNEED)` (drop both the mapping's pages and the page-cache copy — addresses for the first, file offsets for the second: the manager stores both per range).
- `prefetch(range)` = `madvise(MADV_WILLNEED)` (async readahead), issued from a background thread.
- `pin(range)` = prefetch once, never evict; `mlock` only for the front model.
Enforcement backstop: always run under `systemd-run --user --scope -p MemoryMax=<cap>`; the manager's job is to stay below the cap proactively so kernel reclaim never chooses pages for us.

**Two independent knobs (do not conflate).** A sliding prefetch window does NOT reduce bytes read per token — every streamed layer is evicted before its next use, so each decode step re-reads the whole streamed region. (1) The **pinned set** (R bytes, never evicted) is what reduces per-token disk to `(S−R)/D`; every pinned byte saves equally, so choose pins to keep the streamed remainder **contiguous** (sequential reads reach full disk bandwidth): pin output head + first layers, stream the middle. (2) The **window W** (layers prefetched ahead) exists only to overlap disk with compute and to bound instantaneous residency at `W·b_layer`. Token-embedding rows fault per token (negligible) — exclude from the ledger's hot set.

**Ledger (startup + every tier switch, logged as a table):**
`MAX_RAM ≥ mlock(front) + resident(easy) + R_pin(active) + W·b_layer(active) + KV/GDN-state + compute buffers + 128 MiB slack`
Solve `R_pin` from the leftovers; refuse to start a tier only if `W=1` layer + overhead exceeds the cap (print the inequality with numbers).

---

## Tasks

**S0 — Discovery.**
1. Disk bandwidth: `dd if=models/Qwen3.5-27B-Q4_K_M.gguf of=/dev/null bs=1M iflag=direct status=progress` (record GB/s; also non-direct run for cached ceiling). Record NVMe vs SATA class in DISCOVERY.md — every latency prediction scales with this number.
2. Ground truth per model via `gguf-dump --no-tensors`: exact `block_count`, arch strings, sizes; compute `b_layer = size/block_count` per tier. (Reported for the 27B dense hybrid sibling: 64 layers ⇒ ~260 MB/layer at Q4_K_M — verify from HIS file, do not assume.)
3. Tree audit: `llama_mmap` flags (MAP_PRIVATE?, existing `prefetch` arg, `unmap_fragment`), availability of the eval callback (`cb_eval` / `ggml_backend_sched_set_eval_callback`; the imatrix tool is the in-tree usage reference), cgroup v2 present (`systemd-run` smoke test).
4. Packer: generalize to N models (`bundle.count = 4`) OR keep 27B as a separate file behind `--model-file` per tier — streaming is per-fd and works either way; bundling all four (~20 GB file) is allowed. Verify per-model tensor payloads are contiguous in file order (the packer writes them grouped; assert, don't assume).
5. Tokenizer identity gate for S4: assert 0.8B/4B/27B produce identical token ids on a probe corpus (family-shared vocab); SmolLM2 is expected to differ (stays text-level co-draft only).

**S1 — Residency manager** (`llama.cpp/common/` or `src/`, one module).
At model load, build per-layer range tables: for each layer, merge its tensors' `[page-aligned addr, len]` (tensor→`data` points into the mapping) plus the matching file offsets (from GGUF tensor offsets + data-section base). Output head = final pseudo-layer; embeddings excluded. Implement `pin/evict/prefetch`, the ledger solver, flags `--max-ram-mib`, `--stream-weights`, `--prefetch-layers W` (default 2), `--pin-budget auto|MiB`. Startup logs the residency plan (per tier: pinned MB, streamed MB, W, predicted s/token at measured D).

**S2 — Execution hook.**
Register the eval callback; parse `blk.N.` from node names; on layer transition into N: `evict(N−1)` if streamed, `prefetch(N+1..N+W)`. At graph end: evict trailing streamed layers, `prefetch(first W)` for the next step. Zero graph-structure changes. Syscall cost per layer is µs-scale — ignore.

**S3 — Multi-tier policy.**
Front: mlock at startup, never streamed (TTFT guarantee). Easy: resident while ledger allows, else auto-demote to streamed (log it). On tier switch: bulk-evict outgoing tier's streamed+pinned ranges (instant), install incoming tier's pin set + first-W prefetch **in the background while the front/easy tier is still streaming text** — the duo trace must show prefetch overlapping generation (this is the TTFT hack under the cap). Idle tiers keep KV/GDN state (small); weights fully evicted.

**S4 — In-family speculative decoding (the decode amortizer).**
Wire the tree's draft/verify path into `llama-duo`: `--draft-tier easy` for mid/top generations, `--draft-k K` (default 8). Same-vocab gate from S0.5 must pass. Per accepted token: `t ≈ (K·t_draft + t_verify)/(a·K+1)`, with `t_verify ≈ (S−R)/D` (one batched pass reads the streamed region once for all K). Measure acceptance `a` per prompt domain on `bench/prompts/`. SmolLM2 must NOT be wired as a llama.cpp draft model for any Qwen (different vocab — enforced by the gate).

**S5 — Gates.**
- **G8 (cap):** `memory.current` < MAX_RAM throughout router, co-draft, escalation to mid and top, 10-turn runs. Log peak per mode.
- **G9 (latency model):** measured streamed decode s/token within ±30% of `(S−R)/D` per tier; large misses → wrong pages being read; debug with `/proc/<pid>/smaps_rollup` + `iostat -x 1`.
- **G10 (amortization):** top-tier tok/s at K ∈ {0,4,8,16}; report `a` and the curve; pick default K.
- **G11 (TTFT):** first front token < 300 ms from cold start under the cap; trace shows tier prefetch concurrent with front segments.
- **G12 (A/B):** cgroup-only (no manager) vs managed, same cap, mid tier: managed should win decisively on decode tok/s (thrash avoidance is the whole point) — record actual ratio, whatever it is.
- Results table → `bench/results.md` §5; report → POC_REPORT.md §streaming.

**S6 — Fallback (only if G9/G12 fail): explicit streamer.**
O_DIRECT double-buffered `pread` into a ring of W layer-sized arenas; rebind each layer's tensor `data` pointers to its ring slot in the callback's ask-phase before the layer executes. Fully deterministic, bypasses page cache; more code and pointer discipline — documented, not default.

## Risks & fallbacks

| # | Risk | Detection | Fallback |
|---|---|---|---|
| R8 | madvise/page-cache semantics differ from expectation (MAP_PRIVATE nuances) | G9 misses, smaps shows stale residency | pair with fadvise (already in design); else S6 |
| R9 | Transparent hugepages coarsen eviction | smaps AnonHugePages/FileHuge > 0 on mapping | `MADV_NOHUGEPAGE` on the mapping at load |
| R10 | `MADV_WILLNEED` behaves synchronously | prefetch stalls in trace | issue from dedicated thread (already normative) |
| R11 | cb_eval unavailable/renamed | S0.3 | hook per-ubatch in the decode path: prefetch schedule derived from static layer order |
| R12 | 0.8B vocab ≠ 4B/27B | S0.5 gate | disable --draft-tier; co-draft only; note in report |
| R13 | Disk is SATA-class | S0.1 | all predictions rescale by D; top tier becomes prefill/verify-only by policy (document) |

## Definition of done
- [ ] S0 numbers in DISCOVERY.md (D, sizes, b_layer, vocab gate)
- [ ] G8–G12 recorded; ledger table logged at startup and on every tier switch
- [ ] Spec-dec K default chosen from G10; patches/ updated; WORKLOG current
