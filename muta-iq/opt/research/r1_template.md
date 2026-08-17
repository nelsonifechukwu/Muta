# R1 — ADTC 2026 submission-package rules (template + Devpost + profiler + ADTF FAQ)

Researched 2026-08-17 (UTC 09:00–09:45). Team: team-muta, domain `math_scientific_reasoning`,
submission dir `muta-iq/`. Everything below is either **quoted verbatim** from a primary source
(marked with the URL) or explicitly labelled *inference*.

Primary sources fetched in full (raw, not summarised):

| Source | URL | Freshness |
|---|---|---|
| Template repo tree (GitHub API) | `https://api.github.com/repos/Africa-Deep-Tech-Foundation/adtc-2026-submission-template/git/trees/main?recursive=1` | HEAD = `63ddc5422404f8ee112fc74d28e29764acd40a50`, single commit "Initial commit" 2026-06-15T01:07:21Z; `pushed_at` 2026-06-15 (never changed since) |
| Template README.md / REPORT.md / metadata.json / download_model.sh / .gitignore / LICENSE / model/.gitkeep | `https://raw.githubusercontent.com/Africa-Deep-Tech-Foundation/adtc-2026-submission-template/main/<file>` | as above |
| Template repo issues (#1 email bounces, #4 team_id) | `https://github.com/Africa-Deep-Tech-Foundation/adtc-2026-submission-template/issues` | open, unanswered |
| Profiler repo (schema, cli, gguf fraud check, comparator, Dockerfile, README, demo submission) | `https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler` | last push 2026-08-15 ("lower minimum Python to >=3.10"); code last changed 2026-07-29/30 |
| Devpost overview / rules / dates / resources / updates / forum | `https://adtc-2026.devpost.com/` (+ `/rules`, `/details/dates`, `/resources`, `/updates`, `/forum_topics/*`) | fetched 2026-08-17 |
| Devpost update "Important Updates to Submission Form: Separate fields for profiler scores" | `https://adtc-2026.devpost.com/updates/45602-important-updates-to-submission-form-separate-fields-for-profiler-scores` | posted ~2026-08-01 |
| ADTF microsite incl. FAQ | `https://africadeeptech.org/challenge-2026/` (`#faq`) | fetched 2026-08-17 |
| ADTF leaderboard | `https://africadeeptech.org/challenge-2026/leaderboard` | "No published runs found" |
| Challenge Participation Agreement (Google Doc linked from Devpost rules) | `https://docs.google.com/document/d/1YIk8lrnBXl5WHed9oe5qzbslyQQsqL6rdNBxI8WJeSw` | exported as txt |
| Profiler tutorial playlist (7 videos, 2026-08-01) | `https://www.youtube.com/playlist?list=PLSj-s4_873dY` | titles only ("ADTC LLM Challenge Profiler Tutorial Video Part 1–7"); not transcribed |
| Upstream model card | `https://huggingface.co/api/models/openbmb/BitCPM-CANN-8B-gguf` | `license: apache-2.0`, `gated: false` |

Not accessible: the Devpost submission *form* itself (login-only at
`https://devpost.com/submit-to/30091-africa-deep-tech-challenge-2026/manage/submissions`), the
project gallery ("The hackathon managers haven't published this gallery yet"), Discord.

---

## 1. Deadlines (verbatim)

Devpost overview (`https://adtc-2026.devpost.com/`): **"Deadline: Aug 24, 2026 @ 11:45pm PDT"**.
Devpost schedule (`/details/dates`): "Submissions — June 16 at 11:45pm PDT — **August 24 at 11:45pm PDT**";
"Winners Announced — October 17 at 2:00pm PDT".

Devpost rules "Dates" table (`/rules`):

> Tue June 16, 2026 | Launch | Contest opens. Problem domains, hardware profile, profiler tool, and validation-set samples published.
> Tue August 25, 2026 | Gate 1 Deadline | Proposals + prototypes submitted. Two-step judging: proposal screen, then prototype review of the top ~10%.
> Tue Sept 8, 2026 | Semifinalists Announced | Up to 20 teams notified. Gate 2 narrowing audit begins.
> Tue Sept 22, 2026 | Semifinalist Submission | Semifinalists submission deadline
> Tue Sept 29, 2026 | Finalists Announced | Up to 10 teams advance to Live Defense. Pitch-prep window opens.
> Sat, Oct 17, 2026 | Live Defense & Awards | Remote live pitches, technical Q&A, and winners announced the same day.

ADTF site: "Gate 1 - Submission Package — Due August 25, 2026"; "Gate 2 - Activities & Audit — September 8 - September 29, 2026"; "Gate 3 - The Final Package — Due October 17, 2026".

**Binding timestamp is the Devpost form close: 2026-08-24 23:45 PDT = 2026-08-25 06:45 UTC = 2026-08-25 07:45 WAT (Lagos).** Treat "Aug 25" on the ADTF site as the same instant, not a later day. (The 2026-06-18 Substack launch post still says "Gate 1 Submission Deadline: July 24, 2026" — superseded.)

Note the two-step Gate-1 judging: "proposal screen, then prototype review of the top ~10%" — the written package (REPORT.md + Devpost text + video) is what gets us through the screen before anyone runs the model.

---

## 2. The template repository — verbatim

### 2.1 Tree

```
.gitignore            (198 B)
LICENSE               (GPL-3.0, 32402 B)
README.md             (7991 B)
REPORT.md             (1619 B)
download_model.sh     (1451 B, mode 100755)
metadata.json         (1088 B)
model/.gitkeep        (0 B)
```

### 2.2 README.md — full text (verbatim, emoji headings kept)

> # ADTC 2026 — Submission Template
>
> This is the official template repository for the **Africa Deep Tech Challenge 2026** Laptop LLM track.
>
> Fork this repository, fill in the required files, and submit your repository URL via [adtc-2026.devpost.com](https://adtc-2026.devpost.com).
>
> ## ✅ Submission Checklist
>
> Before submitting, confirm every item:
>
> - [ ] Your repository is **public** on GitHub
> - [ ] `metadata.json` is fully filled in — no placeholder values remain
> - [ ] `metadata.json` contains exactly **2 test prompts** in the `test_prompts` array, written for your chosen domain
> - [ ] `download_model.sh` successfully downloads your model to `model/`
> - [ ] The downloaded file is a valid **GGUF format** (`.gguf`) weight file
> - [ ] `model/*.gguf` is listed in `.gitignore` — do **not** commit large weight files
> - [ ] `REPORT.md` is filled in with your technical writeup
> - [ ] Running `bash download_model.sh` completes without errors
> - [ ] Your model runs entirely **offline** — zero external network calls during inference
>
> ## 📁 Required File Structure
>
> ```
> your-submission/
> ├── metadata.json          ← Required. Team, model, and test prompt metadata.
> ├── download_model.sh      ← Required. Downloads your .gguf model weight file.
> ├── REPORT.md              ← Required. Technical writeup (problem, design, benchmarks).
> ├── model/
> │   └── your-model.gguf   ← Downloaded by the script above. Do NOT commit.
> └── .gitignore             ← Must exclude *.gguf and model/ from version control.
> ```
>
> ## 📝 metadata.json
>
> Fill in every field. No field should remain at its placeholder value.
>
> ```json
> {
>   "team_id": "your-team-id",
>   "domain": "coding_assistants",
>   "language_scope": ["en"],
>   "african_alpha_claim": false,
>   "budget_laptop_claim": true,
>   "submitter": {
>     "name": "your-name",
>     "email": "your-email@domain.com",
>     "github_handle": "your-github"
>   },
>   "cross_disciplinary_pairing": {
>     "discipline": "education",
>     "load_bearing": true,
>     "description": "Brief description of how your model serves a real-world domain."
>   },
>   "test_prompts": [
>     { "prompt_id": "tp_001", "prompt": "Your first test prompt, written for your chosen domain." },
>     { "prompt_id": "tp_002", "prompt": "Your second test prompt, written for your chosen domain." }
>   ],
>   "model": {
>     "name": "YourModel-Q4_K_M",
>     "runtime": "llama.cpp",
>     "quantization": "GGUF Q4_K_M",
>     "parameters_estimate": "1.1B",
>     "packaging": "binary_bundle"
>   },
>   "_runtime": {
>     "model_path": "model/your-model.gguf"
>   }
> }
> ```
>
> ### Field Reference
>
> | Field | Required | Description |
> |---|---|---|
> | `team_id` | ✅ | Your unique team ID as registered on the ADTF portal |
> | `domain` | ✅ | Your challenge track. One of: `math_scientific_reasoning`, `healthcare_medical`, `agriculture`, `creative_writing`, `coding_assistants`, `corporate_enterprise`, `autonomous_ai_agents` |
> | `language_scope` | ✅ | Array of BCP-47 language codes. Must include at least one. |
> | `african_alpha_claim` | ✅ | `true` only if claiming the African Use Case Bonus |
> | `budget_laptop_claim` | ✅ | Must be `true` — all submissions target the 8 GB RAM laptop profile |
> | `submitter.name` | ✅ | Full name of the team member submitting the run |
> | `submitter.email` | ✅ | Valid email address linked to the registered team |
> | `submitter.github_handle` | ✅ | Verifiable GitHub username |
> | `cross_disciplinary_pairing.discipline` | ✅ | The deep-tech discipline your model serves |
> | `cross_disciplinary_pairing.load_bearing` | ✅ | `true` if the pairing is integral to the submission, not cosmetic |
> | `test_prompts` | ✅ | **Exactly 2 prompts** in your chosen domain. Organizers will add 2 hidden prompts to test for overfitting. |
> | `model.runtime` | ✅ | Must be `llama.cpp`. No other runtime is accepted. |
> | `model.quantization` | ✅ | Must be a GGUF quantization format (e.g. `GGUF Q4_K_M`, `GGUF Q5_K_M`) |
> | `model.parameters_estimate` | ✅ | Approximate parameter count (e.g. `135M`, `1.1B`, `7B`) |
> | `model.packaging` | ✅ | How the model is packaged. One of: `docker_image`, `docker_build_from_repo`, `binary_bundle` |
> | `_runtime.model_path` | ✅ | Relative path from repo root to your `.gguf` file (e.g. `model/my-model.gguf`) |
>
> ## 📥 download_model.sh
>
> This script **must** download your model weight file to the `model/` directory.
>
> Rules:
> - Must be idempotent — safe to run multiple times without re-downloading.
> - Must work without any credentials — your weights must be publicly accessible.
> - The downloaded file path must exactly match `_runtime.model_path` in `metadata.json`.
>
> Recommended hosting options for your weights:
> - [Hugging Face](https://huggingface.co) — public model repos (free, best for GGUF files)
> - GitHub Release Assets — attach the `.gguf` file to a GitHub Release
> - Any stable public URL (GCS public bucket, S3 public object, etc.)
>
> ## 📄 REPORT.md
>
> Your technical writeup. Judges and the LLM-based audit system will read this to understand your submission. Cover:
>
> 1. **Problem** — What problem are you solving? Who is the target user in an African context?
> 2. **Design Decisions** — What model did you start from? Why that quantization level? What alternatives did you evaluate?
> 3. **Constraints** — What hardware, connectivity, or data constraints shaped your approach?
> 4. **Benchmarks** — What inference speed and memory numbers did you observe on your development machine?
>
> Keep it factual and specific. One to three pages is ideal.
>
> ## 🧪 Local Testing
>
> The ADTC profiler is open source. Install it directly from the official repository:
>
> ```bash
> pip install "git+https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler.git"
> ```
>
> Then run a local smoke test before submitting:
>
> ```bash
> # 1. Download your weights
> bash download_model.sh
>
> # 2. Run the profiler in participant mode
> adtc-profiler run \
>   --submission . \
>   --mode participant \
>   --output submission.json \
>   --skip-accuracy
>
> # 3. Review your report
> cat submission.json
> ```
>
> A valid run produces a `submission.json` with `"measured_on": "participant_laptop"`.
>
> The profiler source code, including the thermal monitoring logic and scoring formulas, is publicly readable at:
> [github.com/Africa-Deep-Tech-Foundation/adtc-profiler](https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler)
>
> ## ⚠️ Rules
>
> 1. **Public repository required.** Your repository must be public at the time of evaluation.
> 2. **No model weights in git.** Add `*.gguf` and `model/` to your `.gitignore`. The evaluator downloads weights fresh via `download_model.sh`.
> 3. **100% offline during evaluation.** Your model must run with zero external network dependencies during our testing window. `download_model.sh` runs before the profiler starts, but once profiling begins, no outbound requests are permitted.
> 4. **llama.cpp only.** All models must use GGUF weights and run through `llama.cpp`. No other runtime is supported by our evaluation framework.
> 5. **8 GB RAM limit.** Your model must run within the standard laptop profile (4 vCPU, 8 GB RAM, integrated GPU only). Out-of-memory errors during evaluation result in automatic disqualification.
> 6. **No size restriction.** There is no parameter count or file size cap — but the 8 GB RAM constraint is strict. Plan your quantization level accordingly.
> 7. **Two test prompts required.** Your `metadata.json` must include exactly 2 prompts in the `test_prompts` array. Organizers will generate 2 additional hidden prompts within your domain. All 4 are used for scoring.
>
> ## 🆘 Support
>
> Open an issue in this repository or contact the ADTF team at challenge@africadeeptech.org.
>
> View the full eligibility rules at [adtc-2026.devpost.com/rules](https://adtc-2026.devpost.com/rules).
>
> ## 📄 License
>
> This template is licensed under the terms of the [GNU GPL v3 License](LICENSE).

(Support note: template issues #1 (2026-06-30) and #4 (2026-08-04) both report `challenge@africadeeptech.org` bounces "address not found". Working channels: Devpost hackathon-manager email `africadeeptechcommunity@gmail.com`, Devpost forum, Discord `https://bit.ly/ADTC_Discord` / `https://discord.com/invite/C6U2ZWdMF`.)

### 2.3 REPORT.md — full text (verbatim; this is the structure to conform to)

```markdown
# Technical Report — [Your Submission Title]

**Team ID:** your-team-id  
**Domain:** coding_assistants  
**Model:** YourModel-Q4_K_M

---

## Problem

<!-- What problem are you solving? Who is the target user? Why does this matter in an African context? -->

Describe the problem your model addresses, the target user group, and why running this model locally (offline, on consumer hardware) is important for this use case.

---

## Design Decisions

<!-- What model did you start from? Why that base model and quantization? What alternatives did you consider and reject? -->

- **Base model:** e.g. Llama 3.2 1B, Mistral 7B, Phi-3 mini, etc.
- **Quantization:** e.g. Q4_K_M chosen for balance of quality and memory footprint
- **Alternatives considered:** e.g. Q8_0 exceeded 8 GB limit; Q2_K degraded output quality too aggressively

---

## Constraints

<!-- What hardware, connectivity, power, or data constraints shaped your choices? -->

- Target: 8 GB RAM, integrated GPU, Ubuntu 22.04
- No GPU acceleration — pure CPU inference via llama.cpp
- Any specific connectivity or data availability constraints relevant to your domain

---

## Benchmarks

<!-- What inference speed and memory numbers did you observe on your development machine? -->

| Metric | Value |
|---|---|
| Machine | e.g. MacBook Air M2 / ThinkPad X1 i5 |
| RAM at peak | e.g. 3.8 GB |
| Time to first token | e.g. 420 ms |
| Generation speed | e.g. 18.4 t/s |
| Thermal throttling | e.g. None observed |

These are self-reported development benchmarks. Official scores are measured by the ADTC profiler on the standard evaluation machine.
```

### 2.4 metadata.json — template file (verbatim)

```json
{
  "team_id": "your-team-id",
  "domain": "coding_assistants",
  "language_scope": ["en"],
  "african_alpha_claim": false,
  "budget_laptop_claim": true,
  "submitter": { "name": "your-name", "email": "your-email@domain.com", "github_handle": "your-github" },
  "cross_disciplinary_pairing": { "discipline": "education", "load_bearing": true,
    "description": "Brief description of how your model serves a real-world domain." },
  "test_prompts": [
    { "prompt_id": "tp_001", "prompt": "Write a Python function that reads a CSV file and returns the column with the highest mean value." },
    { "prompt_id": "tp_002", "prompt": "Explain the difference between a list and a tuple in Python, and give one example where each is the better choice." }
  ],
  "model": { "name": "SmolLM2-135M-Instruct-Q4_K_M", "runtime": "llama.cpp", "quantization": "GGUF Q4_K_M",
    "parameters_estimate": "135M", "packaging": "binary_bundle" },
  "_runtime": { "model_path": "model/SmolLM2-135M-Instruct-Q4_K_M.gguf" }
}
```
(Whitespace compacted here; key set and values are exact.)

### 2.5 download_model.sh — template file (verbatim)

```bash
#!/usr/bin/env bash
# Download your model weight file.
#
# Rules:
#   - Must be idempotent (safe to run multiple times).
#   - Must download without any credentials (public URL only).
#   - The output path must match `_runtime.model_path` in metadata.json.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_DIR="$HERE/model"
MODEL_FILE="$MODEL_DIR/SmolLM2-135M-Instruct-Q4_K_M.gguf"

# ── Replace this URL with your public model weight URL ─────────────────────────
MODEL_URL="https://huggingface.co/bartowski/SmolLM2-135M-Instruct-GGUF/resolve/main/SmolLM2-135M-Instruct-Q4_K_M.gguf"
# ───────────────────────────────────────────────────────────────────────────────

mkdir -p "$MODEL_DIR"

if [[ -f "$MODEL_FILE" ]]; then
  echo "model already present at $MODEL_FILE — skipping download"
  exit 0
fi

echo "downloading $MODEL_URL → $MODEL_FILE (~80 MB)…"

if command -v curl > /dev/null 2>&1; then
  curl -L --fail --progress-bar -o "$MODEL_FILE.partial" "$MODEL_URL"
elif command -v wget > /dev/null 2>&1; then
  wget --show-progress -O "$MODEL_FILE.partial" "$MODEL_URL"
else
  echo "error: neither curl nor wget found" >&2
  exit 1
fi

mv "$MODEL_FILE.partial" "$MODEL_FILE"
echo "done: $MODEL_FILE"
```

### 2.6 .gitignore — template file (verbatim)

```
# Model weights — never commit these to git
model/*.gguf
model/*.bin
model/*.safetensors

# macOS
.DS_Store

# Python
__pycache__/
*.pyc
.venv/

# Local profiler output
submission.json
audit.json
```

Observation: the template ignores `submission.json` (i.e. the organisers do not expect it in git), yet the profiler README says "Run on your own laptop to produce the `submission.json` you ship". See §7 (open questions).

### 2.7 LICENSE

GPL-3.0 (applies to the template itself: "This template is licensed under the terms of the GNU GPL v3 License"). A fork inherits it; nothing in the rules requires our repo to be GPL — the Devpost requirement is only "Open Source Github repo".

---

## 3. What the profiler enforces mechanically (source of truth for "hard" rules)

All from `https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler` @ main (0.1.0, schema 1.1.0).

### 3.1 metadata.json validation (`cli.py` + `schema/adtc-profiler.schema.json`)

- `metadata.json` must exist in the submission directory (`--submission <dir>`), else exit 2.
- `_runtime` must be an object; `_runtime.model_path` (default `"model.gguf"`) must exist relative to the submission dir, else exit 2 ("Run the submission's download_model.sh first").
- Every top-level key **not** starting with `_` is validated against the `submission` sub-schema **before** benchmarking; on failure exit 2. The sub-schema is `additionalProperties: false` at every level, so:
  - Allowed top-level keys: exactly `team_id, domain, language_scope, african_alpha_claim, budget_laptop_claim, submitter, cross_disciplinary_pairing, test_prompts, model` (all **required**) plus any `_*` keys (stripped).
  - `team_id`: string, minLength 1.
  - `domain`: enum `math_scientific_reasoning | healthcare_medical | agriculture | creative_writing | coding_assistants | corporate_enterprise | autonomous_ai_agents`.
  - `language_scope`: array, minItems 1, items string minLength 2 (BCP-47 by convention; not validated beyond length).
  - `african_alpha_claim`, `budget_laptop_claim`: boolean.
  - `submitter`: `{name (min 1), email (min 3), github_handle (min 1)}` only.
  - `cross_disciplinary_pairing`: `{discipline (min 1), load_bearing (bool), description (min 1)}` only.
  - `test_prompts`: array **minItems 2, maxItems 2**, each `{prompt_id (min 1), prompt (min 1)}` only.
  - `model`: `{name (min 1), runtime (min 1), quantization (string), parameters_estimate (string), packaging enum docker_image|docker_build_from_repo|binary_bundle}` only. (Schema does not check `runtime == "llama.cpp"` or that `quantization` starts with `GGUF` — those are README rules, enforced by humans/LLM audit.)
- Demo README (`examples/demo-submission/README.md`): "**All top-level fields are required** and no extra fields are allowed (`additionalProperties: false`) — the profiler validates before benchmarking and tells you exactly what's wrong." "`test_prompts` must contain **exactly two** prompts — judges use them alongside domain and hidden prompts." "`model.parameters_estimate` is checked against the actual parameter count read from your GGUF's tensor table (±15%) — state it honestly." "Underscore-prefixed keys never appear in the report."

### 3.2 `params_match` (±15 %) — `gguf.py`

```python
def fraud_check(claimed_estimate: str, actual_params: int | None) -> bool | None:
    """Two-sided check: measured params within ±15% of the claimed estimate. ..."""
    ...
    return claimed * 0.85 <= actual_params <= claimed * 1.15
```
- `parse_parameter_estimate` accepts `"8B"`, `"1.1B"`, `"135M"`, `"K"` suffix, or a bare integer (case-insensitive). Anything else → `None` → `params_match: null` ("an unknown must not masquerade as a passed check").
- `actual_params` = GGUF KV `general.parameter_count` **if present**, else the sum of tensor element counts from the tensor table (only GGUF v2/v3; v1 rejected → `{}` → `params_match: null`).
- Result lands in `model_info.params_match` of the report; the comparator does not act on it — it is "for fraud detection and run display" (human/LLM review). Ours: `params_count 7947423872` vs `"8B"` → `true` (window 6.8 B – 9.2 B). Even the post-prune true count (~7.7 B if `general.parameter_count` were absent) stays inside.

### 3.3 Throughput / memory / thermal (what "only the GGUF" means)

- `throughput.py`: `llama-bench -m <gguf> -p 512 -n 128 -ngl 0 --output json` (first `llama-bench` on PATH; no thread flag; the pp row → `first_token_latency_ms = 512/pp_rate*1000`; tg row `avg_ts` → `tokens_per_second_generation`).
- `memory.py`: psutil RSS of profiler + all descendants at 10 Hz during llama-bench; `peak_rss_mb` = max; `steady_state_rss_mb` = mean of last 60 s (or last half).
- `thermal.py`: `throttled = peak_temp >= 85.0` (best-effort; `core_temp_c_peak` may be `null`).
- Dockerfile: llama.cpp **`b10175`** built with `-DGGML_NATIVE=OFF -DGGML_AVX=OFF -DGGML_AVX2=OFF -DGGML_AVX512=OFF -DGGML_FMA=OFF -DGGML_F16C=OFF -DGGML_BLAS=OFF`, targets `llama-bench llama-cli llama-server`; runtime image `python:3.11-slim` + `lm-sensors libgomp1 git curl`.
- README audit command: `docker run --rm --memory=7.5g -v "/path/to/submission:/submission:ro" -v "/path/to/artifacts:/artifacts" adtc-profiler:latest run --submission /submission --mode audit --output /artifacts/audit.json`. **The submission is mounted read-only inside the audit container → `download_model.sh` is executed by the orchestrator beforehand, on the host, in an environment we cannot see** (inference from `:ro`; consistent with README rule 3 "`download_model.sh` runs before the profiler starts").
- Reproducibility block: `git_commit_sha` = `git rev-parse --short=12 HEAD` in the submission dir (or `000000000000`), `docker_image_digest` = inspect of `_runtime.docker_image` if given, else `"unknown"`, `random_seed` = `--seed` (42).

### 3.4 Comparator (`comparator.py`) — how our self-reported `submission.json` is judged against `audit.json`

- Tolerances: `memory.peak_rss_mb` ±15 %, `memory.steady_state_rss_mb` ±15 %, `throughput.tokens_per_second_generation` ±25 %, `throughput.first_token_latency_ms` ±25 % → beyond tolerance = **flag** ("routed to manual judge review"); |Δ| > 50 % = **fail**.
- Structural **fail**: submission or audit schema-invalid; `team_id` differs between the two; submission `environment.measured_on != "participant_laptop"`; audit `!= "audit_cloud_vm"`; any compared field missing/non-numeric; any submission value `== 0` ("An unverifiable zero claim maximizes the efficiency score").
- Accuracy is passed through, not diffed: "participant accuracy is on public benchmarks; audit accuracy is on the hidden 30% subset."
- Nothing in any source says what a `fail` verdict does to the score; the README only calls `flag` "marked for manual judge review". *Inference:* a `fail` on throughput because we profiled on an M1 (NEON) while the audit is x86 no-AVX is a real risk of a "doctored report" impression; see §8 recommendations.

### 3.5 Profiler README scoring (verbatim)

> | **S_acc (Accuracy)** | Qualifying score | Based on model responses to participant-submitted prompts, domain prompts, and hidden prompts supplied by judges. |
> | **S_perf (Throughput)** | `min(TPS / TPS_REFERENCE, 1.0) * 100` | Normalised against `TPS_REFERENCE = 15.0`. |
> | **S_eff (Efficiency)** | `max(0, (RAM_LIMIT_GB - peak_rss_gb) / RAM_LIMIT_GB) * 100` | Normalised against `RAM_LIMIT_GB = 7.0` (8 GB target profile). |
> | **P_thermal (Penalty)** | `10` points deduction | Applied if the CPU throttles or core temp exceeds 85°C. |

Participant mode: "Run on your own laptop to produce the `submission.json` you ship. The full run includes the accuracy benchmark ... While iterating, add `--skip-accuracy` ... but your final submitted report should come from a full run." Default accuracy task `arc_easy`, limit 50 ("Real audits use the hidden validation subset").

---

## 4. Devpost — rules, requirements, judging (verbatim)

### 4.1 Eligibility (`/rules`)

> Eligibility & Truth in Declaration: This challenge is strictly dedicated to early-stage builders. By entering, you formally declare that your project or company is less than 12 months old and that your product is in the ideation, conceptual, or early prototype phase (not commercially launched).
> Note: While we operate on an honor system during registration, the organizers reserve the right to conduct background checks on all finalists. Any team found to have misrepresented their stage, age, or funding will be immediately disqualified from the challenge and stripped of any awarded prizes.
> - Open to individuals or teams of up to 3 members.
> - Participants must reside in any of the listed African countries.
> - Participants must be above the legal age of majority in their country of residence
> - No prior startup or funding status required—this challenge is for emerging innovators.
> - Venture Age: Incorporations, formal registrations, or organized teams must not exceed 12 months of existence as of June 16, 2026.
> - Product Stage: Submissions must be at the ideation, conceptual, or early proof-of-concept (PoC) stage. Teams with fully commercialized products, active monthly recurring revenue (MRR), or mature minimum viable products (MVPs) already deployed in the market for more than 6 months will be disqualified.
> - Funding Cap: To ensure equity, participating teams must not have raised more than $25,000 USD in external dilutive capital or non-dilutive grants.
> - All submissions must be the original work of the team.
> - Teams can use open-source tools or libraries but must cite them clearly.
> - You agree to the Challenge Participation Agreement

Manager clarification (forum 44727, 9 days ago): "As an individual participant, you are eligible if the project was built from scratch for this challenge and the IP does not belong to your business entity that has been in existence for more than 12 months."

Participation Agreement (Google Doc) — relevant clauses: §5 "Team participants must appoint and authorize one individual (the 'Representative') ... Prizes will be payable to ... the participant's Representative, if a Team"; §7 "Participants retain ownership of all intellectual property created during the Contest. However, by participating, you grant us and our partners a non-exclusive, royalty-free license to use your submissions for promotional and marketing purposes."; §2 prizes discretionary; §9 terms may change.

### 4.2 Project and Submission Requirements (`/rules`, repeated as "What to Submit" on the overview)

> - Open Source Github repo that leverages the approved ADTC 2026 Report Template  [link → the template repo]
> - A comprehensive project report including:
> - Problem definition and context
> - Identified constraints (e.g. power, data, compute, connectivity)
> - Documentation of design alternatives and final decisions
> - Tools used and why they were chosen
> - Performance tests and benchmarks
> - Screenshots or short videos showing your build in action
> - A short video (max 2 minutes) explaining your solution and development journey
> - Updated repo, documentation and video (if part of semi-final or final round)

Overview "What to Build": "Participants build a working, end-to-end, on-device Language Model that runs without cloud dependencies on the ADTC Standard Laptop (defined below). The model must address one of the published problem domains ... Each team selects one primary domain." Domain text for ours: "**Math & Scientific Reasoning** - problem solving, proof assistance, scientific question-answering, and quantitative reasoning tasks."

Standard Laptop table (overview): CPU "Intel Core i5 10th–12th gen OR AMD Ryzen 5 3000–5000 (x86-64)"; RAM "8 GB DDR4"; Graphics "Integrated only ... No discrete GPU."; Storage "256 GB SSD"; OS "Ubuntu 22.04 LTS"; price "$400–$500 new / $150–$250 refurbished". "Participants may develop on any hardware, but final benchmarks and audits are reported against the Standard Laptop profile."

### 4.3 Judging Criteria (`/rules` and overview)

> Model Accuracy & Quality | 50% | A combination of multiple-choice benchmarks and qualitative evaluations that includes accuracy of prompts, quality of documentation
> Model Throughput Performance | 30% | Evaluated relative to the maximum observed tokens per second
> Model Efficiency | 20% | Rewards lower RAM utilization profiles relative to the maximum memory budget
> African Use Case Bonus | Bonus | Up to 10 extra points awarded for how applicable the model is to a real African use case
> Hardware & Thermal Penalties | Penalty | 10 points deducted if core/package temperature exceeds 85∘C or if thermal throttling is flagged. OOM or sandbox execution crash results in disqualification

Overview "Leaderboard Scoring": `Stotal = 0.50⋅Sacc+0.30⋅Sperf+0.20⋅Seff−Pthermal`; Sacc "Weighted average of model response scored between 0 and 100 by a Judge."; Sperf "100 × (TPSact ÷ TPSmax) — TPS_REFERENCE = 15.0 provisional"; Seff "100 × ((7 GB − Peak RAM) ÷ 7 GB) ... Peak RAM = 7 GB"; Pthermal "-10 if throttled or temp > 85°C Else 0".

**"quality of documentation" is explicitly inside the 50 % accuracy bucket** → REPORT.md is scored, not just read.

### 4.4 Prizes (Devpost)

Grand $8,000; Second $4,000; 3rd $3,000; **Best African Use Case $1,500** ("Awarded for the strongest African use case implementation. 3-month residency"); Finalist stipends $250 GPU credits ×10; Semifinalist $50 GPU credits ×20 ("awarded to top 20 by submission quality"). (ADTF site labels the $3,000 tier "Best Integration Award — most load-bearing and robust cross-disciplinary deep-tech pairing" and the $1,500 tier "Best Localisation Award — deepest integration with African languages, offline data, or local contextual depth"; Devpost is the registration of record — treat the site's labels as intent.)

### 4.5 Devpost update — the two self-reported numeric fields (2026-08-01, verbatim)

> The submission form has been updated to enable you to enter the self-reported profiler scores in separate fields.
> - Self-Reported Profiler Performance Score (Sperf)
> - Self-Reported Profiler Efficiency Score (Seff)
> If you have previously completed your submission, please ensure that you update your submission to include the correct self-reported profiler scores.

ADTF FAQ on the same: "These are two separate numeric fields on the DevPost submission form — enter one plain number in each, not a combined string like 'Sperf=46, Seff=41'. Your local profiler's `submission.json` gives you raw numbers, not the normalized 0–100 score, so compute each score yourself from your own run, then enter the resulting number in each field."

### 4.6 Devpost forum clarifications by the hackathon manager (verbatim)

- **team_id** (forum 44336): "The team ID in this context means the project ID. E.g for this Devpost project (https://devpost.com/software/project-farmspeak) it is : project-farmspeak". (ADTF FAQ says: "Your Team ID is generated automatically when you register your team on DevPost — use that same ID in your submission's `metadata.json`." Template README says "as registered on the ADTF portal" — no such portal exists; template issue #4 asks exactly this and is unanswered.) **Working rule: `team_id` = the slug of our Devpost project URL.**
- **Offline scope** (forum 44164, Q "Clarification if App should work completely offline? Or only the model should be offline?"): "For the first round, we will only be testing your model, and it has to work completely offline."
- Repo links (forum 44127): profiler and template URLs confirmed as the ones used above.
- Open, unanswered: forum 44742 (where is the validation set; is Sacc multiple-choice or judged free text), forum 44369 (profiler accuracy.py bugs; may Gate 1 ship `accuracy: []` via `--skip-accuracy`).

### 4.7 Devpost form fields — what is known

Confirmed from public pages: a **"Problem Domain"** select (gallery filter lists the seven domains), **Sperf** numeric, **Seff** numeric, the repo URL ("submit your repository URL via adtc-2026.devpost.com"), the ≤2-minute video. Standard Devpost project fields (*inference from Devpost's generic form; the exact list is login-only*): project name (its slug becomes `team_id`), tagline, "About the project" (inspiration / what it does / how we built it / challenges / accomplishments / what we learned / what's next), "Built with" tags, "Try it out" links (repo), video demo link (publicly viewable YouTube/Vimeo etc.), image gallery/thumbnail, team members invited by Devpost account, eligibility attestations (residency country, age), and acceptance of the Participation Agreement.

---

## 5. ADTF microsite — hardware ceiling, gates, bonuses, FAQ (verbatim)

- Hardware: "Memory ceiling **7 GB RAM** — Exceeding this limit results in immediate disqualification (Stotal = 0)." Target spec table = Devpost's (i5 10th–12th gen, 8 GB DDR4, integrated graphics, 256 GB SSD, Ubuntu 22.04).
- "### African Alpha Bonus — Submissions with meaningful functionality in at least one African language earn +15% on their panel score." and "Score multipliers Budget Profile +10% · African Language +15%".
- Gate 1 deliverables: "Open-source GitHub repo (ADTC 2026 submission template)"; "REPORT.md — problem definition, constraints, design decisions, tools & benchmarks"; "Screenshots or short video clips showing your model running"; "2-minute video — your solution and development journey"; "**Bonus claims: African language support / budget laptop**".
- Gate 2 deliverables: "30-minute technical Q&A session (scheduled)"; "Prompt responses to reviewer clarification requests"; "Optional: 1-page response to feedback"; "Optional: updated benchmark report". Gate 3: "Final pitch deck (max 10 slides)"; "Live-session attendance confirmation"; "Technical setup verification".
- Scoring block: Sperf "Generation speed relative to the fastest submission across all teams. Sperf = 100 × (TPSact ÷ TPSmax)"; Seff "Peak RAM: maximum RSS measured during audit · Budget = 7 GB"; "OOM / Crash → Disqualified ... Stotal = 0".

FAQ entries that bind the package (verbatim):

- "**How does offline/local judging execution work?** Judging is done by actually running your submitted model, not by reading a transcript or a static output log. When a judge opens your run, we spin up a fresh sandboxed instance of your exact submission inside an environment resource-capped to match the Standard Laptop profile (8 GB RAM, 4 CPU cores), and the judge chats with it live through our in-browser interface. There's no third-party tool involved on the judge's side — your score reflects how your model actually behaves under the real target hardware constraints."
- "**What specific tools or frameworks are allowed for quantization and deployment?** llama.cpp only. All submissions must run through llama.cpp using GGUF weights to ensure compatibility with our evaluation setup."
- "**What is the maximum allowed size for the model?** There is no strict maximum size limit. However, your model will be evaluated entirely on its performance and efficiency on the standard benchmark computer (8 GB RAM). Keep memory constraints in mind to avoid OOM disqualification."
- "**How will the final benchmarking and audit be conducted ...?** We will run your model on a dedicated testing machine using our automated evaluation framework. To ensure your model tests successfully without errors, your submission must conform to the official template: adtc-2026-submission-template"
- "**What exactly do I need to submit for evaluation?** Just your model repository with a working `download_model.sh`, plus your two required test prompts. You are not required to run or submit any accuracy benchmarking yourself — you only need to produce your own performance and efficiency telemetry locally as a self-check (throughput, memory, thermal). Accuracy (S_acc) is scored entirely by the judging panel, who run your actual model — you never submit an accuracy number."
- "**Does evaluation measure my whole application, or just the model?** Just the model. Automated profiling and resource limits (memory, throughput, thermal) apply only to the LLM inference process itself (llama.cpp running your GGUF model) — we do not measure or enforce resource limits on any supporting application stack (CV, audio, sensing, etc.). Judging is also scoped to the model's responses, not a broader application UI."
- "**What exact benchmarks and prompts will be used for grading accuracy?** You will provide two test prompts with your submission. The organizers will then generate **three** additional hidden prompts within your chosen domain to test for response accuracy."
- "**How will core temperatures and thermal throttling be monitored ...?** We capture the device's temperature immediately before and immediately after each benchmark run. For multiple runs, we introduce a cooldown delay ... A 10-point thermal penalty applies if the CPU throttles or the peak core temperature exceeds 85°C."
- "**Are hybrid approaches allowed, or must the application be 100% offline?** The model must run 100% offline with zero external network dependencies during our testing window."
- "**What qualifies an entry for the 'African Use Case Bonus'?** The bonus rewards any solution that clearly caters to real-world African contexts and infrastructure realities. Supporting a local language is not a requirement—the primary language of evaluation for this competition is English."
- "**What African languages qualify for the Alpha Bonus?** Any African language qualifies when the functionality is meaningful. Swahili, Yoruba, Wolof, Igbo, Zulu, Amharic, Hausa, Shona, and Twi are all excellent examples."
- "**What does cross-disciplinary actually mean?** Your local LLM must connect to another deep-tech discipline in a load-bearing way. Examples include offline RAG over agricultural records, edge sensing, geospatial analysis, or local medical diagnostic assistance."
- "**Can I use fine-tuned open-source models?** Yes. You are encouraged to use open-source base models (e.g. Llama, Mistral), quantize them, fine-tune them on local data, and compile them for local CPU runtimes."
- "**Does the 2-minute video require a live demonstration of the model running in real-time?** While seeing your model running live is highly encouraged, it is not strictly required. This video is your opportunity to pitch yourself and your engineering work to the judges—feel free to use your creative license to make it stand out!"
- "**Where do I get my ADTC Team ID for metadata.json?** Your Team ID is generated automatically when you register your team on DevPost — use that same ID in your submission's `metadata.json`."

---

## 6. Field semantics — consolidated (with source and our reading)

| Field | Semantics (sources) | Our value now | Verdict |
|---|---|---|---|
| `team_id` | Manager: Devpost **project slug** (e.g. `project-farmspeak`); FAQ: "generated automatically when you register your team on DevPost"; template: "ADTF portal" (nonexistent). Comparator hard-fails on submission/audit mismatch (both come from our metadata.json, so only self-inconsistency can bite). | `team-muta` | **Set to the actual Devpost project slug once the project exists** (or name the Devpost project so its slug is `team-muta`); regenerate `submission.json` afterwards. |
| `domain` | enum | `math_scientific_reasoning` | OK |
| `language_scope` | "Array of BCP-47 language codes. Must include at least one." Semantics = languages in which the model has meaningful functionality; the primary evaluation language is English (FAQ). Any non-`en` entry is a claim judges may probe live. | `["en"]` | OK and honest (vocab pruned to English). Do not add African languages unless the model actually handles them. |
| `african_alpha_claim` | Template README: "`true` only if claiming the African Use Case Bonus" (Devpost: "Up to 10 extra points ... how applicable the model is to a real African use case"; FAQ: "Supporting a local language is not a requirement"). ADTF site names the same flag "African **Alpha** Bonus — meaningful functionality in at least one African language earn +15% on their panel score", and Gate 1 lists "Bonus claims: African language support / budget laptop". Two readings coexist. | `true` with `language_scope ["en"]` | Defensible **only under the use-case reading**; internally inconsistent under the language reading. Whatever we choose, REPORT.md must carry an explicit "African use case" section with evidence (curriculum, currency/context of prompts, offline classroom deployment, cost of the target laptop). If we keep `true`, say plainly in REPORT.md that the claim is a *use-case* claim, not a language claim. |
| `budget_laptop_claim` | Template: "Must be `true` — all submissions target the 8 GB RAM laptop profile"; ADTF: "Budget Profile +10%" multiplier; Gate 1 "Bonus claims: ... budget laptop". Evidence = runs on the Standard Laptop profile with headroom (peak RSS ≪ 7 GB, no OOM, thermal OK). | `true` | OK. Put the evidence table (peak RSS, tok/s, x86 run) in REPORT.md. |
| `submitter.*` | name = "Full name of the team member submitting the run"; email = "Valid email address linked to the registered team"; github_handle = "Verifiable GitHub username". | Timi Owolabi / timiiowolabi@gmail.com / iitimii | Must match the Devpost account that files the submission (or a listed member) — verify the Devpost team roster/representative. |
| `cross_disciplinary_pairing` | FAQ: "must connect to another deep-tech discipline in a load-bearing way"; `load_bearing` "`true` if the pairing is integral to the submission, not cosmetic". Best Integration Award ($3k on the ADTF site) keys off this. | education / true / adaptive Socratic tutoring | OK; REPORT.md must show *why* it is load-bearing (pedagogy baked into the model's behaviour, not a UI skin). |
| `test_prompts` | Exactly 2, ids+text non-empty, "written for your chosen domain"; judges use them plus 2 (README) or 3 (FAQ) hidden in-domain prompts; judged live via chat, scored 0–100 each. | tp_001 (naira profit word problem), tp_002 (falling-ball misconception) | Format OK. Content strategy is R-other, but note the prompts are public and will be sent as plain user turns to the raw GGUF (no system prompt from us unless baked into the chat template). |
| `model.name` | free string | `bitcpm4-8b-tq2_0-envocab` | OK |
| `model.runtime` | "Must be `llama.cpp`" | `llama.cpp` | OK |
| `model.quantization` | "Must be a GGUF quantization format (e.g. `GGUF Q4_K_M`)" — string, human/LLM-read | long descriptive string | Prefer the canonical short form `GGUF TQ2_0` (details go in REPORT.md); the long string is not invalid, but "an LLM-based audit system will read this". |
| `model.parameters_estimate` | `"<num>[K|M|B]"`, ±15 % of GGUF params (KV or tensor sum) | `8B` | OK (`params_match: true`). |
| `model.packaging` | enum; for a bare GGUF the template/demo use `binary_bundle` | `binary_bundle` | OK |
| `_runtime.model_path` | relative path, must equal what `download_model.sh` writes | `model/bitcpm4-8b-tq2_0-envocab.gguf` | OK; `_runtime.docker_image` optional (feeds `docker_image_digest`), not needed. |

---

## 7. Discrepancies between sources (know them before someone asks)

1. **Hidden prompt count**: template README = 2 hidden ("All 4 are used for scoring") vs ADTF FAQ = "three additional hidden prompts". Plan for 2–3.
2. **RAM ceiling wording**: template/Devpost "8 GB RAM limit ... OOM = disqualification"; ADTF "Memory ceiling 7 GB RAM — exceeding = Stotal 0"; profiler `Seff` budget 7.0 GB and Docker `--memory=7.5g`. Practical hard cap = 7.5 GB for llama-bench + profiler; anything ≥ 7 GB peak scores Seff = 0 and per ADTF is a DQ.
3. **Sperf normalisation**: profiler README `min(TPS/15,1)*100`; Devpost "100 × (TPSact ÷ TPSmax) — TPS_REFERENCE = 15.0 provisional"; ADTF "relative to the fastest submission". For the Devpost self-report field, use 15.0 (the only number we can compute today) and say so in REPORT.md.
4. **team_id source**: portal (template) vs Devpost auto-generated (FAQ) vs Devpost project slug (manager). Follow the manager.
5. **`african_alpha_claim`**: use-case bonus (+10 pts, Devpost/template) vs African-language bonus (+15 % panel score, ADTF site). See §6.
6. **Prize labels**: Devpost 3rd place $3,000 vs ADTF "Best Integration Award $3,000"; Devpost "Best African Use Case $1,500" vs ADTF "Best Localisation Award $1,500".
7. **Deadline**: Devpost Aug 24 23:45 PDT vs "Aug 25" (same instant in UTC/WAT) vs Substack "July 24" (stale).
8. **`submission.json` in git**: template `.gitignore` excludes it; profiler README says it is what you "ship"; Devpost captures only Sperf/Seff numbers. No file-upload field is documented.
9. **Support email** in the template bounces; use Devpost forum / manager email / Discord.

---

## 8. The checklist for `muta-iq/` (files, fields, form) — with current status

Legend: ✅ satisfied now · ⚠️ needs action · ❌ missing/blocking.

### 8.1 Repository shape

- ❌ **Submission repo root must contain `metadata.json`, `download_model.sh`, `REPORT.md`, `.gitignore`** (template "Required File Structure"; FAQ "your submission must conform to the official template"; profiler `--submission <dir>` looks for `metadata.json` in that dir). Today these live in `muta-iq/` *inside* `github.com/nelsonifechukwu/Muta` whose root has none of them. Either (a) publish `muta-iq/` as its own public repo (preferred — ideally created by forking the template so it appears in the template's fork network and inherits `model/.gitkeep`), or (b) move the four files to the Muta root. Whatever URL goes into Devpost must have `metadata.json` at its root.
- ⚠️ Repository **public** at evaluation time (rule 1). Muta is currently a personal-account repo; confirm visibility.
- ⚠️ `LICENSE` present and open-source ("Open Source Github repo"). Muta root has an MIT LICENSE; `muta-iq/` alone has none. If we fork the template we inherit GPL-3.0; otherwise add MIT/Apache-2.0 at the submission root.
- ✅ `.gitignore` excludes `*.gguf` and `model/` (rule 2). Ours ignores `model/` wholesale plus `*.gguf` — fine (`download_model.sh` does `mkdir -p`). Add `!model/.gitkeep` only if we want the dir tracked like the template.
- ⚠️ `submission.json` is tracked in git (Muta already tracks `muta-iq/submission.json`); template ignores it. Decision: **keep it committed** (it is the only place the comparator can get it from) but regenerate it from the *final* `metadata.json` and, ideally, on x86 (see 8.5).
- ⚠️ `dashboard/profiler.db` (binary) and the whole `opt/` workspace: keep the repo lean and readable — the LLM audit reads the repo. `opt/` is currently untracked; if `download_model.sh` keeps referencing `opt/scripts/prune_vocab.py`, that script (and its deps) must be tracked; better to remove the dependency (8.3).
- ⚠️ Screenshots/clips "showing your build in action" must live in the repo (e.g. `docs/screenshots/*.png` referenced from REPORT.md) — only the repo + video reach the judges.

### 8.2 `metadata.json`

- ✅ Exactly the nine required top-level keys + `_runtime`; no extras (schema `additionalProperties: false`). Re-validate with `adtc-profiler run ... --skip-accuracy` after every edit.
- ⚠️ `team_id` → Devpost project slug (§6). Then regenerate `submission.json` (comparator hard-fails on mismatch).
- ⚠️ `submitter.email` must be the address on the Devpost account/team of the person submitting.
- ⚠️ `african_alpha_claim: true` vs `language_scope: ["en"]` — decide (§6) and back it in REPORT.md.
- ⚠️ `model.quantization` → `GGUF TQ2_0` (short canonical form).
- ✅ `test_prompts` exactly 2, ids `tp_001`/`tp_002`.
- ✅ `parameters_estimate "8B"` within ±15 % of the GGUF's parameter count (`params_match: true`).
- ✅ `packaging binary_bundle`; `_runtime.model_path` = script output path.
- ⚠️ No placeholder text anywhere (template checklist item 2) — description strings are fine today.

### 8.3 `download_model.sh`

- ❌ **`MODEL_URL` is still a TODO.** The fallback (download upstream 2.4 GB → `pip install gguf numpy` → run `opt/scripts/prune_vocab.py`) needs python3 + pip + network + `opt/` in the repo + enough RAM/disk on the *orchestrator host*, none of which is guaranteed (the audit container mounts the submission `:ro`, so the script runs somewhere we do not control). **Upload the final pruned GGUF to a public, non-gated HF repo and hard-code that URL as the default; keep the derive path only as an explicitly opt-in developer mode (or drop it).**
- ✅ Idempotent (sha256 check → skip), no credentials, `set -euo pipefail`, curl/wget fallback, `.partial` rename, output path == `_runtime.model_path`.
- ⚠️ Idempotency detail: template semantics are "skip if file exists"; ours re-downloads if the sha mismatches (good) — make sure the hard-coded `MODEL_SHA256` is updated whenever the GGUF is rebuilt, or the script hard-fails on the auditor's machine.
- ⚠️ `sha()` helper: `shasum` (perl) is absent on minimal Debian images; the `|| sha256sum` fallback works only because `pipefail` makes the first pipeline fail — keep, but test in `debian:bookworm-slim` and `python:3.11-slim`.
- ⚠️ Print the expected size honestly (`~2.2 GB`) and finish with `done: <path>` (template convention). Test with literally `bash download_model.sh` from a fresh clone (template checklist item 8), including on Linux x86.
- ✅ HF hosting is the template's first recommendation; upstream `openbmb/BitCPM-CANN-8B-gguf` is Apache-2.0 and not gated, so redistributing a derived GGUF is licence-clean (attribute it).

### 8.4 `REPORT.md` (❌ missing at submission root; `opt/docs/REPORT.md` is an internal optimisation log, not the deliverable)

Must exist at the repo root, keep the template's skeleton, and additionally cover every bullet in the Devpost list. Recommended structure (template headings verbatim, extra sections appended — the audit LLM and judges are told to expect the four):

```
# Technical Report — Muta IQ: offline math & science tutor
**Team ID:** <devpost-slug>   **Domain:** math_scientific_reasoning   **Model:** bitcpm4-8b-tq2_0-envocab
---
## Problem            (African context, target user, why offline/on-device; the African use-case evidence lives here)
## Design Decisions   (base model + licence, why TQ2_0/ternary, vocab prune, alternatives rejected WITH numbers: TQ1_0, SVD, head requant, other bases)
## Constraints        (Standard Laptop profile, audit engine b10175 no-AVX/no-FMA/no-F16C generic kernels, 7 GB budget, offline, GGUF-only)
## Benchmarks         (template table: Machine / RAM at peak / TTFT / Generation speed / Thermal; then an x86 no-AVX row; then the profiler submission.json numbers and how Sperf/Seff self-reports were computed; the closing sentence from the template)
## Tools used and why (llama.cpp b10175/b10360, gguf-py, adtc-profiler, lm-eval, prune_vocab.py … — "must cite them clearly")
## Cross-disciplinary pairing (education): why it is load-bearing
## African use case & budget-laptop claims (explicit evidence for both metadata flags; state that african_alpha_claim is a use-case claim, language_scope stays en)
## Demo (screenshots / clip links; the 2-minute video URL)
## Reproducibility (download_model.sh, sha256, how to run the profiler, commit SHA)
```
"One to three pages is ideal" — keep the root REPORT.md tight and link to `opt/docs/REPORT.md` for the long-form log.

### 8.5 `submission.json` / self-reported numbers

- ⚠️ Regenerate after the final `metadata.json` and final GGUF (team_id, sha, commit). Full run (with accuracy) is what the profiler README asks for; forum 44369 notes the accuracy stage was buggy in 0.1.0 (fixed 2026-07-29 in-process llama-cpp-python path); our current file already has `arc_easy acc_norm 0.84 (50 samples)`.
- ⚠️ `measured_on` must be `participant_laptop` (comparator structural rule) — i.e. run with `--mode participant`, never `audit`.
- ⚠️ Comparator risk: M1 numbers (18.21 tok/s, 2462 MB) vs the x86 no-AVX audit will almost certainly differ by > 50 % on TPS → `fail` verdict. *Recommendation (inference):* produce the shipped `submission.json` with the profiler's own Docker image (`docker build` the profiler repo, `--platform linux/amd64`, `--memory=7.5g`, `--mode participant`) on a real 4-vCPU x86 box or cloud VM so the deltas sit inside ±25 %/±15 %; keep the M1 numbers in REPORT.md as "development machine". At minimum, document the expected gap in REPORT.md.
- ⚠️ Devpost fields: **Sperf** = `min(TPS/15,1)*100` from the shipped `submission.json`; **Seff** = `(7 - peak_rss_gb)/7*100`. One plain number each. Update the Devpost entry if `submission.json` changes ("please ensure that you update your submission").
- ✅ Never a `0` in any compared field (comparator fails zero claims).

### 8.6 The GGUF itself (the only artefact that reaches the audit)

- ✅ Valid GGUF v3, loads in stock `llama.cpp b10175` built without AVX/AVX2/FMA/F16C (test with the profiler image, not Homebrew).
- ⚠️ Chat template: judges "chat with it live through our in-browser interface" — presumably `llama-server` from the same image with the GGUF's `tokenizer.chat_template` and default sampling. There is no channel to ship a system prompt, flags, grammar or sampler settings; anything persona-related must be inside the GGUF (weights or the embedded chat template — cf. `opt/scripts/bake_system_prompt.py`). Verify the template renders correctly under b10175's Jinja engine and that responses are robust to default sampling (*inference*; the judge tool is not public).
- ✅ Peak RSS on x86 (MAP_POPULATE → ≈ file size + buffers ≈ 2.3–2.6 GB) is far under 7 GB.
- ⚠️ `parameters_estimate` stays consistent if the GGUF is rebuilt (prune changes the tensor sum; `general.parameter_count` KV, if present, wins).

### 8.7 Devpost entry

- ❌ Create the project (this fixes `team_id`), select Problem Domain = Math & Scientific Reasoning, paste the repo URL, upload/link the ≤ 2-minute video ("explaining your solution and development journey"; live demo encouraged, not required), enter Sperf and Seff as plain numbers, add screenshots, list team members (≤ 3, all resident in eligible countries, of majority age), accept the Participation Agreement, name the Representative.
- ⚠️ Truth-in-declaration: project < 12 months old as of 2026-06-16, PoC stage, < $25k raised; the finalist background check applies.
- ⚠️ Submit well before 2026-08-25 06:45 UTC; Devpost lets you edit until the deadline.

### 8.8 Things that do NOT reach the audit (do not rely on them for score)

The dashboard, the streaming engine, any llama.cpp patches, run scripts, system prompts passed at runtime, GBNF grammars, sampler flags. FAQ: "Automated profiling and resource limits ... apply only to the LLM inference process itself (llama.cpp running your GGUF model)"; "Judging is also scoped to the model's responses, not a broader application UI." They *do* count for documentation quality (part of the 50 %), the video, and later gates.

---

## 9. Verbatim hard-rule list (one line each, with source)

1. Public GitHub repo, conforming to the template (template README rule 1; Devpost "leverages the approved ADTC 2026 Report Template"; FAQ).
2. `metadata.json` — all nine fields, no placeholders, no extra keys, exactly 2 `test_prompts` (template checklist; profiler schema).
3. `model.runtime` = `llama.cpp`; GGUF weights only; "No other runtime is supported" (template rule 4; FAQ "llama.cpp only").
4. No weights in git; `*.gguf` and `model/` in `.gitignore`; evaluator downloads via `download_model.sh` (template rule 2).
5. `download_model.sh`: idempotent, credential-free public URL, output path == `_runtime.model_path`, `bash download_model.sh` exits 0 (template).
6. 100 % offline during evaluation; no outbound requests once profiling begins (template rule 3; FAQ; forum 44164).
7. 8 GB Standard Laptop profile (4 vCPU, integrated GPU only); OOM/sandbox crash = disqualification; 7 GB Seff budget / ADTF "7 GB ceiling"; audit container `--memory=7.5g` (template rule 5; Devpost judging; ADTF; profiler).
8. No parameter/file-size cap (template rule 6; FAQ).
9. `parameters_estimate` within ±15 % of the GGUF's real parameter count (`params_match`) (profiler gguf.py; demo README).
10. Test prompts: exactly 2, in-domain; organisers add 2 (template) / 3 (FAQ) hidden in-domain prompts; all scored 0–100 by judges chatting live (template rule 7; FAQ).
11. `language_scope`: ≥ 1 BCP-47 code; English is the primary evaluation language (template; FAQ).
12. `african_alpha_claim`: true only if claiming the African Use Case / Alpha bonus; evidence expected in the package (template; Devpost +10 pts; ADTF +15 % language reading).
13. `budget_laptop_claim`: must be `true`; evidence = runs within the 8 GB profile (template; ADTF +10 %).
14. REPORT.md: problem, design decisions, constraints, benchmarks (+ Devpost: tools used and why; performance tests; screenshots/short videos) — "quality of documentation" is scored inside Sacc (template; Devpost rules/judging).
15. Video ≤ 2 minutes, solution + development journey (Devpost; FAQ).
16. Team ≤ 3, resident in eligible African countries, age of majority, venture < 12 months as of 2026-06-16, PoC stage, < $25k raised, original work, cite OSS clearly, accept Participation Agreement (Devpost rules).
17. Devpost form: repo URL, Problem Domain, Sperf and Seff as separate plain numbers, video (Devpost update 45602; FAQ).
18. Deadline 2026-08-24 23:45 PDT / 2026-08-25 06:45 UTC (Devpost).

---

## 10. Open questions worth one forum/Discord post (unanswered publicly as of 2026-08-17)

1. Is `team_id` the Devpost *project* slug (manager, forum 44336) or a team identifier (FAQ)? Confirm which value the audit orchestrator uses.
2. Should `submission.json` be committed to the repo (template ignores it) or uploaded elsewhere? What does a comparator `fail` (not `flag`) do to a Gate-1 entry?
3. Hidden prompts: two (README) or three (FAQ)?
4. Judge chat interface: does it use the GGUF's embedded chat template and llama-server defaults (temperature etc.), and is a system prompt ever injected?
5. `african_alpha_claim`: use-case (+10 pts) or African-language (+15 %) claim — may a purely English tutor with African-context content claim it?
6. Environment in which `download_model.sh` is executed on the audit side (Ubuntu with curl only? python available? disk quota for a 2.2 GB file?).
