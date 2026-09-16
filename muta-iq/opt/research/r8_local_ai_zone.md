# R8 — Local AI Zone census and ADTC model shortlist

**Research date:** 2026-09-13
**Decision question:** Which models in the full Local AI Zone catalogue are plausible replacements for Muta's fine-tuned Qwen2.5-1.5B GGUF under the ADTC laptop-LLM rules?
**Recommendation in one sentence:** Benchmark **LFM2.5-1.2B-Thinking Q4_0**, **MiniCPM5-1B converted to pure Q4_0**, and **Qwen3.5-2B Q4_0** first; the first two have the best chance of raising total score, while Qwen3.5-2B has the best chance of improving hidden science/general-reasoning answers.

## 1. Executive decision

This was a catalogue-wide screen, not a search for a few familiar model names. The live Local AI Zone snapshot contained **36,946 GGUF file records belonging to 16,811 distinct Hugging Face model repositories**. Every repository passed through a reproducible filter. The screen then inspected the primary model cards, actual Hugging Face file sizes, licences, quantization choices, and llama.cpp architecture compatibility of the serious survivors.

The top five models to put through the exact Muta bake-off are:

| Test order | Candidate | Exact deployment candidate | Why it may beat tuned Qwen2.5-1.5B | Main reason it may not |
|---:|---|---|---|---|
| **1** | **LFM2.5-1.2B-Thinking** | Official `Q4_0`, 695,751,680 bytes | About 29% smaller than the baseline GGUF, already in the profiler-friendly quant, MATH-500 87.96, GPQA-Diamond 37.86, IFEval 88.42 | Long reasoning can be truncated; LFM licence is not Apache-2.0 |
| **2** | **MiniCPM5-1B** | Convert official F16 to a **pure Q4_0**; keep the 688,065,920-byte official Q4_K_M as an accuracy control | Best public math-per-byte evidence in the small tier: MATH-500 91.60, AIME25 40.42, IFEval 80.41; Apache-2.0 and plain Llama architecture | No official Q4_0; conversion quality and output stopping must be verified |
| **3** | **Qwen3.5-2B** | `Q4_0`, 1,268,357,529 bytes | Strongest balanced knowledge/science candidate near this size: thinking MMLU-Pro 66.5 and GPQA 51.6; Apache-2.0 | Larger than the baseline and its GDN layers need exact-profiler timing |
| **4** | **Qwen3-1.7B** | `Q4_0`, approximately 1.078 GB | Conservative, mature llama.cpp path; MATH-500 93.4 in thinking mode and 73.0 without it | Thinking can loop; instruction following and science are weaker than Qwen3.5-2B |
| **5** | **LFM2.5-2.6B** | Official `Q4_0`, 1,593,894,912 bytes | AIME25 51.87 and strong instruction results in a relatively compact, CPU-oriented architecture | Always thinks, costs more RAM/TPS, and its card warns against knowledge-heavy use |

Two additional **accuracy-max** candidates deserve a second queue: **Ministral-3-3B-Reasoning-2512** and **Qwen3.5-4B**. They may win the qualitative judge chat, but their 2–2.6 GB files and slower decode make them much less likely to maximize the combined score. **LFM2.5-8B-A1B** is the interesting MoE wildcard: only about 1B parameters are active per token, but its 4.845 GB Q4_0 file consumes too much of the efficiency budget to recommend without a measured upset.

The catalogue's exciting **Spark-X2.5-1.7B/4B** models are **not presently submission-safe**. Spark support landed in llama.cpp after the profiler's pinned `b10175`; the pinned runtime does not recognize the `spark` architecture. They belong on a post-profiler-upgrade watchlist, not in the current submission set.[^18]

No public benchmark can prove that any of these models beats Muta's tuned model. The current internal bar is real and fairly strong: tuned Qwen2.5-1.5B Q4_K_M reached **77.8% ARC-Easy-500** and a vector-profile total of **84.1387**; it also scored **76/100** on Muta's synthetic math/science judge simulation. The recommendations above are challengers that have a defensible chance. Promotion still requires the same prompt set, template, token cap, sampler, and profiler binary.

## 2. What “all 10,000+ models” means

Local AI Zone is a GGUF **file catalogue**, so a model repository may appear in several rows—one for each quantization. On 2026-09-13 the site's live `gguf_models.json` yielded:

| Census measure | Count |
|---|---:|
| GGUF file records | **36,946** |
| Distinct `modelId` repositories | **16,811** |
| Text or MoE file records | 27,798 |
| Records marked CPU-eligible by the site | 6,898 |
| CPU-eligible repositories | 4,445 |
| CPU-eligible records no larger than 1 GiB | 916 |
| CPU-eligible records no larger than 2 GiB | 1,883 |
| CPU-eligible records no larger than 3 GiB | 4,789 |
| CPU-eligible records no larger than 4 GiB | 6,604 |

Snapshot provenance:

- Local AI Zone catalogue commit: [`5c14f670b799184d3805581c3a3ed40a85ba7300`](https://github.com/local-ai-zone/local-ai-zone.github.io/commit/5c14f670b799184d3805581c3a3ed40a85ba7300), dated 2026-09-13.
- Downloaded JSON SHA-256: `31e35f542a2798a8ac9e40fa4dd587bfe82ba0ac89e3b74c8c2afb9a238206c5`.
- Live catalogue source: [`gguf_models.json`](https://raw.githubusercontent.com/local-ai-zone/local-ai-zone.github.io/main/gguf_models.json).[^1]

### Screening funnel

The funnel used repository-level deduplication so a model with ten quant files was not counted as ten independent candidates.

| Stage | Repositories left | Rule |
|---|---:|---|
| Complete catalogue | **16,811** | Every distinct `modelId` in the live JSON |
| Relevant modality | **14,093** | Retain text and MoE models; remove vision/audio-only entries |
| Deployable size/quant envelope | **3,204** | At least one Q4_0, Q4_K_M, or IQ4_XS file between 0.25 and 5.5 GB |
| General reasoning/domain sanity | **2,012** | Remove obvious roleplay, uncensored-persona, translation-only, embedding, coding-only, game, and narrow-domain models |
| High-recall reasoning shortlist | **848** | Name/card evidence of instruct, reasoning, math, science, tutor, general chat, or a strong current base family |
| Primary-source verification set | **19** | Competitive size plus credible model card, usable GGUF, licence, and plausible runtime support |
| Immediate benchmark queue | **5** | Best expected ADTC total-score trade-off |

This is the defensible interpretation of “go through all models”: **all 16,811 repositories were mechanically screened**, and every high-potential family that survived was manually checked. It would be misleading to claim that 16,811 model cards were read line by line; many catalogue rows are duplicate quants, user merges, broken metadata, or clearly irrelevant specializations.

## 3. Competition constraints applied

The shortlist is shaped by the competition, not by a generic leaderboard.

1. **Hard deployment envelope.** The official challenge describes an Ubuntu 22.04, four-core, 8 GB CPU-only laptop and disqualifies models above the stated memory ceiling. The judges run the submitted GGUF offline through llama.cpp.[^2]
2. **Combined score, not accuracy alone.** Muta's working score model is `0.50 * accuracy + 0.30 * performance + 0.20 * efficiency - thermal penalty`. In the executable profiler, performance caps at 15 tok/s and efficiency falls linearly with RSS up to 7 GB.[^3]
3. **The exact profiler changes the best quant.** Its reference Dockerfile pins llama.cpp `b10175` and disables native, AVX, AVX2, AVX-512, FMA, and F16C for `llama-bench`. In that unusual build, Q4_0 retains an SSSE3 dot-product path while K-quants and IQ quants fall to generic scalar code. This makes a pure Q4_0 file much more attractive for scored throughput than the Q4_K_M files normally preferred for quality.[^3]
4. **Bare-model behavior matters.** The judge can chat with the submitted GGUF rather than Muta's orchestration layer. Chat template, default thinking state, stop tokens, verbosity, and identity therefore affect accuracy. A mathematically capable model that spends its whole 256-token answer budget on hidden or visible reasoning can score worse than a smaller model that follows the requested format.
5. **Math plus scientific reasoning is mixed-domain.** Pure math checkpoints are penalized when hidden questions ask for conceptual physics, chemistry, biology, experimental design, or correction of misconceptions. GPQA/MMLU-Pro and instruction-following evidence therefore matter alongside MATH/AIME/GSM8K.
6. **Architecture support is a hard gate.** A great model whose architecture was added after `b10175` is not merely slower; it may not load, which is a submission failure.

There remains a public rules inconsistency: the challenge page describes performance relative to the fastest submission, whereas the published profiler implements a fixed 15 tok/s reference. This report follows the executable profiler for decisions and flags the discrepancy rather than silently blending the two definitions.[^2][^3]

## 4. Why the catalogue metadata could not be trusted blindly

Local AI Zone is valuable for exhaustive discovery, but its hardware labels are heuristic. The site's calculator infers parameter count from repository names when possible, estimates it from file size otherwise, and marks a file CPU-friendly largely from quant type and a 4 GB file-size threshold.[^4] The fetcher can also estimate missing sizes.[^5]

That produced material errors in promising rows. Examples found during verification include:

- Gemma-4-E4B Q4_0 shown near 2.36 GB in the catalogue, while the actual Hugging Face file is 4,590,807,392 bytes.
- Nanbeige4.2-3B IQ4_XS shown near 1.67 GB, while the actual file is 2,403,808,096 bytes.
- NVIDIA Nemotron-3-Nano-4B Q4_K_M shown near 2.36 GB, while the actual file is 2,837,072,864 bytes.
- DeepSeek-R1-Distill-Qwen-1.5B shown near 856 MB, while the checked IQ4_XS file is 1,098,800,224 bytes.

For every finalist, this report therefore uses the Hugging Face repository API/file listing rather than the catalogue's estimated size. “GPU required: false” is treated as a discovery hint, not evidence that the model satisfies the 7 GB whole-process RSS limit.

## 5. Baseline to beat

Muta's current strongest candidate is not generic Qwen2.5-1.5B; it is the project's **fine-tuned** Qwen2.5-1.5B-Instruct Q4_K_M. That distinction raises the bar.

| Evidence | Current tuned Qwen2.5-1.5B result |
|---|---:|
| ARC-Easy-500 `acc_norm` | **77.8%** (control 74.4%) |
| Synthetic math/science judge simulation | **76/100** |
| Scalar proxy | 5.63 tok/s, 1,117 MiB RSS, **67.0475 total** |
| Vector proxy | 17.44 tok/s, 1,706 MiB RSS, **84.1387 total** |
| GGUF size | 986,048,128 bytes |

The scalar/vector split is important. The baseline's Q4_K_M is excellent on a normal AVX2 host but heavily penalized by the official no-AVX throughput build. That opens a scoring route for a smaller pure-Q4_0 challenger even if its accuracy is only similar. Conversely, on a normal vector build where both models exceed 15 tok/s, the challenger must win primarily through accuracy and a smaller RSS.

At 15 tok/s and 0.9 GB RSS, a challenger needs roughly **73.4 accuracy points** to exceed the current 84.1387 vector total under Muta's formula. That is a useful promotion floor, not a forecast: real candidate RSS and accuracy must replace the assumptions.

## 6. Ranked shortlist

### Tier A — benchmark immediately

#### 1. LFM2.5-1.2B-Thinking — best ready-to-run challenger

The official Q4_0 is 695,751,680 bytes, about 290 MB smaller than Muta's baseline GGUF, and `lfm2` is supported by the pinned llama.cpp. Liquid reports MATH-500 87.96, GSM8K 85.60, AIME25 31.73, MMLU-Pro 49.65, GPQA-Diamond 37.86, and IFEval 88.42. Its reasoning traces are also reported to use fewer tokens than Qwen3-1.7B on the compared tasks.[^7]

Why it is first: this is the only candidate combining a strong public math/reasoning profile, high instruction following, an **official** profiler-friendly Q4_0, sub-700 MB storage, and mature llama.cpp support. It has a realistic route to beat Qwen2.5 both on total score and on the two target categories.

Risks: the Thinking checkpoint may lose judged answers to truncation; the non-thinking Instruct sibling is much weaker on math; and the LFM Open Licence v1.0, while allowing broad use below its revenue threshold, is not Apache-2.0.[^8] Run both siblings, but expect Thinking to be the competitive one.

#### 2. MiniCPM5-1B — best expected score after the right conversion

MiniCPM5 is a 1.08B-parameter on-device model with only about 0.68B non-embedding parameters, a standard Llama architecture, hybrid thinking, and Apache-2.0 licensing. OpenBMB reports an average reasoning score of 42.57, with MATH-500 91.60, AIME25 40.42, MMLU-Pro 48.85, MMLU-Redux 70.06, GPQA 26.26, and IFEval 80.41. The training recipe explicitly targeted overlong reasoning, reducing max-token failures in the authors' comparison.[^6]

The official GGUF repository has a 688,065,920-byte Q4_K_M, but no Q4_0. Under ordinary llama.cpp the Q4_K_M would be a sensible choice; under this profiler it misses the surviving fast Q4_0 path. The competitive deployment candidate is therefore a **pure Q4_0 conversion from official F16**, expected around 0.62 GB, with the vocabulary/output tensors deliberately audited rather than accidentally left in a slow mixed quant. The official Q4_K_M should remain an accuracy control.

Why it is second rather than first: it may ultimately be the winner, but the required custom conversion adds a quality and reproducibility gate that LFM2.5 does not have. It also has weaker published GPQA than LFM/Qwen3.5, which matters for scientific reasoning.

#### 3. Qwen3.5-2B — best balanced hidden-science candidate

Qwen3.5-2B is the strongest small candidate when the hidden distribution extends beyond school arithmetic into general science knowledge and conceptual reasoning. Its card reports thinking-mode MMLU-Pro 66.5, MMLU-Redux 79.6, GPQA 51.6, IFEval 78.6, and multilingual MMLU 63.1. It is Apache-2.0 and supports thinking/non-thinking behavior.[^9]

The preferred Q4_0 is 1,268,357,529 bytes. That is about 29% larger than the existing baseline and materially larger than the first two picks, so it needs a clear accuracy gain. It also uses Qwen3.5's hybrid GDN/attention architecture. `b10175` knows `qwen35`, but recognition is not the same as good performance in the profiler's generic build. Time-to-first-token, decode, and recurrent-state memory must be measured.

Use Qwen3.5-2B when the priority is the highest probability of better judge-chat answers across math **and** science, not merely the best projected throughput score.

#### 4. Qwen3-1.7B — lowest architecture-risk alternative

Qwen3-1.7B is the conservative fallback: Apache-2.0, conventional transformer architecture, broad llama.cpp support, and a large ecosystem. The published card supports hybrid thinking and reports strong reasoning; Muta's earlier primary-source transcription records MATH-500 93.4 in thinking mode and 73.0 without thinking.[^10]

Use the approximately 1.078 GB Q4_0 rather than IQ4_XS/Q4_K_M for the scored no-AVX binary. The key operational risk is generation behavior: Qwen warns that greedy decoding can cause repetition or performance degradation, while the judge/profiler may use settings the team does not control. Test the embedded template under the exact server defaults and enforce a clean final answer before the cap.

#### 5. LFM2.5-2.6B — strong upper-middle experiment

The official Q4_0 is 1,593,894,912 bytes. Liquid reports AIME25 51.87 and strong instruction/agentic results from a 2.69B model designed for on-device use.[^11] This offers a plausible quality step above the 1.2B model without entering the 2.5–5 GB penalty zone.

It is fifth because the checkpoint always reasons, so output-cap behavior is central, and its own card says it is not recommended for knowledge-heavy tasks. That warning directly overlaps the scientific-reasoning category. It should advance only if it materially beats the 1.2B sibling on Muta's physics, chemistry, biology, and experiment-design subsets.

### Tier B — accuracy-max and wildcards

| Candidate | Preferred file | Evidence for inclusion | Why it is below Tier A |
|---|---:|---|---|
| **Ministral-3-3B-Reasoning-2512** | Q4_K_M, 2,147,021,472 bytes | Official results include AIME25 72.1%, AIME24 77.5%, GPQA-Diamond 53.4%; designed for STEM reasoning[^12] | Q4_K_M is slow in the audit build; system prompt explicitly emits a full `[THINK]` block before the answer, creating severe cap risk[^13] |
| **Qwen3.5-4B** | Q4_0, 2,583,221,408 bytes | Strong public all-round ceiling: MMLU-Pro 79.1, GPQA 76.2, IFEval 89.8 in the project's verified transcription | Likely 5–6 tok/s in the generic build; must gain roughly 40+ accuracy points over the 1B score leaders to repay the performance/efficiency loss |
| **Nanbeige4.2-3B** | IQ4_XS, 2,403,808,096 bytes | Base card reports GSM8K 92.7, BBH 81.6, MMLU-Pro 63.8, GPQA 53.3; post-trained card reports stronger reasoning[^14] | Recurrent loop architecture makes active compute larger than file size suggests; no preferred Q4_0; unusually strong claims need independent reproduction |
| **LFM2.5-8B-A1B** | Q4_0, 4,844,678,368 bytes | MoE with roughly 1B active parameters; reported MATH-500 88.76, AIME25 42.53, IFEval 91.84[^15] | 4.51 GiB just for weights leaves little efficiency headroom and creates RSS/KV risk; active-parameter speed must be proven in b10175 |
| **NVIDIA Nemotron-3-Nano-4B** | Q4_K_M, 2,837,072,864 bytes | Modern reasoning-oriented hybrid; b10175 recognizes `nemotron` | Generic-quant penalty, 2.84 GB file, and no compelling verified accuracy-per-byte win over Qwen3.5-2B |
| **SmolLM3-3B** | Q4_K_M, 1,915,305,312 bytes | Mature `smollm3` support and an official GGUF | Older/lower public reasoning ceiling than the leading 1–2B candidates, with a slower quant in the audit build |
| **Jan-v3.5-4B** | Q4_0, 2,588,332,896 bytes | Qwen3-4B base, math/identity fine-tuning, Apache-2.0[^17] | Model card does not publish enough quantitative evaluation; personality training may conflict with the tutor persona |
| **Qwen3.8-2B-Distill** | Q4_K_M, 1,312,164,224 bytes | Community distillation of Qwen3.5-2B with reported GSM8K and MMLU improvements[^16] | Not an official Qwen release; every answer is trained to open with reasoning and the author recommends 16K output, a poor match for the judge cap |

### Tier C — controls, narrow specialists, or exclusions

- **DeepSeek-R1-Distill-Qwen-1.5B:** useful reasoning control, but always-thinking behavior and modest mixed-science evidence make it less attractive than the newer 1–2B models.
- **Qwen2.5-Math-1.5B-Instruct:** potentially strong on calculation, but the model card discourages non-math use and its context is limited. It is not a sensible replacement for a mixed math/science tutor.
- **Qwen2.5-3B-Instruct:** older and larger, without an accuracy-per-byte case against Qwen3.5-2B.
- **Gemma-4-E4B:** the actual Q4_0 is 4,590,807,392 bytes, not the much smaller catalogue estimate; the published math case is not strong enough to repay that size.
- **BitCPM-CANN ternary family:** attractive file sizes, but the profiler's generic CPU kernel removes the expected ternary-speed advantage. The 1B/3B accuracy evidence is also below the new dense small-model leaders.
- **Coding, roleplay, uncensored, translation, embedding, vision-only, and narrow-domain merges:** removed because they do not fit the selected competition categories or consume capacity on irrelevant behavior.

### Watchlist — strong models that currently fail the runtime gate

Spark-X2.5-1.7B and Spark-X2.5-4B publish very strong 2026 math/reasoning results, including AIME/HMMT/GPQA gains at unusually small sizes. Their official Q4_K_M files are 1,107,457,856 and 2,600,224,352 bytes respectively. However, llama.cpp's Spark architecture support merged in PR #27868 on 2026-09-06, while the competition profiler is pinned to `b10175`, whose architecture table has no `spark` entry.[^18] Unless the organiser updates the pinned runtime, these models are expected not to load. A future profiler revision could immediately move Spark-X2.5-1.7B into Tier A.

## 7. Quantization and reasoning-mode decisions

### Prefer Q4_0 for the submitted speed artifact

For this competition only, the profiler build makes **pure Q4_0** the default performance choice. That does not mean Q4_0 is universally better. For normal Muta deployment on AVX2, Q4_K_M or IQ4_XS may retain more quality for a modest speed/memory cost. Maintain two labelled artifacts if needed:

- **Audit candidate:** pure Q4_0, measured with the exact b10175 reference build.
- **Product-quality control:** official Q4_K_M/IQ4_XS, measured on the real target laptop.

Do not assume a filename containing `Q4_0` is pure. Inspect the GGUF tensor-type histogram; mixed output/embedding tensors may dominate a small model and can land on the generic path.

### Thinking is not simply “on by default in llama-server”

llama-server does not have one universal reasoning mode. Behavior comes from the model's embedded chat template, template arguments, and sampling/request fields. Some checkpoints always produce reasoning; some support `enable_thinking`; some default to non-thinking; others expose reasoning in visible text. The profiler's accuracy harness can also bypass the chat template for multiple-choice log-likelihood evaluation.

For each candidate record four separate results:

1. raw log-likelihood/MC accuracy with the profiler path;
2. judge-style chat at the profiler/server defaults;
3. explicit thinking enabled, if supported;
4. explicit thinking disabled, if supported.

Any candidate that fails to reach a concise final answer within both 256 and 512 generated tokens should be rejected or have its template fixed before accuracy comparisons.

## 8. Recommended bake-off

### Round 0 — load and compliance gate

For every Tier A model:

- confirm the exact GGUF loads in llama.cpp `b10175`;
- inspect architecture, tensor quant counts, embedded template, BOS/EOS/stop tokens, licence, and exact byte size;
- run under the 7 GB whole-process RSS cap with `-ngl 0`;
- reject any illegal architecture, infinite reasoning loop, missing answer, or memory breach.

### Round 1 — exact profiler performance

Run the same b10175, compiler flags, `llama-bench -p 512 -n 128`, thread policy, and cold/warm protocol already used by the fine-tuning campaign. Record prompt processing, token generation, peak RSS for the whole child tree, and temperature/throttling on the physical target. No published vendor tok/s is comparable.

### Round 2 — matched accuracy

Use the same evaluation harness and no data leakage:

- ARC-Easy-500 for continuity with the 77.8% baseline;
- the existing 100-prompt Muta judge simulation;
- a new held-out 100-prompt battery balanced across arithmetic, algebra, geometry, probability, units, conceptual physics, chemistry, biology, experimental design, misconception correction, and concise tutoring;
- explicit 256- and 512-token generation-cap conditions;
- blinded human grading for correctness, working, instruction following, pedagogy, and unsupported claims.

Published MATH/AIME results are screening evidence only; they must not be substituted for this matched battery.

### Round 3 — tuning fairness

If an untuned challenger comes within five points of the tuned baseline on the matched accuracy battery, fine-tune it with the same leakage controls, licence-clean ARC/QASC-style data, completion formatting, and compute budget. Comparing an untuned challenger to a tuned incumbent is appropriate for discovery but not the final architecture decision.

### Promotion rule

Promote a candidate only when it satisfies all of the following:

1. no hard runtime, RAM, licence, or output-termination failure;
2. at least **74%** on the matched 100-point accuracy scale if it saturates 15 tok/s near 0.9 GB RSS, or a recalculated threshold using its measured TPS/RSS;
3. no more than a two-point regression in either math or science separately;
4. a measured combined score above **84.1387** on the same profile, or above the final physical-laptop baseline if that changes;
5. three clean repeated runs without thermal throttling.

## 9. Final recommendation

The best immediate decision is a **three-model shoot-out**:

1. **LFM2.5-1.2B-Thinking Q4_0** — most practical probability of beating the current total score today.
2. **MiniCPM5-1B pure Q4_0** — highest expected score-per-byte if the custom quant preserves its published advantage.
3. **Qwen3.5-2B Q4_0** — strongest hedge against harder hidden science/general-reasoning questions.

Add **Qwen3-1.7B Q4_0** as the low-risk architecture control and **LFM2.5-2.6B Q4_0** as the upper-quality experiment. Do not spend target-box time on the 4B–8B tier until at least one of the three leading small candidates has a measured accuracy shortfall large enough to justify the projected 15–25 point performance/efficiency sacrifice.

If only one model can be downloaded first, choose **LFM2.5-1.2B-Thinking Q4_0**. If the licence constraint requires Apache-2.0, choose **MiniCPM5-1B**, make and validate the pure-Q4_0 conversion, then test **Qwen3.5-2B Q4_0**. If the organiser updates llama.cpp beyond PR #27868, immediately retest **Spark-X2.5-1.7B**.

## 10. Limitations

- Vendor benchmark suites, prompts, answer extraction, sampling, and thinking budgets differ; cross-card numbers establish plausibility, not winners.
- Local AI Zone changes daily. The commit and SHA above make this census reproducible, but later models are outside the snapshot.
- Some GGUF sizes came from repository file listings rather than downloading every multi-gigabyte file; the final bake-off must hash the exact artifacts.
- TPS projections from model size/architecture are not measurements. Only the pinned profiler and physical target produce score-of-record performance.
- The project's 100-prompt simulation is useful but synthetic; it cannot reproduce the judges' hidden questions or qualitative discretion.
- The competition page and profiler disagree on the performance normalization rule. Both favor small fast models, but the size of the advantage differs.
- The competition deadline predates this research date. This document is a retrospective/re-run decision aid unless the organiser has reopened or extended evaluation.

## Sources

[^1]: Local AI Zone, live catalogue and repository documentation: [site](https://local-ai-zone.github.io/), [GitHub repository](https://github.com/local-ai-zone/local-ai-zone.github.io), and [catalogue JSON](https://raw.githubusercontent.com/local-ai-zone/local-ai-zone.github.io/main/gguf_models.json).
[^2]: Africa Deep Tech Foundation, [ADTC 2026 challenge page](https://africadeeptech.org/challenge-2026/) and [Devpost rules](https://adtc-2026.devpost.com/rules).
[^3]: Africa Deep Tech Foundation, [official profiler repository](https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler) and [reference Dockerfile](https://raw.githubusercontent.com/Africa-Deep-Tech-Foundation/adtc-profiler/main/Dockerfile).
[^4]: Local AI Zone, [`hardware_calculator.py`](https://raw.githubusercontent.com/local-ai-zone/local-ai-zone.github.io/main/spam_filter/hardware_calculator.py).
[^5]: Local AI Zone, [`daily_gguf_fetcher.py`](https://raw.githubusercontent.com/local-ai-zone/local-ai-zone.github.io/main/scripts/daily_gguf_fetcher.py).
[^6]: OpenBMB, [MiniCPM5-1B model card](https://huggingface.co/openbmb/MiniCPM5-1B) and [official GGUF files](https://huggingface.co/openbmb/MiniCPM5-1B-GGUF/tree/main).
[^7]: Liquid AI, [LFM2.5-1.2B-Thinking model card](https://huggingface.co/LiquidAI/LFM2.5-1.2B-Thinking) and [official GGUF files](https://huggingface.co/LiquidAI/LFM2.5-1.2B-Thinking-GGUF/tree/main).
[^8]: Liquid AI, [LFM Open Licence v1.0](https://huggingface.co/LiquidAI/LFM2.5-1.2B-Thinking/blob/main/LICENSE).
[^9]: Qwen, [Qwen3.5-2B model card](https://huggingface.co/Qwen/Qwen3.5-2B) and Unsloth, [Qwen3.5-2B GGUF files](https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/tree/main).
[^10]: Qwen, [Qwen3-1.7B model card](https://huggingface.co/Qwen/Qwen3-1.7B) and Unsloth, [Qwen3-1.7B GGUF files](https://huggingface.co/unsloth/Qwen3-1.7B-GGUF/tree/main).
[^11]: Liquid AI, [LFM2.5-2.6B model card](https://huggingface.co/LiquidAI/LFM2.5-2.6B) and [official GGUF files](https://huggingface.co/LiquidAI/LFM2.5-2.6B-GGUF/tree/main).
[^12]: Mistral AI, [Ministral-3-3B-Reasoning-2512 model card](https://huggingface.co/mistralai/Ministral-3-3B-Reasoning-2512) and [GGUF files](https://huggingface.co/mistralai/Ministral-3-3B-Reasoning-2512-GGUF/tree/main).
[^13]: Mistral AI, [Ministral reasoning system prompt](https://huggingface.co/mistralai/Ministral-3-3B-Reasoning-2512/blob/main/SYSTEM_PROMPT.txt).
[^14]: Nanbeige, [Nanbeige4.2-3B-Base model card](https://huggingface.co/Nanbeige/Nanbeige4.2-3B-Base) and [Nanbeige4.2-3B post-trained model card](https://huggingface.co/Nanbeige/Nanbeige4.2-3B).
[^15]: Liquid AI, [LFM2.5-8B-A1B model card](https://huggingface.co/LiquidAI/LFM2.5-8B-A1B) and [GGUF files](https://huggingface.co/LiquidAI/LFM2.5-8B-A1B-GGUF/tree/main).
[^16]: Empero AI, [Qwen3.8-2B-Distill model card](https://huggingface.co/empero-ai/Qwen3.8-2B-Distill) and [GGUF files](https://huggingface.co/empero-ai/Qwen3.8-2B-Distill-GGUF/tree/main).
[^17]: Jan, [Jan-v3.5-4B model card](https://huggingface.co/janhq/Jan-v3.5-4B-gguf).
[^18]: llama.cpp, [Spark architecture support PR #27868](https://github.com/ggml-org/llama.cpp/pull/27868) and [`b10175` architecture table](https://raw.githubusercontent.com/ggml-org/llama.cpp/b10175/src/llama-arch.cpp).
