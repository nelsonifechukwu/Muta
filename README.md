# ADTC 2026 — Math & Scientific Reasoning (Education)

Offline, adaptive AI tutor for math and scientific reasoning, running on the 8 GB ADTC laptop. [Brilliant](http://brilliant.org)'s interactivity + Khan Academy's curriculum breadth + Encarta/Britannica's self-containedness — no server required. Groups below follow dependency order: each rests on the one above it.

```
Constraint → Model → Inference → Correctness/Safety → Pedagogy
   → Exam Prep → Interface → Collaboration/Distribution
   → Evaluation/Business → Competition Strategy → Story
(Team Study Shelf runs alongside all of the above.)
```

## 0. Constraint
- Hardware: i5 (10th–12th gen) / Ryzen 5 (3000–5000), 8 GB DDR4, integrated graphics only, 256 GB SSD, Ubuntu 22.04 — no GPU at deployment.
- $S_{\text{total}} = 0.50\,S_{\text{acc}} + 0.30\,S_{\text{perf}} + 0.20\,S_{\text{eff}} - P_{\text{thermal}}$
- $S_{\text{acc}}$ (50%) — tutoring quality → Section 3
- $S_{\text{perf}} = 100 \times \dfrac{\text{TPS}_{\text{act}}}{\text{TPS}_{\text{max}}}$, $\text{TPS}_{\text{max}} \approx 15$ (provisional)
- $S_{\text{eff}} = 100 \times \dfrac{7\text{GB} - \text{Peak RAM}}{7\text{GB}}$ — e.g. peak RAM 4GB→3GB raises $S_{\text{eff}}$ from 42.9 to 57.1
- $P_{\text{thermal}}$: −10 if >85°C or throttled
- **Implication:** small quantized model + retrieval + verified tool-calls beats a large model squeezed on.

## --- See https://github.com/addyosmani/agent-skills for Setup ---

## 1. Model Layer
- Candidates to bake off: Qwen3 (0.6B–4B), Phi-4-mini, DeepSeek-R1 distills, Gemma small, [Liquid AI](http://liquidai.com) LFMs — score on accuracy/GB, not raw accuracy.
- Fine-tune with **Unsloth**; corpus = WASSCE/JAMB/KCSE past questions + worked solutions + Socratic dialogue transcripts.
- Refs: [Hugging Face docs](https://huggingface.co/docs), [QWEN0.6B from scratch](https://github.com/emmanuelalo52/QWEN0.6B), [linas.substack GLM guide](https://linas.substack.com/p/glm-52-local-ai-guide).
- Udutech's ~5hrs GPU credit = training only; model gets quantized down before deployment (Section 2).
- Consider: train a draft model alongside the full model → speculative decoding (Sec 2) + standalone fast "hint mode."

## 2. Inference & Optimization
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
- KV-cache quantization (biggest hidden RAM cost), `mmap` model loading, cap thread count to avoid the −10 thermal penalty.
- See [bitnet.cpp](https://github.com/microsoft/BitNet)
- Must be multi-modal (and can even respond in whatever format to the student. see [audio](https://github.com/pwilkin/thinksound.cpp).
- Switch between f4 and f16 to get best mixed results without triggering throttling.

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
- How'd the blind use this (especially with audio/braille feature.)

## 5. Exam-Prep Layer (Africa)
- Target exams: WAEC/WASSCE, BECE, JAMB, NECO, KCSE, Matric, university entrance.
- Question generator: WASSCE-style items + worked solution + difficulty + examiner marking scheme.
- Past-question tutor: offline database of past exams + explanations + common mistakes.
- Adaptive exam mode: diagnoses weak spot (e.g. "chain rule") → concrete 7-day improvement plan.

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
- Brilliant
- Opennote.com

## 11. The Story
- Cambridge: got a C despite being Best in Nigeria.
- Cambridge: a classmate wouldn't employ me.
- HCI coursework as proof of TARL.
- UDO as proof of TARL.
- The live shared-laptop demo (Sec 7/9) as the moment judges remember.

## 12. Team Study Shelf
- [Sebastian Raschka — local coding agents](https://magazine.sebastianraschka.com/p/using-local-coding-agents)
- [Ahmad Osman — Latent Space](https://www.latent.space/p/ahmad-osman-local-ai?utm_source=post-email-title&publication_id=1084089&post_id=204360411&utm_campaign=email-post-title&isFreemail=true&r=8pqpb&triedRedirect=true&utm_medium=email)
- [awesome-local-ai](https://github.com/msb-msb/awesome-local-ai)
- Kernel worklogs from Section 2

## Next Step
Sections 0–3 = non-negotiable MVP. Thin slice of 4–7 (1–2 modes, 1 exam, bare interface, shared-laptop demo) tells the full story by 25 Aug. 7 (full) and 8 mostly post-competition.
