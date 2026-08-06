# ADTC 2026 — Math & Scientific Reasoning (Education)

Offline, adaptive AI tutor for math and scientific reasoning, running on the 8 GB ADTC laptop. [Brilliant](http://brilliant.org)'s / [Marble's](https://withmarble.com/) interactivity + Khan Academy's curriculum breadth + Encarta/Britannica's self-containedness — no server required. Groups below follow dependency order: each rests on the one above it.

```
Constraint → Model → Inference → Correctness/Safety → Pedagogy
   → Exam Prep → Interface → Collaboration/Distribution
   → Evaluation/Business → Competition Strategy → Story
(Team Study Shelf runs alongside all of the above.)
```

## **Process**
 - Load model locally -> (RLHF) Fine-tune (Train on 10 years WAEC, JAMB, and other African exams) -> Post-training quantisation -> [quantisation aware training](https://github.com/mit-han-lab/llm-awq) -> inference engine -> Run benchmark on questions (WAEC)

 - Read tons of papers on optimisation for LLMs on edge, else you wouldn’t figure things like [this](https://github.com/mit-han-lab/llm-awq) even w/ai. Browse references in papers, too

## 0. Constraint
- Hardware: i5 (10th–12th gen) / Ryzen 5 (3000–5000), 8 GB DDR4, integrated graphics only, 256 GB SSD, Ubuntu 22.04 — no GPU at deployment.

$$
S_{\text{total}} = 0.50S_{\text{acc}} + 0.30S_{\text{perf}} + 0.20S_{\text{eff}} - P_{\text{thermal}}
$$

- $S_{\text{acc}}$ (50%) — tutoring quality → Section 3

$$
S_{\text{perf}} = 100 \times \frac{\mathrm{TPS}_{\mathrm{act}}}{\mathrm{TPS}_{\mathrm{max}}}, where $TPS_{max} \approx 15$ (provisional).
$$

$$
S_{\text{eff}} = 100 \times \frac{7\mathrm{GB} - \mathrm{Peak\ RAM}}{7\mathrm{GB}}
$$

Example: peak RAM reduction from **4 GB** to **3 GB** increases $S_{\text{eff}}$ from **42.9** to **57.1**.

- $P_{\text{thermal}}$: −10 if temperature exceeds **85°C** or thermal throttling occurs.

**Implication:** A small quantized model combined with retrieval and verified tool calls beats a large model squeezed onto constrained hardware.

- Energy consumption is included as an evaluation metric.

## --- See https://github.com/addyosmani/agent-skills for Setup ---

## 1. Model Layer
- Candidates to bake off: Qwen3 (0.6B–4B), Phi-4-mini, DeepSeek-R1 distills, Gemma small, [Liquid AI](http://liquidai.com) LFMs — score on accuracy/GB, not raw accuracy.
- Fine-tune with **Unsloth**; corpus = WASSCE/JAMB/KCSE past questions + worked solutions + Socratic dialogue transcripts.
- Refs: [Hugging Face docs](https://huggingface.co/docs), [QWEN0.6B from scratch](https://github.com/emmanuelalo52/QWEN0.6B), [linas.substack GLM guide](https://linas.substack.com/p/glm-52-local-ai-guide).
- Udutech's ~5hrs GPU credit = training only; model gets quantized down before deployment (Section 2).
- Consider: train a draft model alongside the full model → speculative decoding (Sec 2) + standalone fast "hint mode."
- Allow option to select models (and even use a cloud model.)

## 2. Inference & Optimization
- allow the option for weight streaming (better than it's not available).
- Format: GGUF/GGML, llama.cpp. Follow [ggerganov](https://x.com/ggerganov?lang=en), incl. [tip](https://x.com/ggerganov/status/2039752638384709661?s=20) + [tip](https://x.com/ggerganov/status/2039804601810001921?s=20).
- Quantization: [nor-blog](https://nor-blog.pages.dev/posts/2025-05-14-quantization/); 4-bit baseline.
- **Adaptive precision:** 4-bit for simple arithmetic, 8-bit for multi-step proofs (quantization error breaks proofs, not arithmetic).
- Speculative decoding, MTP, model pruning — benchmark each with/without (feeds Section 9's table).
- Build-your-own-engine ambition: study [Cactus Compute](https://cactuscompute.com) (zero-copy graphs, ~10x RAM via mmap, phone-tier) and [Mirai](https://trymirai.com).
- Kernel study shelf (methodology transfers to CPU AVX2/AVX-512 even with no GPU to deploy):
  [GEMM on H100](https://hamzaelshafie.bearblog.dev/worklog-optimising-gemm-on-nvidia-h100-for-cublas-like-performance-wip/) ·
  [CUDA Matmul Kernel worklog](https://siboehm.com/articles/22/CUDA-MMM) ·
  [Outperforming cuBLAS on H100](https://cudaforfun.substack.com/p/outperforming-cublas-on-h100-a-worklog) ·
  [Basic facts about GPUs](https://damek.github.io/random/basic-facts-about-gpus/) ·
  [GPU Puzzles](https://github.com/srush/GPU-Puzzles) ·
  [Modal GPU glossary](https://modal.com/gpu-glossary) ·
  [IIT Delhi CUDA book](https://www.cse.iitd.ac.in/~rijurekha/col730_2022/cudabook.pdf) ·
  [GEMM-on-GPU tutorial](https://salykova.github.io/gemm-gpu) (has a CPU-side companion).
  [everythign i learned about local llms](https://nullprogram.com/blog/2024/11/10/)
- [z_ml](https://x.com/zml_ai/status/2074770878458417195)
- KV-cache quantization (biggest hidden RAM cost), `mmap` model loading, cap thread count to avoid the −10 thermal penalty.
- See [bitnet.cpp](https://github.com/microsoft/BitNet)
- Must be multi-modal (and can even respond in whatever format to the student. see [audio](https://github.com/pwilkin/thinksound.cpp).
- Switch between f4 and f16 to get the best mixed results without triggering throttling.
- Run these models on phones, see bigger competition, [Africa AI X-Prize](https://africaaixprize.org/#challenge). Other companies include: [cactuscompute.com](cactuscompute.com), [trymirai.com](trymirai.com)
- Run on Bare Android/Nokia touch light
- Swing between CPU, GPU, and cloud (if it notices that GPU and Cloud are available for better responses).

## 3. Correctness & Safety
- Route arithmetic/algebra/calculus through **SymPy/NumPy** — cheapest hallucination fix available.
- **Lean 4 + Mathlib + Lean Copilot** (Caltech LeanDojo) for the proof-assistance requirement.
- **RAG** over local textbooks/past papers/formula sheets — grounds answers, keeps model small (helps $S_{\text{eff}}$ too).
- Self-consistency pass (solve twice, check agreement) for problems already routed to 8-bit.
- Safety: no vulgar content, educational-only mode, age-appropriate calibration, misinformation handling, medical/science claim boundaries.

## 4. Pedagogy
- **Philosophy:** new tools aren't the answer — inspire first (Veritasium). AI should create curiosity, not replace it. E.g., don't open with "derivative = rate of change"; open with a speedometer in a moving car, then show that intuition powers modern AI.
- **TARL infrastructure:** curriculum graph (prerequisite DAG — algebra → quadratics → calculus → diff. eq. → physics → ML) + a personal "learning twin" tracking mastery/misconceptions/pace per student.
- **Methods:**
  - Feynman: student explains back, AI probes gaps ("a derivative is just dividing" → "what happens as the denominator shrinks?")
  - Socratic: AI asks first ("what do we know?") before revealing $x=4$
  - Subgoal learning — e.g. $\int x^2e^x\,dx$ by parts, twice:
    $u=x^2,\ dv=e^x dx \Rightarrow \int x^2e^xdx = x^2e^x - 2\int xe^xdx$
    $u=x,\ dv=e^xdx \Rightarrow \int xe^xdx = xe^x - e^x + C$
    combine: $\int x^2e^xdx = e^x(x^2-2x+2)+C$
  - Normal Q&A mode; peer-simulation mode (AI plays a classmate solo — real-peer version in Sec 7)
  - Personas: Teacher / Friend / Professor / Exam-mode(minimal hints) / [Clicky](https://heyclicky.com)
- Scientific reasoning (physics/chem/bio) uses the same subgoal method, not a separate one.
- **AI Laboratory:** offline physics sims, graphing, coding experiments. [Cartesian.app](https://cartesian.app) is a concrete existence proof — an offline interactive DSA book with code playback + embedded Python, running on hardware close to the ADTC spec. Also: [Opennote.com](https://opennote.com).
- Gamefied learning: Flashcards, Quizzes, whatever method the user wants, they can describe and get.
- How'd the blind use this (especially with the audio/braille feature)
- The product can be personalised (like Hey Siri--whatever name the learner wants to call it.)
- Look at clicky and the way it runs background tasks for you. Not only education, but education that empowers you too.
- The application should consistently learn about its primary user and [adapt](https://blog.google/innovation-and-ai/technology/developers-tools/developers-changing-lives-with-gemma-3n/#:~:text=The%20result%20is%20a%20custom%20AI%20assistant%20that%20understands%20the%20user%E2%80%99s%20unique%20speech%20patterns%20and%20enables%20voice%20control%20over%20device%20functions.) to their taste (or even language).
- This app will extend to UDO features...Not only science, but also a personal educational companion.
- Teachers can even share their resources on the app (their curriculum via RAG - which each student can tailor to themselves) and even monitor students' progress. See [RACHEL](https://worldpossible.org/products/rachel-5-500).
- [Guided discovery approach](https://youtu.be/6rkSPPyz_Bo)

## 5. Exam-Prep & Skills Training Layer (Africa)
- Target exams: WAEC/WASSCE, BECE, JAMB, NECO, KCSE, Matric, university entrance.
- Question generator: WASSCE-style items + worked solution + difficulty + examiner marking scheme.
- Past-question tutor: offline database of past exams + explanations + common mistakes.
- Adaptive exam mode: diagnoses weak spot (e.g. "chain rule") → concrete 7-day improvement plan.
- Skills/concept training mode: same generator and diagnostic engine, but organized by topic or concept instead of exam calendar, for students building foundational skills outside an active exam cycle.

## 6. Interface
- Adaptive UI ("I don't like the way I look, change me"): theme, avatar, personality, difficulty, explanation style, language, pace. Refs: [Claude Dispatch](https://www.oneusefulthing.org/p/claude-dispatch-and-the-power-of), YC [Dynamic Software Interfaces](https://www.ycombinator.com/rfs#:~:text=Dynamic%20Software%20Interfaces).
- Multilingual: English, French, Arabic, Swahili, Hausa, Yoruba, Igbo, Amharic, Zulu — plus culturally local examples (farming, markets, transport), not just translation.
- Offline KaTeX/MathJax for math rendering; interactive canvas for graphs/geometry (doubles as the AI Lab surface).
- Voice: [Moonshine](https://github.com/moonshine-ai/moonshine) (STT) → local model → offline TTS. [Wispr](https://wisprflow.ai) is the UX quality bar only — it's cloud-only, can't be reused as a component.
- [OpenClaw](https://openclaw.ai) — self-hosted, connects WhatsApp/Telegram to an agent, supports local models via Ollama. Proof that "talk to your tutor via chat app" works with zero cloud dependency.

## 7. Collaboration & Distribution
- **Shared-laptop classroom server:** one laptop runs the model, ~30 students connect via phone over local network.
- Peer-learning mode with real peers, network packets optimized for spotty local links; syncs models/lessons/progress when internet appears.
- Teacher dashboard: class progress, assignment generation, flag struggling students.
- Deployment: one click, single flash drive, phone-to-laptop, multi-OS (Linux/Windows/macOS).
- Mechanism: llama.cpp server + LAN discovery (phone just needs a browser); AppImage + portable build; offline signed-patch updates.
- Shared discussions, [catalogue of resources](https://cdn.sanity.io/images/4cwcet86/production/b10c325c051b0a91583bf2e764e1b04c8512f99a-1646x918.png?w=3840&q=70&auto=format), and competitive quizzes w/mates on devices on the same network (LAN, Internet or Bluetooth).

## 8. Evaluation & Business
- Metrics: learning (before/after, retention, problem-solving), AI (latency, TPS, RAM, battery, temp), education (engagement, completion rate).
- Test with real users.
- Monetization: free core, paid features + updates; likely bigger channel = institutional site licenses (schools/NGOs) via flash drive; offline license keys (no server needed to validate).

## 9. Competition Strategy
- Live demo: invite judges/audience to connect phones to the laptop and use the shared model.
- Report = running before/after benchmark log:

| Optimization | Before | After |
|---|---|---|
| FP16 → INT4 quantization | baseline RAM | reduced RAM |
| KV-cache quantization | baseline latency | reduced latency |
| Speculative decoding | baseline tokens/sec | increased tokens/sec |
| Model pruning | baseline size | reduced size |

- Run the ADTC local profiler on every commit, not just once at the end.
- Target Best African Use Case explicitly: multi-country exams + multilingual + shared-laptop mode.

## 10. Similar Products
- [Learning Equity](https://learningequality.org/)
- Khan Academy
- [Brilliant](brilliant.org)
- [Opennote.com](https://withmarble.com/)
- [Marble](https://withmarble.com/)
- [Khanmigo](https://www.khanmigo.ai/)
- [RACHEL](https://worldpossible.org/products/rachel-5-500)
- [HEY CLICKY](https://www.heyclicky.com/)
- [ANATOMY](https://anatomy-livid.vercel.app/)

## 11. The Story
- If the laptop is low, how about we build something like [RACHEL](https://worldpossible.org/cdn/shop/products/RACHEL4-Englishcrop_480x6272.png?v=1656701790) or [LENTERA](https://youtu.be/qO_A8_DId0g) w/a powerbank. 
- Run a benchmark like [this](https://ai.google.dev/gemma/docs/core/model_card_4#benchmark_results), proving why we concluded on the chosen model. Say we went through 1000 models, measured against x, y, and z, and selected this as ideal.
- Get feedback from the student -- they input their email once they use it, and then, we prompt them in their email, or as in-app notifications (remember, they may not have internet access.)
- Cambridge: got a C despite being Best in Nigeria.
- Cambridge: a classmate wouldn't employ me.
- HCI coursework as proof of TARL.
- UDO as proof of TARL.
- The live shared-laptop demo (Sec 7/9) as the moment judges remember.
- Life presentation show energy consumption since we loaded it till the end and as everyone in the room was using it
- Present like [this](https://youtu.be/YgF98vyn2fY)
- Do a survey on how many people (black vs. white) feel left behind...? We're slowly beginning slaves to those with higher knowledge. Which is the final call--when we outsource out thinking to them.

## 12. Team Study Shelf
- [Sebastian Raschka — local coding agents](https://magazine.sebastianraschka.com/p/using-local-coding-agents)
- [Ahmad Osman — Latent Space](https://www.latent.space/p/ahmad-osman-local-ai?utm_source=post-email-title&publication_id=1084089&post_id=204360411&utm_campaign=email-post-title&isFreemail=true&r=8pqpb&triedRedirect=true&utm_medium=email)
- [awesome-local-ai](https://github.com/msb-msb/awesome-local-ai)
- Kernel worklogs from Section 2
- [AI Inference Resources](https://github.com/aerlabsAI/ai-inference-resources)

## Extra features
- Misconception detector
- Mastery map. A visual graph showing mastered topics, weak topics, prerequisites missing, next best lesson
- Let teachers inject their own notes and test materials into the system
- Handwritten equation OCR as an input feature
- [Agents](https://x.com/0xCarnagee/status/2075983721841225885?s=20)--which can help the learners build things as they learn.

## A Four-Step Guide to AI-Assisted Codebase Work
- Step 1: Have the model study before it writes. Before generating any code, have Claude read the existing codebase (or spec, if starting fresh) and produce a plan — an explicit guide describing what needs to happen and why. Skipping this step means the model starts pattern-matching too early, before it understands the constraints it's working within.
- Step 2: Externalize the tribal knowledge.
Identify what only lives in developers' heads — ownership rules, lifetimes, invariants, "why this weird workaround exists" — and force the model to write it down explicitly, structured (a table or spreadsheet works well). This step matters because implementation agents in Step 3 can't ask a human clarifying questions mid-task; if the knowledge isn't written down first, it gets guessed at, and guesses compound into bugs.
- Step 3: Parallelize the implementation, but partition the work cleanly.
Split the codebase into independent units (files, modules, worktrees) and assign parallel agents to each. This works only because Step 2 already resolved the cross-cutting knowledge — parallel agents can't coordinate with each other in real time, so ambiguity between units has to be eliminated before they start, not discovered after.
- Step 4: Pair every writer with an adversarial reviewer.
Assign each implementer agent one or more separate reviewer agents, in isolated context windows, whose only job is to assume the output is wrong and try to find why. This is the step that catches what Step 3 introduces: parallel agents move fast but don't self-correct, so the review layer has to be structurally separate — not the same context, and not optimistic by default — or errors just get rubber-stamped.
## Next Step
Sections 0–3 = non-negotiable MVP. Thin slice of 4–7 (1–2 modes, 1 exam, bare interface, shared-laptop demo) tells the full story by 25 Aug. 7 (full) and 8 mostly post-competition.
