"""Pinned text-only science source ingestion; no claim of semantic row approval.

One raw copy is cached per source. Source partitions are retained and source test
rows are never relabelled as training. This adapter emits candidates, not an
integrated training manifest. Run with ``uv run --with pyarrow ...`` for SciQ.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

PINS = {
    "scienceqa": "2cbf8318e07b9ece895bb2ae605e71e38d623264",
    "sciq": "2c94ad3e1aafab77146f384e23536f97a4849815",
    "sciinstruct": "098a7e88a9385dd170f78ed9edbce2c1b130cf81",
}
LICENSES = {"scienceqa": "CC-BY-NC-SA-4.0", "sciq": "CC-BY-NC-3.0", "sciinstruct": "CC-BY-4.0"}
FILES = {
    "scienceqa": {
        name: f"https://raw.githubusercontent.com/lupantech/ScienceQA/{PINS['scienceqa']}/{remote}"
        for name, remote in {
            "problems.json": "data/scienceqa/problems.json",
            "README.md": "README.md",
            "LICENSE-DATA": "LICENSE-DATA",
        }.items()
    },
    "sciq": {
        name: f"https://huggingface.co/datasets/allenai/sciq/resolve/{PINS['sciq']}/{remote}"
        for name, remote in {
            "train.parquet": "data/train-00000-of-00001.parquet",
            "validation.parquet": "data/validation-00000-of-00001.parquet",
            "test.parquet": "data/test-00000-of-00001.parquet",
            "README.md": "README.md",
        }.items()
    },
    "sciinstruct": {
        name: f"https://huggingface.co/datasets/zd21/SciInstruct/resolve/{PINS['sciinstruct']}/{name}"
        for name in ["README.md", "train_en_phy_chem.json"]
    },
}
VISUAL = re.compile(
    r"\b(?:pictures?|images?|drawings?|diagrams?|figures?|graphs?|charts?|maps?|figure\s*[0-9]|fig\.|(?:following|above|below|this|the)\s+(?:picture|image|diagram|graph|figure|map)|"
    r"(?:shown|illustrated|pictured)\s+(?:above|below|here)|refer\s+to\s+(?:the\s+)?(?:figure|diagram|table)|"
    r"look\s+at\s+(?:the\s+)?(?:picture|image|diagram|graph)|(?:chart|table)\s+(?:above|below))\b",
    re.IGNORECASE,
)
BROKEN = re.compile(
    r"<img\b|\[image\]|!\[[^\]]*\]\(|\ufffd|(?:https?://)\S+\.(?:png|jpg|jpeg)", re.IGNORECASE
)
ADVANCED = re.compile(
    r"\b(?:hamiltonian|lagrangian|schrodinger|schrödinger|hilbert|bra[- ]ket|eigenstate|"
    r"quantum field|path integral|partition function|tensor field|dirac|density matrix|"
    r"canonical transformation|variational principle|perturbation theory|feynman|"
    r"wavefunction|wave function|spherical harmonics|creation operator|annihilation operator)\b",
    re.IGNORECASE,
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def dump_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def read_source_json(value: bytes | str) -> object:
    """Pinned SciInstruct has a .json suffix but newline-delimited objects."""
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        decoded = value.decode("utf-8") if isinstance(value, bytes) else value
        lines = [json.loads(line) for line in decoded.splitlines() if line.strip()]
        if not lines or not all(isinstance(row, dict) for row in lines):
            raise ValueError("not a valid JSON object/array or JSON Lines object stream")
        return lines


def verify_raw_inputs(source: str, root: Path, receipts: Path) -> list[dict]:
    """Both online and offline normalization require preserved acquisition bytes."""
    acquisition = json.loads((receipts / "science-downloads.json").read_text())
    entries = {(r["source"], Path(r["path"]).name): r for r in acquisition["files"]}
    checked = []
    for name, url in FILES[source].items():
        entry = entries.get((source, name))
        if entry is None or entry["url"] != url or entry["revision"] != PINS[source]:
            raise ValueError("missing or mismatched pinned acquisition receipt")
        path = root / source / name
        value = path.read_bytes()
        if sha256_bytes(value) != entry["sha256"] or len(value) != entry["bytes"]:
            raise ValueError("raw source bytes changed since acquisition")
        checked.append({"path": str(path), "url": url, "sha256": entry["sha256"], "bytes": len(value)})
    return checked


def text(value: object) -> str:
    return re.sub(r"[ \t]+", " ", str(value or "").replace("\r\n", "\n")).strip()


def fetch_one(source: str, name: str, url: str, root: Path) -> dict:
    path = root / source / name
    path.parent.mkdir(parents=True, exist_ok=True)
    downloaded = not path.exists()
    if downloaded:
        req = urllib.request.Request(url, headers={"User-Agent": "Muta-science-tutor-research/1.0"})
        # Only an exact pinned URL is requested. No credentials are used.
        with urllib.request.urlopen(req, timeout=60) as response:
            value = response.read(150_000_001)
        if len(value) > 150_000_000:
            raise ValueError(f"unexpectedly large source: {source}/{name}")
        path.write_bytes(value)
    else:
        value = path.read_bytes()
    if name.endswith(".json"):
        read_source_json(value)
    if (
        source == "sciinstruct"
        and name == "train_en_phy_chem.json"
        and sha256_bytes(value)
        != "ebfe39cd940bcddd3bf9b960b83c55a86a5df273e5b9481e919320ba79b62d11"
    ):
        raise ValueError("SciInstruct bytes disagree with pinned upstream LFS SHA256")
    return {
        "source": source,
        "revision": PINS[source],
        "url": url,
        "path": str(path),
        "bytes": len(value),
        "sha256": sha256_bytes(value),
        "downloaded_this_run": downloaded,
    }


def base_row(
    source: str,
    source_id: str,
    split: str,
    question: str,
    answer: str,
    explanation: str,
    subject: str,
    choices: list[str] | None = None,
    answer_index: int | None = None,
) -> dict:
    prompt = question
    if choices:
        prompt += "\n\n" + "\n".join(f"{chr(65 + i)}. {choice}" for i, choice in enumerate(choices))
    prompt += "\n\nAnswer the question and give a brief scientific explanation."
    label = f"{chr(65 + answer_index)}. " if answer_index is not None else ""
    completion = f"{label}{answer}\n\n{explanation}"
    return {
        "id": f"{source}:{source_id}",
        "group_id": f"{source}:{source_id}",
        "source": source,
        "source_revision": PINS[source],
        "source_id": source_id,
        "source_split": split,
        "license": LICENSES[source],
        "subject": subject,
        "capabilities": ["conceptual_understanding", "accessible_communication"],
        "quality": {
            "tier": "source_answer_and_explanation_screened",
            "independent_check": False,
            "independent_verification": False,
            "checks": [
                "nonempty_answer_and_explanation",
                "text_dependency_screen",
                "original_partition_retained",
            ],
            "limitations": [
                "Source answer and explanation are not independently verified for every row.",
                "Text dependency screening is conservative but cannot guarantee absence of implicit missing context.",
            ],
        },
        "messages": [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": completion},
        ],
        "question": question,
        "answer": answer,
        "choices": choices or [],
        "answer_index": answer_index,
    }


def normalize_scienceqa(source_id: str, item: dict) -> tuple[dict | None, str | None]:
    if item.get("subject") != "natural science":
        return None, "not_natural_science"
    if item.get("image"):
        return None, "image_present"
    question, hint, lecture, solution = [
        text(item.get(k)) for k in ["question", "hint", "lecture", "solution"]
    ]
    choices = [text(c) for c in item.get("choices", [])]
    index = item.get("answer")
    if (
        not question
        or not 2 <= len(choices) <= 10
        or not all(choices)
        or len(set(choices)) != len(choices)
    ):
        return None, "invalid_question_or_choices"
    if type(index) is not int or not 0 <= index < len(choices):
        return None, "invalid_answer_index"
    if item.get("split") not in {"train", "val", "test"}:
        return None, "invalid_split"
    combined = "\n".join([question, hint, lecture, solution, *choices])
    if VISUAL.search(combined) or BROKEN.search(combined):
        return None, "visual_or_broken_text_dependency"
    skill = text(item.get("skill"))
    # Root's independent 45-item audit found systematic explanatory defects.
    # Exclude the entire matching source families, not just inspected instances.
    if skill in {"Identify rocks using properties", "Identify minerals using properties"}:
        return None, "reviewed_family_rock_mineral_overgeneralization"
    if skill == "How do mass and force affect motion?":
        return None, "reviewed_family_force_without_acceleration_assumptions"
    if "copper" in combined.casefold() and "green" in combined.casefold():
        return None, "reviewed_family_green_copper_chemistry"
    if "silver" in combined.casefold() and re.search(r"polish|tarnish", combined, re.IGNORECASE):
        return None, "reviewed_family_ambiguous_silver_polishing"
    if not solution or len(solution.split()) < 8:
        return None, "missing_substantive_solution"
    # Lecture is explanatory source text, never presented as part of the question.
    explanation = (
        solution
        if len(solution.split()) >= 20
        else "\n\n".join(p for p in [lecture, solution] if p)
    )
    if len(explanation) > 6500:
        return None, "explanation_too_long"
    question_with_context = f"{hint}\n\n{question}" if hint else question
    topic = text(item.get("topic"))
    subject = {
        "biology": "biology",
        "chemistry": "chemistry",
        "physics": "physics",
        "earth-science": "earth_environmental_science",
    }.get(topic, "integrated_science")
    row = base_row(
        "scienceqa",
        source_id,
        item["split"],
        question_with_context,
        choices[index],
        explanation,
        subject,
        choices,
        index,
    )
    row["source_metadata"] = {
        k: item.get(k) for k in ["grade", "topic", "category", "skill", "task"]
    }
    row["source_solution"] = solution
    row["source_lecture"] = lecture
    return row, None


def infer_sciq_subject(content: str) -> str:
    # These are conservative lexical metadata labels, not source-supplied taxonomy.
    groups = {
        "biology": r"\b(cell|cells|organism|organisms|dna|rna|gene|genes|protein|plant|plants|animal|animals|bacteria|photosynthesis|blood|evolution)\b",
        "chemistry": r"\b(atom|atoms|element|elements|compound|compounds|molecule|molecules|chemical|acid|base|ionic|covalent|electron|electrons|proton|protons)\b",
        "earth_environmental_science": r"\b(earth|planet|planets|rock|rocks|atmosphere|weather|climate|ocean|tectonic|erosion|sediment|volcano|star|stars|galaxy)\b",
        "physics": r"\b(force|energy|motion|velocity|acceleration|gravity|electrical|electricity|magnetic|wave|waves|heat|light|sound|pressure|momentum)\b",
    }
    counts = {
        key: len(re.findall(pattern, content, flags=re.IGNORECASE))
        for key, pattern in groups.items()
    }
    best = max(counts, key=counts.get)
    return best if counts[best] else "integrated_science"


def normalize_sciq(split: str, number: int, item: dict) -> tuple[dict | None, str | None]:
    question, answer, support = [
        text(item.get(k)) for k in ["question", "correct_answer", "support"]
    ]
    choices = [answer] + [text(item.get(f"distractor{i}")) for i in range(1, 4)]
    if not question or not answer or not all(choices) or len({c.casefold() for c in choices}) != 4:
        return None, "invalid_question_or_choices"
    if split not in {"train", "validation", "test"}:
        return None, "invalid_split"
    if len(support.split()) < 12 or len(support) > 5000:
        return None, "missing_or_long_explanatory_support"
    if VISUAL.search("\n".join([question, support, *choices])) or BROKEN.search(
        "\n".join([question, support, *choices])
    ):
        return None, "visual_or_broken_text_dependency"
    # Support must literally ground the keyed concept. It is labelled source
    # support, not a newly asserted verified derivation from a teacher model.
    if answer.casefold() not in support.casefold():
        return None, "answer_not_literal_in_support"
    source_id = f"{split}:{number}"
    rotation = int(sha256_bytes(source_id.encode())[:8], 16) % 4
    choices = choices[rotation:] + choices[:rotation]
    index = choices.index(answer)
    row = base_row(
        "sciq", source_id, split, question, answer, support, "science_unspecified", choices, index
    )
    row["quality"]["checks"].append("answer_literal_in_source_support")
    row["quality"]["limitations"].append(
        "Support passage may contain facts beyond the shortest needed explanation."
    )
    row["source_metadata"] = {
        "subject_assignment": "not_authoritatively_supplied",
        "subject_hint_heuristic": infer_sciq_subject(question + " " + support),
    }
    return row, None


def normalize_sciinstruct(number: int, item: dict) -> tuple[dict | None, str | None]:
    question = text(item.get("content"))
    explanation = text(item.get("summary"))
    subject = text(item.get("subject")).casefold()
    if subject not in {"physics", "chemistry", "physics_chemistry"}:
        return None, "subject_not_physics_or_chemistry"
    if not 30 <= len(question) <= 2400 or not 80 <= len(explanation) <= 6500:
        return None, "length_outside_pilot_bounds"
    combined = question + "\n" + explanation
    if re.search(r"[\u4e00-\u9fff]", combined):
        return None, "non_english_text"
    if VISUAL.search(combined) or BROKEN.search(combined):
        return None, "visual_or_broken_text_dependency"
    if ADVANCED.search(combined):
        return None, "advanced_topic_outside_school_pilot"
    if re.search(
        r"\b(?:cannot (?:be )?(?:answer|determin)|not enough information|need more information|as an ai)\b",
        explanation,
        re.IGNORECASE,
    ):
        return None, "unresolved_source_answer"
    # SciInstruct summary has no separately keyed verified answer. Keep a separate
    # tier so integration cannot silently treat synthetic text as ground truth.
    row = base_row("sciinstruct", str(number), "train", question, "", explanation, subject)
    row["messages"][1]["content"] = explanation
    row["answer"] = None
    row["quality"]["tier"] = "synthetic_source_explanation_unverified"
    row["quality"]["admission"] = "quarantine_until_independent_answer_verification"
    row["quality"]["checks"] = [
        "length_and_language_screen",
        "text_dependency_screen",
        "school_topic_exclusion_heuristic",
    ]
    row["quality"]["limitations"] += [
        "No separate answer key; synthetic explanation may contain unsupported claims or errors.",
        "Curriculum fit is a heuristic, not an expert grade-level assessment.",
    ]
    return row, None


def write_candidates(
    source: str, inputs: list[tuple[str, int | str, dict]], root: Path, receipts: Path
) -> dict:
    directory = root / source
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / "normalized.jsonl"
    quarantine = directory / "quarantine-index.jsonl"
    counts: Counter = Counter()
    by_split: Counter = Counter()
    by_subject: Counter = Counter()
    audit: dict[tuple[str, str], list[dict]] = defaultdict(list)
    quarantined_screen_pass = 0
    with output.open("w") as accepted, quarantine.open("w") as rejected:
        for split, source_id, item in inputs:
            if source == "scienceqa":
                row, reason = normalize_scienceqa(str(source_id), item)
            elif source == "sciq":
                row, reason = normalize_sciq(split, int(source_id), item)
            else:
                row, reason = normalize_sciinstruct(int(source_id), item)
            if row is None:
                counts[reason] += 1
                rejected.write(
                    json.dumps(
                        {"source_id": str(source_id), "source_split": split, "reason": reason}
                    )
                    + "\n"
                )
                continue
            if source == "sciinstruct":
                # A direct source inspection already revealed a false scientific
                # claim. Screening alone must not approve the remaining targets.
                quarantined_screen_pass += 1
                counts["synthetic_answer_requires_independent_verification"] += 1
                rejected.write(
                    json.dumps(
                        {
                            "source_id": str(source_id),
                            "source_split": split,
                            "reason": "synthetic_answer_requires_independent_verification",
                        }
                    )
                    + "\n"
                )
                audit[(row["source_split"], row["subject"])].append(row)
                continue
            accepted.write(json.dumps(row, ensure_ascii=False) + "\n")
            by_split[row["source_split"]] += 1
            by_subject[row["subject"]] += 1
            key = (row["source_split"], row["subject"])
            audit[key].append(row)
    # Deterministic hash-stratified content review packet. It is NOT a completed
    # review ledger and the review status remains pending until a reviewer acts.
    packet = []
    for key in sorted(audit):
        chosen = sorted(audit[key], key=lambda row: sha256_bytes(row["id"].encode()))[:3]
        packet.extend(
            {"stratum": list(key), "review_status": "pending", "row": row} for row in chosen
        )
    packet_path = directory / "content-audit-packet.json"
    dump_json(packet_path, packet)
    receipt = {
        "source": source,
        "revision": PINS[source],
        "license": LICENSES[source],
        "normalizer_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "source_rows_examined": len(inputs),
        "candidate_rows": sum(by_split.values()),
        "candidate_rows_by_source_split": dict(sorted(by_split.items())),
        "candidate_rows_by_subject": dict(sorted(by_subject.items())),
        "unverified_synthetic_rows_passing_mechanical_screen_but_quarantined": quarantined_screen_pass,
        "excluded_rows": sum(counts.values()),
        "exclusion_reasons": dict(sorted(counts.items())),
        "normalized_path": str(output),
        "normalized_sha256": sha256_bytes(output.read_bytes()),
        "quarantine_index_path": str(quarantine),
        "quarantine_index_sha256": sha256_bytes(quarantine.read_bytes()),
        "audit_packet_path": str(packet_path),
        "audit_packet_sha256": sha256_bytes(packet_path.read_bytes()),
        "audit_packet_rows": len(packet),
        "audit_status": "pending_independent_review",
        "semantic_verification_status": "not_independently_verified_per_row",
        "integration_status": "candidates_only_not_admitted_training",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    dump_json(receipts / f"science-{source}-normalization.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", type=Path, default=Path("data/muta-science-tutor-20260919/sources")
    )
    parser.add_argument(
        "--receipts", type=Path, default=Path("provenance/science-tutor-20260919/sources")
    )
    parser.add_argument(
        "--sources", nargs="+", choices=sorted(PINS), default=["scienceqa", "sciq", "sciinstruct"]
    )
    parser.add_argument("--fetch-only", action="store_true")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    if not args.offline:
        jobs = [(s, name, url, args.root) for s in args.sources for name, url in FILES[s].items()]
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda job: fetch_one(*job), jobs))
        receipt = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "files": results,
            "code_sha256": sha256_bytes(Path(__file__).read_bytes()),
        }
        receipt_path = args.receipts / "science-downloads.json"
        if receipt_path.exists():
            existing = json.loads(receipt_path.read_text())
            old_files = {entry["path"]: entry for entry in existing["files"]}
            for entry in results:
                if (
                    entry["path"] in old_files
                    and old_files[entry["path"]]["sha256"] != entry["sha256"]
                ):
                    raise ValueError("cached source changed from preserved download receipt")
            # Preserve original successful receipt, never silently replace it.
        else:
            dump_json(receipt_path, receipt)
        print(
            json.dumps(
                {"downloaded_files": len(results), "bytes": sum(r["bytes"] for r in results)}
            ),
            flush=True,
        )
    if args.fetch_only:
        return
    for source in args.sources:
        verify_raw_inputs(source, args.root, args.receipts)
        directory = args.root / source
        if source == "scienceqa":
            data = json.loads((directory / "problems.json").read_text())
            inputs = [(v.get("split", ""), k, v) for k, v in data.items()]
        elif source == "sciq":
            import pyarrow.parquet as pq

            inputs = [
                (split, n, item)
                for split in ["train", "validation", "test"]
                for n, item in enumerate(pq.read_table(directory / f"{split}.parquet").to_pylist())
            ]
        else:
            data = read_source_json((directory / "train_en_phy_chem.json").read_text())
            inputs = [("train", n, item) for n, item in enumerate(data)]
        print(json.dumps(write_candidates(source, inputs, args.root, args.receipts)), flush=True)


if __name__ == "__main__":
    main()
