# ADTC 2026 — rules digest

**ROADMAP deliverable: Tue 14 Jul, `[All]`.** The roadmap set six questions and said each one
changes a design decision. This answers them from primary sources.

**Status:** four answered from the profiler's source code, two from official pages, several
still open. **Three answers contradict assumptions the ROADMAP is built on** — see
[Contradictions](#contradictions-read-this).

## Sources, pinned

Everything below is cited to one of these. The profiler is pinned to a **commit SHA**, not
`HEAD` — the upstream repo moves and an unpinned claim rots silently.

| Source | Reference |
|---|---|
| Profiler source (GPL-3.0) | [`Africa-Deep-Tech-Foundation/adtc-profiler`](https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler) @ [`cf3432cf`](https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler/tree/cf3432cf54216617429cf3f9d3d7150fb891fdd1) (2026-06-22) |
| Submission template | [`adtc-2026-submission-template`](https://github.com/Africa-Deep-Tech-Foundation/adtc-2026-submission-template) (pushed 2026-06-15) |
| Official challenge page | <https://africadeeptech.org/challenge-2026/> |
| Devpost | <https://adtc-2026.devpost.com/> |
| Clarifications | `africadeeptechcommunity@gmail.com` |

Read *the code*, not the prose: the challenge page itself says you can "review the exact logic,
thresholds, and sensor tracking by studying the profiler source code." Where page and code
disagree, the code is what runs.

---

## 2026-08-05 addendum — profiler moved to `7adbe08` (upstream HEAD, 2026-07-30)

The digest below was written against `cf3432cf` (2026-06-22). A local clone of upstream HEAD
now lives at `bench/adtc-profiler/` (verified = origin/main, zero commits since), and
`bench/adtc/install.py` pins it. What changed, verified from that source:

1. **The audit reference Dockerfile exists now, and its llama-bench is nearly SIMD-less.**
   Stage 1 builds llama.cpp `b10175` with `GGML_NATIVE/AVX/AVX2/AVX512/FMA/F16C all OFF`
   (SSE4.2 + BMI2 remain on via defaults); the container runs under `--memory=7.5g`.
   Consequences, verified in llama.cpp source at that tag:
   - Only **Q4_0** has a vectorized (`__SSSE3__`) CPU dot kernel in such a build; Q4_K,
     Q5_K, Q6_K, Q8_0 and every IQ type fall through to pure-scalar generic C
     (`ggml/src/ggml-cpu/arch/x86/quants.c`). Quant choice changes scored TPS by
     multiples, not percents, if the audit uses this image.
   - **No weight repack happens** (every x86 repack path is gated on compile-time AVX2 in
     `repack.cpp`), so scored peak RSS ≈ GGUF file size + ~0.4–0.6 GB — NOT the
     file+repack ≈ 4.36 GB measured through an AVX2 llama-bench (RESULTS.md 2026-08-04).
   - The accuracy stage's llama-cpp-python is built with only `GGML_NATIVE=OFF` →
     AVX2 stays on for S_acc; the crippled build applies to throughput/memory only.
2. **The accuracy stack ships in the default profiler install** (lm-eval ≥0.4.4 +
   llama-cpp-python ≥0.3.0, in-process, `n_ctx=2048` hardcoded, **no chat template**,
   `acc_norm` preferred, generation greedy temp=0; audit mode exits 4 if the stack is
   missing). New CLI: `--accuracy-task` (default `arc_easy`), `--accuracy-limit` (50),
   `--skip-accuracy`.
3. **The fraud check went two-sided**: claimed params must satisfy
   `0.85·claim ≤ tensor-table sum ≤ 1.15·claim`, and returns `null` (not `true`) when
   uncheckable. Our Qwen3.5-4B GGUF sums to **4,205,751,296** → "4B" and "4.2B" both pass.
4. **Comparator bands clarified**: pass within ±25% TPS / ±15% RSS; **flag** (manual judge
   review) out to a fixed |Δ| ≤ 50%; **fail** only beyond 50% or structural (schema,
   team_id, `measured_on` ≠ participant_laptop/audit_cloud_vm, zero/missing values).
   Delta is computed relative to the *submission* value. Accuracy is never delta-checked.
   The old "beyond 2× tolerance" framing under-stated the flag band for memory.
5. **`-ngl 0` is now pinned** in the profiler's llama-bench call (cf3432cf had no `-ngl`),
   and TTFT is `n_prompt/pp_rate`, not `1/pp_rate`. Still no `-t` — the binary's default
   thread count rules (llama-bench = physical/P cores; cgroup-oblivious in Docker).
6. **Correction, 2026-08-19: there is no sourced 6 August clarification.** The public
   challenge page says cohort-relative `100·TPS/TPS_max`, but the official profiler README
   and executable code use `min(TPS/15, 1)·100`. The profiler also describes audit mode as
   running in secure cloud VMs. Until ADTF publishes a versioned resolution, campaign
   decisions use the profiler implementation: fixed 15 tok/s, capped.
7. **Deadline**: devpost says Aug 24, 2026 23:45 PDT; the site says Aug 25. Treat Aug 24
   as binding. `>7 GB peak RSS = disqualification (S_total = 0)`, per the official page.

Strategy consequence: **the submitted GGUF file is the only lever the scored path sees**
(model, quant recipe, file size). Self-reported TPS/RSS must be rehearsed through the exact
b10175 reference image/binary; AVX2 laptop measurements remain a separately labelled product
proxy, not the audit score-of-record. See
`bench/.artifacts/campaign-20260805.md` for the running bake-off.

---

## The six questions

### 1. Does the profiler measure raw model TPS or end-to-end system TPS? — **RAW**

The roadmap called this "the highest-value unknown in the project."

[`throughput.py`](https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler/blob/cf3432cf54216617429cf3f9d3d7150fb891fdd1/src/adtc_profiler/throughput.py)
shells out to **`llama-bench`** against the GGUF file:

```
llama-bench -m <model.gguf> -p 512 -n 128 --output json
```

> "Wrap llama.cpp's `llama-bench` to produce throughput numbers in the schema's shape."

No HTTP, no server, no orchestrator, no tokenizer round-trip through our code. **The scored
throughput never touches our product.**

**Consequence:** SymPy routing, RAG, self-consistency and every millisecond of orchestration
overhead cost **zero** `S_perf`. The roadmap's premise — that `profile.py` measures "end-to-end
through the product (what gets scored)" and that the profile-vs-bench gap "is worth 12 points
of `S_perf`" — does not hold. That gap is a product-UX metric, not a scoring metric.

### 2. Is TPS_max fixed at 15, or set by the fastest submission? — **PUBLICLY CONTRADICTORY; USE PROFILER 15**

Official challenge page, on `S_perf`:

> "TPSact: actual tokens/sec during audit · **TPSmax: highest speed across all submissions**"

The official profiler README and code instead implement:

> `min(TPS / TPS_REFERENCE, 1.0) * 100`, with `TPS_REFERENCE = 15.0`

No public dated organiser reply resolves the conflict. The old 6 August repository entry
claiming one existed has no link, quote, email, or issue reference; later project research
correctly marked the question unresolved. **Decision:** match the executable profiler. Below
15 tok/s, one tok/s contributes 2.00 total points and 1 GB costs 2.86 points; at and above
15, further speed contributes zero under this rule.

### 3. Is peak RAM RSS or PSS? Whole tree or single PID? — **RSS, WHOLE TREE**

[`memory.py`](https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler/blob/cf3432cf54216617429cf3f9d3d7150fb891fdd1/src/adtc_profiler/memory.py):

```python
family = [root] + root.children(recursive=True)
rss = sum(p.memory_info().rss for p in family if p.is_running())
```

- **RSS**, via `psutil` — **not PSS**. There is no `smaps_rollup` read anywhere in the repo.
- **Whole process tree**, recursive. (Roadmap correct here.)
- Sampled every **0.1 s**; peak = max observed; steady-state = mean of the last 60 s (or last
  half if the run is under 120 s). Both are reported: `peak_rss_mb`, `steady_state_rss_mb`.
- It samples around a **subprocess it launches** — `sample_during()` wraps a `llama-bench` /
  `llama-cli` invocation.

**Consequence:** the roadmap's instruction to treat **PSS** as the number of record
(`CLAUDE.md`: "Measure peak RAM as PSS … because `mmap` makes RSS misleading") optimizes a
metric nobody scores. The `mmap` reasoning is *technically correct* — file-backed model pages
inflate RSS above true pressure — but the competition scores RSS anyway, so RSS is the number
to minimise. Keep measuring PSS for diagnosis; report and optimise RSS.

### 4. Is prefill scored, or only decode? — **DECODE ONLY**

[`throughput.py`](https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler/blob/cf3432cf54216617429cf3f9d3d7150fb891fdd1/src/adtc_profiler/throughput.py):

> "throughput.tokens_per_second_generation -> **tg row's avg_ts**"
> "throughput.first_token_latency_ms -> approximated from pp row's avg_ts"

The scored figure is the generation row. Prompt-processing only *approximates* TTFT, and TTFT
is not a term in `S_total`.

**Consequence:** prefill optimisations do not move the score directly. They remain worth doing
for felt latency, but they are a product decision, not a scoring one.

### 5. What triggers the thermal flag? — **PEAK SAMPLE, AND IT MAY NOT EXIST**

[`thermal.py`](https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler/blob/cf3432cf54216617429cf3f9d3d7150fb891fdd1/src/adtc_profiler/thermal.py):

> "CPU utilization (p99) + best-effort core temperature.
> **Cloud VMs typically do not expose host thermal sensors — schema allows `core_temp_c_peak`
> to be null.** CPU percent is always available via psutil."

Samples at 0.5 s, matches sensor labels (`core`, `cpu`, `tdie`, `tccd`, `package`), takes
`max()` — an **instantaneous peak**, not a sustained average. Penalty condition per the
official page: "core temperature exceeds 85°C or thermal throttling is detected."

**Consequence:** the roadmap treats temperature as a wall ("RAM is a linear dial; temperature
is a wall") and caps threads to avoid a −10 cliff. If the audit runs on a cloud VM with null
temperature, **that cliff may be unreachable and the thread cap may be costing throughput for
nothing.** Not proven — the audit environment is an open question below — but the thread-cap
decision now rests on an assumption worth testing rather than a fact.

### 6. What is in the validation set? Is a sample published? — **HIDDEN 30% SUBSET**

[`comparator.py`](https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler/blob/cf3432cf54216617429cf3f9d3d7150fb891fdd1/src/adtc_profiler/comparator.py):

> "participant accuracy is on public benchmarks; audit accuracy is on the **hidden 30%
> subset**. The comparator passes audit accuracy through as-is for judge review rather than
> diffing."

[`accuracy.py`](https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler/blob/cf3432cf54216617429cf3f9d3d7150fb891fdd1/src/adtc_profiler/accuracy.py)
runs **lm-evaluation-harness** directly against the GGUF:

```python
def run_benchmark(model_path, *, task="arc_easy", limit=50, ...)
```

> "Run lm-evaluation-harness against the model and project to the schema's accuracy block."

No sample of the hidden subset is published. `arc_easy` is the profiler's smoke-test default,
**not** a statement that ARC is the audit task.

**Consequence — the largest one here.** The profiler's `S_acc` is an lm-eval score on the raw
GGUF. **Our tutoring layer — Socratic prompts, personas, RAG grounding, SymPy verification —
is invisible to it.** The ROADMAP's expanded reading (that "the pedagogy work in Phase 4 feeds
the 50%-weighted term, not merely the 10-point African Use Case bonus") is not supported by
the profiler's code. Pedagogy may still matter to the human judges and the report; it does not
move the number this tool computes.

---

## Contradictions (read this)

Four load-bearing roadmap assumptions the evidence does not support. **No decision is taken
here** — recording, not re-deciding.

| Roadmap says | Evidence says | What it puts at risk |
|---|---|---|
| `S_acc` (50%) is *tutoring quality*, so Phase 4 pedagogy feeds the heaviest term | `accuracy.py` = lm-eval on the GGUF; the product is never invoked | The strategic case for Phase 4's weighting. Pedagogy is likely a judging/report asset, not a profiler-score asset |
| Measure and report peak RAM as **PSS** | Profiler reads **RSS**; no `smaps_rollup` anywhere | Optimising an unscored metric. RSS ≥ PSS with `mmap`, so we'd under-report our own scored number |
| Profiler: cap at fixed 15; challenge page: relative to fastest submission | Both are current official public sources; no sourced clarification resolves them | Every break-even. Use the executable profiler for decisions and label webpage-relative numbers sensitivity-only |
| `profile.py` measures "end-to-end through the product (**what gets scored**)"; the profile-vs-bench gap is worth ~12 pts | `llama-bench` *is* the scored path | Effort spent shaving orchestration overhead for `S_perf` points that don't exist |

One more, not a contradiction but a gap: the roadmap plans a single **12 Aug** submission. The
real structure is three gates (below).

---

## Dates — the roadmap's timeline does not match the official one

Official challenge page:

| Gate | Date |
|---|---|
| **Gate 1 — Submission** | **Due August 25, 2026** |
| **Gate 2 — Activities & Audit** | **September 8 – September 29, 2026** |
| **Gate 3 — Final Package** | **Due October 17, 2026** |

`ROADMAP.md` and `CLAUDE.md` are built on a single deadline of **Wed 12 Aug 2026**, with
"Sprint 1–5" framed as *post-competition* work from 13 Aug onward. Those sprints in fact fall
**inside** the competition, across Gates 2 and 3.

Not rescheduled here — flagged for a deliberate call. Note the possible upside: Gate 1 is 13
days later than the roadmap assumes, and the audit window is a further two weeks out.

> One unresolved conflict: a secondary source (CompeteHub) lists a Gate 1 deadline of **July
> 24, 2026**. The official page says August 25. Treat August 25 as authoritative and confirm by
> email — if July 24 were right, it is 8 days away and everything changes.

---

## The audit mechanic — our numbers get re-run

From [`comparator.py`](https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler/blob/cf3432cf54216617429cf3f9d3d7150fb891fdd1/src/adtc_profiler/comparator.py):
participants self-report a `submission.json`; auditors produce an `audit.json`; the comparator
diffs them field by field.

| Field | Tolerance |
|---|---|
| `memory.peak_rss_mb` | ±15% |
| `memory.steady_state_rss_mb` | ±15% |
| `throughput.tokens_per_second_generation` | ±25% |
| `throughput.first_token_latency_ms` | ±25% |

Verdict ladder: **pass** (all inside tolerance) · **flag** (outside, but within 2×) · **fail**
(beyond 2× tolerance, or structural — missing fields, schema-invalid, `team_id` mismatch).

**Consequence, and it is a design constraint rather than a reporting note:** a number we
cannot reproduce on someone else's hardware is worse than no number. An optimistic
`tokens_per_second_generation` that misses by 2× is a **fail**, not a lower score. This is why
`bench/profile.py` gets a mode that mirrors the official methodology exactly, instead of
trusting our own harness to agree with theirs.

Report schema top-level keys (`schema/adtc-profiler.schema.json`, `additionalProperties:
false`): `schema_version`, `profiler_version`, `submission`, `environment`, `throughput`,
`memory`, `accuracy`, `cpu_thermal`, `reproducibility`, `model_info`.
Required: `throughput.{tokens_per_second_generation, first_token_latency_ms}`,
`memory.{peak_rss_mb, steady_state_rss_mb}`.

Useful alignment: the profiler expects **GGUF via llama.cpp** and locates `llama-bench` **on
`PATH`** — our stack is already the right shape, though our binary lives in
`runtime/build/bin` rather than on `PATH`.

---

## Still open — worth an email

The source settles measurement; it does not settle process. Send to
`africadeeptechcommunity@gmail.com`:

1. **Does the audit run the *product*, or only the GGUF?** If only the GGUF, the gateway/RAG
   RAM never counts against the 7 GB and the architecture's RAM story changes completely. The
   single highest-value remaining unknown.
2. **Which lm-eval tasks make up the hidden 30% subset?** `arc_easy` is a profiler default, not
   an announcement. Decides whether the domain (math + scientific reasoning) is even what's
   measured.
3. **Is the audit on real hardware or a cloud VM?** Decides whether the thermal penalty is
   reachable at all (Q5), and therefore whether the thread cap is worth its throughput.
4. **Is `TPS_max` per-cohort or the provisional 15?** Sets every break-even in the ladder (Q2).
5. **Confirm Gate 1: August 25 vs the July 24 seen on a secondary listing.**
6. **What is the ADTC Standard Laptop's exact spec?** Referenced repeatedly; not pinned down
   here.

Until 1–4 are answered, treat conclusions drawn from them as provisional and say so in the
report.
