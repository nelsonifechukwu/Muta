"""Pinned, auditable acquisition of dialogue sources for the science tutor pilot.

Run with the repository virtualenv and pyarrow==19.0.1. Downloads are kept once,
under each source's raw/ directory; subsequent runs verify and reuse those bytes.
Normalization never turns individual dialogue turns into independent examples.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from collections import Counter, defaultdict
from itertools import pairwise
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_ROOT = ROOT / "data/muta-science-tutor-20260919/sources"
DEFAULT_PROVENANCE = ROOT / "provenance/science-tutor-20260919/sources"
PINS = {
    "convolearn": {
        "repository": "masharma/convolearn",
        "revision": "f250e930356f2092462c4d1cd6bb2aae85689b1f",
        "files": ["README.md", "data/train-00000-of-00001.parquet"],
    },
    "mathdial": {
        "repository": "eth-nlped/mathdial",
        "revision": "acc3878459e0bd8c04ab840056572f0b8b1abe1f",
        "files": ["README.md", "train.jsonl", "test.jsonl"],
        "github_revision": "b06c020a0a1f57a87577fec33e657b63e7eb476e",
    },
}
EXPECTED_SHA256 = {
    "convolearn": {
        "MIT.txt": "b05785f9f18e6716bab63424b11454513b9943a222595b70411009202fc592b5",
        "README.md": "44acc0889ba1a10598fb98c1d2d39e0cfd433c4fb765eb9ec985fa4c5c5d78bf",
        "data/train-00000-of-00001.parquet": "c1599655c3a2a3ef5fd199906200f02afd6b26a1bd4b5fbc16a18d6b784d5c04",
    },
    "mathdial": {
        "CC-BY-4.0.txt": "9ba9550ad48438d0836ddab3da480b3b69ffa0aac7b7878b5a0039e7ab429411",
        "CC-BY-SA-4.0.txt": "28a9529c7d0bb4dc51f4bf5c116a3d16ef247a052f7591466768ddf563fd1cf5",
        "README.md": "c63e86fd95d4e1fd60cccd78226a27d9e787ad91ed037b353d8e3083a0e5eaeb",
        "github-README.md": "50430d327d94453c02a9c21d831fac2bfb73aa8a261d4c669cf2b335651ec227",
        "test.jsonl": "3ec54ee8ab921dc6191bf5e2ee766d4e7916b4264394eb17a6be9b3fe486e50b",
        "train.jsonl": "d6135869c02dccf8d14756fa2f0367c5352922bb263ec22dc0eeace4da815d43",
    },
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8")


def acquire_file(url: str, target: Path, previous: dict | None = None) -> dict:
    """Fail closed on changed cached bytes; never silently refresh a source."""
    if target.exists():
        if previous is None:
            raise ValueError(f"Existing source has no receipt: {target}")
        content = target.read_bytes()
        if previous["url"] != url or sha256_bytes(content) != previous["sha256"]:
            raise ValueError(f"Cached source/receipt mismatch: {target}")
    else:
        content = subprocess.run(
            [
                "curl",
                "--fail",
                "--silent",
                "--show-error",
                "--location",
                "--connect-timeout",
                "20",
                "--max-time",
                "90",
                "--retry",
                "2",
                url,
            ],
            check=True,
            capture_output=True,
        ).stdout
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return {"url": url, "path": str(target), "sha256": sha256_bytes(content), "bytes": len(content)}


def acquire_source(source: str, data_root: Path, provenance: Path) -> dict:
    pin = PINS[source]
    raw = data_root / source / "raw"
    receipt_path = provenance / f"dialogues-{source}-acquisition.json"
    previous = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
    receipt = {"source": source, "pin": pin, "artifacts": previous.get("artifacts", {})}
    urls = {
        path: f"https://huggingface.co/datasets/{pin['repository']}/resolve/{pin['revision']}/{path}"
        for path in pin["files"]
    }
    urls["dataset-metadata.json"] = (
        f"https://huggingface.co/api/datasets/{pin['repository']}/revision/{pin['revision']}"
    )
    if source == "mathdial":
        urls["github-README.md"] = (
            "https://raw.githubusercontent.com/eth-nlped/mathdial/"
            f"{pin['github_revision']}/README.md"
        )
        urls["CC-BY-4.0.txt"] = "https://creativecommons.org/licenses/by/4.0/legalcode.txt"
        urls["CC-BY-SA-4.0.txt"] = "https://creativecommons.org/licenses/by-sa/4.0/legalcode.txt"
    else:
        urls["MIT.txt"] = (
            "https://raw.githubusercontent.com/spdx/license-list-data/v3.27.0/text/MIT.txt"
        )
    for relative, url in urls.items():
        item = acquire_file(url, raw / relative, receipt["artifacts"].get(relative))
        expected = EXPECTED_SHA256[source].get(relative)
        if expected is not None and item["sha256"] != expected:
            raise ValueError(f"Pinned artifact digest mismatch: {source}/{relative}")
        receipt["artifacts"][relative] = item
        save_json(receipt_path, receipt)
    return receipt


def normalized_text(value: str) -> str:
    return " ".join(re.findall(r"[\w]+", value.casefold()))


def content_hash(value: str) -> str:
    return sha256_bytes(normalized_text(value).encode("utf-8"))


def merge_adjacent(messages: list[dict]) -> tuple[list[dict], int]:
    """Preserve text when a speaker sent multiple successive source messages."""
    result: list[dict] = []
    merges = 0
    for message in messages:
        if not message["content"].strip():
            raise ValueError("empty_speaker_turn")
        if result and result[-1]["role"] == message["role"]:
            result[-1]["content"] += "\n\n" + message["content"]
            merges += 1
        else:
            result.append(dict(message))
    return result, merges


def parse_convolearn(text: str) -> tuple[list[dict], int]:
    markers = list(re.finditer(r"(?m)^(Student|Teacher):[ \t]*", text))
    if not markers or text[: markers[0].start()].strip():
        raise ValueError("unparsed_dialogue_prefix")
    messages = []
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        content = text[marker.end() : end].strip()
        # Unrecognized role-like labels cannot be assigned to an assistant safely.
        if re.search(r"(?m)^[A-Z][A-Za-z ]{0,24}:\s", content):
            raise ValueError("unrecognized_embedded_role")
        messages.append(
            {"role": "user" if marker[1] == "Student" else "assistant", "content": content}
        )
    if messages[0]["role"] != "user":
        raise ValueError("missing_initial_student_prompt")
    return merge_adjacent(messages)


def parse_mathdial(record: dict) -> tuple[list[dict], int]:
    profile = record.get("student_profile") or ""
    match = re.match(r"^([A-Za-z]+)\s+is\b", profile)
    student_names = {"Student"}
    if match:
        student_names.add(match[1])
    question = record.get("question")
    attempt = record.get("student_incorrect_solution")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("missing_problem")
    if not isinstance(attempt, str) or not attempt.strip():
        raise ValueError("missing_student_attempt")
    # Correct ground_truth and teacher-only confusion annotations never enter input.
    messages = [
        {
            "role": "user",
            "content": (
                f"Please help me understand this problem:\n{question.strip()}\n\n"
                f"Here is my attempt:\n{attempt.strip()}"
            ),
        }
    ]
    for turn in record["conversation"].split("|EOM|"):
        speaker, separator, content = turn.strip().partition(":")
        if not separator or speaker not in student_names | {"Teacher"}:
            raise ValueError("unrecognized_source_speaker")
        content = content.strip()
        if speaker == "Teacher":
            content = re.sub(r"^\((?:focus|probing|generic|telling)\)\s*", "", content)
            if re.match(r"^\([a-z_-]+\)", content):
                raise ValueError("unrecognized_teacher_act")
        messages.append(
            {"role": "assistant" if speaker == "Teacher" else "user", "content": content}
        )
    return merge_adjacent(messages)


VISUAL_REFERENCE = re.compile(
    r"(?:looking at (?:a|the) topographic map|(?:this|above|below|following) "
    r"(?:map|diagram|graph|figure|image)|(?:map|diagram|graph|figure|image) "
    r"(?:shown|above|below)|(?:look|looking) at (?:this|the) (?:map|diagram|image))",
    re.IGNORECASE,
)


def dialogue_issues(messages: list[dict]) -> list[str]:
    issues = []
    if sum(message["role"] == "assistant" for message in messages) < 2:
        issues.append("fewer_than_two_assistant_turns")
    if any(VISUAL_REFERENCE.search(message["content"]) for message in messages):
        issues.append("visual_reference_requires_review")
    for left, right in pairwise(messages):
        if left["role"] == right["role"]:
            issues.append("nonalternating_roles")
            break
    return issues


def license_evidence(source: str, raw: Path) -> dict:
    card = (raw / "README.md").read_text(encoding="utf-8")
    if source == "convolearn":
        permitted = bool(re.search(r"(?m)^license:\s*mit\s*$", card))
        return {
            "status": "explicit_public_license" if permitted else "unresolved",
            "effective_license": "MIT" if permitted else "unknown",
            "requirements": ["Retain source attribution and MIT permission notice."],
            "evidence": [str(raw / "README.md"), str(raw / "MIT.txt")],
            "copyright_notice": "No separate copyright holder notice supplied by dataset card.",
        }
    repository_card = (raw / "github-README.md").read_text(encoding="utf-8")
    permitted = bool(re.search(r"(?m)^license:\s*cc-by-4\.0\s*$", card)) and bool(
        re.search(r"https?://creativecommons.org/licenses/by-sa/4\.0/", repository_card)
    )
    return {
        "status": "explicit_licenses_conservative_combined_obligations"
        if permitted
        else "unresolved",
        "effective_license": "CC-BY-SA-4.0" if permitted else "unknown",
        "declared_huggingface": "CC-BY-4.0",
        "declared_github": "CC-BY-SA-4.0",
        "requirements": [
            "Credit MathDial authors and original source; link both license declarations.",
            "Record normalization/filtering modifications.",
            "Retain attribution and ShareAlike requirements on redistributed adapted dataset.",
            "Do not represent the conflicting upstream declarations as resolved.",
            "Any public model/dataset release requires separate license review; no publication here.",
        ],
        "evidence": [
            str(raw / name)
            for name in ["README.md", "github-README.md", "CC-BY-4.0.txt", "CC-BY-SA-4.0.txt"]
        ],
    }


def base_row(source: str, split: str, index: int, record: dict, license_info: dict) -> dict:
    if source == "mathdial":
        source_id = f"{split}:{record.get('qid')}:{record.get('scenario')}:{index}"
        group = f"mathdial:qid:{record.get('qid')}"
        subject = "mathematics"
        capabilities = ["quantitative_reasoning", "misconception_repair", "adaptive_dialogue"]
        quality = {
            "tier": "source_reviewed_not_independently_verified",
            "evidence": "Human teacher dialogue and teacher self-report; LLM-simulated student.",
            "self_correctness": record.get("self-correctness"),
            "self_typical_confusion": record.get("self-typical-confusion"),
            "self_typical_interactions": record.get("self-typical-interactions"),
        }
        metadata = {
            key: record.get(key) for key in ["qid", "scenario", "teacher_described_confusion"]
        }
    else:
        source_id = f"row:{index}:dialogue:{sha256_bytes(record['cleaned_conversation'].encode())}"
        group = "pending_parse"
        subject = "earth_science"
        capabilities = ["conceptual_reasoning", "adaptive_dialogue"]
        if record["earthscience_topic"] == "Investigation and Experimentation":
            capabilities.append("experimental_reasoning")
        quality = {
            "tier": "source_reviewed_not_independently_verified",
            "evidence": "Credentialed human teacher; simulated student; silver LLM annotations.",
            "effectiveness_consensus": record["effectiveness_consensus"],
            "completeness_consensus": record["completeness_consensus"],
        }
        metadata = {
            key: record[key]
            for key in ["kb_dim", "kb_subdim", "earthscience_topic", "num_exchanges"]
        }
    quality["independent_scientific_verification"] = False
    return {
        "id": f"{source}:{source_id}",
        "group_id": group,
        "source": source,
        "source_revision": PINS[source]["revision"],
        "source_id": source_id,
        "license": license_info["effective_license"],
        "subject": subject,
        "capabilities": capabilities,
        "quality": quality,
        "messages": [],
        "original_split": split,
        "source_row_index": index,
        "source_metadata": metadata,
        "eligibility": "candidate_train" if split == "train" else "source_test_only",
        "fresh_holdout_admission": "pending_historical_and_campaign_overlap_screen",
        "license_evidence_status": license_info["status"],
    }


def read_sources(data_root: Path) -> dict[str, dict[str, list[dict]]]:
    import pyarrow.parquet as pq

    return {
        "convolearn": {
            "train": pq.read_table(
                data_root / "convolearn/raw/data/train-00000-of-00001.parquet"
            ).to_pylist()
        },
        "mathdial": {
            split: [
                json.loads(line)
                for line in (data_root / f"mathdial/raw/{split}.jsonl").read_text().splitlines()
            ]
            for split in ("train", "test")
        },
    }


def normalize_source(
    source: str, partitions: dict[str, list[dict]], license_info: dict
) -> list[dict]:
    output = []
    test_ids = {str(row["qid"]) for row in partitions.get("test", [])}
    # Stronger than preserving a source's dialogue split: hold out entire qids.
    for split, records in partitions.items():
        for index, record in enumerate(records):
            row = base_row(source, split, index, record, license_info)
            excluded, quarantine = [], []
            if license_info["status"] == "unresolved":
                quarantine.append("unresolved_source_permission")
            try:
                messages, merges = (
                    parse_convolearn(record["cleaned_conversation"])
                    if source == "convolearn"
                    else parse_mathdial(record)
                )
                row["messages"] = messages
                row["source_metadata"]["adjacent_role_merges"] = merges
                quarantine.extend(dialogue_issues(messages))
            except (ValueError, KeyError, TypeError) as error:
                quarantine.append(f"parse_error:{error}")
                messages = []
            if source == "convolearn":
                first_prompt = messages[0]["content"] if messages else ""
                # No generic greeting is treated as an independent problem.
                informative = len(normalized_text(first_prompt).split()) >= 8
                group_key = (
                    normalized_text(first_prompt)
                    if informative
                    else f"unresolved-prompt-topic:{record['earthscience_topic']}"
                )
                row["group_id"] = f"convolearn:prompt:{sha256_bytes(group_key.encode())}"
                row["source_metadata"]["grouping_basis"] = (
                    "normalized_initial_student_problem" if informative else "topic_fallback"
                )
                if not informative:
                    quarantine.append("uninformative_initial_prompt")
                effectiveness, completeness = (
                    record["effectiveness_consensus"],
                    record["completeness_consensus"],
                )
                if not all(
                    isinstance(v, (int, float)) and math.isfinite(v)
                    for v in (effectiveness, completeness)
                ):
                    quarantine.append("missing_or_nonfinite_quality_rating")
                elif effectiveness < 4 or completeness < 3:
                    excluded.append("silver_quality_below_4_effectiveness_or_3_completeness")
                raw_text = record["cleaned_conversation"]
            else:
                if split == "train" and str(record["qid"]) in test_ids:
                    excluded.append("source_test_problem_group_overlap")
                if split == "train" and record.get("self-correctness") != "Yes":
                    excluded.append("not_self_reported_solved_without_revealing_answer")
                raw_text = record["conversation"]
            digest = content_hash(raw_text)
            row["source_metadata"]["dialogue_content_hash"] = digest
            row["exclusion_reasons"] = excluded
            row["quarantine_reasons"] = quarantine
            if quarantine:
                row["eligibility"] = "quarantine"
            elif excluded:
                row["eligibility"] = "excluded"
            output.append(row)
    # Prefer the source test copy, then an otherwise eligible training copy.
    # This cannot move a training example into a test split.
    duplicates: dict[str, list[dict]] = defaultdict(list)
    for row in output:
        duplicates[row["source_metadata"]["dialogue_content_hash"]].append(row)
    priority = {"source_test_only": 0, "candidate_train": 1, "quarantine": 2, "excluded": 3}
    for members in duplicates.values():
        ordered = sorted(members, key=lambda r: (priority[r["eligibility"]], r["id"]))
        for duplicate in ordered[1:]:
            duplicate["exclusion_reasons"].append("duplicate_dialogue")
            if duplicate["eligibility"] != "quarantine":
                duplicate["eligibility"] = "excluded"
    return output


def write_jsonl(path: Path, rows: list[dict]) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = "".join(canonical_json(row) + "\n" for row in rows).encode("utf-8")
    path.write_bytes(data)
    return {"path": str(path), "sha256": sha256_bytes(data), "bytes": len(data), "rows": len(rows)}


def audit_sample(rows: list[dict], per_stratum: int = 2) -> list[dict]:
    strata: dict[tuple, list] = defaultdict(list)
    for row in rows:
        stratum = (
            row["source"],
            row["original_split"],
            row["eligibility"],
            row["source_metadata"].get("kb_dim", "math"),
            row["source_metadata"].get("earthscience_topic", "math"),
        )
        strata[stratum].append(row)
    samples = []
    for stratum, members in sorted(strata.items()):
        for row in sorted(members, key=lambda x: sha256_bytes(x["id"].encode()))[:per_stratum]:
            samples.append(
                {
                    "stratum": list(stratum),
                    "stratum_population": len(members),
                    "audit_status": "pending_independent_review",
                    "row": row,
                }
            )
    return samples


def normalize_all(data_root: Path, provenance: Path) -> dict:
    sources = read_sources(data_root)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "pipeline": str(Path(__file__).resolve()),
        "pipeline_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "normalization_policy": {
            "convolearn": "Keep silver effectiveness>=4, completeness>=3; preserve full dialogue.",
            "mathdial": "Train only self-correctness Yes; remove train qids appearing in source test.",
            "role_policy": "Strip MathDial act labels; merge adjacent same-role messages without text removal.",
            "quality_limit": "Source-reviewed only; no independent scientific verification or final admission.",
            "holdout_limit": "Source test retained separately; historical and cross-source checks still required.",
            "training_input": "MathDial question plus incorrect student attempt; NEVER ground_truth.",
        },
        "sources": {},
    }
    all_rows = []
    for source, partitions in sources.items():
        info = license_evidence(source, data_root / source / "raw")
        rows = normalize_source(source, partitions, info)
        all_rows.extend(rows)
        admitted = [r for r in rows if r["eligibility"] in {"candidate_train", "source_test_only"}]
        outputs = {}
        for kind, selected in {
            "normalized": admitted,
            "quarantine": [r for r in rows if r["eligibility"] == "quarantine"],
            "excluded": [r for r in rows if r["eligibility"] == "excluded"],
        }.items():
            outputs[kind] = write_jsonl(data_root / source / f"{kind}.jsonl", selected)
        manifest["sources"][source] = {
            "pin": PINS[source],
            "license": info,
            "raw_partition_rows": {key: len(value) for key, value in partitions.items()},
            "eligibility_counts": dict(Counter(row["eligibility"] for row in rows)),
            "candidate_train_groups": len(
                {r["group_id"] for r in rows if r["eligibility"] == "candidate_train"}
            ),
            "source_test_groups": len(
                {r["group_id"] for r in rows if r["eligibility"] == "source_test_only"}
            ),
            "reason_counts": dict(
                Counter(
                    reason
                    for row in rows
                    for reason in row["exclusion_reasons"] + row["quarantine_reasons"]
                )
            ),
            "candidate_assistant_turns": sum(
                m["role"] == "assistant"
                for r in rows
                if r["eligibility"] == "candidate_train"
                for m in r["messages"]
            ),
            "outputs": outputs,
        }
    packet = audit_sample(all_rows)
    manifest["audit_packet"] = write_jsonl(provenance / "dialogues-audit-packet.jsonl", packet)
    save_json(provenance / "dialogues-manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--provenance", type=Path, default=DEFAULT_PROVENANCE)
    parser.add_argument("--download-only", action="store_true")
    args = parser.parse_args()
    for source in PINS:
        receipt = acquire_source(source, args.data_root, args.provenance)
        print(canonical_json({"source": source, "downloaded_files": len(receipt["artifacts"])}))
    if not args.download_only:
        manifest = normalize_all(args.data_root, args.provenance)
        print(
            canonical_json(
                {
                    source: value["eligibility_counts"]
                    for source, value in manifest["sources"].items()
                }
            )
        )


if __name__ == "__main__":
    main()
