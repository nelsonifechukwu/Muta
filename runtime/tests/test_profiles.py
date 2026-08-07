"""Serving-profile tests (TDD §6.2–§6.4, §6.7).

These read like a transcription of the TDD's flag table, and that is the intent: the flags
*are* the memory budget and the DQ guard, so a silent drift (a dropped `--pooling cls`, a
`--parallel` that went back to auto, an mmproj instance asking for `--cache-reuse`) has to
fail here rather than on a judge's laptop.
"""

from __future__ import annotations

import pytest

from runtime.profiles import (
    PROFILES,
    BundlePaths,
    ThreadPlan,
    core_text_command,
    core_vision_command,
    draft_command,
    embed_command,
    get_profile,
    main,
    thread_plan,
)


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    """A staged bundle with a fake engine and fake weights — enough to build invocations."""
    root = tmp_path / "opt-tutor"
    for d in ("bin", "models/core", "models/adapters", "models/draft", "models/embed", "data/kv-slots", "data/logs"):
        (root / d).mkdir(parents=True)
    (root / "bin" / "llama-server-core").write_text("#!/bin/sh\n")
    (root / "bin" / "llama-server-core").chmod(0o755)
    (root / "models" / "core" / "core-q4_k_m.gguf").write_bytes(b"GGUF")
    (root / "models" / "core" / "mmproj-q8_0.gguf").write_bytes(b"GGUF")
    (root / "models" / "draft" / "draft-q4_k_m.gguf").write_bytes(b"GGUF")
    (root / "models" / "embed" / "bge-small-q8_0.gguf").write_bytes(b"GGUF")
    (root / "models" / "adapters" / "tutor-persona.gguf").write_bytes(b"GGUF")
    (root / "models" / "adapters" / "marking-mode.gguf").write_bytes(b"GGUF")
    (root / "data" / "api.key").write_text("secret-key\n")
    monkeypatch.setenv("TUTOR_ROOT", str(root))
    monkeypatch.delenv("PROFILE", raising=False)
    for var in ("TUTOR_KV_TYPE", "TUTOR_MLOCK", "TUTOR_TTS_ENGINE", "TUTOR_SPECULATION"):
        monkeypatch.delenv(var, raising=False)
    for var in ("TUTOR_CORE_THREADS", "TUTOR_CORE_THREADS_BATCH", "TUTOR_VISION_THREADS"):
        monkeypatch.setenv(var, "0")
    return BundlePaths(root)


def flag_value(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


# --- the §5.2 profile rows ---------------------------------------------------------------


def test_default_profile_is_classroom_6_short():
    """30 phones share 6 slots via suspend/resume, so slots are sized for the working set."""
    p = get_profile()
    assert (p.name, p.n_ctx, p.n_parallel, p.ctx_per_slot) == ("classroom", 12288, 6, 2048)


@pytest.mark.parametrize(
    "name,n_ctx,n_parallel,ctx_per_slot",
    [("classroom", 12288, 6, 2048), ("classroom-6", 24576, 6, 4096), ("classroom-8", 32768, 8, 4096), ("solo-demo", 8192, 2, 4096)],
)
def test_profile_rows_match_the_tdd_table(name, n_ctx, n_parallel, ctx_per_slot):
    p = PROFILES[name]
    assert (p.n_ctx, p.n_parallel, p.ctx_per_slot) == (n_ctx, n_parallel, ctx_per_slot)


def test_solo_demo_turns_on_the_things_classroom_cannot_afford():
    p = PROFILES["solo-demo"]
    assert p.mlock is True and p.tts_engine == "kokoro"
    assert PROFILES["classroom"].mlock is False and PROFILES["classroom"].tts_engine == "piper"


def test_open_gates_are_env_switchable_without_a_rebuild(monkeypatch):
    monkeypatch.setenv("TUTOR_KV_TYPE", "q5_1")  # D6
    monkeypatch.setenv("TUTOR_MLOCK", "1")  # D9
    p = get_profile("classroom")
    assert p.cache_type == "q5_1" and p.mlock is True


def test_unknown_profile_is_a_loud_error(monkeypatch):
    with pytest.raises(KeyError, match="unknown profile"):
        get_profile("classroom-99")


# --- CORE-TEXT (§6.2) --------------------------------------------------------------------


def test_core_text_carries_every_load_bearing_flag(bundle):
    argv = core_text_command(bundle).argv
    assert flag_value(argv, "-c") == "12288"
    assert flag_value(argv, "--parallel") == "6"  # never left to auto: it fights the cgroup cap
    assert flag_value(argv, "--cache-type-k") == "q8_0"
    assert flag_value(argv, "--cache-type-v") == "q8_0"
    assert flag_value(argv, "--flash-attn") == "on"  # forced, not auto — quantized V needs it
    assert flag_value(argv, "--cache-reuse") == "256"  # what makes the §7.3 layout cheap
    assert flag_value(argv, "--cache-ram") == "512"
    assert flag_value(argv, "--defrag-thold") == "0.10"
    assert flag_value(argv, "--slot-save-path").endswith("data/kv-slots")
    for flag in ("--kv-unified", "--cont-batching", "--context-shift", "--jinja", "--metrics", "--slots", "--props", "--no-webui"):
        assert flag in argv, flag


def test_core_text_binds_loopback_and_carries_the_api_key(bundle):
    argv = core_text_command(bundle).argv
    assert flag_value(argv, "--host") == "127.0.0.1"
    assert flag_value(argv, "--api-key") == "secret-key"


def test_adapters_are_listed_but_inactive(bundle):
    argv = core_text_command(bundle).argv
    assert "--lora-init-without-apply" in argv
    assert argv.count("--lora") == 2, "both adapters listed; activation is per-request (§7.4)"


def test_no_mlock_in_classroom_and_mlock_in_solo_demo(bundle):
    assert "--mlock" not in core_text_command(bundle).argv
    inv = core_text_command(bundle, PROFILES["solo-demo"])
    assert "--mlock" in inv.argv
    assert any("mlock ON" in n for n in inv.notes), "a RAM-pinning decision must be announced"


def test_speculation_is_off_by_default(bundle):
    assert "--spec-draft-model" not in core_text_command(bundle).argv


def test_speculation_b_adds_draft_flags(bundle, monkeypatch):
    monkeypatch.setenv("TUTOR_SPECULATION", "b")
    inv = core_text_command(bundle)
    assert flag_value(inv.argv, "--spec-draft-n-max") == "8"
    assert flag_value(inv.argv, "--spec-draft-model").endswith("draft-q4_k_m.gguf")


def test_speculation_b_degrades_to_none_when_no_draft_model_is_staged(bundle, monkeypatch):
    monkeypatch.setenv("TUTOR_SPECULATION", "b")
    (bundle.root / "models" / "draft" / "draft-q4_k_m.gguf").unlink()
    inv = core_text_command(bundle)
    assert "--spec-draft-model" not in inv.argv
    assert any("falling back to D2-c" in n for n in inv.notes)


def test_thread_flags_come_from_the_table(bundle):
    plan = ThreadPlan(cores=6, core_threads=4, core_threads_batch=6, vision_threads=3)
    argv = core_text_command(bundle, plan=plan).argv
    assert flag_value(argv, "--threads") == "4"  # decode: bandwidth-bound
    assert flag_value(argv, "--threads-batch") == "6"  # prefill: compute-bound, may exceed
    assert flag_value(argv, "--threads-http") == "2"


def test_env_can_pin_threads_over_the_table(bundle, monkeypatch):
    monkeypatch.setenv("TUTOR_CORE_THREADS", "3")
    argv = core_text_command(bundle, plan=ThreadPlan(6, 4, 6, 3)).argv
    assert flag_value(argv, "--threads") == "3"


# --- CORE-VISION (§6.3) ------------------------------------------------------------------


def test_vision_omits_the_three_flags_mmproj_disables(bundle):
    """#21133: an mmproj sets the multimodal capability flag on every slot, which disables
    prompt-cache reuse, slot save/restore and context shift. Requesting them would assert."""
    argv = core_vision_command(bundle).argv
    for forbidden in ("--cache-reuse", "--slot-save-path", "--context-shift"):
        assert forbidden not in argv, f"{forbidden} is not available under mmproj"


def test_vision_is_a_second_instance_over_the_same_weight_file(bundle):
    text = core_text_command(bundle).argv
    vision = core_vision_command(bundle).argv
    assert flag_value(text, "-m") == flag_value(vision, "-m"), "page cache shares the weights"
    assert flag_value(vision, "--mmproj").endswith("mmproj-q8_0.gguf")
    assert flag_value(vision, "--port") != flag_value(text, "--port")


def test_vision_uses_smaller_batches_than_core(bundle):
    argv = core_vision_command(bundle).argv
    assert flag_value(argv, "-b") == "1024" and flag_value(argv, "-ub") == "256"


def test_vision_forces_the_qwen_vl_image_token_floor(bundle):
    """The pinned engine warns at load that Qwen-VL models need ≥ 1024 image tokens to read
    accurately (upstream #16842). Without the floor a 1280 px photo encodes to ~58 tokens and
    the "transcription" is confident garbage returned as accepted:true — the worst failure a
    tutor can produce."""
    argv = core_vision_command(bundle).argv
    assert flag_value(argv, "--image-min-tokens") == "1024"


def test_vision_keeps_weights_on_the_shared_page_cache(bundle):
    """The "second instance is nearly free" claim only holds for mmap'd pages: the engine's
    default repack copies Q4-family tensors into PRIVATE anonymous buffers, so a repacked
    vision spike stacked on the repacked chat server would blow the 8 GB box's 7 GB
    disqualification ceiling."""
    assert "--no-repack" in core_vision_command(bundle).argv


# --- EMBED (§6.7) ------------------------------------------------------------------------


def test_embed_uses_cls_pooling(bundle):
    """BGE is trained with CLS pooling; mean-pooling degrades retrieval silently — no error,
    just worse top-k, which is the hardest kind of bug to notice in a demo."""
    argv = embed_command(bundle).argv
    assert flag_value(argv, "--pooling") == "cls"
    assert "--embeddings" in argv
    assert flag_value(argv, "-c") == "512" and flag_value(argv, "--threads") == "1"


def test_draft_server_is_small(bundle):
    argv = draft_command(bundle).argv
    assert flag_value(argv, "-c") == "2048" and flag_value(argv, "-np") == "2"


# --- paths -------------------------------------------------------------------------------


def test_core_model_resolution_ignores_the_mmproj(bundle):
    assert bundle.core_model.name == "core-q4_k_m.gguf"
    assert bundle.mmproj.name == "mmproj-q8_0.gguf"


def test_two_candidate_core_ggufs_is_an_error_not_a_coin_flip(bundle):
    """The core filename changes with the D1 bake-off winner; serving last week's quant
    because it sorted first is exactly the kind of silent regression bench week cannot see."""
    (bundle.root / "models" / "core" / "other-q4_k_m.gguf").write_bytes(b"GGUF")
    with pytest.raises(RuntimeError, match="candidate GGUFs"):
        _ = bundle.core_model


def test_missing_bundle_dir_names_itself(tmp_path):
    with pytest.raises(FileNotFoundError, match="not staged"):
        _ = BundlePaths(tmp_path / "nope").core_model


# --- thread table (§6.4) -----------------------------------------------------------------


@pytest.mark.parametrize("cores,threads,batch,vis", [(4, 3, 4, 2), (6, 4, 6, 3), (8, 6, 8, 4)])
def test_thread_table_rows(cores, threads, batch, vis):
    plan = thread_plan(cores)
    assert (plan.core_threads, plan.core_threads_batch, plan.vision_threads) == (threads, batch, vis)
    assert plan.from_table is True


def test_off_table_core_counts_are_flagged_not_silently_adopted():
    """A 12-core dev laptop must never quietly become the number in the report."""
    plan = thread_plan(12)
    assert plan.from_table is False
    assert plan.core_threads == 10 and plan.core_threads_batch == 12


def test_tiny_boxes_do_not_ask_for_more_threads_than_they_have():
    plan = thread_plan(2)
    assert plan.core_threads <= 2 and plan.core_threads_batch <= 2


# --- CLI ---------------------------------------------------------------------------------


def test_cli_print_emits_a_runnable_command(bundle, capsys):
    assert main(["print", "core", "--profile", "solo-demo"]) == 0
    out = capsys.readouterr().out
    assert "--parallel 2" in out and "-c 8192" in out


def test_cli_table_reports_the_box(bundle, capsys):
    assert main(["table"]) == 0
    out = capsys.readouterr().out
    assert "profile" in out and "ctx per slot" in out


def test_cli_reports_a_missing_model_instead_of_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TUTOR_ROOT", str(tmp_path / "empty"))
    assert main(["print", "core"]) == 1
    assert "cannot build core invocation" in capsys.readouterr().err
