# Technical Report — Muta Tutor: an offline maths & science tutor for the 8 GB classroom laptop

> **19 August 2026 provenance correction.** An old repository entry claimed that organisers
> privately confirmed a physical AVX2 audit and uncapped cohort-relative score on 6 August.
> No source for that claim exists in the repository or online. The public challenge page and
> official profiler conflict; this report follows the executable profiler: secure cloud-VM
> audit mode and `min(TPS/15, 1)·100`. AVX2 results are deployment evidence only.

## Current result — 20 August overnight campaign

The overnight search tested nine additional model artifacts and eight Math-Expert quantization
layouts. Two sub-1B models passed the staged screen. Their direct participant-profiler and
controlled portable AVX2 results select different models depending on the accuracy sample.

| Exact finalist | Direct scalar total, ARC-Easy-50 | AVX2 pp512 / tg128 | Est. AVX2 profiler RSS | AVX2 total, ARC-Easy-50 | AVX2 diagnostic, ARC-Easy-500 |
|---|---:|---:|---:|---:|---:|
| **Qwen3 0.6B Math-Expert Q4_K_M** `7f64c2…ae9a1` | **77.9324** | **153.9351 / 39.2320** | **759.7 MiB** | **81.8803** | 75.1803 |
| **Muta Tutor Qwen3.5 0.8B Q4_0 final** `c96df4…d5d7b` | 75.3895 | 98.0094 / 27.1509 | 928.1 MiB | 79.4104 | **76.8104** |

Both AVX2 decode results exceed 15 tok/s, so both receive `S_perf = 100` under the executable
formula. With ARC-Easy-50, Math-Expert leads by 2.4699 total points. With the matched 500-item
ARC-Easy estimates, Qwen leads by 1.6301 points. The 500-item values are diagnostics, not direct
participant-profiler scores.

The controlled AVX2 ledger now contains seven artifacts across the 19 and 20 August campaigns:

| AVX2 rank | Artifact | AVX2 tg128 | Est. profiler RSS | ARC-Easy-50 | Fixed-15 total |
|---:|---|---:|---:|---:|---:|
| 1 | **Math-Expert 0.6B Q4_K_M** | **39.2320** | **759.7 MiB** | 68% | **81.8803** |
| 2 | Qwen3 1.7B Q4_K_M tied | 15.6714 | 1,989.7 MiB | 72% | 80.4484 |
| 3 | Muta Tutor Qwen3 1.7B Q4_0 tied | 16.8927 | 2,049.4 MiB | 72% | 80.2818 |
| 4 | Qwen3 1.7B IQ4_XS tied | 14.0644 | 1,082.3 MiB | 70% | 80.1089 |
| 5 | Qwen3 1.7B Q5_K_M tied | 12.7191 | 1,364.6 MiB | 76% | 79.6307 |
| 6 | Muta Tutor Qwen3.5 0.8B Q4_0 final | 27.1509 | 928.1 MiB | 64% | 79.4104 |
| 7 | BitCPM4 8B TQ2_0 envocab | 7.4876 | 2,316.4 MiB | 88% | 72.5121 |

All AVX2 rows use llama.cpp b10175 commit `60bccc…f70` and binary SHA-256 `4abfa11a…12fd8`
with AVX/AVX2/FMA/F16C enabled, native tuning and AVX-512 disabled, `p512/tg128`, two physical
cores and five internal samples. AVX2 RSS is measured child-tree peak plus a 45 MiB profiler-root
estimate. The final Qwen AVX2 measurement comes from its pinned Q4_0 source; an independent
comparison verified all 320 tensors and 496,192,768 tensor bytes as identical to the final
metadata-wrapped file. The final file itself completed the direct scalar participant run.

The current recommendation remains
`Muta-Tutor-Qwen3.5-0.8B-Q4_0-final.gguf` because Qwen leads the larger matched ARC-Easy,
ARC-Challenge and SciQ checks. Math-Expert is the raw fixed-15 alternative and should replace Qwen
if a physical-target, tutoring-aware evaluation confirms the ARC-Easy-50 ordering. Current data do
not justify describing either model as an unconditional winner.

## Corrected 19 August decision (historical)

The seven-hour campaign keeps three non-blended evidence lanes: direct bundled-profiler reports,
broader no-AVX b10175 promotion screens scored at the profiler's fixed 15 tok/s cap, and separately
labelled AVX2 product rows. Exact reports, timing vectors, task intervals and hashes live in
`bench/measurements/campaign-20260819/`; unlike the earlier decision, no score averages the two
public rule interpretations.

In the full profiler reports, the shipped Muta Tutor Q4_0 tied-head file remains the winner:
9.79 tok/s, 1116.31 MiB directly measured profiler peak RSS, 72% ARC-Easy-50 and a 72.4653
composite. The Qwen3.5-0.8B hedge is close at 71.5416 (9.74 tok/s, 694.73 MiB, 68%); its
421.58 MiB saving almost repays the four-point accuracy gap, but historical maths/tutoring gates
remain below the product bar. BitCPM4-8B scores 59.1843 despite 88% Easy because scalar TQ2_0
decode is 0.81 tok/s; Qwen3.5-4B IQ4_XS scores 52.9293. Thermal is unknown on GCP and the
accuracy term is a small diagnostic proxy, not a claim about the hidden panel.

The AVX2/webpage-relative panel is still preserved. Treating each scenario as a pre-entry cohort
floor and using `max(floor, candidate TPS)` as the effective denominator, it selects Q3_K_M at
15, Q4_K_S at 30, Q5_K_M at 45, and BitCPM4-8B at 60/100/150. That alternative is useful if
the webpage, rather than the published profiler image, turns out to govern the final audit.

## 19 August AVX2/FMA/F16C CPU benchmark regime

The 19 August campaign reran five score-of-record artifacts on the same GCP 2C/4T proxy to isolate one
variable: portable x86 SIMD. The original scalar binary remains untouched and reproducible at
SHA-256 `7f01dc0465d64f726b2b66139859a8ff1ca204f4901e18b71ddfa678dea19370`.
The new binary is a separate deterministic build at
`4abfa11a3f86b8c5e4d508cce10daf8f381c968585a3e5961fea3d5cbe312fd8`, from the same llama.cpp
b10175 commit `60bccc3763395e01b039aa1ddeacc8cc0ea69f70`, CMake 3.22.1 and GNU 11.4.0.

The VM exposes AVX, AVX2, FMA and F16C. Configuration was explicit: `GGML_NATIVE=OFF`,
`GGML_AVX=ON`, `GGML_AVX2=ON`, `GGML_FMA=ON`, `GGML_F16C=ON`, with `GGML_AVX512=OFF`,
`GGML_AVX512_VBMI=OFF` and `GGML_AVX512_VNNI=OFF`. GGML's runtime trace reports
`AVX=1 | AVX2=1 | F16C=1 | FMA=1`; the scalar trace reports none of them. The backend archive
and llama-bench reproduce an independent AVX2 build byte-for-byte, and a disassembly scan found
zero ZMM/opmask or selected AVX-512 signatures. The full CMake cache, CPU flags, compiler output,
feature traces and build logs are retained with the result.

Every artifact hash matched the scalar record. Each AVX2 invocation used the unchanged workload:

```text
llama-bench -m MODEL -p 512 -n 128 -o json -ngl 0 -r 5
```

No thread override was supplied; llama-bench selected the two physical cores. The same 100 ms
child-tree RSS sampler and 45 MiB profiler-root estimate were used. ARC-Easy was reused by exact
GGUF hash because the weights did not change. All AVX2 rows contain five internal timing samples;
the scalar incumbent also has five, while the four retained scalar challenger rows remain clearly
labelled one-repetition promotion screens.

| Artifact | Scalar pp512 / tg128 | AVX2 pp512 / tg128 ± decode sd | Decode speedup | Scalar → AVX2 est. RSS | ARC-Easy | Scalar → AVX2 S_total |
|---|---:|---:|---:|---:|---:|---:|
| Muta Tutor Qwen3-1.7B Q4_0 tied `a98ce3…` | 14.7166 / 9.9869 | 47.0716 / 16.8927 ± 0.1642 | **1.691×** | 1133.1 → 2049.4 MiB | 72% | **72.8122 → 80.2818** |
| **Qwen3-1.7B Q4_K_M tied `e8a413…`** | 7.1859 / 5.2954 | **55.4554 / 15.6714 ± 1.2364** | **2.959×** | 1183.5 → 1989.7 MiB | 72% | **63.2887 → 80.4484** |
| Qwen3-1.7B Q5_K_M tied `17ddf7…` | 6.5613 / 4.7839 | 24.3231 / 12.7191 ± 0.0784 | 2.659× | 1364.5 → 1364.6 MiB | 76% | 63.7606 → 79.6307 |
| Qwen3-1.7B IQ4_XS tied `aea3cb…` | 3.2063 / 2.4961 | 23.9364 / 14.0644 ± 0.0942 | 5.635× | 1081.8 → 1082.3 MiB | 70% | 56.9738 → 80.1089 |
| BitCPM4-8B TQ2_0 envocab `069621…` | 0.8762 / 0.8108 | 13.6569 / 7.4876 ± 0.0562 | **9.235×** | 2316.3 → 2316.4 MiB | 88% | 59.1587 → 72.5121 |

Within the 19 August set, the scalar winner is Muta Tutor pure Q4_0 tied and the AVX2 winner is
Q4_K_M tied: both
Q4 variants clear the 15 tok/s performance cap, and Q4_K_M's estimated RSS is 59.7 MiB lower,
producing a 0.1666-point lead. That is not a robust promotion margin: Q4_K_M has one 13.6101
tok/s internal outlier and substantially higher decode variance. IQ4_XS is only 0.3395 points
behind the nominal winner with essentially no repacking-RSS increase.

BitCPM's old 0.8108 tok/s result was primarily a scalar-kernel failure: AVX2 makes it 9.235×
faster and operationally viable. The conclusion still does not flip under the capped score. At
7.49 tok/s and about 2.26 GiB estimated profiler RSS, its 88% Easy proxy reaches 72.5121—7.94
points behind Q4_K_M. It remains the accuracy experiment, not the capped-15 submission winner.

This 19 August result was superseded by the 20 August candidate extension above. At the time, the
executable-profiler submission stayed Muta Tutor pure Q4_0 tied. If the final audit
instead supplies a portable AVX2 build, optimization direction changes toward Q4_K_M, with
IQ4_XS close enough to confirm on the physical target before switching. The GCP host exposes no
temperature sensor, so thermal is unknown and these are cloud-proxy, not physical-laptop, scores.
The complete evidence is in
`bench/measurements/campaign-20260819/avx2-score-of-record/`.

---

## Historical 17 August report (superseded where it conflicts with the correction above)

**Team ID:** team-muta  
**Domain:** math_scientific_reasoning  
**Model:** muta-tutor-qwen3-1.7b-q4_0 (Qwen3-1.7B, pure Q4_0, tied Q4_0 LM head, tutoring persona baked into the GGUF; 974,198,528 bytes, sha256 `a98ce36e9ff97e5271d90cbc429c952f99a5a966bb0195ae74661b4c054fd63e`)

---

## Problem

Secondary-school students across West and East Africa sit high-stakes exams (WASSCE, JAMB, NECO,
KCSE) with very few teachers per student and, outside the cities, unreliable connectivity and no
budget for cloud AI. What they increasingly do have is a shared, low-cost laptop in a classroom
or a community centre. Muta is a tutor that runs entirely on that machine: it solves and *explains*
maths and science problems step by step, diagnoses a student's misconception ("a heavier ball falls
faster because gravity pulls harder"), and speaks in the student's world (naira, cedis, shillings,
markets, farming, transport). Because it is a single GGUF file running through llama.cpp, one 8 GB
laptop can serve a whole class over the local network with no internet, no subscription and no data
leaving the room.

Target users: students aged ~14–19 and their teachers; the "shared-laptop classroom" is the
deployment we design for, so peak RAM and tokens per second decide how many students one machine
can serve at once.

---

## Design Decisions

We spent the first part of the challenge on the largest model that fits the budget (an 8 B ternary
BitCPM4 in TQ2_0, ~2.2 GB) and instrumented everything: the profiler's own source, kernel paths,
memory accounting, weight streaming, SVD low-rank compression, requantisation and vocabulary
pruning. Two facts from that work drove the final choice:

1. **The scored run is the audit's `llama-bench` on a 4-vCPU x86 VM with the profiler image's
   llama.cpp build (b10175, no AVX/AVX2/FMA/F16C).** On that binary only Q4_0 has a hand-written
   SIMD kernel; TQ2_0, every k-quant and every i-quant fall back to generic C and run 3–7× slower per
   byte. An 8 B ternary file that does 18 tok/s on a laptop does ~2 tok/s there. Only the GGUF file
   reaches that run, with no flags and no engine of ours, so the *file* has to be right for that
   binary.
2. **Accuracy is half the score and it is judged two ways**: an automated multiple-choice benchmark
   through llama-cpp-python (raw text, no template) and a live judge chat with the *bare* GGUF
   through stock llama-server (Jinja template on by default, no system prompt, sampling seeded from
   the file's `general.sampling.*` keys). So the tutoring behaviour must live in the file too.

**Base model — Qwen3-1.7B (Apache-2.0).** Chosen from a bake-off of nine candidates run under
profiler-identical conditions on our development machine (stock Homebrew llama-bench for tg/RSS, a
forced-generic-kernel build as the audit proxy, GSM8K-40 greedy with the tutoring persona, the
profiler's own arc_easy(50) path, and ten saved tutoring transcripts read by hand):

| candidate (all with our tutoring prompt) | file | GSM8K-40 | arc_easy(50) | note |
|---|---|---|---|---|
| BitCPM4-8B TQ2_0, CJK-pruned vocab | 2209 MB | 0.775 | 0.84 | best accuracy; ~2 tok/s on the audit build |
| BitCPM-CANN-3B / 1B TQ2_0 (pruned) | 992 / 468 MB | 0.225 / 0.250 | 0.62 / 0.60 | too weak for maths |
| MiniCPM5-1B (Q4_0) | 613–714 MB | 0.00–0.03 (template failure) | 0.48–0.52 | shipped Jinja template breaks both llama.cpp's and jinja2's renderers; fragile with system prompts |
| LFM2.5-1.2B-Instruct Q4_0 | 696 MB | 0.575 | 0.56 | fast, weak on multiple-choice; non-OSI licence |
| **Qwen3-1.7B, pure Q4_0, tied head** | 974 MB | 0.70 (0.60–0.65 with a longer draft persona) | 0.70 (0.74 before the head drop) | chosen |
| Qwen3-1.7B Q4_0 (bartowski, Q6_K head + Q4_1 layers) | 1232 MB | 0.65 | 0.72 | source file |

Qwen3-1.7B is the smallest model in the study that is *both* a solid multiple-choice reasoner and a
correct, readable tutor (its transcripts get the crate-profit problem, the falling-ball
misconception, titration and simple interest right and explain them in numbered steps).

**Quantisation — pure Q4_0, tied Q4_0 embedding/LM head (974 MB).** Every matrix is Q4_0 so 100%
of the token time runs the SSSE3 kernel on the audit build (the source GGUF's Q6_K head and three
imatrix-induced Q4_1 layers would have run scalar generic C for a quarter of the bytes). The model's
embedding and LM head are tied, so we drop the duplicated `output.weight` and let llama.cpp use the
Q4_0 embedding as the head: −255 MB of file and RSS, zero accuracy change (measured GSM8K/arc within
noise of the source file). Alternatives measured and rejected: Q4_K_M/IQ4_XS (generic kernels on
the audit build; a 1.5 B Q4_K_M runs ~3.5 tok/s there vs ~9–13 for Q4_0 files of this size, per our
own kernel analysis and other teams' published audit-build runs); Q8_0 (2× the bytes for a scalar
kernel); TQ1_0/TQ2_0 ternary (fast on ARM/AVX2, generic C on the audit box).

**Behaviour baked into the file.** The chat template is replaced by a clean ChatML template that
(a) injects the Muta tutoring persona as the system turn when the client sends none, or merges it in
front of a client-supplied system message, and (b) always opens the assistant turn with an empty
`<think></think>` block so the model answers directly instead of producing long reasoning traces
(a minute of silence per prompt at audit-box speed). `general.sampling.*` defaults are set to
temp 0.4, top_p 0.9, min_p 0.05, repeat_penalty 1.05 (honoured by llama-server); `general.name`
identifies the tutor. The persona is ~130 tokens so a judge's first turn pays little extra prefill.
Verified on both paths the judges can use: llama.cpp's own Jinja engine (the code llama-server
and llama-cli use; the shipped file was probed on a stock b10175 llama-server with zero flags:
persona injected, `chat template, thinking = 0`, `/props` sampling read from the file, both test
prompts answered correctly with `finish_reason: stop`) and llama-cpp-python's jinja2 path.

**Vocabulary pruning and streaming (from the 8 B track, kept for the classroom runtime).** For the
ternary model we built a byte-exact CJK vocabulary pruner (73,448 → 44,416 tokens, −164 MB, identical
English tokenisation and logits) and a residency-window streaming engine for llama.cpp that holds a
1.7–2.4 GB model at 0.3–1.6 GB of RSS (10.5–15.4 tok/s on an M1). Neither reaches the audit binary,
so neither is claimed in the scored numbers; both are documented in `opt/docs/` and power the
shared-laptop deployment.

**Alternatives considered and rejected with data:** SVD low-rank factor pairs (ternary matrices are
numerically full-rank; the proposed rank-2048 pair reconstructs at 0.80 relative error), TQ1_0
(−22% speed on generic C), disk-fed weight streaming (1.35 GB/s SSD → 1% of a model per token at
15 tok/s), layer pruning (accuracy is half the score).

---

## Constraints

- Target: 8 GB RAM, integrated GPU, Ubuntu 22.04, Intel i5 10th–12th gen / Ryzen 5 — pure CPU
  inference through llama.cpp; the audit binary has no AVX, so the GGUF quant type *is* the kernel
  choice.
- Peak RSS is what the profiler sums for the llama-bench process tree; on Linux llama.cpp
  `MAP_POPULATE`s the whole file, so file bytes ≈ RSS. Every 100 MB is 1.4 points of S_eff.
- Judges chat with the bare file: no application layer, no system prompt, default sampling → the
  persona, decoding mode and sampling defaults live in GGUF metadata.
- Offline and reproducible: `download_model.sh` fetches one public, sha256-pinned GGUF; the
  derivation from the Apache-2.0 base is scripted (`opt/scripts/`).
- Data: no student data leaves the machine; the tutor uses local currencies/examples in its
  persona rather than any personal data.
- Development machine is an Apple M1 (8 GB); all timing/RSS below are from it and are marked as
  such. The audit box will be slower (different ISA/kernels), and that is expected.

---

## Benchmarks

Self-reported development benchmarks (Apple M1, 8 GB, macOS 27; `adtc-profiler run --mode
participant`, i.e. `llama-bench -p 512 -n 128 -ngl 0`, 4 threads, plus the profiler's arc_easy).
`submission.json` was produced with a CPU-only llama.cpp b10360 build with weight repacking
disabled, the same behaviour as the audit image, so its RSS is comparable to the audit box. The
Homebrew ARM build's numbers are given in parentheses for reference (`opt/results/`).

| Metric | Value |
|---|---|
| Machine | MacBook Air M1 (4P+4E), 8 GB, macOS 27.0 |
| Model file | 974 MB (Q4_0 pure, tied head), 1.72 B parameters |
| RAM at peak (profiler process tree) | 1133 MB (llama.cpp CPU build with weight repacking off, the audit image's behaviour); 2029 MB with Homebrew's ARM build, which additionally copies the Q4_0 weights into a repacked buffer |
| Time to first token (512-token prompt) | 3810 ms (2232 ms with the Homebrew build's BLAS prompt path) |
| Generation speed | 43.4 tok/s in the final `submission.json` (51.2 tok/s in an earlier run of the same file, recorded in the repo's RESULTS.md, and 52.2 with the Homebrew build; the final run overlapped a background upload) |
| arc_easy (50, profiler's own path) | 0.70 acc_norm |
| GSM8K-40 (greedy, baked persona, no-think, shipped file) | **0.70 (28/40)**, ~170 generated tokens per answer (`opt/eval/results/muta-tutor-ship.json`) |
| Thermal throttling | None observed (cpu p99 65%) |

Expected on the audit build (no-AVX x86, 4 vCPU): ~9–13 tok/s (Q4_0 SSSE3 kernel; other teams'
published audit-build runs give 9.4 tok/s for a ≈1.2 GB Q4_0 Qwen3-1.7B, ours is 21% smaller) and
~1.2 GB peak RSS. A ready-to-run GitHub-Actions workflow that reproduces the audit binary on a free
x86 runner is in `opt/audit-bench/`.

Official scores are measured by the ADTC profiler on the standard evaluation machine.

### Sample transcripts (bare GGUF, stock llama.cpp, no client system prompt)

**Prompt:** A trader buys 24 identical crates for 18000 naira and sells them at a 25% profit. What is the selling price of one crate? Show your working.

> Let's solve this step by step.
> 
> **Step 1: Find the cost price of one crate**
> 
> The trader buys 24 crates for 18000 naira.
> 
> So, the cost price of one crate is:
> 
> $$
> \text{Cost per crate} = \frac{18000}{24}
> $$
> 
> $$
> \text{Cost per crate} = 750 \text{ naira}
> $$
> 
> **Step 2: Calculate the selling price with 25% profit**
> 
> A 25% profit means the selling price is 125% of the cost price.
> 
> $$
> \text{Selling price per crate} = 750 \times 1.25
> $$
> 
> $$
> \text{Selling price per crate} = 937.5 \text{ naira}
> $$
> 
> **Step 3: Final answer**
> 
> The selling price of one crate is:
> 
> $$
> \boxed{937.5} \text{ naira}
> $$
> 
> **Takeaway:** The selling price of one crate is 937.5 naira, which is 125% of the cost price.

**Prompt:** I think 1/2 + 1/3 = 2/5. Where did I go wrong?

> You made a mistake in adding the fractions. To add fractions, they must have the same denominator. Let's go step by step:
> 
> 1. Find the least common denominator (LCD) of 2 and 3. The LCD is 6.
> 2. Convert 1/2 to 3/6 (since 1 × 3 = 3 and 2 × 3 = 6).
> 3. Convert 1/3 to 2/6 (since 1 × 2 = 2 and 3 × 2 = 6).
> 4. Add the numerators: 3 + 2 = 5.
> 5. So, 1/2 + 1/3 = 5/6.
> 
> **Takeaway:** To add fractions, they must have the same denominator. Multiply numerator and denominator of each fraction by the same number to get the same denominator. Then add the numerators.

**Prompt:** Solve x^2 - 5x + 6 = 0 and show me how to check that the answers are right.

> Let's solve the quadratic equation $ x^2 - 5x + 6 = 0 $ step by step.
> 
> ---
> 
> ### **Step 1: Factor the quadratic**
> 
> We look for two numbers that multiply to 6 (the constant term) and add to -5 (the coefficient of $ x $).
> 
> - The numbers are **-2** and **-3**.
> 
> So, the equation factors as:
> $$
> x^2 - 5x + 6 = (x - 2)(x - 3)
> $$
> 
> ---
> 
> ### **Step 2: Solve the equation**
> 
> Set the factored form equal to zero:
> $$
> (x - 2)(x - 3) = 0
> $$
> 
> This means:
> $$
> x - 2 = 0 \quad \text{or} \quad x - 3 = 0
> $$
> 
> So, the solutions are:
> $$
> x = 2 \quad \text{and} \quad x = 3
> $$
> 
> ---
> 
> ### **Step 3: Check the answers**
> 
> Let's substitute each solution back into the original equation to verify.
> 
> #### For $ x = 2 $:
> $$
> (2)^2 - 5(2) + 6 = 4 - 10 + 6 = 0
> $$
> 
> #### For $ x = 3 $:
> $$
> (3)^2 - 5(3) + 6 = 9 - 15 + 6 = 0
> $$
> 
> Both values satisfy the equation.
> 
> ---
> 
> ### **Takeaway:**
> The solutions are correct. The equation $ x^2 - 5x + 6 = 0 $ has roots at $ x = 2 $ and $ x = 3 $.

---

## Reproducibility

- Model file: `model/muta-tutor-qwen3-1.7b-q4_0.gguf`, 974,198,528 bytes, sha256
  `a98ce36e9ff97e5271d90cbc429c952f99a5a966bb0195ae74661b4c054fd63e` (pinned in `download_model.sh`).
- Derivation (all scripts in `opt/scripts/`): bartowski `Qwen_Qwen3-1.7B-Q4_0.gguf` →
  `llama-quantize --allow-requantize --pure --output-tensor-type q4_0 --token-embedding-type q4_0 … Q4_0`
  → `drop_tensor.py … output.weight` → `bake_system_prompt.py --replace-chatml off --set-name … --sampling temp=0.4,top_p=0.9,min_p=0.05,penalty_repeat=1.05` (persona text in `opt/eval/system_prompt.txt`).
- Numbers: `adtc-profiler run --submission . --mode participant --output submission.json` (Apple M1,
  llama.cpp CPU build with repack off first on PATH); bake-off table `opt/results/bakeoff.tsv`;
  transcripts `opt/eval/results/muta-tutor-final2.json`, GSM8K-40 `opt/eval/results/muta-tutor-ship.json`.
- Licences: Qwen3-1.7B — Apache-2.0 (Alibaba); the derived GGUF and our scripts are released under
  the same terms; bartowski's GGUF conversion is credited as the source file.

## Tools used and why

- **llama.cpp** (b10360 for our builds; the profiler pins b10175) — the only permitted runtime; we
  read its kernel/quant sources to choose Q4_0 and its template engine to bake behaviour.
- **gguf-py** — byte-exact GGUF surgery (vocab pruning, tensor drop, metadata/template rewrite).
- **llama-cpp-python + lm-eval** — the profiler's own accuracy path, used unchanged for arc_easy;
  our GSM8K harness uses the same library so numbers are comparable.
- **adtc-profiler 0.1.0** — every reported number comes from the official tool.
- Base weights: Qwen/Qwen3-1.7B (Apache-2.0) via bartowski's GGUF conversion; BitCPM-CANN
  (openbmb, Apache-2.0) for the ternary track. All cited in `opt/docs/`.

## African use case

`african_alpha_claim: true` in `metadata.json` is a use-case claim (Devpost/template: "true only if
claiming the African Use Case Bonus"), not an African-language claim: `language_scope` is `["en"]`
and the model is evaluated in English. Muta is built for the shared-laptop classroom: one 8 GB
machine, ~30 students on phones over the local network, no internet. The persona teaches in the exam
formats students actually sit (WASSCE/JAMB/KCSE), uses local currencies and contexts, and diagnoses
misconceptions rather than just answering. Those are the behaviours a scarce teacher cannot give
thirty students at once. The streaming
runtime in `opt/` exists so that the same file also fits beside a browser and a classroom server on
that laptop.

---

## 20 August 2026 model search and current submission recommendation

This section supersedes the earlier model choice above. The earlier experiments remain as a record
of the path to the current result.

### Measurement boundary

The search ran on the GCP `n2-custom-4-8192` proxy: 2 physical cores, 4 threads, 8 GB RAM and no
swap. It is not the physical target laptop and exposes no package-temperature sensor. Two b10175
binaries were retained:

- executable-profiler configuration: scalar x86 binary SHA-256 `7f01dc04…9370`;
- controlled portable configuration: AVX/AVX2/FMA/F16C enabled, native and AVX-512 disabled,
  binary SHA-256 `4abfa11a…2fd8`.

Every promoted result records the exact GGUF SHA-256, binary SHA-256, model revision, command,
sample count and raw output. The executable-profiler score uses
`S_perf = 100 × min(TPS / 15, 1)`. Cohort-relative results are reported separately and are not
averaged with it.

### Model screen

Nine new artifacts were tested. Staged screening used the same scalar and AVX2 binaries before the
slow participant-profiler run. The table shows the scalar generation result because that binary
matches the executable profiler.

| Candidate | Scalar tg128, tok/s | ARC-Easy-50 | Decision |
|---|---:|---:|---|
| OpenMath-Nemotron 1.5B Q4_0 | 11.25 | 44% | reject: low accuracy |
| Noema 2B Q4_K_M | 4.45 | 74% | reject: low scalar throughput |
| Noema 2B pure Q4_0 | 8.89 | 70% | reject: lower combined result |
| Qwen3.5 0.8B Opus reasoning distill Q4_K_M | 9.86 | 64% | reject: slower and weaker provenance |
| Qwen3 0.6B Math-Expert Q4_K_M | 12.63 | 68% | promote |
| Qwen2 0.5B NuminaMath Q4_K_M | 7.54 | 54% | reject |
| Qwen3.5 2B Q4_0 | 6.23 | 70% | reject: low scalar throughput |
| VibeThinker 1.5B Q4_K_M | 5.68 | 36% | reject |
| Gemma 3 1B Q4_0 | 12.75 | 58% staged accuracy | reject |

The retained general-model control was Qwen3.5 0.8B Q4_0. Its final participant-profiler run is
reported below.

### Math-Expert quantization sweep

Eight layouts were derived from one pinned F16 source. This isolates quantization from model and
training differences.

| Layout | Scalar tg128 | AVX2 tg128 | ARC-Easy-50 | Decision |
|---|---:|---:|---:|---|
| pure Q4_0 | 22.79 | 43.31 | 52% | reject: 16-point loss |
| pure Q5_0 | 3.97 | 28.61 | 70% | reject: scalar kernel cost |
| Q4_K_S | 12.99 | 39.28 | 60% | reject |
| **Q4_K_M** | **11.93** | **39.73** | **68%** | **retain** |
| IQ4_XS | 7.64 | 35.65 | 62% | reject |
| Q4_0 body + Q6_K tied embedding | 17.93 | 40.05 | 50% | reject |
| Q4_0 body + Q8_0 tied embedding | 19.47 | 38.10 | 50% | reject |
| Q4_0 body + Q5_0 final four blocks + Q8_0 embedding | 13.59 | — | 56% | reject |

The mixed layouts show that the loss is distributed through the quantized body. Raising the tied
embedding or the final four blocks does not recover enough accuracy. Q4_K_M remains the best tested
Math-Expert layout.

### Direct participant-profiler results

| Exact artifact | Generation | Peak RSS | ARC-Easy-50 | Fixed-15 total |
|---|---:|---:|---:|---:|
| **Qwen3 0.6B Math-Expert Q4_K_M** `7f64c2…ae9a1` | **12.72 tok/s** | **540.32 MiB** | **68%** | **77.9324** |
| Muta Tutor Qwen3.5 0.8B Q4_0 final `c96df4…d5d7b` | 12.63 tok/s | 670.39 MiB | 64% | 75.3895 |

Math-Expert wins the executable profiler's 50-item ARC-Easy slice by 2.5429 total points. The 95%
Wilson intervals are wide: 54.2–79.2% for Math-Expert and 50.1–75.9% for Qwen. The difference is
not a reliable estimate of general task quality.

### Controlled AVX2/FMA/F16C finalist results

The same b10175 AVX2 binary used for the 19 August campaign measured both finalist weight sets.
AVX, AVX2, FMA and F16C were enabled; native tuning and AVX-512 were disabled. The score below
uses the executable profiler's 15 tok/s cap.

| Exact artifact | AVX2 pp512 | AVX2 tg128 | Est. profiler RSS | ARC-Easy-50 | Fixed-15 total |
|---|---:|---:|---:|---:|---:|
| **Qwen3 0.6B Math-Expert Q4_K_M** | **153.9351** | **39.2320** | **759.7 MiB** | **68%** | **81.8803** |
| Muta Tutor Qwen3.5 0.8B Q4_0 final | 98.0094 | 27.1509 | 928.1 MiB | 64% | 79.4104 |

Math-Expert leads by 2.4699 points. Both models saturate `S_perf`; Math-Expert retains four more
ARC-Easy-50 points and uses 168.4 MiB less estimated profiler RSS. RSS combines measured
child-tree peaks of 714.7 and 883.1 MiB with a 45 MiB profiler-root estimate.

The Math-Expert row uses the exact submitted GGUF. The Qwen benchmark used the pinned source
`Qwen3.5-0.8B-Q4_0.gguf`; raw tensor comparison verified that its 320 tensors and 496,192,768
tensor bytes are identical to `Muta-Tutor-Qwen3.5-0.8B-Q4_0-final.gguf`. The metadata-wrapped
final file still requires an exact-file AVX2 rerun for complete procedural parity.

Replacing ARC-Easy-50 with the matched ARC-Easy-500 values gives **76.8104 for Qwen** and
**75.1803 for Math-Expert** under the same fixed-15 AVX2 performance and RSS measurements. This is
a larger-sample diagnostic, not an official profiler score.

### Larger matched checks

| Task | Samples | Muta Tutor Qwen3.5 0.8B | Math-Expert 0.6B |
|---|---:|---:|---:|
| ARC-Easy | 500 | **58.8%** (54.4–63.0) | 54.6% (50.2–58.9) |
| ARC-Challenge | 50 | **32%** | 30% |
| SciQ | 50 | **92%** | 88% |
| GSM8K strict | 10 | 30% | 30% |

Substituting the 500-item ARC-Easy estimates while keeping each model's directly measured
throughput and RSS gives a diagnostic fixed-15 total of **72.7895 for Qwen** and **71.2324 for
Math-Expert**. This is not an official profiler score. It is the reason Qwen is the lower-risk
choice: it leads every larger matched check except the tied GSM8K sample.

### Cohort-relative sensitivity

The public-page formula was also retained. The table uses the AVX2 generation results, the larger
ARC-Easy estimates, and `max(pre-entry floor, candidate TPS)` as the effective denominator so no
candidate receives performance above 100.

| Pre-entry TPS floor | Qwen3.5 0.8B total | Math-Expert total | Higher result |
|---:|---:|---:|---|
| 15 | **76.8104** | 75.1803 | Qwen |
| 30 | 73.9613 | **75.1803** | Math-Expert |
| 45 | 64.9110 | **71.3350** | Math-Expert |
| 60 | 60.3859 | **64.7963** | Math-Expert |
| 100 | 54.9557 | **56.9499** | Math-Expert |
| 150 | 52.2406 | **53.0267** | Math-Expert |

These rows are sensitivity analysis. The cohort maximum and physical-laptop results are unknown.

### Embedded template and live acceptance test

The final Qwen file is tensor-identical to the pinned Q4_0 source. GGUF metadata adds the tutor
policy, English language tag, sampling defaults and a ChatML template that forces non-thinking
responses. The final file was rerun through the participant profiler after this rewrite.

A deterministic four-prompt battery tested a profit calculation, fraction misconception, thermal
energy calculation and proof that √2 is irrational. With unrestricted thinking, both finalists
used the 256-token allowance on hidden reasoning and returned no usable answer. Disabling thinking
produced direct answers. Both models still failed the proof prompt, and some Qwen answers reached
the 256-token limit. This is a recorded quality limitation, not a pass.

### Submission decision

The current recommendation is:

`Muta-Tutor-Qwen3.5-0.8B-Q4_0-final.gguf`

- size: 507,156,160 bytes;
- SHA-256: `c96df4ef6d9416bea6a35866751cb6cf02e20ec6ce28b20980d66c90604d5d7b`;
- source revision: `unsloth/Qwen3.5-0.8B-GGUF@6ab461498e2023f6e3c1baea90a8f0fe38ab64d0`;
- source SHA-256: `444406ddd926550c724ec18d5120a9d40ded44908a063b0e66e9a7e5464c652c`;
- transformation: metadata and chat-template rewrite only; no tensor change.

Keep `Qwen3-0.6B-Math-Expert.Q4_K_M.gguf` as the alternative if the objective is restricted to the
current executable profiler's 50 ARC-Easy items. The broader evidence does not support replacing
Qwen with Math-Expert. Neither result guarantees a hidden-panel win or measures thermal behaviour
on the physical laptop.

The complete manifest, raw rows, direct profiler reports, live responses, generator and summary
are in `bench/measurements/campaign-20260820-overnight/`.
