# R2 — How S_acc is judged and what the prompts look like (ADTC 2026, Laptop LLM track)

Research date: 2026-08-17 (Gate 1 due 2026-08-25 / Devpost form closes 2026-08-24 23:45 PDT).
Team context: team-muta, `math_scientific_reasoning`, submission GGUF `model/bitcpm4-8b-tq2_0-envocab.gguf` (arch `minicpm`, ChatML template, 32k trained ctx).

Legend: **[VERIFIED]** = read from a primary source (official page, repo source, profiler code, llama.cpp source at the audit tag, or a test I ran). **[INFERRED]** = my reasoning from verified facts. **[SECONDARY]** = third-party paraphrase, unverified.

---

## 0. Executive summary

1. **S_acc has two channels [VERIFIED]:** (a) an *automated multiple-choice benchmark* run by the profiler through **lm-eval-harness + llama-cpp-python** (loglikelihood scoring of raw text, `n_ctx=2048`, **no chat template**, greedy for generation tasks) on a "hidden 30% validation subset"; and (b) a **live judge chat** with the bare GGUF in a sandbox ("we spin up a fresh sandboxed instance of your exact submission … and the judge chats with it live through our in-browser interface"), scored 0–100 per response on your 2 `test_prompts` + 2 or 3 organizer-written hidden prompts in your domain, plus "quality of documentation". Relative weights of (a) vs (b) are **not published**.
2. **Only the GGUF reaches judging [VERIFIED]:** "Just the model … Judging is also scoped to the model's responses, not a broader application UI." Forum answer: "For the first round, we will only be testing your model." No mechanism to ship a system prompt, flags, or an app for Gates 1–2. The profiler Docker image ships **llama-bench + llama-cli + llama-server @ b10175** — the sandbox is almost certainly one of those two chat front-ends on your GGUF **[INFERRED]**.
3. **The GGUF file itself can carry behaviour [VERIFIED by source + local test]:** llama-server/llama-cli at b10175 use the GGUF's `tokenizer.chat_template` by default (`--jinja` is on by default), and llama-server's per-request sampling defaults are seeded from GGUF `general.sampling.*` keys (`temp`, `top_p`, `min_p`, `top_k`, `penalty_repeat`, …). Our file already carries `general.sampling.temp=0.8`, `general.sampling.top_p=0.8` (confirmed via `/props`). So a **default tutoring system prompt in the chat template + tuned sampling keys + reliable EOS** is the way to bake tutoring behaviour into the model file.
4. **No "validation-set samples", domain prompt list, or rubric were ever published anywhere I could find** (ADTF site, Devpost overview/rules/updates/forum, both GitHub repos and their history, the org profile, Substack, the 7 tutorial videos, Hugging Face). Devpost's timeline claims they were "published" at launch; a participant asked on Devpost on ~2026-08-10 where the validation set is and **got no answer**. The profiler's default task is `arc_easy` (explicitly a smoke-test default, not the audit task).
5. **Bonuses [VERIFIED]:** African-language "Alpha" bonus = "+15% on their panel score" for "meaningful functionality in at least one African language"; Budget Profile = "+10%" (no published condition beyond the claim flag); "African Use Case Bonus: Up to 10 extra points awarded for how applicable the model is to a real African use case" and "Supporting a local language is not a requirement — the primary language of evaluation for this competition is English."
6. **Sandbox context length is not published.** llama-server default `n_ctx=0` = the GGUF's trained context (`minicpm.context_length=32768` for our file → ≈1 GiB KV at f16 with 4 unified slots) and `n_predict=-1` (unlimited) — the model must stop on its own. Sandbox OOM/crash = disqualification.

---

## 1. Sources (all fetched 2026-08-17)

| # | Source | URL |
|---|---|---|
| S1 | ADTF challenge page (FAQ, scoring, gates) | https://africadeeptech.org/challenge-2026 |
| S2 | ADTF leaderboard ("Asante Benchmark Leaderboard", empty) | https://africadeeptech.org/challenge-2026/leaderboard |
| S3 | Devpost overview | https://adtc-2026.devpost.com/ |
| S4 | Devpost official rules | https://adtc-2026.devpost.com/rules |
| S5 | Devpost updates | https://adtc-2026.devpost.com/updates |
| S6 | Devpost discussions | https://adtc-2026.devpost.com/forum_topics (threads 44742, 44369, 44164, 44336, 44127, 44727) |
| S7 | Devpost resources | https://adtc-2026.devpost.com/resources |
| S8 | Profiler repo (README, Dockerfile, src, tests, examples, PRs #1 #2, full commit history) | https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler |
| S9 | Submission template repo (README, REPORT.md, metadata.json) | https://github.com/Africa-Deep-Tech-Foundation/adtc-2026-submission-template |
| S10 | Installed profiler 0.1.0 source | `~/miniforge3/envs/ai/lib/python3.12/site-packages/adtc_profiler/` |
| S11 | Profiler tutorial playlist (7 videos, auto-captions) | https://www.youtube.com/playlist?list=PLSj-s4_873dY (ids UQm-hP33Czo … AifmGRhMkdU) |
| S12 | llama.cpp at the audit tag b10175 (`common/common.h`, `common/common.cpp`, `common/arg.cpp`, `tools/server/*`) | https://github.com/ggml-org/llama.cpp/tree/b10175 |
| S13 | Local llama.cpp b10360 clone + Homebrew llama-server b10360 (behavioural tests) | `muta-iq/opt/llama.cpp`, `/opt/homebrew/bin/llama-server` |
| S14 | Substack archive (launch post + builder series) | https://adtc.substack.com |
| S15 | Peer submission (AgriDoc) — how another team read the rules | https://github.com/cruso003/agridoc-adtc2026 (REPORT.md) |
| S16 | Our own earlier digest | `Muta/docs/rules-digest.md` |

Not reachable: Discord (`https://bit.ly/ADTC_Discord` → expired invite `discord.com/invite/C6U2ZWdMF`); Wayback Machine (503 during the session); CompeteHub (403).

---

## 2. Q1 — How are model responses generated for judging?

### 2.1 What the official sources say [VERIFIED, verbatim]

**S1 (ADTF FAQ) — "How does offline/local judging execution work?"**
> "Judging is done by actually running your submitted model, not by reading a transcript or a static output log. When a judge opens your run, we spin up a fresh sandboxed instance of your exact submission inside an environment resource-capped to match the Standard Laptop profile (8 GB RAM, 4 CPU cores), and the judge chats with it live through our in-browser interface. There's no third-party tool involved on the judge's side — your score reflects how your model actually behaves under the real target hardware constraints."

**S1 — "How are the telemetry and qualitative scores calculated?"**
> "We use the formula: S_total = 0.50·S_acc + 0.30·S_perf + 0.20·S_eff - P_thermal. S_perf (Performance) and S_eff (Efficiency) are calculated automatically by running inference on standard target laptops. S_acc (Accuracy) is a qualitative evaluation graded by our judging panel."

**S1 — "Does evaluation measure my whole application, or just the model?"**
> "Just the model. Automated profiling and resource limits (memory, throughput, thermal) apply only to the LLM inference process itself (llama.cpp running your GGUF model) — we do not measure or enforce resource limits on any supporting application stack (CV, audio, sensing, etc.). Judging is also scoped to the model's responses, not a broader application UI."

**S1 — "What exactly do I need to submit for evaluation?"**
> "Just your model repository with a working `download_model.sh`, plus your two required test prompts. You are not required to run or submit any accuracy benchmarking yourself — you only need to produce your own performance and efficiency telemetry locally as a self-check (throughput, memory, thermal). Accuracy (S_acc) is scored entirely by the judging panel, who run your actual model — you never submit an accuracy number."

**S1 — "What exact benchmarks and prompts will be used for grading accuracy?"**
> "You will provide two test prompts with your submission. The organizers will then generate three additional hidden prompts within your chosen domain to test for response accuracy."

**S1 — "What specific tools or frameworks are allowed for quantization and deployment?"**
> "llama.cpp only. All submissions must run through llama.cpp using GGUF weights to ensure compatibility with our evaluation setup."

**S1 — Scoring model card, Accuracy (Sacc):**
> "Weighted combination of automated benchmark scores and qualitative assessment of model prompt responses by the judge panel."

**S3 (Devpost overview) — Leaderboard Scoring table, Sacc row:**
> "Weighted average of model response scored between 0 and 100 by a Judge." / Notes: "Weighted combination of automated benchmark scores and qualitative assessment of model prompt responses by the judge panel."

**S4 (Devpost rules) — Judging Criteria and Winner Selection:**
> "Model Accuracy & Quality — 50% — A combination of multiple-choice benchmarks and qualitative evaluations that includes accuracy of prompts, quality of documentation"
> "Model Throughput Performance — 30% — Evaluated relative to the maximum observed tokens per second"
> "Model Efficiency — 20% — Rewards lower RAM utilization profiles relative to the maximum memory budget"
> "African Use Case Bonus — Bonus — Up to 10 extra points awarded for how applicable the model is to a real African use case"
> "Hardware & Thermal Penalties — Penalty — 10 points deducted if core/package temperature exceeds 85∘C or if thermal throttling is flagged. OOM or sandbox execution crash results in disqualification"

**S8 (profiler README, Leaderboard Scoring):**
> "S_acc (Accuracy) | Qualifying score | Based on model responses to participant-submitted prompts, domain prompts, and hidden prompts supplied by judges."
(Commit `e26411ca` 2026-07-21 changed this from "Based on standard accuracy benchmarks." — the wording deliberately added *prompt responses*.)

**S9 (template README):**
> "`test_prompts` | ✅ | **Exactly 2 prompts** in your chosen domain. Organizers will add 2 hidden prompts to test for overfitting."
> Rules §7: "**Two test prompts required.** Your `metadata.json` must include exactly 2 prompts in the `test_prompts` array. Organizers will generate 2 additional hidden prompts within your domain. All 4 are used for scoring."
> REPORT.md section: "Your technical writeup. Judges and the LLM-based audit system will read this to understand your submission."

**S8 (examples/demo-submission/README.md):**
> "`test_prompts` must contain **exactly two** prompts — judges use them alongside domain and hidden prompts."

**S6 (Devpost forum 44164, organizer "Africa Deep Tech Community – Manager", ~June 2026):**
> Q: "Clarification if App should work completely offline? … Or only the model should be offline?"
> A: "For the first round, we will only be testing your model, and it has to work completely offline."

**S11 (tutorial video Part 1, auto-caption):**
> "Judging in the Africa DeepTech Challenge is measurement-based. The profiler is a standard tool that produces the benchmark report, which every submission is scored from. We look at the throughput, memory, CPU, and accuracy, all in one schema valid JSON file submission. The same tool is used in different instances. First, you run it on your laptop and ship a submission the JSON. Then, we'll run the exact same command on a cloud virtual machine, which matches the standard laptop profile, 8 GB RAM, four CPUs, and no GPU."

**S11 (Part 6):**
> "In real audit mode, the accuracy is mandatory. So, if you are issuing a submission and you don't include accuracy, uh it will be rejected. So, run the profiler on hardware that is close to the standard laptop profile because all of these will be verified."

Discrepancy to note: ADTF FAQ says **three** hidden prompts (2+3=5), the template says **two** (2+2=4), the profiler README says three *categories* ("participant-submitted prompts, domain prompts, and hidden prompts"). Plan for ~3–5 judged prompts, at least 2 of which you control.

### 2.2 Channel A — the automated benchmark (profiler `accuracy.py`) [VERIFIED from source]

`adtc_profiler/accuracy.py` (0.1.0, HEAD `ac2e137d`):
> "The model is evaluated in its quantized form, in-process, via llama-cpp-python (same llama.cpp runtime the challenge targets): we tokenize context+continuation, evaluate once, and read continuation log-probabilities straight from the logits. lm-eval supplies the datasets, prompting, and metrics."
> `run_benchmark(model_path, *, task="arc_easy", limit=50, language="en", seed=42)` — docstring: "Defaults to a small ARC-Easy subset (50 questions) for fast smoke testing. **Real audits use the full hidden 30% validation subset distributed by judges.**"

Mechanics that matter for us:
- `Llama(model_path, n_ctx=2048, verbose=False)` — **`n_ctx=2048` hardcoded**; long docs are left-truncated.
- `loglikelihood`: `self._llm.tokenize((context+continuation).encode(), add_bos=True, special=False)` — **raw text, no chat template**, so any system prompt/template we bake into the GGUF is invisible here. Metric preference `acc_norm` → `acc` → any numeric.
- `generate_until` (for generation tasks like gsm8k): `create_completion(prompt=context, max_tokens=max_gen, temperature=0.0, stop=until)` — **greedy raw completion**, no template.
- `cli.py --accuracy-task` help: "lm_eval task name. Real audits use the hidden validation subset." Audit mode hard-fails (exit 4) if the accuracy stack is unavailable.
- `comparator.py`: "Accuracy comparison is NOT a delta-vs-claim check: participant accuracy is on public benchmarks; audit accuracy is on the hidden 30% subset. The comparator passes audit accuracy through as-is for judge review rather than diffing."
- The wheel is built with `CMAKE_ARGS="-DGGML_NATIVE=OFF"` only (Dockerfile stage 2) — i.e. AVX2 stays on for the accuracy stack; the SIMD-less build applies to `llama-bench`/`llama-cli`/`llama-server` (stage 1) only.

So Channel A is: an lm-eval **multiple-choice (loglikelihood) task** — the identity of the task/dataset ("hidden 30% validation subset") is unpublished; ARC-Easy is only the default. `metric` in our shipped `submission.json` = `arc_easy acc_norm 0.84 (50 samples)`.

### 2.3 Channel B — the live judge chat sandbox [VERIFIED facts + INFERRED mechanics]

Verified facts: sandbox = "fresh sandboxed instance of your exact submission … resource-capped … (8 GB RAM, 4 CPU cores)"; judge "chats with it live through our in-browser interface"; "no third-party tool involved on the judge's side"; only the model is tested; the audit reference Docker image (profiler `Dockerfile`, `LLAMACPP_REF=b10175`, `-DGGML_AVX=OFF -DGGML_AVX2=OFF -DGGML_FMA=OFF -DGGML_F16C=OFF`, targets `llama-bench llama-cli llama-server`) copies **`llama-server` and `llama-cli` onto PATH** — the only reason to ship a server/CLI in a profiler image is to serve chat; the profiler itself never calls them. Repo has a `.gcloudignore` → the "evaluation orchestrator inside secure cloud VMs" is GCP-hosted [INFERRED].

Therefore [INFERRED, high confidence]: the judge chat is `llama-server -m <your.gguf>` (or `llama-cli`) from that image, driven by their web UI (possibly llama.cpp's built-in UI, which is enabled by default and syncs its sampling sliders to the server's defaults) hitting `/v1/chat/completions`.

What that means concretely, from llama.cpp **b10175** source [VERIFIED]:
- `common/common.h`: `bool use_jinja = true;` and `common/arg.cpp` only flips it to false for `LLAMA_EXAMPLE_COMPLETION` and `LLAMA_EXAMPLE_MTMD` → **llama-server and llama-cli render chats with the GGUF's `tokenizer.chat_template` via the Jinja engine by default** (`--chat-template … (default: template taken from model's metadata)`).
- `n_ctx = 0` ("context the model was trained with"), `n_predict = -1` ("no limit"), `n_batch 2048`, `n_ubatch 512`, `system_prompt = ""` (and `-sys/--system-prompt` is not even a server flag).
- `tools/server/server.cpp`: `n_parallel < 0` → "using n_parallel = 4 and kv_unified = true" → 4 slots sharing one KV of size n_ctx.
- `tools/server/server-schema.cpp:524`: `params.sampling = params_base.sampling;` — per-request defaults come from the server's params, and `common/common.cpp:1266` `common_init_sampler_from_model(model, params.sampling)` overwrites those with the GGUF's `general.sampling.{sequence,top_k,top_p,min_p,xtc_*,temp,penalty_last_n,penalty_repeat,mirostat*}` unless the operator passed the flag explicitly. Otherwise defaults: temp 0.8, top_p 0.95, top_k 40, min_p 0.05, repeat_penalty 1.0.
- `tools/server/server-context.cpp:1452`: thinking is enabled iff `--reasoning` is not `off` **and** the chat template's differential analysis says it supports `enable_thinking`.
- Built-in UI (`tools/ui/docs/flows/settings-flow.md`): "Non-overridden params adopt server default" — the UI's temperature/top_p sliders follow the server (hence the GGUF) unless the judge changes them.

Local confirmation (Homebrew llama-server b10360, same code paths): with our GGUF and stock flags, `/props` reports `temperature 0.8, top_p 0.8` (top_p ≠ the 0.95 default ⇒ read from the GGUF), `total_slots 4`, `n_predict -1`; a plain `/v1/chat/completions` request rendered `<|im_start|>user…<|im_start|>assistant\n<think>\n\n</think>\n` and the log said `chat template, thinking = 0`; reply to "What is 3/4 of 24?" was `3/4 of 24 is $\boxed{18}$.`

### 2.4 Is the participant's app used at any gate?

- Gate 1 / Gate 2: **No** [VERIFIED] — "Just the model", "only be testing your model", "The evaluator downloads weights fresh via download_model.sh" (template rules §2), profiler consumes only `metadata.json` + the GGUF; `model.packaging` enum offers `docker_image | docker_build_from_repo | binary_bundle` but nothing in the pipeline reads it beyond schema validation.
- Gate 3 (Live Defense, Oct 17): S4 dates: "Remote live pitches, technical Q&A, and winners announced the same day." S1 deliverables: "Final pitch deck (max 10 slides) · Live-session attendance confirmation · Technical setup verification". Screenshots/video "showing your build in action" are Gate 1 report deliverables. So the app is presentation material (video, screenshots, pitch, demo you drive), not something judges run [INFERRED from the above].

---

## 3. Q2 — The "validation-set samples" published at launch

**S4 (Devpost rules, Dates table) [VERIFIED]:**
> "Tue June 16, 2026 — Launch — Contest opens. Problem domains, hardware profile, profiler tool, and validation-set samples published."
> "Tue August 25, 2026 — Gate 1 Deadline — Proposals + prototypes submitted. Two-step judging: proposal screen, then prototype review of the top ~10%."
> "Tue Sept 8, 2026 — Semifinalists Announced — Up to 20 teams notified. Gate 2 narrowing audit begins."
> "Tue Sept 22, 2026 — Semifinalist Submission — Semifinalists submission deadline"
> "Tue Sept 29, 2026 — Finalists Announced — Up to 10 teams advance to Live Defense. Pitch-prep window opens."
> "Sat, Oct 17, 2026 — Live Defense & Awards — Remote live pitches, technical Q&A, and winners announced the same day."

**What I searched, and found nothing:** ADTF site + its JS bundles (all FAQ text is in `challenge-2026-BFN64hlc.js`; no rubric/sample text beyond what renders), Devpost overview/rules/resources/updates/gallery ("The hackathon managers haven't published this gallery yet"), the profiler repo at every commit since `d36c2e35` (2026-06-15) — no dataset, no task YAML, no prompt list; the template repo; the org `.github` repo; Hugging Face (`search=adtc`, `author=Africa-Deep-Tech-Foundation` → nothing official); Substack (launch post says only "Applications are now open"); the 7 tutorial videos (only ARC download is mentioned: "the first accuracy run will download the an aux data set from Hugging Face" [= ARC]).

**S6, thread 44742 (2026-08-10, unanswered as of 2026-08-17) [VERIFIED]:**
> "The challenge description states that these are 'standardized ADTC benchmarking domains, and validation sets are provided for each.' We haven't been able to locate the Agriculture validation set… How is the accuracy score (Sacc) computed…? The reference adtc-profiler runs arc_easy (a multiple-choice, loglikelihood task) by default, but the README's scoring section describes Sacc as based on 'model responses to participant-submitted prompts, domain prompts, and hidden prompts supplied by judges.' Could you confirm whether the Agriculture accuracy is: 1- a multiple-choice / loglikelihood task (like arc_easy), or 2- free-text responses to advisory prompts, assessed by judges (LLM or human)? Is there a public dev/validation subset…?" — **0 comments.**
(The current Devpost text reads only "These are the ADTC standardized benchmarking domains."; the "validation sets are provided for each" phrasing the poster quotes is not on the page today — likely edited [INFERRED].)

**S6, thread 44369 (Ahmed Madi, ~mid-July, unanswered) [VERIFIED]:** reports the old `base_url=local` bug and "Missing --apply_chat_template degrades accuracy … Instruct models are evaluated on unformatted raw prompts, resulting in below-chance scores (e.g., our model scored 0.12 acc_norm on arc_easy…)" and asks "Are participants permitted to submit submission.json with an empty accuracy array … since the official audit utilizes a hidden validation set?" — 0 comments. (The tutorial's answer is effectively no: "accuracy is mandatory … it will be rejected".)

**Only concrete prompt examples that exist [VERIFIED]:** the demo/template `test_prompts` for `coding_assistants` —
> tp_001 "Write a Python function that reads a CSV file and returns the column with the highest mean value."
> tp_002 "Explain the difference between a list and a tuple in Python, and give one example where each is the better choice."
— i.e., one *task* prompt and one *explain/teach* prompt. Ours (already in `metadata.json`) follow the same shape: tp_001 a worked-arithmetic word problem in naira ("Show your working"), tp_002 a misconception-diagnosis physics prompt.

Bottom line for Q2: **no domain sample prompts, no rubric, no scoring guide, no dataset were ever published**; "hidden 30% validation subset" (profiler) + "2–3 hidden prompts within your chosen domain" (site/template) is all that exists. Treat `arc_easy`-style MC science QA + free-text math/science tutoring prompts as the two things to optimise for [INFERRED].

---

## 4. Q3 — Rubric criteria for tutoring quality

**Published criteria text, exhaustively [VERIFIED]:**
- S4/S3: "A combination of multiple-choice benchmarks and qualitative evaluations that includes **accuracy of prompts, quality of documentation**".
- S3: "Weighted average of model response scored between 0 and 100 by a Judge."
- S1: "qualitative assessment of model prompt responses by the judge panel"; hidden prompts "to test for response accuracy"; template: hidden prompts "to test for overfitting".
- S9: "Judges and the LLM-based audit system will read [REPORT.md] to understand your submission" and REPORT.md must cover Problem (target user "in an African context"), Design Decisions, Constraints, Benchmarks — "Keep it factual and specific. One to three pages is ideal."
- S3 domain definition: "Math & Scientific Reasoning - problem solving, proof assistance, scientific question-answering, and quantitative reasoning tasks."
- S1 (2025 archive text, generic): "Judges will assess both the final solution and the development journey. Emphasis will be placed on how participants approached problem-solving under constraints, made thoughtful technical decisions, and demonstrated innovation throughout the process."
- **[SECONDARY]** opportunitiesforyouth.org paraphrase: "Accuracy (50%): Judges evaluate: Automated benchmark performance, Prompt quality, Model correctness, Overall reasoning ability" — not on any official page; do not rely on it.

**There is no published rubric** for correctness / pedagogy / safety / format. Judges are 9 named people (Oji Udezue, Yannick Djoumbou Feunang, Oluwatobi Oyinlola, Christine Abernathy, Omoju Miller, Peter Ing, Mbangula Lameck Amugongo, Ola Fadiran, Houda Ghozzi — S3), each presumably typing 4–5 prompts into a chat box and giving 0–100 [INFERRED]. What a 0–100 chat-judge in a math/science *education* domain will reward [INFERRED, but consistent with "response accuracy", "problem solving", "quantitative reasoning"]: (1) the correct final answer, visibly stated; (2) legible step-by-step working; (3) staying on-domain and refusing to hallucinate; (4) responsiveness in the sandbox (no minute-long `<think>` traces on a 4-vCPU no-AVX box); (5) an identity/tone that reads as a tutor for African secondary students (the use-case bonus and "Best Localisation" both look at this); (6) documentation quality (explicitly in the criterion).

---

## 5. Q4 — Bonuses and multipliers

**Verbatim [VERIFIED]:**
- S1 hardware section: "**African Alpha Bonus** — Submissions with meaningful functionality in at least one African language earn +15% on their panel score."
- S1 scoring footer: "Score multipliers — Budget Profile +10% · African Language +15%".
- S1 FAQ: "What African languages qualify for the Alpha Bonus? — Any African language qualifies when the functionality is meaningful. Swahili, Yoruba, Wolof, Igbo, Zulu, Amharic, Hausa, Shona, and Twi are all excellent examples."
- S1 FAQ: "What qualifies an entry for the 'African Use Case Bonus'? — The bonus rewards any solution that clearly caters to real-world African contexts and infrastructure realities. Supporting a local language is not a requirement—the primary language of evaluation for this competition is English."
- S3/S4: "African Use Case Bonus — Up to 10 extra points awarded for how applicable the model is to a real African use case."
- S1 Gate 1 deliverables: "Bonus claims: African language support / budget laptop".
- S1 prizes: "Best Localisation Award — Specialized award for demonstrating the deepest integration with African languages, offline data, or local contextual depth. $1,500"; S3/S4 name it "Best African Use Case — $1,500 — Awarded for the strongest African use case implementation. 3-month residency".
- S9 field reference: "`african_alpha_claim` | `true` only if claiming the African Use Case Bonus"; "`budget_laptop_claim` | Must be `true` — all submissions target the 8 GB RAM laptop profile"; "`language_scope` | Array of BCP-47 language codes. Must include at least one."
- Profiler schema: `african_alpha_claim: boolean`, `budget_laptop_claim: boolean`, `language_scope: string[] (minLength 2 each)`; nothing else in the pipeline consumes them.

**Reading [INFERRED]:**
- Three distinct things exist: (i) *African Use Case Bonus* — up to **+10 points** additive, judged on applicability, **English is fine**; (ii) *African Language / "Alpha" multiplier* — **+15% on the panel score** (i.e. on the judged S_acc component, most plausibly), requires "meaningful functionality in at least one African language" — since judges only interact by chatting with the bare GGUF, the only way to *demonstrate* that is for the model to understand/answer in that language when prompted; the report/video can claim it, but the sandbox will test it; (iii) *Budget Profile +10%* — no condition published anywhere beyond the claim flag; the template says the flag "must be true" for everyone, so it may be a universal +10% or may relate to a lower-spec "budget" profile that is not otherwise defined. Unknown; low-effort to keep `true`.
- Naming trap: the template maps `african_alpha_claim` to "African Use Case Bonus" while the site's "African Alpha Bonus" is the *language* +15%. Our `metadata.json` has `african_alpha_claim: true` with `language_scope: ["en"]`. If a reviewer reads the flag as a language claim, an English-only model looks like a false claim; if they read it as use-case, it is fine and supported by the naira/classroom prompts. Mitigation: state explicitly in REPORT.md and the Devpost form which bonus we claim and why (African use case: offline classroom tutor, local-currency word problems, WAEC/NECO-style questions), and consider a small amount of Yoruba/Hausa/Swahili tutoring capability *only if* it can be shown to be "meaningful" in chat — otherwise do not claim the language bonus.
- Evidence channels: `metadata.json` flags, the Devpost form's bonus questions ("Bonus claims" is a Gate 1 deliverable), REPORT.md, the 2-minute video, and — decisively — how the model behaves when a judge types in an African language.

---

## 6. Q5 — The judge chat sandbox and the live defense

**Verified:** see §2.1 quotes ("fresh sandboxed instance of your exact submission", 8 GB RAM / 4 CPU cores, "in-browser interface", "no third-party tool involved on the judge's side", "OOM or sandbox execution crash results in disqualification"). Reference image: profiler `Dockerfile` (llama.cpp b10175, AVX/AVX2/FMA/F16C off, ships llama-server + llama-cli), README: `docker run --rm --memory=7.5g … adtc-profiler:latest run --mode audit`. Devpost dates: Gate 1 "Two-step judging: proposal screen, then prototype review of the top ~10%"; Gate 2 "narrowing audit"; Gate 3 "Remote live pitches, technical Q&A". Gate 3 deliverables (S1): "Final pitch deck (max 10 slides) / Live-session attendance confirmation / Technical setup verification". Gate 2 deliverables (S1): "30-minute technical Q&A session (scheduled) / Prompt responses to reviewer clarification requests / Optional: 1-page response to feedback / Optional: updated benchmark report".

**Inferred (high confidence):** the sandbox runs the profiler image (or a sibling built the same way) with `llama-server` on the GGUF fetched by `download_model.sh`; the "in-browser interface" is either llama.cpp's built-in UI or a thin custom chat page over `/v1/chat/completions`. It does not run our repo's Docker stack, FastAPI gateway, RAG, or system prompt. **Context length**: unpublished; unless they pass `-c`, llama-server allocates the GGUF's trained context (`minicpm.context_length = 32768` for our file) as one unified KV shared by 4 slots. For our tensor shapes (32 layers, 2 KV heads, head_dim 128, f16 KV) that is 32 KiB/token → **≈1.0 GiB of KV at 32k**, on top of the ≈2.2 GB weights and compute buffers — comfortably under 7.5 GB, but a model with a 128k–256k trained context and full-MHA KV would OOM the sandbox at defaults [VERIFIED arithmetic, INFERRED applicability]. **Generation cap**: `n_predict = -1` → the model must emit EOS (`<|im_end|>` id 44408) reliably; a looping model burns the judge's patience or the context.

**Can we ship a system prompt / app?** Not as a flag or file — nothing in the pipeline reads anything but `metadata.json` and the GGUF. **Yes inside the GGUF** (chat template default system prompt, `general.sampling.*`, `general.name`) — see §7. The app can be shown in the Gate 1 video/screenshots and Gate 3 pitch, and mentioned in REPORT.md as the deployment story, but it will not be exercised by judges.

---

## 7. Recommendation — bake tutoring behaviour into the model file

Because judges chat with the bare GGUF through stock llama-server/llama-cli (Jinja on, no system prompt, sampling seeded from GGUF metadata) and the MC benchmark scores raw text without a template, the levers are:

1. **Chat template with a default tutor system prompt (merge, don't replace).** Rewrite `tokenizer.chat_template` so that (a) if the request has no `system` message, a persona system turn is prepended; (b) if the request *does* carry a system message (a judge UI may send "You are a helpful assistant"), the persona is prepended to it rather than dropped; (c) the assistant turn starts with an **unconditional** empty think block `<think>\n\n</think>\n` so llama.cpp's differential analysis reports "thinking = 0" and every llama.cpp version renders the fast direct-answer mode (our template currently only does this when the caller passes `enable_thinking=false`; b10360 happened to render it by default because the analysis found no reasoning markers, but making it unconditional removes version dependence). Tested with llama-server b10360 `--chat-template-file` on SmolLM2 and inspected via `/apply-template` and `--verbose`: persona injected in both cases, `chat template, thinking = 0`, model answers directly. Template used (adjust persona text; keep it short — every judged turn pays its prefill on a no-AVX 4-vCPU box):

```jinja
{%- set persona = "You are Muta, an offline mathematics and science tutor for secondary-school students in Africa. Solve step by step, state the final answer clearly, and end with one short check-your-understanding question." -%}
{%- set ns = namespace(has_system=false) -%}
{%- for m in messages if m['role'] == 'system' -%}{%- set ns.has_system = true -%}{%- endfor -%}
{%- if not ns.has_system -%}{{ '<|im_start|>system\n' + persona + '<|im_end|>\n' }}{%- endif -%}
{%- for message in messages -%}
{%- if message['role'] == 'system' -%}{{ '<|im_start|>system\n' + persona + '\n\n' + message['content'] + '<|im_end|>\n' }}
{%- else -%}{{ '<|im_start|>' + message['role'] + '\n' + message['content'] + '<|im_end|>\n' }}{%- endif -%}
{%- endfor -%}
{%- if add_generation_prompt -%}{{ '<|im_start|>assistant\n' }}{{ "<think>\n\n</think>\n" }}{%- endif -%}
```
   Write it with `gguf-py/gguf/scripts/gguf_new_metadata.py in.gguf out.gguf --chat-template-file tutor.jinja --general-name "Muta Tutor (BitCPM4-8B)"` (rewrites metadata only; tensor bytes unchanged → scored TPS/RSS unchanged). Verify with `llama-server --jinja -m out.gguf` → `/apply-template` and `/props`, and once with `--no-jinja` (legacy path falls back to plain ChatML because the template contains `<|im_start|>` — persona lost but format intact; acceptable degradation).
   Decide deliberately whether to *keep* thinking: on the audit box a `<think>` trace of a few hundred tokens at single-digit tok/s is a judge-visible minute of silence per prompt; unless measured accuracy gains on our two prompts justify it, ship no-think and put the "step by step" into the persona instead.

2. **Sampling defaults in the GGUF (`general.sampling.*`).** Verified honoured by llama-server at b10175 (`common_init_sampler_from_model`) and already present in our file (temp 0.8/top_p 0.8 from the MiniCPM4.1 generation config). For a tutor, prefer lower variance: e.g. `temp 0.3–0.5`, `top_p 0.9`, `min_p 0.05`, `penalty_repeat 1.05`, `penalty_last_n 64` — evaluate on our two prompts + ~10 guessed hidden ones (worked arithmetic/percentages/ratios, algebra, geometry, unit conversion, basic physics/chemistry/biology explanations, misconception diagnosis, "explain like I'm in JSS3", proof sketch). Note the accuracy-stack path ignores these (greedy/loglikelihood), so they only affect the judged chat.

3. **Termination and identity hygiene.** Confirm `tokenizer.ggml.eos_token_id` (44408 = `<|im_end|>`) is what the model actually emits at end of turn under the new template on the b10175 image build (server default `n_predict=-1`); check multi-turn (judges will follow up); set `general.name`/`general.description` to the tutor identity (surfaces in `/props`, `/v1/models`, the built-in UI title); keep `general.languages` honest.

4. **Protect Channel A.** The MC benchmark is raw-text loglikelihood at `n_ctx=2048` through llama-cpp-python (AVX2 on) — nothing above touches it, but any further weight/vocab surgery must be re-checked with `adtc-profiler run --mode participant` (accuracy stage on) and ideally `--accuracy-task` on a couple of science MC tasks (arc_challenge, sciq, mmlu-stem subsets) as proxies for the hidden subset. Ship the full-run `submission.json` (accuracy non-empty — "it will be rejected" otherwise).

5. **Rehearse the sandbox exactly.** Build the profiler image (`docker build -t adtc-profiler .` from S8), then `docker run --memory=7.5g --cpus=4 --entrypoint llama-server adtc-profiler -m /submission/model/…gguf --host 0.0.0.0` with **no other flags**, and chat via `/v1/chat/completions` (no system message, no sampling overrides) with our 2 prompts + guessed hidden prompts; record RSS (`docker stats`), tok/s, and full transcripts for REPORT.md. Also try the built-in UI once. This is the closest reproducible proxy to what a judge sees.

6. **Test prompts and report.** Our two `test_prompts` are the only judged prompts we control — keep them the ones the model answers best *and* that showcase African context + tutoring format (current tp_001/tp_002 are good; re-verify final answers under the shipped template/sampling). REPORT.md is explicitly part of "Model Accuracy & Quality … quality of documentation" and is read by "the LLM-based audit system": include the sandbox-rehearsal transcripts, the persona/template design decision, and the exact claim we make for the African Use Case bonus.

7. **Optional, test before doing:** lowering `minicpm.context_length` in metadata would shrink default KV in the sandbox, but the arch uses `longrope` factors keyed to the trained context — could change rope selection; RSS at 32k is already fine, so skip unless a bigger model is chosen.

---

## 8. Open questions (ask on Discord/email `africadeeptechcommunity@gmail.com` / `challenge@africadeeptech.org`; none answered publicly)

1. Which lm-eval task(s)/dataset form the "hidden 30% validation subset" for `math_scientific_reasoning`, and where are the "validation-set samples" the June 16 timeline says were published? (Devpost thread 44742 already asks; no reply.)
2. Weighting between the automated benchmark and the judge-panel chat inside S_acc.
3. Sandbox specifics: llama-server flags (`-c`, `--temp`, `-t`), whether the interface sends a system prompt, and whether the built-in UI or a custom page is used.
4. Number of hidden prompts (2 per template vs 3 per FAQ) and whether "domain prompts" are a third set.
5. Exact condition for the Budget Profile +10% and whether the +15% language multiplier requires the model to converse in the language.
6. Whether `african_alpha_claim` means the language bonus or the use-case bonus.

---

## Appendix A — Verbatim ADTF FAQ block (S1), for reference

- "What hardware do I need to develop on? — The target is the ADTC Standard Laptop (8 GB RAM, integrated graphics). You may develop on any machine, but your final model must run without cloud dependencies on the target specifications."
- "What does cross-disciplinary actually mean? — Your local LLM must connect to another deep-tech discipline in a load-bearing way. Examples include offline RAG over agricultural records, edge sensing, geospatial analysis, or local medical diagnostic assistance."
- "Can I use fine-tuned open-source models? — Yes. You are encouraged to use open-source base models (e.g. Llama, Mistral), quantize them, fine-tune them on local data, and compile them for local CPU runtimes."
- "Where do I get my ADTC Team ID for metadata.json? — Your Team ID is generated automatically when you register your team on DevPost — use that same ID in your submission's `metadata.json`." (Forum 44336 clarifies: "The team ID in this context means the project ID. E.g for this Devpost project (https://devpost.com/software/project-farmspeak) it is : project-farmspeak".)
- "What is the maximum allowed size for the model…? — There is no strict maximum size limit. However, your model will be evaluated entirely on its performance and efficiency on the standard benchmark computer (8 GB RAM). Keep memory constraints in mind to avoid OOM disqualification."
- "How will the final benchmarking and audit be conducted on the 'Standard Laptop' profile? — We will run your model on a dedicated testing machine using our automated evaluation framework. To ensure your model tests successfully without errors, your submission must conform to the official template."
- "What do I enter for 'Self Reported Profiler Performance Score (Sperf)' and 'Self Reported Profiler Efficiency Score (Seff)' on DevPost? — These are two separate numeric fields on the DevPost submission form — enter one plain number in each, not a combined string like 'Sperf=46, Seff=41'. Your local profiler's `submission.json` gives you raw numbers, not the normalized 0–100 score, so compute each score yourself from your own run, then enter the resulting number in each field."
- "How will core temperatures and thermal throttling be monitored during testing? — We capture the device's temperature immediately before and immediately after each benchmark run. For multiple runs, we introduce a cooldown delay between them and confirm the system has returned to its baseline temperature before starting the next one… A 10-point thermal penalty applies if the CPU throttles or the peak core temperature exceeds 85°C."
- "Are hybrid approaches allowed, or must the application be 100% offline? — The model must run 100% offline with zero external network dependencies during our testing window."
- "Does the 2-minute video require a live demonstration of the model running in real-time? — While seeing your model running live is highly encouraged, it is not strictly required. This video is your opportunity to pitch yourself and your engineering work to the judges…"
- Scoring cards: "Speed (Sperf) — Generation speed relative to the fastest submission across all teams. Sperf = 100 × (TPSact ÷ TPSmax) — TPSact: actual tokens/sec during audit · TPSmax: highest speed across all submissions"; "Efficiency (Seff) … Seff = 100 × ((7 GB − Peak RAM) ÷ 7 GB) — Peak RAM: maximum RSS measured during audit · Budget = 7 GB"; "−10 Thermal Penalty"; "0 OOM / Crash → Disqualified — Out-of-memory or sandbox crash results in Stotal = 0 and immediate disqualification."; "Memory ceiling 7 GB RAM — Exceeding this limit results in immediate disqualification (Stotal = 0)."

## Appendix B — Peer reading (S15, [SECONDARY] but instructive)

AgriDoc (cruso003) REPORT.md: "the bare `.gguf` is judged conversationally (S_acc, 50%). So the *model itself* must cover all four [sub-domains]…"; "Judges chat the **bare `.gguf`**, so the *model* — not just the app — must be safe and useful conversationally, with no system prompt."; they gated releases with "an **independent, blind reviewer chatting the bare gguf** the way judges do (no system prompt, sampled, single- *and* multi-turn, adversarial)"; and found "the **identity leak was the chat template, not the weights** — we swapped Qwen2.5's 'You are Qwen…' default system for the **AgriDoc persona**" — i.e., another team independently arrived at the same "bake the persona into the chat template" mechanism.

## Appendix C — Files/artefacts from this research (scratchpad, not in repo)

`/private/tmp/claude-501/-Users-timii-Developer-Muta/87be2b7d-3db1-4a09-b73d-eb31657570f8/scratchpad/r2/` — raw HTML/text of every page above, forum threads, tutorial transcripts (`yt/*.txt`), `tutor_template.jinja` (tested), `server*.log`.
