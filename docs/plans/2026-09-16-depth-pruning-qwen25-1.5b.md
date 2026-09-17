# Depth Pruning (BI / Angular-Distance) of Muta-Tutor Qwen2.5-1.5B — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a 25–40 % shallower Muta-Tutor Qwen2.5-1.5B Q4_K_M GGUF whose ADTC total score, measured on the reference audit image, beats the published 28-layer file — or a documented rejection with data.

**Architecture:** Three stages, cheapest first. (A) *Rank* layers on CPU with ShortGPT Block Influence and Gromov-style n-block angular distance over a calibration set drawn from the healing data. (B) *Screen* unhealed prunes (4/7/9/11 layers, two selection policies) by byte-exact GGUF surgery on the published Q4_K_M file and run each through the reference audit — this yields the real tok/s and RSS gains (healing cannot change them) and the accuracy floor, so only depths that can pay for themselves go to the GPU. (C) *Heal* the top depths on an A100/L4: rebuild the merged BF16 tutor, delete layers in the HF checkpoint, BF16 LoRA on the licence-clean hybrid mixture, merge, export through pinned llama.cpp b10175, then run the full promotion gate (audit, ARC-Easy-500, ARC-Challenge, GSM8K, the ten judge prompts) and score with `bench/score.py`.

**Tech Stack:** Python 3.10+ (repo), PyTorch + transformers 5.5.0 + Unsloth 2026.8.19 + PEFT 0.20.0 (GPU host, `model-development/finetune/requirements-gpu.txt`), `gguf` (gguf-py) for GGUF surgery, llama.cpp **b10175** (`convert_hf_to_gguf.py`, `llama-quantize`), the ADTC reference profiler image `adtc-profiler:latest` on GCP `muta-vm`, `bench/score.py`, pytest.

**Spec:** [docs/plans/2026-09-16-depth-pruning-qwen25-1.5b-spec.md](2026-09-16-depth-pruning-qwen25-1.5b-spec.md)

## Global Constraints

- Base model: `Muta-Tutor-Qwen2.5-1.5B-Q4_K_M.gguf`, 986,048,128 B, sha256 `a750d00d458c6ab38925364ea1413db00648449180941e47025736d09922e1eb`; upstream `Qwen/Qwen2.5-1.5B-Instruct` @ `989aa7980e4cf806f80c7fef2b1adb7bc71aa306`. The Qwen3.5-0.8B lane is closed.
- 28 layers; prune sets of size 4 (anchor), 7, 9, 11. Never drop layers 0, 1 or 27 (`--protect-first 2 --protect-last 1`).
- Healing recipe (verbatim from `model-development/finetune/train_lora.py`): BF16 LoRA, rank 16, alpha 16, targets q/k/v/o/gate/up/down, dropout 0, completion-only loss, 1024 context, micro-batch 4 × grad-accum 4, cosine schedule, warmup 5 %, adamw_8bit, seed 3407. Data: `licensed-hybrid` profile (train sha256 `d70dfe0e0126489a3abc4c0370875aee4c398539dda21c8412558f9756de2090`, 15,259 rows).
- Export: pinned llama.cpp `b10175` `convert_hf_to_gguf.py --outtype f16` then `llama-quantize … Q4_K_M`; tied head (no `output.weight`).
- Excluded from all training and calibration: every ARC/QASC/OpenBookQA/GSM8K validation and test split, the ARC-Easy-500 set, the 2 submitted test prompts, the 10 Round-1 judge prompts (`bench/measurements/semifinal-20260916/prompts.json`).
- Score-of-record: `docker run --rm --memory=7.5g … adtc-profiler:latest run --submission /submission --mode audit --output … --seed 42` on `muta-vm` (image id `sha256:b83ff230b398…`, profiler `ac2e137`, llama.cpp b10175 scalar). One measurement at a time; VM otherwise idle.
- Scoring: `S = 0.50·S_acc + 0.30·min(TPS/15,1)·100 + 0.20·max(0,(7−peak_GB)/7)·100 − 10·throttled`, `peak_GB = peak_rss_mb/1000` (`bench/score.py`).
- GGUF/metadata consistency: `qwen2.block_count` = kept layers; `metadata.json` `parameters_estimate` within ±15 % of the tensor-table parameter count.
- Repo rules: ruff line-length 100, `from __future__ import annotations`, tests importable without GPU or network; same-day `RESULTS.md` entry per measurement; GGUFs untracked.

## Projected payoff (to be replaced by Stage B measurements)

Assumes tok/s scales with bytes read per token and RSS falls by the pruned layers' bytes (30.5 MB/layer); baseline 5.77 tok/s, 1099.5 MB.

| Layers dropped | Kept | Est. tok/s | Est. S_perf | Est. peak RSS | Est. S_eff | ΔS_total before accuracy | Break-even accuracy loss |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 4 (14 %) | 24 | 6.57 | 43.8 | 977 MB | 86.0 | +1.9 | 3.9 pts |
| 7 (25 %) | 21 | 7.32 | 48.8 | 886 MB | 87.3 | +3.7 | 7.4 pts |
| 9 (32 %) | 19 | 7.94 | 52.9 | 825 MB | 88.2 | +5.1 | 10.2 pts |
| 11 (39 %) | 17 | 8.66 | 57.7 | 764 MB | 89.1 | +6.7 | 13.5 pts |

On the organisers' Round-1 VM (measured 0.63× our decode speed) every ΔS_perf shrinks by the same factor. KV-cache savings are real but small here (1 KiB/token/layer; ≈3.5 MB at 512 tokens) — do not claim them as an RSS win.

## File Structure

New directory `model-development/prune/` (sibling of `finetune/`, same conventions: standalone scripts, pure helpers unit-tested via `importlib` loading):

- `README.md` — how to run the three stages.
- `layer_selection.py` — pure math: cosine rows, Block Influence, angular distance, contiguous / lowest-BI selection with protections, old→new renumber plan. No torch.
- `calibration.py` — build `calibration.jsonl` from the healing train set; contamination guard against the judge/test prompts.
- `block_influence.py` — HF forward hooks → per-layer BI and n-block distances → `bi-<tag>.json` (CPU or CUDA).
- `prune_gguf_layers.py` — gguf-py surgery: drop `blk.i.*`, renumber, rewrite `block_count`, emit params count.
- `prune_hf_layers.py` — HF checkpoint surgery: delete `model.layers[i]`, fix `layer_idx`, config, save.
- `screen_metadata.py` — write a schema-valid `metadata.json` per candidate with a correct `parameters_estimate`.
- `export_gguf.sh` — pinned b10175 convert + quantize + sha256 manifest.
- `run_screen.sh` — Stage B on `muta-vm`: sequential reference-image audits.
- `run_heal_sweep.sh` — Stage C on the GPU host: control + candidates.
- `accuracy_battery.py` — ARC-Easy-500 / ARC-Challenge-100 / GSM8K-40 via the profiler's own `adtc_profiler.accuracy.run_benchmark` inside the reference image.
- `score_candidates.py` — exchange-rate table, break-even, promotion verdict via `bench/score.py`.
- `test_prune_helpers.py` — all pure helpers.

Modified: `model-development/finetune/train_lora.py` (accept `--revision local`), `model-development/finetune/test_finetune_helpers.py` (test for it).

Measurements land in `bench/measurements/prune-20260917/` (audit JSONs, BI JSON, manifests, grades, `scores.json`). Docs: `docs/depth-pruning.md`, `RESULTS.md`, `bench/optimization-log.md`.


> **Executed 2026-09-17 with two recorded deviations.** Task 7 Step 7: the merged BF16 tutor was not retrained — the original run (`~/muta-finetune/runs-metric/qwen25-bf16-r16-licensed-mcq-lr2e5-500/merged_16bit` on the A100 host) whose GGUF is byte-identical to the published file (sha256 `a750d00d…`) was used directly and exported through b10175 as the same-export control (`rebuilt-28L`, sha256 `1fce28cd…`). Task 8 Step 5: the contiguous n=7 window differs on the tutor (12–18 vs 9–15 on the base; block distances 0.19788 vs 0.19791), so 21L-contiguous was pruned with the tutor ranking as the plan prescribes. Tasks 1–6 were executed on 2026-09-17 00:20–04:50 (commits f0e9727…2e540af), Tasks 7–9 from 16:00 (commits 90ab2bc…81951f3).

---

### Task 1: Pure layer-selection math

**Files:**
- Create: `model-development/prune/__init__.py` (empty)
- Create: `model-development/prune/layer_selection.py`
- Create: `model-development/prune/test_prune_helpers.py`
- Create: `model-development/prune/README.md`

**Interfaces:**
- Produces: `cosine_rows(a, b) -> np.ndarray`, `block_influence(layer_in, layer_out) -> float`, `angular_distance(x_a, x_b) -> float`, `select_contiguous(block_distance: dict[int, float], n: int, n_layers: int, protect_first: int, protect_last: int) -> list[int]`, `select_lowest_bi(bi: list[float], n: int, protect_first: int, protect_last: int) -> list[int]`, `renumber_plan(n_layers: int, drop: list[int]) -> dict[int, int]`, `kept_layer_indices(n_layers: int, drop: list[int]) -> list[int]`.

- [x] **Step 1: Write the failing tests**

```python
# model-development/prune/test_prune_helpers.py
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


layer_selection = _load("layer_selection")


def test_block_influence_is_zero_for_identity_and_one_for_orthogonal():
    x = np.array([[1.0, 0.0], [0.0, 2.0]])
    assert layer_selection.block_influence(x, x) == pytest.approx(0.0, abs=1e-6)
    y = np.array([[0.0, 1.0], [3.0, 0.0]])
    assert layer_selection.block_influence(x, y) == pytest.approx(1.0)


def test_angular_distance_is_zero_same_half_orthogonal_one_opposite():
    x = np.array([[1.0, 0.0]])
    assert layer_selection.angular_distance(x, x) == pytest.approx(0.0, abs=1e-6)
    assert layer_selection.angular_distance(x, np.array([[0.0, 1.0]])) == pytest.approx(0.5)
    assert layer_selection.angular_distance(x, -x) == pytest.approx(1.0)


def test_select_contiguous_picks_minimum_inside_protections():
    # 8 layers, blocks of 3: start 0 has the smallest distance but is protected.
    dist = {0: 0.01, 1: 0.30, 2: 0.05, 3: 0.20, 4: 0.09, 5: 0.40}
    assert layer_selection.select_contiguous(dist, 3, 8, 2, 1) == [2, 3, 4]
    # protect_last=1 forbids a block that would include layer 7 (start 5 → 5,6,7).
    dist_tail = {5: 0.0, 2: 0.5, 3: 0.6, 4: 0.7}
    assert layer_selection.select_contiguous(dist_tail, 3, 8, 2, 1) == [2, 3, 4]


def test_select_contiguous_raises_when_nothing_is_eligible():
    with pytest.raises(ValueError):
        layer_selection.select_contiguous({0: 0.1}, 3, 8, 2, 1)


def test_select_lowest_bi_respects_protections_and_sorts_ascending():
    bi = [0.0, 0.0, 0.9, 0.1, 0.5, 0.2, 0.05, 0.0]  # layer 7 lowest but protected
    assert layer_selection.select_lowest_bi(bi, 3, 2, 1) == [3, 5, 6]


def test_renumber_plan_and_kept_indices_preserve_order():
    assert layer_selection.kept_layer_indices(4, [1, 2]) == [0, 3]
    assert layer_selection.renumber_plan(4, [1, 2]) == {0: 0, 3: 1}
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest model-development/prune/test_prune_helpers.py -v`
Expected: FAIL — `FileNotFoundError` for `layer_selection.py`.

- [x] **Step 3: Implement the helpers**

```python
# model-development/prune/layer_selection.py
"""Pure layer-ranking math for depth pruning (no torch).

Block Influence (ShortGPT, arXiv:2403.03853): BI_i = 1 - E_t[cos(x_t^in, x_t^out)] over the
residual stream entering and leaving layer i. Angular distance (Gromov et al.,
arXiv:2403.17887): d_n(l) = E_t[arccos(cos(x_t^(l), x_t^(l+n)))/pi] for a block of n layers
starting at l. Low values mean the layers barely rotate the residual stream and are the
cheapest to remove.
"""

from __future__ import annotations

import math

import numpy as np


def cosine_rows(a: np.ndarray, b: np.ndarray, eps: float = 1e-8) -> np.ndarray:
    """Row-wise cosine similarity between two (tokens, hidden) arrays."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    num = (a * b).sum(axis=-1)
    # eps guards zero-norm rows only; adding it would bias identical vectors below cos = 1.
    den = np.maximum(np.linalg.norm(a, axis=-1) * np.linalg.norm(b, axis=-1), eps)
    return num / den


def block_influence(layer_in: np.ndarray, layer_out: np.ndarray) -> float:
    """1 - mean cosine between a layer's input and output residual stream."""
    return float(1.0 - cosine_rows(layer_in, layer_out).mean())


def angular_distance(x_a: np.ndarray, x_b: np.ndarray) -> float:
    """Mean arccos(cos)/pi in [0, 1]; 0 = identical direction, 1 = opposite."""
    c = np.clip(cosine_rows(x_a, x_b), -1.0, 1.0)
    return float((np.arccos(c) / math.pi).mean())


def _eligible_range(n_layers: int, protect_first: int, protect_last: int) -> range:
    return range(protect_first, n_layers - protect_last)


def select_contiguous(
    block_distance: dict[int, float],
    n: int,
    n_layers: int,
    protect_first: int,
    protect_last: int,
) -> list[int]:
    """Block [l*, l*+n) with the smallest distance whose layers are all unprotected."""
    eligible = _eligible_range(n_layers, protect_first, protect_last)
    best: tuple[int, float] | None = None
    for start, distance in sorted(block_distance.items()):
        if start not in eligible or (start + n - 1) not in eligible:
            continue
        if best is None or distance < best[1]:
            best = (start, distance)
    if best is None:
        raise ValueError(
            f"no contiguous block of {n} layers fits between layer {protect_first} and "
            f"layer {n_layers - protect_last - 1}"
        )
    return list(range(best[0], best[0] + n))


def select_lowest_bi(
    bi: list[float], n: int, protect_first: int, protect_last: int
) -> list[int]:
    """The n unprotected layers with the smallest Block Influence, ascending by index."""
    eligible = list(_eligible_range(len(bi), protect_first, protect_last))
    if n > len(eligible):
        raise ValueError(f"cannot drop {n} of {len(eligible)} eligible layers")
    chosen = sorted(eligible, key=lambda i: (bi[i], i))[:n]
    return sorted(chosen)


def kept_layer_indices(n_layers: int, drop: list[int]) -> list[int]:
    dropped = set(drop)
    unknown = sorted(i for i in dropped if i < 0 or i >= n_layers)
    if unknown:
        raise ValueError(f"layer indices out of range for {n_layers} layers: {unknown}")
    return [i for i in range(n_layers) if i not in dropped]


def renumber_plan(n_layers: int, drop: list[int]) -> dict[int, int]:
    """Old layer index -> new contiguous index for every kept layer."""
    return {old: new for new, old in enumerate(kept_layer_indices(n_layers, drop))}
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest model-development/prune/test_prune_helpers.py -v`
Expected: 6 passed.

- [x] **Step 5: Write the README and commit**

```markdown
# Depth pruning (Block Influence / angular distance)

Stages: (A) `calibration.py` → `block_influence.py` ranks layers on CPU;
(B) `prune_gguf_layers.py` + `screen_metadata.py` + `run_screen.sh` measure unhealed prunes on
the reference audit image; (C) `prune_hf_layers.py` + `run_heal_sweep.sh` + `export_gguf.sh`
heal on a GPU and export; `accuracy_battery.py` + `score_candidates.py` decide.
Plan and constraints: `docs/plans/2026-09-16-depth-pruning-qwen25-1.5b.md`.
Pure helpers are tested by `test_prune_helpers.py` (no GPU, no network).
```

```bash
git add model-development/prune/__init__.py model-development/prune/layer_selection.py \
        model-development/prune/test_prune_helpers.py model-development/prune/README.md
git commit -m "feat(prune): layer-selection math for BI / angular-distance depth pruning"
```

---

### Task 2: Calibration set with contamination guard

**Files:**
- Create: `model-development/prune/calibration.py`
- Modify: `model-development/prune/test_prune_helpers.py` (append tests)

**Interfaces:**
- Consumes: `model-development/finetune/train_lora.py::join_raw_prompt_completion(prompt, completion)`; `data-metric-licensed-hybrid/train.jsonl` rows `{"mode": "raw"|"chat", "prompt", "completion", "source"}` (built by `build_metric_dataset.py --profile licensed-hybrid`).
- Produces: `render_text(row: dict) -> str`, `stratified_sample(rows: list[dict], per_source: int, seed: int) -> list[dict]`, `normalize(text: str) -> str`, `contaminated(text: str, banned: list[str], ngram: int = 8, threshold: float = 0.5) -> bool`; CLI writes `calibration.jsonl` (`{"source", "text"}` lines) and `calibration-manifest.json`.

- [x] **Step 1: Write the failing tests**

```python
# append to model-development/prune/test_prune_helpers.py
calibration = _load("calibration")


def test_render_text_uses_lm_eval_boundary_for_raw_and_chatml_for_chat():
    raw = {"mode": "raw", "prompt": "Q: 2+2?\nAnswer:", "completion": "4", "source": "arc"}
    assert calibration.render_text(raw) == "Q: 2+2?\nAnswer: 4"
    chat = {"mode": "chat", "prompt": "hi", "completion": "hello", "source": "gsm8k"}
    assert calibration.render_text(chat) == (
        "<|im_start|>user\nhi<|im_end|>\n<|im_start|>assistant\nhello<|im_end|>"
    )


def test_stratified_sample_is_deterministic_and_balanced():
    rows = [{"source": s, "text": f"{s}{i}"} for s in ("a", "b") for i in range(10)]
    first = calibration.stratified_sample(rows, per_source=3, seed=3407)
    second = calibration.stratified_sample(rows, per_source=3, seed=3407)
    assert first == second
    assert sorted(r["source"] for r in first) == ["a", "a", "a", "b", "b", "b"]


def test_contaminated_detects_exact_and_high_ngram_overlap_only():
    banned = ["A trader in Onitsha buys 40 kg of rice at ₦1,850 per kg."]
    assert calibration.contaminated("x " + banned[0] + " y", banned)
    # Not an exact substring (first word differs) but 6 of the phrase's 7 eight-grams survive.
    near = "One trader in Onitsha buys 40 kg of rice at ₦1,850 per kg."
    assert calibration.contaminated(near, banned)
    assert not calibration.contaminated("A farmer sells 3 goats for 40,000 naira.", banned)
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest model-development/prune/test_prune_helpers.py -v -k "render or stratified or contaminated"`
Expected: FAIL — `calibration.py` not found.

- [x] **Step 3: Implement**

```python
# model-development/prune/calibration.py
#!/usr/bin/env python3
"""Build the BI calibration set from the healing train split, guarded against eval prompts.

Usage:
  calibration.py --train ../finetune/data-metric-licensed-hybrid/train.jsonl \
      --banned ../../bench/measurements/semifinal-20260916/prompts.json \
      --banned ../../muta-iq/metadata.json \
      --per-source 22 --output calibration.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_finetune(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE.parent / "finetune" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render_text(row: dict) -> str:
    if row["mode"] == "chat":
        return (
            f"<|im_start|>user\n{row['prompt']}<|im_end|>\n"
            f"<|im_start|>assistant\n{row['completion']}<|im_end|>"
        )
    return _load_finetune("train_lora").join_raw_prompt_completion(
        row["prompt"], row["completion"]
    )


def stratified_sample(rows: list[dict], per_source: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    by_source: dict[str, list[dict]] = {}
    for row in rows:
        by_source.setdefault(row["source"], []).append(row)
    out: list[dict] = []
    for source in sorted(by_source):
        pool = list(by_source[source])
        rng.shuffle(pool)
        out.extend(pool[:per_source])
    return out


def normalize(text: str) -> str:
    text = text.lower().replace("₦", " ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _ngrams(text: str, n: int) -> set[tuple[str, ...]]:
    words = normalize(text).split()
    return {tuple(words[i : i + n]) for i in range(max(0, len(words) - n + 1))}


def contaminated(text: str, banned: list[str], ngram: int = 8, threshold: float = 0.5) -> bool:
    norm = normalize(text)
    for phrase in banned:
        if normalize(phrase) in norm:
            return True
        grams = _ngrams(phrase, ngram)
        if grams and len(grams & _ngrams(text, ngram)) / len(grams) >= threshold:
            return True
    return False


def load_banned(paths: list[Path]) -> list[str]:
    banned: list[str] = []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else data.get("test_prompts", [])
        banned.extend(item["prompt"] for item in items)
    return banned


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--banned", type=Path, action="append", required=True)
    parser.add_argument("--per-source", type=int, default=22)
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows = [json.loads(line) for line in args.train.read_text(encoding="utf-8").splitlines() if line]
    banned = load_banned(args.banned)
    hits = [row for row in rows if contaminated(render_text(row), banned)]
    if hits:
        raise SystemExit(f"{len(hits)} training rows overlap banned prompts; first: {hits[0]}")
    sample = stratified_sample(rows, args.per_source, args.seed)
    with args.output.open("w", encoding="utf-8") as handle:
        for row in sample:
            handle.write(json.dumps({"source": row["source"], "text": render_text(row)}) + "\n")
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    manifest = {
        "schema_version": 1,
        "train": {"path": str(args.train), "sha256": hashlib.sha256(args.train.read_bytes()).hexdigest()},
        "banned_files": [str(p) for p in args.banned],
        "banned_count": len(banned),
        "per_source": args.per_source,
        "seed": args.seed,
        "rows": len(sample),
        "sources": sorted({row["source"] for row in sample}),
        "output": {"path": str(args.output), "sha256": digest},
    }
    args.output.with_name("calibration-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest model-development/prune/test_prune_helpers.py -v`
Expected: 9 passed.

- [x] **Step 5: Build the healing data and the calibration file (one-time, network)**

```bash
cd model-development/finetune
python3 -m venv .venv-data && .venv-data/bin/pip install -q datasets==4.3.0 huggingface_hub==1.28.0
.venv-data/bin/python build_metric_dataset.py --profile licensed-hybrid --output data-metric-licensed-hybrid
sha256sum data-metric-licensed-hybrid/train.jsonl   # must print d70dfe0e0126489a3abc4c0370875aee4c398539dda21c8412558f9756de2090
cd ../prune
../finetune/.venv-data/bin/python calibration.py \
  --train ../finetune/data-metric-licensed-hybrid/train.jsonl \
  --banned ../../bench/measurements/semifinal-20260916/prompts.json \
  --banned ../../muta-iq/metadata.json \
  --per-source 22 --output calibration.jsonl
```
Expected: manifest prints `rows: 132` (6 sources × 22) and no contamination exit. If the train sha256 differs from the recorded manifest, stop: the upstream dataset revision moved and the healing data is no longer the recorded one.

- [x] **Step 6: Commit (manifest only; data stays untracked)**

```bash
git add model-development/prune/calibration.py model-development/prune/test_prune_helpers.py \
        model-development/prune/calibration-manifest.json
git commit -m "feat(prune): calibration sampler with judge/test-prompt contamination guard"
```

---

### Task 3: Block Influence and angular-distance ranking (Stage A)

**Files:**
- Create: `model-development/prune/block_influence.py`
- Modify: `model-development/prune/test_prune_helpers.py` (append tests)
- Create: `bench/measurements/prune-20260917/bi-qwen25-1.5b-instruct-base.json` (output)

**Interfaces:**
- Consumes: `layer_selection.*`, `calibration.jsonl`.
- Produces: `accumulate(stats: dict, ins: list[np.ndarray], outs: list[np.ndarray], blocks: list[int]) -> None`, `finalize(stats: dict, blocks: list[int], protect_first: int, protect_last: int) -> dict`; CLI writes `bi-<tag>.json` with keys `n_layers`, `bi` (list), `block_distance` (`{n: {start: d}}`), `selections` (`{"contiguous": {n: [...]}, "lowest_bi": {n: [...]}}`), `calibration` (sha256, rows, tokens), `model`, `revision`, `dtype`.

- [x] **Step 1: Write the failing tests (pure accumulation, no torch)**

```python
# append to model-development/prune/test_prune_helpers.py
block_influence = _load("block_influence")


def test_accumulate_and_finalize_rank_the_identity_layer_lowest():
    # 4 layers on 3 tokens of hidden size 2. Layer 1 is the identity (BI 0);
    # layers 0, 2 rotate by 90°; layer 3 rotates by 45°.
    t = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
    rot90 = np.array([[0.0, -1.0], [1.0, 0.0]])
    rot45 = np.array([[np.cos(np.pi / 4), -np.sin(np.pi / 4)], [np.sin(np.pi / 4), np.cos(np.pi / 4)]])
    x0 = t
    x1 = x0 @ rot90.T
    x2 = x1
    x3 = x2 @ rot90.T
    x4 = x3 @ rot45.T
    stats = block_influence.new_stats(n_layers=4, blocks=[2])
    block_influence.accumulate(stats, [x0, x1, x2, x3], [x1, x2, x3, x4], blocks=[2])
    result = block_influence.finalize(stats, blocks=[2], protect_first=0, protect_last=0)
    assert result["bi"][1] == pytest.approx(0.0, abs=1e-6)
    assert result["bi"][0] == pytest.approx(1.0)
    assert result["bi"][3] == pytest.approx(1 - np.cos(np.pi / 4))
    # 2-blocks: start 1 = layers 1,2 → x1→x3 is 90° (0.5); start 0 → x0→x2 is 90° (0.5);
    # start 2 → x2→x4 is 135° (0.75). Ties resolve to the lowest start.
    assert result["block_distance"]["2"]["2"] == pytest.approx(0.75)
    assert result["selections"]["contiguous"]["2"] == [0, 1]
    assert result["selections"]["lowest_bi"]["2"] == [1, 3]
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest model-development/prune/test_prune_helpers.py -v -k accumulate`
Expected: FAIL — `block_influence.py` not found.

- [x] **Step 3: Implement**

```python
# model-development/prune/block_influence.py
#!/usr/bin/env python3
"""Rank decoder layers by Block Influence and n-block angular distance.

Hooks capture each layer's residual-stream input and output directly, so the last layer is
measured before the final RMSNorm (HF's `output_hidden_states` would return it post-norm).

Usage (CPU, ~20 min on an M2 Pro for 132 × 512 tokens):
  block_influence.py --model Qwen/Qwen2.5-1.5B-Instruct \
      --revision 989aa7980e4cf806f80c7fef2b1adb7bc71aa306 \
      --calibration calibration.jsonl --blocks 4,7,9,11 \
      --protect-first 2 --protect-last 1 --dtype float32 --device cpu \
      --output ../../bench/measurements/prune-20260917/bi-qwen25-1.5b-instruct-base.json
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


layer_selection = _load("layer_selection")


def new_stats(n_layers: int, blocks: list[int]) -> dict:
    return {
        "n_layers": n_layers,
        "tokens": 0,
        "cos_sum": [0.0] * n_layers,
        "ang_sum": {n: {start: 0.0 for start in range(0, n_layers - n + 1)} for n in blocks},
    }


def accumulate(stats: dict, ins: list[np.ndarray], outs: list[np.ndarray], blocks: list[int]) -> None:
    """Add one sequence's (tokens, hidden) layer inputs/outputs to the running sums."""
    n_layers = stats["n_layers"]
    assert len(ins) == len(outs) == n_layers
    tokens = ins[0].shape[0]
    stats["tokens"] += tokens
    for i in range(n_layers):
        stats["cos_sum"][i] += float(layer_selection.cosine_rows(ins[i], outs[i]).sum())
    stream = list(ins) + [outs[-1]]  # x^(0) … x^(L); x^(L) is the last layer's output
    for n in blocks:
        for start in range(0, n_layers - n + 1):
            c = np.clip(layer_selection.cosine_rows(stream[start], stream[start + n]), -1.0, 1.0)
            stats["ang_sum"][n][start] += float((np.arccos(c) / math.pi).sum())


def finalize(stats: dict, blocks: list[int], protect_first: int, protect_last: int) -> dict:
    tokens = stats["tokens"]
    bi = [1.0 - s / tokens for s in stats["cos_sum"]]
    block_distance = {
        str(n): {str(start): stats["ang_sum"][n][start] / tokens for start in stats["ang_sum"][n]}
        for n in blocks
    }
    selections = {"contiguous": {}, "lowest_bi": {}}
    for n in blocks:
        dist = {int(k): v for k, v in block_distance[str(n)].items()}
        selections["contiguous"][str(n)] = layer_selection.select_contiguous(
            dist, n, stats["n_layers"], protect_first, protect_last
        )
        selections["lowest_bi"][str(n)] = layer_selection.select_lowest_bi(
            bi, n, protect_first, protect_last
        )
    return {
        "n_layers": stats["n_layers"],
        "tokens": tokens,
        "bi": bi,
        "block_distance": block_distance,
        "selections": selections,
        "protect": {"first": protect_first, "last": protect_last},
    }


def collect_layer_io(model, input_ids):
    """Run one sequence and return per-layer (input, output) residual streams as numpy."""
    import torch

    ins: dict[int, np.ndarray] = {}
    outs: dict[int, np.ndarray] = {}
    hooks = []
    for i, layer in enumerate(model.model.layers):
        def pre(_module, args, kwargs, i=i):
            hidden = args[0] if args else kwargs["hidden_states"]
            ins[i] = hidden.detach()[0].float().cpu().numpy()

        def post(_module, _args, _kwargs, output, i=i):
            hidden = output[0] if isinstance(output, tuple) else output
            outs[i] = hidden.detach()[0].float().cpu().numpy()

        hooks.append(layer.register_forward_pre_hook(pre, with_kwargs=True))
        hooks.append(layer.register_forward_hook(post, with_kwargs=True))
    with torch.no_grad():
        model(input_ids=input_ids, use_cache=False)
    for hook in hooks:
        hook.remove()
    n = len(model.model.layers)
    return [ins[i] for i in range(n)], [outs[i] for i in range(n)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="HF id or local checkpoint directory")
    parser.add_argument("--revision", default=None)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--blocks", default="4,7,9,11")
    parser.add_argument("--protect-first", type=int, default=2)
    parser.add_argument("--protect-last", type=int, default=1)
    parser.add_argument("--dtype", choices=("float32", "bfloat16"), default="float32")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    blocks = [int(b) for b in args.blocks.split(",")]
    dtype = torch.float32 if args.dtype == "float32" else torch.bfloat16
    tokenizer = AutoTokenizer.from_pretrained(args.model, revision=args.revision)
    model = AutoModelForCausalLM.from_pretrained(
        args.model, revision=args.revision, dtype=dtype  # transformers 5.x name (was torch_dtype)
    ).to(args.device).eval()
    n_layers = len(model.model.layers)
    stats = new_stats(n_layers, blocks)
    rows = [json.loads(l) for l in args.calibration.read_text(encoding="utf-8").splitlines() if l]
    for index, row in enumerate(rows):
        ids = tokenizer(row["text"], return_tensors="pt", truncation=True, max_length=args.max_tokens)
        ins, outs = collect_layer_io(model, ids["input_ids"].to(args.device))
        accumulate(stats, ins, outs, blocks)
        if index % 10 == 0:
            print(f"{index + 1}/{len(rows)} sequences, {stats['tokens']} tokens", flush=True)
    result = finalize(stats, blocks, args.protect_first, args.protect_last)
    result.update(
        {
            "model": args.model,
            "revision": args.revision,
            "dtype": args.dtype,
            "max_tokens": args.max_tokens,
            "calibration": {
                "path": str(args.calibration),
                "sha256": hashlib.sha256(args.calibration.read_bytes()).hexdigest(),
                "rows": len(rows),
            },
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("bi", "selections")}, indent=2))


if __name__ == "__main__":
    main()
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest model-development/prune/test_prune_helpers.py -v`
Expected: 10 passed.

- [x] **Step 5: Run the ranking on the pinned base (CPU)**

```bash
cd model-development/prune
python3 -m venv .venv-cpu && .venv-cpu/bin/pip install -q torch transformers==5.5.0 numpy safetensors
.venv-cpu/bin/python block_influence.py --model Qwen/Qwen2.5-1.5B-Instruct \
  --revision 989aa7980e4cf806f80c7fef2b1adb7bc71aa306 --calibration calibration.jsonl \
  --blocks 4,7,9,11 --protect-first 2 --protect-last 1 --dtype float32 --device cpu \
  --output ../../bench/measurements/prune-20260917/bi-qwen25-1.5b-instruct-base.json
```
Expected: 132 sequences processed; the JSON lists 28 BI values. Sanity checks before continuing: BI for layers 0–1 is among the highest; the contiguous `7`-block lies inside layers 2–26; the `lowest_bi` and `contiguous` sets for n=7 overlap in ≥3 layers (if they are disjoint, print both and continue — Stage B screens both policies anyway).

- [x] **Step 6: Commit**

```bash
git add model-development/prune/block_influence.py model-development/prune/test_prune_helpers.py \
        bench/measurements/prune-20260917/bi-qwen25-1.5b-instruct-base.json
git commit -m "feat(prune): Block Influence + angular-distance ranking of Qwen2.5-1.5B layers"
```

---

### Task 4: Byte-exact GGUF layer surgery and the unhealed ladder (Stage B, build)

**Files:**
- Create: `model-development/prune/prune_gguf_layers.py`
- Modify: `model-development/prune/test_prune_helpers.py` (append tests)

**Interfaces:**
- Consumes: `layer_selection.renumber_plan`, `bi-*.json` selections, the published GGUF.
- Produces: `plan_tensor_names(names: list[str], n_layers: int, drop: list[int]) -> list[tuple[str, str]]`, `params_from_shapes(shapes: list[tuple[int, ...]]) -> int`; CLI `prune_gguf_layers.py IN.gguf OUT.gguf --drop 8,9,10 [--name-suffix]` writing `OUT.gguf` and `OUT.prune-manifest.json` (`drop`, `kept_layers`, `params_count`, `bytes`, `sha256`, `source_sha256`).

- [x] **Step 1: Write the failing tests**

```python
# append to model-development/prune/test_prune_helpers.py
prune_gguf_layers = _load("prune_gguf_layers")  # imports gguf lazily, so loading is safe


def test_plan_tensor_names_renumbers_blocks_and_keeps_globals():
    names = ["token_embd.weight", "blk.0.attn_q.weight", "blk.1.attn_q.weight",
             "blk.2.attn_q.weight", "blk.3.attn_q.weight", "output_norm.weight"]
    plan = prune_gguf_layers.plan_tensor_names(names, 4, [1, 2])
    assert plan == [
        ("token_embd.weight", "token_embd.weight"),
        ("blk.0.attn_q.weight", "blk.0.attn_q.weight"),
        ("blk.3.attn_q.weight", "blk.1.attn_q.weight"),
        ("output_norm.weight", "output_norm.weight"),
    ]


def test_params_from_shapes_multiplies_dims():
    assert prune_gguf_layers.params_from_shapes([(8, 4), (4,), (2, 3, 5)]) == 32 + 4 + 30


def test_prune_gguf_roundtrip_drops_layers_and_rewrites_block_count(tmp_path):
    pytest.importorskip("gguf")  # inside the test: a missing dep must not skip the whole module
    from gguf import GGUFReader, GGUFWriter

    src = tmp_path / "tiny.gguf"
    writer = GGUFWriter(str(src), "qwen2")
    writer.add_block_count(4)
    writer.add_uint32("qwen2.embedding_length", 4)
    writer.add_tensor("token_embd.weight", np.arange(32, dtype=np.float32).reshape(8, 4))
    for i in range(4):
        writer.add_tensor(f"blk.{i}.attn_q.weight", np.full((4, 4), float(i), dtype=np.float32))
    writer.add_tensor("output_norm.weight", np.ones(4, dtype=np.float32))
    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_tensors_to_file()
    writer.close()

    dst = tmp_path / "pruned.gguf"
    manifest = prune_gguf_layers.prune(src, dst, drop=[1, 2])
    reader = GGUFReader(str(dst))
    field = reader.fields["qwen2.block_count"]
    assert int(field.parts[field.data[0]][0]) == 2
    tensors = {t.name: t for t in reader.tensors}
    assert set(tensors) == {"token_embd.weight", "blk.0.attn_q.weight", "blk.1.attn_q.weight",
                            "output_norm.weight"}
    assert float(tensors["blk.1.attn_q.weight"].data.reshape(-1)[0]) == 3.0  # old layer 3
    assert manifest["kept_layers"] == [0, 3]
    assert manifest["params_count"] == 32 + 2 * 16 + 4
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python3 -m pip install -q gguf && python3 -m pytest model-development/prune/test_prune_helpers.py -v -k "gguf or plan_tensor or params_from"`
Expected: FAIL — `prune_gguf_layers.py` not found.

- [x] **Step 3: Implement**

```python
# model-development/prune/prune_gguf_layers.py
#!/usr/bin/env python3
"""Copy a GGUF without the given decoder layers: tensors byte-identical, blocks renumbered,
`<arch>.block_count` rewritten. Mirrors muta-iq/opt/scripts/drop_tensor.py's copy pattern.

Usage: prune_gguf_layers.py IN.gguf OUT.gguf --drop 8,9,10,11,12,13,14
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
_BLK = re.compile(r"^blk\.(\d+)\.(.+)$")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


layer_selection = _load("layer_selection")


def plan_tensor_names(names: list[str], n_layers: int, drop: list[int]) -> list[tuple[str, str]]:
    """(old_name, new_name) for every kept tensor, in the original order."""
    mapping = layer_selection.renumber_plan(n_layers, drop)
    plan: list[tuple[str, str]] = []
    for name in names:
        match = _BLK.match(name)
        if match is None:
            plan.append((name, name))
            continue
        old = int(match.group(1))
        if old in mapping:
            plan.append((name, f"blk.{mapping[old]}.{match.group(2)}"))
    return plan


def params_from_shapes(shapes: list[tuple[int, ...]]) -> int:
    return int(sum(int(np.prod(shape)) for shape in shapes))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prune(src: Path, dst: Path, drop: list[int]) -> dict:
    import gguf
    from gguf import GGUFReader, GGUFWriter, GGUFValueType

    reader = GGUFReader(str(src))
    fields = reader.fields
    arch_field = fields["general.architecture"]
    arch = bytes(arch_field.parts[arch_field.data[0]]).decode()
    count_field = fields[f"{arch}.block_count"]
    n_layers = int(count_field.parts[count_field.data[0]][0])
    kept = layer_selection.kept_layer_indices(n_layers, drop)

    writer = GGUFWriter(str(dst), arch)
    for field in fields.values():
        if field.name == gguf.Keys.General.ARCHITECTURE or field.name.startswith("GGUF."):
            continue
        if field.name == f"{arch}.block_count":
            writer.add_uint32(field.name, len(kept))
            continue
        value_type = field.types[0]
        sub_type = field.types[-1] if value_type == GGUFValueType.ARRAY else None
        writer.add_key_value(field.name, field.contents(), value_type, sub_type=sub_type)

    by_name = {t.name: t for t in reader.tensors}
    plan = plan_tensor_names([t.name for t in reader.tensors], n_layers, drop)
    for old, new in plan:
        t = by_name[old]
        writer.add_tensor_info(new, t.data.shape, t.data.dtype, t.data.nbytes, t.tensor_type)
    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_ti_data_to_file()
    for old, _new in plan:
        t = by_name[old]
        writer.write_tensor_data(t.data, tensor_endianess=reader.endianess)
    writer.close()

    manifest = {
        "schema_version": 1,
        "source": {"path": str(src), "sha256": _sha256(src), "block_count": n_layers},
        "drop": sorted(drop),
        "kept_layers": kept,
        "block_count": len(kept),
        "tensors": len(plan),
        "params_count": params_from_shapes([tuple(int(d) for d in by_name[o].shape) for o, _ in plan]),
        "bytes": dst.stat().st_size,
        "sha256": _sha256(dst),
    }
    dst.with_suffix(".prune-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("src", type=Path)
    parser.add_argument("dst", type=Path)
    parser.add_argument("--drop", required=True, help="comma-separated layer indices")
    args = parser.parse_args()
    drop = sorted({int(x) for x in args.drop.split(",")})
    print(json.dumps(prune(args.src, args.dst, drop), indent=2))


if __name__ == "__main__":
    main()
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest model-development/prune/test_prune_helpers.py -v`
Expected: 13 passed.

- [x] **Step 5: Build the unhealed ladder from the published GGUF, on muta-vm (the file is already there; avoids a 6 GB upload)**

```bash
gcloud compute ssh muta-vm --zone=us-west1-b --project=muta-adtc --command='mkdir -p ~/adtc-prune/candidates ~/adtc-prune/tools && python3 -m pip install -q --user gguf numpy'
gcloud compute scp model-development/prune/layer_selection.py model-development/prune/prune_gguf_layers.py \
  bench/measurements/prune-20260917/bi-qwen25-1.5b-instruct-base.json muta-vm:~/adtc-prune/tools/ --zone=us-west1-b --project=muta-adtc
gcloud compute ssh muta-vm --zone=us-west1-b --project=muta-adtc --command='cd ~/adtc-prune && BI=tools/bi-qwen25-1.5b-instruct-base.json && SRC=~/adtc-semis/subs/qwen25-1.5b/model/Muta-Tutor-Qwen2.5-1.5B-Q4_K_M.gguf && sha256sum $SRC && for n in 4 7 9 11; do for policy in contiguous lowest_bi; do drop=$(python3 -c "import json; print(\",\".join(map(str, json.load(open(\"$BI\"))[\"selections\"][\"$policy\"][\"$n\"])))"); python3 tools/prune_gguf_layers.py $SRC candidates/unhealed-$((28-n))L-$policy.gguf --drop $drop | tail -3; done; done; ls -la candidates/'
```
Expected: the sha256 printed is `a750d00d…2e1eb`; 8 GGUFs; each `*-21L-*` is ≈ 986 − 7×30.5 ≈ 772 MB; manifests show `block_count` 24/21/19/17 and `params_count` = 1,543,714,304 − n × 46,797,824. Copy the eight `*.prune-manifest.json` files back into `bench/measurements/prune-20260917/`.

- [x] **Step 6: Load-and-generate check on the reference image (muta-vm)**

```bash
gcloud compute ssh muta-vm --zone=us-west1-b --project=muta-adtc --command='for f in ~/adtc-prune/candidates/*.gguf; do echo "== $f"; sudo docker run --rm -v ~/adtc-prune/candidates:/c:ro --entrypoint llama-cli adtc-profiler:latest -m /c/$(basename $f) -p "What is 25% of 80?" -n 32 --temp 0 -no-cnv 2>/dev/null | tail -2; done'
```
Expected: every file loads (`print_info: n_layer = 21` etc.) and emits text; for 17L the text may already be degraded — that is information, not failure. A load error means the renumbering is wrong: stop and fix before Task 5.

- [x] **Step 7: Cross-check one candidate against llama-quantize `--prune-layers`**

```bash
gcloud compute ssh muta-vm --zone=us-west1-b --project=muta-adtc --command='L=/home/elijahnelson/Muta/bench/.artifacts/llama.cpp-b10175; sudo cmake --build $L/build --target llama-quantize -j2 >/dev/null && DROP=$(python3 -c "import json; print(\",\".join(map(str, json.load(open(\"$HOME/adtc-prune/candidates/unhealed-21L-contiguous.prune-manifest.json\"))[\"drop\"])))") && sudo $L/build/bin/llama-quantize --prune-layers $DROP ~/adtc-semis/subs/qwen25-1.5b/model/Muta-Tutor-Qwen2.5-1.5B-Q4_K_M.gguf /tmp/xcheck-21L.gguf copy 2 2>&1 | tail -3; sudo python3 - <<EOF
import sys; sys.path.insert(0, "$L/gguf-py")
from gguf import GGUFReader
a = {t.name: (tuple(t.shape), t.tensor_type, t.data.tobytes()) for t in GGUFReader("/tmp/xcheck-21L.gguf").tensors}
b = {t.name: (tuple(t.shape), t.tensor_type, t.data.tobytes()) for t in GGUFReader("$HOME/adtc-prune/candidates/unhealed-21L-contiguous.gguf").tensors}
print("names equal:", set(a) == set(b)); print("bytes equal:", all(a[k] == b[k] for k in a))
EOF'
```
Expected: `names equal: True`, `bytes equal: True`. If `llama-quantize` refuses a quantized input with `COPY`, record that in `docs/depth-pruning.md` and rely on Step 6 plus the unit tests.

- [x] **Step 8: Commit**

```bash
git add model-development/prune/prune_gguf_layers.py model-development/prune/test_prune_helpers.py
git commit -m "feat(prune): byte-exact GGUF layer removal with block renumbering"
```

---

### Task 5: Screen the unhealed ladder on the reference audit image (Stage B, measure)

**Files:**
- Create: `model-development/prune/screen_metadata.py`
- Create: `model-development/prune/run_screen.sh`
- Modify: `model-development/prune/test_prune_helpers.py` (append tests)
- Create: `bench/measurements/prune-20260917/audit-*.json` (outputs)

**Interfaces:**
- Consumes: `bench/measurements/semifinal-20260916/submissions/metadata-qwen25-1.5b.json` (Round-1 claims), `*.prune-manifest.json`.
- Produces: `parameter_estimate_label(params: int) -> str`, `build_metadata(base: dict, model_file: str, params: int, quantization: str) -> dict`; `run_screen.sh` producing `audit-<candidate>.json` per submission directory.

- [x] **Step 1: Write the failing tests**

```python
# append to model-development/prune/test_prune_helpers.py
screen_metadata = _load("screen_metadata")


def test_parameter_estimate_label_rounds_like_the_profiler_expects():
    assert screen_metadata.parameter_estimate_label(1_543_714_304) == "1.54B"
    assert screen_metadata.parameter_estimate_label(1_216_129_536) == "1.22B"
    assert screen_metadata.parameter_estimate_label(752_393_024) == "752M"


def test_build_metadata_replaces_only_the_model_block_and_runtime_path():
    base = {"team_id": "muta", "model": {"name": "old", "runtime": "llama.cpp",
            "quantization": "GGUF Q4_K_M", "parameters_estimate": "1.54B",
            "packaging": "binary_bundle"}, "_runtime": {"model_path": "model/old.gguf"}}
    meta = screen_metadata.build_metadata(base, "unhealed-21L-contiguous.gguf", 1_216_129_536, "GGUF Q4_K_M")
    assert meta["team_id"] == "muta"
    assert meta["model"] == {"name": "unhealed-21L-contiguous.gguf", "runtime": "llama.cpp",
                             "quantization": "GGUF Q4_K_M", "parameters_estimate": "1.22B",
                             "packaging": "binary_bundle"}
    assert meta["_runtime"] == {"model_path": "model/unhealed-21L-contiguous.gguf"}
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest model-development/prune/test_prune_helpers.py -v -k "estimate_label or build_metadata"`
Expected: FAIL — `screen_metadata.py` not found.

- [x] **Step 3: Implement**

```python
# model-development/prune/screen_metadata.py
#!/usr/bin/env python3
"""Write a profiler-valid submission directory for one candidate GGUF.

The profiler's fraud check requires `parameters_estimate` within ±15 % of the tensor-table
count, so a pruned file must not inherit the 28-layer claim.

Usage: screen_metadata.py --base <round1 metadata.json> --gguf candidates/x.gguf \
           --manifest candidates/x.prune-manifest.json --out subs/x
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def parameter_estimate_label(params: int) -> str:
    if params >= 1_000_000_000:
        return f"{params / 1e9:.2f}B"
    return f"{round(params / 1e6)}M"


def build_metadata(base: dict, model_file: str, params: int, quantization: str) -> dict:
    meta = {k: v for k, v in base.items() if k not in ("model", "_runtime")}
    meta["model"] = {
        "name": model_file,
        "runtime": base["model"]["runtime"],
        "quantization": quantization,
        "parameters_estimate": parameter_estimate_label(params),
        "packaging": base["model"]["packaging"],
    }
    meta["_runtime"] = {"model_path": f"model/{model_file}"}
    return meta


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--gguf", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True, help="*.prune-manifest.json or export manifest with params_count")
    parser.add_argument("--quantization", default="GGUF Q4_K_M")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--link", action="store_true", help="hard-link the GGUF instead of copying")
    args = parser.parse_args()
    base = json.loads(args.base.read_text(encoding="utf-8"))
    params = int(json.loads(args.manifest.read_text(encoding="utf-8"))["params_count"])
    (args.out / "model").mkdir(parents=True, exist_ok=True)
    target = args.out / "model" / args.gguf.name
    if not target.exists():
        if args.link:
            target.hardlink_to(args.gguf)
        else:
            shutil.copy2(args.gguf, target)
    meta = build_metadata(base, args.gguf.name, params, args.quantization)
    (args.out / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(meta["model"], indent=2))


if __name__ == "__main__":
    main()
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest model-development/prune/test_prune_helpers.py -v`
Expected: 15 passed.

- [x] **Step 5: Write the screen runner (runs on muta-vm)**

```bash
# model-development/prune/run_screen.sh
#!/usr/bin/env bash
# Sequential reference-image audits for every submission dir under $ROOT/subs.
# Usage (on muta-vm): ROOT=~/adtc-prune ./run_screen.sh
set -u
ROOT=${ROOT:-$HOME/adtc-prune}
IMG=${IMG:-adtc-profiler:latest}
mkdir -p "$ROOT/artifacts" "$ROOT/logs" "$ROOT/hfcache"
ts() { date -u +%FT%TZ; }
sudo docker image inspect --format '{{.Id}}' "$IMG" > "$ROOT/artifacts/image-id.txt"
for sub in "$ROOT"/subs/*/; do
  name=$(basename "$sub")
  [ -f "$ROOT/artifacts/audit-$name.json" ] && { echo "skip $name (audit exists)"; continue; }
  echo "=== audit $name start $(ts) ==="
  sudo docker run --rm --memory=7.5g \
    -v "$sub:/submission:ro" -v "$ROOT/artifacts:/artifacts" -v "$ROOT/hfcache:/root/.cache/huggingface" \
    "$IMG" run --submission /submission --mode audit --output "/artifacts/audit-$name.json" --seed 42 \
    > "$ROOT/logs/audit-$name.log" 2>&1
  echo "audit $name exit=$? end $(ts)"
done
echo "SCREEN_DONE $(ts)"
```

- [x] **Step 6: Build submission dirs and run the screen**

```bash
gcloud compute scp model-development/prune/screen_metadata.py model-development/prune/run_screen.sh muta-vm:~/adtc-prune/ --zone=us-west1-b --project=muta-adtc
gcloud compute ssh muta-vm --zone=us-west1-b --project=muta-adtc --command='cd ~/adtc-prune && mkdir -p subs logs && BASE=~/adtc-semis/subs/qwen25-1.5b/metadata.json && for g in candidates/unhealed-*.gguf; do n=$(basename $g .gguf); python3 screen_metadata.py --base $BASE --gguf $g --manifest candidates/$n.prune-manifest.json --out subs/$n --link; done; ls subs; uptime; sudo docker ps -q | wc -l'   # 8 dirs; load ~0.0; 0 containers
gcloud compute ssh muta-vm --zone=us-west1-b --project=muta-adtc --command='chmod +x ~/adtc-prune/run_screen.sh; nohup ~/adtc-prune/run_screen.sh > ~/adtc-prune/logs/screen.log 2>&1 &'
```
Expected: 8 audits, each ≈ 5–11 min, all `✓ wrote`. Poll `tail ~/adtc-prune/logs/screen.log` until `SCREEN_DONE`; then copy `~/adtc-prune/artifacts/audit-*.json` into `bench/measurements/prune-20260917/`. Every audit must report `params_match: true`; a `false` means Task 5's label is wrong for that file.

- [x] **Step 7: Commit the measurements**

```bash
git add model-development/prune/screen_metadata.py model-development/prune/run_screen.sh \
        model-development/prune/test_prune_helpers.py bench/measurements/prune-20260917/audit-unhealed-*.json \
        bench/measurements/prune-20260917/image-id.txt
git commit -m "feat(prune): unhealed depth-pruning screen on the reference audit image"
```

---

### Task 6: Exchange-rate scoring and the healing shortlist

**Files:**
- Create: `model-development/prune/score_candidates.py`
- Modify: `model-development/prune/test_prune_helpers.py` (append tests)
- Create: `bench/measurements/prune-20260917/screen-scores.json` (output)

**Interfaces:**
- Consumes: `bench/score.py::score(accuracy, tps_actual, peak_rss_gb, max_temp_c, throttled, label)`; audit JSONs; optional `judge-grades-<name>.json` (`{"scores": {...}}`) and `battery-<name>.json` (Task 10).
- Produces: `row_from_audit(name: str, audit: dict) -> dict`, `break_even_accuracy_loss(control: dict, candidate: dict) -> float`, `shortlist(rows: list[dict], control: dict, max_depths: int = 2) -> list[dict]`, `verdict(candidate: dict, published: dict) -> dict`; CLI `score_candidates.py --dir DIR --control audit-published-28L.json [--gate] --out scores.json`.

- [x] **Step 1: Write the failing tests**

```python
# append to model-development/prune/test_prune_helpers.py
score_candidates = _load("score_candidates")


def _audit(tps, peak, arc):
    return {"throughput": {"tokens_per_second_generation": tps, "first_token_latency_ms": 1.0},
            "memory": {"peak_rss_mb": peak, "steady_state_rss_mb": peak},
            "accuracy": [{"benchmark": "arc_easy", "samples": 50, "score": arc}],
            "cpu_thermal": {"core_temp_c_peak": None, "throttled": False, "cpu_percent_p99": 70.0},
            "model_info": {"params_count": 1, "params_match": True}}


def test_break_even_matches_the_exchange_rates():
    control = score_candidates.row_from_audit("control", _audit(5.77, 1099.54, 0.84))
    cand = score_candidates.row_from_audit("21L", _audit(7.32, 885.5, 0.70))
    # ΔS_perf = (7.32-5.77)/15*100 = 10.33 → ×0.3 = 3.10; ΔS_eff = (1099.54-885.5)/7000*100 = 3.06 → ×0.2 = 0.61
    assert score_candidates.break_even_accuracy_loss(control, cand) == pytest.approx(7.42, abs=0.01)
    assert cand["S_total_arc50"] == pytest.approx(0.5 * 70 + 0.3 * 48.8 + 0.2 * 87.35, abs=0.05)


def test_shortlist_keeps_depths_whose_floor_is_within_twice_break_even():
    control = score_candidates.row_from_audit("control", _audit(5.77, 1099.54, 0.84))
    rows = [
        score_candidates.row_from_audit("unhealed-24L-contiguous", _audit(6.57, 977.0, 0.82)),
        score_candidates.row_from_audit("unhealed-21L-contiguous", _audit(7.32, 885.5, 0.72)),
        score_candidates.row_from_audit("unhealed-21L-lowest_bi", _audit(7.30, 885.5, 0.66)),
        score_candidates.row_from_audit("unhealed-17L-contiguous", _audit(8.66, 764.0, 0.40)),
    ]
    picked = score_candidates.shortlist(rows, control, max_depths=2)
    # 17L fails the 2×break-even floor (loss 44 > 27); 21L-lowest_bi loses to 21L-contiguous
    # (same depth, lower total); survivors rank by unhealed S_total: 24L (71.35) then 21L (68.11).
    assert [r["name"] for r in picked] == ["unhealed-24L-contiguous", "unhealed-21L-contiguous"]


def test_verdict_requires_both_totals_gsm8k_and_fraud_check():
    published = {"S_total_arc500": 70.0, "S_total_judge": 47.0, "gsm8k_40": 0.50}
    good = {"S_total_arc500": 71.5, "S_total_judge": 48.5, "gsm8k_40": 0.47, "params_match": True}
    assert score_candidates.verdict(good, published)["promote"] is True
    bad = dict(good, gsm8k_40=0.40)
    assert score_candidates.verdict(bad, published)["promote"] is False
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest model-development/prune/test_prune_helpers.py -v -k "break_even or shortlist or verdict"`
Expected: FAIL — `score_candidates.py` not found.

- [x] **Step 3: Implement**

```python
# model-development/prune/score_candidates.py
#!/usr/bin/env python3
"""Score audit JSONs with the ADTC formula, compute exchange-rate break-evens, shortlist
depths for healing, and (with --gate) issue the promotion verdict.

Usage:
  score_candidates.py --dir bench/measurements/prune-20260917 \
      --control bench/measurements/semifinal-20260916/audit-qwen25-1.5b.json --out screen-scores.json
  score_candidates.py --dir … --control … --gate --out gate-scores.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from bench.score import score  # noqa: E402

W_ACC, W_PERF, W_EFF = 0.50, 0.30, 0.20
PROMOTE_MARGIN = 1.0
GSM8K_MAX_DROP = 0.05


def _components(tps: float, peak_mb: float) -> tuple[float, float]:
    return min(tps / 15.0, 1.0) * 100.0, max(0.0, (7.0 - peak_mb / 1000.0) / 7.0) * 100.0


def row_from_audit(name: str, audit: dict) -> dict:
    tps = audit["throughput"]["tokens_per_second_generation"]
    peak = audit["memory"]["peak_rss_mb"]
    throttled = bool(audit["cpu_thermal"]["throttled"])
    temp = audit["cpu_thermal"].get("core_temp_c_peak")
    arc50 = audit["accuracy"][0]["score"] * 100.0 if audit["accuracy"] else None
    s_perf, s_eff = _components(tps, peak)
    row = {
        "name": name,
        "layers": int(m.group(1)) if (m := re.search(r"-(\d+)L", name)) else 28,
        "tps": tps,
        "peak_rss_mb": peak,
        "throttled": throttled,
        "params_match": audit.get("model_info", {}).get("params_match"),
        "arc_easy_50": arc50,
        "S_perf": round(s_perf, 2),
        "S_eff": round(s_eff, 2),
    }
    if arc50 is not None:
        r = score(accuracy=arc50, tps_actual=tps, peak_rss_gb=peak / 1000.0,
                  max_temp_c=temp, throttled=throttled, label=name)
        row["S_total_arc50"] = round(r.s_total, 2)
    return row


def break_even_accuracy_loss(control: dict, candidate: dict) -> float:
    """Accuracy points the candidate may lose and still tie the control on S_total."""
    gain = W_PERF * (candidate["S_perf"] - control["S_perf"]) + W_EFF * (candidate["S_eff"] - control["S_eff"])
    return gain / W_ACC


def shortlist(rows: list[dict], control: dict, max_depths: int = 2) -> list[dict]:
    """Top depths by unhealed S_total whose ARC-50 floor is within 2× break-even of control."""
    eligible = []
    for row in rows:
        be = break_even_accuracy_loss(control, row)
        loss = control["arc_easy_50"] - row["arc_easy_50"]
        row = dict(row, break_even=round(be, 2), arc50_loss=round(loss, 2))
        if loss <= 2.0 * be:
            eligible.append(row)
    eligible.sort(key=lambda r: -r["S_total_arc50"])
    picked, depths = [], set()
    for row in eligible:
        if row["layers"] in depths:
            continue
        picked.append(row)
        depths.add(row["layers"])
        if len(picked) == max_depths:
            break
    return picked


def verdict(candidate: dict, published: dict) -> dict:
    checks = {
        "arc500_total": candidate["S_total_arc500"] >= published["S_total_arc500"] + PROMOTE_MARGIN,
        "judge_total": candidate["S_total_judge"] >= published["S_total_judge"] + PROMOTE_MARGIN,
        "gsm8k": candidate["gsm8k_40"] >= published["gsm8k_40"] - GSM8K_MAX_DROP,
        "params_match": bool(candidate.get("params_match")),
    }
    return {"promote": all(checks.values()), "checks": checks}


def _gate_row(row: dict, directory: Path) -> dict:
    battery = directory / f"battery-{row['name']}.json"
    grades = directory / f"judge-grades-{row['name']}.json"
    if battery.exists():
        b = json.loads(battery.read_text())
        row["arc_easy_500"] = b["arc_easy"]["score"] * 100.0
        row["arc_challenge_100"] = b["arc_challenge"]["score"]
        row["gsm8k_40"] = b["gsm8k"]["score"]
        r = score(accuracy=row["arc_easy_500"], tps_actual=row["tps"], peak_rss_gb=row["peak_rss_mb"] / 1000.0,
                  throttled=row["throttled"], label=row["name"])
        row["S_total_arc500"] = round(r.s_total, 2)
    if grades.exists():
        g = json.loads(grades.read_text())["scores"]
        row["judge_pct"] = sum(g.values()) / len(g) * 10.0
        r = score(accuracy=row["judge_pct"], tps_actual=row["tps"], peak_rss_gb=row["peak_rss_mb"] / 1000.0,
                  throttled=row["throttled"], label=row["name"])
        row["S_total_judge"] = round(r.s_total, 2)
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, required=True)
    parser.add_argument("--control", type=Path, required=True, help="audit JSON of the published 28L file")
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    control = row_from_audit("published-28L", json.loads(args.control.read_text()))
    rows = [row_from_audit(p.stem.removeprefix("audit-"), json.loads(p.read_text()))
            for p in sorted(args.dir.glob("audit-*.json"))]
    rows = [r for r in rows if r["name"] != control["name"]]
    result: dict = {"control": control, "rows": rows}
    if args.gate:
        control = _gate_row(control, args.dir)
        rows = [_gate_row(r, args.dir) for r in rows]
        result["verdicts"] = {r["name"]: verdict(r, control) for r in rows if "S_total_judge" in r and "S_total_arc500" in r}
    else:
        result["shortlist"] = shortlist(rows, control)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(f"{'name':36s} {'L':>3s} {'tok/s':>6s} {'peakMB':>8s} {'ARC50':>6s} {'S_perf':>7s} {'S_eff':>6s} {'T(arc50)':>9s}")
    for r in [control] + rows:
        print(f"{r['name']:36s} {r['layers']:3d} {r['tps']:6.2f} {r['peak_rss_mb']:8.1f} {r.get('arc_easy_50') or 0:6.1f} {r['S_perf']:7.2f} {r['S_eff']:6.2f} {r.get('S_total_arc50') or 0:9.2f}")
    if not args.gate:
        print("shortlist:", [r["name"] for r in result["shortlist"]])
    else:
        print(json.dumps(result["verdicts"], indent=2))


if __name__ == "__main__":
    main()
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest model-development/prune/test_prune_helpers.py -v`
Expected: 18 passed.

- [x] **Step 5: Score the screen and record the shortlist**

```bash
python3 model-development/prune/score_candidates.py --dir bench/measurements/prune-20260917 \
  --control bench/measurements/semifinal-20260916/audit-qwen25-1.5b.json \
  --out bench/measurements/prune-20260917/screen-scores.json
```
Expected: a table of 8 rows and a shortlist of ≤2 depths. If the shortlist is empty (every prune's ARC-50 floor exceeds 2× break-even), still heal `21L` and `24L` with the better policy at each depth — the screen is a floor, and healing is the experiment — and say so in the RESULTS entry.

- [x] **Step 6: RESULTS.md entry for Stage A+B and commit**

Add a `## 2026-09-17 — depth-pruning screen (unhealed ladder)` entry to `RESULTS.md` above the previous entry with: hardware context (`x86 cloud proxy`, `muta-vm`, reference image id), the BI ranking summary (top-3 lowest-BI layers, the contiguous blocks), the 8-row table (layers, policy, tok/s, TTFT, peak RSS, ARC-Easy-50, S_perf, S_eff, S_total_arc50, break-even), the shortlist and the reason. Then:

```bash
git add model-development/prune/score_candidates.py model-development/prune/test_prune_helpers.py \
        bench/measurements/prune-20260917/screen-scores.json RESULTS.md
git commit -m "feat(prune): exchange-rate scoring, healing shortlist, screen results"
```

---

### Task 7: GPU host, rebuilt merged tutor, pinned export path (Stage C, setup)

**Files:**
- Modify: `model-development/finetune/train_lora.py` (add `resolve_revision`, `--revision local`)
- Modify: `model-development/finetune/test_finetune_helpers.py` (append test)
- Create: `model-development/prune/export_gguf.sh`

**Interfaces:**
- Consumes: `model-development/finetune/setup_gpu_env.sh`, `requirements-gpu.txt`, `run_metric_sweep.sh`'s recorded recipe for `qwen25-bf16-r16-licensed-mcq-lr2e5-500`.
- Produces: `train_lora.resolve_revision(value: str) -> str | None`; `export_gguf.sh MERGED_DIR OUT_PREFIX` → `OUT_PREFIX-Q4_K_M.gguf` + `OUT_PREFIX.export-manifest.json` (`params_count`, `bytes`, `sha256`, `llama_cpp_commit`); `runs-prune/tutor-28L/merged_16bit/` (the rebuilt base).

- [x] **Step 1: Write the failing test for local revisions**

```python
# append to model-development/finetune/test_finetune_helpers.py
def test_resolve_revision_maps_local_to_none_and_keeps_hashes():
    assert train_lora.resolve_revision("local") is None
    assert train_lora.resolve_revision("989aa7980e4cf806f80c7fef2b1adb7bc71aa306") == (
        "989aa7980e4cf806f80c7fef2b1adb7bc71aa306"
    )
```

- [x] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest model-development/finetune/test_finetune_helpers.py -v -k resolve_revision`
Expected: FAIL — `AttributeError: module has no attribute 'resolve_revision'`.

- [x] **Step 3: Implement in `train_lora.py`**

Add after `sha256_file`:
```python
def resolve_revision(value: str) -> str | None:
    """`--revision local` means a local checkpoint directory: pass no revision to HF."""
    return None if value == "local" else value
```
and change the two call sites:
```python
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.model,
        revision=resolve_revision(args.revision),
```
and in the manifest keep `"revision": args.revision` (so `local` is recorded verbatim). Update the `--revision` help: `help="HF revision hash, or 'local' for a checkpoint directory"`.

- [x] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest model-development/finetune/test_finetune_helpers.py -v`
Expected: all pass (the existing suite plus the new test).

- [x] **Step 5: Write the pinned export script**

```bash
# model-development/prune/export_gguf.sh
#!/usr/bin/env bash
# Export a merged BF16 HF checkpoint to Q4_K_M with pinned llama.cpp b10175 (audit parity).
# Usage: LLAMA_DIR=/path/to/llama.cpp-b10175 ./export_gguf.sh MERGED_DIR OUT_PREFIX [PYTHON]
set -euo pipefail
MERGED=$1; OUT=$2; PY=${3:-python3}
LLAMA_DIR=${LLAMA_DIR:?set LLAMA_DIR to a b10175 checkout with build/bin/llama-quantize}
TAG=$(git -C "$LLAMA_DIR" describe --tags --exact-match 2>/dev/null || git -C "$LLAMA_DIR" rev-parse --short HEAD)
[ "$TAG" = "b10175" ] || { echo "llama.cpp checkout is $TAG, not b10175" >&2; exit 1; }
[ -x "$LLAMA_DIR/build/bin/llama-quantize" ] || { echo "build llama-quantize first: cmake -B build -DGGML_NATIVE=OFF && cmake --build build --target llama-quantize -j" >&2; exit 1; }
"$PY" "$LLAMA_DIR/convert_hf_to_gguf.py" "$MERGED" --outtype f16 --outfile "$OUT-f16.gguf"
"$LLAMA_DIR/build/bin/llama-quantize" "$OUT-f16.gguf" "$OUT-Q4_K_M.gguf" Q4_K_M 8
rm -f "$OUT-f16.gguf"
"$PY" - "$OUT-Q4_K_M.gguf" "$LLAMA_DIR" "$MERGED" > "$OUT.export-manifest.json" <<'PY'
import hashlib, json, subprocess, sys
sys.path.insert(0, sys.argv[2] + "/gguf-py")
from gguf import GGUFReader
import numpy as np
path, llama_dir, merged = sys.argv[1:4]
reader = GGUFReader(path)
params = int(sum(int(np.prod(t.shape)) for t in reader.tensors))
digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
commit = subprocess.check_output(["git", "-C", llama_dir, "rev-parse", "HEAD"], text=True).strip()
json.dump({"schema_version": 1, "source_dir": merged, "artifact": path, "params_count": params,
           "bytes": __import__("os").path.getsize(path), "sha256": digest,
           "llama_cpp_commit": commit, "quantization": "Q4_K_M",
           "tensor_types": sorted({str(t.tensor_type).split(".")[-1] for t in reader.tensors})},
          sys.stdout, indent=2)
PY
cat "$OUT.export-manifest.json"
```

- [x] **Step 6: Provision the GPU host and the environment**

Reuse the previously supplied A100-40GB host if it still exists (`ssh` in; `nvidia-smi` shows `NVIDIA A100-SXM4-40GB`, PyTorch 2.7, CUDA 12.8). Otherwise create one on GCP:

```bash
gcloud compute images list --project=deeplearning-platform-release --filter="family~cu128 AND family~py312" --format="value(family)" | head -3
gcloud compute instances create muta-gpu --project=muta-adtc --zone=us-central1-a \
  --machine-type=g2-standard-8 --accelerator=type=nvidia-l4,count=1 --maintenance-policy=TERMINATE \
  --image-project=deeplearning-platform-release --image-family=<family printed above> \
  --boot-disk-size=200GB --metadata="install-nvidia-driver=True"
```
(An L4 24 GB is sufficient: the recorded run used ≤ 20 GB at micro-batch 4 × 1024 tokens BF16 LoRA. Delete the instance when Task 9 finishes.) Then on the host:

```bash
git clone <this repo> ~/Muta && cd ~/Muta/model-development/finetune
./setup_gpu_env.sh .venv            # pins unsloth 2026.8.19, transformers 5.5.0, peft 0.20.0
.venv/bin/python build_metric_dataset.py --profile licensed-hybrid --output data-metric-licensed-hybrid
.venv/bin/python build_metric_dataset.py --profile licensed-mcq --output data-metric-licensed-mcq
sha256sum data-metric-licensed-hybrid/train.jsonl data-metric-licensed-mcq/train.jsonl
#   d70dfe0e…2090  and  0d1b52db…3734c — must match the recorded manifests
git clone --depth 1 --branch b10175 https://github.com/ggerganov/llama.cpp.git ~/llama.cpp-b10175
cd ~/llama.cpp-b10175 && cmake -B build -DGGML_NATIVE=OFF -DBUILD_SHARED_LIBS=OFF && cmake --build build --target llama-quantize -j
~/Muta/model-development/finetune/.venv/bin/pip install -q gguf sentencepiece
```

- [x] **Step 7: Rebuild the merged tutor (the model we prune) and validate it**

```bash
cd ~/Muta/model-development/finetune
.venv/bin/python train_lora.py --model Qwen/Qwen2.5-1.5B-Instruct --revision 989aa7980e4cf806f80c7fef2b1adb7bc71aa306 \
  --train data-metric-licensed-mcq/train.jsonl --validation data-metric-licensed-mcq/validation.jsonl \
  --output ../prune/runs-prune/tutor-28L --rank 16 --learning-rate 2e-5 --max-steps 500 --eval-steps 250
LLAMA_DIR=~/llama.cpp-b10175 ../prune/export_gguf.sh ../prune/runs-prune/tutor-28L/merged_16bit ../prune/runs-prune/tutor-28L/tutor-28L .venv/bin/python
```
Expected: `training-manifest.json` with `train_rows: 10756`, eval_loss ≈ 2.71 (recorded 2.7091); export manifest `params_count: 1543714304`, `bytes` within 0.1 % of 986,048,128, `tensor_types` ⊆ {Q4_K, Q6_K, F32}. Then audit it as the same-export control:

```bash
gcloud compute scp ../prune/runs-prune/tutor-28L/tutor-28L-Q4_K_M.gguf ../prune/runs-prune/tutor-28L/tutor-28L.export-manifest.json muta-vm:~/adtc-prune/healed/ --zone=us-west1-b --project=muta-adtc
gcloud compute ssh muta-vm --zone=us-west1-b --project=muta-adtc --command='cd ~/adtc-prune && python3 screen_metadata.py --base ~/adtc-semis/subs/qwen25-1.5b/metadata.json --gguf healed/tutor-28L-Q4_K_M.gguf --manifest healed/tutor-28L.export-manifest.json --out subs/rebuilt-28L --link && nohup ./run_screen.sh > logs/rebuilt.log 2>&1 &'
```
Expected: `audit-rebuilt-28L.json` with ARC-Easy-50 within ±0.04 of 0.84 and tok/s within ±5 % of 5.77 — this is the control every healed candidate is compared with. If it misses, do not proceed: the export path differs from the published one and Task 11's comparison would be confounded.

- [x] **Step 8: Commit**

```bash
git add model-development/finetune/train_lora.py model-development/finetune/test_finetune_helpers.py \
        model-development/prune/export_gguf.sh
git commit -m "feat(prune): local-checkpoint training and pinned b10175 GGUF export"
```

---

### Task 8: HF checkpoint layer removal and BI re-check on the tutor

**Files:**
- Create: `model-development/prune/prune_hf_layers.py`
- Modify: `model-development/prune/test_prune_helpers.py` (append test)
- Create: `bench/measurements/prune-20260917/bi-tutor-28L-merged.json` (output)

**Interfaces:**
- Consumes: `layer_selection.kept_layer_indices`, `runs-prune/tutor-28L/merged_16bit/`, the shortlist from `screen-scores.json`.
- Produces: `prune_model(model, drop: list[int])` (in place; returns kept indices), CLI `prune_hf_layers.py --source DIR --drop 8,9,… --output DIR [--bi bi.json]` writing the checkpoint plus `prune-manifest.json`.

- [x] **Step 1: Write the failing test (tiny random Qwen2, CPU)**

```python
# append to model-development/prune/test_prune_helpers.py
prune_hf_layers = _load("prune_hf_layers")  # torch is imported inside its functions


def test_prune_model_keeps_the_right_layer_objects_and_still_runs():
    torch = pytest.importorskip("torch")  # inside the test, never at module level
    pytest.importorskip("transformers")
    from transformers import Qwen2Config, Qwen2ForCausalLM

    config = Qwen2Config(hidden_size=32, intermediate_size=64, num_hidden_layers=4,
                         num_attention_heads=4, num_key_value_heads=2, vocab_size=128,
                         max_position_embeddings=64, tie_word_embeddings=True)
    torch.manual_seed(0)
    model = Qwen2ForCausalLM(config).eval()
    original = list(model.model.layers)
    kept = prune_hf_layers.prune_model(model, drop=[1, 2])
    assert kept == [0, 3]
    assert model.config.num_hidden_layers == 2
    assert model.model.layers[0] is original[0] and model.model.layers[1] is original[3]
    assert model.model.layers[1].self_attn.layer_idx == 1
    ids = torch.tensor([[1, 2, 3, 4]])
    with torch.no_grad():
        logits = model(input_ids=ids, use_cache=False).logits
    assert logits.shape == (1, 4, 128) and torch.isfinite(logits).all()
```

- [x] **Step 2: Run test to verify it fails**

Run: `model-development/prune/.venv-cpu/bin/python -m pytest model-development/prune/test_prune_helpers.py -v -k prune_model`
Expected: FAIL — `prune_hf_layers.py` not found.

- [x] **Step 3: Implement**

```python
# model-development/prune/prune_hf_layers.py
#!/usr/bin/env python3
"""Delete decoder layers from a Qwen2 HF checkpoint and save a loadable, shallower model.

Usage: prune_hf_layers.py --source runs-prune/tutor-28L/merged_16bit --drop 8,9,10,11,12,13,14 \
           --output runs-prune/pruned-21L-contiguous --bi ../../bench/measurements/prune-20260917/bi-tutor-28L-merged.json
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


layer_selection = _load("layer_selection")


def prune_model(model, drop: list[int]) -> list[int]:
    """Remove `drop` from model.model.layers in place; renumber layer_idx; fix config."""
    import torch.nn as nn

    layers = model.model.layers
    kept = layer_selection.kept_layer_indices(len(layers), drop)
    model.model.layers = nn.ModuleList([layers[i] for i in kept])
    for new_index, layer in enumerate(model.model.layers):
        if hasattr(layer, "self_attn") and hasattr(layer.self_attn, "layer_idx"):
            layer.self_attn.layer_idx = new_index
    model.config.num_hidden_layers = len(kept)
    if getattr(model.config, "max_window_layers", None) is not None:
        model.config.max_window_layers = min(model.config.max_window_layers, len(kept))
    if getattr(model.config, "layer_types", None):
        model.config.layer_types = [model.config.layer_types[i] for i in kept]
    return kept


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--drop", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bi", type=Path, default=None, help="BI json used to choose --drop (provenance)")
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    drop = sorted({int(x) for x in args.drop.split(",")})
    model = AutoModelForCausalLM.from_pretrained(args.source, dtype=torch.bfloat16)
    tokenizer = AutoTokenizer.from_pretrained(args.source)
    kept = prune_model(model, drop)
    args.output.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(args.output, safe_serialization=True)
    tokenizer.save_pretrained(args.output)
    manifest = {
        "schema_version": 1,
        "source": str(args.source),
        "drop": drop,
        "kept_layers": kept,
        "num_hidden_layers": len(kept),
        "params_count": int(sum(p.numel() for p in model.parameters())),
        "bi_json": str(args.bi) if args.bi else None,
        "bi_sha256": hashlib.sha256(args.bi.read_bytes()).hexdigest() if args.bi else None,
    }
    (args.output / "prune-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
```

- [x] **Step 4: Run tests to verify they pass**

Run: `model-development/prune/.venv-cpu/bin/python -m pytest model-development/prune/test_prune_helpers.py -v`
Expected: 19 passed.

- [x] **Step 5: Re-rank on the rebuilt tutor (GPU host, seconds) and compare with the base ranking**

```bash
cd ~/Muta/model-development/prune
../finetune/.venv/bin/python block_influence.py --model runs-prune/tutor-28L/merged_16bit \
  --calibration calibration.jsonl --blocks 4,7,9,11 --protect-first 2 --protect-last 1 \
  --dtype bfloat16 --device cuda --output ../../bench/measurements/prune-20260917/bi-tutor-28L-merged.json
python3 - <<'EOF'
import json
a = json.load(open("../../bench/measurements/prune-20260917/bi-qwen25-1.5b-instruct-base.json"))["selections"]
b = json.load(open("../../bench/measurements/prune-20260917/bi-tutor-28L-merged.json"))["selections"]
for policy in ("contiguous", "lowest_bi"):
    for n in ("4", "7", "9", "11"):
        print(policy, n, "base", a[policy][n], "tutor", b[policy][n], "same" if a[policy][n] == b[policy][n] else "DIFFERS")
EOF
```
Expected: identical sets (the LoRA delta is rank-16 and small). If a shortlisted set differs, **use the tutor ranking** for Task 8 Step 6 and note the difference in RESULTS.md; the Stage B floor for that depth was measured on a slightly different set and is stated as such.

- [x] **Step 6: Prune the tutor checkpoint for each shortlisted depth**

```bash
BI=../../bench/measurements/prune-20260917/bi-tutor-28L-merged.json
for spec in $(python3 -c "import json; print(' '.join(r['name'].removeprefix('unhealed-') for r in json.load(open('../../bench/measurements/prune-20260917/screen-scores.json'))['shortlist']))"); do
  n=${spec%%L-*}; policy=${spec#*L-}; k=$((28-n))
  drop=$(python3 -c "import json; print(','.join(map(str, json.load(open('$BI'))['selections']['$policy']['$k'])))")
  ../finetune/.venv/bin/python prune_hf_layers.py --source runs-prune/tutor-28L/merged_16bit --drop "$drop" --output "runs-prune/pruned-$spec" --bi "$BI"
done
```
Expected: one directory per shortlisted candidate with `config.json` `num_hidden_layers` = 21/24/… and `prune-manifest.json` `params_count` = 1,543,714,304 − dropped × 46,797,824.

- [x] **Step 7: Commit**

```bash
git add model-development/prune/prune_hf_layers.py model-development/prune/test_prune_helpers.py \
        bench/measurements/prune-20260917/bi-tutor-28L-merged.json
git commit -m "feat(prune): HF layer removal for healing; BI re-ranked on the merged tutor"
```

---

### Task 9: Healing sweep and export (Stage C, train)

**Files:**
- Create: `model-development/prune/run_heal_sweep.sh`
- Create: `bench/measurements/prune-20260917/training/*.json`, `export/*.json` (manifests)

**Interfaces:**
- Consumes: `train_lora.py --revision local`, `export_gguf.sh`, `runs-prune/pruned-*`, `runs-prune/tutor-28L/merged_16bit`.
- Produces: `runs-prune/<run>/merged_16bit/`, `runs-prune/<run>/<run>-Q4_K_M.gguf`, `<run>.export-manifest.json` for: `control-28L-hybrid-lr5e5-1000`, `heal-<spec>-lr5e5-1000` per shortlisted spec, `heal-<best spec>-lr2e5-1000`.

- [x] **Step 1: Write the sweep runner**

```bash
# model-development/prune/run_heal_sweep.sh
#!/usr/bin/env bash
# Heal each shortlisted pruned checkpoint with the recorded LoRA recipe on licensed-hybrid;
# train an unpruned control with the identical recipe so the pruning cost is isolated.
# Usage (GPU host): SPECS="21L-contiguous 24L-contiguous" BEST=21L-contiguous ./run_heal_sweep.sh
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FT="$HERE/../finetune"
PY="${PY:-$FT/.venv/bin/python}"
DATA="${DATA:-$FT/data-metric-licensed-hybrid}"
RUNS="$HERE/runs-prune"
LLAMA_DIR="${LLAMA_DIR:?}"
SPECS="${SPECS:?space-separated e.g. '21L-contiguous 24L-contiguous'}"
BEST="${BEST:?the first spec to also heal at lr 2e-5}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}" TOKENIZERS_PARALLELISM=false PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
mkdir -p "$RUNS/logs"

heal() {  # name source lr steps
  local name=$1 source=$2 lr=$3 steps=$4 out="$RUNS/$1"
  if [[ -f "$out/training-manifest.json" ]]; then echo "SKIP $name"; return 0; fi
  echo "START $name $(date -u +%FT%TZ)"
  if "$PY" "$FT/train_lora.py" --model "$source" --revision local \
       --train "$DATA/train.jsonl" --validation "$DATA/validation.jsonl" --output "$out" \
       --rank 16 --learning-rate "$lr" --max-steps "$steps" --eval-steps 250 \
       > "$RUNS/logs/$name.log" 2>&1 \
     && LLAMA_DIR="$LLAMA_DIR" "$HERE/export_gguf.sh" "$out/merged_16bit" "$out/$name" "$PY" >> "$RUNS/logs/$name.log" 2>&1; then
    echo "PASS $name"
  else
    echo "FAIL $name"; tail -30 "$RUNS/logs/$name.log"
  fi
}

heal control-28L-hybrid-lr5e5-1000 "$RUNS/tutor-28L/merged_16bit" 5e-5 1000
for spec in $SPECS; do
  heal "heal-$spec-lr5e5-1000" "$RUNS/pruned-$spec" 5e-5 1000
done
heal "heal-$BEST-lr2e5-1000" "$RUNS/pruned-$BEST" 2e-5 1000
echo "HEAL_DONE $(date -u +%FT%TZ)"
```

- [x] **Step 2: Dry-check the script's argument handling**

Run: `bash -n model-development/prune/run_heal_sweep.sh && SPECS="" BEST="" LLAMA_DIR=x bash model-development/prune/run_heal_sweep.sh; echo "exit=$?"`
Expected: `bash -n` is silent; the run prints the `SPECS` usage error and exits non-zero without touching the GPU.

- [x] **Step 3: Run the sweep (GPU host)**

```bash
cd ~/Muta/model-development/prune
SPECS="21L-contiguous 24L-contiguous" BEST="21L-contiguous" LLAMA_DIR=~/llama.cpp-b10175 nohup ./run_heal_sweep.sh > runs-prune/logs/sweep.log 2>&1 &
```
(Substitute the shortlist names from Task 6.) Expected wall-clock: 1000 steps ≈ 18 min per run on an A100 (the recorded 500-step run took 544 s) — four runs ≈ 75 min, pruned runs faster. Each run ends with `PASS`, a `training-manifest.json`, and an export manifest whose `params_count` equals the pruned checkpoint's. Validation `eval_loss` on licensed-hybrid: record all; a healed 21L loss more than 0.25 nats above the 28L control's is a warning sign, not a stop.

- [x] **Step 4: Collect manifests and ship GGUFs to muta-vm**

```bash
mkdir -p ~/Muta/bench/measurements/prune-20260917/{training,export}
for r in runs-prune/control-* runs-prune/heal-*; do n=$(basename $r); cp $r/training-manifest.json ../../bench/measurements/prune-20260917/training/$n.json; cp $r/$n.export-manifest.json ../../bench/measurements/prune-20260917/export/$n.json; done
gcloud compute scp runs-prune/*/*-Q4_K_M.gguf runs-prune/*/*.export-manifest.json muta-vm:~/adtc-prune/healed/ --zone=us-west1-b --project=muta-adtc
```
Then delete the GPU instance if it was created for this task (`gcloud compute instances delete muta-gpu --zone=us-central1-a`) — after confirming the GGUFs' sha256 on `muta-vm` match the manifests.

- [x] **Step 5: Commit manifests (weights stay untracked)**

```bash
git add model-development/prune/run_heal_sweep.sh bench/measurements/prune-20260917/training bench/measurements/prune-20260917/export
git commit -m "feat(prune): healing sweep — control + pruned candidates, pinned export manifests"
```

---

### Task 10: Promotion gate — audit, accuracy battery, judge prompts, verdict

**Files:**
- Create: `model-development/prune/accuracy_battery.py`
- Create: `bench/measurements/prune-20260917/audit-{rebuilt-28L,control-28L-…,heal-…}.json`, `battery-*.json`, `responses-*.json`, `judge-grades-*.json`, `gate-scores.json`

**Interfaces:**
- Consumes: `adtc_profiler.accuracy.run_benchmark(model_path, task=, limit=, seed=)` (inside the reference image), `bench/measurements/semifinal-20260916/scripts/generate.py` (judge prompts; expects `~/adtc-semis/subs/<name>/metadata.json`), `rubric.md`, `score_candidates.py --gate`.
- Produces: `battery-<name>.json` = `{"arc_easy": {...}, "arc_challenge": {...}, "gsm8k": {...}}` rows from the profiler's own function; `judge-grades-<name>.json` in the semi-final shape; `gate-scores.json`.

- [ ] **Step 1: Write the accuracy battery driver**

```python
# model-development/prune/accuracy_battery.py
#!/usr/bin/env python3
"""Run the profiler's own accuracy function on more tasks than the audit's ARC-Easy-50.

Runs INSIDE the reference image so lm-eval, llama-cpp-python and their versions are the
audit's. Usage (on muta-vm):
  sudo docker run --rm -v ~/adtc-prune:/w -v ~/adtc-prune/hfcache:/root/.cache/huggingface \
    --entrypoint python adtc-profiler:latest /w/accuracy_battery.py \
    --model /w/subs/heal-21L-contiguous-lr5e5-1000/model/heal-21L-contiguous-lr5e5-1000-Q4_K_M.gguf \
    --tasks arc_easy:500,arc_challenge:100,gsm8k:40 --output /w/artifacts/battery-heal-21L-contiguous-lr5e5-1000.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_tasks(spec: str) -> list[tuple[str, int]]:
    out = []
    for item in spec.split(","):
        name, limit = item.split(":")
        out.append((name.strip(), int(limit)))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--tasks", default="arc_easy:500,arc_challenge:100,gsm8k:40")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from adtc_profiler import accuracy

    result: dict = {"model": str(args.model), "seed": args.seed}
    for task, limit in parse_tasks(args.tasks):
        row = accuracy.run_benchmark(args.model, task=task, limit=limit, seed=args.seed)
        result[task] = row
        print(json.dumps(row), flush=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
```
Test (append to `test_prune_helpers.py`):
```python
accuracy_battery = _load("accuracy_battery")


def test_parse_tasks_splits_name_and_limit():
    assert accuracy_battery.parse_tasks("arc_easy:500, gsm8k:40") == [("arc_easy", 500), ("gsm8k", 40)]
```
Run: `python3 -m pytest model-development/prune/test_prune_helpers.py -v -k parse_tasks` → PASS.

- [ ] **Step 2: Build submission dirs for every healed file and the control (muta-vm)**

```bash
gcloud compute scp model-development/prune/screen_metadata.py model-development/prune/accuracy_battery.py model-development/prune/run_screen.sh muta-vm:~/adtc-prune/ --zone=us-west1-b --project=muta-adtc
gcloud compute ssh muta-vm --zone=us-west1-b --project=muta-adtc --command='cd ~/adtc-prune && for g in healed/*-Q4_K_M.gguf; do n=$(basename $g -Q4_K_M.gguf); python3 screen_metadata.py --base ~/adtc-semis/subs/qwen25-1.5b/metadata.json --gguf $g --manifest healed/$n.export-manifest.json --out subs/$n --link; done; ls subs'
```
Expected: `subs/control-28L-hybrid-lr5e5-1000`, `subs/heal-…` each with `metadata.json` whose `parameters_estimate` matches its export manifest.

- [ ] **Step 3: Audits (score-of-record), sequential**

```bash
gcloud compute ssh muta-vm --zone=us-west1-b --project=muta-adtc --command='cd ~/adtc-prune && nohup ./run_screen.sh > logs/gate-audits.log 2>&1 &'
```
`run_screen.sh` skips the eight unhealed audits (their JSONs exist) and audits only the new dirs. Expected: `params_match: true` for all; healed tok/s and RSS within ±3 % of the unhealed file of the same depth (healing changes weights, not shapes) — a larger gap means the export produced different tensor types; compare `tensor_types` in the export manifest with the published file's.

- [ ] **Step 4: Accuracy battery, sequential, after the audits finish**

```bash
gcloud compute ssh muta-vm --zone=us-west1-b --project=muta-adtc --command='cd ~/adtc-prune && for d in subs/rebuilt-28L subs/control-* subs/heal-*; do [ -d $d ] || continue; s=$(basename $d); m=$(ls $d/model/*.gguf); sudo docker run --rm -v ~/adtc-prune:/w -v ~/adtc-prune/hfcache:/root/.cache/huggingface --entrypoint python adtc-profiler:latest /w/accuracy_battery.py --model /w/${m#$HOME/adtc-prune/} --tasks arc_easy:500,arc_challenge:100,gsm8k:40 --output /w/artifacts/battery-$s.json > logs/battery-$s.log 2>&1; done; echo BATTERY_DONE' 
```
Also run it once for the published file (`~/adtc-semis/subs/qwen25-1.5b/model/…gguf` → `battery-published-28L.json`). Expected runtime: ARC-Easy-500 + ARC-Challenge-100 are loglikelihood (minutes); GSM8K-40 is generative at 6–9 tok/s (≈ 20–30 min per model).

- [ ] **Step 5: Judge prompts, sequential, same protocol as RESULTS.md 2026-09-16**

For each candidate `s` (plus `control-28L-hybrid-lr5e5-1000`): copy `subs/$s` to `~/adtc-semis/subs/$s`, then `python3 ~/adtc-semis/generate.py $s` (greedy, seed 42, 1536 tokens, reference image llama-server). Copy `responses-$s.json` into `bench/measurements/prune-20260917/`. Grade each file with a fresh-context LLM judge given `bench/measurements/semifinal-20260916/rubric.md`, blind labels, the same calibration instruction used on 2026-09-16, writing `judge-grades-$s.json` (`{"model_label", "scores", "rationale"}`). Reuse the published file's existing grades (`judge-grades-qwen25-1.5b.json` → copy as `judge-grades-published-28L.json`).

- [ ] **Step 6: Score the gate**

```bash
cp bench/measurements/semifinal-20260916/audit-qwen25-1.5b.json bench/measurements/prune-20260917/audit-published-28L.json
python3 model-development/prune/score_candidates.py --dir bench/measurements/prune-20260917 \
  --control bench/measurements/prune-20260917/audit-published-28L.json --gate \
  --out bench/measurements/prune-20260917/gate-scores.json
```
Expected: one verdict per healed candidate with the four checks. The decision rule is the spec's: promote only if `arc500_total`, `judge_total`, `gsm8k` and `params_match` are all true; ties or a single failed check keep the published file.

- [ ] **Step 7: RESULTS.md entry and commit**

Add `## 2026-09-1x — depth-pruning healing gate` to `RESULTS.md` with: the exact healing recipe, per-candidate table (layers, policy, LR, tok/s, peak RSS, ARC-50, ARC-500, ARC-C-100, GSM8K-40, judge %, S_total(arc500), S_total(judge), verdict), the control-vs-published comparison (isolates the data change), and the decision. Add scored rows to `bench/optimization-log.md` in its existing column format.

```bash
git add model-development/prune/accuracy_battery.py model-development/prune/test_prune_helpers.py \
        bench/measurements/prune-20260917 RESULTS.md bench/optimization-log.md
git commit -m "feat(prune): healing gate — audits, accuracy battery, judge prompts, verdict"
```

---

### Task 11: Finalise the winner (only if a verdict says promote) and document

**Files:**
- Create: `docs/depth-pruning.md`
- Modify (promotion only): `runtime/model-catalog.json`, `docs/model-selection.md`, `muta-iq/fetch_qwen25.sh`, `muta-iq/metadata.json`, `muta-iq/REPORT.md`, the HF model card
- Modify: `RESULTS.md`

**Interfaces:**
- Consumes: `muta-iq/opt/scripts/bake_system_prompt.py` (`--replace-chatml plain --system FILE --set-name NAME --sampling …`), `gate-scores.json`.

- [ ] **Step 1: Write `docs/depth-pruning.md` regardless of verdict**

Contents (all facts, no placeholders): the method (BI vs angular distance, protections, why calibration comes from the healing data), the projected-vs-measured payoff table, why unhealed screening precedes GPU work, the exchange-rate break-even rule, what healing recovered and what it did not (per task type), the export-parity requirement (b10175, tied head), the metadata `parameters_estimate` trap, the KV-cache non-claim, and the rejected alternatives with their numbers (e.g. `lowest_bi` scattered removal vs contiguous blocks). Link the spec, the plan, and `bench/measurements/prune-20260917/`.

- [ ] **Step 2: If promoted — bake the tutor template and re-verify**

```bash
python3 muta-iq/opt/scripts/bake_system_prompt.py runs-prune/<winner>/<winner>-Q4_K_M.gguf \
  muta-iq/model/Muta-Tutor-Qwen2.5-1.5B-<K>L-Q4_K_M.gguf --system muta-iq/opt/eval/system_prompt.txt \
  --replace-chatml plain --set-name "Muta Tutor" --sampling "temp=0.4,top_p=0.9,min_p=0.05,penalty_repeat=1.05" --set-languages en
sha256sum muta-iq/model/Muta-Tutor-Qwen2.5-1.5B-<K>L-Q4_K_M.gguf
```
Re-run the reference audit on the baked file (template bake is metadata-only; tok/s, RSS and ARC-50 must be unchanged within noise) and the four-prompt `bench/live_prompt_battery.py` on it. Update `muta-iq/metadata.json` (`model.name`, `parameters_estimate` = the export manifest's label) and `muta-iq/fetch_qwen25.sh` (`FINAL`, `FINAL_SHA`, `FINAL_BYTES`, `HF_FILE`); upload the file to `timiiowolabi/Muta-Tutor-Qwen2.5-1.5B-ADTC-GGUF` alongside the existing one, with `training/`, `provenance/` and `pruning/` manifests (BI JSON, prune manifest, export manifest); update the model card's evaluation table with the gate numbers; then `runtime/model-catalog.json` (path, sha256, size_bytes, description with ARC/tok-s) and `docs/model-selection.md` (new row; old row kept as "superseded").

- [ ] **Step 3: If rejected — record it as a result**

In `RESULTS.md` and `docs/depth-pruning.md`: the best candidate's numbers, how far each check missed, and the exchange-rate reason (e.g. "21L needed ≤ 7.4 ARC points loss; healed loss was 9.6"). The published file remains the submission. Keep the unhealed and healed GGUFs on `muta-vm` under `~/adtc-prune/` for later experiments; note their sha256s.

- [ ] **Step 4: Commit**

```bash
git add docs/depth-pruning.md RESULTS.md   # plus the promotion-only files when applicable
git commit -m "docs(prune): depth-pruning campaign write-up and decision"
```

---

## Self-review

**Spec coverage.** BI + angular distance → Task 3; 25–40 % middle layers with protections → Tasks 1, 3, 4 (sizes 7/9/11 plus the 4 anchor); healing LoRA on remaining layers, merge into BF16, quantize to GGUF → Tasks 7–9; RAM/tok-s payoff measured, KV claim bounded → Tasks 5–6 and the payoff table; promotion criteria 1–5 → Task 6 `verdict` + Task 10; exclusion of eval data → Task 2 guard + dataset builder; score-of-record procedure → Tasks 5, 7, 10; same-day RESULTS entries → Tasks 6, 10, 11.

**Placeholders.** None: every script is given in full; the only discovery command is the GCP image-family lookup in Task 7, which prints the value to use.

**Type consistency.** `select_contiguous(block_distance, n, n_layers, protect_first, protect_last)` and `select_lowest_bi(bi, n, protect_first, protect_last)` are called with those argument orders in `block_influence.finalize`; `renumber_plan`/`kept_layer_indices` are used by both `prune_gguf_layers` and `prune_hf_layers`; `row_from_audit` rows carry `S_perf`, `S_eff`, `arc_easy_50`, `S_total_arc50`, which `break_even_accuracy_loss`, `shortlist` and `_gate_row` read; `screen_metadata.build_metadata` is reused unchanged for healed files via `--manifest <export manifest>` because both manifest kinds carry `params_count`.
