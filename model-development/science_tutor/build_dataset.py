"""Assemble source-screened conversations without claiming semantic verification.

This builds a candidate, not an admission receipt. Source/content review and a
tokenizer preflight are separate gates before any training launch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SEED = 3407


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize(text):
    return " ".join(re.findall(r"[\w]+", unicodedata.normalize("NFKC", text).casefold()))


def problem_text(row):
    value = row.get("question") or row.get("problem") or row.get("prompt")
    if isinstance(value, str) and value.strip():
        choices = row.get("choices", [])
        return value + ("\n" + "\n".join(str(x) for x in choices) if choices else "")
    return next(m["content"] for m in row["messages"] if m["role"] == "user")


def group_question(row):
    # SciQ restates the same specific question with different distractors across
    # original splits. ScienceQA has generic stems needing choices for identity.
    if row["source"] == "sciq":
        return row["question"]
    return problem_text(row)


def student_texts(row):
    return list(
        dict.fromkeys(
            [group_question(row), problem_text(row)]
            + [m["content"] for m in row["messages"] if m["role"] == "user"]
        )
    )


def index_row(index, row):
    keys = []
    for position, text in enumerate(student_texts(row)):
        key = f"{row['id']}:student-text:{position}"
        index.add(key, text)
        keys.append(key)
    return keys


def reviewed_policy(path):
    """Bind ID allowlists to verified review decisions and exact raw-row bytes."""
    if not path:
        return {}, {}
    policy = json.loads(path.read_text())
    reviewed = {}
    for ref in policy.get("review_receipts", []):
        receipt_path = path.parent / ref["path"]
        if file_hash(receipt_path) != ref["sha256"]:
            raise ValueError("content review receipt hash mismatch")
        receipt = json.loads(receipt_path.read_text())
        for items in receipt.values():
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                decision = item.get("decision", item.get("verdict", ""))
                if decision in (
                    "acceptable_bounded_review",
                    "acceptable_bounded_independent_agent_content_review",
                ):
                    key, sha = item["id"], item["row_canonical_sha256"]
                    if key in reviewed and reviewed[key] != sha:
                        raise ValueError("conflicting raw-row review hashes")
                    reviewed[key] = sha
    for source, ids in policy.get("require_reviewed_ids_for_sources", {}).items():
        if len(ids) != len(set(ids)) or any(key not in reviewed for key in ids):
            raise ValueError(f"review allowlist lacks exact reviewed row: {source}")
    return policy, reviewed


def shingles(text):
    words = normalize(text).split()
    return {tuple(words[i : i + 5]) for i in range(max(0, len(words) - 4))}


class NearIndex:
    """Conservative lexical screening; not proof of semantic/family exclusion."""

    def __init__(self):
        self.exact = defaultdict(set)
        self.items = {}
        self.postings = defaultdict(set)

    def add(self, key, text):
        normalized = normalize(text)
        if not normalized:
            return
        self.exact[normalized].add(key)
        grams = shingles(text)
        self.items[key] = grams
        for gram in grams:
            self.postings[gram].add(key)

    def matches(self, text):
        hits = set(self.exact.get(normalize(text), ()))
        grams = shingles(text)
        if len(grams) < 4:
            return sorted(hits)
        counts = Counter(key for gram in grams for key in self.postings.get(gram, ()))
        for key, shared in counts.items():
            other = self.items[key]
            # Containment flags questions embedded inside instruction wrappers.
            if len(other) >= 4 and shared >= 4 and shared / min(len(grams), len(other)) >= 0.82:
                hits.add(key)
        return sorted(hits)


def validate(row):
    for key in ("id", "group_id", "source", "source_id", "source_revision", "license", "subject"):
        if not isinstance(row.get(key), str) or not row[key].strip():
            raise ValueError(f"missing_or_invalid_{key}")
    if not isinstance(row.get("quality"), dict):
        raise ValueError("missing_quality_tier")  # noqa: TRY004 - a row validation failure
    if not isinstance(row.get("capabilities"), list):
        raise ValueError("missing_capabilities")  # noqa: TRY004 - a row validation failure
    messages = row.get("messages")
    if not isinstance(messages, list) or len(messages) < 2:
        raise ValueError("missing_messages")
    index = 1 if messages[0].get("role") == "system" else 0
    turns = messages[index:]
    if len(turns) % 2:
        raise ValueError("incomplete_conversation")
    for i, message in enumerate(turns):
        if message.get("role") != ("user" if i % 2 == 0 else "assistant"):
            raise ValueError("nonalternating_roles")
    for message in messages:
        if not isinstance(message.get("content"), str) or not message["content"].strip():
            raise ValueError("empty_message")
        if any(x in message["content"] for x in ("<|im_start|>", "<|im_end|>")):
            raise ValueError("embedded_chat_control_token")


def training_view(row):
    """Preserve source evidence for a final learner turn with no teacher target."""
    row = dict(row)
    messages = row.get("messages")
    if isinstance(messages, list) and len(messages) >= 3 and messages[-1].get("role") == "user":
        row["source_messages_sha256"] = digest(canonical(messages))
        row["unsupervised_trailing_student_turn"] = messages[-1]
        row["training_transformations"] = [
            {
                "kind": "omit_terminal_student_turn_without_teacher_target",
                "source_turn_sha256": digest(canonical(messages[-1])),
            }
        ]
        row["messages"] = messages[:-1]
    if row.get("source") == "sciq":
        row["source_messages_sha256"] = digest(canonical(row["messages"]))
        row["messages"] = [dict(m) for m in row["messages"]]
        row["messages"][0]["content"] = row["messages"][0]["content"].replace(
            "Answer the question and give a brief scientific explanation.",
            "Choose the best option; give the option letter and answer text only.",
        )
        row["messages"][1]["content"] = f"{chr(65 + row['answer_index'])}. {row['answer']}"
        row["training_transformations"] = [
            {"kind": "answer_key_only_no_support_passage_supervision"}
        ]
        row["quality"] = dict(
            row["quality"],
            tier="source_mc_answer_key_only_screened",
            independent_verification=False,
        )
        row["capabilities"] = ["scientific_knowledge_mc", "concise_instruction_following"]
    if row.get("source") == "scienceqa":
        cleanups = {
            "Read the underlined text carefully.": "Read the relevant passage carefully.",
            "The underlined text tells you": "The passage tells you",
            "They are not physical changes.": "They are not only physical changes.",
            "This organism is not photosynthetic:\nThe text does not provide evidence": "The text does not identify this organism as photosynthetic:\nThe text does not provide evidence",
        }
        original = row["messages"][1]["content"]
        revised = original
        applied = []
        for old, new in cleanups.items():
            if old in revised:
                revised = revised.replace(old, new)
                applied.append({"before": old, "after": new})
        if applied:
            row["messages"] = [dict(m) for m in row["messages"]]
            row["messages"][1]["content"] = revised
            row["training_transformations"] = [
                {
                    "kind": "reviewed_scienceqa_scope_and_plaintext_repair",
                    "original_target_sha256": digest(original),
                    "revised_target_sha256": digest(revised),
                    "replacements": applied,
                }
            ]
    return row


def source_split(row):
    value = row.get("source_split", row.get("original_split", "train"))
    if value in ("validation", "val", "dev"):
        return "dev"
    if value == "test":
        return "holdout"
    if value not in ("train", "unspecified", "unknown", "all", "authored_unsplit"):
        raise ValueError("unsupported_source_split")
    return "train"


class Union:
    def __init__(self):
        self.parent = {}

    def find(self, item):
        self.parent.setdefault(item, item)
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def join(self, a, b):
        a, b = self.find(a), self.find(b)
        self.parent[max(a, b)] = min(a, b)


def group_rows(rows):
    """Co-group exact question matches even if providers use different IDs."""
    union = Union()
    seen = {}
    for row in rows:
        group = f"{row['source']}:{row['group_id']}"
        key = normalize(group_question(row))
        if key in seen:
            union.join(group, seen[key])
        seen[key] = group
        union.find(group)
    groups = defaultdict(list)
    for row in rows:
        group = union.find(f"{row['source']}:{row['group_id']}")
        row["original_group_id"] = row["group_id"]
        row["group_id"] = "st-group-" + digest(group)[:24]
        groups[row["group_id"]].append(row)
    return groups


def known_index(repo):
    sys.path.insert(0, str(repo))
    from bench.judges_prompt_suite import prompts as judges
    from bench.stem_prompt_suite import prompts as stem

    index = NearIndex()
    for row in [*judges(), *stem()]:
        index.add(f"known:{row.id}", row.text)
    path = repo / "provenance/evaluation/practical-winner-2000-20260919/battery.json"
    battery = json.loads(path.read_text())
    for row in battery["items"]:
        index.add(f"practical:{row['id']}", row["problem"])
    return index, {
        "known_judges": len(judges()),
        "known_stem": len(stem()),
        "practical": len(battery["items"]),
        "battery_sha256": file_hash(path),
    }


def choose_groups(groups, caps):
    """Deterministic bounded pilot subset; don't split a question's dialogues."""
    selected, reserved, counts = [], [], Counter()
    for group, rows in sorted(groups.items(), key=lambda x: digest(f"{SEED}:{x[0]}")):
        additions = Counter(r["source"] for r in rows)
        if any(counts[s] + n > caps.get(s, 1000000) for s, n in additions.items()):
            reserved.extend(rows)
        else:
            selected.extend(rows)
            counts.update(additions)
    return selected, reserved


def stats(rows):
    return {
        "rows": len(rows),
        "unique_groups": len({r["group_id"] for r in rows}),
        "assistant_turns": sum(sum(m["role"] == "assistant" for m in r["messages"]) for r in rows),
        "multi_turn_rows": sum(
            sum(m["role"] == "assistant" for m in r["messages"]) > 1 for r in rows
        ),
        "sources": dict(Counter(r["source"] for r in rows)),
        "subjects": dict(Counter(r["subject"] for r in rows)),
        "capabilities": dict(Counter(c for r in rows for c in r["capabilities"])),
        "row_ids_sha256": digest(canonical(sorted(r["id"] for r in rows))),
        "sequence_tokens": sum(r.get("tokenization", {}).get("sequence_tokens", 0) for r in rows),
        "trainable_tokens": sum(r.get("tokenization", {}).get("trainable_tokens", 0) for r in rows),
        "tokenized_rows": sum("tokenization" in r for r in rows),
    }


def write_json(path, value):
    with path.open("x") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def write_rows(path, rows):
    with path.open("xb") as handle:
        for row in rows:
            handle.write(canonical(row) + b"\n")
    return {
        "path": str(path.resolve()),
        "sha256": file_hash(path),
        "bytes": path.stat().st_size,
        **stats(rows),
    }


def historical_screen(partitions, repo, excluded):
    """Exclude new eval groups matching any accessible prior model-stage input."""
    refs = []
    for manifest_path, expected in [
        (
            repo / "data/muta-stem-v2-sft-300k-quality-first-20260917-v1/manifest.json",
            "93b7dbcbad72350e099d8951effcbc9a253693dc364b25ffc165102a6e844f4e",
        ),
        (
            repo / "provenance/dataset/round2-dev-5000/manifest.json",
            "2bbde7545eef5ddd531705e6e71ebc09321e3c7bfbb371ec89ed471696dda301",
        ),
    ]:
        if file_hash(manifest_path) != expected:
            raise ValueError("historical manifest hash mismatch")
        manifest = json.loads(manifest_path.read_text())
        for shard in manifest["shards"]:
            refs.append({"path": manifest_path.parent / shard["path"], "sha256": shard["sha256"]})
    for name, expected in [
        ("incumbent_train", "0d1b52db8dc0785fe8c0b62cbe374e79c35192b9ccd7fe86480c998808c3734c"),
        ("incumbent_dev", "fd48e23f20afb5ae8986730b19cb42523610cd0620e71021e9e2e8aa99dbf69b"),
    ]:
        refs.append(
            {
                "path": repo / f"data/muta-science-tutor-20260919/history/{name}.jsonl",
                "sha256": expected,
            }
        )
    index, lookup = NearIndex(), {}
    for split in ("dev", "holdout"):
        for group, members in partitions[split].items():
            for row in members:
                for key in index_row(index, row):
                    lookup[key] = (split, group, row["id"])
    flagged, events, scanned = set(), [], 0
    for ref in refs:
        if file_hash(ref["path"]) != ref["sha256"]:
            raise ValueError("historical shard hash mismatch")
        with ref["path"].open() as handle:
            for line_number, line in enumerate(handle, 1):
                row = json.loads(line)
                prompt = row.get("prompt")
                if not isinstance(prompt, str):
                    raise ValueError("historical row lacks a prompt")  # noqa: TRY004
                for hit in index.matches(prompt):
                    split, group, candidate_id = lookup[hit]
                    flagged.add((split, group))
                    if len(events) < 10000:
                        events.append(
                            {
                                "candidate_id": candidate_id,
                                "candidate_text_key": hit,
                                "split": split,
                                "group_id": group,
                                "history_path": str(ref["path"]),
                                "line": line_number,
                                "history_prompt_sha256": digest(prompt),
                            }
                        )
                scanned += 1
        print(
            json.dumps({"history_rows_screened": scanned, "flagged_eval_groups": len(flagged)}),
            flush=True,
        )
    for split, group in sorted(flagged):
        members = partitions[split].pop(group)
        excluded.extend(
            {"id": r["id"], "reason": "prior_model_input_lexical_overlap", "group_id": group}
            for r in members
        )
    return {
        "rows_screened": scanned,
        "flagged_groups": len(flagged),
        "events": events,
        "files": [{"path": str(r["path"]), "sha256": r["sha256"]} for r in refs],
        "scope": "300350 selected train + 5000 development + exact incumbent train/development; not unknown pretraining or unused warehouse",
        "method": "normalized exact + five-gram containment at0.82; not semantic or whole-family clearance",
    }


def build(args):
    block_path = getattr(args, "blocklist", None)
    blocked, reviewed_hashes = reviewed_policy(block_path)
    args.output.mkdir(parents=True, exist_ok=False)
    known, known_receipt = known_index(args.repo)
    rows, excluded, inputs, ids = [], [], [], set()
    known_matches = {}
    blocked_groups = set(blocked.get("groups", []))
    blocked_ids = set(blocked.get("ids", []))
    whitelist = blocked.get("require_reviewed_ids_for_sources", {})
    tokenizer = None
    if getattr(args, "tokenizer", None):
        from tokenization import tokenize_messages
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, local_files_only=True)
    for path in args.sources:
        inputs.append({"path": str(path.resolve()), "sha256": file_hash(path)})
        with path.open() as handle:
            for line_number, line in enumerate(handle, 1):
                raw_row = json.loads(line)
                raw_sha = digest(canonical(raw_row))
                if (
                    raw_row.get("id") in reviewed_hashes
                    and raw_sha != reviewed_hashes[raw_row["id"]]
                ):
                    raise ValueError("reviewed raw-row hash mismatch")
                row = training_view(raw_row)
                row["raw_source_row_sha256"] = raw_sha
                if row["id"] in reviewed_hashes:
                    row["exact_content_review_sha256"] = reviewed_hashes[row["id"]]
                try:
                    validate(row)
                    eligibility = row.get("eligibility", "candidate_train")
                    authored_reviewed = (
                        eligibility == "candidate_pending_review"
                        and row["source"] == "muta_authored_science"
                        and row["id"] in whitelist.get(row["source"], [])
                    )
                    if (
                        (
                            eligibility not in ("candidate_train", "source_test_only")
                            and not authored_reviewed
                        )
                        or row.get("quarantine_reasons")
                        or row.get("exclusion_reasons")
                    ):
                        raise ValueError("source_not_eligible")
                    if row["id"] in ids:
                        raise ValueError("duplicate_source_id")
                    ids.add(row["id"])
                    known_matches[row["id"]] = sorted(
                        {hit for text in student_texts(row) for hit in known.matches(text)}
                    )
                    source_split(row)
                    rows.append(row)
                except ValueError as error:
                    excluded.append(
                        {
                            "id": row.get("id"),
                            "source_file": str(path),
                            "line": line_number,
                            "reason": str(error),
                        }
                    )
    groups = group_rows(rows)
    partitions = {"train": {}, "dev": {}, "holdout": {}}
    for group, members in groups.items():
        splits = {source_split(row) for row in members}
        # Original held-out status takes precedence for the WHOLE group.
        split = "holdout" if "holdout" in splits else "dev" if "dev" in splits else "train"
        if split == "train" and not any(
            r.get("known_prior_training_exposure") or r["source"] == "muta_authored_science"
            for r in members
        ):
            bucket = int(digest(f"{SEED}:split:{group}")[:8], 16) % 100
            split = "holdout" if bucket < 5 else "dev" if bucket < 10 else "train"
        if split != "train" and any(r.get("known_prior_training_exposure") for r in members):
            excluded.extend(
                {"id": r["id"], "reason": "prior_training_exposure_in_evaluation_group"}
                for r in members
            )
            continue
        matches = sorted({m for row in members for m in known_matches[row["id"]]})
        rejected = {r["original_group_id"] for r in members} & blocked_groups
        if matches or rejected:
            reason = (
                "known_evaluation_group_overlap" if matches else "content_review_group_quarantine"
            )
            excluded.extend(
                {
                    "id": r["id"],
                    "reason": reason,
                    "matches": matches,
                    "blocked_groups": sorted(rejected),
                }
                for r in members
            )
            continue
        seen_content, unique = set(), []
        priority = {"holdout": 0, "dev": 1, "train": 2}
        for row in sorted(members, key=lambda r: (priority[source_split(r)], r["id"])):
            if row["id"] in blocked_ids or (
                row["source"] in whitelist and row["id"] not in whitelist[row["source"]]
            ):
                excluded.append(
                    {
                        "id": row["id"],
                        "reason": "content_review_pending_or_flagged",
                        "group_id": group,
                    }
                )
                continue
            if tokenizer:
                try:
                    encoded = tokenize_messages(
                        row["messages"], tokenizer=tokenizer, max_length=args.max_length
                    )
                    row["tokenization"] = {
                        k: encoded[k]
                        for k in (
                            "sequence_tokens",
                            "trainable_tokens",
                            "assistant_turns",
                            "messages_sha256",
                            "input_ids_sha256",
                            "labels_sha256",
                        )
                    }
                except ValueError as error:
                    excluded.append(
                        {
                            "id": row["id"],
                            "reason": "tokenization_quarantine",
                            "detail": str(error),
                            "group_id": group,
                        }
                    )
                    continue
            content_hash = digest(canonical(row["messages"]))
            if content_hash in seen_content:
                excluded.append(
                    {"id": row["id"], "reason": "duplicate_conversation", "group_id": group}
                )
                continue
            seen_content.add(content_hash)
            unique.append(row)
        if unique:
            partitions[split][group] = unique
    history = (
        historical_screen(partitions, args.repo, excluded)
        if getattr(args, "history", False)
        else None
    )
    holdout_index = NearIndex()
    for members in partitions["holdout"].values():
        for row in members:
            index_row(holdout_index, row)
    for group, members in list(partitions["dev"].items()):
        matches = sorted(
            {
                hit
                for row in members
                for text in student_texts(row)
                for hit in holdout_index.matches(text)
            }
        )
        if matches:
            del partitions["dev"][group]
            excluded.extend(
                {"id": r["id"], "reason": "holdout_development_near_overlap", "matches": matches}
                for r in members
            )
    # No exact/near question match from training into either new evaluation set.
    eval_index = NearIndex()
    for split in ("dev", "holdout"):
        for group, members in partitions[split].items():
            for row in members:
                index_row(eval_index, row)
    for group, members in list(partitions["train"].items()):
        matches = sorted(
            {
                hit
                for row in members
                for text in student_texts(row)
                for hit in eval_index.matches(text)
            }
        )
        if matches:
            del partitions["train"][group]
            excluded.extend(
                {"id": r["id"], "reason": "new_evaluation_near_overlap", "matches": matches}
                for r in members
            )
    caps = dict(pair.split("=", 1) for pair in args.cap)
    caps = {key: int(value) for key, value in caps.items()}
    pilot, reserve = choose_groups(partitions["train"], caps)
    artifacts = {"train": pilot, "expansion_reserve": reserve}
    for split in ("dev", "holdout"):
        artifacts[split] = [r for members in partitions[split].values() for r in members]
    receipts = {
        name: write_rows(args.output / f"{name}.jsonl", value) for name, value in artifacts.items()
    }
    with (args.output / "exclusions.jsonl").open("x") as handle:
        for value in excluded:
            handle.write(json.dumps(value, sort_keys=True) + "\n")
    manifest = {
        "schema_version": 1,
        "status": "candidate_not_training_admitted",
        "seed": SEED,
        "inputs": inputs,
        "known_evaluations": known_receipt,
        "content_blocklist": {"path": str(block_path), "sha256": file_hash(block_path)}
        if block_path
        else None,
        "historical_overlap": history,
        "splits": receipts,
        "pilot_source_caps": caps,
        "exclusion_counts": dict(Counter(x["reason"] for x in excluded)),
        "pending_gates": (
            [] if history is not None else ["historical_training_overlap_screen_for_new_holdout"]
        )
        + ([] if tokenizer else ["whole_conversation_tokenizer_preflight"])
        + [
            "independent_pipeline_review",
            "stratified_semantic_content_audit",
            "evaluation_answer_rubric_verification",
        ],
        "limitations": [
            "Source keys and silver labels are not independent verification.",
            "Lexical five-gram screening does not establish semantic/family independence.",
            "Capability labels describe declared tasks, not demonstrated model performance.",
            "Original base-model pretraining contamination is unknown.",
        ],
    }
    write_json(args.output / "manifest.json", manifest)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "status": manifest["status"],
                "counts": {k: v["rows"] for k, v in receipts.items()},
                "exclusions": manifest["exclusion_counts"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--sources", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cap", action="append", default=[])
    parser.add_argument("--blocklist", type=Path)
    parser.add_argument("--tokenizer", type=Path)
    parser.add_argument("--max-length", type=int, default=4096)
    parser.add_argument("--history", action="store_true")
    build(parser.parse_args())
