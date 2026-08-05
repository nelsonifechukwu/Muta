# D1 model/quant bake-off — 2026-08-05 campaign journal

**For anyone picking this up:** this is the raw working journal (pre-registered predictions,
graded honestly, including the misses). The reviewed summary lives in `RESULTS.md`
(2026-08-05) and the scored ablation rows in `bench/optimization-log.md`. Every number here
is `dev_host_provisional` — an Apple M2 Pro that also ran another project's `llama-cli` at
~100% CPU throughout, so **accuracy rows are decision-grade (deterministic, load-independent)
and throughput rows are not**.

## Reproducing it

```bash
# 1. the profiler + its accuracy stack (GPL-3.0, never vendored — cloned by SHA)
python3 -c "from bench.adtc import install; install.ensure_profiler()"

# 2. candidate GGUFs (pinned; ~14 GB)
python3 scripts/fetch_models.py --quant-variants

# 3. the batteries (serial — parallel evals deadlock on the subprocess timeout)
bash bench/measurements/run-serial-battery.sh
bash bench/measurements/run-stem-probe.sh

# 4. score the composite (both audit scenarios)
python3 bench/score_campaign.py --audit-tps-4b 2.0 --bw 28 --tps-max 15
```

Measured rows: `bench/measurements/bakeoff-20260805.jsonl`. Audit-parity build recipe and
launch posture: `docs/audit-parity.md`.

---

# D1 model/quant campaign — 2026-08-05 (dev_host_provisional)

Autoresearch-style loop: frozen harness (`bench/adtc_bakeoff.py` + `bench/.venv-profiler`
accuracy path + three llama-bench builds), one composite objective (`bench/score.py`
S_total at tps_max=15, plus a cohort-30 sensitivity read), pre-registered predictions
below, append-only measurements in `bakeoff.jsonl`. Harness is not edited mid-campaign.

## Scenario model (from verified scoring-path facts)

- **Scenario S (audit docker, most likely Gate 2)**: llama-bench b10175 SSE4.2-only.
  Q4_0 = only vectorized weight kernel (verified in source: `__SSSE3__` path exists for
  q4_0_q8_0 only; q4_K/q6_K/iq4_xs → generic scalar). No repack (all x86 repack paths
  gated on compile-time AVX2). Scored RSS ≈ file + 0.4-0.6 GB. Thermal null on VM.
- **Scenario L (Standard Laptop, AVX2 llama-bench)**: decode bandwidth-bound
  (DDR4 dual ≈ 25-35 GiB/s practical → 4B Q4 ≈ 9-14 tok/s). Q4_0/Q4_K repack ≈ +file-size
  anon RSS (measured 4.36 GB total for stock Q4_K_M); Q3_K/IQ4_XS bodies don't repack.
  Thermal −10 risk is real on laptops.
- Accuracy (both): llama-cpp-python AVX2/NEON, n_ctx=2048, no chat template, greedy.

## Candidates

| id | file | GB | status |
|---|---|---|---|
| stock | Qwen3.5-4B-Q4_K_M | 2.55 | on disk |
| ud-q3kxl | Qwen3.5-4B-UD-Q3_K_XL | 2.27 | downloaded |
| iq4xs | Qwen3.5-4B-IQ4_XS | 2.31 | downloading |
| ud-q4kxl | Qwen3.5-4B-UD-Q4_K_XL | 2.71 | queued |
| q4_0 | Qwen3.5-4B-Q4_0 | ~2.4 | to fetch (core-cand-q4-0) |
| 2b | Qwen3.5-2B-Q4_K_M | ~1.2 | to fetch (core-cand-2b-q4km) |
| 0.8b | Qwen3.5-0.8B-Q4_K_M | 0.50 | on disk (floor reference) |
| custom-* | BF16 + llama-quantize recipes (q4_0 embd, imatrix) | — | wave 2 |
| dense-probe | Qwen3-4B-Instruct-2507 Q4_K_M | ~2.4 | probe only (GDN-vs-dense TPS control) |

## Pre-registered predictions (write BEFORE measuring; grade honestly after)

Accuracy battery (arc_easy:100 / arc_challenge:100 / sciq:100 / gsm8k:40, acc_norm / strict exact_match):

1. stock 4B Q4_K_M: arc_e 0.85-0.92, arc_c 0.65-0.80, sciq 0.93-0.97, gsm8k 0.55-0.80.
2. 0.8B: arc_e 0.62-0.72, arc_c 0.35-0.45, sciq 0.80-0.90, gsm8k 0.15-0.35.
3. ud-q3kxl: MCQ within 2 pts of stock; gsm8k −2 to −6 pts vs stock.
4. iq4xs: MCQ within 1 pt; gsm8k −1 to −3.
5. ud-q4kxl: ≈ stock ±1 everywhere.
6. q4_0: MCQ −0 to −1.5; gsm8k −1 to −4 vs stock.
7. 2b: MCQ 8-15 pts below stock; gsm8k −15 to −30.

Throughput/RSS:

8. Rosetta SSE probe (audit proxy): 4B Q4_0 tg ≥ 2.5× 4B Q4_K_M tg (ratio, interleaved).
9. Native arm64 b10175 tg128 tracks 1/file-size for K-quants: ud-q3kxl +8-12% vs stock,
   q4_0 +3-8%, 2b ≈ 2.1×; iq4xs *slower* than stock despite smaller file.
10. x86sse RSS (no repack): stock ≈ 2.9-3.2 GB tree peak; native arm64 (repack) ≈ 5.0-5.3.

Decision rule (pre-registered): composite S_total with measured S_acc proxy
(mean of 4 tasks × 100), S_perf/S_eff from the scenario the number belongs to; a candidate
must beat stock on BOTH scenario composites, not regress gsm8k by more than the points it
buys elsewhere (exchange: 1 gsm8k pt on the 4-task mean = 0.125 S_acc pt = 0.0625 S_total),
and never fail a probe (crash/nonsense output = reject).

## Verdicts (filled as measurements land)

### Measured rows (profiler-exact accuracy path, dev host, ambient load ~50)

| model | task | score | metric | wall | prediction | graded |
|---|---|---|---|---|---|---|
| 4B Q4_K_M (stock) | arc_easy:100 | **0.78** | acc_norm | 2467s | 0.85-0.92 | **MISS low** — raw no-template MCQ under-performs chat-mode reputation; recalibrate all MCQ predictions down ~5-8 pts |
| 4B Q4_K_M (stock) | arc_challenge:100 | **0.53** | acc_norm | 1780s | 0.65-0.80 | MISS low, same direction — recalibration holds |

Tensor-map facts (gguf-py header reads): every stock candidate incl. Q4_0 keeps
token_embd at **Q6_K** (497-521 MB) → scalar head in the audit build; stock Q4_0 also
carries 48×Q8_0 + 24×Q5_K sensitive tensors (scalar there too) → ~25-40% of its bytes
stay off the SSSE3 path. UD-Q3_K_XL carries 48×F16 tensors (F16C off at audit → slow).
Custom fast-head recipe remains the unique full-fast-path option.

Rosetta SSE probe (x86sse build, -p 32 -n 16 -r 1, interleaved 2 rounds, load 60-74 —
**ratio signal only**): Q4_K_M tg 0.139 / 0.015; Q4_0 tg 0.194 / 0.261 tok/s.
Q4_0/Q4_K_M ≈ **1.4-1.9×** (prediction ≥2.5× — under-shot; consistent with Q4_0's
Q6_K head + 48 Q8_0 tensors keeping ~30% of bytes scalar). Direction confirmed;
quiet-host rerun required before pricing. Absolute scalar tg this small also means:
in the docker-audit scenario S_perf compresses toward 0-5 pts for every 4B variant →
that scenario is decided by S_acc + S_eff (small file, max accuracy), with Q4_0 a
cheap hedge that also wins the AVX2-laptop scenario on repack GEMV.

| 4B Q4_K_M (stock) | sciq:100 | **0.97** | acc_norm | 1778s | 0.93-0.97 | HIT |
| 0.8B Q4_K_M | arc_easy:100 | **0.66** | acc_norm | 221s | 0.62-0.72 | HIT |
| 0.8B Q4_K_M | arc_challenge:100 | **0.34** | acc_norm | 274s | 0.35-0.45 | ~HIT (edge) |
| 0.8B Q4_K_M | sciq:100 | **0.85** | acc_norm | 634s | 0.80-0.90 | HIT |

**Model-gap interim (3-task MCQ mean): 4B 76.0 vs 0.8B 61.7 → gap 14.3 pts** — smaller
than the 20-35-pt chat-benchmark estimate in RESULTS 2026-08-04. gsm8k pending = decider.

**Harness bug found (upstream, competition-relevant):** profiler `_extract_score` @7adbe08
under lm-eval 0.4.12 returns gsm8k's `sample_len` (= the limit!) as the score — generation
tasks would be mis-scored by the official tool. Bake-off runner v2 now extracts
explicitly (acc_norm > acc > exact_match,strict); MCQ rows unaffected (acc_norm path was
correct). Worth reporting upstream before the audit window.

### Model-class results (serial battery v2, gsm8k = exact_match strict, runner v2)

| task | 4B Q4_K_M | 2B Q4_K_M | 0.8B | prediction graded |
|---|---|---|---|---|
| arc_easy:100 | 0.78 | 0.73 | 0.66 | 2B not predicted; 0.8B HIT |
| arc_challenge:100 | 0.53 | 0.40 | 0.34 | — |
| sciq:100 | 0.97 | 0.91 | 0.85 | — |
| gsm8k:40 (strict) | 0.65 | 0.55 (flex 0.575) | 0.20 | 4B 0.55-0.80 HIT; 0.8B 0.15-0.35 HIT; 2B −15/−30 pred = **MISS (gap far smaller)** |
| **4-task mean** | **73.3** | **64.8** | **51.3** | |

**Headline: the raw-mode 4B→2B S_acc gap is ~8.5 pts (±2.7 SE), not the 13-15 chat-mode
estimate.** Composite deltas (2B vs 4B, S_acc=mean×100):
- Scenario L (AVX2 laptop, tps_max 15, BW 28 GiB/s): ΔS_acc −4.25, ΔS_eff +4.2,
  ΔS_perf +9.1 → **2B +9.1**. At cohort tps_max 30 the 2B edge grows.
- Scenario S (SSE docker, 4B ≈ 2 tok/s assumption): **2B +5.3**.
- Break-even accuracy gap ≈ 18-26 pts depending on scenario — the measured gap is
  well inside 2B-wins territory. Sensitivity risks: hidden set harder than the proxy
  battery (GPQA-like chat gap is 24), qualitative judging of the 4 prompts, sampling
  noise. Probes queued: 2B-Q6_K battery, harder-STEM MCQ (mmlu subtasks) 4B vs 2B.
- 0.8B: rejected (gsm8k 0.20; mean gap 22 pts — outside every break-even).

(the earlier 3-way-parallel battery attempt deadlocked on a 7200s subprocess timeout and
lost ~6 CPU-hours — harness v3 now returns failed rows on timeout; evals run serially.)

### Quant-variant rows (4B) — wave 1 COMPLETE

| variant | arc_easy:100 | gsm8k:40 strict | verdict signal |
|---|---|---|---|
| stock Q4_K_M (2.55 GiB) | 0.78 | 0.65 | baseline |
| **Q4_0 (2.41 GiB)** | **0.78** | **0.675** | **no accuracy cost; dominates stock: smaller + 1.4-1.9× audit-build tg** |
| UD-Q4_K_XL (2.71 GiB) | 0.78 | 0.65 | = stock at +0.16 GiB → rejected (KLD edge invisible at task level) |
| UD-Q3_K_XL (2.27 GiB) | 0.77 | 0.625 | −2.5 gsm8k pts (inside SE ±7.7) — prediction "−2 to −6" HIT; no cliff |
| IQ4_XS (2.31 GiB) | 0.82 | 0.65 | accuracy fine (arc_e high = noise), but scalar-audit + CPU decode worst → rejected on S_perf |

**Wave-1 quant conclusion: no accuracy cliff in any ≥3.5-bpw quant of the 4B. Quant
choice therefore collapses to S_perf/S_eff → Q4_0 family wins.**

### Gate results

- **Q4_0-EH (2.21 GiB, all-Q4_0 incl. head + ssm tensors): PASSED** — arc_easy 0.77,
  gsm8k 0.675 (flex 0.70). No measurable cost from the aggressive recipe.
- **2B-Q6_K (1.47 GiB): no gain** — 4-task mean 66.0 vs 64.8 (noise); 2B-Q4_K_M stays
  the 2B representative.

### Rosetta SSE probe #2 (quieter host, load 9-27, interleaved; ratio signal)

| model | tg r1 | tg r2 | pp r1/r2 |
|---|---|---|---|
| Q4_K_M | 2.96 | 5.45 | 6.6/6.8 |
| Q4_0 | 5.87 | 6.54 | 8.2/8.8 |
| **Q4_0-EH** | **6.61** | **6.76** | **9.1/9.0** |

EH/Q4_K_M tg = 1.24-2.23× (load-dependent); EH > stock Q4_0 in both rounds (+3-13%).
Absolute ~6.7 tok/s under Rosetta suggests the real audit box may sit well above the
2 tok/s anchor — scenario-S S_perf for EH could be 40-55, further widening its lead.

**Standing verdict (pre-imatrix): submission model = Qwen3.5-4B-Q4_0-EH** — wins/ties
scenario S, second in L, +8.8 raw acc pts over the 2B as hidden-task insurance, and it
is the better tutor. 2B-Q4_K_M documented as the aggressive alternative if organizers
confirm cohort-relative TPS_max with a small-model cohort.

Engine-config track (self-reported S_perf/S_eff reframe): no_repack wired into
RuntimeConfig+server (default off, env-flippable; 12/12 tests), Linux None-threads
documented as deliberate (engine default = physical/P cores), x86 AVX-only + AVX2
Rosetta probe builds launched, 5-agent research workflow complete → docs/audit-parity.md.

Engine research verdicts (source-verified): repack = prefill-only on x86 (PR #12332
pp +61-76%, tg128 −2%) at +Q4_K-tensor-bytes anon RSS → GGML_CPU_REPACK=OFF (an upstream
cmake option) is the clean self-report lever; first_token_latency_ms is ALSO reconciled
at ±25% so build-mismatch postures hard-fail on pp deltas alone; cgroup cpuset flips
llama-bench thread default to all-cores (never use); BIOS SMT-off on hybrid halves the
P-core count (never); official page says audit numbers score ("TPSact during audit") —
self-report exists to reconcile. Product fixes: vision --no-repack (private repack copy
would bust 7 GB with two 4B servers), compose thread-pin x86 warning.

RSS probe (time -l peak, mini-bench, macOS host under eval memory pressure — caveat):
x86sse Q4_0 2.44 / Q4_K_M 2.83 GB (≈ file size, no repack — clean confirmation);
x86avx2 rows 2.98/3.11 GB are pressure-confounded (macOS evicts cold file pages; the
repack-ON figure of record remains the 2026-08-04 Linux-VM 4.36 GB measurement).
