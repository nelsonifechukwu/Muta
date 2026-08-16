# BitCPM 8B SVD + TQ2_0 Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the RAM/VRAM footprint and increase prompt-processing and token-generation throughput of `muta-iq/model/bitcpm4-8b-tq2_0.gguf` by replacing selected dense ternary FFN matrices with low-rank TQ2_0 factor pairs initialized by SVD, while preserving acceptable model quality.

**Architecture:** Keep the source GGUF immutable. First build measurement, GGUF inspection, dequantization, factorization, reconstruction, and rank-selection tooling in Python. Validate quality using dense reconstructed probes that require no runtime modification. After the rank policy is proven, emit a factorized GGUF and patch the pinned llama.cpp MiniCPM loader and graph to execute each selected projection as `B(x)` followed by `A(h)`, with both factors stored as TQ2_0. Reuse existing TQ2_0 matmul kernels first. Add a fused low-rank kernel only if profiling shows that two-matmul launch/intermediate overhead materially limits TPS.

**Tech Stack:** Python 3.11+, PyTorch, NumPy, PyYAML, psutil, pytest, gguf-py from the pinned llama.cpp checkout, CMake, C++17, llama.cpp, `llama-bench`, `llama-perplexity`, GGUF, TQ2_0.

## Global Constraints

- Repository root is `muta-iq/`; all paths in this plan are relative to that root unless they start with `/`.
- Baseline model is `model/bitcpm4-8b-tq2_0.gguf` and MUST remain byte-for-byte unchanged.
- Record the source model SHA256 before any experiment and include it in every generated manifest.
- Pin one exact llama.cpp commit in `vendor/llama.cpp.commit`; do not benchmark different commits against each other.
- MVP compression scope is FFN only: `ffn_gate`, `ffn_up`, and `ffn_down` for all 32 transformer layers.
- Do not factorize K or V in the MVP. Their output dimension is too small to produce a useful TQ2_0 low-rank storage win when factor rank must align to 256.
- Q and O are Phase 2 candidates only after FFN-only passes quality and throughput gates.
- Candidate factor ranks MUST be positive multiples of 256 because TQ2_0 quantizes in 256-value blocks.
- MVP candidate ranks are exactly `[1024, 1280, 1536, 1792, 2048, 2304, 2560]`.
- Matrix convention in Python is `W[out, in] = A[out, r] @ B[r, in]`.
- GGML tensor storage convention is `[in, out]`. Therefore B is stored as `[in, r]` and A is stored as `[r, out]`.
- Both low-rank factors MUST be quantized to TQ2_0 before final quality evaluation. FP16/BF16 factors are diagnostic only and are not release candidates.
- Reuse existing TQ2_0 matmul execution for the MVP. Do not build a custom fused kernel before the two-matmul path has passed quality gates and shown a plausible bandwidth reduction.
- Primary correctness target is CPU plus one accelerator backend. Multi-GPU tensor splitting is out of MVP scope and must not be claimed as supported until tested explicitly.
- All benchmarks must use identical llama.cpp commit, build type, backend flags, thread count, context settings, prompt length, generation length, and repetitions for baseline and candidate.
- Every benchmark JSON must include model SHA256, git commit, command line, hostname, CPU model, accelerator model, driver/runtime versions when available, and timestamp.
- Quality gates are engineering targets, not assumptions: conservative relative perplexity <= 1.015x baseline; balanced <= 1.03x; aggressive <= 1.05x.
- Balanced performance targets: file size <= 0.72x baseline, prompt-processing TPS >= 1.10x baseline, token-generation TPS >= 1.20x baseline, and peak model-process RSS <= 0.80x baseline under the same context settings.
- If the balanced target misses TPS but passes size and quality, profile before changing rank policy. If matmul time falls but launch/intermediate overhead dominates, proceed to the optional fused-kernel task.
- No generated artifact replaces the source GGUF. Generated files live under `artifacts/`.

---

## File Map

Create these focused files:

```text
pyproject.toml
configs/svd_ffn.yaml
src/bitcpm_svd/__init__.py
src/bitcpm_svd/types.py
src/bitcpm_svd/tq2.py
src/bitcpm_svd/gguf_io.py
src/bitcpm_svd/factorize.py
src/bitcpm_svd/rank_policy.py
src/bitcpm_svd/rewrite.py
src/bitcpm_svd/benchmark.py
src/bitcpm_svd/manifest.py
scripts/inspect_model.py
scripts/benchmark_model.py
scripts/analyze_spectra.py
scripts/build_dense_svd_probe.py
scripts/measure_sensitivity.py
scripts/select_rank_manifest.py
scripts/build_factorized_gguf.py
scripts/evaluate_quality.py
scripts/profile_factorized.py
scripts/prepare_eval_corpus.py
tests/test_tq2.py
tests/test_factorization.py
tests/test_rank_policy.py
tests/test_gguf_io.py
tests/test_rewrite.py
tests/test_manifest.py
tests/fixtures/ppl-smoke.txt
vendor/llama.cpp.commit
results/.gitkeep
artifacts/.gitkeep
```

Modify these files in the pinned llama.cpp checkout for the factorized runtime:

```text
vendor/llama.cpp/src/llama-arch.h
vendor/llama.cpp/src/llama-arch.cpp
vendor/llama.cpp/src/llama-model.h
vendor/llama.cpp/src/models/minicpm.cpp
```

Expected result tree:

```text
results/
  baseline/system.json
  baseline/llama_bench.json
  baseline/memory.json
  baseline/perplexity.json
  spectra/index.json
  sensitivity/layers.jsonl
  rank_sweep/<variant>.json
  final/benchmark.json
  final/quality.json
  final/profile.json
artifacts/
  dense-probes/
  bitcpm4-8b-svd-ffn-conservative-tq2_0.gguf
  bitcpm4-8b-svd-ffn-balanced-tq2_0.gguf
  bitcpm4-8b-svd-ffn-aggressive-tq2_0.gguf
  bitcpm4-8b-svd-ffn-<policy>.manifest.json
```

## Data Model and Naming Contract

Use these Python types in `src/bitcpm_svd/types.py` and keep their names stable across all tasks:

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Projection = Literal["ffn_gate", "ffn_up", "ffn_down", "attn_q", "attn_o"]

@dataclass(frozen=True)
class TensorKey:
    layer: int
    projection: Projection
    dense_name: str
    in_features: int
    out_features: int

@dataclass(frozen=True)
class FactorizationMetrics:
    rank: int
    fp_relative_fro_error: float
    tq2_relative_fro_error: float
    original_bytes_est: int
    factor_bytes_est: int

@dataclass(frozen=True)
class RankChoice:
    layer: int
    projection: Projection
    rank: int
    score: float

@dataclass(frozen=True)
class BenchmarkResult:
    model: Path
    sha256: str
    pp_tps: float
    tg_tps: float
    peak_rss_bytes: int
    file_size_bytes: int
```

Use these factor tensor names in GGUF:

```text
blk.N.ffn_gate_svd_b.weight
blk.N.ffn_gate_svd_a.weight
blk.N.ffn_up_svd_b.weight
blk.N.ffn_up_svd_a.weight
blk.N.ffn_down_svd_b.weight
blk.N.ffn_down_svd_a.weight
```

Custom GGUF metadata keys:

```text
muta.svd.version = 1
muta.svd.base_sha256 = <64 lowercase hex chars>
muta.svd.factor_dtype = "TQ2_0"
muta.svd.algorithm = "balanced-svd"
muta.svd.ffn_gate.ranks = [32 integer ranks]
muta.svd.ffn_up.ranks = [32 integer ranks]
muta.svd.ffn_down.ranks = [32 integer ranks]
```

For each factorized projection, omit the original dense tensor from the final GGUF. All unrelated tensors must be copied with their original quantized payload and GGUF tensor type.

---

### Task 1: Reproducible environment, model fingerprint, and llama.cpp pin

**Files:**
- Create: `pyproject.toml`
- Create: `configs/svd_ffn.yaml`
- Create: `scripts/inspect_model.py`
- Create: `vendor/llama.cpp.commit`
- Create: `results/.gitkeep`
- Create: `artifacts/.gitkeep`

**Interfaces:**
- Consumes: `model/bitcpm4-8b-tq2_0.gguf`
- Produces: deterministic Python environment, pinned llama.cpp revision, `results/baseline/model.json`, source SHA256.

- [ ] **Step 1: Assert the baseline exists and fingerprint it**

Run:

```bash
test -f model/bitcpm4-8b-tq2_0.gguf
sha256sum model/bitcpm4-8b-tq2_0.gguf | tee results/model.sha256
stat -c '%s' model/bitcpm4-8b-tq2_0.gguf | tee results/model.bytes
```

Expected: one SHA256 line and one positive byte count. Never write to this file.

- [ ] **Step 2: Create the Python package definition**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=75", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "bitcpm-svd"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "numpy>=2.0",
  "torch>=2.4",
  "PyYAML>=6.0",
  "psutil>=6.0",
]

[project.optional-dependencies]
test = ["pytest>=8.3"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src", "vendor/llama.cpp/gguf-py"]
```

Install:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e '.[test]'
```

- [ ] **Step 3: Pin llama.cpp**

If `vendor/llama.cpp` does not exist:

```bash
mkdir -p vendor
git clone https://github.com/ggml-org/llama.cpp.git vendor/llama.cpp
```

Record the exact revision:

```bash
git -C vendor/llama.cpp rev-parse HEAD | tee vendor/llama.cpp.commit
```

Do not update the checkout after baseline measurements begin.

- [ ] **Step 4: Build baseline tools in Release mode**

CPU build:

```bash
cmake -S vendor/llama.cpp -B vendor/llama.cpp/build -DCMAKE_BUILD_TYPE=Release
cmake --build vendor/llama.cpp/build -j --target llama-cli llama-bench llama-perplexity
```

For an NVIDIA benchmark host, use a separate build directory and keep it fixed for every compared model:

```bash
cmake -S vendor/llama.cpp -B vendor/llama.cpp/build-cuda -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=ON
cmake --build vendor/llama.cpp/build-cuda -j --target llama-cli llama-bench llama-perplexity
```

- [ ] **Step 5: Create the experiment configuration**

Create `configs/svd_ffn.yaml`:

```yaml
model: model/bitcpm4-8b-tq2_0.gguf
seed: 17
scope:
  projections: [ffn_gate, ffn_up, ffn_down]
  layers: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31]
ranks: [1024, 1280, 1536, 1792, 2048, 2304, 2560]
probe_rank: 1536
policies:
  conservative:
    max_relative_ppl_ratio: 1.015
    max_file_size_ratio: 0.82
  balanced:
    max_relative_ppl_ratio: 1.03
    max_file_size_ratio: 0.72
    min_pp_speedup: 1.10
    min_tg_speedup: 1.20
    max_peak_rss_ratio: 0.80
  aggressive:
    max_relative_ppl_ratio: 1.05
    max_file_size_ratio: 0.62
benchmark:
  prompt_tokens: [512, 2048]
  generation_tokens: [128, 256]
  repetitions: 5
quality:
  smoke_corpus: tests/fixtures/ppl-smoke.txt
  full_corpus: data/eval/wiki.test.raw
```

- [ ] **Step 6: Implement GGUF metadata inspection**

`scripts/inspect_model.py` must use `gguf.GGUFReader` and emit JSON containing: architecture, tensor count, tensor names, tensor shapes, tensor GGML types, metadata keys, file bytes, and SHA256. It must assert:

```python
assert architecture == "minicpm"
assert len([n for n in tensor_names if n.startswith("blk.")]) > 0
assert sha256_from_file == sha256_from_results_file
```

Run:

```bash
PYTHONPATH=vendor/llama.cpp/gguf-py:src python scripts/inspect_model.py \
  --model model/bitcpm4-8b-tq2_0.gguf \
  --out results/baseline/model.json
```

- [ ] **Step 7: Confirm the actual target tensor names and shapes before coding against assumptions**

Run:

```bash
python - <<'PY'
import json
p = json.load(open('results/baseline/model.json'))
for t in p['tensors']:
    if any(k in t['name'] for k in ('ffn_gate', 'ffn_up', 'ffn_down', 'attn_q', 'attn_k', 'attn_v', 'attn_output')):
        print(t['name'], t['shape'], t['type'])
PY
```

Acceptance: all 32 layers expose the three FFN tensors; every selected dense tensor has dimensions matching the MiniCPM architecture. If naming differs, update only the centralized mapping in `gguf_io.py` in Task 3, not downstream code.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml configs/svd_ffn.yaml scripts/inspect_model.py vendor/llama.cpp.commit results/.gitkeep artifacts/.gitkeep
git commit -m "chore: pin BitCPM SVD experiment environment"
```

---

### Task 2: Baseline quality, TPS, and peak-memory harness

**Files:**
- Create: `src/bitcpm_svd/benchmark.py`
- Create: `scripts/benchmark_model.py`
- Create: `scripts/evaluate_quality.py`
- Create: `scripts/prepare_eval_corpus.py`
- Create: `tests/fixtures/ppl-smoke.txt`

**Interfaces:**
- Produces: `run_llama_bench(...) -> list[dict]`, `measure_peak_rss(...) -> int`, baseline benchmark JSON, baseline perplexity JSON.

- [ ] **Step 1: Add a deterministic smoke corpus**

Generate a repository-owned synthetic corpus so smoke evaluation never depends on network access:

```bash
python - <<'PY'
from pathlib import Path
lines = [
    "Singular value decomposition represents a matrix using orthogonal directions ordered by captured energy.",
    "A low rank approximation trades reconstruction accuracy for fewer parameters and less memory traffic.",
    "Quantized inference depends on data layout, block size, kernel shape, and memory bandwidth as well as arithmetic count.",
    "The benchmark must compare the baseline and candidate with the same executable, backend, context, and thread settings.",
    "Machine learning systems should separate algorithmic quality experiments from runtime engineering experiments.",
    "A deterministic evaluation corpus makes regressions easier to reproduce and attribute to a specific code change.",
    "For autoregressive decoding, weight bandwidth often matters because each generated token reuses the full model weights.",
    "Prompt processing uses larger matrix multiplications and may respond differently to low rank factorization than decoding.",
    "The quick brown fox jumps over the lazy dog while a second process records latency, memory, and throughput statistics.",
    "A robust experiment records source hashes, software revisions, hardware information, commands, and numerical results.",
]
text = "\n".join(lines * 128) + "\n"
out = Path("tests/fixtures/ppl-smoke.txt")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(text, encoding="utf-8")
assert out.stat().st_size >= 8192
PY
```

Commit this generated file.

- [ ] **Step 2: Write tests for llama-bench JSON parsing**

Create `tests/test_benchmark.py`:

```python
from bitcpm_svd.benchmark import extract_speed_metrics


def test_extract_speed_metrics():
    rows = [
        {"n_prompt": 512, "n_gen": 0, "avg_ts": 1200.0},
        {"n_prompt": 0, "n_gen": 128, "avg_ts": 42.0},
    ]
    out = extract_speed_metrics(rows)
    assert out["pp512"] == 1200.0
    assert out["tg128"] == 42.0
```

Run:

```bash
pytest tests/test_benchmark.py::test_extract_speed_metrics -v
```

Expected: FAIL because the module/function does not exist.

- [ ] **Step 3: Implement benchmark parsing and subprocess RSS polling**

Implement in `src/bitcpm_svd/benchmark.py`:

```python
def extract_speed_metrics(rows: list[dict]) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in rows:
        if int(row.get("n_prompt", 0)) > 0 and int(row.get("n_gen", 0)) == 0:
            out[f"pp{int(row['n_prompt'])}"] = float(row["avg_ts"])
        if int(row.get("n_prompt", 0)) == 0 and int(row.get("n_gen", 0)) > 0:
            out[f"tg{int(row['n_gen'])}"] = float(row["avg_ts"])
    return out
```

Implement `measure_peak_rss(command: list[str]) -> tuple[int, int, str, str]` with `subprocess.Popen` plus `psutil.Process(pid).memory_info().rss` polling every 20 ms until exit. Return peak RSS, return code, stdout, stderr. Include child-process RSS recursively.

Run:

```bash
pytest tests/test_benchmark.py -v
```

Expected: PASS.

- [ ] **Step 4: Implement the benchmark script**

`scripts/benchmark_model.py` must:

1. Read `configs/svd_ffn.yaml`.
2. Invoke the pinned `llama-bench` executable with `-o json`.
3. Run prompt-only cases for 512 and 2048 tokens.
4. Run generation-only cases for 128 and 256 tokens.
5. Use 5 repetitions.
6. Record exact command line and environment metadata.
7. Run one representative `llama-cli` command under RSS polling using the same backend.
8. Write one JSON object to the requested output path.

Baseline command shape:

```bash
vendor/llama.cpp/build/bin/llama-bench \
  -m model/bitcpm4-8b-tq2_0.gguf \
  -p 512,2048 \
  -n 128,256 \
  -r 5 \
  -o json
```

Use the backend-specific build directory selected in Task 1 for every later comparison.

- [ ] **Step 5: Prepare the full quality corpus reproducibly**

Create `configs/eval_corpus.yaml` with a pinned WikiText-2 test-file mirror and verified SHA256:

```yaml
url: https://raw.githubusercontent.com/pytorch/examples/main/word_language_model/data/wikitext-2/test.txt
sha256: d790b833ef8cf03a90db7bf1271b7520b83c45ce07ba3c1a9699df81e239eca0
out: data/eval/wiki.test.raw
bytes: 1256449
```

`scripts/prepare_eval_corpus.py` must read this file, download with Python `urllib.request` only when output is absent, verify both byte count and SHA256, and delete an invalid download before exiting nonzero. Run:

```bash
python scripts/prepare_eval_corpus.py --config configs/eval_corpus.yaml
sha256sum data/eval/wiki.test.raw
```

Expected SHA256: `d790b833ef8cf03a90db7bf1271b7520b83c45ce07ba3c1a9699df81e239eca0`. If the benchmark host has no network, copy this exact verified file onto the host and rerun the checksum command.

- [ ] **Step 6: Implement perplexity evaluation**

`scripts/evaluate_quality.py` executes:

```bash
vendor/llama.cpp/build/bin/llama-perplexity \
  -m model/bitcpm4-8b-tq2_0.gguf \
  -f tests/fixtures/ppl-smoke.txt
```

and parses the final reported perplexity into JSON. It must also support `--corpus data/eval/wiki.test.raw`.

- [ ] **Step 7: Establish baseline numbers**

Run:

```bash
python scripts/benchmark_model.py \
  --model model/bitcpm4-8b-tq2_0.gguf \
  --config configs/svd_ffn.yaml \
  --out results/baseline/llama_bench.json

python scripts/evaluate_quality.py \
  --model model/bitcpm4-8b-tq2_0.gguf \
  --corpus tests/fixtures/ppl-smoke.txt \
  --out results/baseline/perplexity-smoke.json
```

Acceptance: baseline output contains finite positive PP TPS, TG TPS, peak RSS, file size, and perplexity.

- [ ] **Step 8: Commit**

```bash
git add src/bitcpm_svd/benchmark.py scripts/benchmark_model.py scripts/evaluate_quality.py scripts/prepare_eval_corpus.py configs/eval_corpus.yaml tests/test_benchmark.py tests/fixtures/ppl-smoke.txt
git commit -m "feat: add reproducible BitCPM baseline benchmarks"
```

---

### Task 3: Exact TQ2_0 decode/encode and GGUF tensor access

**Files:**
- Create: `src/bitcpm_svd/tq2.py`
- Create: `src/bitcpm_svd/gguf_io.py`
- Create: `tests/test_tq2.py`
- Create: `tests/test_gguf_io.py`

**Interfaces:**
- Produces: `dequantize_tq2(raw, shape) -> np.ndarray`, `quantize_tq2(x) -> np.ndarray`, `load_dense_matrix(reader, key) -> np.ndarray`, `iter_target_tensors(reader) -> list[TensorKey]`.

- [ ] **Step 1: Write a TQ2_0 round-trip test against llama.cpp gguf-py**

Test a deterministic `(256, 4)` float32 array. Quantize using llama.cpp's `gguf.quants.TQ2_0.quantize`, dequantize with the project wrapper, and assert exact equality with llama.cpp's dequantizer output.

```python
import numpy as np
from gguf.quants import TQ2_0
from bitcpm_svd.tq2 import dequantize_tq2


def test_dequantizer_matches_gguf_py():
    x = np.linspace(-2.0, 2.0, 1024, dtype=np.float32).reshape(4, 256)
    q = TQ2_0.quantize(x)
    expected = TQ2_0.dequantize(q)
    actual = dequantize_tq2(q, expected.shape)
    np.testing.assert_array_equal(actual, expected)
```

Run and confirm FAIL before implementation.

- [ ] **Step 2: Implement TQ2 wrappers by delegating to pinned gguf-py**

Do not reimplement the bit packing independently in the MVP. In `tq2.py`, wrap the pinned implementation and assert the last dimension is divisible by 256 before quantization.

```python
def quantize_tq2(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32, order="C")
    if x.shape[-1] % 256 != 0:
        raise ValueError(f"TQ2_0 requires last dimension multiple of 256, got {x.shape}")
    return TQ2_0.quantize(x)
```

Add the equivalent dequantize wrapper.

- [ ] **Step 3: Add target tensor-name mapping tests**

Use the actual names found in `results/baseline/model.json`. Assert exactly 96 FFN target tensors are enumerated, three per layer for 32 layers, and that every `TensorKey` reports correct input/output dimensions.

- [ ] **Step 4: Implement GGUF access**

`gguf_io.py` must:

1. Open with `GGUFReader` using memory mapping.
2. Centralize actual MiniCPM tensor names in one function.
3. Convert GGML stored `[in, out]` data to Python `W[out, in]` after dequantization.
4. Expose original tensor GGML type and raw payload for byte-preserving copy paths.
5. Refuse to silently cast unsupported quantization types when a tensor is expected to be TQ2_0.

- [ ] **Step 5: Verify a real tensor round trip**

Select `blk.0.ffn_gate.weight` or its exact discovered equivalent. Decode it, quantize it back to TQ2_0, decode again, and record relative Frobenius difference. The second decode need not equal the original because re-quantization occurs, but shape and finite-value assertions must pass.

Run:

```bash
pytest tests/test_tq2.py tests/test_gguf_io.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/bitcpm_svd/tq2.py src/bitcpm_svd/gguf_io.py tests/test_tq2.py tests/test_gguf_io.py
git commit -m "feat: add exact TQ2 tensor IO"
```

---

### Task 4: Low-rank SVD, factor balancing, and quantized reconstruction metrics

**Files:**
- Create: `src/bitcpm_svd/factorize.py`
- Create: `src/bitcpm_svd/types.py`
- Create: `tests/test_factorization.py`

**Interfaces:**
- Produces: `factorize_balanced(W, rank, seed) -> tuple[np.ndarray, np.ndarray]`, `quantized_factorization(W, rank, seed) -> tuple[Aq, Bq, metrics]`.

- [ ] **Step 1: Write the exact low-rank reconstruction test**

```python
import numpy as np
from bitcpm_svd.factorize import factorize_balanced


def test_balanced_svd_preserves_exact_rank_matrix():
    rng = np.random.default_rng(17)
    left = rng.normal(size=(128, 16)).astype(np.float32)
    right = rng.normal(size=(16, 96)).astype(np.float32)
    w = left @ right
    a, b = factorize_balanced(w, rank=16, seed=17)
    rel = np.linalg.norm(w - a @ b) / np.linalg.norm(w)
    assert rel < 1e-4
```

Run and confirm FAIL.

- [ ] **Step 2: Implement truncated randomized SVD**

For large FFN matrices, do not call full `torch.linalg.svd`. Use `torch.svd_lowrank` with deterministic seed and oversampling `q = min(rank + 64, min(W.shape))`, then sort singular values descending if needed.

Construct factors as:

```python
sqrt_s = torch.sqrt(s[:rank])
a = u[:, :rank] * sqrt_s.unsqueeze(0)
b = sqrt_s.unsqueeze(1) * v[:, :rank].T
```

- [ ] **Step 3: Implement diagonal latent balancing before quantization**

For each latent component `j`:

```python
an = torch.linalg.vector_norm(a, dim=0).clamp_min(1e-12)
bn = torch.linalg.vector_norm(b, dim=1).clamp_min(1e-12)
scale = torch.sqrt(bn / an)
a = a * scale.unsqueeze(0)
b = b / scale.unsqueeze(1)
```

Test that `a @ b` is unchanged within `1e-5` relative error before and after balancing.

- [ ] **Step 4: Quantize both factors and compute true post-TQ2 error**

Because gguf-py represents a 2D GGML tensor as a NumPy array with reversed logical dimensions, quantize the Python factors in `[out, in]` ndarray form and verify that the final NumPy axis maps to GGML `ne0`:

```python
# Python ndarray shape is [out, r]. GGUF/GGML logical dimensions are [r, out].
# The last NumPy axis maps to GGML ne0, so rank must be divisible by 256.
q_a_storage = quantize_tq2(a.copy())
a_q = dequantize_tq2(q_a_storage, a.shape)

# Python ndarray shape is [r, in]. GGUF/GGML logical dimensions are [in, r].
q_b_storage = quantize_tq2(b.copy())
b_q = dequantize_tq2(q_b_storage, b.shape)
```

Before finalizing this code, assert with the real gguf-py API which ndarray axis represents GGML `ne0`. Encode that convention once in `gguf_io.py` and test it. The invariant is that the quantized contiguous block dimension must be divisible by 256.

Compute:

```python
fp_err = norm(W - A @ B) / norm(W)
tq2_err = norm(W - Aq @ Bq) / norm(W)
```

- [ ] **Step 5: Add rank validation**

Reject rank when:

```python
rank <= 0
rank % 256 != 0
rank >= min(in_features, out_features)
rank * (in_features + out_features) >= in_features * out_features
```

The last check prevents a factorization that increases raw weight count.

- [ ] **Step 6: Run tests**

```bash
pytest tests/test_factorization.py tests/test_tq2.py -v
```

Expected: PASS on CPU.

- [ ] **Step 7: Commit**

```bash
git add src/bitcpm_svd/types.py src/bitcpm_svd/factorize.py tests/test_factorization.py
git commit -m "feat: add balanced quantized SVD factorization"
```

---

### Task 5: Spectral analysis and rank-cost report for all FFN tensors

**Files:**
- Create: `scripts/analyze_spectra.py`
- Create: `results/spectra/.gitkeep`

**Interfaces:**
- Consumes: 96 decoded FFN matrices.
- Produces: `results/spectra/index.json` and one compressed spectrum summary per tensor.

- [ ] **Step 1: Implement spectral-energy metrics**

For each target tensor and candidate rank, record:

```text
rank
cumulative_energy = sum(s[:r]^2) / sum(s^2)
fp_relative_fro_error
post_tq2_relative_fro_error
original_parameter_count
factor_parameter_count
parameter_ratio
estimated_tq2_byte_ratio
```

Do not materialize all 96 matrices at once. Process one tensor, write its result, free CPU/GPU buffers, then continue.

- [ ] **Step 2: Add analytic break-even assertions**

For `W[out, in]`, factorization saves weight count iff:

```text
r * (in + out) < in * out
```

Add unit assertions for the discovered FFN dimensions. For 4096 x 16384, candidate rank 1024 must report a factor/original parameter ratio of 0.3125 and rank 2560 must remain below break-even.

- [ ] **Step 3: Run spectral analysis**

```bash
PYTHONPATH=vendor/llama.cpp/gguf-py:src python scripts/analyze_spectra.py \
  --model model/bitcpm4-8b-tq2_0.gguf \
  --config configs/svd_ffn.yaml \
  --out results/spectra/index.json
```

Acceptance: all 96 target tensors have seven candidate-rank entries, finite errors, and monotonically non-increasing FP SVD reconstruction error as rank rises.

- [ ] **Step 4: Generate a machine-readable recommendation summary**

For each tensor, report the smallest candidate rank satisfying each local TQ2 reconstruction threshold: 0.10, 0.075, 0.05, and 0.035 relative Frobenius error. These thresholds guide later sweeps but do not override perplexity measurements.

- [ ] **Step 5: Commit**

```bash
git add scripts/analyze_spectra.py results/spectra/.gitkeep
git commit -m "feat: analyze BitCPM FFN low-rank spectra"
```

---

### Task 6: Dense reconstructed SVD probes for quality isolation

**Files:**
- Create: `src/bitcpm_svd/rewrite.py`
- Create: `scripts/build_dense_svd_probe.py`
- Create: `tests/test_rewrite.py`

**Interfaces:**
- Produces: a standard GGUF that keeps the original tensor name/shape but replaces selected `W` with `TQ2_0(Aq @ Bq)`. This stage does not save RAM or TPS. Its purpose is to measure quality loss before runtime changes.

- [ ] **Step 1: Write a byte-preservation test for untouched tensors**

Build a tiny synthetic GGUF fixture with two tensors. Replace one and copy the other. Assert the untouched tensor has identical raw bytes and identical GGML type in source and output.

- [ ] **Step 2: Implement `rewrite_dense_probe`**

Signature:

```python
def rewrite_dense_probe(
    source: Path,
    destination: Path,
    replacements: dict[str, tuple[np.ndarray, int]],
    base_sha256: str,
) -> None:
    ...
```

For each replacement tuple `(dense_float32, rank)`, quantize reconstructed dense `Aq @ Bq` back to TQ2_0 and store under the original tensor name and original shape. Copy all non-replaced tensors in original order with original raw quantized payload.

- [ ] **Step 3: Make the writer atomic**

Write to `destination.with_suffix(destination.suffix + ".tmp")`, fsync, then rename. Delete temporary file on exception. Never modify source in place.

- [ ] **Step 4: Build single-layer sensitivity probes**

For each layer `0..31`, build one GGUF where all three FFN tensors in that layer are replaced at `probe_rank: 1536` and every other tensor is unchanged.

File naming:

```text
artifacts/dense-probes/layer-00-r1536.gguf
...
artifacts/dense-probes/layer-31-r1536.gguf
```

Run one layer first and verify it loads:

```bash
vendor/llama.cpp/build/bin/llama-cli \
  -m artifacts/dense-probes/layer-00-r1536.gguf \
  -p 'The capital of France is' \
  -n 8 \
  --temp 0
```

- [ ] **Step 5: Build global uniform-rank probes**

Build full FFN replacement models for ranks 1024, 1536, 2048, and 2560. These models remain dense after reconstruction, so file size is not expected to improve.

- [ ] **Step 6: Run smoke perplexity for all probes**

```bash
for m in artifacts/dense-probes/global-r*.gguf; do
  python scripts/evaluate_quality.py \
    --model "$m" \
    --corpus tests/fixtures/ppl-smoke.txt \
    --out "results/rank_sweep/$(basename "$m" .gguf).json"
done
```

Acceptance: quality loss should generally decline as rank rises. If it is non-monotonic, retain the measurements and inspect quantization error instead of assuming a bug.

- [ ] **Step 7: Commit**

```bash
git add src/bitcpm_svd/rewrite.py scripts/build_dense_svd_probe.py tests/test_rewrite.py
git commit -m "feat: add dense SVD quality probes"
```

---

### Task 7: Layer sensitivity and adaptive rank allocation

**Files:**
- Create: `scripts/measure_sensitivity.py`
- Create: `src/bitcpm_svd/rank_policy.py`
- Create: `scripts/select_rank_manifest.py`
- Create: `tests/test_rank_policy.py`

**Interfaces:**
- Produces: `results/sensitivity/layers.jsonl`; `select_ranks(...) -> list[RankChoice]`; conservative, balanced, and aggressive rank manifests.

- [ ] **Step 1: Measure each layer's quality sensitivity**

For each `layer-NN-r1536.gguf`, evaluate the smoke corpus and compute:

```text
relative_ppl = probe_ppl / baseline_ppl
sensitivity = max(relative_ppl - 1.0, 0.0)
```

Store one JSON line with layer, rank, probe perplexity, baseline perplexity, and sensitivity.

- [ ] **Step 2: Write rank allocator tests on synthetic costs**

The allocator must start every tensor at the lowest candidate rank and repeatedly buy the next rank increment with the largest benefit per added byte until the policy byte budget is exhausted.

Define upgrade benefit:

```python
benefit = sensitivity_weight * max(error_r - error_next, 0.0)
score = benefit / max(extra_bytes, 1)
```

Use `sensitivity_weight = 1.0 + 20.0 * layer_sensitivity`.

Test that a more sensitive tensor receives an equal or higher rank than an otherwise identical less-sensitive tensor under a tight budget.

- [ ] **Step 3: Implement exact byte estimates from TQ2 block layout**

Do not estimate using `2 bits * parameter_count`. Ask gguf-py for quantized byte count by quantizing a zero array of the same stored shape, or encode the pinned TQ2 block formula once and test it against gguf-py. Include metadata overhead only at final file-size validation, not per-rank optimizer cost.

- [ ] **Step 4: Produce three manifests**

Each manifest must include:

```json
{
  "schema_version": 1,
  "base_model": "model/bitcpm4-8b-tq2_0.gguf",
  "base_sha256": "...",
  "policy": "balanced",
  "factor_dtype": "TQ2_0",
  "algorithm": "balanced-svd",
  "layers": {
    "0": {"ffn_gate": 1536, "ffn_up": 1536, "ffn_down": 1792}
  }
}
```

The actual ranks come from measurements; the example structure above is not a mandated allocation.

- [ ] **Step 5: Validate each selected rank**

For every manifest entry assert:

```text
rank in candidate_ranks
rank % 256 == 0
rank < break_even_rank
projection is in MVP scope
```

- [ ] **Step 6: Run full-corpus dense-probe validation for the three manifests**

Before patching llama.cpp, reconstruct three dense probes from the manifests and run full perplexity. Reject any policy exceeding its configured relative perplexity gate. If balanced fails, promote ranks using the allocator until it passes or until file-size budget becomes impossible.

- [ ] **Step 7: Commit**

```bash
git add scripts/measure_sensitivity.py src/bitcpm_svd/rank_policy.py scripts/select_rank_manifest.py tests/test_rank_policy.py
git commit -m "feat: add sensitivity-aware FFN rank allocation"
```

---

### Task 8: Emit the custom factorized GGUF

**Files:**
- Create: `src/bitcpm_svd/manifest.py`
- Create: `scripts/build_factorized_gguf.py`
- Create: `tests/test_manifest.py`
- Extend: `src/bitcpm_svd/rewrite.py`
- Extend: `tests/test_rewrite.py`

**Interfaces:**
- Produces: final GGUF files containing factor pairs instead of selected dense FFN tensors.

- [ ] **Step 1: Test factor tensor shape conversion**

For Python `W[out=16384, in=4096]` with `r=1536`, assert emitted tensor metadata reports:

```text
B GGML logical shape: [4096, 1536]
A GGML logical shape: [1536, 16384]
```

For `ffn_down`, assert:

```text
B: [16384, r]
A: [r, 4096]
```

- [ ] **Step 2: Implement manifest validation**

`manifest.py` must verify base SHA256, 32 layer entries, legal projections, legal ranks, and policy name before any output file is opened.

- [ ] **Step 3: Implement factorized writer**

For each selected dense tensor:

1. Decode original TQ2 tensor to `W[out, in]`.
2. Run balanced SVD at manifest rank.
3. Quantize A and B independently to TQ2_0.
4. Omit original dense tensor.
5. Add `*_svd_b.weight` and `*_svd_a.weight` tensors with raw type TQ2_0.
6. Preserve all unrelated tensor payloads and metadata.
7. Add the custom `muta.svd.*` metadata keys.
8. Write atomically.

- [ ] **Step 4: Add structural validation immediately after write**

Re-open output with `GGUFReader` and assert:

```text
source dense target tensor absent
both factor tensors present
factor GGML type == TQ2_0
factor rank matches manifest
all non-target source tensor names present
muta.svd.base_sha256 matches source
```

- [ ] **Step 5: Build one minimal factorized test model**

Factorize only `blk.0.ffn_gate.weight` at rank 1536. Do not attempt to load it in unmodified llama.cpp; structural GGUF tests are sufficient at this step.

- [ ] **Step 6: Build all three policy models after runtime support lands**

The build command must be deterministic:

```bash
PYTHONPATH=vendor/llama.cpp/gguf-py:src python scripts/build_factorized_gguf.py \
  --source model/bitcpm4-8b-tq2_0.gguf \
  --manifest artifacts/bitcpm4-8b-svd-ffn-balanced.manifest.json \
  --output artifacts/bitcpm4-8b-svd-ffn-balanced-tq2_0.gguf
```

- [ ] **Step 7: Commit**

```bash
git add src/bitcpm_svd/manifest.py src/bitcpm_svd/rewrite.py scripts/build_factorized_gguf.py tests/test_manifest.py tests/test_rewrite.py
git commit -m "feat: write factorized TQ2 BitCPM GGUF files"
```

---

### Task 9: Add SVD factor tensor schema and loader support to llama.cpp

**Files:**
- Modify: `vendor/llama.cpp/src/llama-arch.h`
- Modify: `vendor/llama.cpp/src/llama-arch.cpp`
- Modify: `vendor/llama.cpp/src/llama-model.h`
- Modify: `vendor/llama.cpp/src/models/minicpm.cpp`

**Interfaces:**
- Consumes: factor tensor names from Task 8.
- Produces: MiniCPM loader that accepts either existing dense FFN tensors or a complete SVD A/B pair per projection.

- [ ] **Step 1: Add six tensor enum values**

Add:

```cpp
LLM_TENSOR_FFN_GATE_SVD_A,
LLM_TENSOR_FFN_GATE_SVD_B,
LLM_TENSOR_FFN_UP_SVD_A,
LLM_TENSOR_FFN_UP_SVD_B,
LLM_TENSOR_FFN_DOWN_SVD_A,
LLM_TENSOR_FFN_DOWN_SVD_B,
```

Do not change the meaning of existing tensor enums.

- [ ] **Step 2: Add canonical tensor-name mappings**

Map the enums to the exact GGUF names:

```text
blk.%d.ffn_gate_svd_a.weight
blk.%d.ffn_gate_svd_b.weight
blk.%d.ffn_up_svd_a.weight
blk.%d.ffn_up_svd_b.weight
blk.%d.ffn_down_svd_a.weight
blk.%d.ffn_down_svd_b.weight
```

Register all six as repeating-layer tensors associated with `GGML_OP_MUL_MAT` so backend placement follows matrix multiplication semantics.

- [ ] **Step 3: Extend `llama_layer`**

Add nullable tensor pointers:

```cpp
ggml_tensor * ffn_gate_svd_a = nullptr;
ggml_tensor * ffn_gate_svd_b = nullptr;
ggml_tensor * ffn_up_svd_a   = nullptr;
ggml_tensor * ffn_up_svd_b   = nullptr;
ggml_tensor * ffn_down_svd_a = nullptr;
ggml_tensor * ffn_down_svd_b = nullptr;
```

- [ ] **Step 4: Implement a loader helper for dense-or-factorized projections**

Inside `minicpm.cpp`, add a local helper that inspects tensor metadata before creating tensors. Inputs: dense enum/name, A enum/name, B enum/name, expected `in_features`, expected `out_features`, and layer index.

Validation rules:

```text
Dense only: accepted.
A and B only: accepted.
Only A or only B: reject with clear error.
Dense plus A/B: reject for release-format model.
Factor type other than TQ2_0: reject for this schema version.
r <= 0: reject.
r % 256 != 0: reject.
B dimensions != [in_features, r]: reject.
A dimensions != [r, out_features]: reject.
r * (in_features + out_features) >= in_features * out_features: reject.
```

Derive `r` from tensor metadata instead of trusting only custom metadata arrays. Cross-check the array value if the `muta.svd.*.ranks` key exists.

- [ ] **Step 5: Preserve old-model compatibility**

Load the untouched baseline GGUF with the patched binary:

```bash
vendor/llama.cpp/build/bin/llama-cli \
  -m model/bitcpm4-8b-tq2_0.gguf \
  -p 'Hello' \
  -n 8 \
  --temp 0
```

Acceptance: it loads and runs exactly as before. Record the same deterministic output as the pre-patch binary for a fixed prompt and seed.

- [ ] **Step 6: Verify malformed factorized files fail early**

Generate three deliberately malformed synthetic GGUFs from the Task 8 writer test path: missing A, rank not divisible by 256, and wrong A shape. Each must fail at model load with a message naming the bad tensor and expected shape/rank rule.

- [ ] **Step 7: Commit the llama.cpp patch**

Inside the pinned checkout:

```bash
git -C vendor/llama.cpp add src/llama-arch.h src/llama-arch.cpp src/llama-model.h src/models/minicpm.cpp
git -C vendor/llama.cpp commit -m "feat: load factorized MiniCPM FFN tensors"
```

Record the new patched commit hash in the experiment manifest and keep the original upstream pin separately in `vendor/llama.cpp.upstream.commit`.

---

### Task 10: Execute factorized FFN projections in the MiniCPM graph

**Files:**
- Modify: `vendor/llama.cpp/src/models/minicpm.cpp`

**Interfaces:**
- Produces: graph path where dense projection uses one matmul and factorized projection uses `B` then `A`.

- [ ] **Step 1: Add a local projection helper**

Implement a helper with this behavior:

```cpp
ggml_tensor * build_svd_or_dense_linear(
        ggml_context * ctx0,
        ggml_tensor * dense,
        ggml_tensor * factor_b,
        ggml_tensor * factor_a,
        ggml_tensor * bias,
        ggml_tensor * x,
        int il,
        const char * cb_name) {
    ggml_tensor * y = nullptr;
    if (dense != nullptr) {
        y = build_lora_mm(dense, x);
    } else {
        GGML_ASSERT(factor_b != nullptr);
        GGML_ASSERT(factor_a != nullptr);
        ggml_tensor * h = build_lora_mm(factor_b, x);
        cb(h, "svd_hidden", il);
        y = build_lora_mm(factor_a, h);
    }
    if (bias != nullptr) {
        y = ggml_add(ctx0, y, bias);
    }
    cb(y, cb_name, il);
    return y;
}
```

Adapt the exact capture/signature to the local graph-builder class so `build_lora_mm` and `cb` are available. Preserve existing LoRA behavior for dense tensors. The SVD release path itself does not require LoRA adapters on factor tensors unless the current helper already supports them transparently.

- [ ] **Step 2: Replace the MiniCPM FFN call with explicit equivalent operations**

Preserve the exact current activation and multiplication order. For a standard gated SiLU FFN, the target structure is:

```cpp
ggml_tensor * up = build_svd_or_dense_linear(... ffn_up ..., cur, il, "ffn_up");
ggml_tensor * gate = build_svd_or_dense_linear(... ffn_gate ..., cur, il, "ffn_gate");
gate = ggml_silu(ctx0, gate);
cb(gate, "ffn_gate_silu", il);
ggml_tensor * gated = ggml_mul(ctx0, gate, up);
cb(gated, "ffn_gated", il);
cur = build_svd_or_dense_linear(... ffn_down ..., gated, il, "ffn_down");
```

Before editing, copy the exact operation order, scaling, bias, and callback behavior from the current MiniCPM `build_ffn` invocation. The patched dense path must remain graph-equivalent to upstream.

- [ ] **Step 3: Regression-test the dense graph**

With the patched binary and untouched baseline model, generate 64 tokens at temperature 0 from three fixed prompts. Compare token IDs with the unpatched pinned baseline binary. Require exact token-ID equality.

- [ ] **Step 4: Load the one-layer factorized model**

Run the minimal Task 8 model where only layer 0 gate is factorized. Acceptance: model loads, graph builds, generation completes, and no tensor shape assertion fires.

- [ ] **Step 5: Add a direct two-matmul backend sanity test**

Add a small C++ test program under `vendor/llama.cpp/tests/` that allocates deterministic float input `x`, quantized TQ2_0 factor tensors B and A with a legal compression rank such as 1024, executes `B(x)` then `A(h)` through ggml on the target backend, and compares the result with a CPU float32 reference computed from the dequantized copies of the same A and B factors. Use representative FFN dimensions for one narrow test slice if full 4096 x 16384 allocation is too expensive for a unit test. Require the backend result to satisfy the same absolute/relative tolerance used by existing quantized `GGML_OP_MUL_MAT` tests for TQ2_0. This validates factor ordering and shape conventions without introducing a non-compressing rank that the loader is required to reject.

- [ ] **Step 6: Build the three final factorized models**

Run `build_factorized_gguf.py` for conservative, balanced, and aggressive manifests. Validate all three with `llama-cli -n 8 --temp 0`.

- [ ] **Step 7: Commit**

```bash
git -C vendor/llama.cpp add src/models/minicpm.cpp
git -C vendor/llama.cpp commit -m "feat: execute low-rank TQ2 MiniCPM FFN"
```

---

### Task 11: End-to-end correctness and quality gates

**Files:**
- Extend: `scripts/evaluate_quality.py`
- Create: `results/final/.gitkeep`

**Interfaces:**
- Produces: quality comparison table and a hard pass/fail decision for each policy.

- [ ] **Step 1: Run smoke perplexity for all factorized models**

Evaluate baseline plus conservative, balanced, aggressive on exactly the same smoke corpus.

- [ ] **Step 2: Run full-corpus perplexity for candidates that pass smoke**

Compute:

```text
relative_ppl_ratio = candidate_ppl / baseline_ppl
```

Apply policy gates exactly from config.

- [ ] **Step 3: Run deterministic generation sanity tests**

Use at least six prompts covering English prose, code, arithmetic, Chinese text, long-context continuation, and instruction following. Use temperature 0. Store prompt, output, model SHA256, and command. This is diagnostic and does not replace perplexity.

- [ ] **Step 4: Verify factorized file size against manifest estimate**

Compute actual file bytes and compare with predicted factor payload bytes plus metadata/tensor-header overhead. Require prediction error <= 2% of final file size. A larger mismatch indicates duplicate dense tensors or an incorrect raw quantized write path.

- [ ] **Step 5: Select the quality-qualified candidates**

A candidate proceeds to performance benchmarking only if:

```text
model loads successfully
all selected factor tensors are TQ2_0
no selected dense tensor remains
full-corpus relative PPL meets policy gate
actual file size meets policy file-size ratio
```

- [ ] **Step 6: Commit**

```bash
git add scripts/evaluate_quality.py results/final/.gitkeep
git commit -m "test: add end-to-end factorized model quality gates"
```

---

### Task 12: TPS and peak-memory benchmark, then profile bottlenecks

**Files:**
- Extend: `src/bitcpm_svd/benchmark.py`
- Extend: `scripts/benchmark_model.py`
- Create: `scripts/profile_factorized.py`

**Interfaces:**
- Produces: `results/final/benchmark.json`, `results/final/profile.json`, decision on whether two-matmul execution is sufficient.

- [ ] **Step 1: Re-run the untouched baseline on the patched binary**

This controls for any performance change introduced by the llama.cpp patch itself. Do not compare the factorized model against a measurement from an older binary.

- [ ] **Step 2: Benchmark each quality-qualified candidate**

Use the exact same prompt lengths, generation lengths, repetitions, backend, GPU offload setting, thread count, and context size as baseline.

Record median and standard deviation for:

```text
PP512 TPS
PP2048 TPS
TG128 TPS
TG256 TPS
peak RSS bytes
file size bytes
```

- [ ] **Step 3: Compute normalized ratios**

```python
pp_speedup = candidate_pp_tps / baseline_pp_tps
tg_speedup = candidate_tg_tps / baseline_tg_tps
rss_ratio = candidate_peak_rss / baseline_peak_rss
size_ratio = candidate_file_size / baseline_file_size
```

For balanced, enforce configured gates.

- [ ] **Step 4: Profile the balanced model if TPS target fails**

`profile_factorized.py` must run the backend's available profiler or llama.cpp internal timings and aggregate time for:

```text
first factor matmul B
second factor matmul A
intermediate tensor allocation/copy
other FFN ops
attention
sampling/runtime overhead
```

On CUDA, add an optional Nsight Systems command path if installed. On CPU, use `perf stat`/`perf record` when available. The script must record which profiler was used.

- [ ] **Step 5: Make the optimization decision from profile evidence**

Use these rules:

```text
If balanced meets quality, size, RSS, PP, and TG gates: stop. Do not add a fused kernel.
If quality and size pass but both PP and TG regress: inspect matmul kernel efficiency and rank alignment before fusion.
If matmul compute time drops but launch/intermediate overhead is >= 15% of factorized FFN time: proceed to Task 14 fused kernel.
If TG improves but PP regresses: profile batched matrix shapes separately; do not assume one kernel strategy serves both.
If no candidate meets quality at useful size reduction: stop and report SVD as unsuccessful for this target/config instead of forcing a release.
```

- [ ] **Step 6: Commit**

```bash
git add src/bitcpm_svd/benchmark.py scripts/benchmark_model.py scripts/profile_factorized.py
git commit -m "perf: benchmark factorized BitCPM runtime"
```

---

### Task 13: Optional Phase 2 Q/O factorization

**Files:**
- Extend: `src/bitcpm_svd/gguf_io.py`
- Extend: `src/bitcpm_svd/rank_policy.py`
- Extend: `scripts/analyze_spectra.py`
- Extend: `scripts/build_factorized_gguf.py`
- Modify: `vendor/llama.cpp/src/llama-arch.h`
- Modify: `vendor/llama.cpp/src/llama-arch.cpp`
- Modify: `vendor/llama.cpp/src/llama-model.h`
- Modify: `vendor/llama.cpp/src/models/minicpm.cpp`

**Interfaces:**
- Trigger: execute only after an FFN-only model passes quality and shows positive TPS gain.
- Produces: optional low-rank Q and O support.

- [ ] **Step 1: Add Q/O to spectral and dense-probe analysis, not directly to final writer**

For 4096 x 4096 Q/O matrices, candidate ranks are `[768, 1024, 1280, 1536, 1792]`, all multiples of 256 and below the raw-parameter break-even rank 2048.

- [ ] **Step 2: Measure Q/O sensitivity separately**

Replace one Q or O matrix at a time in dense reconstructed probes and measure perplexity. Do not infer sensitivity from FFN results.

- [ ] **Step 3: Promote only quality-safe Q/O tensors into the manifest**

Require the combined model to remain under the selected policy's perplexity gate. Favor Q/O only if their added compression improves actual RSS/file size and does not erase TPS gains through extra sequential matmuls.

- [ ] **Step 4: Extend GGUF names, loader pointers, validation, and graph helper using the same dense-or-factor-pair contract as FFN**

Keep K and V dense.

- [ ] **Step 5: Re-run all Task 11 and Task 12 gates**

A Phase 2 model replaces the FFN-only balanced candidate only if it is strictly better on the chosen Pareto objective: lower size/RSS with no unacceptable quality loss and no lower TG TPS.

- [ ] **Step 6: Commit**

```bash
git add src/bitcpm_svd/gguf_io.py src/bitcpm_svd/rank_policy.py scripts/analyze_spectra.py scripts/build_factorized_gguf.py
git commit -m "feat: add optional low-rank attention QO support"
```

Commit the corresponding llama.cpp changes inside `vendor/llama.cpp` separately.

---

### Task 14: Optional fused TQ2 low-rank kernel

**Files:**
- Modify only backend files identified by the Task 12 profile in `vendor/llama.cpp/ggml/`.
- Extend: `scripts/profile_factorized.py`

**Interfaces:**
- Trigger: only when Task 12 shows intermediate/launch overhead >= 15% of factorized FFN time or two separate matmuls leave a clear backend bottleneck.
- Produces: backend-specific fused operation or graph optimization that avoids unnecessary materialization/launch overhead between B and A.

- [ ] **Step 1: Create a microbenchmark before kernel work**

Benchmark representative shapes independently:

```text
Gate/Up: x [4096, batch] -> B [r,4096] -> h [r,batch] -> A [16384,r]
Down: x [16384,batch] -> B [r,16384] -> h [r,batch] -> A [4096,r]
Ranks: 1024, 1536, 2048
Batch/token modes: 1, 8, 32, 128
```

Record two-matmul latency and effective bytes/token.

- [ ] **Step 2: Define the fusion success criterion**

Do not merge a kernel that only reduces microbenchmark latency. Require:

```text
>= 10% FFN projection latency improvement for batch 1 at the balanced ranks
no > 3% regression for batch 32+
end-to-end TG TPS improves >= 5% over the two-matmul factorized model
numerical output matches two-matmul TQ2 reference within the backend's existing quantized-matmul tolerance
```

- [ ] **Step 3: Implement only for the measured bottleneck backend**

Keep the generic two-matmul path as fallback. Guard the fused path by backend capability and supported shape/rank constraints.

- [ ] **Step 4: Add backend tests against the unfused reference**

Generate deterministic random inputs and compare output tensors for all representative rank/batch combinations.

- [ ] **Step 5: Re-run the complete benchmark and quality suite**

Quality should be unchanged because factor weights are identical. Confirm this with smoke perplexity and deterministic generation, then rerun PP/TG benchmark.

- [ ] **Step 6: Commit**

Commit backend kernel changes inside `vendor/llama.cpp` with a message naming the backend and operation, then record the commit in final manifest metadata.

---

### Task 15: Release artifacts, reproducibility report, and final decision

**Files:**
- Create: `README-SVD.md`
- Create: `artifacts/bitcpm4-8b-svd-ffn-<policy>.manifest.json`
- Create: `results/final/summary.json`
- Create: `results/final/summary.md`

**Interfaces:**
- Produces: reproducible release candidate or an explicit no-release result if targets are not met.

- [ ] **Step 1: Select the Pareto winner**

Compare baseline and all quality-qualified candidates on:

```text
relative perplexity
file size
peak RSS
PP512
PP2048
TG128
TG256
```

Prefer balanced policy when it meets all balanced gates. Otherwise select the best candidate that meets conservative quality and provides a real size plus TPS benefit. Do not call a model optimized if TPS regresses materially.

- [ ] **Step 2: Write final manifest with provenance**

Include:

```text
source model path and SHA256
source model file bytes
upstream llama.cpp commit
patched llama.cpp commit
Python package lock/freeze
rank for every factorized tensor
factor dtype
SVD seed and algorithm
quality corpus SHA256
benchmark commands
host hardware/software metadata
final metrics and normalized ratios
```

- [ ] **Step 3: Write `README-SVD.md` with exact reproduction commands**

Document, in order:

```text
create environment
verify source SHA256
build pinned/patched llama.cpp
run baseline
analyze spectra
build probes
measure sensitivity
select ranks
build factorized GGUF
evaluate quality
benchmark performance
```

Every command must be copy-paste runnable from repository root.

- [ ] **Step 4: Verify source immutability**

Run:

```bash
sha256sum -c results/model.sha256
```

Expected: `model/bitcpm4-8b-tq2_0.gguf: OK`.

- [ ] **Step 5: Verify release model structure**

Run `inspect_model.py` and assert factorized tensors are present, selected dense tensors are absent, metadata arrays contain 32 ranks each, and all factors are TQ2_0.

- [ ] **Step 6: Run one clean-room reproduction of the winning model**

Delete only generated candidate files, rebuild the winner from the source GGUF plus manifest, and assert the rebuilt GGUF SHA256 matches the recorded release SHA256. If SVD implementation is nondeterministic on the selected hardware, require identical rank manifest and numerically identical factor payloads after dequantization, then record the source of nondeterminism explicitly.

- [ ] **Step 7: Final test suite**

```bash
pytest -q
cmake --build vendor/llama.cpp/build -j --target llama-cli llama-bench llama-perplexity
vendor/llama.cpp/build/bin/llama-cli \
  -m artifacts/bitcpm4-8b-svd-ffn-balanced-tq2_0.gguf \
  -p 'Explain singular value decomposition in one sentence.' \
  -n 32 \
  --temp 0
```

Run the same validation against the actual winning policy filename if it is not balanced.

- [ ] **Step 8: Commit**

```bash
git add README-SVD.md artifacts/*.manifest.json results/final/summary.json results/final/summary.md
git commit -m "docs: finalize BitCPM SVD optimization results"
```

---

## Agent Decision Rules

The coding agent must follow these rules during execution:

1. Do not optimize kernels before establishing baseline and quality-qualified ranks.
2. Do not compare TPS across different llama.cpp commits or build flags.
3. Do not claim RAM savings from a dense reconstructed probe. Only the factorized GGUF/runtime path saves static weight memory.
4. Do not retain FP16/BF16 low-rank factors in a release candidate.
5. Do not compress K/V in the MVP.
6. Do not use a rank that is not divisible by 256 for TQ2_0 factor storage.
7. Do not choose ranks solely from singular-value energy. Quantized reconstruction and perplexity decide quality.
8. Do not infer that smaller file size guarantees higher TPS. Measure PP and TG separately.
9. If a candidate fails quality, increase rank selectively using sensitivity, not uniformly unless the data supports uniform promotion.
10. If two-matmul execution already meets TPS targets, stop. Extra kernel work is unnecessary risk.
11. Keep baseline-compatible MiniCPM loading and graph execution intact.
12. Every generated model must be traceable to the source SHA256 and a checked-in rank manifest.

## Expected Milestones

- Milestone A: Baseline is fingerprinted and benchmarked reproducibly.
- Milestone B: TQ2 decode/encode and SVD factorization are validated against gguf-py.
- Milestone C: Dense reconstructed probes identify a quality-safe rank region without runtime changes.
- Milestone D: Sensitivity-aware rank manifests pass the full perplexity gate.
- Milestone E: Factorized GGUF loads in patched llama.cpp and produces valid generations.
- Milestone F: End-to-end size, RSS, PP TPS, and TG TPS are measured against a same-binary baseline.
- Milestone G: Either a release candidate meets target tradeoffs, or the experiment terminates with evidence that this SVD strategy does not improve the target deployment.

## Self-Review Checklist

- [ ] Every user requirement is represented: SVD, BitCPM 8B, TQ2_0, RAM reduction, TPS improvement, and the exact source model path.
- [ ] Source GGUF remains immutable.
- [ ] FFN-first scope is explicit and K/V exclusion is justified by dimensions and TQ2 rank alignment.
- [ ] Factor tensor shapes are consistent between Python, GGUF storage, loader validation, and graph matmuls.
- [ ] Candidate ranks are multiples of 256 and below raw-parameter break-even.
- [ ] Quality is measured before and after independent TQ2 factor quantization.
- [ ] Dense probe stage separates algorithmic quality loss from runtime implementation risk.
- [ ] Runtime changes preserve loading/execution of ordinary MiniCPM GGUF files.
- [ ] Performance comparisons use the same patched binary for baseline and candidate.
- [ ] Fused-kernel work is conditional on profile evidence.
- [ ] Every task has a test cycle and a commit boundary.
- [ ] No source/model overwrite path exists.
