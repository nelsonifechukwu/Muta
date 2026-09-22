"""Freeze an exact science-pilot checkpoint as a GGUF export authority.

This module never loads a model, touches a GPU, merges weights, or launches an
export.  It joins the selected development result to the original training run,
checkpoint seal, parent lineage, and tokenizer before the already-reviewed
round-two exporter is invoked separately.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path


class ExportAdmissionError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            value.update(block)
    return value.hexdigest()


def file_receipt(path: Path) -> dict:
    path = path.resolve()
    if path.is_symlink() or not path.is_file():
        raise ExportAdmissionError(f"not a regular file: {path}")
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def tree_receipt(path: Path) -> dict:
    path = path.resolve()
    if path.is_symlink() or not path.is_dir():
        raise ExportAdmissionError(f"not a directory: {path}")
    files = []
    for child in sorted(path.rglob("*")):
        if child.is_symlink():
            raise ExportAdmissionError(f"symlink in tree: {child}")
        if child.is_file():
            files.append(
                {
                    "path": child.relative_to(path).as_posix(),
                    "bytes": child.stat().st_size,
                    "sha256": sha256_file(child),
                }
            )
        elif not child.is_dir():
            raise ExportAdmissionError(f"special file in tree: {child}")
    if not files:
        raise ExportAdmissionError(f"empty tree: {path}")
    tree_sha = hashlib.sha256(
        "\n".join(f"{row['sha256']}  {row['path']}" for row in files).encode()
    ).hexdigest()
    return {
        "root": str(path),
        "tree_sha256": tree_sha,
        "file_count": len(files),
        "bytes": sum(row["bytes"] for row in files),
        "files": files,
    }


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExportAdmissionError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ExportAdmissionError(f"JSON root must be an object: {path}")
    return value


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ExportAdmissionError(f"invalid {label}")
    return value


def verify_file_ref(ref: dict, label: str) -> dict:
    if not isinstance(ref, dict) or set(ref) != {"path", "sha256"}:
        raise ExportAdmissionError(f"invalid {label} reference")
    observed = file_receipt(Path(ref["path"]))
    if observed["sha256"] != _sha(ref["sha256"], f"{label} sha256"):
        raise ExportAdmissionError(f"{label} hash mismatch")
    return observed


def verify_tree_ref(ref: dict, label: str) -> dict:
    if not isinstance(ref, dict) or set(ref) != {"path", "tree_sha256"}:
        raise ExportAdmissionError(f"invalid {label} reference")
    observed = tree_receipt(Path(ref["path"]))
    if observed["tree_sha256"] != _sha(ref["tree_sha256"], f"{label} tree sha256"):
        raise ExportAdmissionError(f"{label} tree mismatch")
    return observed


def validate_config(config: dict) -> None:
    required = {
        "schema_version",
        "selection_id",
        "checkpoint_step",
        "checkpoint",
        "checkpoint_seal",
        "run_complete",
        "resolved_config",
        "base",
        "base_lineage",
        "tokenizer",
        "selection_declaration",
        "selection_scores",
        "r1_expansion_review",
        "r1_admission_decision",
        "expected_training",
    }
    if set(config) != required or config.get("schema_version") != 1:
        raise ExportAdmissionError("unexpected selected-export config")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]+", str(config["selection_id"])):
        raise ExportAdmissionError("invalid selection ID")
    if type(config["checkpoint_step"]) is not int or config["checkpoint_step"] < 1:
        raise ExportAdmissionError("invalid checkpoint step")
    expected = config["expected_training"]
    expected_fields = {
        "config_sha256",
        "train_sha256",
        "dev_sha256",
        "admission_sha256",
        "source_sha256",
        "adapter_model_sha256",
        "adapter_tensor_sha256",
    }
    if not isinstance(expected, dict) or set(expected) != expected_fields:
        raise ExportAdmissionError("unexpected expected_training fields")
    for key in expected_fields - {"source_sha256"}:
        _sha(expected[key], key)
    if not isinstance(expected["source_sha256"], dict) or not expected["source_sha256"]:
        raise ExportAdmissionError("source hashes are required")
    for name, value in expected["source_sha256"].items():
        if not isinstance(name, str) or not name:
            raise ExportAdmissionError("invalid source name")
        _sha(value, f"source {name}")


def prepare(config: dict) -> dict:
    validate_config(config)
    checkpoint = verify_tree_ref(config["checkpoint"], "checkpoint")
    seal_ref = verify_file_ref(config["checkpoint_seal"], "checkpoint seal")
    run_ref = verify_file_ref(config["run_complete"], "run completion")
    resolved_ref = verify_file_ref(config["resolved_config"], "resolved config")
    base = verify_tree_ref(config["base"], "base")
    tokenizer = verify_tree_ref(config["tokenizer"], "tokenizer")
    lineage_ref = verify_file_ref(config["base_lineage"], "base lineage")
    declaration = verify_file_ref(config["selection_declaration"], "selection declaration")
    scores = verify_file_ref(config["selection_scores"], "selection scores")
    r1_review = verify_file_ref(config["r1_expansion_review"], "R1 expansion review")
    r1_decision_ref = verify_file_ref(config["r1_admission_decision"], "R1 admission decision")
    r1_decision = load_json(Path(r1_decision_ref["path"]))
    if (
        r1_decision.get("decision") != "SKIP_R1_NO_MEANINGFUL_EXPANSION"
        or r1_decision.get("training_action", {}).get("launch_r1") is not False
    ):
        raise ExportAdmissionError("R1 fallback decision is not terminal")

    checkpoint_root = Path(checkpoint["root"])
    if Path(seal_ref["path"]) != checkpoint_root / "COMPLETE.json":
        raise ExportAdmissionError("checkpoint seal is not inside selected checkpoint")
    seal = load_json(Path(seal_ref["path"]))
    step = config["checkpoint_step"]
    if checkpoint_root.name != f"checkpoint-{step}" or seal.get("step") != step:
        raise ExportAdmissionError("checkpoint path/seal step mismatch")
    sealed_files = seal.get("files")
    observed_without_seal = [row for row in checkpoint["files"] if row["path"] != "COMPLETE.json"]
    if sealed_files != observed_without_seal:
        raise ExportAdmissionError("checkpoint contents differ from its seal")
    names = {row["path"] for row in checkpoint["files"]}
    required_names = {
        "COMPLETE.json",
        "adapter_config.json",
        "adapter_model.safetensors",
        "state.json",
        "training-state.pt",
    }
    if not required_names <= names:
        raise ExportAdmissionError("checkpoint is missing required evidence")

    expected = config["expected_training"]
    if seal.get("config_sha256") != expected["config_sha256"]:
        raise ExportAdmissionError("checkpoint training config mismatch")
    if seal.get("source_sha256") != expected["source_sha256"]:
        raise ExportAdmissionError("checkpoint trainer source mismatch")
    by_name = {row["path"]: row for row in checkpoint["files"]}
    if by_name["adapter_model.safetensors"]["sha256"] != expected["adapter_model_sha256"]:
        raise ExportAdmissionError("adapter weights mismatch")
    state = load_json(checkpoint_root / "state.json")
    if state.get("step") != step or state.get("adapter", {}).get("tensor_sha256") != expected[
        "adapter_tensor_sha256"
    ]:
        raise ExportAdmissionError("adapter tensor identity mismatch")

    selected = r1_decision.get("selected_export_candidate", {})
    selected_checkpoint = selected.get("checkpoint", {})
    if (
        selected.get("candidate_id") != "P2-half"
        or selected.get("parent", {}).get("tree_sha256") != base["tree_sha256"]
        or selected_checkpoint.get("step") != step
        or selected_checkpoint.get("tree_sha256") != checkpoint["tree_sha256"]
        or selected_checkpoint.get("checkpoint_seal_sha256") != seal_ref["sha256"]
    ):
        raise ExportAdmissionError("R1 decision selected a different export candidate")
    r1_evidence = r1_decision.get("evidence", {})
    if (
        r1_evidence.get("independent_review", {}).get("sha256") != r1_review["sha256"]
        or r1_evidence.get("development_winner_declaration", {}).get("sha256")
        != declaration["sha256"]
    ):
        raise ExportAdmissionError("R1 decision evidence binding mismatch")

    resolved = load_json(Path(resolved_ref["path"]))
    training_config = resolved.get("config", {})
    if resolved.get("config_file", {}).get("sha256") != expected["config_sha256"]:
        raise ExportAdmissionError("resolved config-file identity mismatch")
    data = training_config.get("data", {})
    for key, expected_key in (
        ("train", "train_sha256"),
        ("dev", "dev_sha256"),
        ("admission", "admission_sha256"),
    ):
        if data.get(key, {}).get("sha256") != expected[expected_key]:
            raise ExportAdmissionError(f"resolved {key} identity mismatch")
    initialization = training_config.get("initialization", {})
    if initialization.get("kind") != "muta_fresh":
        raise ExportAdmissionError("selected pilot did not start fresh on original Muta")
    if initialization.get("base", {}).get("tree_sha256") != base["tree_sha256"]:
        raise ExportAdmissionError("resolved parent base mismatch")
    if initialization.get("tokenizer", {}).get("tree_sha256") != tokenizer["tree_sha256"]:
        raise ExportAdmissionError("resolved tokenizer mismatch")

    run_complete = load_json(Path(run_ref["path"]))
    checkpoint_rows = run_complete.get("all_checkpoints", [])
    if not any(
        row.get("tree_sha256") == checkpoint["tree_sha256"]
        and Path(row.get("root", "")).resolve() == checkpoint_root
        for row in checkpoint_rows
    ):
        raise ExportAdmissionError("training completion does not retain selected checkpoint")
    if run_complete.get("config_sha256") != expected["config_sha256"]:
        raise ExportAdmissionError("training completion config mismatch")

    lineage = load_json(Path(lineage_ref["path"]))
    if lineage.get("training_base", {}).get("tree_sha256") != base["tree_sha256"]:
        raise ExportAdmissionError("base lineage mismatch")

    # Keep the `adapter` key compatible with the already-reviewed generic exporter.
    return {
        "schema_version": 1,
        "kind": "science_tutor_selected_checkpoint_export_authority",
        "status": "admitted_for_merge_and_q4_k_m_export",
        "selection_id": config["selection_id"],
        "checkpoint_step": step,
        "adapter": checkpoint,
        "checkpoint_seal": seal_ref,
        "adapter_state": file_receipt(checkpoint_root / "state.json"),
        "run_complete": run_ref,
        "resolved_config": resolved_ref,
        "base": base,
        "base_lineage": lineage_ref,
        "tokenizer": tokenizer,
        "selection_declaration": declaration,
        "selection_scores": scores,
        "r1_expansion_review": r1_review,
        "r1_admission_decision": r1_decision_ref,
        "expected_training": expected,
        "limitations": [
            "Development selection is not final deployment qualification.",
            "The checkpoint directory includes optimizer state, but the exporter loads only PEFT adapter files.",
        ],
    }


def write_exclusive(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config_ref = file_receipt(args.config)
    if config_ref["sha256"] != _sha(args.config_sha256, "config sha256"):
        raise ExportAdmissionError("selected-export config hash mismatch")
    authority = prepare(load_json(args.config))
    authority["config"] = config_ref
    authority["script"] = file_receipt(Path(__file__))
    write_exclusive(args.output, authority)
    print(json.dumps(file_receipt(args.output), sort_keys=True))


if __name__ == "__main__":
    main()
