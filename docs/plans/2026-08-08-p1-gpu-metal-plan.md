# P1 — GPU auto-detect, Metal first: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The stack uses the best engine the box has — Metal on Apple Silicon native mode, CPU AVX2 everywhere else — chosen automatically, overridable, and measured.

**Architecture:** `RuntimeConfig.n_gpu_layers` widens to accept the engine's own vocabulary (`0`, N, `auto`, `all`); the vision spawn command learns the same knob from `MUTA_RT_N_GPU_LAYERS`; `run.sh` detects the hardware, exports the env in native mode, and gains a side-effect-free `plan` subcommand that tests can probe. The container/competition path stays byte-equivalent CPU.

**Tech Stack:** pydantic-settings, pytest (monkeypatch + subprocess), bash, pinned llama.cpp b10035 (arm64 Metal build already in `runtime/build/bin/`).

## Global Constraints

- Engine pin `b10035` everywhere; `/usr/local/bin/llama-server` on PATH is b10050 x86_64 — never the engine of record.
- `n_gpu_layers` defaults to `0` (CPU): the AVX2 container invariant and every existing measurement stay untouched.
- At the pin, `-ngl` accepts an exact number, `auto`, or `all`, and **defaults to `auto`** — so an explicit `0` is what keeps CPU runs CPU; never omit the flag on a path that must stay CPU.
- Config lives in `RuntimeConfig` (`MUTA_RT_*`) / `runtime/profiles.py` — nowhere else (CLAUDE.md).
- Every task ends green: `.venv/bin/python -m pytest <touched test files> -q` and `.venv/bin/python -m ruff check .`.
- Same-day RESULTS.md entry with `native` context numbers before P1 is called done (Task 4).

---

### Task 1: `RuntimeConfig.n_gpu_layers` speaks the engine's vocabulary

**Files:**
- Modify: `runtime/config.py:74` (the `n_gpu_layers: int = 0` field)
- Test: `runtime/tests/test_server_command.py`

**Interfaces:**
- Produces: `RuntimeConfig.n_gpu_layers: int | Literal["auto", "all"]` (default `0`). `runtime/server.py:67` already emits `str(cfg.n_gpu_layers)` — no change there.

- [x] **Step 1: Write the failing tests** (append to `runtime/tests/test_server_command.py`, following the file's existing `cfg`/`build_command` pattern — copy the setup used by `test_build_command_baseline_flags`):

```python
def test_gpu_layers_accepts_the_engine_vocabulary(tmp_path, monkeypatch):
    """At the pin -ngl takes a number, 'auto' or 'all' (default auto): 'all' is how
    native Metal mode offloads without hardcoding a layer count."""
    monkeypatch.setenv("MUTA_RT_N_GPU_LAYERS", "all")
    cfg = RuntimeConfig()
    model = tmp_path / "m.gguf"
    model.touch()
    cmd = LlamaServer(cfg).build_command(model)
    assert cmd[cmd.index("--n-gpu-layers") + 1] == "all"


def test_gpu_layers_default_stays_cpu(tmp_path):
    cfg = RuntimeConfig()
    model = tmp_path / "m.gguf"
    model.touch()
    cmd = LlamaServer(cfg).build_command(model)
    assert cmd[cmd.index("--n-gpu-layers") + 1] == "0"
```

- [x] **Step 2: Run to verify the first fails** — `.venv/bin/python -m pytest runtime/tests/test_server_command.py -q` — expected: `"all"` fails pydantic int validation (ValidationError), the default test passes already.

- [x] **Step 3: Widen the field** in `runtime/config.py` (add `Literal` to the existing `typing` import if absent):

```python
    # CPU-only target; "all"/"auto"/N for GPU boxes. At the b10035 pin -ngl DEFAULTS to
    # auto — the explicit 0 here is what keeps CPU paths CPU.
    n_gpu_layers: int | Literal["auto", "all"] = 0
```

- [x] **Step 4: Verify green** — same pytest command, plus `.venv/bin/python -m ruff check runtime/`.

- [x] **Step 5: Commit** — `git add runtime/config.py runtime/tests/test_server_command.py && git commit -m "config: n_gpu_layers accepts the engine's auto/all vocabulary"`

---

### Task 2: the vision spawn gets the same knob

**Files:**
- Modify: `runtime/profiles.py` (`core_vision_command`, argv list around line 390)
- Test: `runtime/tests/test_profiles.py` (vision section, after `test_vision_forces_the_qwen_vl_image_token_floor`)

**Interfaces:**
- Consumes: env `MUTA_RT_N_GPU_LAYERS` (same name Task 1 reads via pydantic; profiles is env-driven by convention — see `port()`, `_env_threads`).
- Produces: vision argv always contains `--n-gpu-layers <value>`, default `"0"`.

- [x] **Step 1: Write the failing tests** (append to `runtime/tests/test_profiles.py`):

```python
def test_vision_pins_cpu_by_default(bundle):
    """-ngl defaults to *auto* at this pin: on a Metal host an unpinned vision spawn
    would silently offload. Explicit 0 keeps CPU paths CPU."""
    assert flag_value(core_vision_command(bundle).argv, "--n-gpu-layers") == "0"


def test_vision_offloads_when_the_env_says_so(bundle, monkeypatch):
    monkeypatch.setenv("MUTA_RT_N_GPU_LAYERS", "all")
    assert flag_value(core_vision_command(bundle).argv, "--n-gpu-layers") == "all"
```

- [x] **Step 2: Verify both fail** — `.venv/bin/python -m pytest runtime/tests/test_profiles.py -q` — expected: `flag_value` finds no `--n-gpu-layers`.

- [x] **Step 3: Implement** — in `core_vision_command`'s argv, directly after the `"--image-min-tokens", "1024",` pair:

```python
        # Explicit because -ngl defaults to *auto* at this pin: a Metal host would
        # otherwise offload silently. run.sh native GPU mode sets the env to "all".
        "--n-gpu-layers", os.environ.get("MUTA_RT_N_GPU_LAYERS", "0"),
```

- [x] **Step 4: Verify green** — same pytest command + `ruff check runtime/`.

- [x] **Step 5: Commit** — `git add runtime/profiles.py runtime/tests/test_profiles.py && git commit -m "profiles: vision spawn takes MUTA_RT_N_GPU_LAYERS, explicit CPU default"`

---

### Task 3: run.sh detection, `plan` subcommand, `--cpu` override

**Files:**
- Modify: `run.sh` (usage text ~line 26-46; arg loop ~line 118; `native_up` env block ~line 94-107; a new `detect_plan` function near `fetch_native_engine`)
- Create: `docs/gpu.md` (the CUDA recipe detection points at)
- Test: `runtime/tests/test_run_sh_plan.py` (new)

**Interfaces:**
- Produces: `./run.sh plan` prints exactly three `key=value` lines (`host=`, `mode=`, `gpu=`) and exits 0 with no side effects; `--cpu` forces `gpu=none`; native mode exports `MUTA_RT_N_GPU_LAYERS=all` on Darwin/arm64 unless the user set it or passed `--cpu`.

- [x] **Step 1: Write the failing test**:

```python
"""./run.sh plan — hardware detection is testable without touching docker."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent


def run_plan(tmp_path, uname_s: str, uname_m: str, *args: str, nvidia: bool = False) -> str:
    """Invoke ./run.sh plan with PATH-shimmed uname (and optionally nvidia-smi)."""
    shim = tmp_path / "bin"
    shim.mkdir(exist_ok=True)
    uname = shim / "uname"
    uname.write_text(
        "#!/bin/sh\n"
        f'case "$1" in -s) echo {uname_s};; -m) echo {uname_m};; *) echo {uname_s};; esac\n'
    )
    uname.chmod(uname.stat().st_mode | stat.S_IEXEC)
    if nvidia:
        smi = shim / "nvidia-smi"
        smi.write_text("#!/bin/sh\nexit 0\n")
        smi.chmod(smi.stat().st_mode | stat.S_IEXEC)
    env = {**os.environ, "PATH": f"{shim}:{os.environ['PATH']}"}
    out = subprocess.run(
        ["bash", str(REPO / "run.sh"), "plan", *args],
        capture_output=True, text=True, env=env, cwd=REPO, timeout=30,
    )
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_plan_on_apple_silicon_offers_metal(tmp_path):
    out = run_plan(tmp_path, "Darwin", "arm64")
    assert "host=Darwin/arm64" in out
    assert "gpu=metal-native" in out


def test_plan_with_cpu_flag_forces_cpu(tmp_path):
    out = run_plan(tmp_path, "Darwin", "arm64", "--cpu")
    assert "gpu=none" in out


def test_plan_on_linux_with_nvidia_points_at_cuda(tmp_path):
    out = run_plan(tmp_path, "Linux", "x86_64", nvidia=True)
    assert "gpu=cuda-available" in out


def test_plan_on_plain_linux_is_cpu(tmp_path):
    out = run_plan(tmp_path, "Linux", "x86_64")
    assert "gpu=none" in out
```

- [x] **Step 2: Verify all four fail** — `.venv/bin/python -m pytest runtime/tests/test_run_sh_plan.py -q` — expected: run.sh exits non-zero on the unknown `plan` argument ("unknown option").

- [x] **Step 3: Implement in `run.sh`** — add after `fetch_native_engine`:

```bash
# GPU detection. CPU is the invariant default; Metal exists only in native mode
# (Docker on macOS has no GPU passthrough); NVIDIA is detect-and-point-at-docs
# (docs/gpu.md) until a CUDA image variant lands.
detect_gpu() {
    [ "${FORCE_CPU:-0}" = 1 ] && { echo none; return; }
    case "$(uname -s)/$(uname -m)" in
        Darwin/arm64) echo metal-native ;;
        Linux/*) command -v nvidia-smi >/dev/null 2>&1 && echo cuda-available || echo none ;;
        *) echo none ;;
    esac
}

print_plan() {
    echo "host=$(uname -s)/$(uname -m)"
    echo "mode=$MODE"
    echo "gpu=$(detect_gpu)"
}
```

In the arg loop add (alongside `--native`): `--cpu) FORCE_CPU=1 ;;` and `plan) MODE=plan ;;`, initialise `FORCE_CPU=0` next to `MODE=docker`, and after the loop: `[ "$MODE" = plan ] && { print_plan; exit 0; }`. Document both in the usage heredoc.

In `native_up`, next to the other exports:

```bash
    # Metal offload unless the user pinned layers or forced CPU. At b10035 -ngl
    # defaults to auto, but RuntimeConfig pins 0 — "all" is the deliberate opt-in.
    if [ "${FORCE_CPU:-0}" != 1 ] && [ -z "${MUTA_RT_N_GPU_LAYERS:-}" ] \
        && [ "$(detect_gpu)" = metal-native ]; then
        export MUTA_RT_N_GPU_LAYERS=all
        info "Metal: offloading all layers (MUTA_RT_N_GPU_LAYERS=all; --cpu to disable)"
    fi
```

In docker mode startup (just before `compose up`), the suggestion line:

```bash
    [ "$(detect_gpu)" = metal-native ] \
        && warn "emulated x86 on Apple Silicon: './run.sh --native' uses Metal and is ~10x faster"
    [ "$(detect_gpu)" = cuda-available ] \
        && warn "NVIDIA GPU detected: see docs/gpu.md for the CUDA backend variant"
```

- [x] **Step 4: Write `docs/gpu.md`** — short doc: the three detection outcomes, `MUTA_RT_N_GPU_LAYERS` semantics (`0`/N/`auto`/`all`; pin default is auto, our default 0), the native-Metal quickstart (`./run.sh --native`, `--cpu` to opt out), and the CUDA recipe outline (build llama.cpp with `GGML_CUDA=ON` in a `docker/backend.cuda.Dockerfile` copied from `docker/backend.Dockerfile`, compose `gpu` profile with `deploy.resources.reservations.devices`) marked as untested-here.

- [x] **Step 5: Verify green** — `.venv/bin/python -m pytest runtime/tests/test_run_sh_plan.py -q`; then a real-hardware smoke: `./run.sh plan` (expect `host=Darwin/arm64`, `gpu=metal-native`) and `./run.sh plan --cpu` (expect `gpu=none`).

- [x] **Step 6: Commit** — `git add run.sh docs/gpu.md runtime/tests/test_run_sh_plan.py && git commit -m "run.sh: GPU auto-detect, plan subcommand, --cpu override; docs/gpu.md"`

---

### Task 4: measure Metal vs CPU, record, close P1

**Files:**
- Modify: `RESULTS.md` (new same-day section, `native` context)

**Interfaces:**
- Consumes: Task 1's config widening (env `MUTA_RT_N_GPU_LAYERS=all`), the pinned arm64 engine at `runtime/build/bin/llama-server`.

- [x] **Step 1: CPU baseline** — start the pinned native server CPU-pinned and probe it (two terminals or `&`):

```bash
TUTOR_ROOT="$PWD" MUTA_RT_MODEL_DIR=models/core MUTA_RT_MODEL_FILE=Qwen3.5-4B-IQ4_XS.gguf \
MUTA_RT_MODEL_ALIAS=qwen3.5-4b MUTA_RT_N_GPU_LAYERS=0 MUTA_RT_SPEC_TYPE=none \
.venv/bin/python -m runtime.server &
sleep 60   # model load
for i in 1 2 3; do
  curl -sS http://127.0.0.1:8080/v1/chat/completions -H 'content-type: application/json' \
    -d '{"model":"qwen3.5-4b","messages":[{"role":"user","content":"Explain why 91 is not prime, step by step."}],"max_tokens":128,"temperature":0}' \
    | python3 -c 'import json,sys; t=json.load(sys.stdin)["timings"]; print(f"prefill {t[\"prompt_per_second\"]:.1f} tok/s, decode {t[\"predicted_per_second\"]:.1f} tok/s")'
done
kill %1
```

(Port 8080 is `MUTA_RT_SERVER_PORT`'s default in `runtime/config.py`. Discard run 1 as cold; record runs 2-3.)

- [x] **Step 2: Metal run** — identical, with `MUTA_RT_N_GPU_LAYERS=all`. Also capture peak RSS: `ps -o rss= -p <llama-server pid>` after run 3, both runs.

- [x] **Step 3: RESULTS.md entry** — append a `### B.` subsection to the 2026-08-08 section: the two configs verbatim, a table (prefill tok/s, decode tok/s, peak RSS, `native` context), and one sentence on what the delta means for the ~4 min/photo vision tax.

- [x] **Step 4: Full suite green** — `.venv/bin/python -m pytest --ignore=bench/adtc-profiler -q` and `.venv/bin/python -m ruff check .`.

- [x] **Step 5: Commit** — `git add RESULTS.md docs/plans/2026-08-08-p1-gpu-metal-plan.md && git commit -m "results: native Metal vs CPU on the M2 Pro; P1 plan checked off"`
