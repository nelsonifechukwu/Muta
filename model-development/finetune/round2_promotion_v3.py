"""Current three-treatment promotion: fresh clean, fresh warm, pilot continuation.

Legacy evidence remains in build_round2_promotions. This module adds only the
current-source gates and treatment identities; it never rewrites old evidence.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import build_round2_promotions as p
from campaign_io import sha256_file
from compile_round2_pilots import PilotResultError

SOURCE_FILES = {
    "promotion_builder_sha256": "build_round2_promotions.py",
    "promotion_v3_sha256": "round2_promotion_v3.py",
    "full_launcher_sha256": "launch_round2_full.py",
    "trainer_sha256": "train_lora_round2.py",
    "campaign_io_sha256": "campaign_io.py",
    "train_lora_sha256": "train_lora.py",
    "gate_wrapper_sha256": "run_round2_stage_smoke.py",
}
CONTINUATION_ID = "full-best-warm-pilot-continuation"
INITIAL_ADAPTER_SHA256 = p.CANONICAL_PILOT_AUTHORITY[p.CANONICAL_WARM_SELECTION]["adapter_sha256"]


def source_hashes() -> dict[str, str]:
    return {key: sha256_file(Path(__file__).parent / name) for key, name in SOURCE_FILES.items()}


def verify_portable_loss_series(
    png: Path, svg: Path, train: list[dict], evaluation: list[dict], renderer_version: str
) -> dict[str, str]:
    """Check original SVG coordinates against metrics, not another OS's pixels.

    The frozen trainer uses ordinary Matplotlib linear axes and the default 5% margin.
    We recover its axes rectangle and independently calculate every plotted point.
    PNG structure/CRC is already checked by the shared smoke validator; its original
    bytes are hashed, never regenerated or relabelled as a locally rendered curve.
    """
    root = ET.fromstring(svg.read_bytes())
    series = p._svg_series_paths(svg.read_bytes())
    paths = {
        element.attrib["d"]: element
        for element in root.iter()
        if element.tag.endswith("path") and "clip-path" in element.attrib
    }
    clips = {element.attrib.get("id"): element for element in root.iter()}
    points = {
        "train": [(float(row["step"]), float(row["loss"])) for row in train],
        "validation": [(float(row["step"]), float(row["eval_loss"])) for row in evaluation],
    }
    all_points = points["train"] + points["validation"]
    xmin, xmax = min(x for x, _ in all_points), max(x for x, _ in all_points)
    ymin, ymax = min(y for _, y in all_points), max(y for _, y in all_points)
    if xmax <= xmin or ymax <= ymin:
        raise PilotResultError("loss-curve metric ranges do not permit a numeric series check")
    for name, data in points.items():
        path = paths[series[name]]
        clip_id = re.fullmatch(r"url\(#([^)]*)\)", path.attrib["clip-path"])
        if clip_id is None or clip_id[1] not in clips:
            raise PilotResultError("loss-curve series has no axes rectangle")
        rectangles = [e for e in clips[clip_id[1]] if e.tag.endswith("rect")]
        if len(rectangles) != 1:
            raise PilotResultError("loss-curve clipping rectangle is ambiguous")
        rect = rectangles[0].attrib
        left, top, width, height = (float(rect[k]) for k in ("x", "y", "width", "height"))
        tokens = re.findall(r"[ML]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", series[name])
        if len(tokens) != 3 * len(data) or tokens[0] != "M":
            raise PilotResultError("loss-curve series point count differs from metrics")
        for index, (step, loss) in enumerate(data):
            command, x, y = tokens[3 * index : 3 * index + 3]
            expected_x = left + (step - xmin + 0.05 * (xmax - xmin)) / (1.1 * (xmax - xmin)) * width
            expected_y = top + (ymax - loss + 0.05 * (ymax - ymin)) / (1.1 * (ymax - ymin)) * height
            if command != ("M" if index == 0 else "L") or not (
                math.isclose(float(x), expected_x, abs_tol=0.0001)
                and math.isclose(float(y), expected_y, abs_tol=0.0001)
            ):
                raise PilotResultError("loss-curve SVG does not plot the recorded metric series")
    return {
        "verification": "original_file_hashes_structure_and_numeric_svg_series_v1",
        "renderer_matplotlib_version": renderer_version,
        "png_file_sha256": sha256_file(png),
        "svg_file_sha256": sha256_file(svg),
        "svg_series_sha256": hashlib.sha256(
            json.dumps(series, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def _initial_adapter(manifest: dict[str, Any]) -> str | None:
    receipt = manifest.get("initial_adapter_receipt")
    if receipt is None:
        return None
    if not isinstance(receipt, dict):
        raise PilotResultError("initial-adapter receipt is malformed")
    return receipt.get("inventory", {}).get("tree_sha256")


def verify_gate(root: Path, pilot_config: dict, *, resumed: bool) -> dict:
    result = p.verify_promotion_smoke_run(
        root, pilot_config=pilot_config, current_source=True, resumed_step=6 if resumed else None
    )
    manifest = p._read_object(root / "training-manifest.json")
    resolved = p._read_object(root / "resolved-config.json")
    expected_adapter = INITIAL_ADAPTER_SHA256 if resumed else None
    if (
        result["planned_steps"] != 24
        or result["milestone_steps"] != [6, 12, 24]
        or result["lineage"] != ("warm" if resumed else "clean")
        or manifest.get("private_policy") != "include"
        or _initial_adapter(manifest) != expected_adapter
        or _initial_adapter(resolved) != expected_adapter
    ):
        raise PilotResultError("current gate is not the exact fresh/continuation treatment")
    result["initial_adapter_tree_sha256"] = expected_adapter
    if resumed:
        loads = [p._read_object(path) for path in (root / "initialization-sessions").glob("*.json")]
        if not loads:
            raise PilotResultError("continuation smoke lacks preserved initialization sessions")
        result["initialization_sessions"] = [
            {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}
            for path in sorted((root / "initialization-sessions").glob("*.json"))
        ]
        first_loads = [item for item in loads if item.get("resume_checkpoint_step") is None]
        resumed_loads = [item for item in loads if item.get("resume_checkpoint_step") == 6]
        if len(first_loads) != 1 or len(resumed_loads) != 1 or len(loads) != 2:
            raise PilotResultError(
                "continuation gate requires exactly initial and checkpoint-6 sessions"
            )
        for item in loads:
            if (
                _initial_adapter(item) != expected_adapter
                or item.get("trainer_sha256") != result["trainer_sha256"]
            ):
                raise PilotResultError("initialization session source binding changed")
        first = first_loads[0].get("load", {})
        if (
            first.get("operation") != "copy_exact_adapter_tensors_once_no_merge"
            or first.get("exact_source_values_loaded") is not True
            or not p._is_sha256(first.get("source_tensor_sha256"))
            or first.get("source_tensor_sha256") != first.get("loaded_tensor_sha256")
            or first.get("source_tree_sha256_before") != expected_adapter
            or first.get("source_tree_sha256_after") != expected_adapter
            or resumed_loads[0].get("load") != manifest.get("initial_adapter_load")
            or manifest.get("initial_adapter_load", {}).get("operation")
            != "defer_to_own_stage_checkpoint"
            or manifest.get("initial_adapter_load", {}).get("pilot_weights_loaded") is not False
        ):
            raise PilotResultError(
                "continuation smoke does not prove one initial load and own-stage resume"
            )
    result["git"] = manifest.get("git")
    # Git cleanliness is reported, not fabricated: immutable script hashes are
    # the source authority when running an external snapshot without a .git dir.
    return result


def verify_interruption(path: Path, resume_dir: Path, gate: dict) -> dict:
    receipt = p._read_object(path)
    terminal = p._read_object(path.parent / "COMPLETED.json")
    wrapper_sha = sha256_file(Path(__file__).parent / "run_round2_stage_smoke.py")
    if (
        receipt.get("signal") != "SIGTERM"
        or receipt.get("signal_number") != 15
        or receipt.get("returncode") != -15
        or receipt.get("checkpoint_step") != 6
        or receipt.get("completed_marker_before_signal") is not False
        or receipt.get("completed_marker_after_signal") is not False
        or not isinstance(receipt.get("pid"), int)
        or receipt["pid"] < 1
        or terminal.get("status") != "complete"
        or terminal.get("wrapper_sha256") != wrapper_sha
        or terminal.get("interruption_receipt_sha256") != sha256_file(path)
    ):
        raise PilotResultError("current resume requires a real checkpoint-6 SIGTERM receipt")
    if receipt.get("pre_resume_resolved_config_sha256") != gate["resolved_config_sha256"]:
        raise PilotResultError("interruption resolved config differs from resumed run")
    if (
        receipt.get("checkpoint_trainer_state_sha256")
        != gate["checkpoint_trainer_state_sha256"]["6"]
    ):
        raise PilotResultError("interruption checkpoint differs from resumed run")
    running = list((resume_dir / "running-sessions").glob("*.json"))
    if not any(sha256_file(item) == receipt.get("running_marker_sha256") for item in running):
        raise PilotResultError("interrupted process running marker was not preserved")
    return {
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "wrapper_sha256": wrapper_sha,
        "terminal_sha256": sha256_file(path.parent / "COMPLETED.json"),
        **receipt,
    }


def validate_config(config: dict, *, enforce_authority: bool = True) -> list[dict]:
    expected_data = {
        key: value for key, value in p.CANONICAL_DATA.items() if key != "rights_clean_rows"
    }
    if (
        config.get("schema_version") != 3
        or config.get("frozen_before_full_runs") is not True
        or config.get("shared") != p.CANONICAL_FULL_SHARED
        or config.get("dataset") != expected_data
        or config.get("validation") != p.CANONICAL_VALIDATION
        or config.get("frozen_authority")
        != {"mode": "external_exact_config_sha256_and_source_snapshot"}
    ):
        raise PilotResultError("schema-v3 full-data protocol changed")
    source = config.get("source_pilots", {})
    p._validate_canonical_config_evidence(config, source, current_gates=True)
    if (
        source.get("best_clean_id") != p.CANONICAL_CLEAN_SELECTION
        or source.get("best_warm_id") != p.CANONICAL_WARM_SELECTION
    ):
        raise PilotResultError("schema-v3 selected-pilot provenance changed")
    if config.get("source_code") != source_hashes():
        raise PilotResultError("schema-v3 executable source snapshot changed")
    candidates = config.get("candidates", [])
    expected = {
        "full-best-clean-private-enriched": p.CANONICAL_CLEAN_SELECTION,
        "full-best-warm-private-enriched": p.CANONICAL_WARM_SELECTION,
        CONTINUATION_ID: p.CANONICAL_WARM_SELECTION,
    }
    if len(candidates) != 3 or {c.get("id") for c in candidates} != set(expected):
        raise PilotResultError("schema-v3 requires exactly clean, warm, and pilot continuation")
    for candidate in candidates:
        pilot_id = expected[candidate["id"]]
        authority = p.CANONICAL_PILOT_AUTHORITY[pilot_id]
        steps = math.ceil(expected_data["artifact_rows"] / 64)
        continuation = candidate["id"] == CONTINUATION_ID
        checks = {
            "source_pilot_id": pilot_id,
            "source_pilot_training_manifest_sha256": authority["training_manifest_sha256"],
            "source_pilot_adapter_sha256": authority["adapter_sha256"],
            "source_pilot_best_dev_loss": authority["best_dev_loss"],
            "lineage": authority["lineage"],
            "rank": authority["rank"],
            "learning_rate": authority["learning_rate"],
            "private_policy": "include",
            "planned_rows": expected_data["artifact_rows"],
            "planned_steps": steps,
            "milestone_steps": p.milestone_steps(steps),
            "initial_adapter_tree_sha256": INITIAL_ADAPTER_SHA256 if continuation else None,
            "initialization": "continue_pilot_adapter_reset_optimizer"
            if continuation
            else "fresh_adapter",
        }
        if any(candidate.get(key) != value for key, value in checks.items()):
            raise PilotResultError(f"schema-v3 treatment changed: {candidate['id']}")
        if (
            not isinstance(candidate.get("selection_note"), str)
            or not candidate["selection_note"].strip()
        ):
            raise PilotResultError("schema-v3 selection requires a provenance note")
    gates = config.get("training_gates", {})
    if set(gates) != {"fresh_24step", "continuation_resumed_24step", "interruption"}:
        raise PilotResultError("schema-v3 current-source gates are incomplete")
    expected_scripts = {
        name: config["source_code"][key]
        for key, name in SOURCE_FILES.items()
        if name in {"train_lora_round2.py", "campaign_io.py", "train_lora.py"}
    }
    for name, lineage, initial in (
        ("fresh_24step", "clean", None),
        ("continuation_resumed_24step", "warm", INITIAL_ADAPTER_SHA256),
    ):
        gate = gates[name]
        if (
            gate.get("script_sha256") != expected_scripts
            or gate.get("planned_steps") != 24
            or gate.get("completed_step") != 24
            or gate.get("milestone_steps") != [6, 12, 24]
            or gate.get("lineage") != lineage
            or gate.get("initial_adapter_tree_sha256") != initial
            or gate.get("train_manifest_sha256") != expected_data["manifest_sha256"]
            or gate.get("validation_manifest_sha256") != p.CANONICAL_VALIDATION["manifest_sha256"]
            or gate.get("resume_checkpoint_step") != (6 if initial else None)
            or not p._is_sha256(gate.get("tree_sha256"))
        ):
            raise PilotResultError("schema-v3 training gate binding changed")
    interruption = gates["interruption"]
    if (
        interruption.get("signal") != "SIGTERM"
        or interruption.get("signal_number") != 15
        or interruption.get("returncode") != -15
        or interruption.get("checkpoint_step") != 6
        or interruption.get("completed_marker_before_signal") is not False
        or interruption.get("completed_marker_after_signal") is not False
        or interruption.get("wrapper_sha256") != config["source_code"]["gate_wrapper_sha256"]
        or not p._is_sha256(interruption.get("sha256"))
        or not p._is_sha256(interruption.get("terminal_sha256"))
    ):
        raise PilotResultError("schema-v3 interruption gate changed")
    return candidates


def build_config(
    *, current_smoke_dir: Path, current_resume_dir: Path, interruption_receipt: Path, **kwargs: Any
) -> dict:
    pilot_path, results_path, pilot, results, compiler_path = p._load_verified_pilot_inputs(
        kwargs["pilot_config_path"], kwargs["pilot_results_path"]
    )
    p._verify_canonical_pilot_authority(
        pilot_config_path=pilot_path,
        pilot_results_path=results_path,
        compiler_receipt_path=compiler_path,
        pilot_config=pilot,
        pilot_results=results,
    )
    comparison = p.verify_canonical_gguf_semantic_evidence(
        kwargs["canonical_comparison_dir"], pilot_config=pilot
    )
    exports = p.verify_export_manifests(
        kwargs["export_root"],
        pilot_config=pilot,
        pilot_results=results,
        comparison_receipt=comparison,
    )
    candidates, shared = p._canonical_treatments(
        pilot_config=pilot,
        results=results,
        rights_clean_rows=300000,
        **{
            key: kwargs[key]
            for key in (
                "best_clean_id",
                "best_warm_id",
                "clean_selection_note",
                "warm_selection_note",
                "batch_size",
                "gradient_accumulation",
            )
        },
    )
    candidates[2] = copy.deepcopy(candidates[1])
    candidates[2]["id"] = CONTINUATION_ID
    candidates[2]["selection_note"] = (
        "User-requested continuation of the selected pilot; optimizer and schedule reset; prior 20K exposure retained."
    )
    for candidate in candidates:
        continuation = candidate["id"] == CONTINUATION_ID
        candidate["initial_adapter_tree_sha256"] = INITIAL_ADAPTER_SHA256 if continuation else None
        candidate["initialization"] = (
            "continue_pilot_adapter_reset_optimizer" if continuation else "fresh_adapter"
        )
    fresh = verify_gate(current_smoke_dir, pilot, resumed=False)
    resumed = verify_gate(current_resume_dir, pilot, resumed=True)
    interruption = verify_interruption(interruption_receipt, current_resume_dir, resumed)
    config = {
        "schema_version": 3,
        "campaign_id": f"{pilot['campaign_id']}-full-v3",
        "frozen_before_full_runs": True,
        "selection_protocol": "canonical_matched_gguf_semantic_addendum_v1",
        "frozen_authority": {"mode": "external_exact_config_sha256_and_source_snapshot"},
        "source_pilots": {
            "config_path": str(pilot_path),
            "config_sha256": sha256_file(pilot_path),
            "results_path": str(results_path),
            "results_sha256": sha256_file(results_path),
            "compiler_receipt_path": str(compiler_path),
            "compiler_receipt_sha256": sha256_file(compiler_path),
            "best_clean_id": kwargs["best_clean_id"],
            "best_warm_id": kwargs["best_warm_id"],
            "pilot_result_warnings": results.get("warnings", []),
            "pilot_environment_groups": results.get("environment_groups", {}),
            "canonical_gguf_semantic_evaluation": comparison,
            "export_manifests": exports,
        },
        "source_code": source_hashes(),
        "runtime_input_authority": copy.deepcopy(p.CANONICAL_RUNTIME_INPUT_AUTHORITY),
        "training_gates": {
            "fresh_24step": fresh,
            "continuation_resumed_24step": resumed,
            "interruption": interruption,
        },
        "dataset": {k: v for k, v in p.CANONICAL_DATA.items() if k != "rights_clean_rows"},
        "validation": copy.deepcopy(p.CANONICAL_VALIDATION),
        "shared": shared,
        "candidates": candidates,
    }
    validate_config(config)
    return config
