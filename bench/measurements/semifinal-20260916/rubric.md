# Grading rubric — ADTC Round-1 judge prompts (semi-final re-test)

Score each response 0–10. Prompt score → accuracy percentage = mean(score) × 10.

General deductions (apply to every prompt):
- Wrong final answer or a factual/scientific error in the explanation: −3 to −6 depending on how central it is.
- A required part of the requested format missing (e.g. no check question, no Yorùbá section, no second method): −2 per missing part.
- Visible reasoning breakdown (repetition loops, "Wait…" back-and-forth that never resolves, self-contradiction): −2 to −4.
- Truncated before a final answer is reached (finish_reason = length with no answer): cap at 3.
- Confidently stated wrong attribution or invented facts: −2.

## auto_1 / judge_4 — Two Sigma model
Reference: "Two Sigma" = Bloom (1984): one-to-one tutored students perform ~2 standard deviations above conventional-class students. Model: dK/dt = c·p (rate proportional to personalization p), so K(t) = K0 + c·p·t; or with a ceiling, dK/dt = c·p·(Kmax − K) → K(t) = Kmax − (Kmax − K0)e^{−c p t}. As p → 0: rate → 0, learning stalls at baseline (no personalization ≈ conventional classroom). As p → ∞: linear model gives unbounded rate (unrealistic); with a ceiling the rate saturates and mastery approaches Kmax quickly — matching the idea that the 2σ gain is an upper limit, not infinite. Good answers note diminishing returns / a ceiling. Full marks need: a correct proportional model, both limits analysed correctly, no invented constants (e.g. "√2") or misattribution (e.g. Kahneman).

## auto_2 — dS/dt = k(T − S)
Reference: separable / linear ODE. S(t) = T − (T − S(0))e^{−kt}. As t → ∞, S → T: the student's mastery asymptotically approaches, but never exceeds, the tutor's expertise T. Link to Two Sigma: the ceiling is set by the tutor's level (and one-on-one attention); scaling education means every student needs a high-T tutor, which is the resource limit Bloom described. Full marks: correct closed form with initial condition applied, correct asymptote, sensible interpretation.

## auto_3 — 4 TOPS, 200 ms, parameter budget
Reference (any coherent dimensional argument accepted): decoding one token costs ≈ 2N operations for an N-parameter model. Budget in 200 ms at 4 TOPS = 4×10^12 × 0.2 = 8×10^11 ops. If one token must arrive within 200 ms: N ≤ 8×10^11 / 2 = 4×10^11 (400 B) — clearly memory-bound in practice. If "2 tokens per character" is used to mean the response must emit ~2 tokens in that window: N ≤ 2×10^11 (200 B). Full marks: sets up ops-per-token, uses the 0.2 s window, states assumptions, gives a number with units, notes practical limits (memory bandwidth). Deduct heavily for loops or no number.

## auto_4 — chalk (team test prompt tp_001)
Reference: C. ₦3,000; 6 × 500 = 3,000. Full marks need the correct option letter AND one calculation, and nothing more that contradicts it.

## auto_5 — photosynthesis MCQ (team test prompt tp_002)
Reference: B. Photosynthesis; one sentence: plants use sunlight (captured by chlorophyll) to convert carbon dioxide and water into glucose and oxygen.

## judge_1 — average speed
Reference: average speed = total distance / total time. 60/40 = 1.5 h; 60/80 = 0.75 h; total 2.25 h; 120/2.25 = 53.33 km/h. The arithmetic mean of speeds is only valid for equal TIMES; here the distances are equal so more time is spent at the slower speed (harmonic-mean situation). Needs: clear diagnosis, correct step-by-step calculation, an intuitive example a 15-year-old could follow, and a transferable "how to spot it" rule (ask: equal times or equal distances? always go back to total distance / total time). Deduct for calling 40 km/h "a time", or contradictions.

## judge_2 — DNA / genes / chromosomes / proteins
Reference: misconception = treating them as synonyms. DNA = the molecule carrying instructions; gene = a stretch of DNA that codes for one protein; chromosome = one long DNA molecule packaged with proteins (humans: 46); protein = the product built from a gene's instructions (does the actual work). Analogy (e.g. library/book/recipe/dish, or cookbook/chapter/recipe/meal). Needs all four parts: analogy, accurate explanation, one check question, and a follow-up for a wrong answer. Deduct for saying chromosomes are cell walls/cells, that they are "different names for the same thing", or an analogy whose mapping changes mid-answer.

## judge_3 — photosynthesis in English and Yorùbá
Reference: plants use sunlight energy, absorbed by chlorophyll in leaves, to combine carbon dioxide (from air) and water (from soil) into glucose (food) and release oxygen. West-African example (cassava/maize/plantain/yam leaves in the sun). Must include all six items correctly, an actual Yorùbá explanation (real, coherent Yorùbá — "Fọ́tòsíntẹ́sì", "oòrùn"/"ìmọ́lẹ̀ oòrùn" = sunlight, "omi" = water, "afẹ́fẹ́ carbon dioxide", "gúlúkósì/oúnjẹ", "ọ́ksíjìn", "ewé"/"chlorophyll"), and two quiz questions in both languages that test understanding. If the Yorùbá section is absent, garbled, or not Yorùbá, cap at 4. Deduct for scientific errors (e.g. plants "take in" oxygen and "release" glucose to the air).

## judge_5 — Onitsha rice trader
Reference: cost = 40 × 1,850 = ₦74,000. First sale: 25 × 2,300 = ₦57,500. Reduced price = 2,300 × 0.85 = ₦1,955; remaining 15 kg → 15 × 1,955 = ₦29,325. (a) Total revenue = 57,500 + 29,325 = ₦86,825. (b) Profit = 86,825 − 74,000 = ₦12,825. (c) % profit on cost = 12,825 / 74,000 × 100 = 17.3%. Check by a different method: e.g. revenue/cost = 86,825/74,000 = 1.1733 → 17.3%, or average selling price per kg 2,170.625 vs cost 1,850 → 320.625/1,850 = 17.3%. Full marks need all three parts correct to one decimal place, working shown, and a genuinely different second method. A wrong first arithmetic step (e.g. 25 × 2,300 = 58,250) caps at 3.
