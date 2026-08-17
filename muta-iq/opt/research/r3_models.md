# R3 — Small-model landscape for a CPU math/science tutor (0.5B–4B, GGUF + llama.cpp)

**Date:** 2026-08-17 · **Author:** research agent (team-muta) · **Scope:** every ≤4B (plus the asked-for 8B references)
open-weight chat/instruct model worth considering for the ADTC 2026 Laptop-LLM track, domain `math_scientific_reasoning`,
scored as `0.5·S_acc + 0.3·S_perf + 0.2·S_eff − thermal`, audited with the profiler image's **stock llama.cpp b10175 built with
GGML_AVX/AVX2/FMA/F16C=OFF** on a 4-vCPU / 8 GB x86 VM (`docker --memory=7.5g`), where **only the GGUF file** reaches the audit.

Everything marked **[V]** was read today from the primary source given (HF model card / config.json / GGUF tree / arXiv text /
GitHub); **[I]** = inference/estimate by me; **[M]** = recalled from memory and not re-verified today (kept to a minimum and
flagged). Companion documents this leans on: `opt/research/r4_x86_kernels.md` (which kernels the audit binary runs — Q4_0 has the
only hand-written SSSE3 path; TQ2_0/K-quants/IQ run generic C) and `opt/results/audit_kernel_proxy.md` (measured 2.40 GB/s per
core on generic-C TQ2_0, M1 proxy).

---

## 0. TL;DR

1. **The scoring formula punishes bytes-per-token twice** (S_perf via tok/s, S_eff via RSS = whole file under `MAP_POPULATE`), and on
   the audit binary only **Q4_0** weights get a SIMD kernel. Under the R4 speed model a ~1B dense model at Q4_0 (0.45–0.7 GB
   streamed/token) saturates S_perf (≥15 tok/s ⇒ 100) and scores S_eff ≈ 88–90; a 4B at Q4_0 (2.3–2.6 GB) gets S_perf ≈ 35–45 and
   S_eff ≈ 60; the current BitCPM-CANN-8B TQ2_0 (2.2 GB on generic C) gets S_perf ≈ 9–18 and S_eff ≈ 66. **Perf+eff spread between
   a 1B and a 4B ≈ 23 points of total score, ≈ 30 points vs the 8B ternary — S_acc would have to differ by 46–60 points to overturn
   it.** [I, formula from profiler README quoted in R4 §1.2: `S_perf = min(TPS/15,1)·100`; `S_eff = (1 − RSS/7 GB)·100` per R4 §8.]
2. **2026 changed the ≤2B tier completely.** MiniCPM5-1B (2026-05-19, Apache-2.0, plain Llama arch, MATH-500 91.6 / AIME25 40.4 in
   thinking mode, MMLU-Pro 48.9), LFM2.5-1.2B-Thinking (2026-01, MATH-500 88–89, GSM8K 85.6, IFEval 88.4), Qwen3.5-2B (2026-03-02,
   MMLU-Pro 66.5 thinking, GPQA 51.6, MMMLU 63.1, 201 languages) and Qwen3-1.7B (MATH-500 93.4 thinking) all beat the ternary
   BitCPM-CANN-1B/3B (GSM8K 61.6 / 79.5, no MATH-500 published, no thinking) on accuracy **at equal or fewer streamed bytes** — and
   they run the fast Q4_0 kernel instead of generic-C TQ2_0.
3. **Best accuracy per class (English math/science):** ≤1B → **MiniCPM5-1B**; 1–2B → **Qwen3.5-2B** (knowledge/multilingual) or
   **Qwen3-1.7B** (pure transformer, MATH-500 93.4); 2–3B → **LFM2.5-2.6B** (2026-08-04; AIME25 51.9) / SmolLM3-3B / Granite-4.1-3B;
   4B → **Qwen3.5-4B** (MMLU-Pro 79.1, GPQA 76.2, HMMT-Feb25 74.0, MMMLU 76.1) ≥ Qwen3-4B-Thinking-2507 ≥ Phi-4-mini-reasoning
   (MATH-500 94.6, English-only).
4. **African languages:** the only published head-to-head at ≤4B is AfriqueLLM (arXiv 2601.06395, Jan 2026): base **Qwen3.5-4B**
   averages **AfriMGSM 22.4 / AfriMMLU 40.4** vs Qwen3-4B 14.8 / 39.2, Gemma-3-4B 10.6 / 37.6, Llama-3.1-8B 10.9 / 38.8 [V]. Nothing
   ≤2B has published Afri* numbers; every non-Qwen/Gemma candidate here lists no African language at all. Cohere's Tiny Aya (3.35B,
   GlobalMGSM-African 39.2 vs Gemma3-4B 17.6) is **CC-BY-NC** and 8K-context — unusable as the scored artifact.
5. **Top-5 for our formula (ranked):** (1) MiniCPM5-1B Q4_0, (2) LFM2.5-1.2B-Thinking Q4_0, (3) Qwen3.5-2B Q4_0, (4) Qwen3-1.7B Q4_0,
   (5) Qwen3.5-4B Q4_0 (accuracy-max fallback). Ternary BitCPM-CANN-1B/3B are dominated; keep BitCPM-CANN-8B only if S_acc on the
   real judged prompts turns out to be catastrophically better than the small dense models (unlikely from the numbers below).
   All five load in b10175 (architectures merged Feb 2026 or earlier) and in the profiler's llama-cpp-python (0.3.34/0.3.35 vendor
   llama.cpp of 2026-07-11 / 2026-08-16) [V, §6].

---

## 1. Constraints that decide the ranking (verified)

| fact | source |
|---|---|
| Audit throughput = stock `llama-bench -m <gguf> -p 512 -n 128 -ngl 0` on b10175 built `-DGGML_AVX=OFF -DGGML_AVX2=OFF -DGGML_FMA=OFF -DGGML_F16C=OFF` (SSE4.2 only); `S_perf = min(TPS/15,1)·100`; RSS sampled at 10 Hz over the whole process tree; Linux mmap `MAP_POPULATE` ⇒ RSS ≈ whole file | R4 §1 (profiler Dockerfile/README, verified 2026-08-17), memory note `adtc-profiler-scoring-mechanics` |
| Only **Q4_0** (and Q1_0) have hand-written SSSE3 `vec_dot`; Q8_0 runs a scalar tail; **all K-quants, TQ1_0/TQ2_0, IQ\*, Q4_1, Q5_0/1** run generic C — 3–7× slower per weight than Q4_0; no repack, no tinyBLAS | R4 §0/§3/§7 (`ggml/src/ggml-cpu/arch/x86/quants.c` @ b10175); confirmed today in `opt/llama.cpp/ggml/src/ggml-cpu/arch/x86/quants.c`: `#elif defined(__SSSE3__)` appears only inside `ggml_vec_dot_q1_0_q8_0` (l.657) and `ggml_vec_dot_q4_0_q8_0` (l.770) |
| Measured generic-C TQ2_0 decode: **1.09 tok/s single-thread = 2.40 GB/s per core**, 3.70 tok/s on 4 threads for the 2.2 GB BitCPM-8B body (M1 proxy) → R4's GCC-based audit estimate for that file: **1.3–2.7 tok/s** | `opt/results/audit_kernel_proxy.md`, R4 §8.1 |
| R4 audit estimates for dense Q4_0 `--pure` (out Q8_0): 4B ≈ 2.3 GB → **4–7 tok/s** (bandwidth-bound); 1.7B ≈ 1.0 GB → **12–15 tok/s** | R4 §8.1 |
| The accuracy stage runs through the image's `llama-cpp-python>=0.3.0` wheel (pip picks newest at build): 0.3.34 (2026-07-12) vendors llama.cpp `e3546c7` (2026-07-11); 0.3.35 (2026-08-17) vendors `4df29be` (2026-08-16) | PyPI JSON + GitHub API, fetched today [V] |
| llama.cpp support dates: Qwen3.5 dense/MoE merged **2026-02-08** (PR #19435; also #19468); Gemma 4 day-0 (2026-04-02); LFM2 (Jul 2025), SmolLM3 (Jul 2025), MiniCPM (2024), TQ2_0 (Aug 2024), Falcon-H1 (Jul 2025); b9829 = 2026-06-28, b10175 = 2026-07-28 | web search results, R4 §1 |

**Speed model used below [I]:** for Q4_0 the audit box is memory-bandwidth-bound (kernel ≈ 0.3 c/w would allow ~20 GB/s on 4 cores;
VM bandwidth assumed ~15 GB/s, ±50 %); `tg ≈ min(15, 15 GB/s ÷ streamed GB/token)`. For TQ2_0 (generic C, compute-bound) I scale
R4's 1.3–2.7 tok/s for 2.2 GB linearly in bytes. "Streamed bytes/token" = every weight tensor except `token_embd` (a row gather),
**but for tied-embedding models the embedding matrix is read in full as the LM head, so streamed ≈ whole file.** Q4_0 = 0.5625 B/weight
(18 B per 32), TQ2_0 = 0.2578 B/weight (66 B per 256). RSS ≈ file + ~0.2 GB (KV/compute buffers) at llama-bench defaults.

---

## 2. Master table A — specs, GGUF sizes, bytes/token, speed class

Sizes are the actual files in the named repos [V] unless marked est. "Q4_0" sizes from unsloth/bartowski/Qwen keep `output`/`token_embd`
at Q6_K/Q8_0 — the audit-optimal file is our own `llama-quantize … q4_0 --pure --output-tensor-type q8_0 --token-embedding-type q4_0`
(R4 §8.2), which is a few % smaller than the listed Q4_0.

| # | model (instruct/chat) | date | lic. | params total / non-emb | tied? | ctx | llama.cpp arch | GGUF sources | Q4_0 | Q4_K_M | TQ2_0 | streamed GB/token (audit format) | est. audit tg (tok/s) [I] | speed class |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **MiniCPM5-1B** | 2026-05-19 | Apache-2.0 | 1.08B / 0.68B | no (vocab 130,560, h=1536) | 131,072 | `llama` | openbmb/MiniCPM5-1B-GGUF (F16 2.17 GB, Q8_0 1.15 GB, Q4_K_M 688 MB — no Q4_0 published; make it from F16) | ≈0.62 GB est. | 688 MB | – | ≈0.50 (0.88B streamed) | **≥15 (cap)** | A |
| 2 | **LFM2.5-1.2B-Thinking** (also -Instruct) | 2026-01-20 | LFM Open License v1.0 (free < $10M revenue) | 1.17B | tied (vocab 65,536) | 32,768 | `lfm2` (10 short-conv + 6 GQA) | LiquidAI/LFM2.5-1.2B-Thinking-GGUF (official), unsloth | **696 MB** | 731 MB | – | ≈0.66 | **14–15** | A/B |
| 3 | **Qwen3.5-0.8B** | 2026-03-02 | Apache-2.0 | 0.76B (BF16 1.52 GB) | tied (vocab 248,320!) | 262,144 | `qwen35` hybrid: 18 Gated-DeltaNet + 6 gated-attn layers | unsloth/Qwen3.5-0.8B-GGUF, bartowski/Qwen_Qwen3.5-0.8B-GGUF | **507 MB** | 533 MB | – | ≈0.45–0.5 | **≥15 (cap)** minus GDN overhead (unmeasured) | A |
| 4 | **Qwen3-1.7B** | 2025-04-29 | Apache-2.0 | 1.7B / 1.4B | tied (151,936) | 32,768 (40,960 max) | `qwen3` | unsloth/Qwen3-1.7B-GGUF, Qwen/Qwen3-1.7B-GGUF, bartowski | **1.06 GB** | 1.11 GB | – | ≈0.96–1.06 | **12–15** | B |
| 5 | **Qwen3.5-2B** | 2026-03-02 | Apache-2.0 | 1.9B (BF16 3.78 GB) | tied (248,320) | 262,144 | `qwen35` (24 layers: 18 GDN + 6 attn) | unsloth/Qwen3.5-2B-GGUF, bartowski | **1.21 GB** | 1.28 GB | – | ≈1.07–1.21 | **11–13** minus GDN overhead | B/C |
| 6 | **LFM2.5-2.6B** | **2026-08-04** | LFM Open License v1.0 | 2.69B | tied (128,000) | 131,072 | `lfm2` (22 conv + 8 attn) | LiquidAI/LFM2.5-2.6B-GGUF, bartowski/LiquidAI_LFM2.5-2.6B-GGUF (quantised with **b10262** — verify it loads on b10175) | **1.60 GB** | 1.68 GB | – | ≈1.5 | **9–10** | C |
| 7 | **SmolLM3-3B** | 2025-07 | Apache-2.0 | 3.08B | tied (128,256) | 65,536 (128K YaRN) | `smollm3` (NoPE 3:1) | unsloth/SmolLM3-3B-GGUF, ggml-org, bartowski | **1.81 GB** | 1.92 GB | – | ≈1.75 | **8–9** | C |
| 8 | **Granite-4.1-3B** | 2026-04-29 | Apache-2.0 | ~3B (40 layers, h=2560, vocab 100,352) | tied | 131,072 | `granite` (dense) | community GGUFs ("57 quantized versions" on card) | ≈1.8 GB est. | ≈1.9 GB est. | – | ≈1.7 | 8–9 | C |
| 9 | Llama-3.2-3B-Instruct | 2024-09-25 | Llama 3.2 Community | 3.21B | tied (128,256) | 131,072 | `llama` | bartowski, unsloth | **1.92 GB** | 2.02 GB | – | ≈1.8 | 8 | C |
| 10 | Falcon-H1-3B-Instruct | 2025-05/07 | Falcon-LLM licence (Apache-based + AUP) | ~3.1B | ? | 128K [M] | `falcon-h1` (attn ∥ Mamba-2 SSM — SSM scan is generic C on x86) | tiiuae official GGUF | ≈1.9 GB est. | – | – | ≈1.8 | 7–8 (SSM overhead) | C |
| 11 | Ministral-3-3B-Instruct-2512 | 2025-12-02 | Apache-2.0 | 3.4B text (+0.4B vision, separate mmproj) | no [M] | 262,144 | `mistral3`/`llama` | unsloth/Ministral-3-3B-Instruct-2512-GGUF, bartowski | **2.05 GB** | 2.15 GB | – | ≈1.8–1.9 | 7–8 | C |
| 12 | Qwen2.5-3B-Instruct | 2024-09 | **Qwen Research License** (non-commercial) | 3.09B / 2.77B | tied | 32,768 | `qwen2` | Qwen/Qwen2.5-3B-Instruct-GGUF | **2.0 GB** | 2.1 GB | – | ≈1.75 | 8 | C |
| 13 | Phi-4-mini-instruct / **Phi-4-mini-reasoning** | 2025-02 / 2025-04 | MIT | 3.84B | tied (200,064) | 131,072 | `phi3` | unsloth/Phi-4-mini-instruct-GGUF, bartowski/microsoft_Phi-4-mini-reasoning-GGUF | **2.33 GB** | 2.49 GB | – | ≈2.2 | 6–7 | D |
| 14 | Gemma-3-4b-it | 2025-03 | Gemma Terms of Use | 3.88B | tied (262,144) | 131,072 | `gemma3` | bartowski/google_gemma-3-4b-it-GGUF (+ mmproj 851 MB, not needed) | **2.37 GB** | 2.49 GB | – | ≈2.2 | 6–7 | D |
| 15 | **Qwen3-4B-Instruct-2507** / **-Thinking-2507** (and Qwen3-4B) | 2025-08 (2507) | Apache-2.0 | 4.0B / 3.6B | tied | 262,144 (orig. 32K) | `qwen3` | unsloth/Qwen3-4B-Instruct-2507-GGUF etc. | **2.38 GB** | 2.5 GB | – | ≈2.25 | 5–7 | D |
| 16 | **Qwen3.5-4B** | 2026-03-02 | Apache-2.0 | 4.2B (BF16 8.42 GB) | tied (248,320) | 262,144 | `qwen35` (32 layers: 24 GDN + 8 attn) | unsloth/Qwen3.5-4B-GGUF, bartowski | **2.58 GB** | 2.74 GB | – | ≈2.4–2.6 | 5–6 minus GDN overhead | D |
| 17 | Gemma-4-E2B-it | 2026-04-02 | **Apache-2.0** | 5.1B total (PLE) / 2.3B effective | – | 131,072 | `gemma4` | unsloth/gemma-4-E2B-it-GGUF (Q4_0 3.04 GB, Q4_K_M 3.11 GB, Q8_0 5.05 GB) | 3.04 GB | 3.11 GB | – | ≈1.3 est. (PLE tables are row-gathers) but **RSS = 3.0+ GB** | 9–11 | C for speed, **E for RSS** |
| 18 | Gemma-4-E4B-it | 2026-04-02 | Apache-2.0 | 8B total / 4.5B eff. | – | 131,072 | `gemma4` | unsloth/gemma-4-E4B-it-GGUF (Q4_0 4.84 GB, Q4_K_M 4.98 GB, Q8_0 8.19 GB) | 4.84 GB | 4.98 GB | – | ≈2.5 est.; RSS ≈ 5 GB | 5–6 | E |
| 19 | Gemma-3-1b-it | 2025-03 | Gemma ToU | 1.0B | tied (262,144 → 302M embd) | 32,768 | `gemma3` | bartowski/google_gemma-3-1b-it-GGUF | **722 MB** | 806 MB | – | ≈0.6 | ≥15 | A |
| 20 | Llama-3.2-1B-Instruct | 2024-09 | Llama 3.2 Community | 1.24B | tied | 131,072 | `llama` | bartowski | **773 MB** | 808 MB | – | ≈0.7 | 14–15 | A/B |
| 21 | Qwen3-0.6B | 2025-04 | Apache-2.0 | 0.6B / 0.44B | tied | 32,768 | `qwen3` | unsloth/Qwen3-0.6B-GGUF | **382 MB** | 397 MB | – | ≈0.35 | ≥15 | A |
| 22 | DeepSeek-R1-Distill-Qwen-1.5B | 2025-01-20 | MIT | 1.78B (Qwen2.5-Math-1.5B base) | tied [M] | 32,768 (max_pos 131,072) | `qwen2` | bartowski/DeepSeek-R1-Distill-Qwen-1.5B-GGUF, unsloth | **1.07 GB** | 1.12 GB | – | ≈0.9–1.0 | 13–15 | B |
| 23 | Qwen2.5-Math-1.5B-Instruct | 2024-09 | Apache-2.0 | 1.54B | tied | **4,096** | `qwen2` | bartowski/Qwen2.5-Math-1.5B-Instruct-GGUF | **938 MB** | 986 MB | – | ≈0.87 | 14–15 | B |
| 24 | Qwen2.5-1.5B-Instruct | 2024-09 | Apache-2.0 | 1.54B | tied | 32,768 | `qwen2` | Qwen/Qwen2.5-1.5B-Instruct-GGUF | **1.07 GB** | 1.12 GB | – | ≈0.87–1.0 | 13–15 | B |
| 25 | **BitCPM-CANN-1B** (ternary, MiniCPM4 line) | 2026-05-23 | Apache-2.0 | 1.62B (BF16 3.25 GB): 28 L, h=2048, vocab 73,448 | no | 32,768 (LongRoPE) | `minicpm`/`llama` | openbmb/BitCPM-CANN-1B-gguf (`bitcpm4-1b-tq2_0.gguf` **551 MB**, bf16 3.25 GB) | – | – | **551 MB** | ≈0.46 (TQ2_0 body 340 MB + Q6_K head 123 MB) — **generic C kernel** | **6–13** | B/C (compute-bound) |
| 26 | **BitCPM-CANN-3B** | 2026-05-23 | Apache-2.0 | 3.35B (BF16 7.21 GB): 32 L, h=2560, FFN 10,240, KV heads 2 | no | 32,768 | `minicpm`/`llama` | openbmb/BitCPM-CANN-3B-gguf (`bitcpm4-3b-tq2_0.gguf` **1.1 GB**) | – | – | **1.1 GB** | ≈0.92 — generic C | **3–6.5** | D (compute-bound) |
| 27 | BitCPM-CANN-8B (current submission) | 2026-05-23 | Apache-2.0 | 8.2B | no | 32,768 | `minicpm` | openbmb/BitCPM-CANN-8B-gguf (**2.37 GB** TQ2_0; ours pruned to ≈2.2 GB) | – | – | 2.37 GB | 2.2 — generic C | **1.3–2.7** (R4) | E |
| 28 | BitCPM-CANN-0.5B | 2026-05-23 | Apache-2.0 | ~0.6B | no | 32,768 | `minicpm` | openbmb/BitCPM-CANN-0.5B-gguf (**245 MB** TQ2_0, bf16 870 MB) | – | – | 245 MB | ≈0.2 | 13–25 | A/B |
| 29 | MiniCPM4-0.5B | 2025-06-06 | Apache-2.0 | 0.5B | – | 32,768 | `minicpm` | convertible (no official GGUF found) | ≈0.3 GB est. | – | – | ≈0.25 | ≥15 | A |
| 30 | MiniCPM4.1-8B | 2025-09-05 | Apache-2.0 | 8B | no | 65,536 (131K LongRoPE) | `minicpm` (InfLLM-v2 sparse attn = dense in llama.cpp) | openbmb/MiniCPM4.1-8B-GGUF | ≈4.4 GB est. | ≈4.9 GB est. | – | ≈4.4 | ~3 | E |
| 31 | Tiny Aya Global (Cohere Labs) | 2026-02-17 | **CC-BY-NC** | 3.35B | – | 8K in / 8K out | `cohere2` [I] | community (8 quants) | ≈2.1 GB ("2.14 GB at 4-bit") | – | – | ≈2 | 7 | D — **licence excludes it** |
| 32 | MobileLLM-R1.5-950M | 2025-11-24 | **FAIR Noncommercial Research** | 0.95B | – | 32,768 | `llama` [I] | GGUF exists per card | ≈0.55 GB | – | – | ≈0.5 | ≥15 | A — **licence excludes it** |
| 33 | HRM-Text-1B (Sapient) | 2026 | Apache-2.0 | ~1B recurrent | – | – | **not supported** upstream ("generic GGUF runners will not work until they implement the HRM runtime graph") | – | – | – | – | – | excluded |
| 34 | Phi-4-mini-flash-reasoning (SambaY hybrid) | 2025-07 | MIT | 3.8B | – | 64K | no llama.cpp arch as of my knowledge [M] | – | – | – | – | – | excluded (verify) |

Not present as of 2026-08-17 (searched): any Qwen3.6/Qwen3.8 model ≤4B (Qwen3.6 = 27B + 35B-A3B, 2026-04-22; Qwen3.8 = Max/2.4T-A95B
2026-08-03/08 + 27B ~2026-08-15) [V]; any new Llama ≤4B; Gemma 4 sizes below E2B.

---

## 3. Master table B — accuracy (instruct/chat versions; exact numbers as published)

Legend: T = thinking mode, NT = non-thinking. `–` not published. Values are per the model card unless a source is named.

| model | GSM8K | MATH / MATH-500 | AIME24 / AIME25 | MMLU (5-shot) | MMLU-Pro | MMLU-Redux | ARC-C | HumanEval | GPQA-D | IFEval | other |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **MiniCPM5-1B** (T) [V, HF leaderboard image transcribed] | – | **MATH-500 91.60** | AIME25 **40.42**, AIME26 40.42, HMMT-Feb26 25.76 | – | 48.85 | 70.06 | – | HumanEval+ 78.7 (note.com transcription) | 26.26 | 80.41 | LCB-v6 33.52, BBH 71.89, IFBench 46.67, avg 42.57 vs LFM2.5-1.2B-T 35.61, Qwen3-0.6B-T 26.77, Qwen3.5-0.8B-T 25.14 |
| **LFM2.5-1.2B-Thinking** [V] | **85.60** | MATH-500 **87.96** (89.00 in MiniCPM5's eval) | AIME25 31.73 | – | 49.65 | 66.08 (MiniCPM5 eval) | – | – | 37.86 | 88.42 | IFBench 44.85, Multi-IF 69.33, BFCLv3 56.97 |
| LFM2.5-1.2B-Instruct (NT) [V] | 64.52 | MATH-500 63.20 | AIME25 14.00 | – | 44.35 | – | – | – | 38.89 | 86.23 | IFBench 47.33 |
| **Qwen3.5-0.8B** [V card] | – | MATH-500 30.40 (T, MiniCPM5 eval) | AIME25 1.04 (T, MiniCPM5 eval) | – | NT 29.7 / T 42.3 | NT 48.5 / T 59.5 | – | – | T 11.9 | NT 52.1 / T 44.0 | MMMLU NT 34.1 / T 44.3; PolyMATH 8.2; **defaults to non-thinking** |
| **Qwen3.5-2B** [V card] | – | – | HMMT-Feb25 22.9, HMMT-Nov25 19.6 (T) | – | NT 55.3 / **T 66.5** | NT 69.2 / T 79.6 | – | – | T 51.6 | NT 61.2 / T 78.6 | MMMLU NT 56.9 / T 63.1; PolyMATH 26.1; INCLUDE 55.4; WMT24++ 45.8; BFCL-V4 43.6 |
| **Qwen3.5-4B** (T) [V card] | – | – | HMMT-Feb25 **74.0**, HMMT-Nov25 76.8; AIME25 49.33 per Liquid's eval (mode unclear) | – | **79.1** | 88.8 | – | – | **76.2** | 89.8 | LiveCodeBench-v6 55.8, SuperGPQA 52.9, MMMLU 76.1, MMLU-ProX 71.5, PolyMATH 51.1, INCLUDE 71.0, WMT24++ 66.6, IFBench 59.2 |
| Qwen3-0.6B [V tech report] | – | MATH-500 T 77.6 / NT 55.2 | AIME24 T 10.7, AIME25 T 15.1 | – | – | NT 44.6 | – | – | T 27.9 | T 59.2 | LiveCodeBench T 12.3, MMMLU T 43.1 |
| **Qwen3-1.7B** [V tech report + Qwen3.5 card] | 85.60 (Liquid's eval, T) | MATH-500 **T 93.4** / NT 73.0 | AIME24 T 48.3, AIME25 T 36.8 | – | T 56.5 / NT 40.2 | T 73.9 / NT 64.4 | – | – | T 40.1 | T 72.5 / NT 68.2 | LiveCodeBench T 33.2, MMMLU T 57.0, HMMT-Feb25 10.2 |
| Qwen3-4B (orig., T / NT) [V tech report] | – | MATH-500 T 97.0 / NT 84.8 | AIME24 T 73.8, AIME25 T 65.6 / NT 19.1 | – | T 70.4 / NT 58.0 | T 83.7 / NT 77.3 | – | – | T 55.9 / NT 41.7 | T 81.9 / NT 81.2 | LiveCodeBench T 48.4 / NT 21.3 |
| **Qwen3-4B-Instruct-2507** (NT) [V] | – | – | AIME25 47.4, HMMT25 31.0 | – | 69.6 | 84.2 | – | MultiPL-E 76.8 | 62.0 | 83.4 | ZebraLogic 80.2, LiveBench 63.0, LCB-v6 35.1, MMMLU-ProX 61.6, PolyMATH 31.1, BFCL-v3 61.9 |
| **Qwen3-4B-Thinking-2507** [V] | – | – | AIME25 **81.3**, HMMT25 55.5 | – | 74.0 | 86.1 | – | – | 65.8 | 87.4 | LCB-v6 55.2, PolyMATH 46.2, MMLU-ProX 64.2 |
| Qwen2.5-Math-1.5B-Instruct (CoT greedy) [V arXiv 2409.12122 table] | **84.8** (TIR 83.7) | MATH **75.8** (TIR 79.9) | AIME24 3/30, AMC23 24/40 | MMLU-STEM 57.5 | – | – | – | – | – | – | Minerva 29.4, GaoKao 65.5, OlympiadBench 38.1, CollegeMath 47.7; **"We do not recommend using this series of models for other tasks"**; ctx 4K |
| Qwen2.5-1.5B-Instruct [V blog] | 73.2 | MATH 55.2 | – | – | 32.4 | 50.7 | – | 61.6 | 29.8 | 42.5 | LiveBench 18.8 |
| Qwen2.5-3B-Instruct [V blog] | 86.7 | MATH 65.9 | – | – | 43.7 | 64.4 | – | 74.4 | 30.3 | 58.2 | MultiPL-E 60.2, LCB 19.9 |
| DeepSeek-R1-Distill-Qwen-1.5B [V] | 77.3 (MobileLLM eval) | MATH-500 **83.9** | AIME24 28.9 (cons@64 52.7), AIME25 23.4 (MobileLLM eval) | – | – | – | – | – | 33.8 | – | LiveCodeBench 16.9, CodeForces 954; always thinks |
| Gemma-3-1b-it [V card] | 62.8 | MATH 48.0, HiddenMath 15.8 | – | – | 14.7 | 33.3 (Qwen3 TR) | – | 41.5 | 19.2 | 80.2 | LiveCodeBench 1.9, MGSM (PT) 2.04, Global-MMLU-Lite 34.2 |
| Gemma-3-4b-it [V card] | **89.2** | MATH 75.6, HiddenMath 43.0 (MATH-500 26.1 in Qwen3 TR's NT eval) | – | PT 59.6 | 43.6 | 59.51 (Qwen3 TR) | PT 56.2 (25-shot) | 71.3 | 30.8 | 90.2 | LiveCodeBench 12.6, BBH 72.2, MGSM (PT) 34.7, Global-MMLU-Lite 54.5, WMT24++ 46.8 |
| Gemma-4-E2B-it [V card] | – | MATH-Vision 52.4 | AIME-2026 37.5 (26.33 per Liquid's eval) | – | 60.0 | – | – | – | 43.4 | – | LCB-v6 44.0, BBEH 21.9, MMMLU 67.4, Codeforces 633 |
| Gemma-4-E4B-it [V card] | – | MATH-Vision 59.5 | AIME-2026 42.5 (34.27 per Liquid's eval) | – | 69.4 | – | – | – | 58.6 | – | LCB-v6 52.0, BBEH 33.1, MMMLU 76.6, Codeforces 940 |
| **Phi-4-mini-instruct** [V card] | **88.6** | MATH 64.0 (MATH-500 67.6 in Qwen3 TR) | – | **67.3** | 52.8 | 67.9 (Qwen3 TR) | **83.7** | – (MBPP/HumanEval not in table; MATH-500 92.5 quoted for reasoning variant elsewhere) | 25.2 | ~68.6 (Qwen3 TR) | BBH 70.4, MGSM 63.9, Multilingual-MMLU 49.3, avg 63.5 |
| **Phi-4-mini-reasoning** [V card] | – | MATH-500 **94.6** | AIME 57.5 | – | – | – | – | – | 52.0 | – | English-only; trained on 150B DeepSeek-R1 synthetic tokens |
| SmolLM3-3B [V card] | base 67.63 (5-shot); GSM-Plus NT 72.8 / T 83.4 | base MATH 46.10 (4-shot) | AIME25 NT 9.3 / T 36.7 | base MMLU-CF 44.13 | – | – | base ARC-CF 65.61 | base HumanEval+ 30.48 | NT 35.7 / T 41.7 | NT 76.7 / T 71.2 | LCB-v4 NT 15.2 / T 30.0, BFCL 92.3, Global-MMLU 53.5 |
| **LFM2.5-2.6B** [V card] | – | – | AIME25 **51.87** | – | – | – | – | – | – | – | IFBench 59.17, Multi-IF 80.07, LCB-v6 59.41, BFCLv4 56.88 (its table: Qwen3.5-4B 49.33/48.40/60.85/50.56; Qwen3.5-9B 56.07/56.47/69.86/60.13; Gemma-4-E4B 34.27/39.24/63.77/46.39) |
| LFM2-2.6B [V card] | 82.41 | – | – | 64.42 | – | – | – | – | 26.57 | 79.56 | MGSM 74.32, MMMLU 55.39, IFBench 22.19 |
| Granite-4.1-3B [V card] | **86.88** | – | – | 67.02 | 49.83 | – | – | 81.71 | 31.70 | 82.30 | MGSM 70.00, MMMLU 57.61; no thinking mode |
| Falcon-H1-3B-Instruct [V card] | 84.76 | MATH-500 74.2 | AIME24 11.88, AIME25 13.33 | 68.3 | 43.69 | – | 49.57 | 76.83 | 33.89 (GPQA-D 38.72) | 85.05 | AMC-23 55.63, MBPP 79.63 |
| Llama-3.2-1B-Instruct [V card] | 44.4 | MATH 30.6 | – | 49.3 | – | – | 59.4 | – | 27.2 | 59.5 | MGSM 24.5 |
| Llama-3.2-3B-Instruct [V card] | 77.7 | MATH 48.0 | – | 63.4 | – | – | 78.6 | – | 32.8 | 77.4 | MGSM 58.2 |
| Ministral-3-3B-Instruct-2512 [V unsloth card] | – | MATH CoT 60.1 (an arXiv table quotes MATH maj@1 83.0 — inconsistent, treat with care) | – | 70.7 | – | – | – | – | 53.4 | – | Arena-Hard 30.5, WildBench 56.8; Reasoning variant exists |
| **BitCPM-CANN-1B** (ternary) vs its 1B FP counterpart [V card] | **61.56** (FP 63.15) | – | – | 57.71 (FP 57.71) | – | 54.16 | ARC-c 67.12 | – | – | – | BBH 60.40, avg 63.42 (97.1 % retention) |
| **BitCPM-CANN-3B** [V card] | **79.45** (FP 81.64) | – | – | 64.41 (FP 66.95) | 60.07 | ARC-c 78.98 | – | – | – | BBH 68.30, avg 72.32 (97.2 %) |
| BitCPM-CANN-8B [V card] | 85.75 (FP 91.51) | – | – | 70.65 (FP 75.83) | – | 69.85 | ARC-c 86.10 | – | – | – | BBH 70.70, avg 77.84 (95.7 %) |
| BitCPM-CANN-0.5B [V card] | 39.42 (FP 52.08) | – | – | 50.73 | – | 43.79 | 50.51 | – | – | – | avg 51.98 (90.1 %) |
| MiniCPM4-0.5B [V tech-report Table 5 image] | 52.08 | MATH500 29.60 | – | 55.55 | – | – | – | 46.34 | – | – | BBH 49.87, MBPP 59.14 |
| MiniCPM4-8B [V] | 91.51 | MATH500 78.60 | – | 75.83 | – | – | – | 85.37 | – | – | BBH 76.73 |
| MiniCPM4.1-8B (T) [V Table 9 image] | 94.16 | MATH500 95.60 | AIME24 83.33, AIME25 73.33 | 86.38 | – | 86.41 | – | 95.73 | – | 75.23 | LCB-v6 52.00, BBH 82.40 |
| MobileLLM-R1.5-950M [V card] (NC licence) | 82.6 | MATH-500 86.6 | AIME24 39.9, AIME25 31.1 | – | – | – | – | – | – | – | LCB-v6 29.1 |
| Tiny Aya Global [V] (NC licence) | – | GlobalMGSM (African) 39.2 vs Gemma3-4B 17.6 | – | – | – | – | – | – | – | – | 70 languages incl. Amharic, Hausa, Igbo, Swahili, Yoruba, Wolof, Xhosa, Zulu |

Cross-eval consistency notes: MiniCPM5's harness gives Qwen3-0.6B-T MATH-500 72.6 (Qwen TR: 77.6) and LFM2.5-1.2B-T 89.0 (Liquid: 87.96) —
±3 pts between harnesses; the ordering MiniCPM5-1B > LFM2.5-1.2B-T > Qwen3-0.6B ≫ Qwen3.5-0.8B on math is stable across both. Liquid's
AIME25 for Qwen3.5-4B (49.33) is far below what Qwen's own HMMT numbers imply (74.0) — probably a limited thinking budget; treat
Liquid's competitor columns as lower bounds.

---

## 4. Per-model notes (what the card actually says, quirks, why it ranks where it does)

### 4.1 BitCPM-CANN 0.5B / 1B / 3B / 8B (openbmb, ternary) [V]
* Card: "the first end-to-end 1.58-bit (ternary) large language model training system natively built on Huawei Ascend NPU … ternary
  values {-1, 0, 1}, achieving ~90% bit-width reduction compared to BF16". Family "0.5B/1B/3B/8B — evaluated against their
  full-precision MiniCPM4 counterparts across 11 benchmarks"; retention 90.1 / 97.1 / 97.2 / 95.7 %. Apache-2.0. Tech report:
  `github.com/OpenBMB/MiniCPM/blob/main/docs/BitCPM_CANN.pdf`. Chat models (`model.chat(...)` examples), **no thinking mode**, EN/ZH.
* Configs: 3B = `LlamaForCausalLM`, h=2560, 32 layers, FFN 10,240, 32 heads / 2 KV, vocab 73,448, `max_position_embeddings` 32,768,
  longrope; 1B = h=2048, 28 layers, FFN 6,144, 16 heads / 2 KV. HF labels the repos "2B" and "4B" because embeddings are counted
  (BF16 GGUFs are 3.25 GB and 7.21 GB ⇒ 1.62B and 3.6B).
* GGUF repos ship exactly two files each: `bitcpm4-{0.5b,1b,3b,8b}-{bf16,tq2_0}.gguf` — TQ2_0 245 MB / 551 MB / 1.1 GB / 2.37 GB.
* Why they lose here: TQ2_0 has no x86 SIMD path without AVX2 (R4 §3), so on the audit build a 3B ternary (0.92 GB streamed) decodes
  about as fast as a **2.2 GB Q4_0** dense model, and its GSM8K 79.5 / MMLU 64.4 with no reasoning mode is below Qwen3-1.7B /
  Qwen3.5-2B / LFM2.5-1.2B-T at ≤1.2 GB. The 1B (GSM8K 61.6) is far below MiniCPM5-1B at the same bytes.

### 4.2 MiniCPM4 / 4.1 / 5 (openbmb) [V]
* **MiniCPM5-1B** (2026-05-19): "dense 1B Transformer built for on-device", "reaches an average score of 42.57 across reasoning,
  knowledge, code, instruction-following, math, logic and agentic benchmarks, surpassing the highest average score of 35.61 among
  strong open-source models in the same size class (LFM2.5-1.2B-Thinking, Qwen3-0.6B/think, Qwen3.5-0.8B/think)". Params
  1,080,632,832 total / 679,552,512 non-embedding; "Standard `LlamaForCausalLM`", 24 layers, 16 Q / 2 KV heads, h=1536, FFN 4,608,
  vocab 130,560, ctx 131,072, **untied**; hybrid `enable_thinking` in one checkpoint; Apache-2.0; languages listed: English, Chinese.
  Trained with SFT → RL → on-policy distillation ("RL + OPD raises the average score by ↑16 points"). Official GGUF: F16 2.17 GB, Q8_0
  1.15 GB, Q4_K_M 688 MB. Ollama `openbmb/minicpm5`.
* **MiniCPM4.1-8B** (2025-09-05): 64K ctx (131K LongRoPE), hybrid reasoning `enable_thinking`, GGUF official; Table 9 numbers above
  (MATH500 95.6, AIME24 83.3). Too big for this formula (Q4_0 ≈ 4.4 GB → ~3 tok/s, S_eff ≈ 34).
* **MiniCPM4-0.5B / 8B** (2025-06-06): Table 5 numbers above; 0.5B is superseded by MiniCPM5-1B and BitCPM-CANN-1B.

### 4.3 Qwen3.5 small series (0.8B / 2B / 4B / 9B — every size that exists) [V]
* Released 2026-03-02 (Unsloth: "Qwen releases 4 new Qwen3.5 Small models! Qwen3.5: 0.8B • 2B • 4B • 9B"). Apache-2.0. Native
  multimodal (vision encoder shipped as separate `mmproj-*.gguf`; text-only GGUF works without it). "Support for 201 languages and
  dialects". Hybrid architecture: 0.8B/2B = 24 layers as `6 × (3 × (Gated DeltaNet → FFN) → 1 × (Gated Attention → FFN))`; 4B = 32
  layers (8 × …); vocab 248,320 **tied**; ctx 262,144 native (1M with YaRN). "Qwen3.5 models operate in thinking mode by default"
  except "**Qwen3.5-0.8B operates in non-thinking mode by default**"; toggle `chat_template_kwargs: {"enable_thinking": …}`.
  Recommended sampling: T 1.0/top_p 0.95/top_k 20/presence 1.5 (thinking); output length 32,768 recommended — a **risk if the
  accuracy harness caps generation**.
* llama.cpp: dense+MoE support merged 2026-02-08 (PR #19435, "based on Qwen3Next but rebased on the common-delta-net PR #19125");
  a later PR (#19375) sped GDN graphs up ~60 % on GPU. On the no-AVX CPU the GDN recurrence per token is small (≈0.5M MACs per GDN
  layer for the 4B) but its ggml ops are generic C — **overhead unmeasured; assume 5–15 % on tg and verify with the b10175 build**.
* GGUF sizes (unsloth): 0.8B Q4_0 507 MB / Q4_K_M 533 MB / Q8_0 812 MB; 2B 1.21 / 1.28 / 2.01 GB; 4B 2.58 / 2.74 / 4.48 GB.
* Accuracy: see Table B. The 0.8B is weak at math (MATH-500 30.4 T, GPQA 11.9); the 2B is the best ≤2B on knowledge/multilingual
  (MMLU-Pro 66.5 T, MMMLU 63.1); the 4B beats Qwen3-4B-Thinking-2507 on MMLU-Pro (79.1 vs 74.0), GPQA (76.2 vs 65.8), HMMT-Feb25
  (74.0 vs 55.5) and MMMLU (76.1 vs 70.8).

### 4.4 Qwen3 0.6B / 1.7B / 4B (+ 4B-2507 variants) [V]
* Apache-2.0, `qwen3` arch (pure GQA transformer, tied), 119 languages, thinking toggle (`/think`, `/no_think`, `enable_thinking`);
  0.6B/1.7B ctx 32K; 4B-Instruct-2507 / Thinking-2507 (Aug 2025) are single-mode, ctx 262,144. GGUF everywhere (unsloth/Qwen/bartowski):
  0.6B Q4_0 382 MB, 1.7B 1.06 GB, 4B 2.38 GB. Tech-report tables 17–20 numbers above.
* Qwen3-1.7B is the "safe" ~1 GB choice: everything on the Q4_0 SSSE3 kernel, MATH-500 93.4 (T) / 73.0 (NT), MMLU-Redux 73.9 (T).

### 4.5 Qwen2.5-1.5B/3B-Instruct, Qwen2.5-Math-1.5B-Instruct [V]
* Qwen2.5-3B is under the **Qwen Research License** (not Apache) — avoid as a shipped artifact. Qwen2.5-Math-1.5B-Instruct: Apache-2.0,
  **4K context**, "mainly supports solving English and Chinese math problems through CoT and TIR. We do not recommend using this
  series of models for other tasks" — unsuitable as a tutor even though GSM8K 84.8 / MATH 75.8 (CoT) is strong for 0.9 GB.

### 4.6 DeepSeek-R1-Distill-Qwen-1.5B [V]
* MIT; base Qwen2.5-Math-1.5B; MATH-500 83.9, AIME24 28.9, GPQA 33.8; "Avoid adding a system prompt; all instructions should be
  contained within the user prompt", "enforcing the model to initiate its response with '<think>'". Always-on long thinking, weak
  general chat/instruction following — superseded by MiniCPM5-1B / LFM2.5-1.2B-T at the same size.

### 4.7 Gemma 4 E2B / E4B (2026-04-02) and Gemma 3 1B / 4B [V]
* Gemma 4: **Apache-2.0** (a change from Gemma 3's Gemma Terms of Use), text+image+audio, 128K ctx, vocab 262K, "Support for 35+
  languages, pre-trained on 140+ languages", thinking via `<|think|>` control token, MTP draft heads shipped separately (irrelevant
  to stock llama-bench). Effective 2.3B / 4.5B but **total 5.1B / 8B with Per-Layer Embeddings** — the GGUF file (Q4_0 3.04 / 4.84 GB)
  is what `MAP_POPULATE` pins, so RSS is ~2× the streamed weights. E2B MMLU-Pro 60.0, GPQA 43.4, AIME-2026 37.5, MMMLU 67.4;
  E4B 69.4 / 58.6 / 42.5 / 76.6. No GSM8K/MATH-500 published; no African-language statement.
* Gemma 3: 1B ctx 32K, 4B 128K, "over 140 languages"; instruction-tuned 4B GSM8K 89.2 / MATH 75.6 / HumanEval 71.3 / MMLU-Pro 43.6;
  1B GSM8K 62.8 / MATH 48.0. Multilingual PT: MGSM 4B 34.7, 1B 2.04; Global-MMLU-Lite IT 54.5 / 34.2. Gemma Terms of Use.

### 4.8 Phi-4-mini-instruct / Phi-4-mini-reasoning [V]
* MIT, 3.8B, 128K ctx, vocab 200,064 (tied), `phi3` arch. Instruct: MMLU 67.3, GSM8K 88.6, MATH 64.0, ARC-C 83.7, MGSM 63.9, 22 languages
  (none African). Reasoning (Apr 2025): MATH-500 94.6, AIME 57.5, GPQA-D 52.0, **English only**, trained on "150B tokens (synthetic
  math content from DeepSeek-R1)". GGUF Q4_0 2.33 GB.

### 4.9 SmolLM3-3B [V]
* Apache-2.0, 3.08B tied, NoPE 3:1, 64K ctx (128K YaRN), `/think` `/no_think`, 6+3 languages (en/fr/es/de/it/pt + ar/zh/ru).
  Extended-thinking AIME25 36.7, GSM-Plus 83.4, GPQA-D 41.7; base GSM8K 67.6 (5-shot), MATH 46.1. Q4_0 1.81 GB.

### 4.10 LFM2 / LFM2.5 (Liquid AI) [V]
* Licence = **LFM Open License v1.0** ("based on Apache 2.0 … rights to use the model for commercial purposes end if your company's
  annual revenue exceeds $10 million USD") — fine for a competition entry; state it in the report.
* LFM2.5-1.2B-Thinking (2026-01-20): 1.17B, 16 layers (10 double-gated short conv + 6 GQA), 32K ctx, 28T tokens, 8 languages
  (en/ar/zh/fr/de/ja/ko/es); "239 tok/s decode on AMD CPU", "<1GB". Numbers in Table B. Instruct sibling for no-think use.
* **LFM2.5-2.6B (2026-08-04)**: 2.69B, 30 layers (22 conv + 8 attn), **131,072 ctx**, vocab 128,000 (tied), 16 languages (no African),
  ~34T tokens, "explicit reasoning mode … `<think>` tags in chat template"; "fits in under 2.5 GB … 113 tok/s on AMD Ryzen AI Max+,
  220 tok/s on Apple M5 Max CPU". Q4_0 1.60 GB (bartowski, "Using llama.cpp release b10262 for quantization" — 4 builds newer than the
  audit's b10175; arch `lfm2` is old, but the 128K-vocab tokenizer is the LFM2.5-8B-A1B one — **load-test on b10175 before relying on it**).
* LFM2-2.6B (2025-09): MMLU 64.4, GSM8K 82.4, MGSM 74.3, IFEval 79.6, 32K ctx.

### 4.11 Llama-3.2-1B/3B, Ministral 3 3B, Granite 4.1-3B, Falcon-H1-3B, MobileLLM, Tiny Aya, HRM-Text [V unless noted]
* Llama 3.2 (2024-09-25): Llama 3.2 Community License; 8 languages (none African); 1B GSM8K 44.4 / MATH 30.6; 3B 77.7 / 48.0, MMLU 63.4,
  ARC-C 78.6. Old and weak per byte now.
* Ministral-3-3B-Instruct-2512 (2025-12): Apache-2.0, 3.4B text + 0.4B vision, 256K ctx, MMLU 70.7, GPQA-D 53.4, MATH CoT 60.1,
  "dozens of languages" (none African listed); a `-Reasoning-2512` variant exists. Q4_0 2.05 GB.
* Granite-4.1-3B (2026-04-29): Apache-2.0, dense, 128K, GSM8K 86.9, MMLU 67.0, HumanEval 81.7, IFEval 82.3, no thinking mode, 12 languages.
* Falcon-H1-3B-Instruct: hybrid attention ∥ Mamba-2; MMLU 68.3, GSM8K 84.8, MATH-500 74.2, IFEval 85.1; Falcon-LLM licence; SSM scan on
  the audit build is generic C (speed penalty unquantified).
* MobileLLM-R1-950M / R1.5-950M (Meta, 2025-09 / 2025-11-24): MATH-500 86.6, GSM8K 82.6, AIME25 31.1 — but "**FAIR Noncommercial Research
  License v1**" → excluded. MobileLLM-Pro (1B, Oct 2025) same licence family [M].
* Tiny Aya (Cohere Labs, 2026-02-17): 3.35B, 70 languages incl. Amharic/Hausa/Igbo/Swahili/Yoruba/Wolof/Xhosa/Zulu, GlobalMGSM-African
  39.2 vs Gemma3-4B 17.6, "2.14 GB at 4-bit, 10 tok/s on an iPhone 13" — **CC-BY-NC**, 8K in/8K out → excluded as the scored artifact
  (could still be cited as a comparison point in the report).
* HRM-Text-1B (Sapient, 2026): Apache-2.0, MMLU 60.7, GSM8K 84.5, MATH 56.2 on 40B training tokens — recurrent dual-timescale
  architecture, "standard upstream llama.cpp … expected not to load this file until hrm_text is supported upstream" → excluded.

---

## 5. African-language evidence (Swahili / Hausa / Yoruba / Igbo / Amharic)

**Only one source publishes AfriMGSM/AfriMMLU for ≤4B models we can ship:** AfriqueLLM (McGill-NLP, arXiv 2601.06395 v3, 2026; text
extracted from the PDF today). Base (pretrained, not instruct) checkpoints, `lm-eval` AfroBench settings, 8-shot CoT AfriMGSM, 5-shot
AfriMMLU. Averages over 18–19 African languages + en/fr:

| base model | AfriMGSM avg | AfriMMLU avg | AfriXNLI | Belebele | Overall (Table 3/7) |
|---|---|---|---|---|---|
| **Qwen3.5-4B** | **22.38** | **40.42** | 57.79 | 30.01 (MT) | 46.01 |
| Qwen3-4B | 14.75 | 39.16 | 46.05 | 20.47 | 31.49 |
| Gemma3-4B | 10.57 | 37.58 | 47.61 | 34.01 | 40.31 |
| Llama3.1-8B | 10.93 | 38.75 | 45.08 | 25.73 | 35.33 |
| Gemma3-12B | 23.77 | 43.13 | 68.20 | 41.44 | 54.80 |
| AfriqueQwen3.5-4B (CPT, released on HF as McGill-NLP/…) | 30.47 (34.17 with ExtendedCM) | 43.66 (45.26) | 41.05 | 66.01 | 57.12 |
| AfriqueGemma-4B | 14.86 | 36.73 | 39.62 | 50.52 | 47.88 |

Per-language (Table 16 AfriMGSM / Table 17 AfriMMLU; columns amh · hau · ibo · swa · yor · **eng**):

| base model | AfriMGSM amh/hau/ibo/swa/yor (eng) | AfriMMLU amh/hau/ibo/swa/yor (eng) |
|---|---|---|
| Qwen3.5-4B | 32.00 / 22.40 / 9.44 / 41.04 / 18.64 (82.80) | 42.68 / 38.68 / 38.64 / 45.28 / 41.28 (73.72) |
| Qwen3-4B | 8.80 / 6.64 / 2.16 / 23.84 / 5.52 (84.40) | 34.68 / 33.80 / 34.64 / 36.56 / 32.00 (75.24) |
| Gemma3-4B | 10.64 / 12.88 / 5.28 / 27.12 / 5.44 (42.48) | 34.40 / 34.08 / 35.36 / 41.48 / 34.72 (58.00) |
| Llama3.1-8B | 2.72 / 13.12 / 7.76 / 23.84 / 6.64 (53.52) | 34.16 / 33.84 / 31.72 / 39.08 / 32.08 (65.56) |
| AfriqueQwen3.5-4B-ExtendedCM | 35.12 / 42.32 / 27.12 / 51.36 / 30.40 (78.64) | 48.64 / 44.96 / 43.32 / 52.20 / 45.12 (69.08) |

Paper's own reading: "Switching from Qwen 3 4B to the more multilingual Qwen 3.5 4B base substantially raises the starting point
(31.49 → 46.01)"; footnote: Qwen 3 "only includes Afrikaans, Swahili, and Northern Arabic dialects" among African languages, Qwen 3.5
"support for 201 vs. 109 languages". Note AfriMMLU at ~35–45 is barely above the 25 % chance floor for every 4B model — **no ≤4B model
is genuinely competent in Hausa/Yoruba/Igbo/Amharic**; Swahili is the only one where a 4B is usable (Qwen3.5-4B 41.0 AfriMGSM).

Other data points: Gemma-3-4b-it MGSM 34.7 (PT) / Global-MMLU-Lite 54.5 (IT); Gemma-3-1b MGSM 2.04; Gemma-4 E2B/E4B MMMLU 67.4/76.6 (no
African split); Tiny Aya GlobalMGSM-African 39.2 (NC licence); IrokoBench (NAACL 2025) and AfroBench evaluate ≥7B/proprietary models only;
AFRILANGTUTOR (arXiv 2604.20996, 2026-04) evaluates Gemma/Qwen/TinyAya small models for *language tutoring* in African languages but the
PDF text I could extract has no per-model numbers. **Nothing ≤2B has any published African-language number**; MiniCPM5 (EN/ZH), LFM2.5
(8/16 languages), SmolLM3, Phi-4-mini, Llama-3.2, Granite, Ministral all list no African language.

---

## 6. llama.cpp / profiler compatibility (verified where possible)

| model family | arch tag | in b10175 (2026-07-28)? | in profiler llama-cpp-python (vendors llama.cpp 2026-07-11 or 2026-08-16)? | note |
|---|---|---|---|---|
| MiniCPM5-1B | `llama` | yes | yes | plain Llama; official GGUF loads anywhere |
| BitCPM-CANN / MiniCPM4 | `minicpm` + TQ2_0 | yes | yes | our current file already runs on it |
| Qwen3.5 0.8B/2B/4B | `qwen35` | yes (merged 2026-02-08) | yes | GDN CPU path speed unmeasured on no-AVX |
| Qwen3 / Qwen2.5 / DeepSeek distill | `qwen3` / `qwen2` | yes | yes | |
| LFM2.5-1.2B | `lfm2` | yes (2025-07) | yes | |
| LFM2.5-2.6B | `lfm2` + 128K tokenizer | **probably** — bartowski quantised with b10262 (2026-08); verify pre-tokenizer on b10175 | 0.3.35 yes; 0.3.34 (2026-07-11 vendor) uncertain | test before choosing |
| Gemma 4 E2B/E4B | `gemma4` | yes (2026-04) | yes | |
| Gemma 3, Phi-4-mini, SmolLM3, Llama-3.2, Ministral 3, Granite 4.1, Falcon-H1 | – | yes | yes | |
| HRM-Text-1B, Phi-4-mini-flash-reasoning | – | **no** | no | excluded |

Which llama-cpp-python the auditors get depends on when they build the image (`llama-cpp-python>=0.3.0`, unpinned). Any model whose
llama.cpp support landed before 2026-07-11 is safe under every plausible build; that covers all five picks below.

---

## 7. Score-model table (why small dense Q4_0 wins) [I — R4 speed model; ±50 % on tok/s; RSS = file + 0.2 GB]

`S_perf = min(TPS/15,1)·100`, `S_eff = (1 − RSS/7)·100`; contribution = 0.3·S_perf + 0.2·S_eff (max 50).

| candidate (audit format) | file / RSS GB | est. tg | S_perf | S_eff | perf+eff pts | accuracy anchor |
|---|---|---|---|---|---|---|
| MiniCPM5-1B **Q4_0 --pure** | 0.62 / 0.82 | ≥15 | 100 | 88 | **47.7** | MATH-500 91.6 T, MMLU-Pro 48.9, IFEval 80.4 |
| Qwen3.5-0.8B Q4_0 | 0.51 / 0.71 | ≥15 (–GDN) | ~95–100 | 90 | 46.5–48 | MATH-500 30.4 T — too weak |
| LFM2.5-1.2B-Thinking Q4_0 | 0.70 / 0.90 | 14–15 | 93–100 | 87 | 45.5–47.4 | MATH-500 88, GSM8K 85.6, IFEval 88.4 |
| Gemma-3-1b-it Q4_0 | 0.72 / 0.92 | ≥15 | 100 | 87 | 47.4 | GSM8K 62.8, MATH 48 — weak |
| BitCPM-CANN-1B TQ2_0 | 0.55 / 0.75 | 6–13 | 40–87 | 89 | 30–44 | GSM8K 61.6, no thinking |
| Qwen3-1.7B Q4_0 | 1.06 / 1.26 | 12–15 | 80–100 | 82 | 40.4–46.4 | MATH-500 93.4 T / 73 NT |
| Qwen3.5-2B Q4_0 | 1.21 / 1.41 | 11–13 (–GDN) | 70–85 | 80 | 37–41.5 | MMLU-Pro 66.5 T, GPQA 51.6, MMMLU 63.1 |
| LFM2.5-2.6B Q4_0 | 1.60 / 1.80 | 9–10 | 60–67 | 74 | 32.8–35 | AIME25 51.9 T, Multi-IF 80 |
| SmolLM3-3B / Granite-4.1-3B / Llama-3.2-3B Q4_0 | 1.8–1.9 / 2.0–2.1 | 8 | 53 | 70–71 | ~30 | GSM8K 87 (Granite) / AIME25 36.7 T (SmolLM3) |
| BitCPM-CANN-3B TQ2_0 | 1.1 / 1.3 | 3–6.5 | 20–43 | 81 | 22–29 | GSM8K 79.5, MMLU 64.4 |
| Qwen3-4B-2507 Q4_0 | 2.38 / 2.58 | 5–7 | 33–47 | 63 | 22.6–26.7 | AIME25 81.3 T-2507 / 47.4 Instruct |
| Phi-4-mini(-reasoning) / Gemma-3-4b Q4_0 | 2.33–2.37 / 2.55 | 6–7 | 40–47 | 64 | 24.8–26.9 | MATH-500 94.6 (Phi reasoning) / GSM8K 89.2 (Gemma) |
| Qwen3.5-4B Q4_0 | 2.58 / 2.78 | 5–6 (–GDN) | 33–40 | 60 | 22–24 | MMLU-Pro 79.1, GPQA 76.2, HMMT 74.0 |
| Gemma-4-E2B Q4_0 | 3.04 / 3.24 | 9–11 | 60–73 | 54 | 28.8–32.7 | MMLU-Pro 60, AIME26 37.5 |
| BitCPM-CANN-8B TQ2_0 (pruned) | 2.2 / 2.4 | 1.3–2.7 | 9–18 | 66 | 15.9–18.5 | GSM8K 85.8, MMLU 70.7 |
| Gemma-4-E4B / MiniCPM4.1-8B Q4_0 | 4.4–4.8 / 5 | 3–6 | 20–40 | 29–34 | 12–19 | best raw accuracy, unaffordable |

If the site's alternative definition applies (S_perf relative to the fastest submission), the ordering is unchanged and the gap
widens, because the fastest submissions will be ~1B Q4_0 files.

---

## 8. Top 5 for our scoring formula (ranked, with reasoning)

1. **MiniCPM5-1B — Q4_0 `--pure` from the official F16 (est. ~0.6 GB), thinking mode on for math, off for chit-chat.**
   Best accuracy per byte in existence today for English math/science: MATH-500 91.6, AIME25 40.4, MMLU-Redux 70.1, IFEval 80.4 —
   above LFM2.5-1.2B-T (avg 35.6 vs 42.6) and far above anything ternary at that size (BitCPM-CANN-1B GSM8K 61.6). Plain
   `LlamaForCausalLM` ⇒ 100 % of the token time on the SSSE3 Q4_0 kernel; 0.88B streamed weights ⇒ S_perf saturates even if the VM
   only delivers ~8 GB/s; RSS ≈ 0.8 GB ⇒ S_eff ≈ 88. Apache-2.0, 128K ctx, released 2026-05-19 (b10175 and both llama-cpp-python
   vendors postdate it). Risks: EN/ZH only (no African language), untied so `--pure` must keep the 200M-param head at Q8_0 or Q4_0
   (R4 §8.2), Q4_0 on a 1B costs more accuracy than on a 4B (mitigation: Q8_0 body ≈1.15 GB still ≈12 tok/s — Q8_0's scalar tail is
   ~0.5 c/w — or measure PPL of both), thinking traces are long (set the harness's max tokens accordingly / use `enable_thinking`
   only for math prompts).
2. **LFM2.5-1.2B-Thinking (with the Instruct sibling as the no-think fallback) — official Q4_0 696 MB.** MATH-500 88, GSM8K 85.6,
   IFEval 88.4 (best instruction-following of the tier — matters for a judged tutor), GPQA-D 37.9 > MiniCPM5's 26.3; "<1 GB",
   32K ctx; day-0 llama.cpp since 2025-07 (`lfm2`); the 10 short-conv layers are cheap on generic C. Licence is LFM Open v1.0 (free
   below $10M revenue) — must be declared, and it is not OSI/Apache, which may matter to judges. Choose it over #1 if pedagogy/
   instruction-following is judged more than raw math, or run both through the real prompt set and pick.
3. **Qwen3.5-2B — Q4_0 1.21 GB.** The best ≤2B on knowledge and languages (MMLU-Pro 66.5 T / 55.3 NT, GPQA 51.6, MMMLU 63.1, INCLUDE
   55.4, 201 languages; the Qwen3.5 base family is the only ≤4B line with measured African-language gains — 4B: AfriMGSM 22.4 vs
   Qwen3-4B 14.8), thinking toggle, 262K ctx, vision optional, Apache-2.0. Costs ~2 points of perf+eff vs #1 (11–13 tok/s, RSS 1.4 GB)
   and carries the GDN-on-generic-C uncertainty (must be measured on the b10175 no-AVX build before committing). Math is behind #1
   (HMMT-Feb25 22.9; MATH-500 not published) — mid-way between #1 and #5.
4. **Qwen3-1.7B — Q4_0 1.06 GB.** The conservative pure-transformer pick if the GDN path turns out slow: MATH-500 93.4 (T) / 73.0 (NT),
   MMLU-Redux 73.9 (T), IFEval 72.5, ~12–15 tok/s, RSS 1.26 GB, Apache-2.0, 119 languages (Swahili only among ours), 32K ctx.
   Superseded on math per byte by #1 and on knowledge by #3, but zero architecture risk and the richest ecosystem.
5. **Qwen3.5-4B — Q4_0 2.58 GB (accuracy-max fallback), or Qwen3-4B-Thinking-2507 (2.38 GB) if GDN proves slow.** Highest ceiling of
   anything ≤4B (MMLU-Pro 79.1, GPQA 76.2, HMMT-Feb25 74.0, MMMLU 76.1, LiveCodeBench 55.8; the best African-language base of the
   4B class) — but it costs ~24 points of perf+eff versus #1 (est. 5–6 tok/s ⇒ S_perf ≈ 35; RSS ≈ 2.8 GB ⇒ S_eff ≈ 60), so it only
   wins if the judged S_acc gap versus the 1B tier exceeds ~45 points, which the benchmark deltas above (MATH-500 ~95 vs 91.6;
   MMLU-Pro 79 vs 49) do not suggest.

**Not in the top 5 and why:** BitCPM-CANN-8B (current: perf+eff ≈ 17 — the formula's worst quadrant); BitCPM-CANN-3B/1B (generic-C
TQ2_0 ⇒ same speed as a 2× larger Q4_0 dense model, and lower accuracy than 2026 dense peers, no thinking); Gemma-4 E2B/E4B (PLE
tables inflate the populated file/RSS 2×; no math benchmarks published); Phi-4-mini-reasoning (94.6 MATH-500 but 2.33 GB, English-only,
always-thinking); Gemma-3-4B / Qwen2.5-3B (older, non-Apache licences); Tiny Aya / MobileLLM-R1.5 (non-commercial licences);
DeepSeek-R1-Distill-1.5B / Qwen2.5-Math-1.5B (single-purpose, chat/ctx limits); LFM2.5-2.6B (strong — AIME25 51.9, IFBench 59 —
but 1.6 GB puts it in the ~33-point tier and it needs a b10175 load test); SmolLM3/Granite-4.1/Falcon-H1/Ministral (3B tier ≈ 30 points,
no accuracy edge over #3/#5).

**Before Gate 1 (2026-08-25):** (a) build b10175 with the profiler's cmake line and run `llama-bench -p 512 -n 128` on Q4_0-pure files of
#1–#4 (and TQ2_0 BitCPM-CANN-1B/3B as controls) — that replaces every "est." in §7; (b) run the actual judged prompt set through #1,
#2, #3 with thinking on/off and score; (c) verify Q4_0-pure vs Q8_0 perplexity for the 1B picks; (d) confirm chat template + thinking
toggle behave through `llama-cpp-python` (0.3.34 and 0.3.35).

---

## 9. Sources (fetched 2026-08-17)

BitCPM-CANN: https://huggingface.co/openbmb/BitCPM-CANN-8B · https://huggingface.co/openbmb/BitCPM-CANN-8B-gguf ·
https://huggingface.co/openbmb/BitCPM-CANN-3B-gguf/tree/main · https://huggingface.co/openbmb/BitCPM-CANN-1B-gguf/tree/main ·
https://huggingface.co/openbmb/BitCPM-CANN-0.5B-gguf/tree/main · https://huggingface.co/openbmb/BitCPM-CANN-3B/raw/main/config.json ·
https://huggingface.co/openbmb/BitCPM-CANN-1B/raw/main/config.json · https://huggingface.co/collections/openbmb/bitcpm-cann
MiniCPM: https://github.com/openbmb/minicpm (README + assets/minicpm5/public_leaderboard_en.png, assets/minicpm4/benchmark.png,
benchmark4.1.png) · https://huggingface.co/openbmb/MiniCPM5-1B (+ config.json) · https://huggingface.co/openbmb/MiniCPM5-1B-GGUF/tree/main ·
https://huggingface.co/openbmb/MiniCPM4.1-8B · https://huggingface.co/openbmb/MiniCPM4-8B · https://note.com/humble_bobcat51/n/n17b71306372c
Qwen3.5: https://huggingface.co/Qwen/Qwen3.5-4B (+/raw/main/README.md, config.json) · https://huggingface.co/Qwen/Qwen3.5-2B ·
https://huggingface.co/Qwen/Qwen3.5-0.8B · https://huggingface.co/unsloth/Qwen3.5-{0.8B,2B,4B}-GGUF/tree/main ·
https://x.com/UnslothAI/status/2028463220063871426 · https://news.ycombinator.com/item?id=47219208 · https://github.com/ggml-org/llama.cpp/pull/19435 ·
https://github.com/ggml-org/llama.cpp/pull/19468 · https://ollama.com/library/qwen3.5:4b
Qwen3 / 2.5: https://arxiv.org/html/2505.09388v1 (Tables 17–20) · https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507 ·
https://huggingface.co/Qwen/Qwen3-4B-Thinking-2507 · https://huggingface.co/unsloth/Qwen3-{4B-Instruct-2507,1.7B,0.6B}-GGUF/tree/main ·
https://qwenlm.github.io/blog/qwen2.5-llm/ · https://huggingface.co/Qwen/Qwen2.5-3B-Instruct · https://huggingface.co/Qwen/Qwen2.5-{3B,1.5B}-Instruct-GGUF/tree/main ·
https://arxiv.org/pdf/2409.12122 (Qwen2.5-Math TR, table text extracted) · https://huggingface.co/Qwen/Qwen2.5-Math-1.5B-Instruct ·
https://huggingface.co/bartowski/Qwen2.5-Math-1.5B-Instruct-GGUF/tree/main
DeepSeek: https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B · https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-1.5B-GGUF/tree/main
Gemma: https://ai.google.dev/gemma/docs/core/model_card_4 · https://ai.google.dev/gemma/docs/core/model_card_3 ·
https://huggingface.co/unsloth/gemma-4-E4B-it-GGUF · https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF ·
https://huggingface.co/bartowski/google_gemma-3-{4b,1b}-it-GGUF/tree/main
Phi: https://huggingface.co/microsoft/Phi-4-mini-instruct · https://huggingface.co/microsoft/Phi-4-mini-reasoning ·
https://huggingface.co/unsloth/Phi-4-mini-instruct-GGUF/tree/main · https://huggingface.co/bartowski/microsoft_Phi-4-mini-reasoning-GGUF/tree/main
SmolLM3: https://huggingface.co/HuggingFaceTB/SmolLM3-3B · https://huggingface.co/unsloth/SmolLM3-3B-GGUF/tree/main
Liquid: https://huggingface.co/LiquidAI/LFM2.5-1.2B-Thinking · https://huggingface.co/LiquidAI/LFM2.5-1.2B-Instruct ·
https://huggingface.co/LiquidAI/LFM2.5-1.2B-Thinking-GGUF/tree/main · https://huggingface.co/LiquidAI/LFM2.5-2.6B ·
https://huggingface.co/bartowski/LiquidAI_LFM2.5-2.6B-GGUF · https://huggingface.co/LiquidAI/LFM2-2.6B · https://www.liquid.ai/lfm-license ·
https://www.marktechpost.com/2026/08/06/liquid-ai-lfm2-5-2-6b-on-device-agentic-model/ · https://www.marktechpost.com/2026/01/20/liquid-ai-releases-lfm2-5-1-2b-thinking-a-1-2b-parameter-reasoning-model-that-fits-under-1-gb-on-device/
Llama / Ministral / Granite / Falcon: https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct · https://huggingface.co/bartowski/Llama-3.2-{3B,1B}-Instruct-GGUF/tree/main ·
https://huggingface.co/unsloth/Ministral-3-3B-Instruct-2512-GGUF · https://huggingface.co/ibm-granite/granite-4.1-3b · https://huggingface.co/tiiuae/Falcon-H1-3B-Instruct
MobileLLM / Tiny Aya / HRM: https://huggingface.co/facebook/MobileLLM-R1.5-950M · https://huggingface.co/CohereLabs/tiny-aya-global ·
https://www.marktechpost.com/2026/02/17/cohere-releases-tiny-aya-a-3b-parameter-small-language-model-that-supports-70-languages-and-runs-locally-even-on-a-phone/ ·
https://github.com/ggml-org/llama.cpp/discussions/23415 (HRM-Text) · https://huggingface.co/sapientinc/HRM-Text-1B
African languages: https://arxiv.org/pdf/2601.06395 (AfriqueLLM; Tables 3, 7, 16, 17 extracted from PDF text) · https://huggingface.co/McGill-NLP/AfriqueGemma-4B ·
https://arxiv.org/abs/2406.03368 (IrokoBench) · https://arxiv.org/pdf/2604.20996 (AFRILANGTUTOR)
Landscape / 2026 releases: https://github.com/xigh/open-weight-models · https://www.premai.io/blog/best-lightweight-language-models-worth-running/ ·
https://tinyweights.dev/posts/best-small-language-models-2026/ · https://techgenyz.com/qwen-3-8-open-weights-release/ · https://github.com/QwenLM/Qwen3.6
Profiler / compatibility: https://raw.githubusercontent.com/Africa-Deep-Tech-Foundation/adtc-profiler/main/Dockerfile ·
https://raw.githubusercontent.com/Africa-Deep-Tech-Foundation/adtc-profiler/main/pyproject.toml · https://pypi.org/pypi/llama-cpp-python/json ·
https://api.github.com/repos/abetlen/llama-cpp-python/contents/vendor/llama.cpp?ref=v0.3.35 (and v0.3.34) ·
`opt/research/r4_x86_kernels.md` · `opt/results/audit_kernel_proxy.md` · `opt/llama.cpp/ggml/src/ggml-cpu/arch/x86/quants.c`
