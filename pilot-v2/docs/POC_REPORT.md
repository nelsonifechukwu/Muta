# DUO PoC Report — Two Models, One GGUF, One Process

Date: 2026-08-09. Host: Apple M2 Pro (6P+4E), macOS (Darwin 25.5), CPU-only build (Metal off, Accelerate BLAS on). NOT the deployment target (x86-64 Ubuntu, 8 GB); all numbers are architecture-comparative, to be re-measured on target hardware.

## Commits

- llama.cpp base: `7ba604f1cb61cd14898138e9abc0b4ff2601f180` (upstream master, 2026-08-09)
- Branch `bundle-poc`, 9 commits, exported to `patches/` (9 patch files; L-series loader patch + T-series duo tool)
- Models: `SmolLM2-135M-Instruct-Q4_K_M.gguf` (front), `Qwen3.5-4B-Q4_K_M.gguf` (expert), both untouched

## What was proven

1. **One file, two models**: `scripts/pack_bundle.py` packs both GGUFs into `bundle/muta-duo.gguf` (2.85 GB = sources + 2,912 bytes). Identity repack of a single model is bit-for-bit identical to its source (same sha256).
2. **One process, prefix loading**: a 6-commit llama.cpp patch adds `bundle_prefix` to `llama_model_params`; `--bundle-prefix m0.`/`m1.` loads either sub-model from the same file with byte-identical greedy output vs the stock single-model files, and perf parity within +/-5%.
3. **Router escalation**: the 135M front classifies via two verdict-token logits (deterministic, no sampling); hard questions go to the 4B expert; easy answers stream from the front with a mean-logprob confidence monitor that escalates mid-answer (with optional `--carry-draft` draft continuation).
4. **Interleaved co-drafting**: both models alternately author segments of one answer over a shared text transcript with zero rollback of the expert's recurrent state, exact tokenization seams (self-tested), and multi-turn stability.

## Gate results

| Gate | Result |
|---|---|
| G1 identity repack | PASS — repacked file bit-identical to source (sha256 equal) |
| G2a byte verification | PASS — all 79 KVs + 698 tensors sha256-equal under prefixes; manifest correct |
| G2b bundle identity | PASS — front and expert, raw and chat modes, byte-identical vs stock |
| G2c perf parity | PASS — same-binary: front tg -1.6%, expert pp -4.1%, expert tg -3.6%; front pp noise-dominated but favorable |
| G3 router quality | PASS — tau=0: 87.5% (easy 16/20, hard 19/20); sweep: -2:70%, -1:75%, 0:87.5%, 1:80%, 2:57.5% |
| G4 seam self-test | PASS — 5 turns x 390-1024 tokens; front strictly canonical on all turns; expert 4/5 canonical + 1 benign self-segment case (identical text, equal counts) |
| G5 co-draft liveness | PASS — 10 mixed turns, 20/20 selftests OK, zero resyncs, no crash/stall/runaway, steady 27-41 tok/s |
| G6 perf matrix | see table below |
| G7 peak RSS | see table below (all rows < 6.5 GB budget) |

## G6/G7 — performance matrix

Full tables in `bench/results.md`. Headlines:

| row | expert share f | tok/s | peak RSS |
|---|---|---|---|
| front alone | 0.00 | 441-495 | 272 MiB |
| expert alone | 1.00 | 26.6-29.5 | 5.31 GiB |
| router-easy | 0.00 | 46.8 (8-token answer incl. routing) | 5.73 GiB |
| router-hard | 1.00 | 26.8 | 5.74 GiB |
| router-escalated | mixed | 28.9 | 5.72 GiB |
| codraft f=0.25 | 0.25 | **48.6** | 5.71 GiB |
| codraft f=0.45 | 0.45 | 36.1 | 5.32 GiB |
| codraft f=0.80 | 0.80 | 29.6 | 5.71 GiB |

G7: every row < 6.5 GB. The duo process peaks only ~0.4 GiB above the expert-ALONE baseline — the double-mmap of one bundle file shares physical pages via the OS page cache, and the front adds ~100 MB. The two-mmap-one-file claim is confirmed empirically.

## Predicted vs measured

`T ~= N * (f/r_e + (1-f)/r_f) + t_ingest` with r_f ~= 400, r_e ~= 30 tok/s (in-duo rates): predictions land within +2%, +3%, +10% of measured wall time for f = 0.45, 0.25, 0.80 respectively, and +3% for router-hard (details in `bench/results.md`). The f=0.80 gap is logprob/sampler overhead on the 248k-vocab expert. The measured deltas track the model, as the plan required.

## Annotated traces

### 1. Router escalation (hard route)

```
[seg 0] author=expert tokens=302 ms=10022.8 tok/s=30.1 mean_lp=-0.21 cut=eos
[turn] route=hard s=1.064 author=expert tokens=302 ms=11254.2 tok/s=26.8
```
"Solve 3x + 5 = 20 and explain each step." scores s = z_B - z_A = +1.06 >= tau=0 on the front's verdict logits -> the expert answers directly (a correct, step-by-step solution). Routing itself is a ~150 ms prefill on the 135M with no sampling.

### 2. Confidence trigger + carry-draft

```
[seg 0] author=front tokens=121 ms=303.1 tok/s=399.2 mean_lp=-0.57 cut=conf
[seg 1] author=expert tokens=131 ms=4354.9 tok/s=30.1 mean_lp=-0.25 cut=eos
[turn] route=easy s=1.211 author=front+expert tokens=252 ms=7199.3 tok/s=35.0 trigger=conf
```
Forced-easy routing of a multi-step question: the front streams 121 tokens at ~400 tok/s until its 16-token mean logprob drops below the threshold; it commits to the last sentence boundary, rewinds its tail, and the expert CONTINUES the draft, finishing in 131 tokens. The identical run without `--carry-draft` had the expert restart fresh and spend 903 tokens: carrying the draft cut expert work by ~7x in this instance.

### 3. Co-draft turn

```
[seg 6] author=front  tokens=27 ms=76.1  tok/s=354.8 mean_lp=-0.71 cut=boundary
[seg 7] author=expert tokens=36 ms=1179.3 tok/s=30.5 mean_lp=-0.23 cut=boundary
[seg 8] author=front  tokens=38 ms=112.1 tok/s=338.8 mean_lp=-0.61 cut=eos
[seg 9] author=expert tokens=0  ms=0.2 tok/s=0.0 mean_lp=0.00 cut=eos
[turn] mode=codraft segs=10 tokens=346 expert_share=0.45 ms=8287.4 tok/s=41.8
```
Alternating authorship over one transcript. Segments cut at sentence boundaries before whitespace (the seam rule), the front's EOS at seg 8 is treated as a handoff under `--closer expert`, and the expert immediately agrees the answer is complete (seg 9: EOS at a boundary ends the turn). Effective throughput 41.8 tok/s vs 26.6 for the expert alone. Qualitatively, the front opened the answer by misnaming the law ("also known as Newton's third law") and the expert's next segment restated it correctly - the correct-course dynamic the asymmetric system prompts ask for.

## Deviations from the plan (full list in docs/WORKLOG.md)

1. Host toolchain: three macOS-specific build fixes (stale CLT libc++ shadow dir -> `-nostdinc++ -isystem SDK`, Rosetta cmake `-mcpu=native` probe misfire -> `GGML_NATIVE=OFF` + explicit `-march`, x86-64 Homebrew OpenSSL -> `LLAMA_OPENSSL=OFF`).
2. This tree's `llama-cli` is a full-screen UI that busy-spins on EOF stdin; all scripted runs use `llama-completion` (built additionally).
3. Speculative reference code lives in `examples/`, gguf scripts under `gguf-py/gguf/scripts/`, RSS via `/usr/bin/time -l` (macOS).
4. Verdict tokens are bare `A`=49/`B`=50 (canonical after `assistant\n`), not the D5 space-prefixed pair.
5. Upstream bug found+fixed on the branch: `create_tensor` named model tensors from the on-file name; with prefix stripping this made `load_all_data` silently skip all weights (garbage output). One-line fix, no stock behavior change.
6. Expert prompt view uses manual prefix-stable ChatML (the jinja template drops past think blocks, forcing O(history) full re-syncs each turn — fixed to zero resyncs).
7. T16 overlap: evaluated and deferred. On this host the front decodes a segment in ~0.1 s while the expert's catch-up prefill costs ~0.4 s; overlap can hide at most the smaller of the two, bounding the gain at ~3-5% end to end, not worth the threading risk for the PoC. On the slower x86 target front the ratio improves and it is the first next step.

## Known limits / next steps

- **Overlap decode+ingest** (T16): implement `--overlap` with a background expert-ingest thread once on target hardware, where front-decode time is a larger share.
- **HTTP serving**: llama-server integration for the bundle (two contexts behind one endpoint).
- **Batch/classroom mode**: several front contexts sharing one expert.
- **Bundle mmap sharing**: two mappings of one file already share page cache; a single shared mapping across both models is a further RSS refinement.
- **Grammar-forced tool tag**: the router's verdict read generalizes to grammar-constrained tool-call detection.
- **RSS realism**: on this host, Accelerate BLAS dequantizes large matmul operands to F32 (~2.5 GB transient for the 248k-vocab output projection), inflating expert RSS; the target build (no Accelerate) will not show this. Re-measure G7 on target.
- **Expert self-segment tokenization**: sampled segments occasionally deviate from canonical tokenization (1 case in 15 turns of testing; text identical). Harmless by construction here, but a from-scratch re-sync would canonicalize if ever needed.

## Streaming (Milestone A)

**Verdict: yes.** Qwen3.5-4B (2614.0 MiB Q4_K_M) stream-decodes under a 2 GiB cgroup cap —
observed (`cgrun 3g`, software budget only) at **2.44 tok/s**, and re-confirmed under a real
kernel-*enforced* 2048m hard cap at **2.26 tok/s** (exit 0, `OOMKilled=false`, within 15% of
the observed number). `memory.peak` stayed under 2048 MiB in both cases, with ~400 MiB of
headroom to spare. A first-ever full-512-token-ubatch prefill run (MA-1b) held the cap too and
closed the one open concern carried from Phase B — `--stream-reserve-mib 640` still has
282.5 MiB of slack under real compute buffers, not just the earlier short-prompt runs. The
unmanaged baseline is dramatically worse under the same hard cap: a kernel-fair
(`--no-repack`) stock load survives only by thrashing the page cache — **3.83x slower**
(0.59 tok/s), 975k major faults, ~168 GiB re-read over one 64-token answer — and the naive
default (repack left on) is outright **OOMKilled**, because it tries to hold the model twice
(a 2603.5 MiB mmap plus a separate 2599.83 MiB repacked copy) against a 2048 MiB cap. The
residency manager is not a marginal win here; it is the difference between decoding at all
and reclaim-thrashing or dying.

| arm | cap-mode | cap MiB | memory.peak MiB | decode tok/s | verdict |
|---|---|---|---|---|---|
| MA-1 observed | observed (3g) | 3072 | 1640.7 | 2.44 | PASS |
| MA-1b observed, full ubatch | observed (3g) | 3072 | 1688.1 | -- (prefill 14.72 s) | PASS |
| MA-2 enforced | enforced (2048m) | 2048 | 1641.5 | 2.26 | PASS |
| MA-3 unmanaged, kernel-fair | enforced (2048m) | 2048 | 2048.0 (= cap) | 0.59 | ran, thrashed |
| MA-3 unmanaged, naive-default | enforced (2048m) | 2048 | 2048.0 (= cap) | -- | OOMKilled |

Full run matrix, ledger blocks verbatim, the reclaim-thrash and double-buffer evidence, the
`--no-repack` accuracy-reference rationale, and the environment/caveats header are in
`bench/results.md` §5.

### Multi-tier (Phase C): the whole trio under one enforced cap

The full three-tier system — mlocked SmolLM2-135M front, resident Qwen3.5-0.8B easy,
streamed Qwen3.5-4B mid, all loaded by prefix from one `muta-trio.gguf` — completes a real
confidence-triggered easy→mid escalation under a kernel-enforced 2048 MiB cgroup cap:
exit 0, OOMKilled=false, `memory.peak` **1755.2 MiB** (292.8 MiB headroom). The same trio
without `--stream-weights` is OOM-killed at 3 GiB. Configuration of record:
`--ctx-expert 4096 --tier-ctx easy=4096 --ubatch 128` — the biggest Phase C discovery is
that the per-context compute buffer (`n_vocab × n_ubatch` f32; 505 MiB at ubatch 512 for
one 248k-vocab tier) had to join the residency ledger, and at duo's defaults the ledger
correctly *refuses* rather than OOMs. Staged startup plus the `--ttft-opener` cuts first
token from **11,247 ms to 431 ms** (26×, macOS warm-cache). Mechanics (occupancy
serialization, sticky demote, the ledger of record) and the cap-run table are in
`bench/results.md` §5.

### Wrap-up status (2026-08-14) — what is proven, what is open

Executed: Phases A (discovery/probes/bundle), B (residency manager + cb_eval scheduler),
Milestone A, and C (multi-tier duo integration), through llama.cpp branch `streaming` @
`7593921` = `patches/0032`. **Descoped at wrap-up, not attempted:** Phase D (spec-decode
amortizer, S4) and the formal Phase E gate harness (`stream_gates.sh`, G-gate matrix,
default K). Gate-by-gate: G9 and G12 are answered in substance (meas÷pred 0.834 single-
model / ~10% trio; 3.83× managed-vs-unmanaged, OOM-kill vs completion at trio level);
G8 is answered in substance in both halves: the cap half (1755.2 MiB enforced) and — after
the carried C5 defect was diagnosed on 2026-08-14 — the answer-quality half. C5 turned out
to be the aarch64 repacked Q4_K kernels breaking the SmolLM2-135M forward pass (the same
run flips garbage→coherent on `--no-repack` alone; route scores follow the kernels,
+2.35 → −3.32 on "Say hello.", macOS reference −3.16); with the validated route-around
`--tier-policy front=streamed` (streamed loads force repack off), default-τ routing
produces coherent, correctly-routed answers under the enforced 2048m cap (peaks 1763.2 /
≈954 MiB), at the cost of TTFT rising to ~1.1–1.2 s until the proper per-tier
`use_extra_bufts` plumbing or an upstream kernel fix lands. G10 was never run;
G11's mechanism is proven but its formal cold-start <300 ms measurement was never taken.
Everything measured here is aarch64-Linux-on-Apple-Silicon — architecture-comparative,
to be re-measured on the x86-64 ADTC target. The dev worktree is gone; the surviving
`muta-stream` image + `muta-build`/`muta-models` volumes were re-verified on 2026-08-14
(streamed 4B, enforced 2048m: 1638.7 MiB peak, 2.23 tok/s — MA-2 within noise), and the
engine tree is reconstructable from `patches/0001–0032`.
