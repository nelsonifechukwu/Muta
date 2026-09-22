"""Freeze the complete source-heldout science MC pack; never run inference.

The model-facing prompt pack and source-key ledger are separate files.  The
fixed production destination is append-only: an existing path is never reused,
resumed, removed or overwritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "data/muta-science-tutor-20260919/pilot-v1/holdout.jsonl"
SOURCE_SHA256 = "cc3587b3fbe2062c4209d18cd86772ac0d6e4646ebb33745a94243af2e1248fa"
SOURCE_BYTES = 4_550_576
SOURCE_ROWS = 1_591
SOURCE_MANIFEST = "data/muta-science-tutor-20260919/pilot-v1/manifest.json"
SOURCE_MANIFEST_SHA256 = "26fafad101f7cd1aab13ea9ca2cd159be581d4942f5daa50cd57e65db3d5d638"
BUILDER = "model-development/science_tutor/freeze_final_science_holdout.py"
TESTS = "model-development/science_tutor/test_freeze_final_science_holdout.py"
PLAN = "docs/plans/2026-09-19-final-science-holdout-evaluation.md"
OUTPUT = "provenance/science-tutor-20260919/evaluation/final-science-mc-v1"
SOURCE_ORDER = {"scienceqa": 0, "sciq": 1}
EXCLUDED_ID = "mathdial:train:5000012:1:0"
PROMPT_INSTRUCTION = "Reply with exactly one option letter and no other text."


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise ValueError("non-finite JSON number: " + value)


def parse(payload: bytes) -> Any:
    return json.loads(
        payload,
        object_pairs_hook=_unique_object,
        parse_constant=_nonfinite,
    )


def jsonl_rows(payload: bytes) -> list[dict[str, Any]]:
    lines = payload.splitlines()
    require(bool(lines) and all(line.strip() for line in lines), "empty JSONL or blank row")
    values = [parse(line) for line in lines]
    require(all(type(value) is dict for value in values), "JSONL rows must be objects")
    return values


def safe_read(root: Path, relative: str) -> bytes:
    rel = Path(relative)
    require(not rel.is_absolute() and ".." not in rel.parts, "unsafe input path")
    path = root / rel
    for candidate in (path, *path.parents):
        require(not candidate.is_symlink(), "symlinked input path: " + relative)
        if candidate == root:
            break
    require(path.is_file(), "missing/nonregular input: " + relative)
    return path.read_bytes()


def load_inputs(root: Path = ROOT) -> dict[str, bytes]:
    source = safe_read(root, SOURCE)
    source_manifest = safe_read(root, SOURCE_MANIFEST)
    require(
        sha(source) == SOURCE_SHA256
        and len(source) == SOURCE_BYTES
        and len(jsonl_rows(source)) == SOURCE_ROWS,
        "immutable holdout identity mismatch",
    )
    require(
        sha(source_manifest) == SOURCE_MANIFEST_SHA256,
        "immutable source manifest identity mismatch",
    )
    manifest = parse(source_manifest)
    holdout = manifest.get("splits", {}).get("holdout", {})
    require(
        holdout.get("sha256") == SOURCE_SHA256
        and holdout.get("bytes") == SOURCE_BYTES
        and holdout.get("rows") == SOURCE_ROWS
        and holdout.get("sources") == {"mathdial": 1, "scienceqa": 733, "sciq": 857},
        "source manifest holdout binding mismatch",
    )
    return {SOURCE: source, SOURCE_MANIFEST: source_manifest}


def _validate_messages(row: dict[str, Any]) -> None:
    messages = row.get("messages")
    require(type(messages) is list and len(messages) == 2, "MC source must have two messages")
    for message, role in zip(messages, ("user", "assistant")):
        require(
            type(message) is dict
            and set(message) == {"role", "content"}
            and message.get("role") == role
            and type(message.get("content")) is str
            and bool(message["content"].strip()),
            "invalid MC source message schema",
        )


def _validate_mc(row: dict[str, Any]) -> None:
    for field in ("id", "source", "subject", "group_id", "question", "answer"):
        require(type(row.get(field)) is str and bool(row[field].strip()), "invalid MC " + field)
    require(row["source"] in SOURCE_ORDER, "unexpected MC source")
    require(row["question"] == row["question"].strip(), "question has boundary whitespace")
    choices = row.get("choices")
    require(
        type(choices) is list
        and 2 <= len(choices) <= 4
        and all(type(choice) is str and choice and choice == choice.strip() for choice in choices)
        and len(set(choices)) == len(choices),
        "invalid MC choices",
    )
    answer_index = row.get("answer_index")
    require(
        type(answer_index) is int and 0 <= answer_index < len(choices),
        "invalid MC answer index",
    )
    require(row["answer"] == choices[answer_index], "source answer/choice mismatch")
    _validate_messages(row)


def prompt_messages(row: dict[str, Any]) -> list[dict[str, str]]:
    options = "\n".join(
        f"{chr(65 + index)}. {choice}" for index, choice in enumerate(row["choices"])
    )
    content = f"{row['question']}\n\n{options}\n\n{PROMPT_INSTRUCTION}"
    return [{"role": "user", "content": content}]


def assemble(source_payload: bytes) -> tuple[dict[str, bytes], dict[str, Any]]:
    source_rows = jsonl_rows(source_payload)
    require(len(source_rows) == SOURCE_ROWS, "source row count changed")
    ids = [row.get("id") for row in source_rows]
    require(
        all(type(row_id) is str and row_id for row_id in ids) and len(set(ids)) == len(ids),
        "invalid/duplicate source row ID",
    )
    eligible: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for row in source_rows:
        if row.get("source") == "mathdial":
            require(
                row.get("id") == EXCLUDED_ID
                and row.get("choices") is None
                and row.get("answer_index") is None,
                "unexpected non-MC holdout row",
            )
            excluded.append(
                {
                    "id": row["id"],
                    "source": "mathdial",
                    "reason": "non_multiple_choice_multi_turn_dialogue",
                }
            )
            continue
        _validate_mc(row)
        eligible.append(row)
    require(
        len(eligible) == 1_590
        and Counter(row["source"] for row in eligible) == {"scienceqa": 733, "sciq": 857}
        and excluded
        == [
            {
                "id": EXCLUDED_ID,
                "source": "mathdial",
                "reason": "non_multiple_choice_multi_turn_dialogue",
            }
        ],
        "eligible/excluded holdout population changed",
    )
    ordered = sorted(eligible, key=lambda row: (SOURCE_ORDER[row["source"]], row["id"]))
    prompt_rows: list[dict[str, Any]] = []
    key_rows: list[dict[str, Any]] = []
    for row in ordered:
        messages = prompt_messages(row)
        prompt = {
            "id": row["id"],
            "source": row["source"],
            "subject": row["subject"],
            "group_id": row["group_id"],
            "messages": messages,
        }
        key = {
            "id": row["id"],
            "source": row["source"],
            "subject": row["subject"],
            "group_id": row["group_id"],
            "choices": row["choices"],
            "answer_index": row["answer_index"],
            "answer_letter": chr(65 + row["answer_index"]),
            "answer_text": row["answer"],
            "key_status": "source_key_not_independently_verified",
            "source_row_canonical_sha256": sha(canonical(row)),
            "source_assistant_target_sha256": sha(row["messages"][-1]["content"].encode()),
            "model_messages_sha256": sha(canonical(messages)),
        }
        require(
            set(prompt) == {"id", "source", "subject", "group_id", "messages"}
            and [message["role"] for message in prompt["messages"]] == ["user"],
            "model-facing prompt contains a forbidden field or role",
        )
        prompt_rows.append(prompt)
        key_rows.append(key)
    require(
        [row["id"] for row in prompt_rows] == [row["id"] for row in key_rows]
        and len({row["id"] for row in prompt_rows}) == 1_590,
        "prompt/key identity or ordering mismatch",
    )
    artifacts = {
        "prompts.jsonl": b"".join(canonical(row) + b"\n" for row in prompt_rows),
        "keys.jsonl": b"".join(canonical(row) + b"\n" for row in key_rows),
    }
    metadata = {
        "ids": [row["id"] for row in prompt_rows],
        "excluded": excluded,
        "sources": dict(sorted(Counter(row["source"] for row in prompt_rows).items())),
        "subjects": dict(sorted(Counter(row["subject"] for row in prompt_rows).items())),
        "unique_groups": len({row["group_id"] for row in prompt_rows}),
    }
    return artifacts, metadata


def _unchanged(root: Path, loaded: dict[str, bytes]) -> None:
    for relative, payload in loaded.items():
        require(safe_read(root, relative) == payload, "input changed during freeze: " + relative)


def freeze(
    *, reviewed_builder_sha256: str, root: Path = ROOT, destination: Path | None = None
) -> dict[str, Any]:
    """Publish the pack.  ``destination`` exists only for CPU tests."""

    root = root.absolute()
    output = (destination if destination is not None else root / OUTPUT).absolute()
    require(not output.exists(), "output already exists; refuse overwrite/resume")
    for candidate in (output, *output.parents):
        require(not candidate.is_symlink(), "symlinked output path")
    loaded = load_inputs(root)
    for relative in (BUILDER, TESTS, PLAN):
        loaded[relative] = safe_read(root, relative)
    require(
        sha(loaded[BUILDER]) == reviewed_builder_sha256,
        "externally reviewed builder hash mismatch",
    )
    for relative in loaded:
        source_path = (root / relative).absolute()
        require(
            output != source_path and output not in source_path.parents,
            "output contains an input",
        )
    artifacts, metadata = assemble(loaded[SOURCE])
    artifact_receipts = {
        name: {
            "sha256": sha(payload),
            "bytes": len(payload),
            "rows": len(jsonl_rows(payload)),
        }
        for name, payload in sorted(artifacts.items())
    }
    manifest = {
        "schema_version": 1,
        "status": "frozen_final_source_heldout_science_mc",
        "rows": 1_590,
        "source_rows": SOURCE_ROWS,
        "excluded_rows": 1,
        "unique_groups": metadata["unique_groups"],
        "sources": metadata["sources"],
        "subjects": metadata["subjects"],
        "ids": metadata["ids"],
        "ordered_ids_sha256": sha(canonical(metadata["ids"])),
        "ordering": "fixed source order scienceqa,sciq; exact id ascending within source",
        "exclusions": metadata["excluded"],
        "input_bindings": [
            {"path": path, "sha256": sha(payload), "bytes": len(payload)}
            for path, payload in sorted(loaded.items())
        ],
        "reviewed_builder_sha256": reviewed_builder_sha256,
        "artifacts": artifact_receipts,
        "prompt_construction": {
            "inputs": ["question", "ordered choices"],
            "instruction": PROMPT_INSTRUCTION,
            "messages": "one user message; no source assistant turn",
            "generation_contract": "one option letter only",
        },
        "answer_leakage_checks": {
            "prompt_schema_exact": ["group_id", "id", "messages", "source", "subject"],
            "assistant_messages_in_prompts": 0,
            "answer_fields_in_prompts": 0,
            "solutions_or_lectures_in_prompts": 0,
            "correct_option_marker_in_prompts": 0,
            "note": "Every answer text necessarily appears once as an unlabeled member of the choice set; no prompt identifies which choice is correct.",
        },
        "key_policy": "Separate source-key ledger; source keys are not independently certified.",
        "limitations": [
            "Source answer keys are not independently verified for every row.",
            "Lexical overlap screening does not prove semantic or pretraining independence.",
            "Row accuracy counts eight related multi-row groups independently; source and subject breakdowns must remain visible.",
        ],
        "inference_performed": False,
        "inference_input": "prompts.jsonl only; capture code must never open keys.jsonl",
        "mutation_policy": "exclusive new directory/files; no overwrite, resume or source mutation; manifest published last",
        "admission_rule": "manifest and artifact hashes valid, no FAILED.json or manifest.FAILED.json, and independent code/artifact review before inference",
    }
    _unchanged(root, loaded)
    output.mkdir(parents=True, exist_ok=False)
    try:
        for name, payload in artifacts.items():
            with (output / name).open("xb") as handle:
                handle.write(payload)
        _unchanged(root, loaded)
        require(
            all((output / name).read_bytes() == payload for name, payload in artifacts.items()),
            "published artifact changed before sealing",
        )
        with (output / "manifest.json").open("xb") as handle:
            handle.write(json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False).encode())
            handle.write(b"\n")
    except BaseException as exc:
        failure = {
            "status": "failed_before_manifest",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "automatic_retry": False,
            "terminal_manifest_valid": False,
        }
        try:
            if (output / "manifest.json").exists():
                (output / "manifest.json").rename(output / "manifest.FAILED.json")
        except OSError as quarantine_error:
            failure["manifest_quarantine_error"] = str(quarantine_error)
        try:
            with (output / "FAILED.json").open("xb") as handle:
                handle.write(canonical(failure) + b"\n")
        except OSError as marker_error:
            raise RuntimeError(
                f"freeze failed ({type(exc).__name__}: {exc}); failure marker failed: {marker_error}"
            ) from exc
        raise
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewed-builder-sha256", required=True)
    args = parser.parse_args()
    manifest = freeze(reviewed_builder_sha256=args.reviewed_builder_sha256)
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "rows": manifest["rows"],
                "output": str(ROOT / OUTPUT),
                "artifact_sha256": {
                    name: receipt["sha256"] for name, receipt in manifest["artifacts"].items()
                },
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
