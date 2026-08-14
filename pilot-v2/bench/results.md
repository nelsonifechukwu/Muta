# G6/G7 — DUO perf matrix

Host: Apple M2 Pro, CPU-only (Metal off, Accelerate BLAS on), 6 threads, llama.cpp `7ba604f` + `bundle-poc`. Sequential mode (no overlap; see POC_REPORT known-limits). Answer prompts: easy = capital question, hard = linear equation, codraft/escalation = "Explain Newton's second law with an example." Peak RSS via `/usr/bin/time -l`. Reproduce with `bash scripts/bench_duo.sh`.

## Matrix

| row | tokens | expert share f | end-to-end tok/s | ingest ms (front/expert) | wall per answer | peak RSS |
|---|---|---|---|---|---|---|
| front alone (baseline) | tg128 | 0.00 | 441-495 | - | - | 272 MiB |
| expert alone (baseline) | tg128 | 1.00 | 26.6-29.5 | - | - | 5.31 GiB |
| router-easy | 8 | 0.00 | 46.8 (incl. 150 ms routing) | - | 0.17 s | 5.73 GiB |
| router-hard | 302 | 1.00 | 26.8 | - | 11.3 s | 5.74 GiB |
| router-escalated (carry) | 636 | mixed | 28.9 | - | 22.0 s | 5.72 GiB |
| codraft f=0.25 | 511 | 0.25 | **48.6** | 342 / 4615 | 10.5 s | 5.71 GiB |
| codraft f=0.45 | 346 | 0.45 | 36.1 | 478 / 3216 | 9.6 s | 5.32 GiB |
| codraft f=0.80 | 886 | 0.80 | 29.6 | 623 / 2505 | 29.9 s | 5.71 GiB |

All rows well under the 6.5 GB G7 budget. The duo process (BOTH models + BOTH contexts + double-mmapped bundle) peaks only ~0.4 GiB above the expert-ALONE baseline: the OS page cache shares the physical pages of the single bundle file across both mappings, and the 135M front adds ~100 MB weights + small KV. This is the two-mmap-one-file claim confirmed empirically.

## Predicted vs measured (sequential model)

`T ~= N * (f/r_e + (1-f)/r_f) + t_ingest_front + t_ingest_expert`, with r_f ~= 400 tok/s and r_e ~= 30 tok/s measured in-duo:

| row | predicted | measured | error |
|---|---|---|---|
| codraft f=0.25 | 10.2 s (48.7 tok/s) | 10.5 s (48.6 tok/s) | +3% |
| codraft f=0.45 | 9.4 s | 9.6 s | +2% |
| codraft f=0.80 | 27.2 s | 29.9 s | +10% |
| router-hard | ~11 s | 11.3 s | +3% |

The model tracks measurements closely; the f=0.80 gap is sampler + logprob overhead on the 248k-vocab expert at high expert share. With overlap (deferred T16), the `t_ingest_expert` term would partially hide under front decode; on this host that term is only 3-4.6 s of which at most the front-decode time (~1 s) could be hidden - the quantitative reason overlap was deferred.

## Optimization session results (branch duo-verify)

Mixed 6-prompt set (2 easy / 2 medium / 2 hard), fresh process per prompt, seed 42, serialized runs:

| config | per-prompt tok/s (hello, capital, water, newton, solve, car) | avg | max | accuracy anchor |
|---|---|---|---|---|
| **router (default)** | 18.1, 46.5, 335.4, 28.2, 28.5, 28.0 | **80.8** | **335** | expert on hard; monitored front on easy |
| codraft f~=0.25 | 23.5, 25.6, 45.2, 51.9, 52.6, 50.3 | 41.5 | 52.6 | none for front-authored 75-82% |
| verify | 26.2, 25.3, 25.4, 23.5, 25.2, 23.9 | 24.9 | 26.2 | EVERY token expert-authored or expert-approved |
| expert-alone | 13.0, 27.5, 23.0, 21.7, 25.2, 26.6 | 22.8 | 27.5 | expert |

Verify-mode findings (fixed prompts, one variable at a time):
- Draft acceptance on this SmolLM2-135M/Qwen3.5-4B pair is ~0.32-0.42 on prose, 0.54 on equation math, and INSENSITIVE to the acceptance threshold (tau -5/-3/-2 identical) - front/expert disagreement is bimodal. Greedy drafting does not help (content divergence, not sampling noise).
- Break-even acceptance for verify vs plain expert decode is ~0.55 (accepted tokens cost ~12 ms vs 33 ms, failed rounds burn draft+verify+redo overhead), hence `--hard-mode` defaults to expert on this pair. Verify still beats expert-alone on average (+9%) because cheap drafts accelerate agreeable spans and short answers.
- The checkpoint mechanism itself (seq 1 cp/rm over the hybrid's Gated-DeltaNet state) is deterministic and exact across 40+ rollback rounds per turn; seam selftests pass strictly for both models.
- The pair is the bottleneck, not the mechanism: a front from the same family (e.g. Qwen 0.5B) should push acceptance past break-even; on the x86 target the front:expert speed ratio is also more favorable to drafting.

## Same-family front experiment (branch duo-qwen-front, bundle/muta-duo-q.gguf)

Front swapped to Qwen3.5-0.8B-MTP Q4_K_M (unsloth GGUF, sha256 ac7c9d7a...): same qwen35 hybrid arch, SAME 248k tokenizer as the expert, MTP head present (nextn_predict_layers=1, unused so far). Baselines: pp512 574 tok/s, tg128 117.7 tok/s. Front is now append-only too (Gated-DeltaNet) - drafts and routing run on a checkpoint sequence.

Acceptance (the number the pair swap was for), SmolLM2 -> Qwen0.8B at temp-front 0:

| prompt | SmolLM2 acc | Qwen0.8B acc | verify tok/s | expert-alone tok/s |
|---|---|---|---|---|
| solve 3x+5=20 | 0.32 | **0.75** (0.80 at draft 24/32) | **26.9** | 25.4 |
| water cycle | 0.41 | 0.36 greedy / 0.48 sampled | 20.2 | 27.4 |
| capital of Nigeria | ~0.5 | 0.57 | 23.9 | 26.4 |

Read: the same-family draft transforms acceptance on structured/mathy content (0.32 -> 0.75-0.80) and verify now BEATS plain expert decode there - the first configuration where drafting wins outright. On open prose the 0.8B's greedy style diverges (temp 0 hurts there; sampled drafts do better) and verify still trails expert-alone. Net: parity on average, wins on math/structured.

Remaining structural bottlenecks, in order of leverage: (1) the front drafts at only 117 tok/s (8.5 ms/token) - its unused MTP head predicts an extra token per forward pass and would roughly halve draft cost; (2) repairs still hand 50-70% of tokens to 33 ms expert decode - a domain-aware dispatch (verify for math/structured, expert for prose) captures the wins without the losses; (3) overlap (T16) hides expert catch-up under front decode. Bonus finding: the 0.8B is a better ROUTER than SmolLM2 (it classifies "describe the water cycle" as hard, s=+1.15, where SmolLM2 called it easy at s=-1.71).

## Reading the tradeoff

Expert share f is the quality/speed knob (set via `--seg-min/-max` and `--seg-min-expert/-max-expert`): f=0.25 runs 1.8x faster than the expert alone, f=0.45 1.4x, f=0.80 1.1x. Routing picks f=0 (front) or f=1 (expert) per question at 87.5% accuracy (tau=0, see POC_REPORT G3), and the confidence monitor turns f=0 answers into mixed ones only when the front is actually struggling.

## 5. Weight streaming under MAX_RAM (Milestone A)

The headline question for the streaming pilot: can Qwen3.5-4B (2,740,937,888 B = 2614.0 MiB
Q4_K_M) stream-decode under a 2 GiB cgroup cap, and at what tok/s? Reproduce with
`scripts/milestone_a.sh {ma1,ma1b,ma2,ma3,all,table}`; raw logs and per-arm `.env` summaries
land in `bench/.artifacts/milestone_a/` (gitignored).

**Environment.** Container `muta-stream` (`scripts/Dockerfile.streaming`, `ubuntu:22.04`),
llama.cpp branch `streaming` @ `84c4f11`, `GGML_BLAS=OFF GGML_NATIVE=OFF
-DGGML_CPU_ARM_ARCH=armv8.5-a+dotprod+i8mm+fp16`. Docker Desktop's native aarch64 linuxkit VM,
cgroup v2, **7.653 GiB VM RAM** (7836 MiB, confirmed in every run's own
`common_params_fit_impl: ... vs. 7836 MiB of total host memory` line — matches
`docs/STREAMING_IMPL_PLAN.md`'s environment section). Enforcement/metric via
`scripts/stream_env.sh cgrun CAP` (`--memory=CAP --memory-swap=CAP --cgroupns=private`,
`/sys/fs/cgroup/memory.{peak,stat}`). `--stream-disk-gbps 2.977` (`D`) is A1's measured
**upper bound, not a guaranteed disk rate**: `scripts/stream_env.sh drop_caches` (run before
every cap-relevant measurement below) clears the linuxkit VM's own page cache, not the host
macOS cache behind the `muta-models` Docker volume, so post-drop reads can still ride host
caching; this is also an aarch64 Docker Desktop VM, not the x86-64 ADTC target — every number
below is architecture-comparative, to be re-measured on target hardware (the same caveat
`docs/POC_REPORT.md` already carries for the DUO numbers). Fixed params on every run:
`-no-cnv --temp 0 --seed 42 -c 4096 -t 6`, standard prompt "Explain the photoelectric effect
in three sentences.", fresh container per run, serialized (nothing else heavy on the host
during measurement).

### Results table

| arm | cap-mode | cap MiB | memory.peak MiB | load s | prefill s [1b] | decode tok/s | predicted s/tok | meas÷pred | verdict |
|---|---|---|---|---|---|---|---|---|---|
| MA-1 observed | observed (3g) | 3072 | 1640.7 | 2.52 | -- | 2.44 (410.33 ms/tok) | 0.531 | 0.773 | **PASS** |
| MA-1b observed, full ubatch | observed (3g) | 3072 | 1688.1 | 14.72 | 14.716 | -- | -- (compute-bound, see below) | -- | **PASS** |
| MA-2 enforced | enforced (2048m) | 2048 | 1641.5 | 2.39 | -- | 2.26 (442.95 ms/tok) | 0.531 | 0.834 | **PASS** |
| MA-3 unmanaged, kernel-fair (`--no-repack`, no `--stream-weights`) | enforced (2048m) | 2048 | **2048.0 (= cap)** | 5.04 | -- | 0.59 (1701.11 ms/tok) | n/a (unmanaged) | n/a | ran to completion, reclaim-thrashed |
| MA-3 unmanaged, naive-default (no flags beyond `-c 4096`) | enforced (2048m) | 2048 | **2048.0 (= cap)** | -- (never logged) | -- | -- (never logged) | n/a | n/a | **OOMKilled**, exit 137 |

Managed/unmanaged ratio (MA-2 vs MA-3 kernel-fair, both at the same enforced 2048m cap):
**2.26 / 0.59 = 3.83x** — the residency manager is 3.83x faster than stock loading fighting
the same hard cap through page-cache reclaim.

### MA-1 — observed (`cgrun 3g`, `--stream-weights --max-ram-mib 2048 --stream-disk-gbps
2.977 -n 64`, memwatch sidecar)

`memory.peak` **1,720,438,784 B = 1640.7 MiB**; memwatch's own max sampled `memory.current`
**1,704,964,096 B = 1626.0 MiB** — both under the 2048 MiB budget throughout (**PASS** on the
cap clause). Decode **410.33 ms/token = 2.44 tok/s**; the ledger's own predicted s/token is
**0.531**, so measured/predicted = 0.773 — inside the ±30% band, toward the fast edge (22.7 of
the 30 points used; **PASS** on the accuracy clause). Running *faster* than predicted here is
expected, not incidental: the Environment header above records `D = 2.977 GB/s` as A1's
measured **upper bound**, not a floor, so a run that rides host-level caching underneath the
`drop_caches`-cleared VM cache should land at or above the predicted rate, exactly the
direction this ratio leans. Load 2516.82 ms, prefill 251.65 ms/token (10-token standard prompt).

Ledger block, verbatim:

```
residency: model = /models/Qwen3.5-4B-Q4_K_M.gguf
residency: mapping 2614.0 MiB, page 4096 B, 34 units = 32 blk + head (tied) + misc (0.010 MiB)
residency: b_layer min/avg/max = 57.7 / 65.8 / 70.3 MiB, head = 497.3 MiB
residency: ledger: max_ram 2048.0 - mlock_front 0.0 - resident_other 0.0 - window 281.3 - reserve 640.0 = R_pin 1126.7 MiB
residency: config = head-pinned
residency: pinned   = 1094.7 MiB in 11 units (9 blk + head + misc)
residency: streamed = 1508.8 MiB in 23 ring units (23 blk), W = 2, window 281.3 MiB, b_layer_max 70.3 MiB
residency: predicted s/token = 0.531 (streamed 1508.8 MiB / 2.977 GB/s)
residency: prefill reads ~= ceil(n_prompt/n_ubatch) x 1508.8 MiB streamed (the ring walks once per ubatch graph -- expected, not a bug)
```

Unchanged from the B2/B3/B4 baseline (same model, same `--max-ram-mib`/`--stream-reserve-mib`
defaults) — Milestone A reconfirms the ledger rather than discovering a new one. This run's
410.33 ms/token is in fact *faster* than B3's own number of record (521.73 ms/token; see MA-4
note below on why that is not directly comparable) — consistent with the upper-bound-D
explanation above. The ±30% band still has to cover the *other* direction too: host
contention on a Docker Desktop VM (other processes, CPU throttling) can push a run slower than
predicted even though `D` cannot push it slower on its own, which is why the band is symmetric
rather than one-sided.

### MA-1b — full-ubatch prefill (first ever), same flags as MA-1, ~600-token prompt, `-n 16`

**Prompt construction.** `bench/prompts/hard.txt` alone (20 lines) is 493 tokens — short of
600 — so the prompt is that file plus its own first 5 lines repeated (25 lines total),
verified at **623 tokens** with `llama.cpp/build-noblas/bin/llama-tokenize --show-count`
(host macOS build; the container has no `llama-tokenize` target and none was added, to keep
this task's file list to what the brief specified). `llama-completion`'s own prefill counted
**622 tokens** for the identical file — a 1-token discrepancy attributable to a difference in
how the two binaries count/report the BOS token, not a construction bug (`scripts/milestone_a.sh`
generates the file from the two checked-in source lines and asserts a fresh tokenizer count
`>= 600` before every run, so this is self-verifying on re-run). Either count exercises a full
512-token ubatch (`ceil(622/512) = 2` ubatches: 512 + 110) for the first time in this project —
previously every run had prompts well under 512 tokens, so no ubatch was ever more than
fractionally full and B3's Concern 1 (`reserve_mib` untested against a full ubatch) was open.

**Cap held.** `memory.peak` **1,770,143,744 B = 1688.1 MiB**, memwatch max `memory.current`
**1,684.2 MiB** — both comfortably under 2048 MiB (**PASS**).

**Reserve-under-full-ubatch verdict: still conservative, not too small.** Memwatch's max
sampled `anon_bytes` (the non-file-backed charge the 640 MiB `--stream-reserve-mib` exists to
cover) peaked at **374,874,112 B = 357.5 MiB** — 282.5 MiB of slack against the 640 MiB budget,
comparable to (slightly less than) B3's original 306 MiB of slack measured at a 10-token
prompt. **This closes B3's Concern 1**: the reserve was sized to cover the worst case and the
worst case (a genuinely full 512-token ubatch, exercised here for the first time) still leaves
headroom.

**Prefill time is compute-bound, not read-bound, and that is the interesting finding.**
Measured prefill: **14,716.48 ms = 14.72 s** (23.66 ms/token average over 622 tokens). The
brief's analytical read-only lower bound — `ceil(622/512) x 1508.8 MiB streamed / (2.977 GB/s
in MiB/s)` = 2 x 1508.8 / 2839.5 = **1.063 s** — undershoots the measurement by ~13.8x. This is
expected once you separate the two costs the ledger's own formula lumps together
(`+ compute`, unspecified): the streamed-bytes-per-ubatch term (1508.8 MiB) is **constant**
regardless of how many tokens are in the ubatch, because the ring walks the same weight units
once per graph either way — but the **FLOPs** are not constant, they scale with ubatch token
count. A 1-token decode step's compute is negligible next to its 1508.8 MiB weight read, so
decode is read-bound and the ledger's formula (no `+ compute` term) predicts it well (MA-1's
0.773 measured/predicted ratio). A 512-token prefill ubatch does roughly 512x the FLOPs of a
1-token step while reading the *same* 1508.8 MiB, so prefill is compute-bound instead —
consistent with `GGML_BLAS=OFF` on this cap-relevant build (no vectorized BLAS gemm, plain CPU
kernels only). This is a real, load-bearing distinction for anyone sizing prefill latency from
the ledger's decode-oriented formula alone.

Ledger block (identical to MA-1's, since it is a function of the model/flags, not the prompt):

```
residency: mapping 2614.0 MiB, page 4096 B, 34 units = 32 blk + head (tied) + misc (0.010 MiB)
residency: ledger: max_ram 2048.0 - mlock_front 0.0 - resident_other 0.0 - window 281.3 - reserve 640.0 = R_pin 1126.7 MiB
residency: config = head-pinned, pinned 1094.7 MiB (9 blk + head + misc), streamed 1508.8 MiB (23 blk), W = 2
```

### MA-2 — enforced (`cgrun 2048m`, same flags as MA-1)

`exit 0`, `OOMKilled=false`. `memory.peak` **1,721,245,696 B = 1641.5 MiB** — under the
*hard* 2048 MiB cap this time (406.5 MiB headroom), not merely the 2048 MiB software budget
inside a looser 3g container. Decode **442.95 ms/token = 2.26 tok/s**, within **-7.4%** of
MA-1's 2.44 tok/s (well inside the ±15% band — **PASS**). Load 2391.99 ms, prefill 239.17
ms/token. **This is the run that answers the headline question**: the same config that passed
"observed" also survives real kernel enforcement of the cap, at a throughput indistinguishable
from the observed run within host noise.

### MA-3 — unmanaged A/B (`cgrun 2048m`, no `--stream-weights`)

**Kernel-fair arm** (`--no-repack -c 4096`, the correct control per B3 Finding 4 — see the
note below): `exit 0`, `OOMKilled=false` — it **ran to completion**, but under sustained
reclaim thrash rather than cleanly. `memory.peak` **2,147,483,648 B = 2048.0 MiB, exactly the
cap** — the kernel held it there rather than killing it, because these are all clean
`MAP_SHARED` file pages: the OOM killer is a last resort for memory that *cannot* be reclaimed
(anonymous/dirty), and every byte of this model's weights is reclaimable by simple eviction
and refault. Load **5036.82 ms** (2.1x MA-2's load, reclaim pressure already active during
load), decode **1701.11 ms/token = 0.59 tok/s** — **3.83x slower than MA-2's managed 2.26
tok/s**. `/usr/bin/time -v`: **975,286 major faults**, **File system inputs 352,386,776**
sectors (x512 B = **168.0 GiB** read over the measured **115.68 s** wall-clock run — GNU
`time`'s `Elapsed (wall clock) time`, `1:55.68`) — about **65.8x the model's own 2.6 GiB
size**, direct evidence of the predicted reclaim-thrash: the kernel evicts and re-faults
the same weight bytes over and over because nothing is holding a working set steady the way
the residency manager's ring does.

**Naive-default arm** (no flags beyond `-c 4096`, repack left at its default ON): one-sentence
fate — **it loaded a 2603.50 MiB `CPU_Mapped` buffer AND a separate 2599.83 MiB `CPU_REPACK`
buffer (the "default repack would double-charge" prediction, confirmed exactly — ~5203 MiB of
model-related footprint attempted against a 2048 MiB cap before KV/compute are even counted),
survived long enough to generate a handful of tokens, and was OOMKilled (`exit 137`) at
wall-clock ~16 s**. Unlike the kernel-fair arm, this genuinely could not be satisfied by
reclaim alone, because the repacked copy exists nowhere else to re-fault from — the OOM killer
is not optional there.

**Managed/unmanaged ratio**: 2.26 / 0.59 = **3.83x** (MA-2 vs the kernel-fair arm, the only
unmanaged arm that produced a decode rate to compare against). The naive-default arm has no
throughput number — it never reached steady-state decode.

### MA-4 — callback overhead, by reference (no new runs)

Satisfied by reference to `task-B3-report.md`'s fix round / `docs/WORKLOG.md`'s "Task B3 fix
round" section, per the brief. Clean same-config pair (SmolLM2-135M, `-n 512 -t 4`,
`--ignore-eos`, 8 interleaved rounds, differing **only** by the callback):
callback-**invocation** overhead best-of-8 = **-0.008%**, under the host's measurement floor.
What the real gate itself costs (`gatecb` vs `noopcb`, 21 real gates/graph on the resident
135M model): **-7.64%** = 0.215 ms/graph; scaled to the 4B's 23 gates and heavier graph, ~0.3
ms against the 410-443 ms/token this run measured (MA-1/MA-2 above; B3's own record was
521-654 ms/token) = **~0.07% at worst, under 0.1%**. No new measurement was needed or taken
for Milestone A.

### The `--no-repack` accuracy reference (kernel-set delta deferred to the G-gates)

Every comparison above that needs to be **kernel-fair** runs on the non-repacked kernel set,
not a bare/default baseline, per B3 Finding 4. MA-1/MA-1b/MA-2 land there automatically via
`--stream-weights` itself (B2 Discovery 1 — streaming disables `use_extra_bufts` because
repacking would copy weights out of the mmap); MA-3's kernel-fair arm does not pass
`--stream-weights` at all, so it needs the explicit `--no-repack` flag to land on the same
kernel set for a fair comparison. B3 measured that repack is not only a throughput tradeoff
but a **numerical** one —
on aarch64/GCC the repacked q4_K/q6_K kernels reach a different sampled token within 16 tokens
of greedy decode (`--no-repack` non-streamed reproduces streamed output byte-for-byte, sha256
`fc290ef7...`; the bare/default baseline does not, sha256 `4de304e3...`). That is exactly why
MA-3 has two arms rather than one: kernel-fair (`--no-repack`) isolates the
streaming-vs-not effect from the repack-vs-not effect, and naive-default (repack ON) is
reported separately, in one sentence, precisely because its OOMKill is dominated by the
repack double-buffer rather than by anything streaming-specific. A **quantified** accuracy
delta between the repacked and non-repacked kernel sets (perplexity, or a small accuracy set
run both ways) is **deferred to the G-gates**, per B3 Finding 4 and `docs/WORKLOG.md` — no
accuracy numbers are claimed here, on either kernel set.

### Multi-tier under the cap (Phase C, S3.1–S3.4 — the informal G8 preview)

Same environment as the Milestone A header above, llama.cpp branch `streaming` @ `7593921`
(the C4 fix commit, final). The trio bundle is `muta-trio.gguf` (3.2 GB): front =
SmolLM2-135M (`m0.`), easy = Qwen3.5-0.8B (`m1.`), mid = Qwen3.5-4B (`m2.`).

**Configuration of record: `--stream-weights --max-ram-mib 2048 --ctx-expert 4096
--tier-ctx easy=4096 --ubatch 128`.** The trio *cannot* fit 2048 MiB at duo's default
`--ctx-expert 8192` + n_ubatch 512: the compute buffer is `n_vocab × n_ubatch` f32 per
context (measured 505.02 MiB at ubatch 512 for one 248k-vocab tier, held for the process
lifetime), so the fixed non-weight cost alone is ~2.6 GiB before one weight byte of mid.
The ledger says so and **refuses** (exit 1, inequality printed, no OOM) — degradation,
not errors. `-ub 128` costs ~123 MiB per 248k-vocab tier instead and is the single
largest non-weight RAM lever in the process. Full compute-buffer measurement matrix and
the flash-attention caveat (the estimator has no n_ctx term, valid only with FA ON, so
`--stream-weights` forces `LLAMA_FLASH_ATTN_TYPE_ENABLED`) are in `docs/WORKLOG.md` Task C4.

**Ledger of record, trio @ 2048 MiB, ctx 4096, ubatch 128** (identical macOS and
container): mid = **head-pinned**, head 497.3 MiB pinned, 0 blk pinned, **2106.2 MiB
streamed** over 32 ring units, W = 2, predicted **0.742 s/token** at D = 2.977 GB/s.
Container measured **1.3–1.7 tok/s** on the streamed mid segments — within ~10% of the
prediction. Two mechanisms make the cross-terms add up:

- **Occupancy serialization:** at most one STREAMED tier is ACTIVE. `duo_switch_to()`
  suspends the outgoing tier, and suspend bulk-evicts *including its pins*; a manager is
  parked the moment it is built, so two tiers' pins are never installed at once. A
  suspended streamed tier charges another tier's ledger for its KV + compute buffer and
  **nothing** for its weights.
- **Sticky demote, observed every run at 2048:** with easy resident the ledger refuses
  (`R_pin` negative at W=1, both head configs); `[ledger] DEMOTE easy resident->streamed`
  fires once, mid re-solves feasible, and easy's own manager then pins its entire
  500.8 MiB (0 streamed) because a suspended mid charges it only KV + compute.

**Cap runs** (all exit 0, OOMKilled=false; fresh container per run):

| run | cgroup `memory.max` | `memory.peak` | vs 2048 |
|---|---|---|---|
| (i) easy prompt, easy answers | 3 GiB (observed mode) | 1417.9 MiB | −630 |
| (ii) hard prompt, mid streams (`-n 96`) | 3 GiB (observed mode) | 1640.7 MiB | −407 |
| (iii) forced easy→mid conf escalation | 3 GiB (observed mode) | 1656.9 MiB | −391 |
| (iv) 3-turn alternating easy/hard/easy | 3 GiB (observed mode) | 1653.8 MiB | −394 |
| **(iii) re-run, G8's own condition** | **2048 MiB (enforced)** | **1755.2 MiB** | **−293** |

The last row is the multi-tier headline: the whole trio — mlocked front, resident easy,
streamed mid — completes a real conf-triggered easy→mid escalation under a
kernel-enforced 2048 MiB cap with 292.8 MiB of headroom, `[tier] switch easy->mid
reason=conf` intact. Control: the same trio **without** `--stream-weights` is OOM-killed
at 3 GiB (exit 137).

**TTFT (staged startup + opener, C3):** first token in **430.9 ms** with the
`--ttft-opener` (front mlocks and speaks first while the background loader brings tiers
up) versus **11,247.3 ms** for the same prompt with `--no-ttft-opener` — a 26× reduction.
Both figures are macOS warm-cache; the formal G11 form (cold start, `drop_caches`, inside
the enforced container, <300 ms threshold) was never run — see wrap-up status below.

**Defect C5 — diagnosed 2026-08-14: the aarch64 repacked Q4_K kernels break the
SmolLM2-135M forward pass.** The original symptom: the front's opener was token salad and
every route score shifted strongly positive (`Say hello.` +2.35 in the container vs −3.16
on macOS), so at τ=0 everything routed hard; Phase C gates worked around it with
`--route-threshold 3.0`. Diagnosis (rung 1 of the WORKLOG ladder, no rebuild needed):
the identical `llama-completion --bundle-prefix m0.` run flips from garbage to coherent
on `--no-repack` alone, and `llama-duo --route-only` scores follow the kernels —
`Say hello.` is **+2.3464** repacked vs **−3.3223** non-repacked (macOS reference −3.16).
One defect, not two. The easy/mid qwen35 tiers were never affected; the 135M llama-arch
geometry (n_embd 576, 9 heads) is where the repack path goes from B3's known numerical
divergence to outright wrong — an upstream kernel bug, not this tree's patch.

**Validated route-around: `--tier-policy front=streamed`** (a streamed load forces
`use_extra_bufts` off). With it, **default τ=0 routing works in the container for the
first time**, under the enforced cap (`cgrun 2048m`, config of record plus the policy
flag): hard prompt → `route=hard s=1.056` (macOS reference +1.064), coherent opener,
`switch none->mid`, correct algebra answer at 2.0 tok/s streamed, `memory.peak`
**1763.2 MiB**; easy prompt → `route=easy s=-3.322`, coherent answer, peak ≈954 MiB.
Both exit 0, OOMKilled=false. Cost: the front loses mlock, so first token is
1079–1215 ms instead of 431 ms — the proper fix (plumb `use_extra_bufts=false` per tier
through duo, or fix the upstream kernel) needs a rebuild from `patches/`. Full detail in
`docs/WORKLOG.md` "C5 diagnosis".

### Wrap-up status (2026-08-14)

Execution stopped after Phase C + Milestone A. Phase D (S4 spec-decode amortizer:
mechanism probe, `--draft-tier`/`--draft-k`, acceptance harness) and the formal Phase E
gate harness (`scripts/stream_gates.sh`, default-K selection) were **descoped at
wrap-up** — not attempted, not partially built. Where that leaves each gate:

| gate | status at wrap-up |
|---|---|
| G8 (cap) | **Answered in substance**, both halves: cap half via the enforced-2048m escalation run, 1755.2 MiB peak (table above); answer-quality half via the C5 route-around (2026-08-14) — coherent, correctly-routed answers at default τ=0 under the enforced cap (`route=hard s=1.056` / `route=easy s=-3.322`, peaks 1763.2 / ≈954 MiB). The formal per-mode × per-cap-mode matrix was not emitted. |
| G9 (latency model) | **Answered in substance**: MA-2 meas÷pred 0.834 (±30% band); trio streamed segments within ~10% of the ledger's 0.742 s/token. Formal `-n 64` forced-hard run not taken. |
| G10 (amortization) | **Not run** — requires Phase D. No K curve, no default K chosen. |
| G11 (TTFT) | Mechanism proven (430.9 ms vs 11,247.3 ms warm, 26×); the formal cold-start in-container <300 ms measurement was never taken, and the known KV-parse risk (bundle loads parse both 248k vocab arrays on the front's critical path) was never exercised cold. |
| G12 (managed/unmanaged A/B) | **Answered in substance**: 3.83× at the single-model level (MA-2 vs MA-3 kernel-fair), OOM-kill vs completion at the trio level (Phase C control). Formal same-prompt `-n 32` duo A/B not taken. |

**Artifacts and reproducibility.** The development worktree (with the llama.cpp checkout,
branch `streaming` @ `7593921`) was removed after the work was consolidated into `main`.
What survives, verified 2026-08-14: the `muta-stream` image and the `muta-build` /
`muta-models` Docker volumes still reproduce the result — a fresh
`scripts/stream_env.sh cgrun 2048m` streamed-4B run gave exit 0, OOMKilled=false,
`memory.peak` 1638.7 MiB, decode 447.66 ms/token = 2.23 tok/s, matching MA-2
(1641.5 MiB, 2.26 tok/s) within host noise. The engine tree itself is reconstructable
from `patches/`: `0001–0016` are the duo/bundle series (upstream base `7ba604f`,
2026-08-09 master), `0017–0032` the streaming series on top (exported from
`01f58cd..streaming`; `0032` **is** the final commit `7593921`, so the in-tree series is
current through the last engine change).
