#!/usr/bin/env python3
"""Freeze explicitly selected round-two pilots into three full-run configs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any

from campaign_io import inventory_tree, sha256_file
from compile_round2_pilots import PilotResultError, validate_pilot_config


def milestone_steps(total_steps: int) -> list[int]:
    """Return exact quarter, half, and final optimizer-step milestones."""
    if total_steps < 1:
        raise PilotResultError("total steps must be positive")
    return sorted({math.ceil(total_steps / 4), math.ceil(total_steps / 2), total_steps})


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PilotResultError(f"cannot read JSON: {path}") from exc
    if not isinstance(value, dict):
        raise PilotResultError(f"JSON root is not an object: {path}")
    return value


def _selected_result(
    results: dict[str, Any], *, candidate_id: str, expected_lineage: str
) -> dict[str, Any]:
    matches = [row for row in results.get("rows", []) if row.get("candidate_id") == candidate_id]
    if len(matches) != 1:
        raise PilotResultError(f"selected pilot is missing or ambiguous: {candidate_id}")
    row = matches[0]
    if row.get("status") != "complete":
        raise PilotResultError(f"selected pilot is not complete: {candidate_id}")
    if row.get("lineage") != expected_lineage:
        raise PilotResultError(
            f"selected {expected_lineage} pilot has {row.get('lineage')!r} lineage"
        )
    for field in ("best_dev_loss", "train_loss", "adapter_sha256"):
        if row.get(field) in (None, ""):
            raise PilotResultError(f"selected pilot lacks {field}: {candidate_id}")
    return row


def _verify_file(path: Path, receipt: dict[str, Any]) -> None:
    if not path.is_file():
        raise PilotResultError(f"evaluation artifact is missing: {path}")
    if path.stat().st_size != receipt.get("bytes") or sha256_file(path) != receipt.get("sha256"):
        raise PilotResultError(f"evaluation artifact receipt mismatch: {path}")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise PilotResultError(
                        f"evaluation response {line_number} is not an object: {path}"
                    )
                rows.append(value)
    except (OSError, json.JSONDecodeError) as exc:
        raise PilotResultError(f"cannot read evaluation responses: {path}") from exc
    return rows


def verify_pilot_evaluation(
    evaluation_dir: Path,
    *,
    pilot_config: dict[str, Any],
    pilot_results: dict[str, Any],
) -> dict[str, Any]:
    """Bind a complete matched-prompt replay to every compiled pilot adapter."""
    root = evaluation_dir.resolve()
    terminal_path = root / "COMPLETED.json"
    if not root.is_dir() or not terminal_path.is_file() or (root / "FAILED.json").exists():
        raise PilotResultError("pilot evaluation is not terminally complete")
    terminal = _read_object(terminal_path)
    if terminal.get("status") != "completed":
        raise PilotResultError("evaluation terminal receipt is not completed")
    inventory_path = root / "artifact-inventory.json"
    if terminal.get("artifact_inventory_sha256") != sha256_file(inventory_path):
        raise PilotResultError("evaluation terminal does not bind its artifact inventory")
    inventory = _read_object(inventory_path)
    if inventory.get("schema_version") != 1:
        raise PilotResultError("evaluation inventory schema is not supported")
    inventory_files = inventory.get("files")
    if not isinstance(inventory_files, list):
        raise PilotResultError("evaluation inventory has no file list")
    listed: set[str] = set()
    listed_bytes = 0
    for receipt in inventory_files:
        if not isinstance(receipt, dict) or not isinstance(receipt.get("path"), str):
            raise PilotResultError("evaluation inventory has an invalid entry")
        relative = Path(receipt["path"])
        unresolved_target = root / relative
        target = unresolved_target.resolve()
        if relative.is_absolute() or root not in target.parents or unresolved_target.is_symlink():
            raise PilotResultError("evaluation inventory path escapes its root")
        _verify_file(target, receipt)
        listed.add(relative.as_posix())
        listed_bytes += target.stat().st_size
    if (
        len(listed) != len(inventory_files)
        or inventory.get("file_count") != len(inventory_files)
        or inventory.get("bytes") != listed_bytes
    ):
        raise PilotResultError("evaluation inventory counts are inconsistent")
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name not in {"artifact-inventory.json", "COMPLETED.json"}
    }
    if listed != actual:
        raise PilotResultError("evaluation inventory does not exactly cover the evidence tree")
    for name, terminal_field in (
        ("summary.csv", "summary_csv_sha256"),
        ("summary.md", "summary_markdown_sha256"),
        ("responses.jsonl", "aggregate_responses_sha256"),
    ):
        if terminal.get(terminal_field) != sha256_file(root / name):
            raise PilotResultError(f"evaluation terminal does not bind {name}")

    run = _read_object(root / "run.json")
    if (
        run.get("schema_version") != 1
        or run.get("prompt_suite") != "judges"
        or run.get("prompt_count", 0) < 2
        or not isinstance(run.get("prompt_set_sha256"), str)
    ):
        raise PilotResultError("evaluation does not contain at least two frozen judges prompts")
    runtime = run.get("runtime")
    runtime_git = runtime.get("git") if isinstance(runtime, dict) else None
    runtime_script = runtime.get("script") if isinstance(runtime, dict) else None
    expected_evaluator_sha = sha256_file(
        Path(__file__).resolve().parents[2] / "bench" / "round2_candidate_eval.py"
    )
    if (
        not isinstance(runtime_git, dict)
        or runtime_git.get("available") is not True
        or runtime_git.get("dirty") is not False
        or not re.fullmatch(r"[0-9a-f]{40,64}", str(runtime_git.get("commit", "")))
        or not isinstance(runtime_script, dict)
        or not re.fullmatch(r"[0-9a-f]{64}", str(runtime_script.get("sha256", "")))
        or runtime_script.get("sha256") != expected_evaluator_sha
    ):
        raise PilotResultError(
            "evaluation runtime is not bound to clean Git and this exact evaluator"
        )
    prompts_path = root / "prompts.json"
    try:
        prompts = json.loads(prompts_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PilotResultError("cannot read evaluation prompts") from exc
    if not isinstance(prompts, list) or len(prompts) != run["prompt_count"]:
        raise PilotResultError("evaluation prompt artifact has the wrong row count")
    prompt_set_sha256 = hashlib.sha256(
        json.dumps(
            prompts,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if prompt_set_sha256 != run["prompt_set_sha256"]:
        raise PilotResultError("evaluation prompt artifact does not match its frozen digest")
    snapshot_path = root / "candidate-manifest.json"
    if run.get("candidate_manifest", {}).get("sha256") != sha256_file(snapshot_path):
        raise PilotResultError("evaluation run does not bind its candidate manifest snapshot")
    snapshot = _read_object(snapshot_path)
    candidates = snapshot.get("candidates")
    if not isinstance(candidates, list):
        raise PilotResultError("evaluation candidate snapshot is invalid")
    evaluated_ids = [row.get("id") for row in candidates if isinstance(row, dict)]
    if (
        len(evaluated_ids) != len(candidates)
        or any(
            not isinstance(identifier, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", identifier)
            for identifier in evaluated_ids
        )
        or len(evaluated_ids) != len(set(evaluated_ids))
    ):
        raise PilotResultError("evaluation candidate IDs are invalid or duplicated")
    pilot_ids = {candidate["id"] for candidate in pilot_config["candidates"]}
    if not pilot_ids.issubset(evaluated_ids):
        raise PilotResultError("evaluation omits a configured fine-tuned pilot")
    snapshot_by_id = {candidate["id"]: candidate for candidate in candidates}
    result_by_id = {row.get("candidate_id"): row for row in pilot_results.get("rows", [])}
    control_ids = set(evaluated_ids) - pilot_ids
    controls_by_backend: dict[str, list[str]] = {}
    for identifier in control_ids:
        controls_by_backend.setdefault(snapshot_by_id[identifier].get("backend"), []).append(
            identifier
        )
    if set(controls_by_backend) != {"hf", "gguf"} or any(
        len(identifiers) != 1 for identifiers in controls_by_backend.values()
    ):
        raise PilotResultError(
            "evaluation must contain exactly one upstream HF and one incumbent GGUF control"
        )
    clean_base_hashes = {
        result_by_id.get(candidate["id"], {}).get("training_base_tree_sha256")
        for candidate in pilot_config["candidates"]
        if candidate["lineage"] == "clean"
    }
    incumbent_gguf_hashes = {
        result_by_id.get(candidate["id"], {}).get("incumbent_gguf_sha256")
        for candidate in pilot_config["candidates"]
        if candidate["lineage"] == "warm"
    }
    if (
        len(clean_base_hashes) != 1
        or not re.fullmatch(r"[0-9a-f]{64}", str(next(iter(clean_base_hashes), "")))
        or len(incumbent_gguf_hashes) != 1
        or not re.fullmatch(r"[0-9a-f]{64}", str(next(iter(incumbent_gguf_hashes), "")))
    ):
        raise PilotResultError("pilot results do not bind unique upstream/incumbent controls")
    expected_upstream_base_sha = next(iter(clean_base_hashes))
    expected_incumbent_gguf_sha = next(iter(incumbent_gguf_hashes))
    prompt_sequence: list[tuple[int, str, str]] | None = None
    detailed_responses: list[dict[str, Any]] = []
    for candidate_id in evaluated_ids:
        candidate_dir = root / "candidates" / candidate_id
        identity = _read_object(candidate_dir / "identity.json")
        result = _read_object(candidate_dir / "result.json")
        snapshot_candidate = snapshot_by_id[candidate_id]
        if (
            identity.get("candidate_id") != candidate_id
            or identity.get("backend") != snapshot_candidate.get("backend")
            or result.get("candidate_id") != candidate_id
            or result.get("backend") != identity.get("backend")
        ):
            raise PilotResultError(f"evaluation identity/result mismatch: {candidate_id}")
        if candidate_id in pilot_ids:
            pilot_result = result_by_id.get(candidate_id, {})
            if identity.get("backend") != "peft":
                raise PilotResultError(f"pilot evaluation backend is not PEFT: {candidate_id}")
            adapter_sha = identity.get("observed", {}).get("adapter", {}).get("tree_sha256")
            if adapter_sha != pilot_result.get("adapter_sha256"):
                raise PilotResultError(f"evaluated adapter does not match pilot: {candidate_id}")
            base_sha = identity.get("observed", {}).get("base_model", {}).get("tree_sha256")
            if base_sha != pilot_result.get("training_base_tree_sha256"):
                raise PilotResultError(
                    f"evaluated adapter uses the wrong training base: {candidate_id}"
                )
        elif identity.get("backend") == "hf":
            control_sha = identity.get("observed", {}).get("model", {}).get("tree_sha256")
            if control_sha != expected_upstream_base_sha:
                raise PilotResultError("HF control is not the pilots' upstream training base")
        elif identity.get("backend") == "gguf":
            control_sha = identity.get("observed", {}).get("model", {}).get("sha256")
            if control_sha != expected_incumbent_gguf_sha:
                raise PilotResultError("GGUF control is not the bound incumbent Muta model")
        if (
            result.get("status") != "complete"
            or result.get("prompts") != run["prompt_count"]
            or result.get("expected_prompts") != run["prompt_count"]
        ):
            raise PilotResultError(f"matched-prompt evaluation is incomplete: {candidate_id}")
        responses_path = candidate_dir / "responses.jsonl"
        if result.get("responses_sha256") != sha256_file(responses_path):
            raise PilotResultError(f"evaluation result does not bind responses: {candidate_id}")
        rows = _read_jsonl(responses_path)
        detailed_responses.extend(rows)
        identity_sha = identity.get("candidate_identity_sha256")
        if not re.fullmatch(r"[0-9a-f]{64}", str(identity_sha or "")):
            raise PilotResultError(f"evaluation has no model identity: {candidate_id}")
        sequence = [
            (int(row.get("ordinal", 0)), str(row.get("id", "")), str(row.get("prompt_sha256", "")))
            for row in rows
        ]
        expected_sequence = [
            (
                ordinal,
                str(prompt.get("id", "")),
                hashlib.sha256(str(prompt.get("text", "")).encode("utf-8")).hexdigest(),
            )
            for ordinal, prompt in enumerate(prompts, 1)
            if isinstance(prompt, dict)
        ]
        if (
            len(rows) != run["prompt_count"]
            or len(expected_sequence) != run["prompt_count"]
            or any(row.get("candidate_id") != candidate_id for row in rows)
            or any(row.get("prompt_set_sha256") != run["prompt_set_sha256"] for row in rows)
            or any(row.get("candidate_backend") != identity.get("backend") for row in rows)
            or any(row.get("model") != candidate_id for row in rows)
            or any(row.get("model_sha256") != identity_sha for row in rows)
            or any(
                row.get("prompt") != prompt or row.get("text") != prompt.get("text")
                for row, prompt in zip(rows, prompts, strict=True)
            )
            or sequence != expected_sequence
        ):
            raise PilotResultError(f"responses violate the frozen prompt set: {candidate_id}")
        if identity.get("backend") == "gguf":
            server_sha = identity.get("observed", {}).get("server", {}).get("sha256")
            if not re.fullmatch(r"[0-9a-f]{64}", str(server_sha or "")) or any(
                row.get("server_sha256") != server_sha for row in rows
            ):
                raise PilotResultError(f"responses do not bind the GGUF server: {candidate_id}")
        raw_paths: set[str] = set()
        for row in rows:
            raw_receipt = row.get("raw_output")
            if not isinstance(raw_receipt, dict) or not isinstance(raw_receipt.get("path"), str):
                raise PilotResultError(f"response has no raw-output receipt: {candidate_id}")
            relative = Path(raw_receipt["path"])
            raw_path = (candidate_dir / relative).resolve()
            if (
                relative.is_absolute()
                or not relative.parts
                or relative.parts[0] != "raw"
                or candidate_dir.resolve() not in raw_path.parents
                or relative.as_posix() in raw_paths
            ):
                raise PilotResultError(f"raw-output path escapes candidate: {candidate_id}")
            raw_paths.add(relative.as_posix())
            _verify_file(raw_path, raw_receipt)
        if prompt_sequence is None:
            prompt_sequence = sequence
        elif sequence != prompt_sequence:
            raise PilotResultError("candidates and controls did not receive identical prompts")

    if _read_jsonl(root / "responses.jsonl") != detailed_responses:
        raise PilotResultError("aggregate responses do not exactly match candidate evidence")

    # Ensure the summary table agrees that each pilot completed; the detailed
    # evidence above remains the source of truth for artifact and prompt identity.
    try:
        with (root / "summary.csv").open(newline="", encoding="utf-8") as handle:
            summary_rows = list(csv.DictReader(handle))
    except (OSError, KeyError) as exc:
        raise PilotResultError("cannot read evaluation summary") from exc
    summary_ids = [row.get("candidate_id") for row in summary_rows]
    if len(summary_ids) != len(set(summary_ids)) or set(summary_ids) != set(evaluated_ids):
        raise PilotResultError("evaluation summary candidate set is not exact")
    summary = {row["candidate_id"]: row for row in summary_rows}
    if any(summary.get(identifier, {}).get("status") != "complete" for identifier in evaluated_ids):
        raise PilotResultError("evaluation summary marks a candidate/control incomplete")
    tree = inventory_tree(root)
    return {
        "path": str(root),
        "tree_sha256": tree["tree_sha256"],
        "bytes": tree["bytes"],
        "file_count": tree["file_count"],
        "terminal_sha256": sha256_file(terminal_path),
        "artifact_inventory_sha256": sha256_file(inventory_path),
        "prompt_suite": run["prompt_suite"],
        "prompt_count": run["prompt_count"],
        "prompt_set_sha256": run["prompt_set_sha256"],
        "evaluated_pilot_ids": sorted(pilot_ids),
        "evaluated_control_ids": sorted(set(evaluated_ids) - pilot_ids),
        "upstream_hf_control_sha256": expected_upstream_base_sha,
        "incumbent_gguf_control_sha256": expected_incumbent_gguf_sha,
    }


def _candidate(
    *,
    identifier: str,
    source: dict[str, Any],
    private_policy: str,
    planned_rows: int,
    global_batch: int,
    selection_note: str,
) -> dict[str, Any]:
    steps = math.ceil(planned_rows / global_batch)
    return {
        "id": identifier,
        "source_pilot_id": source["candidate_id"],
        "source_pilot_training_manifest_sha256": source["training_manifest_sha256"],
        "source_pilot_adapter_sha256": source["adapter_sha256"],
        "source_pilot_best_dev_loss": source["best_dev_loss"],
        "selection_note": selection_note,
        "lineage": source["lineage"],
        "rank": source["rank"],
        "learning_rate": source["learning_rate"],
        "private_policy": private_policy,
        "planned_rows": planned_rows,
        "planned_steps": steps,
        "milestone_steps": milestone_steps(steps),
    }


def validate_promotion_config(config: dict[str, Any]) -> list[dict[str, Any]]:
    if config.get("schema_version") != 1 or config.get("frozen_before_full_runs") is not True:
        raise PilotResultError("full-run config is not a frozen schema-v1 config")
    shared = config.get("shared")
    if not isinstance(shared, dict):
        raise PilotResultError("full-run config has no shared settings")
    try:
        batch_size = shared["batch_size"]
        gradient_accumulation = shared["gradient_accumulation"]
        global_batch = shared["global_batch"]
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1
            for value in (batch_size, gradient_accumulation, global_batch)
        ):
            raise ValueError
        derived_global_batch = batch_size * gradient_accumulation
    except (KeyError, TypeError, ValueError) as exc:
        raise PilotResultError("invalid full-run batch settings") from exc
    if global_batch != 64 or derived_global_batch != 64:
        raise PilotResultError("full-run global batch must equal 64")
    for field in ("max_length", "seed", "logging_steps"):
        if not isinstance(shared.get(field), int) or shared[field] < 1:
            raise PilotResultError(f"invalid full-run shared field: {field}")
    for field in ("epochs", "warmup_ratio", "weight_decay"):
        try:
            value = float(shared[field])
        except (KeyError, TypeError, ValueError) as exc:
            raise PilotResultError(f"invalid full-run shared field: {field}") from exc
        if not math.isfinite(value) or value < 0 or (field != "weight_decay" and value == 0):
            raise PilotResultError(f"invalid full-run shared field: {field}")
    if float(shared["epochs"]) != 1.0:
        raise PilotResultError("full-run protocol requires exactly one epoch")
    if (
        shared.get("training_method") != "BF16 LoRA"
        or shared.get("completion_only_loss") is not True
    ):
        raise PilotResultError("full-run training method must be completion-only BF16 LoRA")
    dataset = config.get("dataset")
    validation = config.get("validation")
    if not isinstance(dataset, dict) or not isinstance(validation, dict):
        raise PilotResultError("full-run config has no dataset/validation binding")
    for label, section, row_field in (
        ("dataset", dataset, "artifact_rows"),
        ("validation", validation, "rows"),
    ):
        if not isinstance(section.get(row_field), int) or section[row_field] < 1:
            raise PilotResultError(f"invalid full-run {label} rows")
        if not re.fullmatch(r"[0-9a-f]{64}", str(section.get("fingerprint_sha256", ""))):
            raise PilotResultError(f"invalid full-run {label} fingerprint")
    if shared.get("checkpoint_schedule") != "quarter_half_end":
        raise PilotResultError("full-run checkpoint schedule is not quarter/half/end")
    source_pilots = config.get("source_pilots")
    evaluation = (
        source_pilots.get("matched_prompt_evaluation") if isinstance(source_pilots, dict) else None
    )
    if (
        not isinstance(evaluation, dict)
        or evaluation.get("prompt_suite") != "judges"
        or not isinstance(evaluation.get("prompt_count"), int)
        or evaluation["prompt_count"] < 2
        or not re.fullmatch(r"[0-9a-f]{64}", str(evaluation.get("prompt_set_sha256", "")))
        or not re.fullmatch(r"[0-9a-f]{64}", str(evaluation.get("tree_sha256", "")))
    ):
        raise PilotResultError("full-run config has no matched-prompt evaluation binding")
    assert isinstance(source_pilots, dict)
    for field in (
        "config_sha256",
        "results_sha256",
        "compiler_receipt_sha256",
    ):
        if not re.fullmatch(r"[0-9a-f]{64}", str(source_pilots.get(field, ""))):
            raise PilotResultError(f"full-run config has invalid source pilot {field}")
    if (
        not isinstance(evaluation.get("evaluated_pilot_ids"), list)
        or not isinstance(evaluation.get("evaluated_control_ids"), list)
        or len(evaluation["evaluated_control_ids"]) != 2
    ):
        raise PilotResultError("matched-prompt evaluation candidate binding is incomplete")
    for field in (
        "terminal_sha256",
        "artifact_inventory_sha256",
        "upstream_hf_control_sha256",
        "incumbent_gguf_control_sha256",
    ):
        if not re.fullmatch(r"[0-9a-f]{64}", str(evaluation.get(field, ""))):
            raise PilotResultError(f"matched-prompt evaluation has invalid {field}")

    candidates = config.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 3:
        raise PilotResultError("full-run config must contain exactly three candidates")
    expected = {
        "full-best-clean-private-enriched": ("clean", "include"),
        "full-best-warm-private-enriched": ("warm", "include"),
        "full-best-warm-rights-clean": ("warm", "exclude"),
    }
    if {candidate.get("id") for candidate in candidates} != set(expected):
        raise PilotResultError("full-run candidate treatment set is not exact")
    by_id = {candidate["id"]: candidate for candidate in candidates}
    for identifier, (lineage, policy) in expected.items():
        candidate = by_id[identifier]
        if candidate.get("lineage") != lineage or candidate.get("private_policy") != policy:
            raise PilotResultError(f"invalid treatment for {identifier}")
        source_id = candidate.get("source_pilot_id")
        if not isinstance(source_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", source_id):
            raise PilotResultError(f"invalid source pilot ID for {identifier}")
        if (
            not isinstance(candidate.get("selection_note"), str)
            or not candidate["selection_note"].strip()
        ):
            raise PilotResultError(f"missing selection note for {identifier}")
        if (
            not isinstance(candidate.get("rank"), int)
            or isinstance(candidate.get("rank"), bool)
            or candidate["rank"] < 1
        ):
            raise PilotResultError(f"invalid rank for {identifier}")
        try:
            learning_rate = float(candidate["learning_rate"])
            best_loss = float(candidate["source_pilot_best_dev_loss"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PilotResultError(f"invalid selected pilot metric for {identifier}") from exc
        if (
            learning_rate <= 0
            or not math.isfinite(learning_rate)
            or best_loss < 0
            or not math.isfinite(best_loss)
        ):
            raise PilotResultError(f"invalid selected pilot metric for {identifier}")
        for field in (
            "source_pilot_training_manifest_sha256",
            "source_pilot_adapter_sha256",
        ):
            if not re.fullmatch(r"[0-9a-f]{64}", str(candidate.get(field, ""))):
                raise PilotResultError(f"invalid {field} for {identifier}")
        rows = candidate.get("planned_rows")
        steps = candidate.get("planned_steps")
        if not isinstance(rows, int) or rows < 1:
            raise PilotResultError(f"invalid planned rows for {identifier}")
        if steps != math.ceil(rows / global_batch):
            raise PilotResultError(f"invalid planned steps for {identifier}")
        if candidate.get("milestone_steps") != milestone_steps(steps):
            raise PilotResultError(f"invalid milestone schedule for {identifier}")
    artifact_rows = dataset["artifact_rows"]
    rights_clean_rows = dataset.get("rights_clean_rows")
    if (
        not isinstance(rights_clean_rows, int)
        or isinstance(rights_clean_rows, bool)
        or not 0 < rights_clean_rows < artifact_rows
    ):
        raise PilotResultError("invalid rights-clean dataset row count")
    if (
        by_id["full-best-clean-private-enriched"]["planned_rows"] != artifact_rows
        or by_id["full-best-warm-private-enriched"]["planned_rows"] != artifact_rows
        or by_id["full-best-warm-rights-clean"]["planned_rows"] != rights_clean_rows
    ):
        raise PilotResultError("candidate row counts do not match their private-data policies")
    clean_source_id = by_id["full-best-clean-private-enriched"]["source_pilot_id"]
    warm_source_id = by_id["full-best-warm-private-enriched"]["source_pilot_id"]
    if clean_source_id == warm_source_id:
        raise PilotResultError("clean and warm promotions cannot share one source pilot")
    selected_pilot_ids = {clean_source_id, warm_source_id}
    if (
        source_pilots.get("best_clean_id") != clean_source_id
        or source_pilots.get("best_warm_id") != warm_source_id
    ):
        raise PilotResultError("selected pilots do not match the source-pilot binding")
    if not selected_pilot_ids.issubset(set(evaluation["evaluated_pilot_ids"])):
        raise PilotResultError("selected pilots are absent from matched-prompt evaluation")
    warm = by_id["full-best-warm-private-enriched"]
    rights_clean = by_id["full-best-warm-rights-clean"]
    for field in (
        "source_pilot_id",
        "source_pilot_training_manifest_sha256",
        "source_pilot_adapter_sha256",
        "source_pilot_best_dev_loss",
        "lineage",
        "rank",
        "learning_rate",
    ):
        if warm.get(field) != rights_clean.get(field):
            raise PilotResultError(f"rights-clean ablation changes warm field: {field}")
    return candidates


def build_promotion_config(
    *,
    pilot_config_path: Path,
    pilot_results_path: Path,
    pilot_evaluation_dir: Path,
    best_clean_id: str,
    best_warm_id: str,
    rights_clean_rows: int,
    clean_selection_note: str,
    warm_selection_note: str,
    batch_size: int = 64,
    gradient_accumulation: int = 1,
) -> dict[str, Any]:
    pilot_config_path = pilot_config_path.resolve()
    pilot_results_path = pilot_results_path.resolve()
    pilot_config = _read_object(pilot_config_path)
    validate_pilot_config(pilot_config)
    results = _read_object(pilot_results_path)
    if results.get("schema_version") != 1:
        raise PilotResultError("pilot result schema_version must be 1")
    if results.get("campaign_id") != pilot_config.get("campaign_id"):
        raise PilotResultError("pilot result campaign does not match pilot config")
    if results.get("source", {}).get("pilot_config_sha256") != sha256_file(pilot_config_path):
        raise PilotResultError("pilot results do not bind the supplied pilot config")
    compiler_receipt_path = pilot_results_path.parent / "compiler-receipt.json"
    compiler_receipt = _read_object(compiler_receipt_path)
    result_receipt = compiler_receipt.get("artifacts", {}).get(pilot_results_path.name, {})
    if result_receipt.get("bytes") != pilot_results_path.stat().st_size or result_receipt.get(
        "sha256"
    ) != sha256_file(pilot_results_path):
        raise PilotResultError("compiler receipt does not bind the supplied pilot results")
    compiler_script = Path(__file__).resolve().parent / "compile_round2_pilots.py"
    compiler_git = compiler_receipt.get("git")
    if (
        compiler_receipt.get("compiler", {}).get("sha256") != sha256_file(compiler_script)
        or not isinstance(compiler_git, dict)
        or compiler_git.get("available") is not True
        or compiler_git.get("dirty") is not False
        or not re.fullmatch(r"[0-9a-f]{40,64}", str(compiler_git.get("commit", "")))
    ):
        raise PilotResultError("pilot results were not produced by this clean exact compiler")
    config_ids = {candidate["id"] for candidate in pilot_config["candidates"]}
    result_ids = [row.get("candidate_id") for row in results.get("rows", [])]
    if len(result_ids) != len(set(result_ids)) or set(result_ids) != config_ids:
        raise PilotResultError("pilot results do not contain the exact configured candidate set")
    if any(row.get("status") != "complete" for row in results["rows"]):
        raise PilotResultError("every configured pilot must complete before promotion")
    evaluation_receipt = verify_pilot_evaluation(
        pilot_evaluation_dir,
        pilot_config=pilot_config,
        pilot_results=results,
    )
    if not clean_selection_note.strip() or not warm_selection_note.strip():
        raise PilotResultError("both selections require a non-empty provenance note")
    if batch_size < 1 or gradient_accumulation < 1:
        raise PilotResultError("batch settings must be positive")
    global_batch = batch_size * gradient_accumulation
    if global_batch != 64:
        raise PilotResultError("full-run global batch must equal 64")

    full_rows = pilot_config["dataset"].get("rows")
    if not isinstance(full_rows, int) or full_rows < 1:
        raise PilotResultError("pilot config has no full dataset row count")
    if not 0 < rights_clean_rows < full_rows:
        raise PilotResultError("rights-clean rows must be positive and below full rows")
    clean = _selected_result(results, candidate_id=best_clean_id, expected_lineage="clean")
    warm = _selected_result(results, candidate_id=best_warm_id, expected_lineage="warm")
    configured = {candidate["id"]: candidate for candidate in pilot_config["candidates"]}
    for selected in (clean, warm):
        treatment = configured[selected["candidate_id"]]
        for field in ("lineage", "rank", "learning_rate"):
            if selected.get(field) != treatment.get(field):
                raise PilotResultError(
                    f"selected pilot result changes frozen treatment field: {field}"
                )

    shared_pilot = pilot_config["shared"]
    candidates = [
        _candidate(
            identifier="full-best-clean-private-enriched",
            source=clean,
            private_policy="include",
            planned_rows=full_rows,
            global_batch=global_batch,
            selection_note=clean_selection_note.strip(),
        ),
        _candidate(
            identifier="full-best-warm-private-enriched",
            source=warm,
            private_policy="include",
            planned_rows=full_rows,
            global_batch=global_batch,
            selection_note=warm_selection_note.strip(),
        ),
        _candidate(
            identifier="full-best-warm-rights-clean",
            source=warm,
            private_policy="exclude",
            planned_rows=rights_clean_rows,
            global_batch=global_batch,
            selection_note=(
                "Rights-clean ablation of selected warm pilot; identical hyperparameters with "
                "private sources excluded."
            ),
        ),
    ]
    promotion = {
        "schema_version": 1,
        "campaign_id": f"{pilot_config['campaign_id']}-full",
        "frozen_before_full_runs": True,
        "source_pilots": {
            "config_path": str(pilot_config_path),
            "config_sha256": sha256_file(pilot_config_path),
            "results_path": str(pilot_results_path),
            "results_sha256": sha256_file(pilot_results_path),
            "compiler_receipt_path": str(compiler_receipt_path.resolve()),
            "compiler_receipt_sha256": sha256_file(compiler_receipt_path),
            "best_clean_id": best_clean_id,
            "best_warm_id": best_warm_id,
            "pilot_result_warnings": results.get("warnings", []),
            "pilot_environment_groups": results.get("environment_groups", {}),
            "matched_prompt_evaluation": evaluation_receipt,
        },
        "dataset": {
            "artifact_rows": full_rows,
            "fingerprint_sha256": pilot_config["dataset"]["fingerprint_sha256"],
            "rights_clean_rows": rights_clean_rows,
        },
        "validation": pilot_config["validation"],
        "shared": {
            "training_method": shared_pilot["training_method"],
            "max_length": shared_pilot["max_length"],
            "epochs": 1.0,
            "batch_size": batch_size,
            "gradient_accumulation": gradient_accumulation,
            "global_batch": global_batch,
            "warmup_ratio": shared_pilot["warmup_ratio"],
            "weight_decay": shared_pilot["weight_decay"],
            "seed": shared_pilot["seed"],
            "logging_steps": max(10, math.ceil(full_rows / global_batch / 100)),
            "checkpoint_schedule": "quarter_half_end",
            "completion_only_loss": True,
        },
        "candidates": candidates,
    }
    validate_promotion_config(promotion)
    return promotion


def write_frozen_config(output: Path, config: dict[str, Any]) -> dict[str, Any]:
    validate_promotion_config(config)
    output = output.resolve()
    receipt_path = output.with_suffix(output.suffix + ".sha256")
    if output.exists() or receipt_path.exists():
        raise FileExistsError(f"promotion config or receipt already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(temporary, output)
    digest = sha256_file(output)
    with receipt_path.open("x", encoding="ascii") as handle:
        handle.write(f"{digest}  {output.name}\n")
    return {"path": str(output), "bytes": output.stat().st_size, "sha256": digest}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot-config", type=Path, required=True)
    parser.add_argument("--pilot-results", type=Path, required=True)
    parser.add_argument("--pilot-evaluation-dir", type=Path, required=True)
    parser.add_argument("--best-clean-id", required=True)
    parser.add_argument("--best-warm-id", required=True)
    parser.add_argument("--rights-clean-rows", type=int, required=True)
    parser.add_argument("--clean-selection-note", required=True)
    parser.add_argument("--warm-selection-note", required=True)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--gradient-accumulation", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    config = build_promotion_config(
        pilot_config_path=args.pilot_config,
        pilot_results_path=args.pilot_results,
        pilot_evaluation_dir=args.pilot_evaluation_dir,
        best_clean_id=args.best_clean_id,
        best_warm_id=args.best_warm_id,
        rights_clean_rows=args.rights_clean_rows,
        clean_selection_note=args.clean_selection_note,
        warm_selection_note=args.warm_selection_note,
        batch_size=args.batch_size,
        gradient_accumulation=args.gradient_accumulation,
    )
    print(json.dumps(write_frozen_config(args.output, config), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
