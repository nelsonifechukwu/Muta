# Cactus-Inspired RAM ↔ tok/s Optimizations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the transferable RAM-vs-tok/s techniques from the Cactus on-device inference engine (https://github.com/cactus-compute/cactus, surveyed 2026-08-01) into Muta as measured experiments and small product changes: a bandwidth-ceiling diagnostic, decode-thread and weight-repack probes, a lower-bit quantization bake-off centered on the embedding/output tensors (Cactus's single biggest finding), an optional mmproj requant, and a token-budgeted history trim so long dialogs degrade instead of 400ing.

**Architecture:** Nothing in Cactus's C++/NEON code can be lifted — Muta is pinned to llama.cpp `b10035` on x86-64/AVX2 (docker) and arm64 (native dev). What transfers are *decisions*: which tensors tolerate fewer bits, how many threads decode deserves, whether repacked weights earn their anonymous RAM, and how to bound long-dialog context. Each idea lands either as a `bench/native_sweep.py` experiment with a RESULTS.md verdict, or as a small change to `RuntimeConfig`/`ChatEngine` behind the existing seams. The `/v1` contract is untouched.

**Tech Stack:** Python ≥3.10, pytest, numpy (bench only), llama.cpp `b10035` (`llama-server`, `llama-quantize`, `convert_hf_to_gguf.py` from the pinned tree/release), `bench/native_sweep.py`, `scripts/fetch_models.py` + `models/pins.lock.json`.

## Global Constraints

- llama.cpp is pinned at `b10035`. Verify every flag spelling against `llama-server --help` / `llama-quantize --help` from the pinned build **before** using it; a missing flag is a *finding to record in `docs/engine-flags.md`*, not an error to work around.
- Measured-and-rejected levers are off the table without new hardware (RESULTS.md 2026-08-01 §B): speculation in every form on CPU, `--no-mmap`, `--mlock`, `-fa` + `--cache-type-v q8_0`, `-ub` > 128, `--prio 2`. Cactus ships **no speculative decoding at all** — treat that as corroboration, not a new question.
- The exchange rate governs verdicts (`bench/optimization-log.md`): at the provisional `TPS_max = 15`, 1 GB = 1.43 tok/s. RAM-spending changes must clear `ΔTPS ≥ 1.43 × ΔRAM_GB`; zero-RAM speedups and free RAM cuts are strictly dominant. Record the `tps_max` each row was scored against.
- Every configuration change lands with a same-day `RESULTS.md` entry (exact config + measured numbers + hardware context). No entry, no change. Scored ablations also get a `bench/optimization-log.md` row. Mac numbers (native or emulated) are tagged `dev_host_provisional`.
- macOS RAM readings: `phys_footprint` (`/usr/bin/footprint <pid>`), never sampled RSS (`docs/engine-flags.md`). A/B comparisons are interleaved runs, one variable at a time.
- Model provenance: no new artifact ships without a `models/pins.lock.json` entry (exact HF revision, sha256 verified twice) and licence capture. Locally-quantized derivatives (Tasks 5, 6) are documented in `docs/model-provenance.md` with the exact recipe + output sha256; they do NOT enter `models/core/` — swapping the shipped model is a decision for the user, plans only park a recommendation.
- The `/v1` contract is untouched: no edits under `contracts/`, no `make contract` run needed.
- `make lint` (`ruff check .`) before every commit. Store-backed tests need the compose db (`docker compose up -d db`) and skip when it is down.
- `ui/app.js` and `ui/styles.css` have unrelated uncommitted changes — never `git add -A`; stage files explicitly.

## Survey → task map

| Cactus idea (evidence) | Verdict for Muta | Task |
|---|---|---|
| Decode is bandwidth-bound; they publish "% of theoretical ceiling" (140/169 tok/s = 83% on iPhone 17 Pro) and stop tuning when near it | Adopt as a diagnostic + x86-target predictor | 2 |
| GEMV/decode gets ≤4-5 threads on macOS, 1 on Android (`cactus-kernels/src/threading.h`, `GemmThreading`) — more threads only add sync cost | Probe decode threads *below* the P-core count | 3 |
| "Stream weights from storage, accept −17% decode, gain evictable RAM + no OS throttling" (lfm2.5_350m blog) | Our analog: the ~1.3 GiB AVX2/arm `CPU_REPACK` anonymous copy — probe disabling it, if the pin has a flag | 3 |
| Embeddings are gather-only and tolerate 2-bit (TurboQuant-H: PLI 8→2.125 bits, +0.06 PPL, −40% model); output head is sensitive (forced 4-bit) | Qwen3.5's 248,320-token vocab makes `token_embd`/`output` our biggest tensors — requant grid | 5 |
| Mixed-precision by tensor sensitivity: CQ3.26 (~3.3 bpw) near-lossless, uniform sub-3-bit collapses GSM8K 73.67→22.00 | Bake off Unsloth UD (dynamic per-tensor) and small-4-bit GGUFs; math probes are the canary | 4 |
| Vision/audio towers quantize gracefully to low bits (2-bit vision holds MMMU 27.9 vs <7 for baselines) | mmproj F16 (0.626 GiB) → Q8_0 locally; vision is TTL-reaped so this cuts the *peak* during vision requests | 6 |
| Rolling KV compaction, default ON: at 4096 tokens compact to 2048 keeping sink-4 + recent 30% + top-KeyDiff rows | Engine-internal at our pin; the product-layer analog is a token-budgeted history trim + the parked `n_ctx` 4096 decision | 7 |
| KV cache floor at INT8 "to ensure correctness"; below INT4 small models degrade | Validates shipped `--cache-type-k q8_0` / f16-V. No task. | — |
| mmap + page-cache weights, `MADV_DONTNEED` on idle; benchmark peak sampled per decoded token, warmup run discarded, mean of 3 | llama.cpp already mmaps; `native_sweep`'s 25 ms sampler ≈ per-token at our speeds. No task. | — |
| Prefix/prompt caching across requests | llama.cpp checkpoint restore already covers this (29/33 reuse). No task. | — |
| Confidence probe → cloud handoff | No cloud in an offline product; the local two-tier analog (0.8B hint mode) is TDD §7.6, already parked behind D2-b. No task. | — |

---

### Task 1: Externalize the survey — `docs/cactus-survey.md`

**Files:**
- Create: `docs/cactus-survey.md`

**Interfaces:**
- Consumes: nothing.
- Produces: the reference doc later tasks cite in commit messages and RESULTS.md entries.

- [ ] **Step 1: Write the doc**

Create `docs/cactus-survey.md` with exactly this content:

```markdown
# Cactus survey — what transfers to Muta and what doesn't (2026-08-01)

Cactus (https://github.com/cactus-compute/cactus, YC S25) is an ARM/mobile-first
on-device inference engine: custom rotation+codebook quantization (CQ1–CQ4 +
mixed-precision CQ2.54/CQ3.26), a zero-copy computation graph, NEON/I8MM kernels,
INT8 KV cache, and cloud handoff gated by a learned confidence probe. Muta is pinned
to llama.cpp b10035 on x86-64/AVX2 — none of the code transfers; these decisions do.
Implementation: docs/plans/2026-08-01-cactus-inspired-ram-toks-optimizations.md.

## Transferable decisions

1. **Bandwidth-ceiling math.** CPU decode streams ~the whole weight file per token.
   Cactus reports % of `bandwidth / bytes-per-token` (iPhone 17 Pro: 140 of 169
   theoretical tok/s = 83%) and stops thread-tuning near the ceiling. Muta tool:
   `bench/ceiling.py`. Also predicts x86-target decode from the box's bandwidth
   before we ever touch it.
2. **Decode wants few threads.** Their GEMV (decode) path caps at 4–5 threads on
   macOS, 2 on iOS, 1 on Android — sync overhead beats bandwidth wins. Matches our
   measured barrier-synchronization fragility (RESULTS.md 2026-08-01); motivates
   probing below the P-core count.
3. **Evictable weights vs speed.** They deliberately keep weights file-backed
   (mmap, MADV hints) and accept −17% decode so the OS can evict under pressure.
   Muta's analog: llama.cpp's CPU_REPACK copies ~1.3 GiB of the 4B into anonymous
   RAM for AVX2/NEON kernels — a repack-off probe prices that trade.
4. **Embeddings tolerate low bits; the output head doesn't.** Embedding rows are
   gathered, not matmul'd — TurboQuant-H runs per-layer embeddings at 2.125 bits
   for +0.06 PPL and −40% model size. Their production recipe: embeddings 2-bit,
   LLM linears 4-bit, output head pinned at 4-bit. Qwen3.5-4B's 248,320-token
   vocab makes token_embd/output the largest tensors in our GGUF — llama-quantize's
   --token-embedding-type/--output-tensor-type is the direct analog.
5. **Mixed precision beats uniform.** "The marginal value of a bit is sharply
   non-uniform across tensors": CQ3.26 (~3.3 bpw, 68 sensitive tensors at 4-bit)
   is near-lossless while uniform 2-bit zeroes GSM8K. GGUF-ecosystem analog:
   Unsloth UD dynamic quants. Generation-heavy math tasks collapse FIRST —
   accuracy probes for any lower-bit candidate must be generative math, not MCQ.
6. **Bound long-context RAM by construction.** Their KV compaction (default on)
   caps the cache at 4096→2048 (sink-4 + recent 30% + top-KeyDiff). At our pin the
   product-layer analog is a token-budgeted history trim in ChatEngine (drop whole
   oldest turns; keep the suffix stable so checkpoint LCP reuse survives).

## Decisions Cactus validates (no change needed)

- KV at INT8, not lower: "models significantly degrade when KV cache goes below
  INT4. We keep KV at INT8 to ensure correctness" — matches our q8_0-K/f16-V.
- No speculative decoding on CPU: Cactus ships none ("No speculative decode or
  MTP, pure decode"); our 07-31/08-01 measurements found every form net-negative.
- mmap'd weights (they measured Android's mmap-degraded-to-malloc costing 4–6×
  RAM vs Apple); our --no-mmap probe was −28% decode +1 GiB. Settled.
- Prompt-prefix reuse across turns: they re-prefill only the token suffix; our
  checkpoint restore already does this (29/33 reuse).
- On-demand vision encoder: they load/run/unload per request; our TTL-reaped
  vision server is the same idea with a 120 s grace.
- Benchmark hygiene: warmup run discarded, mean of 3, peak RAM sampled inside the
  decode loop, Apple phys_footprint vs Linux RSS named per-platform — all already
  native_sweep practice.

## Not applicable / rejected

- CQ/TurboQuant-H formats themselves, NEON kernels, zero-copy graph internals,
  Metal paths: engine-internal, ARM-only, unreachable at our pin.
- Confidence-probe cloud handoff: no cloud offline. The local analog (draft model
  serving instant hints) is TDD §7.6, parked behind the D2-b admission rule.
- KV-cache start-small-and-double, sliding-window ring, KeyDiff compaction:
  llama.cpp b10035 allocates -c up front and has no compaction hook; revisit only
  on a pin move.
- Single-core decode for OS-throttle stealth: a phone/background concern; the
  tutor box is foreground and plugged in.
```

- [ ] **Step 2: Commit**

```bash
git add docs/cactus-survey.md
git commit -m "docs: cactus survey — transferable RAM/tok-s decisions, validations, rejections"
```

---

### Task 2: Bandwidth-ceiling diagnostic — `bench/ceiling.py`

**Files:**
- Create: `bench/ceiling.py`
- Test: `bench/test_ceiling.py`

**Interfaces:**
- Produces: `ceiling_tps(bandwidth_bytes_s: float, bytes_per_token: float) -> float`; `measure_copy_bandwidth_bytes_s(size_mib: int = 512, passes: int = 5) -> float`; CLI `python -m bench.ceiling --model <gguf> [--measured <tok/s>] [--bandwidth-gib-s <override>]`. Tasks 3 and 4 cite its output in RESULTS.md entries.

- [ ] **Step 1: Write the failing test**

Create `bench/test_ceiling.py`:

```python
"""Ceiling math is pure arithmetic — test it exactly; smoke the bandwidth probe."""

from bench.ceiling import ceiling_tps, measure_copy_bandwidth_bytes_s


def test_ceiling_tps_exact():
    # 60 GB/s over a 355 MB model -> the cactus blog's ~169 tok/s iPhone ceiling.
    assert round(ceiling_tps(60e9, 355e6), 0) == 169


def test_ceiling_tps_zero_guard():
    assert ceiling_tps(60e9, 0) == float("inf")


def test_bandwidth_probe_returns_plausible_number():
    # 64 MiB keeps the test fast; any machine that can run the stack moves >1 GiB/s.
    bw = measure_copy_bandwidth_bytes_s(size_mib=64, passes=2)
    assert bw > 2**30
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python3 -m pytest bench/test_ceiling.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bench.ceiling'`.

- [ ] **Step 3: Write the implementation**

Create `bench/ceiling.py`:

```python
"""Decode-throughput ceiling from memory bandwidth (cactus-inspired diagnostic).

CPU decode of a dense GGUF is memory-bandwidth-bound: each generated token streams
essentially the whole weight file once. Cactus publishes "% of theoretical ceiling"
per device (iPhone 17 Pro: 140 measured of ~169 theoretical tok/s = 83%, from
~60 GB/s over a 355 MB model) and uses it to decide when thread tuning is DONE.

    python -m bench.ceiling --model models/core/Qwen3.5-4B-Q4_K_M.gguf --measured 31.1

bytes/token = the model file size. Assumptions stated so the number is honest:
- the AVX2/arm repacked copy is the same bytes, read once per token;
- attention-KV reads at -c 2048 on this hybrid (~24.5 KiB/token) are <2% and ignored;
- the 50 MiB SSM state is re-read per token but is likewise ~2% of 2.5 GiB.
So the ceiling is OPTIMISTIC by a few percent — good enough for "keep tuning or stop",
and for predicting the x86 target box's decode from its bandwidth before we have it.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path


def ceiling_tps(bandwidth_bytes_s: float, bytes_per_token: float) -> float:
    if bytes_per_token <= 0:
        return float("inf")
    return bandwidth_bytes_s / bytes_per_token


def measure_copy_bandwidth_bytes_s(size_mib: int = 512, passes: int = 5) -> float:
    """Best-of-N large-copy bandwidth (reads + writes counted, STREAM-copy style).

    numpy memcpy underestimates true peak DRAM bandwidth somewhat; that bias makes
    the resulting ceiling conservative, which is the safe direction for a stop rule.
    """
    import numpy as np

    a = np.ones(size_mib * 2**20 // 8, dtype=np.float64)
    b = np.empty_like(a)
    best = 0.0
    for _ in range(passes):
        t0 = time.perf_counter()
        np.copyto(b, a)
        dt = time.perf_counter() - t0
        best = max(best, 2 * a.nbytes / dt)
    return best


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ceiling", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", type=Path, required=True, help="GGUF whose size = bytes/token")
    p.add_argument("--measured", type=float, default=None, help="measured decode tok/s to grade")
    p.add_argument("--bandwidth-gib-s", type=float, default=None,
                   help="skip the probe and use this bandwidth (e.g. the x86 target's spec sheet)")
    args = p.parse_args(argv)

    bytes_per_token = args.model.stat().st_size
    bw = (args.bandwidth_gib_s * 2**30) if args.bandwidth_gib_s else measure_copy_bandwidth_bytes_s()
    ceil = ceiling_tps(bw, bytes_per_token)

    print(f"model            {args.model}  ({bytes_per_token / 2**30:.2f} GiB)")
    print(f"bandwidth        {bw / 2**30:.1f} GiB/s" + ("  (asserted)" if args.bandwidth_gib_s else "  (measured copy)"))
    print(f"ceiling          {ceil:.1f} tok/s")
    if args.measured is not None:
        print(f"measured         {args.measured:.1f} tok/s  ({100 * args.measured / ceil:.0f}% of ceiling)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest bench/test_ceiling.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Run it for real and record the number**

```bash
python3 -m bench.ceiling --model models/core/Qwen3.5-4B-Q4_K_M.gguf --measured 31.1
```

Record the printed ceiling and %-of-ceiling in a RESULTS.md entry (hardware context `native`, tag `dev_host_provisional`), plus the *predicted x86-target decode*: rerun with `--bandwidth-gib-s <target box's spec>` once known. Interpretation rule to state in the entry: ≥70% of ceiling → thread/flag tuning is done, only smaller weights help; ≤40% → decode is not bandwidth-limited here, keep looking at threading/kernels.

- [ ] **Step 6: Commit**

```bash
git add bench/ceiling.py bench/test_ceiling.py RESULTS.md
git commit -m "bench: bandwidth-ceiling diagnostic (cactus % -of-ceiling rule) + measured native row"
```

---

### Task 3: Cheap native probes — decode-thread floor and repack toggle

**Files:**
- Modify: `bench/native_sweep.py` (the `CONFIGS` dict, around line 278)
- Modify: `docs/engine-flags.md` (record the repack-flag finding either way)

**Interfaces:**
- Consumes: `run_config(name, extra, suite=...)` and the `CONFIGS: dict[str, tuple[list[str], str]]` table in `bench/native_sweep.py`; `_T6` is the existing `["--threads", "6", "--threads-batch", "6"]` base (verify its exact spelling at the top of the CONFIGS block before reusing).
- Produces: RESULTS.md + optimization-log verdicts on `T4/T5-DECODE` and `WINNER-NOREPACK`.

- [ ] **Step 1: Discover the repack flag at this pin**

```bash
runtime/build/bin/llama-server --help 2>&1 | grep -iE "repack|extra.buf" || echo "NO REPACK FLAG AT b10035"
```

Record the exact spelling (or its absence) in `docs/engine-flags.md` under a new heading `## Weight repacking (CPU_REPACK) and whether it can be disabled`, citing the existing fact that load repacks ~1.3 GiB of the 4B into anonymous RAM. If there is **no** flag, delete the `WINNER-NOREPACK` config from Step 2 and state in the doc that the cactus "stream weights, lose some decode" trade is unreachable at this pin.

- [ ] **Step 2: Add the probe configs**

In `bench/native_sweep.py`, append to `CONFIGS` (using the repack spelling found in Step 1 — `--no-repack` below is a placeholder for whatever `--help` printed):

```python
    # Cactus GEMV policy: their macOS decode path caps at 4-5 threads even on big
    # cores (sync overhead beats bandwidth once saturated). Decode here is
    # barrier-synchronized; probe below the P-core count.
    "T4-DECODE": (["--threads", "4", "--threads-batch", "6",
                   "--kv-unified", "--ctx-checkpoints", "2"], "speed"),
    "T5-DECODE": (["--threads", "5", "--threads-batch", "6",
                   "--kv-unified", "--ctx-checkpoints", "2"], "speed"),
    # Cactus streams weights from storage, accepting -17% decode for evictable RAM.
    # Our analog: disable CPU_REPACK (~1.3 GiB anonymous on the 4B) — spelling from
    # `llama-server --help`, see docs/engine-flags.md.
    "WINNER-NOREPACK": (_T6 + ["--kv-unified", "--ctx-checkpoints", "2",
                               "--no-repack"], "full"),
```

- [ ] **Step 3: Run interleaved A/B against the shipped config**

```bash
python3 -m bench.native_sweep WINNER T4-DECODE WINNER T5-DECODE WINNER WINNER-NOREPACK
python3 -m bench.native_sweep T4-DECODE T5-DECODE WINNER-NOREPACK   # second round
```

Quiet host; note ambient load in the entry. Metrics: decode max + floor across the interleaved probes, prefill median, `phys_footprint` (NOREPACK's whole point — expect a large drop if weights stay file-backed; confirm via the footprint delta, and note that sampled RSS is untrustworthy here).

- [ ] **Step 4: Verdicts + journal**

Decision rules, stated in advance:
- `T4/T5-DECODE`: keep (flip the darwin thread derivation in `runtime/config.py:darwin_performance_cores` usage to `min(pcores, N)`) only if max ≥ WINNER's max AND the loaded-host floor improves. Otherwise record as rejected.
- `WINNER-NOREPACK`: price it with the exchange rate (`ΔTPS ≥ 1.43 × ΔRAM_GB` at tps_max 15) *and* note the caveat that the competition profiler may run `llama-bench` with its own flags — a repack-off win may be product-RAM-only. Park the ship decision with both numbers if it's close.

Same-day RESULTS.md entry (context `native`, `dev_host_provisional`) + one optimization-log row per lever. If a keep-verdict changes `runtime/config.py`, update the field comment with the measured numbers, and re-run `python3 -m pytest runtime/tests/test_server_command.py -v` (expected: PASS).

- [ ] **Step 5: Commit**

```bash
git add bench/native_sweep.py docs/engine-flags.md RESULTS.md bench/optimization-log.md
git commit -m "bench: decode-thread floor + repack-off probes (cactus GEMV/stream-weights analogs), measured verdicts"
```

---

### Task 4: Quantization bake-off — mixed-precision candidates through the sweep

**Files:**
- Modify: `scripts/model_specs.py` (append two `Artifact`s to `QUANT_VARIANTS`, after line 405)
- Modify: `bench/native_sweep.py` (`run_config` model override ~line 185, `ACCURACY` list ~line 63, CLI ~line 312)
- Modify: `models/pins.lock.json` (via the fetch flow, not by hand)

**Interfaces:**
- Consumes: `Artifact` dataclass and `QWEN_LICENSE` from `scripts/model_specs.py`; `GiB` constant; fetch via `--quant-variants` (already plumbed in `scripts/fetch_models.py:421-490`).
- Produces: `run_config(name, extra, *, suite="speed", model: Path | None = None)` — Task 5 reuses this override; four extra generative-math `ACCURACY` probes all later tasks inherit.

- [ ] **Step 1: Add the two candidate specs**

Append to `QUANT_VARIANTS` in `scripts/model_specs.py`:

```python
    Artifact(
        name="core-cand-unsloth-ud-q3kxl",
        role="D1 candidate: Unsloth dynamic UD-Q3_K_XL (~3.5 bpw, per-tensor mixed)",
        tier="on-demand",
        repo="unsloth/Qwen3.5-4B-GGUF",
        file="Qwen3.5-4B-UD-Q3_K_XL.gguf",
        dest="models/core/candidates",
        license=QWEN_LICENSE,
        planning_bytes=int(2.1 * GiB),
        flag="--quant-variants",
        caveats=(
            "Cactus CQ3.26 evidence (docs/cactus-survey.md): mixed ~3.3 bpw held "
            "GSM8K/HumanEval near-lossless while uniform sub-3-bit collapsed GSM8K "
            "73.67 -> 22.00. Generative math probes are the admission gate, not MCQ.",
        ),
    ),
    Artifact(
        name="core-cand-iq4xs",
        role="D1 candidate: IQ4_XS (~4.25 bpw, smallest mainline 4-bit)",
        tier="on-demand",
        repo="unsloth/Qwen3.5-4B-GGUF",
        file="Qwen3.5-4B-IQ4_XS.gguf",
        dest="models/core/candidates",
        license=QWEN_LICENSE,
        planning_bytes=int(2.3 * GiB),
        flag="--quant-variants",
    ),
```

Filename caveat: if `scripts/fetch_models.py` reports a 404, list the repo's actual GGUF filenames (`https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/tree/main`), correct `file=` to the exact spelling, and only then pin. Never substitute a different repo silently (T2 hard rule).

- [ ] **Step 2: Teach the sweep a model override**

In `bench/native_sweep.py`:

1. Change the signature at ~line 185: `def run_config(name: str, extra: list[str], *, suite: str = "speed", model: Path | None = None) -> dict:` and at the top of the body:

```python
    flags = list(BASE_FLAGS)
    if model is not None:
        flags[flags.index("--model") + 1] = str(model)
```

(then use `flags + extra` wherever the body used `BASE_FLAGS + extra`), and include `"model": str(model or MODEL)` in the JSONL result row.

2. CLI (in `main`, ~line 315): add `parser.add_argument("--model", type=Path, default=None, help="override the swept GGUF (bake-off candidates)")` and pass `model=args.model` through to `run_config`.

3. Append to `ACCURACY` (generation-heavy math — the canary that collapses first under bit starvation, per the survey):

```python
    ("A shop sells pens at 3 for 450 naira. How much do 7 pens cost in naira? Give only the number.", ["1050"]),
    ("Solve for x: 2x + 7 = 19. Give only the number.", ["6"]),
    ("What is 15% of 240? Give only the number.", ["36"]),
    ("A car travels at 72 km/h. How many metres does it cover in 25 seconds? Give only the number.", ["500"]),
```

- [ ] **Step 3: Verify the harness change does not disturb the reference**

Run: `python3 -m bench.native_sweep WINNER` (no `--model`) and confirm the JSONL row carries `"model": ".../models/core/Qwen3.5-4B-Q4_K_M.gguf"` and decode/accuracy are in line with the 08-01 record (max ~29–31 tok/s on a quiet host, accuracy 8/8 with the extended probes — if a NEW probe fails on the *shipped* model, fix or drop that probe before judging any candidate with it).

- [ ] **Step 4: Fetch and pin the candidates**

```bash
python3 scripts/fetch_models.py --quant-variants
python3 scripts/verify_models.py
```

(Invocation spelling per RUN.md if it differs.) Disk note: the set includes the 7.85 GiB BF16 source (also needed by Task 5); ensure ~13 GiB free. Commit the `models/pins.lock.json` delta this produces.

- [ ] **Step 5: Sweep every candidate, interleaved with the reference**

```bash
for M in models/core/candidates/*.gguf; do
  case "$M" in *BF16*) continue;; esac   # source artifact, not a candidate
  python3 -m bench.native_sweep WINNER                       # reference re-anchor
  python3 -m bench.native_sweep WINNER --model "$M"
done
```

Per candidate record: file GiB, decode max, prefill median, stressed `phys_footprint`, accuracy 8/8-or-not, and `bench/ceiling.py --model "$M" --measured <its decode>` (smaller file ⇒ higher ceiling ⇒ decode should RISE if we are bandwidth-bound; if it doesn't, say so — that is evidence we're compute-bound on this host and the x86 verdict may differ).

- [ ] **Step 6: Verdict table + journal**

RESULTS.md entry with the full table and exchange-rate scoring (state `tps_max=15` and that RAM here is file-driven footprint). Admission gate: accuracy 8/8 — a candidate that drops ANY generative-math probe is rejected regardless of RAM/speed (cactus cliff evidence). The shipped-model swap is **parked as a recommendation** — moving a winner into `models/core/` changes provenance-of-record and is the user's call. Optimization-log rows tagged `dev_host_provisional; x86 re-run required`.

- [ ] **Step 7: Commit**

```bash
git add scripts/model_specs.py bench/native_sweep.py models/pins.lock.json RESULTS.md bench/optimization-log.md
git commit -m "bench: quant bake-off — UD-Q3_K_XL + IQ4_XS candidates, sweep model override, generative-math probes"
```

---

### Task 5: Embedding/output-tensor requant grid (the TurboQuant-H analog)

**Files:**
- Modify: `docs/model-provenance.md` (recipe + hashes for local derivatives)
- Uses: `models/core/candidates/Qwen3.5-4B-BF16.gguf` (fetched in Task 4), `bench/native_sweep.py --model` (Task 4), pinned `llama-quantize`.

**Interfaces:**
- Consumes: `run_config(..., model=...)` from Task 4; the extended `ACCURACY` probes.
- Produces: up to four local GGUFs under `models/core/candidates/local/` + their measured rows. Nothing enters `models/core/`.

- [ ] **Step 1: Locate the pinned llama-quantize**

```bash
ls runtime/build/bin/ | grep -i quantize || echo MISSING
```

If missing: the pinned `b10035` release archive that `run.sh --native` provisions contains `llama-quantize` — extract it next to `llama-server` (same archive, same pin; note the sha of the archive in the provenance doc). Then confirm the flags exist at this pin:

```bash
runtime/build/bin/llama-quantize --help 2>&1 | grep -E "token-embedding-type|output-tensor-type"
```

If either flag is absent, record that in `docs/engine-flags.md` and stop this task (finding, not failure).

- [ ] **Step 2: Establish whether the embeddings are tied**

```bash
python3 - <<'EOF'
from gguf import GGUFReader
r = GGUFReader("models/core/candidates/Qwen3.5-4B-BF16.gguf")
names = {t.name for t in r.tensors}
for n in ("token_embd.weight", "output.weight"):
    print(n, "PRESENT" if n in names else "ABSENT")
for t in r.tensors:
    if t.name in ("token_embd.weight", "output.weight"):
        print(t.name, list(t.shape), t.tensor_type)
EOF
```

Two branches, decided by `output.weight`:
- **PRESENT (untied):** full grid below. Cactus evidence: embedding tensor tolerates aggressive bits (gather-only); the output head is sensitive — go one step at a time on it.
- **ABSENT (tied):** one shared matrix serves both roles → `--output-tensor-type` has nothing to hit and lowering `--token-embedding-type` hurts the head too. Shrink the grid to `q4_k` embd only (vs the Q6_K-ish default) and expect little headroom; say so in the entry.

Record the tensor shapes and their byte cost in the shipped Q4_K_M (same script against `models/core/Qwen3.5-4B-Q4_K_M.gguf`) — this is the measured "how embedding-dominated are we" number the verdict cites.

- [ ] **Step 3: Build the grid**

```bash
mkdir -p models/core/candidates/local
Q=runtime/build/bin/llama-quantize
SRC=models/core/candidates/Qwen3.5-4B-BF16.gguf
D=models/core/candidates/local
$Q "$SRC" "$D/rebase-Q4_K_M.gguf" Q4_K_M 8                                       # fair baseline: OUR Q4_K_M from the same source
$Q --token-embedding-type q3_k "$SRC" "$D/embd-q3k.gguf" Q4_K_M 8
$Q --output-tensor-type q4_k "$SRC" "$D/out-q4k.gguf" Q4_K_M 8                   # untied branch only
$Q --token-embedding-type q3_k --output-tensor-type q4_k "$SRC" "$D/both.gguf" Q4_K_M 8   # untied branch only
shasum -a 256 "$D"/*.gguf
```

Add to `docs/model-provenance.md`: source pin (BF16 file + HF revision from `models/pins.lock.json`), the exact commands above, output sha256s, and the statement that these are bench-only derivatives (Qwen license permits; not shipped, not pinned).

- [ ] **Step 4: Sweep the grid**

```bash
for M in models/core/candidates/local/*.gguf; do
  python3 -m bench.native_sweep WINNER --model models/core/candidates/local/rebase-Q4_K_M.gguf
  python3 -m bench.native_sweep WINNER --model "$M"
done
```

Compare every variant against `rebase-Q4_K_M.gguf` (NOT the pinned stock file — same-source comparison isolates the tensor-type deltas). Record per variant: file GiB delta, decode delta, footprint delta, accuracy 8/8. Gate: 8/8 or reject.

- [ ] **Step 5: Verdict + journal**

RESULTS.md entry: the grid table, the embedding-dominance numbers from Step 2, exchange-rate scores, and the interaction with Task 4 (if UD-Q3_K_XL already dominates on RAM at 8/8, this grid is its cross-check — Unsloth's dynamic recipe already allocates per-tensor bits; agreement between the two is the interesting finding). Ship decision parked for the user. Optimization-log rows `dev_host_provisional; x86 re-run required`.

- [ ] **Step 6: Commit**

```bash
git add docs/model-provenance.md RESULTS.md bench/optimization-log.md
git commit -m "bench: token-embd/output-tensor requant grid vs same-source Q4_K_M rebase (TurboQuant-H analog), measured"
```

---

### Task 6 (stretch): mmproj F16 → Q8_0 — vision-request peak RAM

**Files:**
- Modify: `docs/model-provenance.md`, `scripts/model_specs.py` (the `UNRESOLVED["mmproj-q8_0"]` note, line 411)

**Interfaces:**
- Consumes: `models/core/mmproj-F16.gguf` (0.626 GiB, pinned); the running stack's `/v1/tutor/vision`; `orchestrator/telemetry.py` readings or `/usr/bin/footprint` on the vision llama-server pid.
- Produces: a local `mmproj-Q8_0.gguf` derivative + measured vision-request peak delta; an updated UNRESOLVED note pointing at the result.

- [ ] **Step 1: Route discovery (in order; first that works wins)**

```bash
# Route A — llama-quantize on the projector (expected to refuse: clip arch, not an LLM):
runtime/build/bin/llama-quantize models/core/mmproj-F16.gguf /tmp/mmproj-Q8_0.gguf Q8_0 8
# Route B — the pinned tree's converter emitting a Q8_0 projector from the pinned
# base-repo revision (models/pins.lock.json names it; ~8 GiB safetensors download):
#   python3 convert_hf_to_gguf.py <base-repo-snapshot> --mmproj --outtype q8_0 --outfile mmproj-Q8_0.gguf
```

Whichever route works, record it (command + source revision + output sha256) in `docs/model-provenance.md`; if neither works at the pin, update `UNRESOLVED["mmproj-q8_0"]` to say exactly that and stop (finding, not failure).

- [ ] **Step 2: A/B the vision request**

With the stack up (`./run.sh`), run the same image through `/v1/tutor/vision` (curl per RUN.md) against F16 and then Q8_0 (swap the file the vision command resolves — `BundlePaths.mmproj` globs `models/core/*mmproj*`; place exactly one at a time, per `_one_gguf`'s single-match rule). Record for each: peak `phys_footprint` of the vision llama-server while serving (poll `/usr/bin/footprint <pid>` at 1 Hz during the request), transcription output for a fixed set of 5 images (a printed equation, handwritten arithmetic, a diagram, a word problem photo, a low-light photo). Quality gate: transcriptions must be semantically equivalent — a wrong digit anywhere is a rejection.

- [ ] **Step 3: Verdict + journal**

Expected: ~−0.3 GiB on the vision-request peak (F16 0.626 GiB → Q8_0 ~0.33 GiB). This is transient RAM (TTL-reaped server), so score it as product-peak, not steady-state. RESULTS.md entry; ship decision (replacing the fetched F16 with a local-quant flow in `run.sh`) parked for the user. Restore the F16 file afterwards — the stack of record is unchanged until that decision.

- [ ] **Step 4: Commit**

```bash
git add docs/model-provenance.md scripts/model_specs.py RESULTS.md
git commit -m "bench: mmproj Q8_0 local-quant probe — vision-request peak RAM A/B (parked)"
```

---

### Task 7: Long-dialog degradation — token-budgeted history trim + the n_ctx 4096 decision

**Files:**
- Modify: `runtime/config.py` (after `max_history_messages`, line 128)
- Modify: `runtime/chat.py:53-60` (`_assemble`) + module top for the estimator
- Modify: `orchestrator/gateway/deps.py:53`
- Modify: `bench/native_sweep.py` (`CONFIGS`: one `WINNER-C4096` row)
- Test: `runtime/tests/test_chat.py`

**Interfaces:**
- Consumes: `ChatEngine.__init__(client, store, *, max_history_messages=20, default_system_prompt=...)`; the `store` fixture in `runtime/tests/conftest.py` (needs the compose db; skips when down).
- Produces: `RuntimeConfig.history_token_budget: int = 1200` (env `MUTA_RT_HISTORY_TOKEN_BUDGET`); `ChatEngine(..., history_token_budget: int = 0)` where `0` disables trimming (back-compat for existing tests).

- [ ] **Step 1: Write the failing tests**

Append to `runtime/tests/test_chat.py`:

```python
def test_history_trimmed_to_token_budget_oldest_first(store):
    engine, client, store = _engine(store, history_token_budget=50)
    first = engine.chat("s1", "x" * 400)  # ~101 estimated tokens: over budget on its own
    engine.chat("s1", "y" * 100, conversation_id=first.conversation_id)  # ~26 tokens
    engine.chat("s1", "what next?", conversation_id=first.conversation_id)

    sent = client.seen[2]
    contents = [m["content"] for m in sent]
    assert "x" * 400 not in contents  # oldest turn dropped, newest kept
    assert "y" * 100 in contents
    assert sent[0]["role"] == "system"  # system prompt is never trimmed
    assert sent[1]["role"] == "user"  # trimmed history still opens on a user turn
    assert sent[-1] == {"role": "user", "content": "what next?"}


def test_zero_budget_disables_trimming(store):
    engine, client, store = _engine(store)  # default history_token_budget=0
    first = engine.chat("s1", "x" * 400)
    engine.chat("s1", "next", conversation_id=first.conversation_id)
    assert "x" * 400 in [m["content"] for m in client.seen[1]]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `docker compose up -d db && python3 -m pytest runtime/tests/test_chat.py -v`
Expected: the two new tests FAIL (`unexpected keyword argument 'history_token_budget'`); existing tests PASS.

- [ ] **Step 3: Implement the trim**

`runtime/chat.py` — add near the top (after the imports):

```python
def _estimate_tokens(text: str) -> int:
    """chars/4, rounded up — a deliberate overestimate (same heuristic cactus-code's
    compaction uses). Only bounds replayed history; never touches what is stored."""
    return len(text) // 4 + 1
```

`ChatEngine.__init__`: add keyword `history_token_budget: int = 0` and store it (`self.history_token_budget = history_token_budget`).

Replace `_assemble` (lines 53-60) with:

```python
    def _assemble(self, conversation_id: str, system_prompt: str | None, message: str) -> list[Message]:
        history = self.store.get_messages(conversation_id, limit=self.max_history_messages)
        if self.history_token_budget > 0:
            # Long-dialog degradation (docs/cactus-survey.md idea 6): the engine 400s
            # prompts over the shared -c window; drop WHOLE oldest turns so the kept
            # suffix is byte-identical and checkpoint LCP reuse survives (one full
            # re-prefill right after a trim, then reuse resumes).
            spent, kept = 0, []
            for m in reversed(history):  # newest first
                cost = _estimate_tokens(m["content"])
                if spent + cost > self.history_token_budget and kept:
                    break
                spent += cost
                kept.append(m)
            history = list(reversed(kept))
            if history and history[0]["role"] == "assistant":
                history = history[1:]  # never open the replay mid-exchange
        messages: list[Message] = [
            {"role": "system", "content": system_prompt or self.default_system_prompt}
        ]
        messages += [{"role": m["role"], "content": m["content"]} for m in history]
        messages.append({"role": "user", "content": message})
        return messages
```

`runtime/config.py` — insert directly after the `max_history_messages` line:

```python
    # Token budget for replayed history (chars/4 estimate, whole-turn trim, oldest
    # first) — the engine rejects prompts over the shared -c window with a 400;
    # degradation-not-errors demands we trim BEFORE it can. 1200 leaves room for the
    # system prompt + current turn + --reasoning-budget 512 inside -c 2048. 0 disables.
    history_token_budget: int = 1200
```

`orchestrator/gateway/deps.py:53`:

```python
    return ChatEngine(
        client,
        store,
        max_history_messages=cfg.max_history_messages,
        history_token_budget=cfg.history_token_budget,
    )
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest runtime/tests/test_chat.py -v`
Expected: all PASS (old tests unaffected: `ChatEngine` default budget is 0).

- [ ] **Step 5: Measure the n_ctx 4096 half (the parked 07-31 decision)**

Add to `CONFIGS` in `bench/native_sweep.py`:

```python
    # 07-31 parked decision: -c 4096 costs ~50 MiB attention-KV on this hybrid (state
    # is per-slot, not per-token). Duplicate --ctx-size relies on last-wins parsing:
    # CONFIRM `n_ctx = 4096` in the run's engine log before trusting the row.
    "WINNER-C4096": (_T6 + ["--kv-unified", "--ctx-checkpoints", "2",
                            "--ctx-size", "4096"], "full"),
```

Run `python3 -m bench.native_sweep WINNER WINNER-C4096 WINNER WINNER-C4096`, confirm `n_ctx = 4096` in the log, and compare footprint/decode. Decision rule: if footprint costs ≤ ~+70 MiB and decode is unchanged, flip `RuntimeConfig.n_ctx` to 4096 and `history_token_budget` to 3000 (same headroom logic at the larger window); otherwise keep 2048/1200. Either way the numbers go in the entry.

- [ ] **Step 6: End-to-end degradation check**

Stack up (`./run.sh` or `make dev` + compose db), then drive one conversation past the window:

```bash
python3 - <<'EOF'
import httpx
long_turn = "Please summarize: " + "The mitochondria is the powerhouse of the cell. " * 60  # ~700 est. tokens
conv = None
with httpx.Client(base_url="http://127.0.0.1:8000", timeout=300) as c:
    for i in range(6):
        r = c.post("/v1/chat", json={"student_id": "trimtest", "message": long_turn,
                                     **({"conversation_id": conv} if conv else {})})
        r.raise_for_status()  # a 4xx/5xx here is the bug this task exists to prevent
        conv = r.json()["conversation_id"]
        print(i, r.status_code)
print("no context-overflow errors across 6 oversized turns")
EOF
```

(Route and body verified against the contract: `POST /v1/chat`, `ChatRequest{student_id, message, conversation_id?}` — `orchestrator/gateway/routes.py:134`, `contracts/models.py:55`. The assertion is simply: six oversized turns, zero non-2xx.) Also verify in the engine log that turn N+1 after a trim shows one full re-prefill and later turns resume `selected slot by LCP similarity` reuse.

- [ ] **Step 7: Adversarial review, journal, commit**

This is the plan's only product-code change on a store-adjacent path — per the working method, hand the diff to a fresh-context reviewer whose brief is "assume the trim is wrong: off-by-one at the budget edge, role alternation broken, stored history mutated, budget interacting with max_history_messages". Fix what they find. Then the same-day RESULTS.md entry (trim behavior + the C4096 numbers + the decision taken) and:

```bash
make lint
git add runtime/chat.py runtime/config.py orchestrator/gateway/deps.py runtime/tests/test_chat.py bench/native_sweep.py RESULTS.md
git commit -m "feat: token-budgeted history trim (cactus kv-compaction analog) + n_ctx 4096 decision, measured"
```

---

## x86 target-box checklist (when the hardware exists)

Every verdict above is `dev_host_provisional`. On the target box, in order: (1) `bench/ceiling.py --bandwidth-gib-s <measured>` — the predicted decode calibrates everything; (2) re-run the Task 4 winner vs the stock Q4_K_M (the bandwidth-bound box should reward smaller files MORE than the M2 Pro did); (3) T4/T5 thread probes at the box's core count; (4) the repack probe if the flag exists; (5) the parked speculation verdicts (`ngram-simple 4/12`, draft n-max 8) — the one place the target box could flip a rejection, since CPU verify-cost was the killer and that box is genuinely bandwidth-bound.

## Self-review notes

- Task 3's `--no-repack` spelling and Task 6's converter route are deliberately gated on discovery steps — the pin decides, and "flag absent" is itself a recorded finding, matching how `docs/engine-flags.md` already works.
- Task 4/5 candidates never touch `models/core/` — `_one_gguf` would refuse a second file there anyway (`scripts... RuntimeError: holds N candidate GGUFs`), which is the guard that makes the bake-off safe to run against a provisioned tree.
- The trim test's arithmetic was traced by hand: budget 50; reversed history costs 2 ("reply-2") + 26 ("y"*100) + 2 ("reply-1") = 30, then "x"*400 at 101 breaks; leading assistant "reply-1" dropped → `[user y*100, assistant reply-2]` — matching every assertion.
- `ChatEngine`'s budget default is 0 (disabled) while `RuntimeConfig`'s is 1200: existing unit tests construct the engine directly and stay green; the product path gets the budget through `deps.py`.
