"""Freeze the corrected final science MC pack; never run inference.

Version 1 remains immutable rejected evidence.  This append-only version removes
only the eight independently reviewed ScienceQA thermometer rows whose required
visual measurement is absent from the model-facing text.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

SPEC = importlib.util.spec_from_file_location(
    "freeze_final_science_holdout_v1",
    Path(__file__).with_name("freeze_final_science_holdout.py"),
)
assert SPEC and SPEC.loader
base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)

ROOT = Path(__file__).resolve().parents[2]
BUILDER = "model-development/science_tutor/freeze_final_science_holdout_v2.py"
BASE_BUILDER = "model-development/science_tutor/freeze_final_science_holdout.py"
TESTS = "model-development/science_tutor/test_freeze_final_science_holdout_v2.py"
PLAN = "docs/plans/2026-09-19-final-science-holdout-context-correction.md"
RAW_SCIENCEQA = "data/muta-science-tutor-20260919/sources/scienceqa/problems.json"
RAW_SCIENCEQA_SHA256 = "4d9b598da966d9736dd79e430a97da861a2216aeb7483a5092350e823ab20ce7"
RAW_SCIENCEQA_BYTES = 31_529_211
OUTPUT = "provenance/science-tutor-20260919/evaluation/final-science-mc-v2"
EXPECTED_ROWS = 1_582
EXPECTED_SOURCES = {"scienceqa": 725, "sciq": 857}
EXPECTED_UNIQUE_GROUPS = 1_574
MISSING_CONTEXT_IDS = (
    "scienceqa:167",
    "scienceqa:3857",
    "scienceqa:4767",
    "scienceqa:7528",
    "scienceqa:10114",
    "scienceqa:12134",
    "scienceqa:15206",
    "scienceqa:20239",
)
THERMOMETER_QUESTION = "Select the temperature shown by this thermometer."
TEMPERATURE = re.compile(r"^-?\d+(?:\.\d+)?°[CF]$")


def _validate_reviewed_exclusions(
    source_rows: list[dict[str, Any]], raw_scienceqa: dict[str, Any]
) -> None:
    by_id = {row.get("id"): row for row in source_rows}
    base.require(set(MISSING_CONTEXT_IDS) <= set(by_id), "reviewed exclusion ID disappeared")
    for row_id in MISSING_CONTEXT_IDS:
        row = by_id[row_id]
        source_id = row_id.split(":", 1)[1]
        raw = raw_scienceqa.get(source_id)
        base.require(type(raw) is dict, "reviewed raw ScienceQA row disappeared")
        base.require(
            row.get("source") == "scienceqa"
            and row.get("source_id") == source_id
            and row.get("question") == THERMOMETER_QUESTION
            and row.get("source_metadata", {}).get("skill") == "Read a thermometer"
            and type(row.get("choices")) is list
            and 2 <= len(row["choices"]) <= 4
            and all(
                type(choice) is str and TEMPERATURE.fullmatch(choice) for choice in row["choices"]
            ),
            "reviewed thermometer exclusion changed family or text evidence",
        )
        solution = row.get("source_solution")
        base.require(
            type(solution) is str
            and "red liquid" in solution.casefold()
            and "scale to the right" in solution.casefold(),
            "reviewed thermometer exclusion lost source-solution visual evidence",
        )
        base.require(
            raw.get("question") == THERMOMETER_QUESTION
            and raw.get("image") is None
            and not str(raw.get("hint") or "").strip(),
            "reviewed raw thermometer context changed",
        )


def load_inputs(root: Path = ROOT) -> dict[str, bytes]:
    loaded = base.load_inputs(root)
    raw = base.safe_read(root, RAW_SCIENCEQA)
    base.require(
        base.sha(raw) == RAW_SCIENCEQA_SHA256 and len(raw) == RAW_SCIENCEQA_BYTES,
        "immutable raw ScienceQA identity mismatch",
    )
    loaded[RAW_SCIENCEQA] = raw
    return loaded


def assemble(
    source_payload: bytes, raw_scienceqa_payload: bytes
) -> tuple[dict[str, bytes], dict[str, Any]]:
    """Apply the reviewed exclusion set to the already validated v1 projection."""

    source_rows = base.jsonl_rows(source_payload)
    raw_scienceqa = base.parse(raw_scienceqa_payload)
    base.require(type(raw_scienceqa) is dict, "raw ScienceQA must be an object")
    _validate_reviewed_exclusions(source_rows, raw_scienceqa)

    v1_artifacts, v1_metadata = base.assemble(source_payload)
    excluded_ids = set(MISSING_CONTEXT_IDS)
    prompt_rows = [
        row
        for row in base.jsonl_rows(v1_artifacts["prompts.jsonl"])
        if row["id"] not in excluded_ids
    ]
    key_rows = [
        row for row in base.jsonl_rows(v1_artifacts["keys.jsonl"]) if row["id"] not in excluded_ids
    ]
    base.require(
        len(prompt_rows) == len(key_rows) == EXPECTED_ROWS
        and [row["id"] for row in prompt_rows] == [row["id"] for row in key_rows]
        and not (excluded_ids & {row["id"] for row in prompt_rows}),
        "corrected prompt/key population mismatch",
    )
    sources = dict(sorted(Counter(row["source"] for row in prompt_rows).items()))
    subjects = dict(sorted(Counter(row["subject"] for row in prompt_rows).items()))
    unique_groups = len({row["group_id"] for row in prompt_rows})
    base.require(
        sources == EXPECTED_SOURCES and unique_groups == EXPECTED_UNIQUE_GROUPS,
        "corrected source/group population mismatch",
    )
    exclusions = list(v1_metadata["excluded"])
    exclusions.extend(
        {
            "id": row_id,
            "source": "scienceqa",
            "reason": "missing_required_visual_context_thermometer",
        }
        for row_id in MISSING_CONTEXT_IDS
    )
    artifacts = {
        "prompts.jsonl": b"".join(base.canonical(row) + b"\n" for row in prompt_rows),
        "keys.jsonl": b"".join(base.canonical(row) + b"\n" for row in key_rows),
    }
    metadata = {
        "ids": [row["id"] for row in prompt_rows],
        "excluded": exclusions,
        "sources": sources,
        "subjects": subjects,
        "unique_groups": unique_groups,
    }
    return artifacts, metadata


def _unchanged(root: Path, loaded: dict[str, bytes]) -> None:
    for relative, payload in loaded.items():
        base.require(
            base.safe_read(root, relative) == payload, "input changed during freeze: " + relative
        )


def freeze(
    *, reviewed_builder_sha256: str, root: Path = ROOT, destination: Path | None = None
) -> dict[str, Any]:
    """Publish v2 exclusively. ``destination`` exists only for CPU tests."""

    root = root.absolute()
    output = (destination if destination is not None else root / OUTPUT).absolute()
    base.require(not output.exists(), "output already exists; refuse overwrite/resume")
    for candidate in (output, *output.parents):
        base.require(not candidate.is_symlink(), "symlinked output path")

    loaded = load_inputs(root)
    for relative in (BUILDER, BASE_BUILDER, TESTS, PLAN):
        loaded[relative] = base.safe_read(root, relative)
    base.require(
        base.sha(loaded[BUILDER]) == reviewed_builder_sha256,
        "externally reviewed builder hash mismatch",
    )
    for relative in loaded:
        source_path = (root / relative).absolute()
        base.require(
            output != source_path and output not in source_path.parents,
            "output contains an input",
        )

    artifacts, metadata = assemble(loaded[base.SOURCE], loaded[RAW_SCIENCEQA])
    artifact_receipts = {
        name: {
            "sha256": base.sha(payload),
            "bytes": len(payload),
            "rows": len(base.jsonl_rows(payload)),
        }
        for name, payload in sorted(artifacts.items())
    }
    manifest = {
        "schema_version": 1,
        "status": "frozen_final_source_heldout_science_mc",
        "release": "final-science-mc-v2",
        "supersedes_rejected_release": "final-science-mc-v1",
        "rows": EXPECTED_ROWS,
        "source_rows": base.SOURCE_ROWS,
        "excluded_rows": 1 + len(MISSING_CONTEXT_IDS),
        "unique_groups": metadata["unique_groups"],
        "sources": metadata["sources"],
        "subjects": metadata["subjects"],
        "ids": metadata["ids"],
        "ordered_ids_sha256": base.sha(base.canonical(metadata["ids"])),
        "ordering": "fixed source order scienceqa,sciq; exact id ascending within source",
        "exclusions": metadata["excluded"],
        "context_dependency_review": {
            "scienceqa_rows_reviewed": 733,
            "scienceqa_skill_families_reviewed": 37,
            "fields": ["question", "choices", "source_solution", "source_metadata"],
            "question_deictic_candidates_reviewed": 27,
            "missing_context_excluded": len(MISSING_CONTEXT_IDS),
            "text_closed_deictic_candidates_retained": 19,
            "missing_context_ids": list(MISSING_CONTEXT_IDS),
            "decision": "exclude_exact_reviewed_rows_before_inference",
        },
        "input_bindings": [
            {"path": path, "sha256": base.sha(payload), "bytes": len(payload)}
            for path, payload in sorted(loaded.items())
        ],
        "reviewed_builder_sha256": reviewed_builder_sha256,
        "artifacts": artifact_receipts,
        "prompt_construction": {
            "inputs": ["question", "ordered choices"],
            "instruction": base.PROMPT_INSTRUCTION,
            "messages": "one user message; no source assistant turn",
            "generation_contract": "one option letter only",
        },
        "answer_leakage_checks": {
            "prompt_schema_exact": ["group_id", "id", "messages", "source", "subject"],
            "assistant_messages_in_prompts": 0,
            "answer_fields_in_prompts": 0,
            "solutions_or_lectures_in_prompts": 0,
            "correct_option_marker_in_prompts": 0,
            "note": (
                "Every answer text necessarily appears once as an unlabeled member of the "
                "choice set; no prompt identifies which choice is correct."
            ),
        },
        "key_policy": "Separate source-key ledger; source keys are not independently certified.",
        "limitations": [
            "Source answer keys are not independently verified for every row.",
            "Context review cannot prove the absence of every possible implicit dependency.",
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
        base.require(
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
                handle.write(base.canonical(failure) + b"\n")
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
                "release": manifest["release"],
                "rows": manifest["rows"],
                "output": str((ROOT / OUTPUT).resolve()),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
