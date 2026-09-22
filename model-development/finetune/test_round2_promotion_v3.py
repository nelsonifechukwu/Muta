from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace

import pytest
import round2_promotion_v3 as v3
import test_build_round2_promotions as fixtures
from campaign_io import dataset_fingerprint, inventory_tree, sha256_file

p = fixtures.promotions
launcher = fixtures.launcher


def _write(path, value):
    fixtures._write(path, value)


@pytest.fixture(scope="module")
def current_evidence(tmp_path_factory):
    root = tmp_path_factory.mktemp("promotion-v3-evidence")
    fresh_parent = root / "fresh"
    resumed_parent = root / "resumed"
    fresh_parent.mkdir()
    resumed_parent.mkdir()
    fresh = fixtures._make_promotion_smoke(fresh_parent)
    resumed = fixtures._make_promotion_smoke(resumed_parent)
    # Match the actual wrapper: 1,536 training rows, 256 development rows,
    # private inclusion, and a hash-bound external source snapshot without Git.
    for directory in (fresh, resumed):
        original = p._read_object(directory / "training-manifest.json")
        configuration = p._read_object(directory / "resolved-config.json")
        original["validation_rows"] = 256
        original["tokenization"]["validation"]["rows"] = 256
        original["git"] = {"available": False}
        configuration["validation_rows"] = 256
        configuration["expected_validation_rows"] = 256
        configuration["git"] = {"available": False}
        _write(directory / "resolved-config.json", configuration)
        (directory / "resolved-config.json.sha256").write_text(
            f"{sha256_file(directory / 'resolved-config.json')}  resolved-config.json\n"
        )
        original["resume"]["initial_resolved_config_sha256"] = sha256_file(
            directory / "resolved-config.json"
        )
        fixtures._reseal_smoke_manifest(directory, original)
    manifest = p._read_object(resumed / "training-manifest.json")
    resolved = p._read_object(resumed / "resolved-config.json")
    initial = {"inventory": {"tree_sha256": v3.INITIAL_ADAPTER_SHA256}}
    for data in (manifest, resolved):
        data["initial_adapter_receipt"] = initial
        data["lineage"] = "warm"
        data["learning_rate"] = 5e-6
    resolved["lineage_receipt_sha256"] = p.HARDENED_LINEAGE["warm"]["receipt_sha256"]
    manifest["base_lineage"] = {
        "receipt_sha256": p.HARDENED_LINEAGE["warm"]["receipt_sha256"],
        "observed": {"tree_sha256": p.HARDENED_LINEAGE["warm"]["base_tree_sha256"]},
    }
    _write(resumed / "resolved-config.json", resolved)
    (resumed / "resolved-config.json.sha256").write_text(
        f"{sha256_file(resumed / 'resolved-config.json')}  resolved-config.json\n"
    )
    manifest["resume"].update(
        requested=True,
        checkpoint_step=6,
        initial_resolved_config_sha256=sha256_file(resumed / "resolved-config.json"),
    )
    manifest["schedule"]["session_save_callback_steps"] = [12, 24]
    manifest["initial_adapter_load"] = {
        "operation": "defer_to_own_stage_checkpoint",
        "pilot_weights_loaded": False,
    }
    sessions = resumed / "initialization-sessions"
    sessions.mkdir()
    common = {
        "initial_adapter_receipt": initial,
        "trainer_sha256": sha256_file(fixtures.HERE / "train_lora_round2.py"),
    }
    _write(
        sessions / "initial.json",
        {
            **common,
            "resume_checkpoint_step": None,
            "load": {
                "operation": "copy_exact_adapter_tensors_once_no_merge",
                "exact_source_values_loaded": True,
                "source_tensor_sha256": "b" * 64,
                "loaded_tensor_sha256": "b" * 64,
                "source_tree_sha256_before": v3.INITIAL_ADAPTER_SHA256,
                "source_tree_sha256_after": v3.INITIAL_ADAPTER_SHA256,
            },
        },
    )
    _write(
        sessions / "resume.json",
        {**common, "resume_checkpoint_step": 6, "load": manifest["initial_adapter_load"]},
    )
    fixtures._reseal_smoke_manifest(resumed, manifest)
    (resumed / "running-sessions").mkdir()
    running = resumed / "running-sessions" / "RUNNING.json"
    _write(running, {"pid": 123})
    interruption = root / "interruption.json"
    _write(
        interruption,
        {
            "signal": "SIGTERM",
            "signal_number": 15,
            "pid": 123,
            "returncode": -15,
            "checkpoint_step": 6,
            "completed_marker_before_signal": False,
            "completed_marker_after_signal": False,
            "pre_resume_resolved_config_sha256": sha256_file(resumed / "resolved-config.json"),
            "checkpoint_trainer_state_sha256": sha256_file(
                resumed / "checkpoints/checkpoint-6/trainer_state.json"
            ),
            "running_marker_sha256": sha256_file(running),
        },
    )
    _write(
        root / "COMPLETED.json",
        {
            "status": "complete",
            "interruption_receipt_sha256": sha256_file(interruption),
            "wrapper_sha256": sha256_file(fixtures.HERE / "run_round2_stage_smoke.py"),
        },
    )
    return fresh, resumed, interruption


@pytest.fixture(scope="module")
def current_config(current_evidence):
    paths = fixtures._canonical_paths()
    paths.pop("hardened_resume_verification")
    fresh, resumed, interruption = current_evidence
    return v3.build_config(
        **paths,
        current_smoke_dir=fresh,
        current_resume_dir=resumed,
        interruption_receipt=interruption,
        best_clean_id="clean-r16-lr1e5",
        best_warm_id="warm-r16-lr5e6",
        clean_selection_note="STEM priority, judges regressed",
        warm_selection_note="Written/judges lead, MC regressed",
        batch_size=64,
        gradient_accumulation=1,
    )


def test_v3_exact_three_all_data_treatments(current_config):
    candidates = p.validate_promotion_config(current_config)
    assert [row["planned_rows"] for row in candidates] == [300350] * 3
    assert all(row["private_policy"] == "include" for row in candidates)
    assert [row["initial_adapter_tree_sha256"] for row in candidates] == [
        None,
        None,
        v3.INITIAL_ADAPTER_SHA256,
    ]
    assert candidates[2]["id"] == v3.CONTINUATION_ID


def test_actual_wrapper_arguments_match_current_smoke_receipts(current_evidence, tmp_path):
    wrapper = fixtures._load("run_round2_stage_smoke")
    trainer = fixtures._load("train_lora_round2")
    args = SimpleNamespace(
        python=Path("python"),
        repo=fixtures.REPO,
        campaign_root=tmp_path / "campaign",
        warm_base=tmp_path / "actual-warm-parent",
        output_root=tmp_path / "smoke",
    )
    pilot = p._read_object(fixtures._canonical_paths()["pilot_config_path"])
    for continuation, directory in zip((False, True), current_evidence[:2], strict=True):
        parsed = trainer.parse_args(wrapper.command(args, continuation=continuation)[2:])
        manifest = p._read_object(directory / "training-manifest.json")
        for field in (
            "pilot_rows",
            "validation_rows",
            "max_length",
            "private_policy",
            "rank",
            "lora_alpha",
            "batch_size",
            "eval_batch_size",
            "gradient_accumulation",
            "seed",
            "learning_rate",
            "logging_steps",
            "max_steps",
        ):
            assert getattr(parsed, field) == manifest[field]
        assert parsed.expected_train_rows == 1536
        assert parsed.expected_validation_rows == 256
        assert parsed.milestone_steps == (6, 12, 24)
        gate = v3.verify_gate(directory, pilot, resumed=continuation)
        assert gate["git"] == {"available": False}
        assert gate["completed_step"] == 24
        assert gate["trainer_sha256"] == sha256_file(fixtures.HERE / "train_lora_round2.py")
        if continuation:
            assert parsed.model == args.warm_base
            assert parsed.expected_initial_adapter_tree_sha256 == v3.INITIAL_ADAPTER_SHA256


@pytest.mark.parametrize("mutation", ["rows", "initial", "exclusion", "source", "resume"])
def test_v3_rejects_drift(current_config, mutation):
    config = copy.deepcopy(current_config)
    if mutation == "rows":
        config["candidates"][2]["planned_rows"] = 300000
    elif mutation == "initial":
        config["candidates"][1]["initial_adapter_tree_sha256"] = v3.INITIAL_ADAPTER_SHA256
    elif mutation == "exclusion":
        config["candidates"][2]["private_policy"] = "exclude"
    elif mutation == "source":
        config["source_code"]["trainer_sha256"] = "0" * 64
    else:
        config["training_gates"]["continuation_resumed_24step"]["resume_checkpoint_step"] = None
    with pytest.raises(p.PilotResultError):
        p.validate_promotion_config(config)


def test_v3_config_requires_external_exact_byte_hash(current_config, tmp_path):
    path = tmp_path / "full-v3.json"
    receipt = p.write_frozen_config(path, current_config)
    with pytest.raises(p.PilotResultError, match="externally"):
        launcher.load_frozen_config(path)
    assert launcher.load_frozen_config(path, expected_sha256=receipt["sha256"])[0] == current_config
    path.write_text(path.read_text() + "\n")
    path.with_suffix(".json.sha256").write_text(f"{sha256_file(path)}  {path.name}\n")
    with pytest.raises(p.PilotResultError, match="externally"):
        launcher.load_frozen_config(path, expected_sha256=receipt["sha256"])


def test_portable_series_does_not_require_local_renderer_version(current_evidence):
    fresh, _, _ = current_evidence
    rows = p._read_jsonl(fresh / "metrics.jsonl")
    receipt = v3.verify_portable_loss_series(
        fresh / "loss-curve.png",
        fresh / "loss-curve.svg",
        [row for row in rows if "loss" in row],
        [row for row in rows if "eval_loss" in row],
        "different-OS-version",
    )
    assert receipt["renderer_matplotlib_version"] == "different-OS-version"
    rows[0]["loss"] += 0.125
    with pytest.raises(p.PilotResultError, match="recorded metric"):
        v3.verify_portable_loss_series(
            fresh / "loss-curve.png",
            fresh / "loss-curve.svg",
            [row for row in rows if "loss" in row],
            [row for row in rows if "eval_loss" in row],
            "different-OS-version",
        )


def _runtime(tmp_path):
    args = SimpleNamespace(initial_adapter=None)
    authority = {"lineages": {}, "tokenizer": {"files": {}}}
    for lineage in ("clean", "warm"):
        base = tmp_path / lineage
        base.mkdir()
        (base / "weights").write_bytes(lineage.encode())
        for name in ("tokenizer.json", "tokenizer_config.json"):
            (base / name).write_text("{}")
        tree = inventory_tree(base)
        receipt = tmp_path / f"{lineage}.json"
        _write(receipt, {"lineage": lineage, "training_base": tree})
        setattr(args, f"{lineage}_base", base)
        setattr(args, f"{lineage}_lineage", receipt)
        authority["lineages"][lineage] = {
            "lineage_receipt_sha256": sha256_file(receipt),
            "base_tree_sha256": tree["tree_sha256"],
        }
    authority["tokenizer"].update(authority["lineages"]["clean"])
    authority["tokenizer"]["files"] = {
        name: {"bytes": 2, "sha256": sha256_file(args.clean_base / name)}
        for name in ("tokenizer.json", "tokenizer_config.json")
    }
    for name in ("dataset", "validation"):
        data = tmp_path / f"{name}.jsonl"
        data.write_text('{"id": "example"}\n')
        shards = [
            {
                "path": data.name,
                "bytes": data.stat().st_size,
                "rows": 1,
                "sha256": sha256_file(data),
            }
        ]
        manifest = tmp_path / f"{name}-manifest.json"
        _write(
            manifest,
            {
                "shards": shards,
                "row_count": 1,
                "dataset_fingerprint_sha256": dataset_fingerprint(shards),
            },
        )
        setattr(args, f"{name}_manifest", manifest)
        authority[name] = {
            "manifest_sha256": sha256_file(manifest),
            "fingerprint_sha256": dataset_fingerprint(shards),
            "rows": 1,
        }
    return (
        args,
        {"schema_version": 3, "runtime_input_authority": authority},
        {"lineage": "warm", "initial_adapter_tree_sha256": None},
    )


@pytest.mark.parametrize(
    "mutation", [None, "base", "lineage", "tokenizer", "data", "manifest", "initial"]
)
def test_runtime_binding_before_training(tmp_path, mutation):
    args, config, candidate = _runtime(tmp_path)
    if mutation is None:
        assert launcher.verify_runtime_inputs(args, config, candidate)["dataset"]["row_count"] == 1
        return
    if mutation == "base":
        (args.warm_base / "weights").write_bytes(b"changed")
    elif mutation == "lineage":
        args.warm_lineage.write_text("{}")
    elif mutation == "tokenizer":
        (args.clean_base / "tokenizer.json").write_text("bad")
    elif mutation == "data":
        (tmp_path / "dataset.jsonl").write_text("changed")
    elif mutation == "manifest":
        args.dataset_manifest.write_text("{}")
    else:
        args.initial_adapter = args.warm_base
    with pytest.raises(ValueError):
        launcher.verify_runtime_inputs(args, config, candidate)


def test_continuation_command_passes_exact_initializer(current_config, tmp_path):
    args = SimpleNamespace(
        python=Path("python"),
        config=tmp_path / "full.json",
        clean_base=Path("clean"),
        warm_base=Path("warm"),
        clean_lineage=Path("clean.json"),
        warm_lineage=Path("warm.json"),
        dataset_manifest=Path("data.json"),
        validation_manifest=Path("dev.json"),
        output_root=tmp_path,
        eval_batch_size=None,
        dataloader_workers=8,
        resume_from_checkpoint=None,
        initial_adapter=Path("pilot/adapter"),
    )
    command = launcher.build_command(
        args, current_config, current_config["candidates"][2], config_sha256="a" * 64
    )
    assert command[command.index("--model") + 1] == "warm"
    assert command[command.index("--initial-adapter") + 1] == "pilot/adapter"
    assert (
        command[command.index("--expected-initial-adapter-tree-sha256") + 1]
        == v3.INITIAL_ADAPTER_SHA256
    )
