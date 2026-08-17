# Adversarial review — ADTC Gate-1 package `muta-iq/` (2026-08-17 15:30)

**Verdict: READY-with-fixes.** The GGUF itself passes every check (schema, quant purity, template on the real b10175 engine, sampling keys, EOS, llama-cpp-python). Three fixes are *blocking* (F1–F3), the rest are report hygiene.

## Evidence gathered (all commands under `with_lock.py --tag review-pkg`)

| check | result |
|---|---|
| `report.validate_submission_block(metadata minus _*)` / `report.validate(submission.json)` | both `None` (pass); 2 test_prompts; model block identical in both files; no placeholders |
| `extract_metadata` + `fraud_check('1.7B', 1,720,574,976)` | `params_match True` (±15 %) |
| gguf-py tensor scan | 310 tensors: 197 Q4_0 matrices, 113 F32 vectors, **no non-Q4_0 matrix, no `output.weight`**, `token_embd` Q4_0 [2048×151936]; 194 Q4_0 tensors byte-identical to bartowski source (only 3 Q4_1 `ffn_down` requantised, Q6_K head dropped) |
| metadata keys | `general.name='Muta Tutor (Qwen3-1.7B)'`, `general.file_type=2`, `general.sampling.temp/top_p/min_p/penalty_repeat = 0.4/0.9/0.05/1.05` (f32), `eos=151645 <\|im_end\|>`, `bos=151643`, `add_bos=false`, `muta.default_system_prompt` present |
| jinja2 3.1.6 renders (no-sys / client-sys / 3-turn / agp=false) | persona injected once; client system merged after persona + `\n\n`; agp=true ends `<\|im_start\|>assistant\n<think>\n\n</think>\n\n`; agp=false emits no assistant header |
| `llama-completion --jinja -cnv -st` (b10360 build-cpu), 2 prompts, `--temp 0` | direct answers (937.5 naira / 5/6), no reasoning trace; sampler log shows `repeat_penalty 1.050, top_p 0.900, min_p 0.050` read from the file |
| **stock `llama-server` at tag b10175** (scratchpad build, zero flags) + b10360 Homebrew | `chat template, thinking = 0`, `reasoning_mode: NONE`, `supports_tools:false`; `/props` temp 0.4 / top_p 0.9 / min_p 0.05 / repeat 1.05, `n_ctx 32768`, 4 slots; `/apply-template` correct for no-system and client-system; both test prompts `finish_reason: stop`, correct (tp_002 139 tok, tp_001 289 tok), `reasoning_content: None` |
| llama-cpp-python 0.3.34 | loads, `chat_format='chat_template.default'`, `create_chat_completion` → correct 5/6 answer, `finish_reason: stop`; persona = **130 tokens** (prompt_tokens 170 for tp_002); raw completion path sane |
| download_model.sh (read) | `set -euo pipefail`, sha256 constant == local file, idempotent (sha-verified skip), curl→wget fallback, `.partial`+`mv`, no credentials, output path == `_runtime.model_path` |
| HF URL (HEAD) | **404 `EntryNotFound`** — repo exists (public, only `.gitattributes`); 3 prior LFS multipart uploads died with S3 `RequestTimeout`; an `hf upload-large-folder … --num-workers 2` has been running since 15:08 (still pre-uploading at 15:26) |
| git | repo root is `/Users/timii/Developer/Muta`; under `muta-iq/` only 12 files tracked (metadata, download script, submission.json, .gitignore, `dashboard/*`); **REPORT.md untracked, `opt/` untracked** (dry-run `git add opt` = 3.5 MB / 218 files, nothing large); `.gitignore` covers `model/`, `*.gguf`, `*.partial` |

## Findings (ranked)

**F1 (blocking) — model URL 404s.** `download_model.sh` cannot fetch → profiler exit 2 → no score. Let the running `upload-large-folder` finish, then verify:
`curl -sIL "$URL" | grep -iE '^HTTP|x-linked-size'` → expect 200 + `x-linked-size: 974198528`; then `git clone <public repo> /tmp/x && cd /tmp/x && bash download_model.sh && shasum -a 256 model/*.gguf` (ideally in `docker run --rm -v $PWD:/s debian:bookworm-slim bash -c 'apt-get -qq update && apt-get -qq install -y curl >/dev/null && cd /s && bash download_model.sh'`). If HF keeps timing out: `pip install hf_xet` / retry, or attach the file as a GitHub Release asset (974 MB < 2 GiB) and add `MODEL_URL_FALLBACK` to the script (try HF, on failure try the release URL).

**F2 (blocking) — REPORT.md numbers/transcripts are from the *previous* build of the GGUF, not the shipped one.** The file was rebuilt at 14:42 (`finalize3.log`, template 4614→1193 chars, persona 220→130 tokens). `GSM8K-40 = 0.625 (25/40), avg 177` and all four sample transcripts come from `opt/eval/results/muta-tutor-final.json` (14:08, old persona). On the shipped file only `muta-tutor-final2.json` exists (n=20: 0.70, avg 166) and its greedy transcripts differ: tp_001 now "Let's solve this step by step… \boxed{937.5}" (250 tok), the falling-ball answer opens with the wrong "the student correctly identifies that the weight… affects how fast it falls" and hits the 400-token cap, the photosynthesis equation is wrong. Fix: `python opt/scripts/eval_math.py --model model/muta-tutor-qwen3-1.7b-q4_0.gguf --n 40 --tag muta-tutor-ship` (or capture from `llama-server` at file defaults, as judges will see it), then replace the numbers and transcripts in REPORT.md; if the old persona was measurably better, re-bake it trimmed rather than shipping unmeasured wording.

**F3 (blocking) — repo layout / provenance.** Template requires `metadata.json`, `download_model.sh`, `REPORT.md`, `.gitignore`, `LICENSE` at the *root of a public repo*; today they live in a subdirectory of a private mono-repo, REPORT.md is untracked, and `submission.json.git_commit_sha=9b1feffe25e5` is a parent-repo commit that does not contain the current metadata/REPORT. Fix: publish `muta-iq/` as its own public repo (add `LICENSE`, e.g. Apache-2.0), commit everything incl. `opt/scripts`, `opt/results/*.json|tsv`, `opt/eval/results/*.json`, then re-run `adtc-profiler run --mode participant` from that checkout so the sha pins the shipped files (drop `*.log` from `.gitignore` or whitelist `opt/results/*.log` so evidence logs are kept). Set `team_id` = the Devpost project slug (comparator hard-fails on mismatch); `submitter.email` must be the filing Devpost account (note only — cannot verify here).

**F4 — REPORT internal contradictions / untraceable numbers.**
- Bake-off row for the chosen model says arc_easy `0.72–0.74`; the shipped (tied) file measures **0.70** (`submission.json`, Benchmarks table). Change to `0.70 (0.74 before the head drop)`.
- "51.2 tok/s earlier run" is only in `RESULTS.md` (its JSON was overwritten) — save/cite it; 52.2 traces to `submission_homebrew_qwen3.json`.
- "9.4 tok/s for a **1.23 GB** Q4_0 Qwen3-1.7B" — r7 records **1.17 GB peak RSS**; write "≈1.2 GB".
- MiniCPM5 GSM8K shown as "—" but measured 0.000/0.025 (`bakeoff.tsv`); say "0.00–0.03 (template failure)".
- "minja" ×3: b10175 uses llama.cpp's own `common/jinja` engine (minja removed 2026-01-16, r5:45). Also "checked on a b10175 build" was the old persona; it is now re-verified on the shipped file (this review) — update the sentence.
- Missing Devpost items: screenshots/short clip in-repo, Reproducibility section (sha256, commit, profiler command), explicit licence of the derived GGUF (Apache-2.0) and repo LICENSE. Headings Problem/Design Decisions/Constraints/Benchmarks + self-reported disclaimer + African use-case paragraph are present and correct; bartowski and Qwen Apache-2.0 credited.

**F5 — submission.json vs audit (expected comparator outcome).** 43.41 tok/s (measured while an upload ran; clean runs 51–52) vs ~9–13 on the no-AVX x86 box → |Δ|>50 % → comparator "fail → manual review" for TPS and TTFT no matter what; RSS 1133 MB vs ≈1.12–1.2 GB is inside ±15 %. Mitigate: run `opt/audit-bench/` on an x86 runner and quote the measured audit-build tg/RSS in REPORT; re-run the profiler on an idle machine before the final commit.

**F6 — template risk on b10175 (reasoned + tested).** Uses only `namespace`, `for…if`, `set`, `+` concat, escaped `\n`, `{%- -%}` — all in the b10175 supported set; parse + analyzer probes pass on the real tag build (`thinking = 0`, no `raise_exception`, no `messages[0]` indexing). Residual: `message['content']` must be a string (llama-server flattens content-part arrays; llama-cpp-python does not — irrelevant to judging); the persona asks for plain text yet the model emits LaTeX `$$…$$` — cosmetic in llama-server's UI (renders KaTeX), verbose elsewhere.

**F7 — minor.** `metadata.model.packaging="binary_bundle"` is the only enum that fits a bare GGUF; fine. `quantize.imatrix.*` keys inherited from bartowski although the 3 Q4_1→Q4_0 requants used no imatrix — harmless. `curl -C -` on a fully-downloaded stale `.partial` can 416; negligible.
