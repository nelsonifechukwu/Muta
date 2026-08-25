# Optimization log

**ROADMAP deliverable: Tue 14 Jul, `[All]`.** The standing rule: **every optimization is
recorded here as a before/after row the day it lands**, scored through
[`bench/score.py`](score.py). The report's ablation table is built continuously, not
reconstructed from memory in August.

An unlogged optimization did not happen. A logged one that made the score worse is more
valuable than an unlogged one that helped — the ablation table is the project's central thesis
under test, and a negative row is evidence.

## How to add a row

1. Measure before and after with the **same** harness, model, flags and fixture set
   (`make bench`). One variable at a time.
2. Score both through `score.py` and use `compare(before, after)` — it attributes the delta to
   a component and names the driver.
3. Paste the `ΔS_total` it reports. Do not eyeball it.
4. **Verdict** is `keep` / `revert` / `park`. `park` means it needs a decision you can't make
   alone — say who decides.

Numbers taken on a Mac (native or emulated) are **dev signals only** and must be tagged as
such. Only the x86 target box produces report numbers (ROADMAP 9–11 Aug).

## The exchange rate governs every verdict

At the provisional `TPS_max = 15`: **+2.00 pts per tok/s · −2.86 pts per GB · +0.50 per
accuracy point.** So **1 GB = 1.43 tok/s = 5.7 accuracy points**, and any RAM-spending change
must clear `ΔTPS ≥ 1.43 × ΔRAM_GB` to be worth it.

> **19 August provenance correction.** The repository never retained evidence for its claimed
> private organiser clarification. The current public challenge page says “highest speed across
> all submissions,” while the official profiler README/code implement the fixed, capped 15.
> New score-of-record rows use the executable profiler. Cohort-relative results are still saved
> as an explicitly separate alternative because that interpretation can flip the verdict.
> `score.py` now requires the formula and denominator provenance to be machine-readable.

## Log

| Date | Change | Harness | tps_max | Before (TPS / RAM / Acc) | After (TPS / RAM / Acc) | ΔTPS | ΔRAM | ΔAcc | ΔS_total | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-08-25 | Qwen3.5 0.8B matched export control → BF16 LoRA r16, 400-step MCQ-aligned fine-tune, merged Q4_0 | ARC-Easy-500 plus matched b10175 GCP 2C/4T scalar and vector binaries; same export path; RSS includes the recorded 45 MiB profiler-root estimate | profiler fixed/capped 15 | scalar 13.6086 tok/s / 690.90 MiB / 55.2% / 72.8896 | scalar 13.5971 / 690.95 MiB / 70.2% / 80.3664 | −0.0115 tok/s | +0.05 MiB | **+15.0 points** | **+7.4768 scalar; +7.5003 vector** | promote as scalar finalist; held-out ARC-Challenge, OpenBookQA and GSM8K checks also improve, but physical-laptop and final tutor-template gates remain |
| 2026-08-25 | Qwen2.5 1.5B same-export control → BF16 LoRA r16, 500-step licence-clean MCQ fine-tune, merged Q4_K_M | ARC-Easy-500 plus the same matched scalar/vector GCP harness | profiler fixed/capped 15 | scalar 5.6224 tok/s / 1,117.15 MiB / 74.4% / 65.3277 | scalar 5.6321 / 1,117.05 MiB / 77.8% / 67.0475 | +0.0098 tok/s | −0.10 MiB | **+3.4 points** | **+1.7198 scalar; +1.7001 vector** | promote as vector finalist; secondary held-out battery and physical-laptop validation remain |
| 2026-08-23 | image path: separate on-demand 4B reader → the selected 0.8B model with its exact 195.5 MiB projector | **measurement pending on x86 target**; ARM browser smoke used the real 601×751 `african billionaires.jpg`, pinned b10035, selected Qwen3.5-0.8B Q4_0, `n_ctx=4096`, and measured a 1.25 GiB product-tree peak while answering the top-left card correctly and retaining the image for a correct follow-up | not yet scored | old analytical auxiliary working set ≈3.79 GiB before gateway/core overlap; no usable end-to-end image answer | dev signal: 1.25 GiB product-tree peak; correct targeted answer + follow-up | — | not comparable until the same x86 harness is run | image capability, not an accuracy-score replacement | **no score claim** | keep the architecture; target A/B must separately measure text-only steady RSS, image-turn peak RSS/TTFT, and dense-image answer quality |
| 2026-08-21 | Muta Power: battery-aware Auto reasoning/reply caps, Critical optional-work reserve, and lower idle telemetry sampling | **measurement pending**: run interleaved default-vs-Eco blocks on the x86 target with the same 30-dialogue tutoring battery; record package joules from Linux powercap where available (otherwise ≥30-minute battery-energy blocks), latency, tokens, RSS/temp, and blind tutoring-quality rubric | not yet scored | — | — | — | — | — | **no savings or score claim** | product default requested by owner; target A/B gate is ≥10% lower joules/ordinary turn with no material tutoring-quality regression; retune or revert caps if it misses |
| 2026-08-20 | native unified context 2,048 → 12,288 plus byte-fallback hard fitting per lane | same GCP 2C/4T native service, final Qwen3.5-0.8B Q4_0, ready=true; warmed gateway+engine process-tree RSS via psutil; engine argv verifies `--ctx-size 12288`; TPS/accuracy held from the direct participant row for memory-only attribution, not remeasured | profiler fixed/capped 15 | 12.63 held / 0.9541 GiB / 64 held | 12.63 held / 1.0423 GiB / 64 held | 0 held | +0.0882 GiB (+90.31 MiB) | 0 held | **−0.2520** | keep; prevents the observed context-exhaustion truncations, remains 5.96 GiB below the 7 GiB hard ceiling; Compose 4B control stays at 2,048 |
| 2026-08-19 | Muta Tutor Q4_0: scalar → portable AVX2/FMA/F16C | b10175 GCP 2C/4T, same p512/tg128/no-ngl geometry and RSS sampler; separate native-off/AVX512-off binary; five AVX2 internal samples | profiler fixed/capped 15 | 9.9869 / 1.1065 GiB / 72 | 16.8927 / 2.0014 GiB / 72 | +6.9058 | +0.895 GiB | 0 | **+7.4696** | keep as AVX2 deployment signal; repacking costs 916 MiB, scalar-profiler submission unchanged |
| 2026-08-19 | Q4_K_M tied: scalar → portable AVX2/FMA/F16C | same; scalar row is the retained one-sample screen, AVX2 has five samples | profiler fixed/capped 15 | 5.2954 / 1.1558 GiB / 72 | 15.6714 / 1.9431 GiB / 72 | +10.3760 | +0.787 GiB | 0 | **+17.1597** | park as nominal AVX2 winner; only +0.1666 vs Q4_0 and one 13.6101 tok/s outlier, needs physical target |
| 2026-08-19 | Q5_K_M tied: scalar → portable AVX2/FMA/F16C | same | profiler fixed/capped 15 | 4.7839 / 1.3325 GiB / 76 | 12.7191 / 1.3326 GiB / 76 | +7.9352 | +0.0001 GiB | 0 | **+15.8701** | reject for current quant choice; AVX2 score 79.6307 remains below Q4_K_M/Q4_0/IQ4 |
| 2026-08-19 | IQ4_XS tied: scalar → portable AVX2/FMA/F16C | same | profiler fixed/capped 15 | 2.4961 / 1.0564 GiB / 70 | 14.0644 / 1.0569 GiB / 70 | +11.5683 | +0.0005 GiB | 0 | **+23.1351** | park as AVX2 efficiency hedge; 80.1089 is 0.3395 behind nominal winner |
| 2026-08-19 | BitCPM4-8B TQ2 envocab: scalar → portable AVX2/FMA/F16C | same | profiler fixed/capped 15 | 0.8108 / 2.2620 GiB / 88 | 7.4876 / 2.2621 GiB / 88 | +6.6768 | +0.0001 GiB | 0 | **+13.3534** | reject as capped-15 winner; 9.235× proves scalar TQ2 collapse, but AVX2 score 72.5121 trails by 7.94 |
| 2026-08-19 | Muta Tutor 1.7B → Qwen3.5-0.8B speed hedge | full bundled `adtc-profiler` participant run on GCP 2C/4T; five internal b10175 samples; direct root-plus-child RSS; ARC-Easy-50 | profiler fixed/capped 15 | 9.79 / 1.0901 GiB / 72 | 9.74 / 0.6784 GiB / 68 | −0.05 | −0.412 GiB | −4 | **−0.9237** | reject narrowly; keep 1.7B winner, retain 0.8B hedge for harder quality study |
| 2026-08-19 | Muta Tutor 1.7B → BitCPM4-8B TQ2 envocab | same full bundled-profiler harness | profiler fixed/capped 15 | 9.79 / 1.0901 GiB / 72 | 0.81 / 2.2525 GiB / 88 | −8.98 | +1.162 GiB | +16 | **−13.2810** | reject under profiler rule; accuracy leader remains selectable in UI |
| 2026-08-19 | Muta Tutor 1.7B → Qwen3.5-4B IQ4_XS | same full bundled-profiler harness | profiler fixed/capped 15 | 9.79 / 1.0901 GiB / 72 | 1.13 / 2.5658 GiB / 76 | −8.66 | +1.476 GiB | +4 | **−19.5360** | reject under profiler rule |
| 2026-08-19 | pure Q4_0 tied → Q4_K_M tied | b10175 profiler-reference no-AVX on GCP 2C/4T; default-5 incumbent vs transparent one-sample promotion screen; RSS adds a 45 MiB profiler-root estimate | profiler fixed/capped 15 | 9.9869 / 1.1065 GiB / 72 | 5.2954 / 1.1558 GiB / 72 | −4.6915 | +0.049 GiB | 0 | **−9.52** | reject; scalar k-quant kernel loses decisively |
| 2026-08-19 | pure Q4_0 tied → Q5_K_M tied | same | profiler fixed/capped 15 | 9.9869 / 1.1065 GiB / 72 | 4.7839 / 1.3325 GiB / 76 | −5.2030 | +0.226 GiB | +4 | **−9.05** | reject; Easy gain does not generalize to hard probes or repay scalar decode/RSS |
| 2026-08-19 | pure Q4_0 tied → IQ4_XS tied | same | profiler fixed/capped 15 | 9.9869 / 1.1065 GiB / 72 | 2.4961 / 1.0564 GiB / 70 | −7.4908 | −0.050 GiB | −2 | **−15.84** | reject; 51 MiB saved cannot repay scalar IQ kernel + accuracy |
| 2026-08-19 | pure Q4_0 tied → BitCPM4-8B TQ2 envocab | same | profiler fixed/capped 15 | 9.9869 / 1.1065 GiB / 72 | 0.8108 / 2.2620 GiB / 88 | −9.1761 | +1.155 GiB | +16 | **−13.65** | reject under profiler rule; accuracy leader remains selectable in UI and wins high-denominator AVX2 alternative |
| 2026-08-19 | scoring provenance: unsupported 6-Aug claim → dual evidence lanes | official page + profiler README/code/Dockerfile; source and git-history audit | 15 primary; 15/30/45/60/100/150 alternative | one blended/contradictory narrative | capped no-AVX primary + AVX2/webpage alternative, separately hashed | — | — | — | not a model delta | keep; prevents optimizing the wrong objective while preserving every result |
| 2026-07-31 | RSS ceilings: -np 2, --ctx-checkpoints 4, --cache-ram 256 (was auto-4/32/8192) | two-turn probe, docker/emulated | 15 | ~6.72 / 4.8 GB / — | 6.72 / 4.44 GB / — | ~0 | -0.36 GB | 0 | dev_host_provisional — RAM row only | keep |
| 2026-07-31 | speculation ON: --spec-type draft-simple + Qwen3.5-0.8B (dead flags + incompatible 0.6B before) | two-turn probe, docker/emulated | 15 | 6.72 / — / — | 4.77 / +1.02 GB / — | -1.95 | +1.02 GB | 0 | dev_host_provisional — acceptance 98.4% ; target-box row pending | park (needs x86 numbers) |
| 2026-07-31 | run.sh --native (pinned arm64 b10035 on host; docker default unchanged) | two-turn probe, native | 15 | 6.72 tok/s docker-emulated | 24.72 tok/s native (draft off: 30.84 tok/s; acceptance 98.41%) | +18.00 | ~0 | 0 | dev_host_provisional — dev-loop only, never report-grade | keep |
| 2026-08-01 | threads = P-core count (6/6, auto-derived on darwin; engine default before) | bench/native_sweep.py, native, interleaved 3×3 A/B | 15 | 29.78 max (probed 6.4–23.5 under morning load; -t 10 collapses to 4.4) / — / 4-4 probes | 31.09 max; winner-family floor 20.5 under the same load | +1.31 (max); the loaded-host floor is the real win | 0 | 0 | dev_host_provisional — darwin-only code path, x86 untouched | keep |
| 2026-08-01 | --kv-unified with explicit -np 2 (restores full 2048 shared window; 1024/slot before) | bench/native_sweep.py, native | 15 | 1495-token prompt → 400 / 3375 MiB fp / — | accepted / 3328 MiB fp / — | ~0 | -0.05 GB | 0 | dev_host_provisional — capability fix priced at zero | keep |
| 2026-08-01 | --ctx-checkpoints 4→2 | bench/native_sweep.py full suite, native | 15 | reuse 29/33 / 3519 MiB fp stressed / 4-4 | reuse 29/33 / 3137 MiB fp stressed (combined winner) / 4-4 | 0 | -0.20 GB worst-case bound | 0 | dev_host_provisional | keep |
| 2026-08-01 | native speculation retunes: draft n-max 3 (98.8% acc) 15.75; n-max 8 25.89; ngram-4/12 21.55 — vs 29.6 draft-off | bench/native_sweep.py, native | 15 | 29.6 draft-off | best retune 25.89 | -3.7 to -13.9 | +0.52 GB (draft) | 0 | dev_host_provisional — run.sh --native now exports MUTA_RT_SPEC_TYPE=none; x86 verdict still pending | reject on native (park for x86) |
| 2026-08-04 | cactus GEMV probe: --threads 4 (T4-DECODE, vs 6 shipped) | bench/native_sweep.py, native, interleaved A/B, 2 rounds, heavy uncontrolled ambient load (load avg 3.9-20.1) | 15 | WINNER anchors 22.86/23.33 max, 13.17 floor (bracketing round 1) | 20.06 max, 8.97 floor | -2.80 to -3.27 (round 1) | ~0 | 0 | dev_host_provisional — fails both keep criteria under the exact loaded-host regime the probe targets | reject |
| 2026-08-04 | cactus GEMV probe: --threads 5 (T5-DECODE, vs 6 shipped) | bench/native_sweep.py, native, interleaved A/B, 2 rounds, heavy uncontrolled ambient load (load avg 3.9-20.1) | 15 | WINNER anchors 23.33-27.38 max, 13.16-19.31 floor (both rounds) | 24.66/25.65 max, 12.88/18.89 floor | -0.61 to +1.33 (mixed, inside noise) | ~0 | 0 | dev_host_provisional — max/floor deltas both inside the session's own noise band | inconclusive under load — re-run on quiet host |
| 2026-08-04 | cactus stream-weights probe: --no-repack (WINNER-NOREPACK, repack confirmed present at b10035 via --help) | bench/native_sweep.py full suite, native, heavy uncontrolled ambient load | 15 | WINNER full-suite fp 3236 MiB, max 22.86-27.38 pooled | fp 602 MiB, max 27.09 | -0.29 to +4.23 (no measurable regression) | -2.57 GB | 0 (accuracy 4/4 unchanged) | +7.35 (score.py exchange_rate, tps_before=27.38 — decode clamps at tps_max=15 so the gain is ~all RAM) | keep as documented lever — product-RAM-only (docs/rules-digest.md: profiler's llama-bench call is fixed/independent of RuntimeConfig, so no expected S_eff move); not wired as a RuntimeConfig default in this task |
| 2026-08-05 | core quant: Qwen3.5-4B Q4_K_M → Q4_0 (stock unsloth) | bench/adtc_bakeoff.py accuracy (profiler code path) + Rosetta x86-SSE tg probes, dev host | 15 | 0.78 arc_e / 0.65 gsm8k / 2.55 GiB | 0.78 arc_e / 0.675 gsm8k / 2.41 GiB | audit-build ratio 1.4-1.9x (probe-grade only) | -0.14 GB | +0.6 pts on the 2 tasks measured (inside noise) | not priced — S_perf leg is not measurement-grade | keep (dominates: smaller, no accuracy cost, only quant with a vectorized kernel in the audit build) |
| 2026-08-05 | core quant: stock Q4_0 → **Q4_0-EH** (ours: `llama-quantize --token-embedding-type q4_0` from BF16; puts the tied 248k-vocab head on the SSSE3 path too) | same | 15 | 0.78 arc_e / 0.675 gsm8k / 2.41 GiB | 0.77 arc_e / 0.675 gsm8k / 2.22 GiB | +3-13% vs stock Q4_0 (2 single-rep rounds — noise-grade) | -0.19 GB | ~0 (−1 pt arc_e, inside ±11.6 difference CI) | not priced (see above) | keep pending publication — **no provenance surface: shipping it needs a public URL, pins entry and metadata rewrite** |
| 2026-08-05 | core model class: 4B → 2B (Qwen3.5-2B-Q4_K_M) | bench/adtc_bakeoff.py 4-task battery, dev host | 15 | 4-task mean 73.3 / 2.55 GiB | 64.8 / 1.19 GiB | modelled (not measured): 2.1-2.3x | -1.36 GB | **-8.5 pts (difference SE 3.67; 95% CI [1.3, 15.7])** | +7.7 (laptop scenario) / +4.8 (audit-docker scenario), per bench/.artifacts/score_campaign.py | **park — the composite prefers the 2B; the 4B is retained on out-of-band grounds (hidden-set difficulty, judged prompts, tutor quality). Decider: harder-STEM probe, running.** |
| 2026-08-05 | core model class: 4B → 0.8B | same | 15 | 73.3 / 2.55 GiB | 51.3 / 0.50 GiB | modelled ~5x | -2.05 GB | -22.0 pts | positive on the composite alone | **reject on product grounds** (gsm8k 0.20 — unusable as a tutor; the composite does not see judged answers) |
| 2026-08-05 | quant ladder rejects: UD-Q4_K_XL (2.71 GiB, = stock accuracy at +0.16 GB), UD-Q3_K_XL (2.27, gsm8k −2.5), IQ4_XS (2.31, accuracy fine but IQ dequant is the slowest scalar path) | same | 15 | — | — | — | — | all inside the difference CI | negative or ~0 | reject all three |
| 2026-08-20 | Qwen3-1.7B Q4_0 → final Muta Tutor Qwen3.5-0.8B Q4_0 | direct participant profiler, GCP 2C/4T, b10175 scalar, ARC-Easy-50 | profiler fixed/capped 15 | 9.79 tok/s / 1116.31 MiB / 72% / 72.4653 | 12.63 / 670.39 MiB / 64% / 75.3895 | +2.84 tok/s | −445.92 MiB | −8 points on n=50; Qwen3.5 leads 58.8% vs 54.6% in the matched n=500 finalist check | **+2.9242 direct; 72.7895 vs 71.2324 when the n=500 proxy is substituted at fixed TPS/RSS** | adopt as risk-adjusted choice; exact hash `c96df4ef…d5d7b` |
| 2026-08-20 | Qwen3-1.7B Q4_0 → Qwen3-0.6B Math-Expert Q4_K_M | same | profiler fixed/capped 15 | 9.79 tok/s / 1116.31 MiB / 72% / 72.4653 | 12.72 / 540.32 MiB / 68% / 77.9324 | +2.93 tok/s | −575.99 MiB | −4 points on profiler n=50; 54.6% on the matched n=500 check | **+5.4671 direct** | retain as exact-profiler proxy leader, not broad-quality winner |
| 2026-08-20 | final Qwen3.5 0.8B: scalar participant → portable AVX2/FMA/F16C | b10175 GCP 2C/4T; direct scalar report vs five-sample controlled AVX2 screen; source/final tensors byte-verified identical | profiler fixed/capped 15 | 12.63 tok/s / 670.39 MiB direct / 64% / 75.3895 | 27.1509 / 928.1 MiB estimated / 64% / 79.4104 | +14.5209 tok/s | +257.71 MiB | 0 | **+4.0209** | retain as AVX2 finalist; exact metadata-wrapped file still needs a direct AVX2 rerun |
| 2026-08-20 | Math-Expert Q4_K_M: scalar participant → portable AVX2/FMA/F16C | same binary, host and workload; exact GGUF in both lanes | profiler fixed/capped 15 | 12.72 tok/s / 540.32 MiB direct / 68% / 77.9324 | 39.2320 / 759.7 MiB estimated / 68% / 81.8803 | +26.5120 tok/s | +219.38 MiB | 0 | **+3.9479** | highest current ARC-Easy-50 AVX2 proxy total |
| 2026-08-20 | AVX2 finalist selection: ARC-Easy-50 → matched ARC-Easy-500 | same AVX2 TPS/RSS; accuracy sample only | profiler fixed/capped 15 | Math-Expert 81.8803 vs Qwen 79.4104 | Qwen 76.8104 vs Math-Expert 75.1803 | 0 | 0 | Qwen 58.8% vs Math-Expert 54.6% | ordering reverses | keep both decisions explicit; Qwen remains risk-adjusted recommendation |
| 2026-08-20 | Math-Expert Q4_K_M → pure Q4_0 / pure Q5_0 / Q4_K_S / IQ4_XS | pinned F16 source, pinned b10360 quantizer; one three-repetition scalar and AVX2 screen; ARC-Easy-50 | profiler fixed/capped 15 | screen: 11.93 tok/s / 556.7 MiB est. / 68% / 76.3058 | Q4_0 22.79/503.9/52/74.5940; Q5_0 3.97/574.9/70/61.3336; Q4_K_S 12.99/544.1/60/74.4696; IQ4_XS 7.64/530.6/62/64.8083 | quant-dependent | −53 to +18 MiB | −16 / +2 / −8 / −6 points | all negative | reject; reasoning quality and scalar kernel path dominate file size |
| 2026-08-20 | pure Q4_0 → Q4_0 body with Q6_K or Q8_0 tied embedding | same | profiler fixed/capped 15 | 22.79 tok/s / 503.9 MiB est. / 52% / 74.5940 | Q6_K: 17.93/542.4/50/73.4866; Q8_0: 19.47/578.2/50/73.3867 | −4.86 / −3.32 tok/s | +38.5 / +74.3 MiB | −2 points | negative | reject; embedding precision does not recover body degradation |
| 2026-08-20 | pure Q4_0 → Q5_0 in blocks 24–27 plus Q8_0 embedding | same | profiler fixed/capped 15 | 22.79 tok/s / 503.9 MiB est. / 52% / 74.5940 | 13.59 / 585.5 MiB / 56% / 73.5542 | −9.20 tok/s | +81.6 MiB | +4 points | **−1.0398** | reject; four higher-precision final blocks are insufficient |
| 2026-08-20 | pinned Qwen3.5-0.8B Q4_0 → final embedded tutor template | direct participant profiler plus four-prompt llama-server battery; tensors unchanged | profiler fixed/capped 15 | 12.69 tok/s / 670.65 MiB / 64% / 75.5088; caller must disable thinking | 12.63 / 670.39 MiB / 64% / 75.3895; no hidden reasoning with no caller setting | −0.06 tok/s (repeat noise) | −0.26 MiB | 0 on profiler; live proof prompt still fails | −0.1193 measured rerun | adopt for interactive reliability; no score gain claimed |

## Why the ordering is what it is

Zero-RAM-cost speedups (n-gram / prompt-lookup speculation, prompt caching) are **strictly
dominant** — they buy `S_perf` without paying `S_eff`, so no break-even calculation is needed
and they cannot lose. They are Phase 1 (17 Jul), before anything that spends RAM.

Everything that costs RAM is a trade and needs the break-even check. A 1 GB draft model must
return ≥ 1.43 tok/s (at `TPS_max=15`) or it is net-negative — `score.py`'s
`exchange.is_worth_it(delta_tps, delta_ram_gb)` answers this directly.

## A caution on what to optimize

Per [`docs/rules-digest.md`](../docs/rules-digest.md), the official profiler measures
throughput by running **`llama-bench` against the GGUF** — it never invokes our product. So
**orchestration overhead does not cost `S_perf`**, and shaving it wins zero points here (it is
still worth doing for felt latency — log it, but score it honestly as 0). Optimizations that
move the scored number are the ones touching the **model, quantization, KV cache, threads and
engine flags**.

## Autonomous runs (`make profile`)

Appended automatically, one row per run. Two paths because they fail differently: the profiler
path is the number the audit reproduces; the product path is where an OOM kill — a
disqualification, not a deduction — would show up. Rows marked `dev_host_provisional` came
from the ARM dev box and are **not report-grade** (CLAUDE.md: benchmark numbers come from the
x86 target box).

Accuracy is held at an assumed constant (`ASSUMED_ACCURACY` in [`autotest.py`](autotest.py)),
so only the `S_perf` and `S_eff` movement in these rows is meaningful. `tps_max` is the
provisional 15.0; every row is rescorable from `bench/.artifacts/runs.jsonl` once the cohort
value is known.

| date | git sha | host | prof tok/s | prof RAM GB | prof S_total | prod tok/s | prod RAM GB | prod S_total |
|---|---|---|---|---|---|---|---|---|
| 2026-07-20 | 1f1244f9212033b8dafa7fdd2f1d147160cded45-dirty | dev_host_provisional | 18.1 | 0.58 | 73.4 | 18.1 | 0.52 | 73.5 |
