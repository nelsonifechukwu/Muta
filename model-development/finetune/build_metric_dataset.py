#!/usr/bin/env python3
"""Build a profiler-aligned, quality-filtered math and science SFT mixture."""

from __future__ import annotations

import argparse
import difflib
import json
import math
import random
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from build_dataset import (
    SEED,
    _record,
    _take_shuffled,
    _write_jsonl,
    build_african_arithmetic,
    choice_text,
    clean_gsm8k_answer,
)

SOURCE_REVISIONS = {
    "openai/gsm8k": "740312add88f781978c0658806c59bc2815b9866",
    "allenai/ai2_arc": "210d026faf9955653af8916fad021475a3f00453",
    "allenai/openbookqa": "388097ea7776314e93a529163e0fea805b8a6454",
    "allenai/qasc": "a34ba204eb9a33b919c10cc08f4f1c8dae5ec070",
    "open-r1/OpenR1-Math-220k": "e4e141ec9dea9f8326f4d347be56105859b2bd68",
}
SOURCE_LICENSES = {
    "openai/gsm8k": "MIT",
    "allenai/ai2_arc": "CC-BY-SA-4.0",
    "allenai/openbookqa": "unknown",
    "allenai/qasc": "CC-BY-4.0",
    "open-r1/OpenR1-Math-220k": "Apache-2.0",
}

MCQ_SOURCES = {
    "arc_easy_train",
    "arc_challenge_train",
    "openbookqa_train",
    "qasc_train",
}


def normalize_question(text: str) -> str:
    """Normalize text for exact and near-duplicate leakage checks."""
    text = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(re.findall(r"[a-z0-9]+", text))


def word_ngrams(text: str, width: int = 5) -> frozenset[str]:
    words = normalize_question(text).split()
    if len(words) < width:
        return frozenset({" ".join(words)}) if words else frozenset()
    return frozenset(
        " ".join(words[index : index + width]) for index in range(len(words) - width + 1)
    )


class LeakageGuard:
    """Reject exact or high-overlap copies of held-out benchmark questions."""

    def __init__(self, questions: Iterable[str], *, threshold: float = 0.8) -> None:
        self.threshold = threshold
        self.normalized: set[str] = set()
        self.texts: list[str] = []
        self.grams: list[frozenset[str]] = []
        self.index: dict[str, set[int]] = defaultdict(set)
        for question in questions:
            normalized = normalize_question(question)
            if not normalized or normalized in self.normalized:
                continue
            self.normalized.add(normalized)
            self.texts.append(normalized)
            grams = word_ngrams(question)
            doc_id = len(self.grams)
            self.grams.append(grams)
            for gram in grams:
                self.index[gram].add(doc_id)

    def matches(self, question: str) -> bool:
        normalized = normalize_question(question)
        if normalized in self.normalized:
            return True
        grams = word_ngrams(question)
        if not grams:
            return False
        candidates: set[int] = set()
        for gram in grams:
            candidates.update(self.index.get(gram, ()))
        for doc_id in candidates:
            reference = self.grams[doc_id]
            union = len(grams | reference)
            if union and len(grams & reference) / union >= self.threshold:
                return True
            if (
                difflib.SequenceMatcher(
                    None, normalized, self.texts[doc_id], autojunk=False
                ).ratio()
                >= 0.92
            ):
                return True
        return False


def _raw_mcq(*, question: str, row: dict[str, Any], source: str) -> dict[str, str]:
    # This is the exact zero-shot context shape used by lm-eval's ARC task.
    return _record(
        prompt=f"Question: {question.strip()}\nAnswer:",
        completion=choice_text(row),
        source=source,
        mode="raw",
    )


def verified_openr1_trace(row: dict[str, Any], *, max_chars: int = 4_500) -> str | None:
    """Choose the shortest complete trace that passed Math Verify."""
    generations = list(row.get("generations") or [])
    verified = list(row.get("correctness_math_verify") or [])
    complete = list(row.get("is_reasoning_complete") or [])
    traces: list[str] = []
    for trace, is_verified, is_complete in zip(generations, verified, complete):
        if not is_verified or not is_complete:
            continue
        cleaned = re.sub(r"</?think>", "", str(trace), flags=re.IGNORECASE).strip()
        if 80 <= len(cleaned) <= max_chars:
            traces.append(cleaned)
    return min(traces, key=len) if traces else None


def _heldout_questions() -> tuple[list[str], dict[str, int]]:
    from datasets import load_dataset

    questions: list[str] = []
    counts: Counter[str] = Counter()

    for config in ("ARC-Easy", "ARC-Challenge"):
        for split in ("validation", "test"):
            dataset = load_dataset(
                "allenai/ai2_arc",
                config,
                split=split,
                revision=SOURCE_REVISIONS["allenai/ai2_arc"],
            )
            values = [str(row["question"]) for row in dataset]
            questions.extend(values)
            counts[f"ai2_arc/{config}/{split}"] += len(values)

    for dataset_id, config, question_field in (
        ("allenai/openbookqa", "main", "question_stem"),
        ("allenai/qasc", None, "question"),
    ):
        for split in ("validation", "test"):
            dataset = load_dataset(
                dataset_id,
                config,
                split=split,
                revision=SOURCE_REVISIONS[dataset_id],
            )
            values = [str(row[question_field]) for row in dataset]
            questions.extend(values)
            counts[f"{dataset_id}/{split}"] += len(values)

    gsm8k = load_dataset(
        "openai/gsm8k",
        "main",
        split="test",
        revision=SOURCE_REVISIONS["openai/gsm8k"],
    )
    values = [str(row["question"]) for row in gsm8k]
    questions.extend(values)
    counts["openai/gsm8k/test"] += len(values)
    return questions, dict(sorted(counts.items()))


def _load_mcq_records(guard: LeakageGuard) -> tuple[list[dict[str, str]], Counter[str]]:
    from datasets import load_dataset

    records: list[dict[str, str]] = []
    rejected: Counter[str] = Counter()

    for config in ("ARC-Easy", "ARC-Challenge"):
        dataset = load_dataset(
            "allenai/ai2_arc",
            config,
            split="train",
            revision=SOURCE_REVISIONS["allenai/ai2_arc"],
        )
        source = f"{config.lower().replace('-', '_')}_train"
        for row in dataset:
            question = str(row["question"])
            if guard.matches(question):
                rejected[f"{source}_heldout_overlap"] += 1
                continue
            records.append(_raw_mcq(question=question, row=row, source=source))

    for dataset_id, config, question_field, source in (
        ("allenai/openbookqa", "main", "question_stem", "openbookqa_train"),
        ("allenai/qasc", None, "question", "qasc_train"),
    ):
        dataset = load_dataset(
            dataset_id,
            config,
            split="train",
            revision=SOURCE_REVISIONS[dataset_id],
        )
        for row in dataset:
            question = str(row[question_field])
            if guard.matches(question):
                rejected[f"{source}_heldout_overlap"] += 1
                continue
            records.append(_raw_mcq(question=question, row=row, source=source))

    return records, rejected


def _load_reasoning_records(
    guard: LeakageGuard,
    *,
    gsm8k_limit: int,
    openr1_limit: int,
) -> tuple[list[dict[str, str]], Counter[str]]:
    from datasets import load_dataset

    records: list[dict[str, str]] = []
    rejected: Counter[str] = Counter()

    gsm8k = load_dataset(
        "openai/gsm8k",
        "main",
        split="train",
        revision=SOURCE_REVISIONS["openai/gsm8k"],
    )
    gsm8k_rows = []
    for row in gsm8k:
        question = str(row["question"])
        if guard.matches(question):
            rejected["gsm8k_train_heldout_overlap"] += 1
            continue
        gsm8k_rows.append(
            _record(
                prompt=question,
                completion="Let's solve it carefully.\n" + clean_gsm8k_answer(str(row["answer"])),
                source="gsm8k_train",
            )
        )
    records.extend(_take_shuffled(gsm8k_rows, gsm8k_limit, SEED + 101))

    openr1 = load_dataset(
        "open-r1/OpenR1-Math-220k",
        "default",
        split="train",
        revision=SOURCE_REVISIONS["open-r1/OpenR1-Math-220k"],
        streaming=True,
    ).shuffle(seed=SEED, buffer_size=10_000)
    scanned = 0
    for row in openr1:
        if len(records) >= gsm8k_limit + openr1_limit:
            break
        scanned += 1
        question = str(row["problem"])
        if guard.matches(question):
            rejected["openr1_heldout_overlap"] += 1
            continue
        trace = verified_openr1_trace(row)
        if trace is None:
            rejected["openr1_no_short_verified_trace"] += 1
            continue
        records.append(
            _record(
                prompt=question,
                completion=trace,
                source="openr1_verified_math_train",
            )
        )
    rejected["openr1_scanned"] = scanned
    if sum(row["source"] == "openr1_verified_math_train" for row in records) < openr1_limit:
        raise RuntimeError("OpenR1 stream ended before the verified-trace target was met")
    return records, rejected


def build_records(profile: str) -> tuple[list[dict[str, str]], dict[str, Any]]:
    heldout, heldout_counts = _heldout_questions()
    guard = LeakageGuard(heldout)
    mcq, mcq_rejected = _load_mcq_records(guard)
    if profile in {"licensed-mcq", "licensed-hybrid"}:
        mcq = [row for row in mcq if row["source"] != "openbookqa_train"]
    records = list(mcq)
    rejected = Counter(mcq_rejected)

    if profile in {"hybrid", "licensed-hybrid"}:
        reasoning, reasoning_rejected = _load_reasoning_records(
            guard,
            gsm8k_limit=2_000,
            openr1_limit=2_500,
        )
        records.extend(reasoning)
        records.extend(build_african_arithmetic())
        rejected.update(reasoning_rejected)
    elif profile not in {"mcq", "licensed-mcq"}:
        raise ValueError(f"unknown profile: {profile}")

    normalized_seen: set[tuple[str, str]] = set()
    deduplicated: list[dict[str, str]] = []
    for row in records:
        key = (normalize_question(row["prompt"]), normalize_question(row["completion"]))
        if key in normalized_seen:
            rejected["duplicate_prompt_completion"] += 1
            continue
        normalized_seen.add(key)
        deduplicated.append(row)

    metadata = {
        "heldout_sources": heldout_counts,
        "heldout_question_count": len(guard.normalized),
        "rejected": dict(sorted(rejected.items())),
        "mcq_fraction": round(
            sum(row["source"] in MCQ_SOURCES for row in deduplicated) / len(deduplicated),
            6,
        ),
    }
    return deduplicated, metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--profile",
        choices=("mcq", "licensed-mcq", "hybrid", "licensed-hybrid"),
        required=True,
    )
    parser.add_argument("--validation-fraction", type=float, default=0.05)
    args = parser.parse_args()
    if not 0 < args.validation_fraction < 0.25:
        raise SystemExit("validation fraction must be between 0 and 0.25")

    records, quality = build_records(args.profile)
    random.Random(SEED).shuffle(records)
    validation_count = max(1, math.floor(len(records) * args.validation_fraction))
    validation = records[:validation_count]
    train = records[validation_count:]

    args.output.mkdir(parents=True, exist_ok=True)
    train_sha = _write_jsonl(args.output / "train.jsonl", train)
    validation_sha = _write_jsonl(args.output / "validation.jsonl", validation)
    active_source_ids = {
        "allenai/ai2_arc",
        "allenai/qasc",
    }
    if args.profile in {"mcq", "hybrid"}:
        active_source_ids.add("allenai/openbookqa")
    if args.profile in {"hybrid", "licensed-hybrid"}:
        active_source_ids.update(
            {
                "openai/gsm8k",
                "open-r1/OpenR1-Math-220k",
            }
        )
    manifest = {
        "schema_version": 1,
        "seed": SEED,
        "profile": args.profile,
        "source_revisions": {
            source_id: SOURCE_REVISIONS[source_id] for source_id in sorted(active_source_ids)
        },
        "source_licenses": {
            source_id: SOURCE_LICENSES[source_id] for source_id in sorted(active_source_ids)
        },
        "quality_controls": quality,
        "excluded": [
            "all source validation and test splits",
            "exact, >=0.8 five-gram-Jaccard or >=0.92 sequence overlaps with held-out questions",
            "OpenR1 traces without both Math Verify and completeness checks",
            "OpenR1 traces longer than 4500 characters",
            "submitted competition prompts",
        ],
        "train": {
            "rows": len(train),
            "sha256": train_sha,
            "sources": dict(sorted(Counter(row["source"] for row in train).items())),
        },
        "validation": {
            "rows": len(validation),
            "sha256": validation_sha,
            "sources": dict(sorted(Counter(row["source"] for row in validation).items())),
        },
    }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
