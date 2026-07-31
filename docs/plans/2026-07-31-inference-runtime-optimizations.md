# Inference Runtime Optimizations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bound llama-server's steady-state RSS with explicit engine caps, activate speculative decoding with the Qwen3.5-0.8B draft (the configured Qwen3-0.6B is vocab-incompatible and the flags were silently dead), add a `--native` dev mode to `run.sh` (docker remains the default), and make the launch path + KV planning math tell the truth about the hybrid Qwen3.5 architecture.

**Architecture:** All engine knobs move into `RuntimeConfig` (env-overridable `MUTA_RT_*`) and are emitted by `LlamaServer.build_command()` — the one launch path the compose stack actually uses. `run.sh` gains a mode switch: docker (default, unchanged 3-container amd64 stack) or native (db + frontend stay in docker, the gateway + an arm64 llama-server run on the host; nginx's upstream becomes a template variable so the frontend container can point at the host). `runtime/gguf.py`/`runtime/kvmath.py` learn the hybrid layout (8 of 32 layers full-attention, 24 recurrent SSM layers with constant f32 state).

**Tech Stack:** Python ≥3.10, pydantic-settings, FastAPI/uvicorn, llama.cpp `b10035` (pinned; arm64 release zip for native dev), docker compose, nginx templates (envsubst), pytest.

## Global Constraints

- llama.cpp is pinned at `b10035`; flag spellings must match that build (`--spec-type`, `--spec-draft-*`, `--ctx-checkpoints`, `--cache-ram`). Empirical facts about it are recorded in `docs/engine-flags.md` (created by Task 8).
- The `/v1` contract is untouched by this plan — no `make contract` run is needed; do not edit `contracts/`.
- Docker stays the default run mode; all compose services remain `--platform=linux/amd64`. Native mode is opt-in per invocation and must not leak into the docker path.
- Degradation, not errors: a missing draft model must never block a boot (warn + run without speculation).
- Engine knobs live in `RuntimeConfig` (`MUTA_RT_*`) on this branch — nothing else may hardcode a context size, slot count, thread count, or cache size. `runtime/profiles.py` is left as-is (vision command + BundlePaths still use it).
- Benchmark numbers measured on the Mac (native or emulated) are dev signals only and must be tagged `dev_host_provisional` in `bench/optimization-log.md`.
- Model paths: core `models/core/Qwen3.5-4B-Q4_K_M.gguf`; draft `models/draft/Qwen3.5-0.8B-Q4_K_M.gguf` (fetched by `scripts/fetch_models.py --with-draft`, spec name `draft`).
- Commit after every task; run `make lint` (`ruff check .`) before each commit.

## Verified facts this plan is built on (measured 2026-07-31 against the pinned engine)

- `--spec-type` defaults to `none`; `--spec-draft-model` without it is a silent no-op.
- Qwen3-0.6B (vocab 151,936) is **rejected** as a draft for Qwen3.5-4B (vocab 248,320): "the target and draft vocabs are not compatible". Only a Qwen3.5-family draft can work.
- `-np` defaults to auto → **4 slots**; each slot of Qwen3.5-4B carries ~50.25 MiB of f32 recurrent state; context checkpoints cost ~50.25 MiB each (default cap 32/slot); `--cache-ram` defaults to 8192 MiB and each cached conversation costs ~57 MiB. RSS drifted 2.9 → 4.8 GiB in four short requests.
- Multi-turn checkpoint restore works: turn 2 of a 269-token conversation processed only 149 tokens. The verification tasks assert this survives the new caps.
- ngram-simple at engine defaults (N=12) produced zero drafts on tutoring turns; `size-n 4 / size-m 12` measured 12–22% token acceptance.

---

### Task 1: RAM-ceiling and thread flags in RuntimeConfig + build_command

**Files:**
- Modify: `runtime/config.py` (after the `n_gpu_layers` field, ~line 39)
- Modify: `runtime/server.py:58-83` (`build_command`)
- Test: `runtime/tests/test_server_command.py`

**Interfaces:**
- Produces: `RuntimeConfig.n_parallel: int = 2`, `RuntimeConfig.ctx_checkpoints: int = 4`, `RuntimeConfig.cache_ram_mib: int = 256`, `RuntimeConfig.n_threads_batch: int | None = None` (env: `MUTA_RT_N_PARALLEL`, `MUTA_RT_CTX_CHECKPOINTS`, `MUTA_RT_CACHE_RAM_MIB`, `MUTA_RT_N_THREADS_BATCH`). Task 3 (compose) and Task 7 (run.sh native) rely on these env names.

- [ ] **Step 1: Write the failing tests**

Append to `runtime/tests/test_server_command.py`:

```python
def test_build_command_bounds_engine_memory(tmp_path):
    """b10035 defaults are sized for bigger boxes: -np auto -> 4 slots x ~50 MiB f32 state,
    32 checkpoints/slot, 8 GiB prompt cache. These flags are what bound steady-state RSS."""
    cfg, model = _cfg(tmp_path)
    cmd = LlamaServer(cfg).build_command(model)
    assert cmd[cmd.index("--parallel") + 1] == "2"
    assert cmd[cmd.index("--ctx-checkpoints") + 1] == "4"
    assert cmd[cmd.index("--cache-ram") + 1] == "256"


def test_build_command_thread_flags_only_when_configured(tmp_path):
    cfg, model = _cfg(tmp_path)
    cmd = LlamaServer(cfg).build_command(model)
    assert "--threads" not in cmd and "--threads-batch" not in cmd

    cfg2, model2 = _cfg(tmp_path, n_threads=8, n_threads_batch=10)
    cmd2 = LlamaServer(cfg2).build_command(model2)
    assert cmd2[cmd2.index("--threads") + 1] == "8"
    assert cmd2[cmd2.index("--threads-batch") + 1] == "10"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest runtime/tests/test_server_command.py -v`
Expected: the two new tests FAIL (`--parallel` not in list / unexpected keyword `n_threads_batch`); the four existing tests PASS.

- [ ] **Step 3: Add the config fields**

In `runtime/config.py`, directly after the `n_gpu_layers` line, insert:

```python
    # --- engine memory ceilings -------------------------------------------------------
    # b10035 defaults are sized for far bigger boxes. Measured on Qwen3.5-4B (hybrid:
    # ~50 MiB f32 recurrent state per slot and per context checkpoint): -np auto picks 4
    # slots, checkpoints cap at 32/slot and the prompt cache at 8 GiB — RSS drifted
    # 2.9 -> 4.8 GiB in four requests. These four fields bound steady-state RSS.
    # Worst case here: 2 slots x (50 state + 4 x 50 checkpoints) + 256 cache ~= 750 MiB.
    n_parallel: int = 2  # 2, not 1: one warm spare conversation for UI switching
    ctx_checkpoints: int = 4  # per slot; too low silently breaks multi-turn reuse (T8 verifies)
    cache_ram_mib: int = 256  # host-RAM prompt cache (--cache-ram); engine default is 8192
    n_threads_batch: int | None = None  # prefill threads; None -> engine default
```

- [ ] **Step 4: Emit the flags in build_command**

In `runtime/server.py`, replace the `cmd = [...]` list and the `n_threads` conditional in `build_command` with:

```python
        cmd = [
            find_binary(cfg),
            "--model", str(model_path),
            "--alias", cfg.model_alias,
            "--host", cfg.server_host,
            "--port", str(cfg.server_port),
            "--ctx-size", str(cfg.n_ctx),
            "--n-gpu-layers", str(cfg.n_gpu_layers),
            "--jinja",  # apply the model's embedded chat template (Qwen3 thinking control)
            # RAM ceilings — see the field comments in runtime/config.py.
            "--parallel", str(cfg.n_parallel),
            "--ctx-checkpoints", str(cfg.ctx_checkpoints),
            "--cache-ram", str(cfg.cache_ram_mib),
        ]
        if cfg.n_threads is not None:
            cmd += ["--threads", str(cfg.n_threads)]
        if cfg.n_threads_batch is not None:
            cmd += ["--threads-batch", str(cfg.n_threads_batch)]
```

(The draft-model block and `cmd += cfg.extra_server_args` below stay untouched in this task.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest runtime/tests/test_server_command.py runtime/tests/test_chat.py -v`
Expected: all PASS.

- [ ] **Step 6: Lint and commit**

```bash
python3 -m ruff check . && git add runtime/config.py runtime/server.py runtime/tests/test_server_command.py && git commit -m "feat(runtime): bound engine RSS with parallel/checkpoint/cache-ram flags"
```

---

### Task 2: Speculation that actually activates (spec_type)

**Files:**
- Modify: `runtime/config.py` (draft-model block, ~lines 50-54)
- Modify: `runtime/server.py` (`build_command` draft block → new `_speculation_flags` method)
- Test: `runtime/tests/test_server_command.py`

**Interfaces:**
- Consumes: `RuntimeConfig.draft_model / draft_max / draft_min` (existing).
- Produces: `RuntimeConfig.spec_type: Literal["none", "draft-simple", "ngram-simple"] = "draft-simple"` (env `MUTA_RT_SPEC_TYPE`); `LlamaServer._speculation_flags() -> list[str]`. Tasks 3/7/8 rely on the default being `draft-simple` and on absence-degradation.

- [ ] **Step 1: Write the failing tests**

Append to `runtime/tests/test_server_command.py`:

```python
def test_spec_type_gates_the_draft_flags(tmp_path):
    """b10035 ignores --spec-draft-model unless --spec-type selects an implementation
    (default none) — the flags were silently dead before this field existed."""
    draft = tmp_path / "draft.gguf"
    draft.touch()
    cfg, model = _cfg(tmp_path, draft_model=draft)
    cmd = LlamaServer(cfg).build_command(model)
    assert cmd[cmd.index("--spec-type") + 1] == "draft-simple"
    assert cmd[cmd.index("--spec-draft-model") + 1] == str(draft)


def test_spec_type_none_disables_speculation_even_with_a_draft(tmp_path):
    draft = tmp_path / "draft.gguf"
    draft.touch()
    cfg, model = _cfg(tmp_path, draft_model=draft, spec_type="none")
    cmd = LlamaServer(cfg).build_command(model)
    assert "--spec-type" not in cmd
    assert "--spec-draft-model" not in cmd


def test_ngram_simple_needs_no_draft_and_uses_measured_params(tmp_path):
    """Engine-default lookup (N=12) produced zero drafts on tutoring turns; N=4/M=12
    measured 12-22% token acceptance (docs/engine-flags.md)."""
    cfg, model = _cfg(tmp_path, spec_type="ngram-simple")
    cmd = LlamaServer(cfg).build_command(model)
    assert cmd[cmd.index("--spec-type") + 1] == "ngram-simple"
    assert cmd[cmd.index("--spec-ngram-simple-size-n") + 1] == "4"
    assert cmd[cmd.index("--spec-ngram-simple-size-m") + 1] == "12"
    assert "--spec-draft-model" not in cmd
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest runtime/tests/test_server_command.py -v`
Expected: three new tests FAIL (`--spec-type` not in list / unexpected keyword `spec_type`).

- [ ] **Step 3: Add the spec_type field**

In `runtime/config.py`, replace the comment + `draft_model`/`draft_max`/`draft_min` block with:

```python
    # Speculative decoding. b10035 gates ALL speculation behind --spec-type (default
    # none): a draft model passed without it is silently ignored (docs/engine-flags.md).
    # "draft-simple" needs draft_model to exist and share the target's vocab — the Qwen3.5
    # family (vocab 248320) rejects Qwen3 drafts (151936). "ngram-simple" is zero-RAM
    # self-speculation from the context; params are the measured tutoring-workload ones.
    spec_type: Literal["none", "draft-simple", "ngram-simple"] = "draft-simple"
    draft_model: Path | None = None
    draft_max: int = 8
    draft_min: int = 1
```

- [ ] **Step 4: Replace the draft block with _speculation_flags**

In `runtime/server.py`, inside `build_command`, replace the whole `if cfg.draft_model and Path(cfg.draft_model).is_file(): ...` block (including its comment) with:

```python
        cmd += self._speculation_flags()
```

and add this method to `LlamaServer` directly below `build_command`:

```python
    def _speculation_flags(self) -> list[str]:
        """Flag spellings are the b10035 ones (--spec-type framework; the old
        --draft-max/--draft-min were REMOVED upstream and hard-fail at startup)."""
        cfg = self.cfg
        if cfg.spec_type == "draft-simple":
            if not (cfg.draft_model and Path(cfg.draft_model).is_file()):
                # Degradation, not error: the stack must boot without the draft.
                log.info("spec_type=draft-simple but no draft model at %s — speculation off", cfg.draft_model)
                return []
            return [
                "--spec-type", "draft-simple",
                "--spec-draft-model", str(cfg.draft_model),
                "--spec-draft-n-max", str(cfg.draft_max),
                "--spec-draft-n-min", str(cfg.draft_min),
                "--spec-draft-p-min", "0.75",
            ]
        if cfg.spec_type == "ngram-simple":
            # Engine defaults (N=12) never drafted on tutoring turns; N=4/M=12 measured
            # 12-22% token acceptance at zero RAM cost (docs/engine-flags.md).
            return [
                "--spec-type", "ngram-simple",
                "--spec-ngram-simple-size-n", "4",
                "--spec-ngram-simple-size-m", "12",
            ]
        return []
```

- [ ] **Step 5: Update the two existing draft tests**

In `runtime/tests/test_server_command.py`, `test_build_command_emits_draft_flags_when_draft_model_exists` gains one assertion (after the existing ones):

```python
    assert cmd[cmd.index("--spec-type") + 1] == "draft-simple"
```

`test_build_command_omits_draft_flags_when_draft_file_missing` gains:

```python
    assert "--spec-type" not in cmd
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 -m pytest runtime/tests/test_server_command.py -v`
Expected: all PASS.

- [ ] **Step 7: Lint and commit**

```bash
python3 -m ruff check . && git add runtime/config.py runtime/server.py runtime/tests/test_server_command.py && git commit -m "feat(runtime): spec_type config — b10035 requires --spec-type to activate speculation"
```

---

### Task 3: Fold the compose extra args into config; point everything at the 0.8B draft

**Files:**
- Modify: `runtime/config.py` (llama-server section)
- Modify: `runtime/server.py` (`build_command`)
- Modify: `docker-compose.yml:44-74` (backend environment)
- Modify: `run.sh:82,94-97` (DRAFT path + warn hint)
- Modify: `RUN.md` (backend env table)
- Test: `runtime/tests/test_server_command.py`

**Interfaces:**
- Produces: `RuntimeConfig.n_batch: int = 512`, `n_ubatch: int = 128`, `cache_type_k: str = "q8_0"`, `reasoning_budget: int = 512` (env `MUTA_RT_N_BATCH`, `MUTA_RT_N_UBATCH`, `MUTA_RT_CACHE_TYPE_K`, `MUTA_RT_REASONING_BUDGET`). Draft path of record becomes `models/draft/Qwen3.5-0.8B-Q4_K_M.gguf` (Task 7/8 use it).

- [ ] **Step 1: Write the failing test**

Append to `runtime/tests/test_server_command.py`:

```python
def test_batch_and_cache_flags_come_from_config_not_extra_args(tmp_path):
    """These four lived in MUTA_RT_EXTRA_SERVER_ARGS in docker-compose.yml — a JSON string
    outside the config schema. Fields make them visible, testable and overridable."""
    cfg, model = _cfg(tmp_path)
    cmd = LlamaServer(cfg).build_command(model)
    assert cmd[cmd.index("-b") + 1] == "512"
    assert cmd[cmd.index("-ub") + 1] == "128"
    assert cmd[cmd.index("--cache-type-k") + 1] == "q8_0"
    assert cmd[cmd.index("--reasoning-budget") + 1] == "512"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest runtime/tests/test_server_command.py::test_batch_and_cache_flags_come_from_config_not_extra_args -v`
Expected: FAIL (`-b` not in list).

- [ ] **Step 3: Add the config fields**

In `runtime/config.py`, after the `n_threads_batch` field from Task 1, insert:

```python
    # Batch geometry + K-cache quantization + thinking cap — previously injected via
    # MUTA_RT_EXTRA_SERVER_ARGS in docker-compose.yml. Small -b/-ub shrink the compute
    # buffers (~31 MiB at -ub 128 on the 4B, measured); q8_0 K halves that side of the
    # attention KV; the reasoning budget force-closes the think phase so the answer
    # always arrives inside a 2048-token context.
    n_batch: int = 512
    n_ubatch: int = 128
    cache_type_k: str = "q8_0"
    reasoning_budget: int = 512  # -1 = unrestricted (engine default)
```

- [ ] **Step 4: Emit them in build_command**

In `runtime/server.py`, in the `cmd = [...]` list from Task 1, after the `"--cache-ram", str(cfg.cache_ram_mib),` line add:

```python
            "-b", str(cfg.n_batch),
            "-ub", str(cfg.n_ubatch),
            "--cache-type-k", cfg.cache_type_k,
            "--reasoning-budget", str(cfg.reasoning_budget),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest runtime/tests/ -v`
Expected: all PASS (Postgres-backed tests skip if the compose db is down — that is fine).

- [ ] **Step 6: Update docker-compose.yml**

In `docker-compose.yml` backend `environment:`, delete the `MUTA_RT_EXTRA_SERVER_ARGS` entry and its comment block ("Smaller batch/ubatch shrink ... always arrives"), delete the old draft comment + entry (`MUTA_RT_DRAFT_MODEL: /app/models/Qwen3-0.6B/...`), and add:

```yaml
      # Engine flags now live in RuntimeConfig (runtime/config.py) — batch geometry,
      # q8_0 K-cache, reasoning budget 512, and the RSS ceilings (--parallel 2,
      # --ctx-checkpoints 4, --cache-ram 256) are the defaults there. Only deltas from
      # those defaults belong here.
      # Threads: the VM's 10 vCPUs are shared with the gateway/db/nginx — decode is
      # bandwidth-bound and gains nothing from oversubscription (runtime/profiles.py
      # thread table rationale), prefill may use them all.
      MUTA_RT_N_THREADS: "8"
      MUTA_RT_N_THREADS_BATCH: "10"
      # Speculation draft: Qwen3.5-0.8B (fetch_models --with-draft). Qwen3-0.6B is NOT
      # usable — vocab 151936 vs the 4B's 248320, the engine rejects the pairing
      # (docs/engine-flags.md). Absent file -> speculation off, boot proceeds.
      MUTA_RT_DRAFT_MODEL: /app/models/draft/Qwen3.5-0.8B-Q4_K_M.gguf
```

Also update the stale comment above `MUTA_CORE_CAP_MIB` ("Core + the speculation draft measure ~4.2 GiB...") to:

```yaml
      # Engine + 0.8B draft with the RSS ceilings applied: re-measure after boot and
      # record in bench/optimization-log.md. 5400 leaves room for vision on this 8 GiB VM.
```

- [ ] **Step 7: Update run.sh draft path + hint**

In `run.sh` replace:

```bash
DRAFT="models/Qwen3-0.6B/Qwen3-0.6B-Q4_K_M.gguf"
```

with:

```bash
DRAFT="models/draft/Qwen3.5-0.8B-Q4_K_M.gguf"
```

and replace the warn line `warn "speculation draft absent ($DRAFT) — running without it. Fetch it with: make model"` with:

```bash
    warn "speculation draft absent ($DRAFT) — running without it. Fetch it with:"
    warn "  docker compose run --rm --no-deps backend python3.10 scripts/fetch_models.py --with-draft --only draft"
```

- [ ] **Step 8: Update RUN.md**

In the backend-env table in `RUN.md`: change the `MUTA_RT_DRAFT_MODEL` row's value to `/app/models/draft/Qwen3.5-0.8B-Q4_K_M.gguf` and its note to `speculative draft (Qwen3.5 family only — Qwen3 vocab is incompatible; skipped if absent)`; fix the `MUTA_RT_ENABLE_THINKING` row to `1` (current compose value); add rows:

```markdown
| `MUTA_RT_N_PARALLEL` | `2` | server slots (each costs ~50 MiB f32 state on the hybrid 4B) |
| `MUTA_RT_CTX_CHECKPOINTS` | `4` | recurrent-state checkpoints per slot, ~50 MiB each |
| `MUTA_RT_CACHE_RAM_MIB` | `256` | host-RAM prompt cache cap (engine default: 8192) |
| `MUTA_RT_N_THREADS` / `_BATCH` | unset / unset (compose: `8` / `10`) | decode / prefill threads |
| `MUTA_RT_N_BATCH` / `_UBATCH` | `512` / `128` | logical / physical batch (compute-buffer size) |
| `MUTA_RT_CACHE_TYPE_K` | `q8_0` | K-cache quantization |
| `MUTA_RT_REASONING_BUDGET` | `512` | max thinking tokens before the answer is forced |
| `MUTA_RT_SPEC_TYPE` | `draft-simple` | `none` \| `draft-simple` \| `ngram-simple` |
```

- [ ] **Step 9: Sanity-check compose interpolation and commit**

```bash
docker compose config >/dev/null && python3 -m ruff check . \
  && git add runtime/config.py runtime/server.py runtime/tests/test_server_command.py docker-compose.yml run.sh RUN.md \
  && git commit -m "feat(runtime): batch/cache/reasoning flags into config; draft of record -> Qwen3.5-0.8B"
```

---

### Task 4: Hybrid-architecture metadata in gguf.py

**Files:**
- Modify: `runtime/gguf.py` (GGUFMetadata properties, after `trained_context`)
- Test: `runtime/tests/test_gguf.py`

**Interfaces:**
- Produces: `GGUFMetadata.full_attention_interval: int`, `.n_attn_layer: int`, `.ssm_state_size: int`, `.ssm_inner_size: int`, `.ssm_conv_kernel: int`, `.ssm_group_count: int`, `.is_hybrid: bool`; test fixture `qwen35_like(path) -> Path` in `runtime/tests/test_gguf.py`. Task 5 consumes all of these.

- [ ] **Step 1: Write the failing tests**

Append to `runtime/tests/test_gguf.py`:

```python
def qwen35_like(path: Path, *, layers=32, interval=4) -> Path:
    """Hybrid fixture matching the shipped Qwen3.5-4B: full attention every `interval`
    layers, gated-delta-net (SSM) state on the rest."""
    entries = [
        _kv("general.architecture", STR, _str("qwen35")),
        _kv("qwen35.block_count", U32, _u32(layers)),
        _kv("qwen35.attention.head_count", U32, _u32(16)),
        _kv("qwen35.attention.head_count_kv", U32, _u32(4)),
        _kv("qwen35.attention.key_length", U32, _u32(256)),
        _kv("qwen35.attention.value_length", U32, _u32(256)),
        _kv("qwen35.context_length", U32, _u32(262144)),
        _kv("qwen35.embedding_length", U32, _u32(2560)),
        _kv("qwen35.full_attention_interval", U32, _u32(interval)),
        _kv("qwen35.ssm.state_size", U32, _u32(128)),
        _kv("qwen35.ssm.inner_size", U32, _u32(4096)),
        _kv("qwen35.ssm.conv_kernel", U32, _u32(4)),
        _kv("qwen35.ssm.group_count", U32, _u32(16)),
    ]
    return write_gguf(path, entries)


def test_hybrid_metadata_splits_attention_from_recurrent_layers(tmp_path):
    md = read_metadata(qwen35_like(tmp_path / "h.gguf"))
    assert md.is_hybrid
    assert md.full_attention_interval == 4
    assert md.n_attn_layer == 8  # 32 // 4 — only these carry token-growing KV
    assert (md.ssm_state_size, md.ssm_inner_size) == (128, 4096)
    assert (md.ssm_conv_kernel, md.ssm_group_count) == (4, 16)


def test_non_hybrid_models_keep_all_layers_as_attention(tmp_path):
    md = read_metadata(qwen_like(tmp_path / "m.gguf"))
    assert not md.is_hybrid
    assert md.n_attn_layer == md.n_layer == 36
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest runtime/tests/test_gguf.py -v`
Expected: the two new tests FAIL (`AttributeError: is_hybrid`); existing tests PASS.

- [ ] **Step 3: Add the properties**

In `runtime/gguf.py`, after the `trained_context` property, insert:

```python
    # --- hybrid (linear-attention / SSM) layout ----------------------------------------
    @property
    def full_attention_interval(self) -> int:
        return _as_int(self.arch_key("full_attention_interval", 0))

    @property
    def n_attn_layer(self) -> int:
        """Layers whose KV grows with tokens. Hybrid models (qwen35: gated delta net)
        run full attention only every `full_attention_interval`-th layer; the rest carry
        constant-size recurrent state instead. Budgeting all layers as attention
        overstates per-token KV 4x on the shipped 4B."""
        interval = self.full_attention_interval
        return self.n_layer // interval if interval > 1 else self.n_layer

    @property
    def ssm_state_size(self) -> int:
        return _as_int(self.arch_key("ssm.state_size", 0))

    @property
    def ssm_inner_size(self) -> int:
        return _as_int(self.arch_key("ssm.inner_size", 0))

    @property
    def ssm_conv_kernel(self) -> int:
        return _as_int(self.arch_key("ssm.conv_kernel", 0))

    @property
    def ssm_group_count(self) -> int:
        return _as_int(self.arch_key("ssm.group_count", 0))

    @property
    def is_hybrid(self) -> bool:
        return self.full_attention_interval > 1 and self.ssm_state_size > 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest runtime/tests/test_gguf.py -v`
Expected: all PASS.

- [ ] **Step 5: Lint and commit**

```bash
python3 -m ruff check . && git add runtime/gguf.py runtime/tests/test_gguf.py && git commit -m "feat(gguf): read hybrid-attention + SSM metadata (qwen35)"
```

---

### Task 5: Hybrid-aware KV math (kvmath.py) + regenerated kv-budget doc

**Files:**
- Modify: `runtime/kvmath.py` (`KVCost.from_metadata`, new `RecurrentStateCost`, `SlotBudget`, `budget`, `budget_table`, `render_markdown`)
- Modify: `docs/kv-budget.md` (regenerated output — do not hand-edit)
- Test: `runtime/tests/test_kvmath.py`

**Interfaces:**
- Consumes: `GGUFMetadata.n_attn_layer`, `.is_hybrid`, `.ssm_*` (Task 4); `qwen35_like` fixture (Task 4).
- Produces: `RecurrentStateCost.from_metadata(md) -> RecurrentStateCost | None` with `.bytes_per_slot: int` and `.mib_per_slot: float`; `SlotBudget.state_mib: float = 0.0` included in `total_mib`; `budget(..., state_bytes_per_slot: int = 0)`.

- [ ] **Step 1: Write the failing tests**

Append to `runtime/tests/test_kvmath.py` (add `qwen35_like` to the existing `from runtime.tests.test_gguf import` line, and `RecurrentStateCost` to the `from runtime.kvmath import` line):

```python
# --- hybrid models -----------------------------------------------------------------------


def test_hybrid_kv_grows_only_on_the_attention_layers(tmp_path):
    """Qwen3.5-4B: 8 of 32 layers are full attention. Budgeting all 32 overstated
    per-token KV 4x and missed the recurrent state entirely."""
    md = read_metadata(qwen35_like(tmp_path / "h.gguf"))
    cost = KVCost.from_metadata(md, "f16")
    assert cost.n_layer == 8
    assert cost.elements_per_token == 8 * 4 * (256 + 256)  # 16,384 — not 65,536


def test_recurrent_state_matches_the_measured_checkpoint_size(tmp_path):
    """The engine reported 'restored context checkpoint ... size = 50.251 MiB' for this
    exact model shape (docs/engine-flags.md) — the formula must reproduce it."""
    md = read_metadata(qwen35_like(tmp_path / "h.gguf"))
    state = RecurrentStateCost.from_metadata(md)
    assert state is not None
    assert state.n_layers == 24
    # per layer: conv R = (4-1) x (4096 + 2*16*128) el, delta-net S = 128 x 4096 el, f32
    assert state.bytes_per_slot == 24 * ((3 * (4096 + 2 * 16 * 128)) + 128 * 4096) * 4
    assert state.mib_per_slot == pytest.approx(50.25, abs=0.1)


def test_non_hybrid_models_have_no_state_cost(tmp_path):
    md = read_metadata(qwen_like(tmp_path / "m.gguf"))
    assert RecurrentStateCost.from_metadata(md) is None


def test_budget_charges_state_per_slot(tmp_path):
    md = read_metadata(qwen35_like(tmp_path / "h.gguf"))
    state = RecurrentStateCost.from_metadata(md)
    cost = KVCost.from_metadata(md, "q8_0")
    row = budget(cost, PROFILES["classroom"], weights_mib=2611, state_bytes_per_slot=state.bytes_per_slot)
    assert row.state_mib == pytest.approx(50.25 * 6, abs=1)  # classroom runs 6 slots
    assert row.total_mib == pytest.approx(row.weights_mib + row.kv_mib + row.buffers_mib + row.state_mib)


def test_markdown_reports_the_hybrid_split(tmp_path):
    md = read_metadata(qwen35_like(tmp_path / "h.gguf"))
    cost, rows = budget_table(md)
    doc = render_markdown(md, cost, rows)
    assert "8 attention" in doc and "24 recurrent" in doc and "50.3 MiB" in doc
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest runtime/tests/test_kvmath.py -v`
Expected: five new tests FAIL (`ImportError: RecurrentStateCost` first — fix imports as you go); all existing tests PASS.

- [ ] **Step 3: Implement**

In `runtime/kvmath.py`:

(a) In `KVCost.from_metadata`, change `n_layer=md.n_layer,` to `n_layer=md.n_attn_layer,` and update the class docstring line to: `"""Per-token KV cost of one model at one cache quantization. `n_layer` counts only the layers whose KV grows with tokens (= all layers on classic transformers, `block_count // full_attention_interval` on hybrids)."""`

(b) After the `KVCost` class, add:

```python
@dataclass(frozen=True)
class RecurrentStateCost:
    """Constant-size f32 state of a hybrid model's recurrent (SSM / gated-delta-net)
    layers. Charged PER SLOT — and per context checkpoint, which is why
    `--ctx-checkpoints` is a RAM knob (runtime/config.py). Formula validated against the
    engine's own 'restored context checkpoint ... 50.251 MiB' log line for Qwen3.5-4B."""

    n_layers: int  # recurrent layers = block_count - n_attn_layer
    conv_kernel: int
    d_inner: int
    d_state: int
    n_groups: int

    @classmethod
    def from_metadata(cls, md: GGUFMetadata) -> "RecurrentStateCost | None":
        if not md.is_hybrid:
            return None
        return cls(
            n_layers=md.n_layer - md.n_attn_layer,
            conv_kernel=md.ssm_conv_kernel,
            d_inner=md.ssm_inner_size,
            d_state=md.ssm_state_size,
            n_groups=md.ssm_group_count,
        )

    @property
    def bytes_per_slot(self) -> int:
        conv = (self.conv_kernel - 1) * (self.d_inner + 2 * self.n_groups * self.d_state)
        delta = self.d_state * self.d_inner
        return self.n_layers * (conv + delta) * 4  # f32

    @property
    def mib_per_slot(self) -> float:
        return self.bytes_per_slot / MiB
```

(c) In `SlotBudget`, add field `state_mib: float = 0.0` (after `buffers_mib`) and change `total_mib` to `return self.weights_mib + self.kv_mib + self.buffers_mib + self.state_mib`.

(d) In `budget(...)`, add keyword param `state_bytes_per_slot: int = 0` and pass `state_mib=state_bytes_per_slot * profile.n_parallel / MiB` to `SlotBudget`.

(e) In `budget_table(...)`, before the row comprehension add `state = RecurrentStateCost.from_metadata(md)` and pass `state_bytes_per_slot=state.bytes_per_slot if state else 0` through to `budget(...)`.

(f) In `render_markdown(...)`: add a `state` column to the slot-budget table header (`| profile | -c | -np | ctx/slot | KV | state | weights | buffers | total | fits? |` with matching `|---|` count) and `f"{r.state_mib:.0f} MiB"` in each row; after the `Model:` paragraph add:

```python
    state = RecurrentStateCost.from_metadata(md)
    hybrid_note = (
        f"\nHybrid layout: **{md.n_attn_layer} attention** layers (token-growing KV) + "
        f"**{md.n_layer - md.n_attn_layer} recurrent** layers at a constant "
        f"**{state.mib_per_slot:.1f} MiB f32 per slot** (and per context checkpoint).\n"
        if state
        else ""
    )
```

and interpolate `{hybrid_note}` into the returned f-string after the `Per-token KV` paragraph. In that paragraph, change `{md.n_layer} ×` to `{cost.n_layer} ×` so the formula line shows attention layers.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest runtime/tests/test_kvmath.py runtime/tests/test_gguf.py -v`
Expected: all PASS (existing worked-example tests unaffected: classic models keep `n_attn_layer == n_layer` and `state_mib == 0`).

- [ ] **Step 5: Regenerate the budget doc from the real file**

Run: `python3 -m runtime.kvmath models/core/Qwen3.5-4B-Q4_K_M.gguf --markdown docs/kv-budget.md`
Expected: exit 0; `docs/kv-budget.md` now says arch `qwen35`, `8 × 4 × (256 + 256)` elements, and the hybrid note with `50.3 MiB` per slot. (The profile rows there describe main-branch classroom profiles — informational on this branch.)

- [ ] **Step 6: Lint and commit**

```bash
python3 -m ruff check . && git add runtime/kvmath.py runtime/tests/test_kvmath.py docs/kv-budget.md && git commit -m "fix(kvmath): hybrid-aware KV budget — attention layers only + per-slot recurrent state"
```

---

### Task 6: Parameterize the nginx upstream (frontend can proxy to the host)

**Files:**
- Rename: `docker/nginx.conf` → `docker/nginx.conf.template` (content edit below)
- Modify: `docker/frontend.Dockerfile:18`
- Modify: `docker-compose.yml` (frontend service)

**Interfaces:**
- Produces: env var `BACKEND_UPSTREAM` (default `backend:8000`) consumed by the nginx container at startup; Task 7 sets `BACKEND_UPSTREAM=host.docker.internal:8000` for native mode.

- [ ] **Step 1: Rename and templatize the nginx conf**

```bash
git mv docker/nginx.conf docker/nginx.conf.template
```

In `docker/nginx.conf.template`, change `proxy_pass http://backend:8000;` to:

```nginx
        # ${BACKEND_UPSTREAM} is substituted by the nginx image's envsubst entrypoint at
        # container start (default set in docker-compose.yml). Docker mode: backend:8000.
        # Native mode (run.sh --native): host.docker.internal:8000 — the gateway on the host.
        proxy_pass http://${BACKEND_UPSTREAM};
```

(nginx's own `$http_upgrade`/`$connection_upgrade`/`$host`/`$uri` variables are safe: the image's envsubst only substitutes names that exist in the container's environment.)

- [ ] **Step 2: Ship it as a template**

In `docker/frontend.Dockerfile`, replace `COPY docker/nginx.conf /etc/nginx/conf.d/default.conf` with:

```dockerfile
# Rendered to /etc/nginx/conf.d/default.conf at start by the image's envsubst entrypoint,
# substituting ${BACKEND_UPSTREAM} (see docker-compose.yml / run.sh --native).
COPY docker/nginx.conf.template /etc/nginx/templates/default.conf.template
```

- [ ] **Step 3: Wire the default in compose**

In `docker-compose.yml` frontend service, add:

```yaml
    environment:
      # nginx proxy target for /v1. run.sh --native overrides this to
      # host.docker.internal:8000 (the host gateway); docker mode keeps the service name.
      BACKEND_UPSTREAM: ${BACKEND_UPSTREAM:-backend:8000}
    extra_hosts:
      # host.docker.internal resolves natively on Docker Desktop; host-gateway makes the
      # same name work on Linux engines so native mode is not macOS-only.
      - "host.docker.internal:host-gateway"
```

- [ ] **Step 4: Verify the rendered config in docker mode**

```bash
docker compose build frontend && docker compose up -d --no-deps frontend \
  && docker compose exec frontend sh -c 'grep proxy_pass /etc/nginx/conf.d/default.conf' \
  && docker compose exec frontend sh -c 'nginx -t' \
  && docker compose stop frontend
```

Expected: `proxy_pass http://backend:8000;` and `syntax is ok / test is successful`.

- [ ] **Step 5: Commit**

```bash
git add docker/nginx.conf.template docker/frontend.Dockerfile docker-compose.yml && git commit -m "feat(frontend): env-templated nginx upstream (BACKEND_UPSTREAM)"
```

---

### Task 7: `run.sh --native` — host backend, pinned arm64 engine, docker by default

**Files:**
- Modify: `run.sh` (arg parsing, usage, image build section, provisioning section, new `fetch_native_engine` + `native_up` functions)
- Modify: `RUN.md` (native-mode section)

**Interfaces:**
- Consumes: `BACKEND_UPSTREAM` (Task 6), `MUTA_RT_*` env names (Tasks 1–3), draft path `models/draft/Qwen3.5-0.8B-Q4_K_M.gguf` (Task 3), `runtime/server.py:find_binary` search order (`MUTA_RT_LLAMA_SERVER_BIN` → `runtime/build/bin/llama-server` → PATH).
- Produces: `./run.sh --native` (docker remains the default with no flag); pinned engine release tag constant `ENGINE_TAG=b10035`.

- [ ] **Step 1: Rework argument parsing and usage**

In `run.sh`, replace the `usage()` heredoc body and the `NO_CACHE=0 / case "${1:-}"` block with:

```bash
usage() {
    cat <<'EOF'
Usage: ./run.sh [--native] [--build] | down | logs

  (no args)   docker mode (default): bring up db + backend + frontend, print the UI URL
  --native    dev mode: db + frontend stay in docker; the gateway and an arm64
              llama-server run on THIS host in the foreground (Ctrl-C stops them;
              './run.sh down' stops the containers). No slow amd64 emulation.
  --build     force a clean (no-cache) image rebuild first (docker images only)
  down        docker compose down (conversations survive: the muta-pgdata volume stays)
  logs        docker compose logs -f

The first docker run compiles llama.cpp (slow) and downloads ~4 GB of models into
./models (kept for every later run). Later runs start in seconds. Native mode needs
'make install' (an importable venv) and downloads the pinned llama.cpp arm64 release
into runtime/build/bin on first use.
EOF
}

MODE=docker
NO_CACHE=0
while [ $# -gt 0 ]; do
    case "$1" in
        --native)   MODE=native ;;
        --build)    NO_CACHE=1 ;;
        down)       exec docker compose down ;;
        logs)       exec docker compose logs -f ;;
        -h|--help)  usage; exit 0 ;;
        *)          die "unknown option: $1  (try --help)" ;;
    esac
    shift
done
```

- [ ] **Step 2: Skip the backend image build in native mode**

Wrap section 1 (Images) so native mode builds only the frontend:

```bash
if [ "$MODE" = native ]; then
    info "native mode: building only the frontend image (the backend runs on this host)"
    docker compose build frontend || die "frontend image build failed"
elif [ "$NO_CACHE" = 1 ]; then
    ... existing --no-cache branch unchanged ...
else
    ... existing cached-build branch unchanged ...
fi
```

- [ ] **Step 3: Host-side provisioning in native mode**

In section 2 (Model provisioning), replace the `docker compose run` invocation inside the `if [ "$missing" = 1 ]` branch with a mode split:

```bash
    if [ "$MODE" = native ]; then
        "${PY:-python3}" scripts/fetch_models.py --with-draft --mmproj-precision f16 \
            || die "model provisioning failed — rerun ./run.sh --native (downloads resume)"
    else
        docker compose run --rm --no-deps backend \
            python3.10 scripts/fetch_models.py --with-draft --mmproj-precision f16 \
            || die "model provisioning failed — rerun ./run.sh (downloads resume where they stopped)"
    fi
```

- [ ] **Step 4: Add the pinned-engine fetch and native_up**

After the `usage()` function, add:

```bash
# Pinned in runtime/VERSIONS.md — must match the container build so native-mode numbers
# are comparable. VERSIONS.md documents this exact practice for macOS dev.
ENGINE_TAG=b10035

fetch_native_engine() {
    # find_binary order (runtime/server.py): env override, runtime/build/bin, PATH.
    [ -n "${MUTA_RT_LLAMA_SERVER_BIN:-}" ] && [ -x "$MUTA_RT_LLAMA_SERVER_BIN" ] && return 0
    [ -x runtime/build/bin/llama-server ] && return 0
    command -v llama-server >/dev/null 2>&1 && {
        warn "using llama-server from PATH — NOT the pinned ${ENGINE_TAG}; numbers are not comparable"
        return 0
    }
    [ "$(uname -s)/$(uname -m)" = "Darwin/arm64" ] \
        || die "no llama-server found — install one on PATH or set MUTA_RT_LLAMA_SERVER_BIN"
    info "fetching pinned llama.cpp ${ENGINE_TAG} (macos-arm64 release) into runtime/build/bin"
    tmp=$(mktemp -d)
    url="https://github.com/ggml-org/llama.cpp/releases/download/${ENGINE_TAG}/llama-${ENGINE_TAG}-bin-macos-arm64.zip"
    curl -fL --retry 3 -o "$tmp/llama.zip" "$url" \
        || die "release download failed ($url) — install llama-server yourself and rerun"
    unzip -q -o "$tmp/llama.zip" -d "$tmp"
    src=$(find "$tmp" -name llama-server -type f | head -1)
    [ -n "$src" ] || die "llama-server missing from the release zip — layout changed? extract manually into runtime/build/bin"
    mkdir -p runtime/build/bin
    cp "$src" runtime/build/bin/
    find "$tmp" \( -name '*.dylib' -o -name '*.metal' \) -exec cp {} runtime/build/bin/ \; || true
    chmod +x runtime/build/bin/llama-server
    rm -rf "$tmp"
}

native_up() {
    "${PY:-python3}" -c "import orchestrator, uvicorn" >/dev/null 2>&1 \
        || die "project not importable by ${PY:-python3} — activate your venv and run 'make install'"
    fetch_native_engine
    info "starting db (docker)"
    docker compose up -d --wait db || die "db failed to start"
    info "starting frontend (docker, proxying /v1 to this host)"
    BACKEND_UPSTREAM="host.docker.internal:8000" docker compose up -d --no-deps frontend \
        || die "frontend failed to start"
    bold "Native dev mode — backend runs in THIS terminal. Ctrl-C stops it; './run.sh down' stops the containers."
    info "chat UI:   http://localhost:3000   (proxies 502 until the model finishes loading — seconds natively)"
    info "API:       http://localhost:8000/v1  (docs at http://localhost:8000/docs)"
    export MUTA_RT_AUTOSTART=1
    export MUTA_RT_MODEL_DIR=models/core
    export MUTA_RT_MODEL_FILE=Qwen3.5-4B-Q4_K_M.gguf
    export MUTA_RT_MODEL_ALIAS=qwen3.5-4b
    export MUTA_RT_N_CTX=2048
    export MUTA_RT_ENABLE_THINKING=1
    export MUTA_RT_AUTO_DOWNLOAD=0
    export MUTA_RT_DRAFT_MODEL=models/draft/Qwen3.5-0.8B-Q4_K_M.gguf
    export MUTA_RT_STARTUP_TIMEOUT_S=300
    export TUTOR_ROOT="$PWD"
    # No MUTA_RT_N_THREADS here: llama.cpp's own Apple P/E-core detection beats a guess.
    exec "${PY:-python3}" -m uvicorn orchestrator.main:app --host 0.0.0.0 --port 8000
}
```

- [ ] **Step 5: Branch into native mode after provisioning**

Replace section 3's opening (before `docker compose up -d --wait`) with:

```bash
if [ "$MODE" = native ]; then
    native_up   # execs uvicorn; never returns
fi
```

(The existing docker-mode `docker compose up -d --wait` block stays as-is below it.)

- [ ] **Step 6: Syntax-check both modes' plumbing**

Run: `bash -n run.sh && ./run.sh --help`
Expected: no syntax errors; help shows `--native`.

- [ ] **Step 7: Document native mode in RUN.md**

Add a `## Native dev mode` section to `RUN.md` after the quick-start:

```markdown
## Native dev mode (Apple silicon)

`./run.sh --native` skips the amd64 emulation tax for day-to-day dev: db and frontend
stay in docker, the gateway + llama-server run on the host (arm64). The pinned
llama.cpp `b10035` macos-arm64 release is fetched into `runtime/build/bin` on first
use, so engine parity with the container is kept. Requires `make install` (importable
venv). Ctrl-C stops the backend; `./run.sh down` stops the containers. Audio degrades
to text-only unless sherpa-onnx is installed on the host — expected in native mode.

Docker (`./run.sh`, no flag) remains the default and the shape that ships: linux/amd64,
compose-gated health, the compiled AVX2 engine. Use it for anything you are about to
call a measurement of the real system, and re-verify there after native-mode iteration.
Mac-native numbers are dev signals only (`bench/optimization-log.md` rule).
```

- [ ] **Step 8: Commit**

```bash
git add run.sh RUN.md && git commit -m "feat(run.sh): --native dev mode — host gateway + pinned arm64 engine, docker default"
```

---

### Task 8: Docker-mode verification, engine-facts doc, optimization-log rows

**Files:**
- Create: `docs/engine-flags.md`
- Modify: `bench/optimization-log.md` (append rows)
- No product code changes — this task validates Tasks 1–6 end to end and records the evidence.

**Interfaces:**
- Consumes: everything above. The acceptance criteria here are the plan's definition of done for docker mode.

- [ ] **Step 1: Fetch the 0.8B draft and rebuild the backend image**

```bash
docker compose build backend
docker compose run --rm --no-deps backend python3.10 scripts/fetch_models.py --with-draft --only draft
ls -la models/draft/Qwen3.5-0.8B-Q4_K_M.gguf
```

Expected: file exists (~0.5–0.7 GB, sha256-verified by the fetcher).

- [ ] **Step 2: Assert the launch command before booting**

```bash
docker compose run --rm --no-deps backend python3.10 -m runtime.server --print-cmd
```

Expected substrings: `--parallel 2`, `--ctx-checkpoints 4`, `--cache-ram 256`, `-b 512`, `-ub 128`, `--cache-type-k q8_0`, `--reasoning-budget 512`, `--threads 8`, `--threads-batch 10`, `--spec-type draft-simple`, `--spec-draft-model /app/models/draft/Qwen3.5-0.8B-Q4_K_M.gguf`. If any is missing, stop and fix the task that owns it.

- [ ] **Step 3: Boot and check the engine accepted the draft**

```bash
./run.sh
docker compose exec backend sh -c 'grep -iE "spec|draft|vocab|n_slots|checkpoints" /app/data/logs/llama-server.log | head -20'
```

Expected: a draft-model load line, **no** "vocabs are not compatible" line, `n_slots = 2`, `context checkpoints enabled, max = 4`. **Decision gate:** if the 0.8B vocab is ALSO rejected, set `MUTA_RT_SPEC_TYPE: "ngram-simple"` in compose instead, note it in `docs/engine-flags.md`, and record the draft as unusable — do not ship a dead flag again.

- [ ] **Step 4: Two-turn probe — reuse must survive the caps, acceptance gets measured**

```bash
docker compose exec backend python3.10 - <<'EOF'
import json, urllib.request

def turn(messages, max_tokens):
    payload = {"messages": messages, "stream": False, "temperature": 0.0, "top_k": 1,
               "seed": 4242, "max_tokens": max_tokens,
               "chat_template_kwargs": {"enable_thinking": True}}
    req = urllib.request.Request("http://127.0.0.1:8080/v1/chat/completions",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    body = json.loads(urllib.request.urlopen(req, timeout=900).read())
    t, u = body.get("timings") or {}, body.get("usage") or {}
    print({k: t.get(k) for k in ("prompt_n", "predicted_n", "predicted_per_second",
                                 "draft_n", "draft_n_accepted")}, "usage:", u.get("prompt_tokens"))
    return body["choices"][0]["message"]["content"]

sys = {"role": "system", "content": "You are a patient tutor for mathematics."}
u1 = {"role": "user", "content": "A rectangle has perimeter 36 cm and length twice its width. Dimensions?"}
a1 = turn([sys, u1], 256)
turn([sys, u1, {"role": "assistant", "content": a1},
      {"role": "user", "content": "Now a square with the same perimeter — side length and which area is bigger?"}], 192)
EOF
```

Expected: turn 2's `prompt_n` is well below its `usage` prompt tokens (checkpoint restore intact under `--ctx-checkpoints 4`); `draft_n`/`draft_n_accepted` are non-null — record the acceptance ratio. If turn 2 re-processes everything, raise `MUTA_RT_CTX_CHECKPOINTS` until reuse returns and record the working value.

- [ ] **Step 5: Measure RSS and write the engine-facts doc**

```bash
docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' $(docker compose ps -q backend)
```

Create `docs/engine-flags.md`:

```markdown
# llama.cpp b10035 — behaviours the flags depend on (measured, not assumed)

Verified 2026-07-31 against the pinned build (`602f828`) with
`models/core/Qwen3.5-4B-Q4_K_M.gguf`, and re-verified whenever the pin moves.
`runtime/config.py` defaults and `docker-compose.yml` comments cite this file.

## Speculation is gated by --spec-type

`--spec-type` defaults to `none`; `--spec-draft-model` alone is silently ignored (no
draft load, no `[spec]` log lines). The dev branch shipped exactly that dead
configuration. `runtime/server.py:_speculation_flags` now always emits `--spec-type`.

## Draft vocab compatibility is enforced

Qwen3-0.6B (vocab 151,936) is rejected for Qwen3.5-4B (vocab 248,320):
`the target and draft vocabs are not compatible`. Only Qwen3.5-family drafts are
viable; the roster's tier-B Qwen3.5-0.8B (`fetch_models --with-draft`) is the draft of
record. <!-- Task 8 Step 3: append the measured 0.8B result (accepted + acceptance rate, or rejected) here. -->

## The hybrid architecture makes state, not KV, the RAM driver

Qwen3.5-4B runs full attention on 8 of 32 layers (`full_attention_interval = 4`);
per-token KV is ~24.5 KiB (q8_0 K + f16 V) — `runtime/kvmath.py` models this. The other
24 layers carry ~50.25 MiB of f32 recurrent state per slot, and every context
checkpoint copies it. Defaults before capping: `-np auto` → 4 slots, 32 checkpoints per
slot, `--cache-ram 8192` (each cached conversation ≈ 57 MiB) — measured RSS drift
2.9 → 4.8 GiB in four short requests. Caps now live in `RuntimeConfig`
(`n_parallel=2, ctx_checkpoints=4, cache_ram_mib=256`).

## Multi-turn prefix reuse works via checkpoint restore

With thinking-stripped history (the product's replay shape), turn 2 of a 269-token
conversation restored the end-of-prompt checkpoint and processed only 149 tokens.
Reuse must be re-verified whenever `ctx_checkpoints` changes — too low a cap silently
degrades to full re-prefill.

## ngram speculation needs non-default params on this workload

`ngram-simple` at engine defaults (lookup N=12) produced zero drafts on tutoring
turns. `size-n 4 / size-m 12` measured 12–22% token acceptance (mean accepted run
3.3). Zero RAM; net-neutral under emulation (compute-bound); expected to pay only on
bandwidth-bound hardware. Wired as `spec_type: "ngram-simple"`.

## Misc

- `-np -1` (auto) resolves to 4 slots with `kv_unified = true` at `-c 2048`.
- Default threads = ALL cores for decode and prefill (`n_threads = 10 (n_threads_batch = 10)`
  in the 10-vCPU VM) — compose pins 8/10.
- `--defrag-thold` is deprecated in this build (profiles.py still passes it — harmless).
- Weight loading repacks ~1.3 GiB of the 4B's tensors into anonymous RAM
  (`CPU_REPACK`) for AVX2 kernels; model memory ≈ 2.6 GiB total, context ≈ 250 MiB at
  the old 4-slot default, compute ≈ 31 MiB at `-ub 128`.
```

Fill in the Step 3/4 measurements (0.8B verdict, acceptance rate) where marked.

- [ ] **Step 6: Append optimization-log rows**

Append to the autonomous-runs table area of `bench/optimization-log.md` (manual rows, same columns as the header table at line 40), using the measured numbers from Steps 4–5:

```markdown
| 2026-07-31 | RSS ceilings: -np 2, --ctx-checkpoints 4, --cache-ram 256 (was auto-4/32/8192) | two-turn probe, docker/emulated | 15 | <before TPS> / 4.8 GB / — | <after TPS> / <after GB> / — | ~0 | <ΔGB> | 0 | dev_host_provisional — RAM row only | keep |
| 2026-07-31 | speculation ON: --spec-type draft-simple + Qwen3.5-0.8B (dead flags + incompatible 0.6B before) | two-turn probe, docker/emulated | 15 | <TPS w/o> / — / — | <TPS with> / +<draft GB> / — | <Δ> | +<GB> | 0 | dev_host_provisional — acceptance <n>% ; target-box row pending | park (needs x86 numbers) |
```

- [ ] **Step 7: Run the full test suite and smoke, then commit**

```bash
python3 -m pytest && make smoke
git add docs/engine-flags.md bench/optimization-log.md && git commit -m "docs: verified b10035 engine facts + optimization-log rows for RSS caps and speculation"
```

---

### Task 9: Native-mode verification + log row

**Files:**
- Modify: `bench/optimization-log.md` (append one row)
- No code changes — validates Task 7 end to end.

- [ ] **Step 1: Bring up native mode**

In one terminal (or backgrounded with output to a file):

```bash
./run.sh --native
```

Expected: frontend + db containers start; uvicorn binds :8000; llama-server (arm64) loads the 4B in seconds-to-tens-of-seconds; `curl -s http://localhost:8000/v1/ready` eventually reports `"ready":true`.

- [ ] **Step 2: Verify the UI proxy path**

```bash
curl -fsS http://localhost:3000/v1/health
```

Expected: `{"status":"ok"}` via nginx → host.docker.internal → host gateway.

- [ ] **Step 3: Measure native decode and speculation**

Run the same two-turn probe as Task 8 Step 4 against the host engine (`http://127.0.0.1:8080`, plain `python3` heredoc on the host this time). Record `predicted_per_second`, `draft_n_accepted / draft_n`, and turn-2 `prompt_n`.

Expected: decode several× the emulated ~5 tok/s (M2 Pro is bandwidth-rich; the draft may genuinely pay here — record whichever way it goes).

- [ ] **Step 4: Confirm docker mode is untouched**

```bash
./run.sh down && ./run.sh && make smoke && ./run.sh down
```

Expected: default path still boots the 3-container amd64 stack and passes smoke.

- [ ] **Step 5: Append the native row and commit**

Append to `bench/optimization-log.md` (same columns as Task 8 Step 6):

```markdown
| 2026-07-31 | run.sh --native (host arm64 engine; docker default unchanged) | two-turn probe, native | 15 | ~5 tok/s emulated | <native TPS> / <GB> / — | +<Δ> | ~0 | 0 | dev_host_provisional — dev-loop only, never report-grade | keep |
```

```bash
git add bench/optimization-log.md && git commit -m "bench: native-mode dev numbers (dev_host_provisional)"
```

---

## Self-review notes

- **Spec coverage:** item 1 (RAM caps) → Tasks 1, 8; item 2 (native flag, docker default) → Tasks 6, 7, 9; item 3 (0.8B draft + threads + tuned ngram fallback) → Tasks 2, 3, 8; item 4 (launch-path unification + dead-config fix + kvmath) → Tasks 1–5.
- **Known risks, called out where they bite:** the 0.8B vocab could still mismatch (Task 8 Step 3 decision gate); the arm64 release-zip asset name/layout may differ at `b10035` (Task 7 `fetch_native_engine` dies with a manual-install instruction rather than guessing); `--ctx-checkpoints 4` could evict the reuse checkpoint on long generations (Task 8 Step 4 asserts reuse and names the remedy).
- **Type consistency:** config field names (`n_parallel`, `ctx_checkpoints`, `cache_ram_mib`, `n_threads_batch`, `n_batch`, `n_ubatch`, `cache_type_k`, `reasoning_budget`, `spec_type`) are used identically in Tasks 1–3 code, compose env names, and RUN.md rows; `RecurrentStateCost` names match between Tasks 4–5.
