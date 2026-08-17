# DECISION BRIEF — team-muta, ADTC 2026 Gate 1 (written 2026-08-17 15:00 WAT; deadline 2026-08-25 06:45 UTC)

**State of play:** `muta-iq/` was switched today (14:05–14:11) from BitCPM4-8B TQ2_0 (2208 MB) to **Qwen3-1.7B pure Q4_0, tied Q4_0 head, persona baked (974 MB)**; `submission.json` = 51.2 tok/s / 1133 MB (M1), arc_easy(50) 0.70, GSM8K-40 0.625. Sources: R1–R7, `opt/docs/REPORT.md`, `opt/results/bakeoff.tsv`, one live b10175 probe.

## 1. Audit-box reality (verified)

- **Scored run** = stock `llama-bench -m X -p 512 -n 128 -ngl 0` in the profiler image: llama.cpp **b10175** compiled with exactly `-msse4.2 -mbmi2` (AVX/AVX2/FMA/F16C OFF), one static CPU backend, `ggml_cpu_has_avx2()` a compile-time 0 → **no runtime dispatch** even on an AVX-512 host (R4 §2). Threads = physical cores (2 on a 2C×2HT VM).
- **Kernels:** only **Q4_0** (and Q1_0) have hand-written SSSE3 `vec_dot` (≈0.25–0.3 cycles/weight); Q8_0 = scalar tail; Q4_K/Q5_K/Q6_K/TQ1_0/TQ2_0/IQ* = generic C under GCC 12.2 (0.7–1.5 c/w) (R4 §3/§7). **No repack**, **no llamafile sgemm** (pp ≈ tg per token → judge TTFT ≈ prompt_tokens/tg).
- **RSS** = Linux `MAP_POPULATE` whole file + KV/compute + profiler ≈ file + 150 MB.
- **Real measurements on that build (R7):** Qwen3-1.7B Q4_0 9.4 tok/s @1.17 GB, Llama-3.2-1B Q4_0 12.8, Qwen2.5-1.5B Q4_0 10.8 (i7-1165G7, `--cpus=4`); Qwen3-0.6B Q4_0 20.3 @527 MB (EPYC 4c); Q4_K_M 1.5B 3.5, 3B 2.75 ⇒ Q4_0 ≈ 10 GB/s streamed, generic C ≈ 3–5 GB/s. M1 generic-C proxy: BitCPM-8B TQ2_0 3.7–3.9 tok/s (clang; GCC 1.3–3× worse → 1–3 on x86).
- **Judge chat** = same image's `llama-server`, stock flags: GGUF Jinja template on, no system prompt, `n_ctx` = trained ctx, `n_predict −1`, sampling from `general.sampling.*` (R2/R5). Automated MC channel = llama-cpp-python raw-text loglikelihood, no template.
- **Probe today (b10175 build, shipped GGUF, zero flags):** loads; persona injected; `supports_system_role:true`; assistant turn ends `<think>\n\n</think>\n\n`; `/props` temp 0.4 / top_p 0.9 / min_p 0.05 / repeat 1.05, `n_ctx 32768`, 4 unified slots (112 KiB/token → 3.5 GiB KV *reserved*, touched lazily, no OOM); tp_002 answered correctly, `finish_reason: stop`, 176 tokens; **prompt_tokens 254 for a 17-token question → persona ≈ 220 tokens** (too long at ~10 tok/s prefill).

## 2. Scoring model

Assumptions: audit tg from §1 anchors (Q4_0: 10 GB/s ÷ streamed GB; TQ2_0: 1.6 tok/s per 2.2 GB; ±50 %); RSS = file+150 MB; S_eff = (7000−RSS)/70; **A** = min(TPS/15,1)·100; **B** = 100·TPS/TPS_max, **TPS_max = 40** (a 135–270 M Q4_0 entrant; at 60, B S_perf ×⅔); S_acc proxy = 0.5·(100·arc_easy) + 0.5·(25 + 70·GSM8K-chat), bakeoff numbers where measured (*italics = estimates from published benchmarks*). Total = 0.5·S_acc + 0.3·S_perf + 0.2·S_eff.

| candidate (audit format) | RSS MB | audit tg (range) | S_perf A / B | S_eff | S_acc | Total A / B | **Exp.** |
|---|---|---|---|---|---|---|---|
| **Qwen3-1.7B pure Q4_0 tied (shipped)** | 1124 | 11 (8–14) | 73 / 28 | 84 | 70 (arc .72 gsm .62) | 73.9 / 60.1 | **67.0** |
| Qwen3-0.6B pure Q4_0 tied | 490 | 22 (17–28) | 100 / 55 | 93 | *54* (arc .55 gsm .40) | 75.6 / 62.1 | 68.8 |
| LFM2.5-1.2B-Instruct Q4_0 | 846 | 14 (11–17) | 93 / 35 | 88 | 61 (arc .56 gsm .575) | 75.9 / 58.4 | 67.1 |
| Qwen3.5-2B Q4_0 (GDN generic) | 1360 | 7 (5–9) | 47 / 18 | 81 | *75* | 67.6 / 58.9 | 63.2 |
| Qwen3-4B-Instruct-2507 pure Q4_0 | 2450 | 4.3 (3–6) | 29 / 11 | 65 | *85* | 64.0 / 58.6 | 61.3 |
| Qwen3.5-4B Q4_0 | 2730 | 3.5 (2.5–5) | 23 / 9 | 61 | *87* | 62.6 / 58.2 | 60.4 |
| BitCPM-8B TQ2_0 pruned (yesterday) | 2359 | 1.6 (1–3) | 11 / 4 | 66 | 82 (arc .84 gsm .775) | 57.3 / 55.3 | 56.3 |
| MiniCPM5-1B pure Q4_0 | 763 | 16 (12–20) | 100 / 40 | 89 | 37 (broken template) | 66.5 / 48.5 | 57.5 |
| BitCPM-1B TQ2_0 pruned | 618 | 8 (5–13) | 53 / 20 | 91 | 51 | 59.9 / 49.9 | 54.9 |

Reading: (i) the 8B ternary is near the bottom under **both** formulas — the pivot was right (+11 expected). (ii) Under **A** the sub-1.2B files nominally lead by ~2 points, entirely from S_perf; the S_acc proxy's ±10 error exceeds that gap, and live judges will separate 1.7B from 0.6B tutoring more sharply than a linear proxy does. (iii) Under **B** everything compresses to 55–62 and S_acc decides; 4B models tie the 1.7B only if TPS_max ≥ 40. (iv) Qwen3-1.7B is the only top-group candidate under both formulas with a measured, template-verified tutoring channel.

## 3. Recommendation

**Primary — ship what is now in `muta-iq/`: Qwen3-1.7B, `llama-quantize --pure Q4_0`, embedding Q4_0, `output.weight` dropped (tied), 974 MB.** Why this quant: 100 % of token time on the SSSE3 kernel (bartowski's Q4_0 carries a 255 MB Q6_K head + imatrix Q4_1 layers = generic/scalar C on ~¼ of the bytes); Q8_0 doubles bytes for a scalar tail; Q4_K_M ≈ 3× slower per byte; TQ*/IQ*/Q4_1/Q5_0 must never ship (R4 §8). Cost: GSM8K-40 0.60–0.65 vs 0.65 source, arc 0.72–0.74 vs 0.72 — noise.

**Hedge (build, hold, ship only on evidence):** Qwen3-0.6B via the identical pipeline (`bake_system_prompt.py` + `drop_tensor.py`, ~340 MB, ~30 min) — formula-A insurance worth +7–9 perf/eff points, shipped only if a bake-off shows GSM8K-40 ≥ 0.50 and clean tp_001/tp_002 transcripts; else LFM2.5-1.2B-Instruct Q4_0 (benched 0.575/0.56; non-OSI licence, declare it). **Do not** up-hedge to a 4B: even under B it nets ≈0 and gives judges 4 tok/s and 30-s TTFTs. No thinking mode, no MiniCPM5 (broken template), no Qwen2.5-Math (arc 0.24, 4k ctx).

## 4. Accuracy plan

**Today (CPU only, b10175 build in scratchpad):**
1. **Trim the persona to ≤ 90 tokens** (keep the `You are Muta` marker and the exact `<think>\n\n</think>` string): 220 tokens ≈ 15–25 s extra first-token latency per fresh judge slot; re-bake, re-verify `/apply-template`, `/props`, `thinking = 0`.
2. **A/B persona wording × sampling** (temp 0.3/0.4/0.5) on tp_001, tp_002 + 12 guessed hidden prompts (percent/ratio word problems, simultaneous equations, geometry, unit conversion, titration, Newton's laws, misconception fixes, short proof) × 5 seeds, plus 3-turn follow-ups; score correctness, `finish_reason=stop`, length ≤ 300 tokens. R5 saw a "Step 1/Step 2" skeleton loop from "solve step by step" wording — hunt that.
3. **Fix `test_prompts`** to the two prompts that pass ≥ 9/10 seeds and show African context + pedagogy: keep tp_001 (naira crates → 937.5) and tp_002 (`1/2+1/3` misconception, verified today); `submission.json` still has the old falling-ball tp_002 → regenerate.
4. **Protect Channel A:** rerun profiler `accuracy.run_benchmark` on `arc_easy`, `arc_challenge`, `sciq`, `openbookqa` (limit 200) on the final baked file — the template is invisible there, so numbers must match the pre-bake file.
5. **African evidence without a language claim:** run R6's JAMB MC probe (100 items each maths/physics/chemistry, `wisdom209/jamb_questions`) and AfriMMLU-eng elementary-math (100); report the numbers; keep `language_scope: ["en"]`, state in REPORT.md/Devpost that `african_alpha_claim: true` is the **use-case** bonus (R1 §6). Optional: AfriMGSM-swa 50; mention Swahili only if ≥ 30 %.

**Later (Gate 2, ≤ 2 GPU-h):** Unsloth LoRA on Qwen3-1.7B (r 16, lr 2e-4, 1 epoch, ≤ 5 k samples: MathDial teacher turns, GSM8K-socratic rewritten, ScienceQA/SciQ explanations, ~1 k JAMB/WAEC MC with worked solutions, 25–50 % general chat, **no system prompt in data**) → merge → `convert_hf_to_gguf.py` (llama.cpp ≤ b10175) → `llama-quantize --pure q4_0 --token-embedding-type q4_0` → drop output → bake → regression gate (no metric −2 pts; rubric up) (R6 §5.1).

## 5. Package checklist — what `muta-iq/` still lacks (R1 §8)

- ❌ **`download_model.sh` URL 404s** (`huggingface.co/timiiowolabi/muta-tutor-qwen3-1.7b-q4_0` not uploaded) — no fetch, no score. Upload public/non-gated; test `bash download_model.sh` from a fresh clone in `debian:bookworm-slim`.
- ❌ `metadata.json`/`download_model.sh`/`REPORT.md`/`.gitignore`/`LICENSE` must be at the root of the **public** repo given to Devpost; today they sit in `muta-iq/` inside `nelsonifechukwu/Muta`. Publish `muta-iq/` as its own repo (fork the template).
- ❌ Devpost project → `team_id` = project slug; regenerate `submission.json` (comparator hard-fails on mismatch); Sperf/Seff plain numbers; ≤ 2-min video; in-repo screenshots; Representative; agreement.
- ⚠️ `submission.json`: M1 51 tok/s vs ~11 audit = >50 % → comparator **fail**. Run `opt/audit-bench/` (free x86 runner), then a full `--mode participant` profiler-image run on x86; commit *that*; never `accuracy: []`.
- ⚠️ REPORT.md: "minja" → llama.cpp's own Jinja engine; add x86 audit-build row, bonus-claim paragraph, sha256/commit, video link.
- ⚠️ `model.quantization` → `GGUF Q4_0`; track only the `opt/` scripts REPORT cites.

## 6. Risks (ranked)

1. HF upload / repo root / team_id not done by 08-25 06:45 UTC → zero.
2. S_perf formula (cap vs relative): primary robust; document the 15 assumption.
3. Audit VM = 2 physical cores → tg 6–8 → S_perf A 40–53 (−6…−10 total); only a smaller model (hedge) helps.
4. Persona loop/verbosity at default sampling, or a template edit that flips thinking on (`</think>` trailing newline is load-bearing, R5) → validate on b10175 after every re-bake; a parse failure = sandbox crash = DQ.
5. Comparator fail on M1 numbers (above).
6. `african_alpha_claim:true` read as a language claim; `submitter.email` must match the filing Devpost account.
7. Channel A: arc_easy 0.70 vs the 8B's 0.84 — accepted (+11 expected total).
