"""`LlamaServer.build_command` — the flags are the contract with the engine."""

from __future__ import annotations

from runtime.config import RuntimeConfig
from runtime.server import LlamaServer


def _cfg(tmp_path, **overrides) -> tuple[RuntimeConfig, object]:
    bin_path = tmp_path / "llama-server"
    bin_path.touch()
    model = tmp_path / "model.gguf"
    model.touch()
    cfg = RuntimeConfig(llama_server_bin=str(bin_path), _env_file=None, **overrides)
    return cfg, model


def test_build_command_baseline_flags(tmp_path):
    cfg, model = _cfg(tmp_path)
    cmd = LlamaServer(cfg).build_command(model)
    assert cmd[cmd.index("--model") + 1] == str(model)
    assert "--jinja" in cmd


def test_build_command_emits_draft_flags_when_draft_model_exists(tmp_path):
    draft = tmp_path / "draft.gguf"
    draft.touch()
    cfg, model = _cfg(tmp_path, draft_model=draft, spec_type="draft-simple")
    cmd = LlamaServer(cfg).build_command(model)
    assert cmd[cmd.index("--spec-draft-model") + 1] == str(draft)
    assert cmd[cmd.index("--spec-draft-n-max") + 1] == "8"
    assert cmd[cmd.index("--spec-draft-n-min") + 1] == "1"
    assert cmd[cmd.index("--spec-draft-p-min") + 1] == "0.75"
    assert cmd[cmd.index("--spec-type") + 1] == "draft-simple"


def test_speculation_is_off_by_default_even_with_a_draft_present(tmp_path):
    """Measured net-negative on CPU in every form (runtime/config.py spec_type), and the
    draft costs ~520 MiB against an 8 GB box whose ceiling is a disqualification."""
    draft = tmp_path / "draft.gguf"
    draft.touch()
    cfg, model = _cfg(tmp_path, draft_model=draft)
    cmd = LlamaServer(cfg).build_command(model)
    assert "--spec-type" not in cmd and "--spec-draft-model" not in cmd


def test_build_command_omits_draft_flags_when_unset(tmp_path):
    cfg, model = _cfg(tmp_path)
    cmd = LlamaServer(cfg).build_command(model)
    assert "--spec-draft-model" not in cmd


def test_build_command_omits_draft_flags_when_draft_file_missing(tmp_path):
    cfg, model = _cfg(tmp_path, draft_model=tmp_path / "missing.gguf")
    cmd = LlamaServer(cfg).build_command(model)
    assert "--spec-draft-model" not in cmd
    assert "--spec-draft-n-max" not in cmd
    assert "--spec-type" not in cmd


def test_no_repack_off_by_default_and_flips_via_config(tmp_path):
    # Default: engine default (repack on) — no flag emitted. The lever exists because
    # repack costs ~model-size anonymous RAM (RESULTS.md 2026-08-04: 3236 -> 602 MiB
    # phys_footprint on the 4B) and the 8 GB target box has a 7 GB disqualification
    # ceiling; the default flips only with a measured x86 A/B.
    cfg, model = _cfg(tmp_path)
    assert "--no-repack" not in LlamaServer(cfg).build_command(model)
    cfg_on, model_on = _cfg(tmp_path, no_repack=True)
    assert "--no-repack" in LlamaServer(cfg_on).build_command(model_on)


def test_build_command_bounds_engine_memory(tmp_path):
    """b10035 defaults are sized for bigger boxes: -np auto -> 4 slots x ~50 MiB f32 state,
    32 checkpoints/slot, 8 GiB prompt cache. These flags are what bound steady-state RSS."""
    cfg, model = _cfg(tmp_path)
    cmd = LlamaServer(cfg).build_command(model)
    assert cmd[cmd.index("--parallel") + 1] == "2"
    # 2 checkpoints: two-turn restore measured intact, ~100-200 MiB shaved (2026-08-01)
    assert cmd[cmd.index("--ctx-checkpoints") + 1] == "2"
    assert cmd[cmd.index("--cache-ram") + 1] == "256"


def test_kv_unified_restores_full_window_sharing(tmp_path):
    """Explicit --parallel silently turns unified KV off (2048 -> 1024/slot, measured:
    longer prompts 400). Default True re-enables sharing; opt-out stays possible."""
    cfg, model = _cfg(tmp_path)
    assert "--kv-unified" in LlamaServer(cfg).build_command(model)
    cfg2, model2 = _cfg(tmp_path, kv_unified=False)
    assert "--kv-unified" not in LlamaServer(cfg2).build_command(model2)


def test_thread_defaults_pin_performance_cores_on_apple_silicon(tmp_path):
    """Measured (RESULTS.md 2026-08-01): engine-default threading is unstable on the
    P/E-asymmetric dev host; the P-core count wins for decode AND prefill. Elsewhere the
    engine default (no flag) stands. Explicit values always win."""
    from runtime.config import darwin_performance_cores

    cfg, model = _cfg(tmp_path)
    cmd = LlamaServer(cfg).build_command(model)
    pcores = darwin_performance_cores()
    if pcores:
        assert cmd[cmd.index("--threads") + 1] == str(pcores)
        assert cmd[cmd.index("--threads-batch") + 1] == str(pcores)
    else:
        assert "--threads" not in cmd and "--threads-batch" not in cmd

    cfg2, model2 = _cfg(tmp_path, n_threads=8, n_threads_batch=10)
    cmd2 = LlamaServer(cfg2).build_command(model2)
    assert cmd2[cmd2.index("--threads") + 1] == "8"
    assert cmd2[cmd2.index("--threads-batch") + 1] == "10"


def test_spec_type_gates_the_draft_flags(tmp_path):
    """b10035 ignores --spec-draft-model unless --spec-type selects an implementation
    (engine default none) — the flags were silently dead before this field existed."""
    draft = tmp_path / "draft.gguf"
    draft.touch()
    cfg, model = _cfg(tmp_path, draft_model=draft, spec_type="draft-simple")
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


def test_batch_and_cache_flags_come_from_config_not_extra_args(tmp_path):
    """These four lived in MUTA_RT_EXTRA_SERVER_ARGS in docker-compose.yml — a JSON string
    outside the config schema. Fields make them visible, testable and overridable."""
    cfg, model = _cfg(tmp_path)
    cmd = LlamaServer(cfg).build_command(model)
    assert cmd[cmd.index("-b") + 1] == "512"
    assert cmd[cmd.index("-ub") + 1] == "128"
    assert cmd[cmd.index("--cache-type-k") + 1] == "q8_0"
    assert cmd[cmd.index("--reasoning-budget") + 1] == "512"


def test_gpu_layers_accepts_the_engine_vocabulary(tmp_path):
    """At the pin -ngl takes a number, 'auto' or 'all' (default auto): 'all' is how native
    Metal mode offloads without hardcoding a layer count."""
    cfg, model = _cfg(tmp_path, n_gpu_layers="all")
    cmd = LlamaServer(cfg).build_command(model)
    assert cmd[cmd.index("--n-gpu-layers") + 1] == "all"


def test_gpu_layers_default_stays_cpu(tmp_path):
    """-ngl DEFAULTS to auto at this pin — the explicit 0 is what keeps CPU paths CPU."""
    cfg, model = _cfg(tmp_path)
    cmd = LlamaServer(cfg).build_command(model)
    assert cmd[cmd.index("--n-gpu-layers") + 1] == "0"
