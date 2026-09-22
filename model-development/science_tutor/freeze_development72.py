"""Freeze only the reviewed science development inputs; never run inference.

Production CLI requires the externally reviewed builder SHA256. Existing output
is never reused or replaced. The manifest is written last after identity checks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BASE = "provenance/science-tutor-20260919"
REVIEWS = BASE + "/reviews/"
MC_REVIEW = REVIEWS + "development64-independent-v1.json"
TUTOR_REVIEW = REVIEWS + "heldout16-independent-review-v2.json"
OVERLAP_REVIEW = REVIEWS + "heldout16-independent-overlap-v2.json"
PILOT_DEV = "data/muta-science-tutor-20260919/pilot-v1/dev.jsonl"
HELDOUT = "data/muta-science-tutor-20260919/sources/muta_authored_science_heldout-v2/"
PACKET = BASE + "/sources/heldout16-v2/heldout16-review-packet.jsonl"
ORIGINAL = BASE + "/evaluation/development64-v1/"
OUTPUT = BASE + "/evaluation/development72-v1"
BUILDER = "model-development/science_tutor/freeze_development72.py"
TESTS = "model-development/science_tutor/test_freeze_development72.py"
PLAN = "docs/plans/2026-09-19-science-tutor-development72-freeze.md"
SUBJECTS = ("biology", "chemistry", "physics", "earth_environmental_science", "integrated_science")
PINNED = {
    MC_REVIEW: "8cb7870e985fc902f5303e25f54e19a8f7a83a6c0aa5cacd22b2e4ab6a144660",
    TUTOR_REVIEW: "f84934cdec29db6e88af18786b37b6b9c56a5f2a9db48ebdd16c076561cbb296",
    OVERLAP_REVIEW: "4af8ad06bdb5c36643a44ba5aad9eec72744d1964550b9e959f2878eaec70874",
    "docs/plans/2026-09-19-science-tutor-selection.md": "30c8e3fa5ce5afa886c883d3fcab4c7500bdcf2728c10014613492b068d057ad",
    "docs/plans/2026-09-19-science-tutor-selection-four-parents.md": "2a3f662f3cc91eb2191e34fdb96098b53c58d32eb62b849c2deb8b7412e34223",
}
APPROVE = "approve_bounded_mc_key_and_wording"
REJECT = "reject_for_single_key_evaluation"
REVIEWER = "/root/winner_battery_progress"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: Any, *, spaced: bool = False) -> bytes:
    options = {} if spaced else {"separators": (",", ":")}
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, allow_nan=False, **options
    ).encode()


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise ValueError("non-finite JSON number: " + value)


def parse(raw: bytes) -> Any:
    return json.loads(raw, object_pairs_hook=_object, parse_constant=_nonfinite)


def rows(raw: bytes) -> list[dict[str, Any]]:
    lines = raw.splitlines()
    require(bool(lines) and all(line.strip() for line in lines), "empty JSONL or blank row")
    values = [parse(line) for line in lines]
    require(all(type(value) is dict for value in values), "JSONL rows must be objects")
    return values


def index(values: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {}
    for row in values:
        key = row.get("id")
        require(type(key) is str and bool(key) and key not in result, "invalid/duplicate row id")
        result[key] = row
    return result


def safe_read(root: Path, relative: str) -> bytes:
    rel = Path(relative)
    require(not rel.is_absolute() and ".." not in rel.parts, "unsafe input path")
    path = root / rel
    for parent in (path, *path.parents):
        require(not parent.is_symlink(), "symlinked input path: " + relative)
        if parent == root:
            break
    require(path.is_file(), "missing/nonregular input: " + relative)
    return path.read_bytes()


def load_inputs(root: Path) -> dict[str, bytes]:
    """The three fixed review hashes authenticate their subsidiary bindings."""
    loaded = {}
    for path, digest in PINNED.items():
        raw = safe_read(root, path)
        require(sha(raw) == digest, "pinned input hash mismatch: " + path)
        loaded[path] = raw
    mc, tutor, overlap = (parse(loaded[p]) for p in (MC_REVIEW, TUTOR_REVIEW, OVERLAP_REVIEW))
    bindings = (
        mc["input_bindings"] + tutor["mechanical_checks"]["bindings"] + overlap["source_bindings"]
    )
    for binding in bindings:
        path = binding["path"]
        raw = safe_read(root, path)
        require(
            sha(raw) == binding["sha256"] and len(raw) == binding["bytes"],
            "review source binding mismatch: " + path,
        )
        require(path not in loaded or loaded[path] == raw, "conflicting review bindings")
        loaded[path] = raw
    return loaded


def rank(row: dict[str, Any]) -> str:
    return sha(("3407:science-dev-v1:" + row["id"]).encode())


def check_messages(messages: Any, roles: list[str]) -> None:
    require(type(messages) is list and len(messages) == len(roles), "message count mismatch")
    for message, role in zip(messages, roles, strict=True):
        require(type(message) is dict and set(message) == {"role", "content"}, "message schema")
        require(
            message["role"] == role
            and type(message["content"]) is str
            and bool(message["content"].strip()),
            "message role/content mismatch",
        )


def mc_key(row: dict[str, Any]) -> dict[str, Any]:
    choices, answer_index = row["choices"], row["answer_index"]
    require(
        type(choices) is list
        and 2 <= len(choices) <= 26
        and all(type(c) is str and c.strip() for c in choices),
        "invalid choices",
    )
    require(type(answer_index) is int and 0 <= answer_index < len(choices), "invalid answer index")
    require(row["answer"] == choices[answer_index], "source answer/choice mismatch")
    check_messages(row["messages"], ["user", "assistant"])
    return {
        "id": row["id"],
        "answer_index": answer_index,
        "answer_letter": chr(65 + answer_index),
        "answer_text": row["answer"],
        "row_canonical_sha256": sha(canonical(row)),
        "model_messages_sha256": sha(canonical(row["messages"][:-1])),
    }


def validate_mc(loaded: dict[str, bytes]) -> list[dict[str, Any]]:
    review = parse(loaded[MC_REVIEW])
    require(
        review["verdict"] == "GO_PROPOSED_REVIEWED_64_ONLY_NOT_ORIGINAL_V1"
        and review["reviewer"] == REVIEWER
        and review["remaining_blockers_for_proposed64"] == []
        and review["original_v1_admission_allowed"] is False,
        "MC review not admitted",
    )
    pool = rows(loaded[PILOT_DEV])
    by_id = index(pool)
    require(len(pool) == 1577, "pilot development count changed")
    reviewed = index(review["reviews"])
    require(len(reviewed) == review["reviewed_count"] == 80, "MC review coverage changed")
    buckets = [(s, 8) for s in SUBJECTS] + [(None, 24)]
    initial, selected, encountered = [], [], set()
    for subject, count in buckets:
        bucket = sorted(
            (
                r
                for r in pool
                if (
                    r["source"] == "sciq"
                    if subject is None
                    else r["source"] == "scienceqa" and r["subject"] == subject
                )
            ),
            key=rank,
        )
        require(len(bucket) >= count, "insufficient source bucket")
        initial.extend(bucket[:count])
        accepted = []
        for position, row in enumerate(bucket, 1):
            require(row["id"] in reviewed, "unreviewed rank gap: " + row["id"])
            item = reviewed[row["id"]]
            encountered.add(row["id"])
            require(
                item["fixed_bucket_rank"] == position and type(item["fixed_bucket_rank"]) is int,
                "review rank mismatch",
            )
            require(
                item["stage"]
                == ("original64" if position <= count else "ranked_replacement_candidate"),
                "review stage mismatch",
            )
            require(
                all(item[key] == row[key] for key in ("source", "subject", "group_id")),
                "review source/group mismatch",
            )
            require(
                all(item[key] == value for key, value in mc_key(row).items()),
                "review row/messages/key mismatch",
            )
            require(item["verdict"] in (APPROVE, REJECT), "unrecognized MC review verdict")
            if item["verdict"] == APPROVE:
                require(
                    type(item["verified_answer_index"]) is int
                    and item["verified_answer_index"] == row["answer_index"],
                    "unverified key",
                )
                accepted.append(row)
            else:
                require(item["verified_answer_index"] is None, "rejected row has verified key")
            if len(accepted) == count:
                break
        require(len(accepted) == count, "insufficient approved source bucket")
        selected.extend(accepted)
    require(encountered == set(reviewed), "unconsumed/extra review entries")
    require(
        rows(loaded[ORIGINAL + "review.jsonl"]) == initial, "original 64 proposal/rank mismatch"
    )
    require(
        rows(loaded[ORIGINAL + "prompts.jsonl"])
        == [
            {"id": r["id"], "subject": r["subject"], "messages": r["messages"][:-1]}
            for r in initial
        ],
        "original prompt projection mismatch",
    )
    require([r["id"] for r in selected] == review["final64_ids"], "review final IDs/order mismatch")
    require(
        [mc_key(r) for r in selected] == review["final64_answer_keys"], "review final keys mismatch"
    )
    require(
        len(selected)
        == len({r["id"] for r in selected})
        == len({r["group_id"] for r in selected})
        == 64,
        "MC identity/group count mismatch",
    )
    require(all(by_id[r["id"]] == r for r in selected), "source row join mismatch")
    return selected


def validate_tutor(loaded: dict[str, bytes]) -> list[dict[str, Any]]:
    review, overlap = (parse(loaded[p]) for p in (TUTOR_REVIEW, OVERLAP_REVIEW))
    require(
        review["verdict"] == "GO_V2_CONTENT_RUBRIC_AND_BOUNDED_LEXICAL_REVIEW"
        and review["reviewer"] == overlap["reviewer"] == REVIEWER
        and review["remaining_blockers_within_this_review"] == []
        and review["overlap_receipt"] == Path(OVERLAP_REVIEW).name,
        "tutor review not admitted",
    )
    require(
        overlap["status"] == "PASS_BOUNDED_LEXICAL_SCREEN_ONLY"
        and overlap["hits"] == overlap["within_heldout_nonself_hits"] == [],
        "heldout overlap review failed",
    )
    cases = [r["case"] for r in rows(loaded[PACKET])]
    all_cases, reviewed, screened = (
        index(v) for v in (cases, review["per_case_review"], overlap["case_bindings"])
    )
    require(
        len(all_cases) == 16 and set(all_cases) == set(reviewed) == set(screened),
        "heldout review coverage mismatch",
    )
    for key, case in all_cases.items():
        digest = sha(canonical(case, spaced=True))
        require(
            reviewed[key]["sha256"] == screened[key]["sha256"] == digest
            and reviewed[key]["split"] == screened[key]["split"] == case["split"],
            "heldout case hash/split mismatch",
        )
        require(
            reviewed[key]["verdict"] == "acceptable_bounded_independent_agent_content_review",
            "heldout case not approved",
        )
        require(
            case["train_eligible"] is False
            and case["usage"] == "evaluation_only_never_train"
            and case["split"] == case["original_split"] in ("dev", "final"),
            "heldout eligibility/split mismatch",
        )
        check_messages(case["messages"], ["user", "assistant", "user"])
    dev = rows(loaded[HELDOUT + "dev_cases.jsonl"])
    final = rows(loaded[HELDOUT + "final_cases.jsonl"])
    for split, subset in (("dev", dev), ("final", final)):
        require(
            len(index(subset)) == 8
            and all(r["split"] == split and all_cases[r["id"]] == r for r in subset),
            "heldout source case join mismatch",
        )
        require(
            rows(loaded[HELDOUT + split + "_prompts.jsonl"])
            == [{k: r[k] for k in ("id", "group_id", "split", "messages")} for r in subset],
            "heldout prompt projection mismatch",
        )
        require(
            Counter(r["subject"] for r in subset)
            == {"physics": 2, "chemistry": 2, "biology": 2, "earth_science": 2},
            "heldout subject balance mismatch",
        )
    require(
        not ({r["group_id"] for r in dev} & {r["group_id"] for r in final}),
        "heldout development/final group overlap",
    )
    return dev


def assemble(loaded: dict[str, bytes]) -> dict[str, bytes]:
    """Pure construction; only freeze() loads/pins inputs and publishes artifacts."""
    mc, tutor = validate_mc(loaded), validate_tutor(loaded)
    prompts = [{"id": r["id"], "messages": r["messages"][:-1]} for r in mc]
    prompts.extend({"id": r["id"], "messages": r["messages"]} for r in tutor)
    require(len(index(prompts)) == 72, "development72 identity count")
    keys = [mc_key(r) | {k: r[k] for k in ("source", "subject", "group_id", "choices")} for r in mc]
    # Copy only development case grading metadata, never the eight final cases.
    rubrics = [
        {k: v for k, v in r.items() if k != "messages"}
        | {
            "source_case_canonical_sha256": sha(canonical(r, spaced=True)),
            "model_messages_sha256": sha(canonical(r["messages"])),
        }
        for r in tutor
    ]
    return {
        name: b"".join(canonical(row) + b"\n" for row in records)
        for name, records in (
            ("prompts.jsonl", prompts),
            ("mc_keys.jsonl", keys),
            ("tutor_rubrics.jsonl", rubrics),
        )
    }


def _unchanged(root: Path, loaded: dict[str, bytes]) -> None:
    for path, raw in loaded.items():
        require(safe_read(root, path) == raw, "input changed during freeze: " + path)


def freeze(
    *, reviewed_builder_sha256: str, root: Path = ROOT, destination: Path | None = None
) -> dict[str, Any]:
    """Destination override is for CPU tests; the CLI exposes only the fixed path."""
    root = root.absolute()
    output = (destination if destination is not None else root / OUTPUT).absolute()
    require(not output.exists(), "output already exists; refuse overwrite/resume")
    for path in (output, *output.parents):
        require(not path.is_symlink(), "symlinked output path")
    loaded = load_inputs(root)
    for source in (BUILDER, TESTS, PLAN):
        loaded[source] = safe_read(root, source)
    require(
        sha(loaded[BUILDER]) == reviewed_builder_sha256, "externally reviewed builder hash mismatch"
    )
    for relative in loaded:
        target = (root / relative).absolute()
        require(output != target and output not in target.parents, "output contains an input")
    artifacts = assemble(loaded)
    bindings = [
        {"path": p, "sha256": sha(raw), "bytes": len(raw)} for p, raw in sorted(loaded.items())
    ]
    manifest = {
        "schema_version": 1,
        "status": "frozen_reviewed_development72",
        "rows": 72,
        "mc_rows": 64,
        "tutor_rows": 8,
        "ids": [r["id"] for r in rows(artifacts["prompts.jsonl"])],
        "input_bindings": bindings,
        "reviewed_builder_sha256": reviewed_builder_sha256,
        "artifacts": {
            name: {"sha256": sha(raw), "bytes": len(raw), "rows": len(rows(raw))}
            for name, raw in sorted(artifacts.items())
        },
        "inference_performed": False,
        "reserved_final_cases_included": False,
        "selection": "8 per five ScienceQA subjects plus 24 SciQ; consume reviewed same-bucket "
        "SHA256(3407:science-dev-v1:<id>) ranks without gaps; then 8 heldout-v2 dev cases",
        "review_scope": "Independent agent science/wording/rubric review; bounded lexical overlap "
        "screen only, not proof of semantic or family independence",
        "input_projection": "MC drops only final assistant target; tutor keeps full user/assistant/user context",
        "inference_input": "prompts.jsonl only; do not open mc_keys.jsonl or tutor_rubrics.jsonl",
        "mutation_policy": "Exclusive new directory/files, no overwrite/resume, manifest published last",
        "admission_rule": "Require successful builder exit, valid manifest and artifact hashes, "
        "and absence of FAILED.json or manifest.FAILED.json",
    }
    _unchanged(root, loaded)
    output.mkdir(parents=True, exist_ok=False)
    try:
        for name, raw in artifacts.items():
            with (output / name).open("xb") as handle:
                handle.write(raw)
        _unchanged(root, loaded)
        require(
            all((output / name).read_bytes() == raw for name, raw in artifacts.items()),
            "output changed before sealing",
        )
        with (output / "manifest.json").open("xb") as handle:
            handle.write(
                json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n"
            )
    except BaseException as exc:
        # A write/close may fail after creating a partial (or even complete)
        # manifest. Quarantine it without deleting its evidence; never mistake
        # file existence for successful publication. Attempt the failure marker
        # independently even if quarantine itself encounters an I/O failure.
        failure = {
            "status": "failed_before_manifest",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "automatic_retry": False,
            "terminal_manifest_valid": False,
        }
        try:
            if (output / "manifest.json").exists():
                require(
                    not (output / "manifest.FAILED.json").exists(),
                    "refuse overwriting existing manifest failure evidence",
                )
                (output / "manifest.json").rename(output / "manifest.FAILED.json")
        except (OSError, ValueError) as quarantine_error:
            failure["manifest_quarantine_error"] = str(quarantine_error)
        try:
            with (output / "FAILED.json").open("xb") as handle:
                handle.write(canonical(failure) + b"\n")
        except OSError as marker_error:
            raise RuntimeError(
                f"Materialization failed ({type(exc).__name__}: {exc}); "
                f"failure marker also could not be written: {marker_error}"
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
            {"status": manifest["status"], "rows": manifest["rows"], "output": str(ROOT / OUTPUT)}
        )
    )


if __name__ == "__main__":
    main()
