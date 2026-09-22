"""Offline artifact checks for the three frozen full-stage selected-adapter exports.

Does not load models, invoke subprocesses, contact a host, or authorize runtime
admission. Inputs are read only; the CLI writes one new exclusive JSON receipt.
Own-stage resumes/retries are explicitly unsupported in this first version.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import math
import os
import re
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

CONFIG_SHA = "da828b9146415ca822fecf1961808b914e9666cf7452de34e7704b97f83675da"
HELPER_SHA = "ded88829f91109eb6664d3cf177cde7a8c9665cab731204213ab33047b8fe121"
EXPORTER_SHA = "ed215c907a1013b85c1b619f83dc3a3a3f75b193136bff21709e1c80c883e1be"
REFERENCE_SHA = "67077e17743327aacbade27f4c497b6fd214bcf22aa07c99a45e21b5e34edc69"
LLAMA_COMMIT = "60bccc3763395e01b039aa1ddeacc8cc0ea69f70"
CONVERTER_SHA = "8f1bed9466221e57e434caa7ee720abe1569deb6bc2fe5a65da950ea66c8e737"
QUANTIZER_SHA = "fd6dcbb13f2c69c29b7038436fa514721cacedec6839748f776cb3fde12beca1"
CANDIDATES = {
    "full-best-clean-private-enriched": ("clean", 1e-5),
    "full-best-warm-private-enriched": ("warm", 5e-6),
    "full-best-warm-pilot-continuation": ("warm", 5e-6),
}
MILESTONES = [1174, 2347, 4693]
TARGETS = {"q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"}
SOURCE_FILES = {
    "train_lora_round2.py": "trainer_sha256",
    "train_lora.py": "train_lora_sha256",
    "campaign_io.py": "campaign_io_sha256",
}
SNAPSHOT_FILES = {
    **SOURCE_FILES,
    "launch_round2_full.py": "full_launcher_sha256",
    "build_round2_promotions.py": "promotion_builder_sha256",
    "round2_promotion_v3.py": "promotion_v3_sha256",
    "run_round2_stage_smoke.py": "gate_wrapper_sha256",
}
MAX_JSON = 32 * 1024 * 1024
MAX_LINE = 1024 * 1024
MAX_FILE = 8 * 1024**3


class PreflightError(ValueError):
    """Codes only: avoid echoing private input prose to CLI output."""


def require(condition, code):
    if not condition:
        raise PreflightError(code)


def sha_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def parse_json(raw):
    value = json.loads(
        raw,
        object_pairs_hook=unique_object,
        parse_constant=lambda _: (_ for _ in ()).throw(PreflightError("nonfinite_json")),
    )
    require(isinstance(value, dict), "json_object_required")
    return value


def safe_path(path, *, directory=False):
    path = Path(os.path.abspath(path))
    require(not any(p.is_symlink() for p in (path, *path.parents)), "symlink_input")
    require(path.is_dir() if directory else path.is_file(), "missing_regular_input")
    return path


def finite(value):
    require(
        type(value) in (int, float) and math.isfinite(value) and value >= 0,
        "nonfinite_or_negative_metric",
    )
    return value


def same_typed(value, expected):
    return type(value) is type(expected) and value == expected


def stripped_tree(tree):
    return {key: tree[key] for key in ("bytes", "file_count", "files", "tree_sha256")}


def load_helper():
    """Load only the inspected stdlib-only helper, after checking its bytes."""
    path = safe_path(Path(__file__).with_name("campaign_io.py"))
    with path.open("rb") as handle:
        raw = handle.read(MAX_LINE + 1)
    require(len(raw) < MAX_LINE and sha_bytes(raw) == HELPER_SHA, "helper_source_changed")
    name = "_full_export_campaign_io"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    # Execute the exact pinned bytes, not a second raceable read of the file.
    exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102
    return module, path


class Inputs:
    def __init__(self):
        self.helper, self.helper_path = load_helper()
        self.files, self.trees = {}, {}
        self.file(self.helper_path, expected=HELPER_SHA)
        self.file(Path(__file__))

    def file(self, path, *, expected=None, maximum=MAX_FILE):
        path = safe_path(path)
        size = path.stat().st_size
        require(0 < size <= maximum, "file_size_bound")
        receipt = {"bytes": size, "sha256": self.helper.sha256_file(path)}
        if expected is not None:
            require(
                re.fullmatch(r"[0-9a-f]{64}", str(expected)) is not None
                and receipt["sha256"] == expected,
                "file_hash_mismatch",
            )
        if path in self.files:
            require(self.files[path] == receipt, "input_changed")
        self.files[path] = receipt
        return receipt

    def raw(self, path, maximum=MAX_JSON):
        path = safe_path(path)
        with path.open("rb") as handle:
            raw = handle.read(maximum + 1)
        require(0 < len(raw) <= maximum, "file_size_bound")
        self.file(path, expected=sha_bytes(raw), maximum=maximum)
        return raw

    def json(self, path, *, expected=None, maximum=MAX_JSON):
        raw = self.raw(path, maximum)
        if expected is not None:
            require(sha_bytes(raw) == expected, "file_hash_mismatch")
        return parse_json(raw)

    def tree(self, root, *, maximum=MAX_FILE):
        root = safe_path(root, directory=True)
        count = 0
        for directory, dirs, files in os.walk(root, followlinks=False):
            require(len(Path(directory).relative_to(root).parts) <= 4, "tree_depth_bound")
            for name in dirs + files:
                require(not (Path(directory) / name).is_symlink(), "symlink_input")
            count += len(dirs) + len(files)
            require(count <= 128, "tree_count_bound")
            for name in files:
                self.file(Path(directory) / name, maximum=maximum)
        result = self.helper.inventory_tree(root)
        require(result["file_count"] > 0 and result["bytes"] <= 2 * MAX_FILE, "tree_size_bound")
        identity = stripped_tree(result)
        if root in self.trees:
            require(self.trees[root] == identity, "tree_changed")
        self.trees[root] = identity
        return result

    def finish(self):
        for path, receipt in list(self.files.items()):
            require(self.file(path) == receipt, "input_changed")
        for root, receipt in list(self.trees.items()):
            require(stripped_tree(self.tree(root)) == receipt, "tree_changed")


def expected_shapes():
    shapes = {}
    for layer in range(28):
        for target in sorted(TARGETS):
            component = "self_attn" if target in {"q_proj", "k_proj", "v_proj", "o_proj"} else "mlp"
            prefix = f"base_model.model.model.layers.{layer}.{component}.{target}"
            incoming = 8960 if target == "down_proj" else 1536
            outgoing = (
                256
                if target in {"k_proj", "v_proj"}
                else (8960 if target in {"up_proj", "gate_proj"} else 1536)
            )
            shapes[prefix + ".lora_A.weight"] = [16, incoming]
            shapes[prefix + ".lora_B.weight"] = [outgoing, 16]
    return shapes


QWEN_SHAPES = expected_shapes()


def adapter_weights(inputs, path):
    receipt = inputs.file(path, maximum=128 * 1024 * 1024)
    with path.open("rb") as handle:
        prefix = handle.read(8)
        require(len(prefix) == 8, "safetensors_header")
        length = struct.unpack("<Q", prefix)[0]
        require(2 <= length <= MAX_LINE and length < receipt["bytes"] - 8, "safetensors_header")
        header = parse_json(handle.read(length))
    metadata = header.pop("__metadata__", {})
    require(
        isinstance(metadata, dict)
        and all(isinstance(k, str) and isinstance(v, str) for k, v in metadata.items()),
        "safetensors_metadata",
    )
    require(set(header) == set(QWEN_SHAPES), "safetensors_tensor_set")
    ranges, dtypes = [], set()
    for name, tensor in header.items():
        require(
            isinstance(tensor, dict) and tensor.get("shape") == QWEN_SHAPES[name],
            "safetensors_shape",
        )
        dtype = tensor.get("dtype")
        require(dtype in {"BF16", "F32"}, "safetensors_dtype")
        dtypes.add(dtype)
        offsets = tensor.get("data_offsets")
        require(
            isinstance(offsets, list)
            and len(offsets) == 2
            and all(type(n) is int and n >= 0 for n in offsets),
            "safetensors_offsets",
        )
        require(
            offsets[1] - offsets[0] == math.prod(QWEN_SHAPES[name]) * (2 if dtype == "BF16" else 4),
            "safetensors_offsets",
        )
        ranges.append(offsets)
    cursor = 0
    for start, end in sorted(ranges):
        require(start == cursor, "safetensors_layout")
        cursor = end
    require(len(dtypes) == 1 and cursor == receipt["bytes"] - 8 - length, "safetensors_layout")
    return receipt


def adapter_config(inputs, path):
    config = inputs.json(path, maximum=MAX_LINE)
    require(
        config.get("peft_type") == "LORA"
        and config.get("task_type") == "CAUSAL_LM"
        and type(config.get("r")) is int
        and config["r"] == 16
        and type(config.get("lora_alpha")) is int
        and config["lora_alpha"] == 16
        and config.get("bias") == "none"
        and config.get("lora_dropout") == 0
        and isinstance(config.get("target_modules"), list)
        and len(config["target_modules"]) == 7
        and set(config["target_modules"]) == TARGETS,
        "adapter_config",
    )
    for name in (
        "modules_to_save",
        "rank_pattern",
        "alpha_pattern",
        "use_dora",
        "use_rslora",
        "use_qalora",
        "use_bdlora",
        "lora_bias",
        "fan_in_fan_out",
        "layer_replication",
        "layers_pattern",
        "layers_to_transform",
        "target_parameters",
        "exclude_modules",
        "trainable_token_indices",
        "alora_invocation_tokens",
        "arrow_config",
        "corda_config",
        "eva_config",
        "loftq_config",
        "lora_ga_config",
        "monteclora_config",
        "velora_config",
        "megatron_config",
        "ensure_weight_tying",
    ):
        require(not config.get(name), "unsupported_adapter_feature")
    return {**config, "target_modules": sorted(config["target_modules"])}


def metrics_and_selection(inputs, run, manifest):
    expected_names = {"metrics.jsonl", "metrics.csv", "loss-curve.png", "loss-curve.svg"}
    require(set(manifest["metrics"]) == expected_names, "metrics_inventory")
    for name, expected in manifest["metrics"].items():
        require(
            inputs.file(run / name, expected=expected["sha256"], maximum=MAX_JSON) == expected,
            "metrics_inventory",
        )
    rows = []
    with (run / "metrics.jsonl").open("rb") as handle:
        while line := handle.readline(MAX_LINE + 1):
            require(len(line) <= MAX_LINE and len(rows) < 20000, "metrics_bound")
            require(bool(line.strip()), "blank_metric_row")
            row = parse_json(line)
            require(
                type(row.get("step")) is int and 1 <= row["step"] <= MILESTONES[-1], "metric_step"
            )
            for value in row.values():
                if type(value) in (int, float):
                    finite(value)
            rows.append(row)
    require([r["step"] for r in rows] == sorted(r["step"] for r in rows), "metric_order")
    train = [row for row in rows if "loss" in row]
    require([r["step"] for r in train] == [1, *range(47, 4694, 47)], "training_log_schedule")
    for row in train:
        finite(row["loss"])
    eval_rows = [row for row in rows if "eval_loss" in row]
    require([r["step"] for r in eval_rows] == [*MILESTONES, 4693], "evaluation_multiplicity")
    losses = {row["step"]: finite(row["eval_loss"]) for row in eval_rows[:-1]}
    best_loss = min(losses.values())
    require(
        math.isclose(finite(eval_rows[-1]["eval_loss"]), best_loss, rel_tol=0, abs_tol=1e-12),
        "post_training_loss",
    )
    require(
        math.isclose(
            finite(manifest["validation_metrics"]["eval_loss"]), best_loss, rel_tol=0, abs_tol=1e-12
        ),
        "post_training_loss",
    )
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=sorted({key for row in rows for key in row}))
    writer.writeheader()
    writer.writerows(rows)
    require(inputs.raw(run / "metrics.csv") == buffer.getvalue().encode(), "metrics_csv_projection")
    png = inputs.raw(run / "loss-curve.png")
    require(png.startswith(b"\x89PNG\r\n\x1a\n") and b"IEND" in png[-12:], "plot_structure")
    svg = ET.fromstring(inputs.raw(run / "loss-curve.svg"))
    require(svg.tag.endswith("svg"), "plot_structure")
    state = inputs.json(run / "checkpoints/trainer_state.json")
    require(
        state["global_step"] == 4693
        and state["max_steps"] == 4693
        and type(state.get("epoch")) in (int, float)
        and math.isfinite(state["epoch"])
        and state["epoch"] == 1.0
        and state["log_history"] == rows,
        "root_trainer_state",
    )
    selection = manifest["adapter_selection"]
    best_step = selection.get("best_checkpoint_step")
    require(
        type(best_step) is int
        and best_step in MILESTONES
        and selection.get("policy") == "minimum_eval_loss"
        and selection.get("best_metric_name") == "eval_loss"
        and selection.get("best_metric") == best_loss
        and losses[best_step] == best_loss
        and selection.get("best_checkpoint_relative_path") == f"checkpoints/checkpoint-{best_step}"
        and state.get("best_metric") == best_loss
        and Path(state.get("best_model_checkpoint", "")).name == f"checkpoint-{best_step}",
        "selected_checkpoint",
    )
    # Trainer uses strict improvement: the earliest scheduled occurrence wins a tie.
    require(
        best_step == min(step for step, loss in losses.items() if loss == best_loss),
        "best_checkpoint_tie",
    )
    root_config = adapter_config(inputs, run / "adapter/adapter_config.json")
    adapter_weights(inputs, run / "adapter/adapter_model.safetensors")
    checkpoint_receipts = {}
    actual_steps = sorted(p.name for p in (run / "checkpoints").glob("checkpoint-*"))
    require(actual_steps == sorted(f"checkpoint-{s}" for s in MILESTONES), "checkpoint_set")
    for step in MILESTONES:
        checkpoint = run / "checkpoints" / f"checkpoint-{step}"
        saved = inputs.json(checkpoint / "trainer_state.json")
        scheduled = eval_rows[MILESTONES.index(step)]
        stop = rows.index(scheduled) + 1
        so_far = {s: loss for s, loss in losses.items() if s <= step}
        prior_best = min(so_far, key=lambda s: (so_far[s], s))
        require(
            saved.get("global_step") == step
            and saved.get("max_steps") == 4693
            and type(saved.get("epoch")) in (int, float)
            and math.isfinite(saved["epoch"])
            and 0 < saved["epoch"] <= 1
            and math.isclose(saved["epoch"], step / 4693, rel_tol=0, abs_tol=1e-12)
            and saved.get("log_history") == rows[:stop]
            and saved.get("best_metric") == so_far[prior_best]
            and Path(saved.get("best_model_checkpoint", "")).name == f"checkpoint-{prior_best}",
            "checkpoint_state",
        )
        require(
            adapter_config(inputs, checkpoint / "adapter_config.json") == root_config,
            "checkpoint_adapter_config",
        )
        adapter_weights(inputs, checkpoint / "adapter_model.safetensors")
        for name in ("optimizer.pt", "scheduler.pt", "rng_state.pth", "training_args.bin"):
            inputs.file(checkpoint / name, maximum=2 * 1024**3)
        checkpoint_receipts[str(step)] = stripped_tree(inputs.tree(checkpoint, maximum=2 * 1024**3))
    for name, checkpoint_key, adapter_key in (
        (
            "adapter_model.safetensors",
            "best_checkpoint_adapter_model_sha256",
            "final_adapter_model_sha256",
        ),
        (
            "adapter_config.json",
            "best_checkpoint_adapter_config_sha256",
            "final_adapter_config_sha256",
        ),
    ):
        current = inputs.file(run / "adapter" / name)["sha256"]
        selected = inputs.file(run / "checkpoints" / f"checkpoint-{best_step}" / name)["sha256"]
        require(
            current == selected == selection[checkpoint_key] == selection[adapter_key],
            "selected_adapter_bytes",
        )
    return {
        "selected_step": best_step,
        "selected_example_exposures_in_this_stage": min(best_step * 64, 300350),
        "exposure_basis": "fixed_batch64_accumulation1_world1_single_epoch_not_unique_rows",
        "selected_epoch": inputs.json(
            run / "checkpoints" / f"checkpoint-{best_step}/trainer_state.json"
        ).get("epoch"),
        "best_dev_loss": best_loss,
        "scheduled_dev_losses": losses,
        "checkpoint_inventories": checkpoint_receipts,
        "plot_check": "manifest_hashes_and_basic_structure_only_not_numeric_curve_revalidation",
    }


def verify_initializer(inputs, run, candidate, manifest, resolved, reference):
    receipt, loaded = manifest.get("initial_adapter_receipt"), manifest.get("initial_adapter_load")
    sessions_dir = run / "initialization-sessions"
    sessions = sorted(sessions_dir.glob("*.json")) if sessions_dir.exists() else []
    require(resolved.get("initial_adapter_receipt") == receipt, "initializer_resolved_binding")
    expected = candidate.get("initial_adapter_tree_sha256")
    if expected is None:
        require(
            receipt is None and loaded is None and not sessions and not sessions_dir.exists(),
            "fresh_initializer",
        )
        return None
    require(
        isinstance(receipt, dict) and isinstance(loaded, dict) and len(sessions) == 1,
        "initializer_evidence",
    )
    require(
        receipt.get("kind") == "completed_pilot_adapter_new_stage"
        and receipt.get("source_run_name") == candidate["source_pilot_id"]
        and receipt.get("prior_training_rows") == 20000
        and receipt.get("prior_trainer_global_step") == 313
        and receipt.get("inventory", {}).get("tree_sha256") == expected
        and stripped_tree(receipt["inventory"]) == stripped_tree(reference["inputs"]["adapter"])
        and receipt.get("training_base_tree_sha256")
        == manifest["base_lineage"]["observed"]["tree_sha256"]
        and receipt.get("training_base_tree_sha256") == reference["inputs"]["base"]["tree_sha256"]
        and receipt.get("training_manifest_sha256")
        == candidate["source_pilot_training_manifest_sha256"]
        and receipt.get("training_manifest_sha256")
        == reference["inputs"]["training_manifest"]["sha256"],
        "initializer_lineage",
    )
    require(
        loaded.get("operation") == "copy_exact_adapter_tensors_once_no_merge"
        and loaded.get("exact_source_values_loaded") is True
        and loaded.get("tensor_count") == len(QWEN_SHAPES)
        and loaded.get("trainable_parameters") == sum(math.prod(s) for s in QWEN_SHAPES.values())
        and loaded.get("tensor_keys") == sorted(QWEN_SHAPES)
        and re.fullmatch(r"[0-9a-f]{64}", str(loaded.get("before_tensor_sha256")))
        and re.fullmatch(r"[0-9a-f]{64}", str(loaded.get("source_tensor_sha256")))
        and loaded.get("source_tensor_sha256") == loaded.get("loaded_tensor_sha256")
        and loaded.get("source_tree_sha256_before") == expected
        and loaded.get("source_tree_sha256_after") == expected,
        "initializer_tensor_copy",
    )
    session = inputs.json(sessions[0], maximum=MAX_LINE)
    require(
        inputs.tree(sessions_dir, maximum=MAX_LINE)["file_count"] == 1, "initializer_session_set"
    )
    require(
        session
        == {
            "initial_adapter_receipt": receipt,
            "load": loaded,
            "resume_checkpoint_step": None,
            "trainer_sha256": manifest["scripts"]["train_lora_round2.py"],
        },
        "initializer_session",
    )
    return {
        "pilot_tree_sha256": expected,
        "session": inputs.file(sessions[0]),
        "tensor_copy_sha256": loaded["loaded_tensor_sha256"],
    }


def preflight(args):
    inputs = Inputs()
    require(args.expected_full_config_sha256 == CONFIG_SHA, "unsupported_full_config")
    config = inputs.json(args.full_config, expected=CONFIG_SHA)
    require(
        config.get("schema_version") == 3 and args.candidate_id in CANDIDATES,
        "unsupported_candidate",
    )
    candidates = [c for c in config["candidates"] if c["id"] == args.candidate_id]
    require(len(candidates) == 1, "candidate_identity")
    candidate = candidates[0]
    require(
        (candidate["lineage"], candidate["learning_rate"]) == CANDIDATES[args.candidate_id]
        and candidate["planned_rows"] == 300350
        and candidate["planned_steps"] == 4693
        and candidate["milestone_steps"] == MILESTONES,
        "candidate_treatment",
    )
    run = safe_path(args.run_dir, directory=True)
    for name in ("RUNNING.json", "FAILED.json"):
        require(not (run / name).exists() and not (run / name).is_symlink(), "conflicting_terminal")
    terminal = inputs.json(run / "COMPLETED.json", maximum=MAX_LINE)
    manifest = inputs.json(
        run / "training-manifest.json", expected=terminal["training_manifest_sha256"]
    )
    require(
        terminal.get("run_name") == manifest.get("run_name") == args.candidate_id
        and manifest.get("schema_version") == 2,
        "terminal_identity",
    )
    resume = manifest["resume"]
    require(
        resume.get("requested") is False
        and resume.get("retry_from_scratch") is False
        and resume.get("checkpoint_step") is None
        and not (run / "resume-sessions").exists(),
        "unsupported_resume",
    )
    resolved = inputs.json(
        run / "resolved-config.json", expected=resume["initial_resolved_config_sha256"]
    )
    require(
        resolved.get("resume_from_checkpoint") is None
        and resolved.get("resume_checkpoint_step") is None,
        "unsupported_resume",
    )
    shared = config["shared"]
    expected = {
        key: shared[key]
        for key in (
            "max_length",
            "epochs",
            "seed",
            "warmup_ratio",
            "weight_decay",
            "batch_size",
            "gradient_accumulation",
            "logging_steps",
        )
    }
    expected.update(
        run_name=args.candidate_id,
        lineage=candidate["lineage"],
        rank=16,
        lora_alpha=16,
        learning_rate=candidate["learning_rate"],
        private_policy="include",
        pilot_rows=None,
        validation_rows=None,
        max_steps=-1,
        eval_steps=250,
        save_steps=250,
        eval_batch_size=64,
    )
    for key, value in expected.items():
        require(
            same_typed(manifest.get(key), value) and same_typed(resolved.get(key), value),
            "frozen_treatment",
        )
    require(
        manifest.get("trainer_global_step") == manifest.get("planned_steps") == 4693
        and type(manifest.get("trainer_epoch")) is float
        and manifest.get("trainer_epoch") == 1.0
        and manifest.get("global_batch_per_gpu") == 64
        and manifest.get("training_method") == "lora_bf16"
        and manifest.get("completion_only_loss") is True
        and manifest.get("warmup_steps") == 141
        and len(manifest.get("target_modules", [])) == 7
        and set(manifest.get("target_modules", [])) == TARGETS,
        "full_stage_contract",
    )
    schedule = manifest["schedule"]
    require(
        schedule
        == {
            "kind": "milestones",
            "requested_steps": MILESTONES,
            "observed_eval_steps": MILESTONES,
            "session_save_callback_steps": MILESTONES,
            "surviving_checkpoint_steps": MILESTONES,
            "trainer_interval": 4694,
        },
        "milestone_schedule",
    )
    require(
        manifest["campaign_config"]["sha256"]
        == resolved["campaign_config"]["sha256"]
        == CONFIG_SHA,
        "campaign_binding",
    )
    scripts = {name: config["source_code"][key] for name, key in SOURCE_FILES.items()}
    require(
        manifest["scripts"] == scripts
        and resolved["script_sha256"] == scripts["train_lora_round2.py"]
        and resolved["campaign_io_sha256"] == HELPER_SHA,
        "trainer_source_binding",
    )
    for name, key in SNAPSHOT_FILES.items():
        inputs.file(
            args.training_code / name, expected=config["source_code"][key], maximum=MAX_JSON
        )
    authority = config["runtime_input_authority"]
    for role, path in (
        ("dataset", args.dataset_manifest),
        ("validation", args.validation_manifest),
    ):
        bound = authority[role]
        original = inputs.json(path, expected=bound["manifest_sha256"])
        receipt = manifest[role]
        require(
            receipt == resolved[role]
            and receipt["manifest_sha256"] == bound["manifest_sha256"]
            and receipt["dataset_fingerprint_sha256"] == bound["fingerprint_sha256"]
            and receipt["row_count"] == original["row_count"] == bound["rows"]
            and receipt["shards"] == original["shards"]
            and original["dataset_fingerprint_sha256"] == bound["fingerprint_sha256"],
            "data_authority",
        )
    for split, count in (("train", 300350), ("validation", 5000)):
        tokenized = manifest["tokenization"][split]
        require(
            type(tokenized["rows"]) is int
            and tokenized["rows"] == count
            and type(tokenized["max_sequence_tokens"]) is int
            and 1 <= tokenized["max_sequence_tokens"] <= 512
            and type(tokenized["assistant_tokens"]) is int
            and count
            <= tokenized["assistant_tokens"]
            <= tokenized["sequence_tokens"]
            <= 512 * count,
            "tokenization_contract",
        )
    bound = authority["lineages"][candidate["lineage"]]
    lineage = inputs.json(args.base_lineage, expected=bound["lineage_receipt_sha256"])
    base = inputs.tree(args.base)
    require(
        not (args.base / "adapter_config.json").exists()
        and lineage["lineage"] == candidate["lineage"]
        and base["tree_sha256"] == bound["base_tree_sha256"]
        and stripped_tree(base) == stripped_tree(lineage["training_base"])
        and stripped_tree(base) == stripped_tree(manifest["base_lineage"]["observed"])
        and manifest["base_lineage"]["receipt"] == lineage
        and manifest["base_lineage"]["receipt_sha256"] == bound["lineage_receipt_sha256"]
        and resolved["lineage_receipt_sha256"] == bound["lineage_receipt_sha256"],
        "merge_parent_binding",
    )
    tokenizer = manifest["tokenizer"]
    require(
        tokenizer == resolved["tokenizer"]
        and tokenizer["lineage_receipt_sha256"] == authority["tokenizer"]["lineage_receipt_sha256"]
        and set(tokenizer["files"]) == set(authority["tokenizer"]["files"]),
        "tokenizer_lineage",
    )
    for name, receipt in tokenizer["files"].items():
        require(
            {k: receipt[k] for k in ("bytes", "sha256")} == authority["tokenizer"]["files"][name],
            "tokenizer_input_receipt",
        )
    signature = resolved["resume_signature"]
    require(
        sha_bytes(canonical(signature["treatment"]))
        == signature["sha256"]
        == resume["treatment_signature_sha256"],
        "treatment_signature",
    )
    treatment = signature["treatment"]
    require(
        type(resolved["dataloader_workers"]) is int and resolved["dataloader_workers"] >= 0,
        "treatment_signature",
    )
    for key, value in expected.items():
        require(same_typed(treatment.get(key), value), "treatment_signature")
    for key, value in {
        "expected_train_rows": 300350,
        "expected_validation_rows": 5000,
        "expected_planned_steps": 4693,
        "dataloader_workers": resolved["dataloader_workers"],
    }.items():
        require(
            same_typed(resolved.get(key), value) and same_typed(treatment.get(key), value),
            "treatment_signature",
        )
    for role in ("dataset", "validation"):
        for suffix in ("manifest_sha256", "fingerprint_sha256"):
            require(
                treatment.get(f"{role}_{suffix}") == authority[role][suffix], "treatment_signature"
            )
    require(
        treatment.get("packages") == resolved.get("packages") == manifest["environment"]["packages"]
        and isinstance(treatment["packages"], dict)
        and bool(treatment["packages"]),
        "environment_receipt_binding",
    )
    require(
        treatment["training_base_tree_sha256"] == base["tree_sha256"]
        and treatment["base_lineage_receipt_sha256"] == bound["lineage_receipt_sha256"]
        and treatment["campaign_config_sha256"] == CONFIG_SHA
        and treatment["scripts"] == scripts
        and same_typed(treatment["world_size"], 1)
        and treatment["tokenizer"] == tokenizer
        and treatment["initial_adapter"] == manifest.get("initial_adapter_receipt")
        and treatment["milestone_steps"] == MILESTONES,
        "treatment_signature",
    )
    adapter = inputs.tree(run / "adapter", maximum=128 * 1024 * 1024)
    require(stripped_tree(adapter) == stripped_tree(manifest["adapter"]), "adapter_inventory")
    require(
        {row["path"] for row in adapter["files"]}
        == {
            "README.md",
            "adapter_config.json",
            "adapter_model.safetensors",
            "tokenizer.json",
            "tokenizer_config.json",
            "chat_template.jinja",
        },
        "saved_tokenizer_inventory",
    )
    inputs.json(run / "adapter/tokenizer.json")
    saved_tokenizer = inputs.json(run / "adapter/tokenizer_config.json", maximum=MAX_LINE)
    require(
        isinstance(saved_tokenizer.get("tokenizer_class"), str)
        and bool(saved_tokenizer["tokenizer_class"])
        and bool(inputs.raw(run / "adapter/chat_template.jinja", MAX_LINE).strip()),
        "saved_tokenizer_structure",
    )
    selection = metrics_and_selection(inputs, run, manifest)
    require(
        args.expected_exporter_sha256 == EXPORTER_SHA
        and args.expected_reference_export_manifest_sha256 == REFERENCE_SHA,
        "unsupported_export_authority",
    )
    inputs.file(args.exporter, expected=EXPORTER_SHA, maximum=MAX_LINE)
    inputs.file(args.exporter.with_name("campaign_io.py"), expected=HELPER_SHA, maximum=MAX_LINE)
    reference = inputs.json(args.reference_export_manifest, expected=REFERENCE_SHA)
    require(
        reference["script"]["sha256"] == EXPORTER_SHA
        and reference["llama_cpp"]["git_commit"] == LLAMA_COMMIT
        and reference["llama_cpp"]["converter"]["sha256"] == CONVERTER_SHA
        and reference["llama_cpp"]["quantizer"]["sha256"] == QUANTIZER_SHA,
        "conversion_reference",
    )
    inputs.file(args.llama_cpp / "convert_hf_to_gguf.py", expected=CONVERTER_SHA, maximum=MAX_JSON)
    inputs.file(
        args.llama_cpp / "build/bin/llama-quantize",
        expected=QUANTIZER_SHA,
        maximum=128 * 1024 * 1024,
    )
    initializer = verify_initializer(inputs, run, candidate, manifest, resolved, reference)
    inputs.finish()
    for name in ("RUNNING.json", "FAILED.json"):
        require(not (run / name).exists() and not (run / name).is_symlink(), "conflicting_terminal")
    return {
        "schema_version": 1,
        "status": "artifact_preflight_passed",
        "candidate_id": args.candidate_id,
        "runtime_admission": "not_assessed",
        "model_loaded": False,
        "export_performed": False,
        "scope": "frozen_v3_fresh_stage_selected_adapter_only",
        "run_directory": str(run),
        "full_config_sha256": CONFIG_SHA,
        "selection": selection,
        "initializer": initializer,
        "run_rows": 300350,
        "run_steps": 4693,
        "adapter": stripped_tree(adapter),
        "base": stripped_tree(base),
        "tokenizer_directory": str(run / "adapter"),
        "exporter_arguments": [
            str(args.exporter),
            "--base",
            str(args.base),
            "--base-lineage",
            str(args.base_lineage),
            "--tokenizer",
            str(run / "adapter"),
            "--adapter",
            str(run / "adapter"),
            "--training-manifest",
            str(run / "training-manifest.json"),
            "--llama-cpp",
            str(args.llama_cpp),
        ],
        "inputs": [
            {"path": str(path), **receipt} for path, receipt in sorted(inputs.files.items())
        ],
        "pending": [
            "live_process_and_resource_admission",
            "exclusive_output_claim_and_full_merge_argv",
            "actual_llama_git_dirty_import_dependency_and_package_state",
            "loaded_tokenizer_and_template_semantics",
            "GGUF_export_integrity_and_load_stop_smoke",
            "input_revalidation_at_launch",
        ],
        "limitations": [
            "No private shard text is read; dataset manifest authority only.",
            "No optimizer pickle/model tensors are deserialized; checkpoint files are hashed.",
            "No payload numerical-finiteness or full tokenizer semantic check is performed.",
            "No numeric loss-curve reconstruction; original plot hashes/basic structure only.",
            "Resumes and retries are unsupported, not silently treated as fresh stages.",
        ],
    }


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    for name in (
        "full-config",
        "run-dir",
        "training-code",
        "base",
        "base-lineage",
        "dataset-manifest",
        "validation-manifest",
        "exporter",
        "llama-cpp",
        "reference-export-manifest",
        "output",
    ):
        result.add_argument("--" + name, required=True, type=Path)
    for name in (
        "expected-full-config-sha256",
        "candidate-id",
        "expected-exporter-sha256",
        "expected-reference-export-manifest-sha256",
    ):
        result.add_argument("--" + name, required=True)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        require(not args.output.exists() and not args.output.is_symlink(), "output_exists")
        destination = Path(os.path.abspath(args.output))
        for root in (
            args.run_dir,
            args.base,
            args.training_code,
            args.llama_cpp,
            args.exporter.parent,
        ):
            require(
                Path(os.path.abspath(root)) not in destination.parents, "output_inside_input_tree"
            )
        safe_path(destination.parent, directory=True)
        report = preflight(args)
        with destination.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, sort_keys=True, indent=2)
            handle.write("\n")
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "runtime_admission": "not_assessed",
                    "candidate_id": args.candidate_id,
                }
            )
        )
        return 0
    except PreflightError as error:
        print(f"Preflight failed: {error}", file=sys.stderr)
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        OverflowError,
        RecursionError,
        ET.ParseError,
    ):
        print("Preflight failed: invalid_or_changed_input", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
