# R7 — Competitive intel: ADTC 2026 Laptop LLM track (as of 2026-08-17)

Scope: Devpost hackathon site (overview / rules / resources / updates / forum / project gallery), the ADTF microsite (challenge page, FAQ, leaderboard), the `adtc-profiler` and `adtc-2026-submission-template` GitHub repos (commits, PRs, issues), **all 99 forks** of the submission template plus **~60 non-fork repos** found via GitHub repo search (`adtc-2026`, `adtc 2026`, `Africa Deep Tech Challenge`, `adtc laptop llm`, `laptop llm challenge`, `adtc2026`), GitHub code search for `african_alpha_claim`, Hugging Face model search `adtc`, ADTC Substack, press (TechAfrica News / Techpoint / TechTrends KE), and general web/X/LinkedIn search.

Legend: **[V]** = verified by fetching the primary source; **[I]** = inference / my reading. Quotes are verbatim.

---

## 0. TL;DR

1. **No public leaderboard numbers exist yet.** The ADTF "Asante Benchmark Leaderboard" (`africadeeptech.org/challenge-2026/leaderboard`) is live but returns `runs: []` ("No published runs found matching search criteria."). Its client bundle renders `run_id`, `submitter_name`, `team_id`, `metrics.rss_peak_gb`, `metrics.tps`, `scores.total` — so the public board will show **peak RSS (GB), tok/s and total score** per run. The Devpost project gallery is unpublished ("The hackathon managers haven't published this gallery yet"). **[V]**
2. **Field size:** Devpost shows **1,679 participants**; the template has **99 forks**; I found **~110 ADTC-2026 repos** on GitHub, **77 with a `metadata.json`**, **65 with a non-template model declared**. Only **2 of 65** declare `math_scientific_reasoning` (both 1.5B Q4_K_M: DeepSeek-R1-Distill-Qwen-1.5B and Qwen2.5-Math-1.5B). Domain split of the 65: agriculture 22, healthcare 13, corporate 12, coding 9, agents 5, math 2, creative 2. **[V]**
3. **What competitors ship:** overwhelmingly **Qwen2.5 (28/65)**, **Q4_K_M (55/65)**, **median 1.8B params** (bucket counts: <1B: 11, 1–2B: 23, 2–4B: 21, 4–5B: 5, ≥5B: 3). Only 5 teams use anything other than Q4_K_M/Q4_0 (IQ4_XS ×2, IQ3_XS, IQ2_M, Q5_K_M). Nobody else is doing ternary/TQ, vocab pruning, SVD, or custom kernels; the "optimisation" frontier among competitors is imatrix Q4_K_M, IQ4_XS, and LoRA fine-tuning. **[V]**
4. **Self-reported tok/s are mostly measured on the wrong build** (AVX2/NEON laptops, Apple M1, Ollama). Only **~5 teams** noticed the audit image is scalar (`GGML_AVX/AVX2/FMA/F16C=OFF`) and measured on it: 3B Q4_K_M → **2.75 tok/s** (i7-1185G7, 4 CPUs), 1.5B Q4_K_M → **3.49 tok/s** (x86 runner), Qwen3-1.7B Q4_0 → **9.4 tok/s** and Llama-3.2-1B Q4_0 → **12.81 tok/s** (i7-1165G7, `--cpus=4`), Qwen3-0.6B Q4_0 → **20.33 tok/s** (EPYC 7763, 4 cores). Fastest self-report of any kind: **Gemma 3 270M Q4_K_M at 44.32 tok/s / 382 MB peak** (build unknown). **[V]**
5. **S_perf definition is contradictory across organiser sources** and **no organiser has clarified it**: Devpost overview says `100 × (TPSact ÷ TPSmax)` with the note "TPS_REFERENCE = 15.0 provisional"; Devpost judging criteria say "Evaluated relative to the maximum observed tokens per second"; the ADTF site says "Generation speed relative to the fastest submission across all teams … TPSmax: highest speed across all submissions"; the profiler README **and code** implement `min(TPS / TPS_REFERENCE, 1.0) * 100` with `TPS_REFERENCE = 15.0`. Competitors are split; the most careful ones (baarali-edge, husseinalamutu, kish-00) explicitly plan for the relative-to-fastest reading and note a 135M/270M entrant could set TPS_max very high. **[V]**
6. **No organiser statement about AVX2 exists anywhere public.** The only source is the profiler `Dockerfile` (`LLAMACPP_REF=b10175`, all SIMD flags OFF, comment: "CPU-only, for parity with Standard Laptop profile"). The forum bug report about `accuracy.py` (v0.1.0) is **unanswered**; the profiler's last commit is 2026-08-15 (`fix(packaging): lower minimum Python requirement to >=3.10`). **[V]**
7. **Common mistakes observed in the field:** placeholder `team_id` (12 repos), template test prompts left unchanged (9), `parameters_estimate` inconsistent with model name (8, incl. two "135M" for 8–9B models — will fail the profiler's ±15% GGUF fraud check), invalid `metadata.json` (2), extra top-level keys, self-reports from GPU/Apple/Ollama, submission.json with `throttled: true` at 92 °C, and REPORT numbers that contradict the committed `submission.json` (e.g., 12.18 tok/s claimed vs 1.23 tok/s in the file). **[V]**

---

## 1. Organiser clarifications and rules (verbatim where it matters)

### 1.1 Devpost overview — scoring table (`https://adtc-2026.devpost.com/`) **[V]**

> Stotal = 0.50⋅Sacc+0.30⋅Sperf+0.20⋅Seff−Pthermal
>
> Sacc | 50% | Weighted average of model response scored between 0 and 100 by a Judge. | Weighted combination of automated benchmark scores and qualitative assessment of model prompt responses by the judge panel.
> Sperf | 30% | 100 × (TPSact ÷ TPSmax) | TPS_REFERENCE = 15.0 provisional
> Seff | 20% | Seff = 100 × ((7 GB − Peak RAM) ÷ 7 GB) | Rewards lower RAM usage. The less memory consumed relative to the 7 GB budget, the higher the score. Peak RAM = 7 GB
> Pthermal | -10 points | -10 if throttled or temp > 85°C | Else 0

Judging criteria block (Devpost overview + `/rules`):
> Model Accuracy & Quality — 50% — A combination of multiple-choice benchmarks and qualitative evaluations that includes accuracy of prompts, quality of documentation
> Model Throughput Performance — 30% — Evaluated relative to the maximum observed tokens per second
> Model Efficiency — 20% — Rewards lower RAM utilization profiles relative to the maximum memory budget
> African Use Case Bonus — Bonus — Up to 10 extra points awarded for how applicable the model is to a real African use case
> Hardware & Thermal Penalties — Penalty — 10 points deducted if core/package temperature exceeds 85∘C or if thermal throttling is flagged. OOM or sandbox execution crash results in disqualification

Standard laptop table: "Intel Core i5 10th–12th gen OR AMD Ryzen 5 3000–5000 (x86-64) | 8 GB DDR4 | Integrated only … No discrete GPU | 256 GB SSD | Ubuntu 22.04 LTS".

Dates (`/rules`): "Tue August 25, 2026 — Gate 1 Deadline — Proposals + prototypes submitted. Two-step judging: proposal screen, then prototype review of the top ~10%." → "Tue Sept 8, 2026 — Semifinalists Announced — Up to 20 teams notified. Gate 2 narrowing audit begins." → "Tue Sept 22 — Semifinalist Submission" → "Tue Sept 29 — Finalists Announced — Up to 10 teams advance to Live Defense" → "Sat, Oct 17, 2026 — Live Defense & Awards". Devpost header: "Deadline: Aug 24, 2026 @ 11:45pm PDT". Prizes: $8,000 / $4,000 / $3,000 / $1,500 (Best African Use Case) + GPU-credit stipends; "Direct pathway into the Africa AI XPrize".

Note the wording "prototype review of the top ~10%" — with 1,679 registrants the Gate-1 proposal screen is likely to be a docs/report screen first. **[I]**

### 1.2 ADTF microsite (`https://africadeeptech.org/challenge-2026/`) — Scoring Model + FAQ **[V]**

Scoring model section:
> Speed (Sperf) — Generation speed relative to the fastest submission across all teams. Sperf = 100 × (TPSact ÷ TPSmax). TPSact: actual tokens/sec during audit · TPSmax: highest speed across all submissions
> Efficiency (Seff) … Peak RAM: maximum RSS measured during audit · Budget = 7 GB
> −10 Thermal Penalty … 0 OOM / Crash → Disqualified … Out-of-memory or sandbox crash results in Stotal = 0 and immediate disqualification.
> Score multipliers — Budget Profile +10% · African Language +15%
> African Alpha Bonus — Submissions with meaningful functionality in at least one African language earn +15% on their panel score.
> Memory ceiling — 7 GB RAM — Exceeding this limit results in immediate disqualification (Stotal = 0).

FAQ (verbatim, the load-bearing ones):
> **How does offline/local judging execution work?** Judging is done by actually running your submitted model, not by reading a transcript or a static output log. When a judge opens your run, we spin up a fresh sandboxed instance of your exact submission inside an environment resource-capped to match the Standard Laptop profile (8 GB RAM, 4 CPU cores), and the judge chats with it live through our in-browser interface. There's no third-party tool involved on the judge's side — your score reflects how your model actually behaves under the real target hardware constraints.
> **How are the telemetry and qualitative scores calculated?** … S_perf (Performance) and S_eff (Efficiency) are calculated automatically by running inference on standard target laptops. S_acc (Accuracy) is a qualitative evaluation graded by our judging panel.
> **What specific tools or frameworks are allowed for quantization and deployment?** llama.cpp only. All submissions must run through llama.cpp using GGUF weights to ensure compatibility with our evaluation setup.
> **What is the maximum allowed size for the model?** There is no strict maximum size limit. However, your model will be evaluated entirely on its performance and efficiency on the standard benchmark computer (8 GB RAM). Keep memory constraints in mind to avoid OOM disqualification.
> **What exactly do I need to submit for evaluation?** Just your model repository with a working `download_model.sh`, plus your two required test prompts. You are not required to run or submit any accuracy benchmarking yourself — you only need to produce your own performance and efficiency telemetry locally as a self-check (throughput, memory, thermal). Accuracy (S_acc) is scored entirely by the judging panel, who run your actual model — you never submit an accuracy number.
> **What do I enter for "Self Reported Profiler Performance Score (Sperf)" and "… (Seff)" on DevPost?** These are two separate numeric fields on the DevPost submission form — enter one plain number in each, not a combined string like "Sperf=46, Seff=41". Your local profiler's `submission.json` gives you raw numbers, not the normalized 0–100 score, so compute each score yourself from your own run, then enter the resulting number in each field.
> **Does evaluation measure my whole application, or just the model?** Just the model. Automated profiling and resource limits (memory, throughput, thermal) apply only to the LLM inference process itself (llama.cpp running your GGUF model) — we do not measure or enforce resource limits on any supporting application stack (CV, audio, sensing, etc.). Judging is also scoped to the model's responses, not a broader application UI.
> **What exact benchmarks and prompts will be used for grading accuracy?** You will provide two test prompts with your submission. The organizers will then generate three additional hidden prompts within your chosen domain to test for response accuracy.
> **How will core temperatures and thermal throttling be monitored during testing?** We capture the device's temperature immediately before and immediately after each benchmark run. For multiple runs, we introduce a cooldown delay between them and confirm the system has returned to its baseline temperature before starting the next one … A 10-point thermal penalty applies if the CPU throttles or the peak core temperature exceeds 85°C.
> **Are hybrid approaches allowed…?** The model must run 100% offline with zero external network dependencies during our testing window.
> **What qualifies an entry for the "African Use Case Bonus"?** The bonus rewards any solution that clearly caters to real-world African contexts and infrastructure realities. Supporting a local language is not a requirement—the primary language of evaluation for this competition is English.
> **Where do I get my ADTC Team ID for metadata.json?** Your Team ID is generated automatically when you register your team on DevPost — use that same ID in your submission's `metadata.json`.
> **Can I use fine-tuned open-source models?** Yes. You are encouraged to use open-source base models (e.g. Llama, Mistral), quantize them, fine-tune them on local data, and compile them for local CPU runtimes.
> **What does cross-disciplinary actually mean?** Your local LLM must connect to another deep-tech discipline in a load-bearing way. Examples include offline RAG over agricultural records, edge sensing, geospatial analysis, or local medical diagnostic assistance.

Gate deliverables (ADTF site): Gate 1 "Open-source GitHub repo (ADTC 2026 submission template); REPORT.md — problem definition, constraints, design decisions, tools & benchmarks; Screenshots or short video clips …; 2-minute video …; Bonus claims: African language support / budget laptop". Gate 2 (Sept 8–29): "Technical reproducibility audit and technical Q&A session … 30-minute technical Q&A session (scheduled); Prompt responses to reviewer clarification requests; Optional: 1-page response to feedback; Optional: updated benchmark report". Gate 3: pitch deck (max 10 slides), live defense.

Inconsistency to note: the **submission-template README** says "Organizers will generate 2 additional hidden prompts within your domain. All 4 are used for scoring." while the ADTF FAQ says "three additional hidden prompts". Either way: **2 own + 2–3 hidden in-domain prompts, judged live by humans in a 4-core/8 GB sandbox, English primary.** **[V]**

### 1.3 Devpost forum — organiser answers (`/forum_topics`) **[V]**

- *"Model Profiler Repository Link Returns 404"* (about 2 months ago) — Manager: "This is the correct URL … Profiler: https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler — Submission Template: https://github.com/Africa-Deep-Tech-Foundation/adtc-2026-submission-template … Also feel free to reach out through the discord channel: https://bit.ly/adtc_discord".
- *"Clarification if App should work completely offline?"* — Manager: **"For the first round, we will only be testing your model, and it has to work completely offline."**
- *"Team ID"* — Manager: **"The team ID in this context means the project ID. E.g for this Devpost project (https://devpost.com/software/project-farmspeak) it is : project-farmspeak"**. (A follow-up from a solo participant 5 days ago is unanswered.)
- *"Bug Report: adtc-profiler v0.1.0 accuracy.py"* (Ahmed Madi, ~1 month ago, **0 comments**): reports (1) hardcoded `base_url=local` making lm_eval fail, (2) "Missing `--apply_chat_template` degrades accuracy … our model scored 0.12 acc_norm on arc_easy, where random guessing is ~0.25", and asks "Are participants permitted to submit submission.json with an empty accuracy array … using the --skip-accuracy flag for Gate 1, since the official audit utilizes a hidden validation set?" — **no organiser reply.**
- *"where to access the provided validation set, accuracy scoring format"* (7 days ago, **0 comments**): asks whether Sacc is MC/loglikelihood like arc_easy or free-text judged; where the promised "validation sets are provided for each" domain are. **No organiser reply.**
- *"Eligibility: individual submission …"* — Manager: "you are eligible if the project was built from scratch for this challenge and the IP does not belong to your business entity that has been in existence for more than 12 months."
- *"Than $5 is not enough to do any serious training"* — complaint about GPU credits, no reply.

### 1.4 Devpost updates (`/updates`) **[V]**

- **"Important Updates to Submission Form: Separate fields for profiler scores"** (16 days ago): "The submission form has been updated to enable you to enter the self-reported profiler scores in separate fields. Self-Reported Profiler Performance Score (Sperf) / Self-Reported Profiler Efficiency Score (Seff). If you have previously completed your submission, please ensure that you update your submission … For more on how to use the profiler, please look at this video tutorial: https://www.youtube.com/playlist?list=PLSj-s4_873dY … Discord Channel https://discord.com/invite/C6U2ZWdMF".
- "Free GPU Credits From UDUTech" (about 2 months ago): "up to 5 hours of free GPU credits … They're intended for training and fine-tuning — final benchmarks must still run on the ADTC Standard Laptop profile".
- Finalists → Africa AI XPrize (14 days ago); knowledge sessions (SVD/low-rank compression, "Last Mile of AI", GPU access) — no scoring content.
- Nothing about AVX2, profiler versions, TPS_max, or a leaderboard.

### 1.5 The profiler repo is the only source on the audit binary **[V]**

`Dockerfile` (verbatim):
```
# Stage 1: build llama.cpp (CPU-only, for parity with Standard Laptop profile)
FROM debian:bookworm-slim AS llama-build
ARG LLAMACPP_REF=b10175
… cmake -B build -DBUILD_SHARED_LIBS=OFF -DGGML_NATIVE=OFF -DGGML_AVX=OFF -DGGML_AVX2=OFF -DGGML_AVX512=OFF -DGGML_FMA=OFF -DGGML_F16C=OFF -DGGML_BLAS=OFF -DGGML_CUDA=OFF -DGGML_METAL=OFF
… --target llama-bench llama-cli llama-server -j2
```
README: audit is `docker run --rm --memory=7.5g … --mode audit`; "Audit Mode (Evaluation Sandbox) — Used by the ADTC evaluation orchestrator inside secure cloud VMs."; scoring table `S_perf = min(TPS / TPS_REFERENCE, 1.0) * 100 — Normalised against TPS_REFERENCE = 15.0`; `S_eff = max(0, (RAM_LIMIT_GB - peak_rss_gb) / RAM_LIMIT_GB) * 100 — RAM_LIMIT_GB = 7.0`; comparator tolerances "peak_rss_mb ±15% (fails >50%), tokens_per_second_generation ±25% (fails >50%)"; verdict `fail` on "zero/missing values, mismatched team IDs, wrong measured_on environment, or schema violations".
`throughput.py`: `llama-bench … -p 512 -n 128 -ngl 0` (default threads unless overridden), TTFT computed from pp rate. `accuracy.py`: default `task="arc_easy", limit=50`, in-process llama_cpp loglikelihood **without a chat template**; docstring "Real audits use the full hidden 30% validation subset distributed by judges." `memory.py`: process-tree RSS sampled during the llama-bench run; peak + steady-state.
Commit timeline: 2026-06-15 initial; 06-22 add `autonomous_ai_agents`; 07-21 remove invalid `base_url`; 07-28/29 (external contributor **durutheguru**, PR #1) accuracy via lm-eval → in-process llama_cpp, "llama-bench now pinned to CPU (`-ngl 0`)", "Comparator fail bound corrected to the documented 50%", "`throttled` threshold matches the published 85 °C penalty rule (was 95 °C)", "**Docker build was broken** … llama.cpp pinned to release b10175", GGUF fraud check "two-sided (±15%)"; 07-30 PR #2 `examples/demo-submission/` ("exactly-2 `test_prompts`, no extra fields, ±15% fraud-checked `parameters_estimate`"); **2026-08-15 `fix(packaging): lower minimum Python requirement to >=3.10`** (latest). No tags/releases; `profiler_version` string in outputs is still `adtc-profiler 0.1.0`. Issues: only the two PRs; no organiser-authored issue responses.

**Bottom line on the three open questions:** (a) AVX2 — no organiser statement; Dockerfile says scalar; (b) profiler version — unversioned, HEAD moves (last 08-15); (c) TPS_max — Devpost/ADTF text says relative-to-fastest, code says 15.0 cap; **unresolved publicly**. **[V]**

### 1.6 Field size and public leaderboard **[V]**

- Devpost: "Participants (1679)"; Devpost gallery unpublished. ADTF leaderboard: "Asante Benchmark Leaderboard — Laptop LLM Challenge 2026 Evaluation Telemetry. Verifying accuracy, memory efficiency, and generation speed on commodity hardware. Published Submissions — No published runs found matching search criteria." SSR payload: `"runs",[]`. Columns in bundle: run_id, submitter, team_id, `rss_peak_gb` ("x.xx GB"), `tps` ("x.x t/s"), `scores.total`; a 2-run compare modal shows "Throughput — Higher is Better — tokens/s" and "Overall Score".
- Template forks: 99 (many untouched since 2026-06-15). ADTC-related repos found: ~110; with metadata.json: 77; non-template model: 65; with a committed `submission.json`: 9. Press coverage (TechAfrica News 2026-07-30, Techpoint, TechTrends KE, MSME Africa) contains no scoring or team-count details beyond "prize pool exceeding $20,000".
- Not accessible: Discord (bit.ly/adtc_discord / discord.com/invite/C6U2ZWdMF), the YouTube tutorial playlist (consent wall), unpublished Devpost submissions.

---

## 2. Observed competitor configurations (65 repos with a declared, non-template model)

Columns: repo (GitHub) · domain · model (as declared) · quant · params · **self-reported gen tok/s** · **self-reported peak RSS** · hardware/method context for those numbers · African-alpha claim · last push. Numbers come from `submission.json` when committed (marked *sub*), otherwise from REPORT/README. Blank = not reported.

| Repo | Domain | Model | Quant | Params | tok/s | Peak RSS | Measurement context | Alpha | Push |
|---|---|---|---|---|---|---|---|---|---|
| **judeszn/eulermind-adtc-submission** | **math_sci** | Qwen2.5-Math-1.5B-Instruct | Q4_K_M | 1.5B | 15.02–15.68 | 1,699–1,700 MB | "official adtc-profiler, unmodified, on x86 4-vCPU CI runners" (GitHub Actions); GSM8K 68% (50 q); TTFT 16.8 s; team_id still "REPLACE-WITH-ADTF-TEAM-ID" | yes | 07-20 |
| **MarvinaChinasa/adtc-2026-offline-stem-reasoning** | **math_sci** | DeepSeek-R1-Distill-Qwen-1.5B | Q4_K_M | 1.5B | **1.23** *sub* (README claims 12.18) | 1,259 MB *sub* (README claims 3,777 MB) | *sub*: i5-7300U, **3.8 GB RAM**, Debian 13, TTFT 514 s; `accuracy: []`; submitter email placeholder | yes | 08-13 |
| 2kDarki/adtc-2026 ("coding tutor") | coding | Qwen3.5-4B | **Q5_K_M** | 4B | 8.25–8.42 (llama-bench), 8.05 live | 4,866–4,949 MB | 4 vCPU/8 GB container on AMD EPYC 7763, llama.cpp b10217 OpenBLAS build, 4 threads; team_id/prompts still template | no | 08-13 |
| Wangadeveloper/adtc-2026-submission | (M-Pesa finance) | **Gemma 3 270M IT** + LoRA | Q4_K_M | 270M | **44.32** | **382 MB** (steady 354) | README table; build/hardware not stated | — | 08-17 |
| Amarame-Emmanuel/ADTC-2026-submission-template ("AGBE"-like agri) | agriculture | Qwen2.5-1.5B-Instruct | **Q4_0** | 1.5B | 38.0 (p50; 3B: 21.5) | 1.71 GB full app (3B: 2.71 GB) | own harness, 773-token prompts, "4-core cpuset", `--memory=7g`; explicitly declines to self-report S_perf because TPS_max unknown | yes | 08-15 |
| benewende-dev/baarali-edge | corporate | Qwen3.5-2B (fine-tuned) | **IQ4_XS** (imatrix) | 1.88B | 31.2–34.3 | 1.54–1.74 GB | Apple M1 8 GB, `-ngl 0`; candidate table (M1): Qwen3.5-0.8B 65.3 t/s/1.21 GB; SmolLM3-3B 25.5/3.02; Phi-4-mini 20.6/3.30; Qwen3.5-4B 14.9/3.49; SmolLM2-135M "reaches 319 t/s on this machine"; S_perf sensitivity table for TPS_max ∈ {65,150,319} | yes | 08-03 |
| nevodesigns/agbe | agriculture | Gemma 3 1B + LoRA r32 | Q4_K_M | 1B | 22–27 (candidates: Qwen2.5-0.5B 46.6, Llama-3.2-1B 22.8, Qwen2.5-1.5B 24.9, Qwen2.5-3B 11.5) | 0.88 GB | i7-10850H, 4 threads, `-ngl 0`, memory capped 7 GB; assumes 15 tok/s cap ("Throughput above 15 tok/s earns nothing") | yes | 08-17 |
| Jayayjay/adtc-2026-submission-template | healthcare | Qwen3.5-0.8B-IMCI (LoRA) | Q4_K_M | 0.8B | 21.7 | 857 MB | i5-7300U (2C/4T), 15 GiB; assumes 15 tok/s cap; 532 MB file | yes | 08-14 |
| qeinstein/adtc-llm-limited-hardware ("JamiiAfya") | healthcare | Qwen3-0.6B-**Base** + LoRA | **Q4_0** (EN+SW imatrix) | 0.6B | **20.33** | **527 MB** | **official profiler, scalar build**, AMD EPYC 7763 4 cores, Ubuntu 24.04; explicitly reasons about the SIMD-off audit and about no-chat-template MC scoring (chose Base over Instruct) | yes | 08-10 |
| saintzema/ZafyaLM | healthcare | Qwen2.5-1.5B-Instruct | Q4_K_M | 1.8B | 33.61 (Gemma alt 17.53) | 2.65 GB | "representative x86 hardware" (unspecified); dev Mac 2-core gave 0.6–0.8 t/s | no | 07-09 |
| Skywalkingzulu1/impilo-llm | healthcare | "Impilo-Health-2B" (Gemma-2-2B?) | Q4_K_M | 2.6B | 18.4 (avg of 10) | 3,420 MB | 8 GB laptop, unspecified CPU; self-scored S_perf 81.8 / S_eff 51.1 | yes | 07-09 |
| ArtTechnologies-User/… | coding | SmolLM2-135M (template) | Q4_K_M | 135M | ~18.4 | — | template numbers | no | 08-05 |
| tifeoshodi/tifeoshodi-adtc-2026-submission | agriculture | Llama-3.2-1B-Instruct | Q4_K_M | 1B | 17.5 | 1,385 MB | unspecified | no | 07-17 |
| AliyuBio/ndlea-secure-operational-assistant | agents | Phi-3 4-bit (per description) | Q4_K_M | — | ~16.5 | ~4.1 GB | unspecified | no | 06-24 |
| damilojohn/ATDC-Challenge | coding | Qwen2.5-0.5B-Instruct | Q4_K_M | 0.5B | 15.42 *sub* | 589 MB *sub* | *sub*: i5-6200U, 5.8 GB, Ubuntu 24.04; `model_path` outside `model/` | no | 07-10 |
| Ayo-Cyber/localmind-adtc-2026 | agents | Qwen2.5-3B-Instruct | Q4_K_M | 3B | 14.8 (profiler; 17.5 llama-bench) | 3.3 GB | unspecified; TTFT 17.7 s | no | 07-17 |
| rssebambulidde/adtc-2026 ("Kilimo") | agriculture | Qwen2.5-0.5B + LoRA SFT | Q4_K_M | 0.5B | 14.40 (1.5B: 5.87) | 543 MB (1.5B: 1,711 MB) | "dev machine" (unspecified); self-scored S_perf 96 / S_eff 92.4 | yes | 08-15 |
| dimittri1/ondjila | agents | Qwen3-1.7B (fine-tuned) | Q4_K_M | 1.7B | 14.02 (Xeon AVX2) / 2.78 (i5-3570S no-AVX2) | 1.90 GB (AVX2) / 1.19 GB (no AVX2) | Xeon 2.2 GHz 4 vCPU **AVX2**; notes "peak memory rises by 0.7 GB on the faster machine … Q4_K runtime repacking"; rejected IQ4_XS ("no CPU repack path"); Qwen3.5-4B measured 1.91 t/s / 2.78 GB on old box | yes | 08-10 |
| victorachede/offline-scholars | healthcare (exam prep) | Phi-3-mini-4k-instruct | Q4_K_M | 3.8B | ~14 | ~4.3 GB | unspecified | yes | 07-03 |
| oumar-code/… | — | (metadata invalid JSON) | — | — | ~14.2 | — | template-ish | — | 08-01 |
| fallback-ai/homa-adtc-2026 | agriculture | "Homa-Afrique-Gemma-4B" (Gemma fine-tune) | Q4_K_M | 4B | 13.79 | **5,570 MB** (steady 4,969) | unspecified | yes | 08-16 |
| mayowaoladosu/adtc-laptop-llm | agriculture | Qwen2.5-3B-Instruct | Q4_K_M | 3.1B | 13.41 *sub* | 3,459 MB *sub* | *sub*: AMD EPYC 7763, 15.6 GB, Ubuntu 24.04; arc_easy 0.80 (50) | yes | 08-04 |
| kherin/karoguard-adtc-2026-submission | agriculture | Qwen3-4B-Instruct-2507 (base tensors + chat-template policy) | Q4_K_M | 4B | 13.15 *sub* | 2,543 MB *sub* | *sub*: AMD EPYC-Genoa, 3.7 GB RAM, llama.cpp b10424 CPU-only | yes | 08-16 |
| joanuka/… | healthcare | Qwen2.5-1.5B-Instruct | Q4_K_M | 1.5B | 12.8 (4 thr; 8.31 at 2 thr) | — | unspecified | no | 08-12 |
| shaba40/siyana-ai | corporate | Qwen3-4B | Q4_K_M | 4B | 10.0–11.19 | 4,288 MB | unspecified | no | 07-22 |
| Oluwabusiolami/edulite-… | creative | Qwen2.5-1.5B-Instruct | Q4_K_M | 1.5B | 8.3–9.6 | — | unspecified | yes | 06-19 |
| Wayazi/adtc-2026 | agents | Qwen3.5-2B fine-tune (multimodal, 32K ctx) | Q4_K_M | 2B | 9–10 | ~4.5 GB | unspecified | yes | 08-04 |
| nogasante/ayekoo | agriculture | Qwen2.5-0.5B-Instruct + local retrieval | Q4_K_M | 0.63B | 9.77 idle (2.69 when swapping) | 545 MB (profiler) | 8 GB laptop, unspecified | yes | 08-13 |
| cruso003/agridoc-adtc2026 | agriculture | Qwen3-1.7B LoRA ("AgriDoc") | **Q4_0** | 1.7B | **9.4 (scalar)** (Llama-3.2-1B Q4_0 12.81; Qwen2.5-1.5B Q4_0 10.79) | 1.17 GB (0.87 / 1.05) | **profiler Docker image, `--cpus=4 --memory=7.5g`, host i7-1165G7** ("scalar floor") | no | 08-16 |
| crispychip146/qwencare-coder-adtc2026 | coding | Phi-3.5-mini-instruct | Q4_K_M | 3.8B | 9.39 (tg128) | 4.23 GB | unspecified | no | 07-05 |
| Overwatch886/team-codewatch-… | coding | IBM Granite-4.0-h-tiny (hybrid) | **IQ4_XS** | 6.94B | 8.57 *sub* | 3,623 MB *sub* | *sub*: Ryzen 5 PRO 4650U, 6.8 GB, "Ubuntu 26.04"; arc_easy 0.86 (50); temp 81 °C | no | 08-15 |
| kish-00/adtc-2026-submission | corporate | Qwen2.5-1.5B-Instruct | Q4_K_M | 1.78B | 8.15 *sub* | 1,822 MB *sub* | *sub*: i5-6200U, **temp 92 °C, throttled: true**; self-scores S_perf 54.33 vs 15 but notes TPS_max "will exceed 15.0" | yes | 08-15 |
| Ajiboye-ibrahim/yieldGuard | agriculture | Qwen2.5-1.5B-Instruct | **Q5_K_M** | 1.5B | 8.16 | — | unspecified | yes | 08-15 |
| iamsamuelk/adtc-2026-agriculture-advisor | agriculture | Qwen2.5-1.5B-Instruct-Persona (fine-tune) | Q4_K_M | 1.5B | 6.7–8.2 | ~1.2 GB | unspecified | yes | 08-16 |
| Gr8n3s/adtc-2026-agri-llm | agriculture | Llama-3.2-3B-Instruct | Q4_K_M | 3.21B | 7.49 | — | unspecified | yes | 08-02 |
| bugindacodeQ/tibaedge-adtc-2026 | healthcare | Qwen2.5-1.5B-Instruct | Q4_K_M | 1.54B | 6.40 | 1,187 MB | profiler; self-scored S_perf 42.67 / S_eff 83.44 | yes | 07-18 |
| Sultan-Othman-Adekoya/buildmate-ai-adtc2026 | corporate | Phi-3 Mini 4K Instruct | Q4_K_M | 3.8B | 5.1 *sub* (README: 28.4) | 3,796 MB *sub* | *sub*: Intel "Model 78" (Skylake-U), 7.9 GB, **Windows 10**; arc_easy 0.76 | yes | 08-14 |
| notomodo/adtc-2026 | corporate | Qwen2.5-3B-Instruct | Q4_K_M | 3B | 4.98 median (llama-bench 4.32) | 3,456 MB | "dev floor" (Ollama + llama-bench); previews score ≈48.8 with −10 thermal | yes | 08-16 |
| Chi-Automates/… | healthcare | Qwen2.5-3B-Instruct | Q4_K_M | 3B | 4.94 | 2,856 MB | unspecified | no | 07-19 |
| SKI-LEH/adtc-2026-agriculture | agriculture | Llama-3.2-1B-Instruct | Q4_K_M | 1B | 4.65 *sub* | 1,391 MB *sub* | *sub*: AMD Family 21 (Excavator), Windows 10; `params_match: false` | no | 08-11 |
| Akixama/baobab-adtc2026 | healthcare | Llama-3.2-3B-Instruct | Q4_K_M | 3B | 4.25 | — | unspecified | yes | 07-11 |
| ABugDrone/… (DroneBug) | corporate | tiny-aya-earth | Q4_K_M | 3.35B | 4.04 | — | unspecified | yes | 07-22 |
| NourTi/rifqa-adtc-2026 | creative | Qwen2.5-3B-Instruct | Q4_K_M | 3B | 3.95 | 3,478 MB | Google Colab shared CPU | yes | 08-09 |
| amaeteventurestudios/afrekaos-… | (invalid domain) | — | — | — | 3.4–5 | ~5.4 GB projected | dev machine | — | 07-15 |
| thepreakerebi/fundi | healthcare | "Fundi-1.5B" (Qwen2.5-1.5B fine-tune) | Q4_K_M | 1.5B | **3.49 (SIMD-off x86)** (67.7 on ARM) | 1,951 MB | **"x86 ubuntu-22.04 runner with llama.cpp built SIMD-off to match the official ADTC Dockerfile"**; "a 0.5B model measured ~the same (3.30)" | no | 06-29 |
| sheismuna/agrilens-ai-adtc-2026 | agriculture | SmolLM3-3B-Instruct | Q4_K_M | 3.08B | 3.20 | 3.24 GB | 2-vCPU shared cloud CPU | no | 07-11 |
| clementcyberknight/Neurons | corporate | Qwen2.5-1.5B custom | **IQ3_XS** | 1.5B | 3.2–5.3 | 831 MB (ctx 2048) / 1.71 GB (ctx 32768) | unspecified | yes | 08-17 |
| husseinalamutu/adtc-2026 ("alamz-tech-sme-copilot") | corporate | Qwen2.5-3B QLoRA, imatrix | Q4_K_M | 3.1B | **2.75 (audit-exact scalar, `-t 4`; ~2.0 at auto threads)** | ~2,023 MB | **i7-1185G7, "4 CPUs / 7.5 GB, audit-exact flags"** (profiler Dockerfile); explicitly models S_perf as relative-to-field | yes | 08-14 |
| japhet996sunday-cell/nova-dev-ai-adtc-2026 | coding | Qwen2.5-Coder-1.5B-Instruct | Q4_K_M | 1.5B | 0.14 (tg16) | — | very weak dev machine | no | 08-14 |
| Archille21/koda | coding | Qwen2.5-Coder-7B-Instruct | Q4_K_M | 7B | — | — | — | yes | 08-16 |
| itsebuka/Apollo-medical-AI-triage-system | healthcare | Meta-Llama-3-8B-Instruct | Q4_K_M | 8B | — | 6.17 GB "total (model + embeddings + OS)" | — | yes | 08-16 |
| hmoent2020-ui/… | corporate | Meta-Llama-3.1-8B-Instruct | Q4_K_M | **"135M"** (wrong) | — | — | template numbers | no | 06-18 |
| Eaahene/… | coding | "Qwen3.5-9B-…-NEO-MAX" | **IQ2_M** | **"135M"** (wrong) | — | — | template numbers | no | 08-03 |
| TH3-HUNTER/adtc | agriculture | Qwen3-4B-Instruct | Q4_K_M | 4B | — | — | — | yes | 08-15 |
| Techris93/igbo-agri-advisor | agriculture | Qwen3-4B (Igbo fine-tune, provisional) | Q4_K_M | 4B | target ≥15 | target <5.5 GB | targets only | yes | 06-29 |
| athandile-tetyana/… | agriculture | tiny-aya-earth | Q4_K_M | 3.35B | — | — | — | yes | 07-16 |
| dagbolade/tbscreen-adtc-2026 | healthcare | gemma-4-E2B-it | Q4_K_M | ~2.6B eff. | 48.65 (M1 Pro) | 1,870 MB (M1 Pro) | Apple M1 Pro 16 GB (explicitly not target) | yes | 07-26 |
| jrcity/nexalith-foreman | agents | Qwen2.5-3B-Instruct | Q4_K_M | 3.4B | ~8 balanced / ~13.5 performance profile (97 °C throttling) | — | unspecified laptop | no | 08-15 |
| Sultan-Othman-Adekoya/buildmate-adtc-2026-submission-template | corporate | Phi-3-Mini | Q4_K_M | 3.8B | — | — | duplicate of above | yes | 08-14 |
| ezekiellemana/kazi-agent-adtc | agents | Qwen2.5-1.5B-Instruct | Q4_K_M | 1.5B | — | 1,818 MB | profiler | yes | 07-10 |
| hadamard-2/qemer-adtc-2026-submission | coding | Qwen3.5-2B | Q4_K_M | 2B | template numbers | — | — | no | 08-16 |
| nyaks1/setlhare | coding | Qwen2.5-Coder-1.5B-Instruct | Q4_K_M | 1.8B | — | — | — | yes | 08-17 |
| Layerrail/adtc-laptop-llm | agriculture | Qwen2.5-0.5B-Instruct | **Q4_0** | 0.5B | "1.9x generation throughput vs FP16" | "54% lower peak RSS than FP16" | — | yes | 08-03 |
| Hamza1610/… | healthcare | Qwen2.5-0.5B-Instruct | **Q4_0** | 0.5B | template numbers | — | — | yes | 07-14 |
| gatsby100m/… | agriculture | qwen2.5-0.5b-instruct | Q4_K_M | 500M | — | — | model_path `models/` (wrong dir) | no | 08-16 |
| ChukwumaUk/… | agriculture | Llama-3.2-1B-Instruct | Q4_K_M | 1.1B | — | — | — | yes | 08-16 |
| fadelkora21/allo-nutri-adtc-2026 | agriculture | Qwen2.5-1.5B-Instruct (feed formulator) | Q4_K_M | 1.5B | — | — | — | yes | 08-12 |
| ksalawu-wq/… | corporate | Qwen2.5-1.5B-Instruct | Q4_K_M | 1.5B | — | — | — | yes | 08-06 |
| nkwedegideon790-coder/… | corporate | TinyLlama-1.1B-chat | Q4_K_M | **"2.7B"** (wrong) | — | — | — | yes | 07-29 |
| IDMan240/… | coding | SmolLM2-135M-Instruct | Q4_K_M | 135M | ~28.5 | — | — | no | 06-22 |
| adrianvince7/… | agriculture | "TODO-SET-AT-FREEZE" | Q4_K_M | TODO | — | — | — | yes | 08-01 |
| NodeA7/NomAgbo, IsraelOdeh/moses-fs, mechakc/adtc-mechakc, theredteamtech/jengaai-edge, CrappyLord/… | various | SmolLM2-135M (template untouched) | Q4_K_M | 135M | — | — | template | no | — |

Other repos found without a usable `metadata.json` (early-stage or app-only; ~30): Ahmadubaismail/QualiFood_Ai (Ollama qwen2.5:1.5b), ImeMonday/Adtc2026-agri-advisor (Ollama llama3.2:3b, 2.4–8.3 tok/s), gbohigbaradc/mediassist_* (Ollama, "~15–20 TPS on i5 10th–13th gen (num_thread=4)", "~2.5 GB"), reuben-adukson123/africa-code-assistant (5–12 tok/s, 3.3 GB), michaelfrancoodev/olyvri (math tutor with SymPy verification — no metadata yet), mj-weshh/shamba-copilot ("fine-tuned ~4B model (GGUF Q4_K_M)"), Cloud99p/omnilearn-adct-2026, kbshow28899, zayyanusani, HabibLLMStudio, idris-software, EricBabatunde, basimtyson, absediqni, emmyfly, Kedarcv, Vicarioy, ruthiiyambo, SaahBrice, Japhetaline, nchiwar, Bamalli11, dan-angila, ParthGurav29 (metadata invalid JSON; plans Qwen 1.5B), fresnel-cyber, wisdom99, zulyadainimuhammad, zoro2444Z, mjaphet532-ops, OinkinB/AgriPocket-LLM, tmachingur-code, Wangadeveloper (see table), nevodesigns/agbe-site.

HF models found by search `adtc`: `Wayazi/qwen3.5-2b-adtc-gguf`, `kherin/karoguard-adtc-2026-gguf`, `iamsamuelk/adtc-2026-agri-advisor-qwen1.5b-persona`, `Menashi22/sentinel-adtc`, `HolyArapaima/ADT_Command_Panel`.

---

## 3. The only numbers that matter: self-reports on the audit-like (scalar) build **[V]**

| Team | Model / quant | tok/s (gen, `-p 512 -n 128`) | Peak RSS | Hardware |
|---|---|---|---|---|
| husseinalamutu | Qwen2.5-3B Q4_K_M (imatrix) | **2.75** (`-t 4`), ~2.0 auto-threads | 2,023 MB | i7-1185G7, profiler Docker image, 4 CPUs / 7.5 GB |
| thepreakerebi/fundi | Qwen2.5-1.5B Q4_K_M | **3.49** ("a 0.5B model measured ~the same (3.30)") | 1,951 MB | x86 ubuntu-22.04 runner, SIMD-off build |
| cruso003/agridoc | Qwen3-1.7B **Q4_0** / Qwen2.5-1.5B Q4_0 / Llama-3.2-1B Q4_0 | **9.4 / 10.79 / 12.81** | 1.17 / 1.05 / 0.87 GB | i7-1165G7, profiler image `--cpus=4 --memory=7.5g` |
| qeinstein/JamiiAfya | Qwen3-0.6B **Q4_0** | **20.33** | 527 MB | AMD EPYC 7763, 4 cores, scalar build (Q8_0 "sits near the line" of 15) |
| judeszn/EulerMind | Qwen2.5-Math-1.5B Q4_K_M | 15.02–15.68 | 1,700 MB | "x86 4-vCPU CI runners" (GitHub Actions; build not stated — likely AVX2 given the fundi/hussein data) |

Read-across **[I]**: on the scalar b10175 build, Q4_K_M at 1.5B ≈ 3–3.5 tok/s and 3B ≈ 2–2.75 tok/s on 11th-gen laptop cores; **Q4_0 appears ~3× faster than Q4_K_M** on the scalar path (1.5B Q4_0 ≈ 10.8 on i7-1165G7 vs 1.5B Q4_K_M ≈ 3.5 on an unspecified x86 runner — different hosts, so indicative only; qeinstein's own sweep on one host also put Q4_0 well ahead of Q8_0), consistent with the ggml scalar dequant paths — several teams (Amarame-Emmanuel, Layerrail, cruso003, qeinstein, Hamza1610) have independently switched to Q4_0 for that reason. Nobody outside our team is reporting TQ1_0/TQ2_0 or vocab-pruned artefacts.

Also relevant, from dimittri1/ondjila (AVX2 build): "peak memory rises by 0.7 GB on the faster machine … with AVX2, llama.cpp rewrites the quantized weights into a SIMD-friendly layout at load time" — i.e., competitors measuring RSS on AVX2 machines will over-report vs the scalar audit (no repack), and vice-versa for anyone measuring RSS on the scalar build. **[V quote, I read-across]**

---

## 4. How competitors are reasoning about the score (patterns) **[V]**

- **"Small beats big" is now the consensus among the serious entries.** qeinstein: "A 14B model … scores ~12/100 on efficiency and near-zero on throughput on a scalar build — it throws away half the score." rssebambulidde: "1.5B Q4: profiled and rejected … 5.87 tok/s on the dev machine gave up 20.31 points of final score against the 0.5B." nevodesigns/agbe: candidate table with 0.5B/1B/1.5B/3B and "Throughput above 15 tok/s earns nothing" (they assume the 15 cap). Jayayjay: "A 0.8B model on CPU clears that comfortably, so we spend no score chasing raw speed."
- **Two camps on TPS_max.** Cap-at-15 camp (agbe, Jayayjay, rssebambulidde, tibaedge, kish-00's arithmetic, MarvinaChinasa's "81.2% of the … provisional target"). Relative-to-fastest camp: baarali-edge ("**S_perf is deliberately not self-reported as a score.** The rule computes it relative to the fastest submission received, a denominator we do not have"; sensitivity table at 65/150/319 t/s; "319 t/s is not a hypothesis: the 135 M-parameter example model shipped by the organisers reaches it on this machine"), husseinalamutu ("`S_perf = 100·TPS/TPS_max` — relative to the field"), kish-00 ("fastest team's throughput across all submissions — which will exceed 15.0"), Amarame-Emmanuel ("It is also the one term no team controls").
- **"The profiler scores only the GGUF"** is widely understood: rssebambulidde "App + RAG wrappers: useful for demos, but the profiler scores only the GGUF weights via llama.cpp, so domain knowledge must live in the model"; husseinalamutu "The sandbox scores the **bare model** on our 2 test prompts + 3 hidden in-domain prompts — no retrieval pipeline runs … Fine-tune, don't rely on RAG for the score." Hence many LoRA/QLoRA fine-tunes of Qwen2.5-0.5B/1.5B/3B and Qwen3-0.6B/1.7B/4B, several with domain imatrix.
- **No-chat-template MC scoring noticed** by qeinstein ("Base rather than Instruct: the profiler ranks answer choices by raw loglikelihood with no chat template, a regime where base checkpoints …") and by the unanswered forum bug report ("0.12 acc_norm on arc_easy, where random guessing is ~0.25").
- **Verification/tool wrappers in our domain**: EulerMind (Qwen2.5-Math-1.5B + LP/CSP solvers + certificate checker; "0% false certification, 192/192"), olyvri (SymPy verifies). Both are application-layer and, per the FAQ, not measured — but they read well in REPORT.md and Gate-2 Q&A.
- **Thermal**: jrcity/nexalith-foreman benchmarks under the Linux `balanced` governor because `performance` "drove sustained core temperatures to 97°C with confirmed throttling"; kish-00 committed a `submission.json` with `throttled: true, core_temp_c_peak: 92` (self-inflicted −10 in their own report).
- **Docs quality is treated as scored**: many REPORT.md files are long, measurement-driven, and cite the formula; template README says "Judges and the LLM-based audit system will read this to understand your submission." Devpost criteria fold "quality of documentation" into the 50% accuracy bucket. **[V]**

---

## 5. Common mistakes seen in the field (useful as a pre-flight checklist) **[V]**

1. Placeholder `team_id` ("your-team-id", "REPLACE-WITH-ADTF-TEAM-ID", "REPLACE_WITH_DEVPOST_TEAM_ID") — 12 repos, including strong ones (EulerMind, agbe, 2kDarki). Organiser says team ID = Devpost project slug (e.g. `project-farmspeak`); comparator FAILs on "mismatched team IDs".
2. Template test prompts left as the CSV/list-vs-tuple examples — 9 repos (incl. 2kDarki's Qwen3.5-4B tutor). Cross-disciplinary description left as "Brief description of how your model serves a real-world domain." — 8. Submitter email placeholder — 9 (incl. MarvinaChinasa, cruso003).
3. `parameters_estimate` inconsistent with the GGUF: "135M" on 8–9B models (hmoent2020-ui, Eaahene), TinyLlama-1.1B labelled "2.7B", 1.5B labelled 1.8B, 0.5B labelled 0.63B; SKI-LEH's committed `submission.json` already shows `params_match: false`. The profiler fraud check is two-sided ±15% on tensor-summed params.
4. `metadata.json` not valid JSON (trailing commas: 2kDarki has a trailing comma in `contributors`; ParthGurav29, oumar-code invalid); extra top-level keys (`contributors`, `self_reported_profiler`, `schema_version`, `_notas_para_nos`) — the demo README warns "no extra fields".
5. `_runtime.model_path` not under `model/` (`../models/…`, `models/…`, empty).
6. Self-reported telemetry from non-representative environments: Apple M1/M1 Pro (baarali-edge, tbscreen), Google Colab (rifqa), Windows 10 (Sultan, SKI-LEH), 2-vCPU cloud (agrilens), Ollama counters (notomodo, ImeMonday), 3.8 GB-RAM laptop (MarvinaChinasa: TTFT 514 s). Comparator tolerance is ±25% TPS / ±15% RSS, fail >50%.
7. Numbers in README/REPORT that contradict the committed `submission.json` (MarvinaChinasa 12.18 vs 1.23 tok/s; Sultan 28.4 vs 5.1 tok/s).
8. Empty `accuracy: []` in committed submission.json (MarvinaChinasa, damilojohn, kherin, SKI-LEH) — allowed by `--skip-accuracy` in participant mode but the README says "your final submitted report should come from a full run"; the forum question about this is unanswered.
9. Big models near the ceiling: Llama-3-8B Q4_K_M ("6.17 GB total"), Qwen2.5-Coder-7B Q4_K_M, Gemma-4B at 5,570 MB peak, Granite 7B IQ4_XS at 3.6 GB — S_eff 20–50 and single-digit scalar tok/s.
10. Q5_K_M/IQ4_XS/IQ3_XS/IQ2_M choices made on AVX2/NEON speed data; ondjila notes IQ4_XS has no CPU repack path — on the scalar audit build all of these are slower than Q4_0. **[V + I]**

---

## 6. Direct competitors in `math_scientific_reasoning` **[V]**

Only two declared entries found (of 65), plus two adjacent:

| Team | Model | Self-reported | Notes |
|---|---|---|---|
| judeszn / EulerMind (Boluwatife Faturoti) | Qwen2.5-Math-1.5B-Instruct Q4_K_M (1.0 GB file) | 15.02–15.68 tok/s, 1,700 MB, GSM8K 68% (50 q), TTFT 16.8 s on "x86 4-vCPU CI runners" | Deterministic OR solver + certificate checker wrapper; test prompts are LP (Lagos furniture workshop) and CSP (Nairobi volunteer assignment); `african_alpha_claim: true` (English-only `language_scope`); team_id placeholder; last push 07-20 |
| MarvinaChinasa (STEM tutor) | DeepSeek-R1-Distill-Qwen-1.5B Q4_K_M | sub: 1.23 tok/s / 1,259 MB on i5-7300U 3.8 GB; README claims 12.18 tok/s / 3,777 MB | Test prompts: solve 3x²−12x+12=0; AP 15th term & sum; `accuracy: []`; email placeholder |
| michaelfrancoodev/olyvri (math tutor) | not declared | — | "LLM parses & explains, SymPy verifies"; no metadata yet (07-24) |
| victorachede/offline-scholars (JAMB/WAEC prep) | Phi-3-mini-4k Q4_K_M | ~14 tok/s, ~4.3 GB | domain declared healthcare_medical (mis-filed) |
| 2kDarki (coding tutor, education pairing) | Qwen3.5-4B **Q5_K_M** | 8.3 tok/s, 4.9 GB on 4 vCPU/8 GB EPYC container | reasoning mode; "7/7 correct"; template prompts/team_id |

Read-across for team-muta **[I]**: our declared config (BitCPM4-8B TQ2_0 body + Q6_K/Q4_K head, 44,416-token English vocab; self-report 18.21 tok/s / 2,462 MB peak on M1, arc_easy 0.84/50) is (a) the only ternary/pruned artefact in the field, (b) the largest parameter count in the math domain by >5×, (c) at 2.4 GB peak RSS, mid-pack on S_eff (competitors in-domain are at 1.2–1.7 GB; the 0.5–0.8B crowd is at 0.5–0.9 GB), and (d) its S_perf depends entirely on the unresolved TPS_max question and on the scalar-kernel decode rate for TQ2_0 on b10175 — which no competitor has data on. If TPS_max is relative-to-fastest, expect a 270M–0.8B Q4_0/Q4_K_M entrant to set the denominator (Gemma-3-270M self-report 44 tok/s; Qwen3-0.6B Q4_0 20 tok/s on scalar EPYC; SmolLM2-135M ~319 t/s on M1), which compresses everyone's S_perf and makes S_acc (50%, judged on 4–5 in-domain prompts) and S_eff the discriminators. If it is the 15-cap, anything ≥15 tok/s on the audit VM saturates and S_eff + S_acc decide.

---

## 7. What judges reward — everything stated publicly **[V]**

- Devpost: "Model Accuracy & Quality — A combination of multiple-choice benchmarks and qualitative evaluations that includes accuracy of prompts, quality of documentation"; "African Use Case Bonus — Up to 10 extra points awarded for how applicable the model is to a real African use case".
- ADTF: judges "chat with it live through our in-browser interface"; "the primary language of evaluation for this competition is English"; "+15% on their panel score" for meaningful African-language functionality; "+10%" budget profile; "Best Integration Award … most load-bearing and robust cross-disciplinary deep-tech pairing"; "Best Localisation Award … deepest integration with African languages, offline data, or local contextual depth"; Gate 1 is "Two-step judging: proposal screen, then prototype review of the top ~10%".
- Template README: "Judges and the LLM-based audit system will read this [REPORT.md] to understand your submission."
- Video: "While seeing your model running live is highly encouraged, it is not strictly required."
- Nothing public about rubric weights within S_acc, about how "multiple-choice benchmarks" and live-chat grades are combined, or about which lm-eval task/limit the audit uses beyond "hidden 30% validation subset" and the arc_easy default.

---

## 8. Gaps / not verifiable from public sources

- Discord (`bit.ly/adtc_discord`, `discord.com/invite/C6U2ZWdMF`) is where the organiser directs questions; it may contain AVX2/TPS_max/profiler clarifications that are not mirrored on Devpost. Not accessible from this session.
- The YouTube profiler tutorial playlist (`PLSj-s4_873dY`) — consent wall; content unknown.
- Devpost submissions are private until the gallery is published; the 1,679 "participants" figure is registrants, not submissions.
- The Devpost "Judges" list (Oji Udezue, Yannick Djoumbou Feunang, Oluwatobi Oyinlola, Christine Abernathy, Omoju Miller, Peter Ing, Mbangula Lameck Amugongo, Ola Fadiran, Houda Ghozzi) is public; no per-judge statements found.
- No X/LinkedIn posts by competitors with numbers surfaced via web search; the topic is too niche for the search index. **[V]**

---

## 9. Source URLs

- Devpost: https://adtc-2026.devpost.com/ · /rules · /resources · /updates · /updates/45602-important-updates-to-submission-form-separate-fields-for-profiler-scores · /forum_topics (44127, 44164, 44336, 44369, 44633, 44727, 44742) · /project-gallery (unpublished)
- ADTF: https://africadeeptech.org/challenge-2026/ (Scoring Model, FAQ) · https://africadeeptech.org/challenge-2026/leaderboard (empty; bundle `/assets/challenge-2026.leaderboard._index-BAFglcZl.js`)
- Profiler: https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler (README, Dockerfile, src/adtc_profiler/{throughput,accuracy,memory,cli}.py, PR #1/#2, commits through 2026-08-15)
- Template: https://github.com/Africa-Deep-Tech-Foundation/adtc-2026-submission-template (README rules; 99 forks)
- Substack: https://adtc.substack.com (launch post 06-18; knowledge-session posts; no scoring content)
- Press: https://techafricanews.com/2026/07/30/africa-deep-tech-foundation-launches-2026-laptop-llm-challenge/ ; https://techpoint.africa/brandpress/africa-deep-tech-foundation-launches-the-laptop-llm-challenge/ ; https://techtrendske.co.ke/2026/07/29/africa-deep-tech-foundation-2026-launches/
- Competitor repos: as named in §2 (all `github.com/<owner>/<repo>`); HF: huggingface.co/{Wayazi/qwen3.5-2b-adtc-gguf, kherin/karoguard-adtc-2026-gguf, iamsamuelk/adtc-2026-agri-advisor-qwen1.5b-persona, fallback-ai/Homa-Afrique-Gemma-4B, NEVODESIGN/agbe-1b, Cruso003/AgriDoc-1.7B-GGUF}
