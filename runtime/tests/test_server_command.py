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
    cfg, model = _cfg(tmp_path, draft_model=draft)
    cmd = LlamaServer(cfg).build_command(model)
    assert cmd[cmd.index("--spec-draft-model") + 1] == str(draft)
    assert cmd[cmd.index("--spec-draft-n-max") + 1] == "8"
    assert cmd[cmd.index("--spec-draft-n-min") + 1] == "1"
    assert cmd[cmd.index("--spec-draft-p-min") + 1] == "0.75"


def test_build_command_omits_draft_flags_when_unset(tmp_path):
    cfg, model = _cfg(tmp_path)
    cmd = LlamaServer(cfg).build_command(model)
    assert "--spec-draft-model" not in cmd


def test_build_command_omits_draft_flags_when_draft_file_missing(tmp_path):
    cfg, model = _cfg(tmp_path, draft_model=tmp_path / "missing.gguf")
    cmd = LlamaServer(cfg).build_command(model)
    assert "--spec-draft-model" not in cmd
    assert "--spec-draft-n-max" not in cmd


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
