# Adversarial review — `0001-muta-residency-window-b10360.patch` (2026-08-17)

**Verdict: PASS-with-notes.** No memory-safety or output-correctness defect found. Two medium
config/robustness issues, several lows. Tree at `opt/llama.cpp` verified byte-identical to the patch.

## Behavioural evidence (all under `with_lock.py`, `-t 4 --temp 0 --seed 1 -no-cnv --no-warmup`, bitcpm4-8b-tq2_0-envocab)

| run | md5 of generated text | tg tok/s | notes |
|---|---|---|---|
| MUTA_STREAM=0 (-n 48) | 93c220f4… | 21.2 | baseline |
| STREAM=1 PREFETCH=0 W=0 NO_REPACK=1 | 93c220f4… | 12.3 | evict=1536=48×32, populate_fail=0, no remap errors |
| STREAM=1 PREFETCH=1 W=2 HELPERS=2 MODE=touch | 93c220f4… | 9.8 | gate_missed 1441/1584 (prefetch never wins, as doc says) |
| … MODE=mlock | 93c220f4… | 4.9 | populate 8.6 ms/op, evict 4.9 ms/op — pathological |
| STREAM=1 PIN_MB=800 | 93c220f4… | 14.2 | pinned 783.8 MiB/13 units; `graphs=0` (cosmetic, see L2) |
| 701-tok prompt, MUTA_UBATCH=128, base vs stream(def) vs stream(pf) (-n 32) | af793f28… ×3 | — | 6 pp ubatches: graphs=37, gates=1221=37×33 |
| llama-bench `-p 128 -n 16 -r 1`, MUTA_STREAM=1 STATS=1 (code defaults) | — | pp 25.3 / tg 4.39 | populate=630 populate_fail=0 evict=627, no "remap failed" |
| `/usr/bin/time -l` -n 24: base / stream(def) / stream(code-defaults) | identical ×3 | 18.1 / 10.3 / 4.7 | **max RSS 2685 MB → 690 MB → 620 MB** |

Outputs are byte-identical in every configuration, including the multi-ubatch prompt; RSS drops ~4×.

## Why the memory-safety argument holds (checked, not assumed)
* Eviction never unmaps. Darwin uses `mmap(MAP_FIXED)` of the same fd/offset (`llama-residency-lite.cpp:167`);
  XNU's `mmap()` translates MAP_FIXED into `VM_FLAGS_OVERWRITE`, whose kernel comment guarantees the
  delete+insert is atomic under the map lock, so a concurrent reader can only soft-fault to identical bytes.
  Linux `MADV_DONTNEED` (:171) keeps the VMA. Hence a *mistimed* eviction (lagging helper, gate false
  negative, HEAD self-evict, boundary-page sharing) costs soft-faults, never a fault or wrong data.
* POST guarantee: `ggml-backend.cpp:1730-1766` computes `[j0..gate]` inclusive via
  `ggml_backend_graph_compute_async` (synchronous for CPU; nodes execute in order with a barrier per node,
  CPU has no `graph_optimize`), then `synchronize`, then POST. Single CPU backend ⇒ one split. Airtight.
* HEAD = exactly `output.weight`; in the llama/minicpm graph its only use is the lm-head `build_lora_mm`
  (`src/models/llama.cpp:240`), so evicting at its own POST is correct.
* `unit_of_node` (:275): views/permutes carry `view_src` to the root weight, and every intermediate op is
  itself a callback node, so a false negative can only delay a gate, never move it past a later unit.
* want/queued state machine (:216, helper :184-212, inline :259-272): invariant "queued ⇔ in exactly one
  queue XOR in-flight in exactly one worker" holds; the inline path pops only from a queue, so it can never
  race a helper on the same uid. Zero-output pp ubatches still contain the (0-column) lm-head node ⇒ HEAD gate
  fires every graph (stats confirm gates = 33×graphs).
* fd lifetime: `llama_model_free` → `muta_residency_release` (joins helpers) → `delete model` → `~impl` closes
  `fd_dup`. Correct order. Boundary-page sharing (verified: all 34 unit boundaries in this file share a 16 KiB
  page, incl. `output.weight|output_norm` and `token_embd|blk.0`) is benign; `unit.bytes` double-counts ~0.5 MB.

## Findings (ranked)

**M1 — built-in defaults are the measured-worst config.** `:370-379` default `W=2, HELPERS=3, PREFETCH=1,
MODE=mlock`; the design doc says the default config is `PREFETCH=0 W=0`. `MUTA_STREAM=1` alone (or
`-DMUTA_STREAM_DEFAULT=1`, or the profiler harness) gives tg 4.4–4.7 tok/s vs 10–12 with PREFETCH=0.
Fix: `env_int("MUTA_STREAM_PREFETCH", 0)`, `env_int("MUTA_STREAM_W", 0)`, default mode `touch`; print
`prefetch=` in `print_plan`.

**M2 — gate state is per-model but assumes one compute stream.** `cur_ask_unit` (:102, :491) and the window
live in the model-keyed residency; two contexts on one model decoding concurrently (this fork's
`LLAMA_CONTEXT_TYPE_MTP` sibling context, a parallel server) race on `cur_ask_unit` (UB) and thrash each
other's window (perf collapse, not a crash). Fix: `cb_eval_user_data` → per-context `{residency*, cur_ask_unit}`;
document single-stream.

**M3 — `--mlock` and streaming conflict silently.** `llama-model.cpp:1539` still wires the whole mapping;
Darwin remap then unwires it behind llama's back, Linux `DONTNEED` on VM_LOCKED returns EINVAL for every
eviction. Related: `evict()`/`populate()` return values are ignored — helper sets `u.actual = want` (:205)
regardless and there is no `n_evict_fail` counter in the STATS line (:480), so Linux failures are invisible.
Fix: return `nullptr` from `get_or_create` when `model.params.use_mlock`; add `n_evict_fail`, and leave
`actual` unchanged on failure.

**M4 — no buffer-type guard.** Classification is by address only (:390-395). A Metal/host-ptr build maps the
same mmap into GPU buffers and would be remapped under the GPU. Not this build (METAL=OFF) — add
`ggml_backend_buffer_is_host(t->buffer)`/CPU-buft check and refuse otherwise.

**L1** `blk.N` for `N ≥ hparams.n_layer()` (nextn/MTP layers) fall to MISC (:402) → pinned+populated forever.
Exclude like `token_embd`. **L2** cosmetics: `graphs=` counts only HEAD gates (0 when head pinned);
`gate_missed` == gates in PREFETCH=0 mode. **L3** `dup()` failure → `fd=-1` → every Darwin remap EBADF-spams
(no auto-disable); `fd_dup` leaks if `mmap` throws in the ctor (`llama-mmap.cpp:450` — dup after mmap).
**L4** zero-length interval (0-byte tensor) → `mmap(len=0)` EINVAL; guard `len==0`. **L5** PREFETCH=0 mode
can still mlock: a helper mid-evict of `u` when compute re-enters `u` requeues it to `q_prefetch` (:208) and
populates with the default `mlock` primitive. Skip the requeue when `!prefetch`. **L6** app-supplied
`cb_eval` silently disables streaming while `init_mappings(false)` still applies — warn. **L7** Evicting HEAD
drops `output_norm`'s shared page each token ("pinned" is one page short; harmless). **L8** Linux cgroup
`memory.current` still counts page cache (reclaimable) — RSS is bounded, cgroup charge is not.
