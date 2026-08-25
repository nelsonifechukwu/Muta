#!/usr/bin/env python3
"""Build the pinned, leakage-controlled ADTC SFT mixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from collections import Counter
from pathlib import Path
from typing import Any

SEED = 3407
SOURCE_REVISIONS = {
    "openai/gsm8k": "740312add88f781978c0658806c59bc2815b9866",
    "allenai/ai2_arc": "210d026faf9955653af8916fad021475a3f00453",
    "allenai/openbookqa": "388097ea7776314e93a529163e0fea805b8a6454",
    "eth-nlped/mathdial-chat": "52b3ffd70162631400016b8ce15a647e4b397ae1",
    "HuggingFaceTB/smoltalk": "5feaf2fd3ffca7c237fc38d1861bc30365d48ffa",
}


def _record(*, prompt: str, completion: str, source: str, mode: str = "chat") -> dict[str, str]:
    prompt = prompt.strip()
    completion = completion.strip()
    if not prompt or not completion:
        raise ValueError(f"empty training field from {source}")
    return {"prompt": prompt, "completion": completion, "source": source, "mode": mode}


def clean_gsm8k_answer(answer: str) -> str:
    answer = re.sub(r"<<[^<>]*>>", "", answer)
    answer = answer.replace("####", "Final answer:")
    return re.sub(r"[ \t]+\n", "\n", answer).strip()


def choice_text(row: dict[str, Any]) -> str:
    labels = list(row["choices"]["label"])
    texts = list(row["choices"]["text"])
    answer = str(row["answerKey"]).strip()
    try:
        return str(texts[labels.index(answer)])
    except ValueError as exc:
        raise ValueError(f"answer {answer!r} absent from labels {labels!r}") from exc


def _take_shuffled(rows: list[dict[str, str]], limit: int, seed: int) -> list[dict[str, str]]:
    chosen = list(rows)
    random.Random(seed).shuffle(chosen)
    return chosen[:limit]


def select_profile(records: list[dict[str, str]], profile: str) -> list[dict[str, str]]:
    if profile == "balanced":
        return list(records)
    if profile != "reasoning-heavy":
        raise ValueError(f"unknown dataset profile: {profile}")
    core = [
        row for row in records if row["source"] not in {"smoltalk_everyday_train", "mathdial_train"}
    ]
    mathdial = [row for row in records if row["source"] == "mathdial_train"]
    return core + _take_shuffled(mathdial, 750, SEED + 20)


def _load_sources() -> list[dict[str, str]]:
    from datasets import load_dataset

    records: list[dict[str, str]] = []

    gsm = load_dataset(
        "openai/gsm8k",
        "main",
        split="train",
        revision=SOURCE_REVISIONS["openai/gsm8k"],
    )
    gsm_rows = [
        _record(
            prompt=str(row["question"]),
            completion=("Let's solve it carefully.\n" + clean_gsm8k_answer(str(row["answer"]))),
            source="gsm8k_train",
        )
        for row in gsm
    ]
    records.extend(_take_shuffled(gsm_rows, 4_000, SEED + 1))

    for config, limit in (("ARC-Easy", 1_500), ("ARC-Challenge", 800)):
        arc = load_dataset(
            "allenai/ai2_arc",
            config,
            split="train",
            revision=SOURCE_REVISIONS["allenai/ai2_arc"],
        )
        rows = [
            _record(
                prompt=f"Question: {row['question']}\nAnswer:",
                completion=choice_text(row),
                source=f"{config.lower().replace('-', '_')}_train",
                mode="raw",
            )
            for row in arc
        ]
        records.extend(_take_shuffled(rows, limit, SEED + len(records)))

    openbook = load_dataset(
        "allenai/openbookqa",
        "main",
        split="train",
        revision=SOURCE_REVISIONS["allenai/openbookqa"],
    )
    openbook_rows = [
        _record(
            prompt=str(row["question_stem"]),
            completion=choice_text(row),
            source="openbookqa_train",
            mode="raw",
        )
        for row in openbook
    ]
    records.extend(_take_shuffled(openbook_rows, 1_000, SEED + 4))

    mathdial = load_dataset(
        "eth-nlped/mathdial-chat",
        split="train",
        revision=SOURCE_REVISIONS["eth-nlped/mathdial-chat"],
    )
    mathdial_rows = []
    for row in mathdial:
        prompt = (
            f"I am solving this problem:\n{row['question']}\n\n"
            f"My attempt was:\n{row['student_incorrect_solution']}\n\n"
            "Please identify the mistake and help me correct it."
        )
        completion = (
            "Let's check the reasoning and correct the first mistake.\n"
            + str(row["ground_truth"]).strip()
        )
        mathdial_rows.append(_record(prompt=prompt, completion=completion, source="mathdial_train"))
    records.extend(_take_shuffled(mathdial_rows, 1_500, SEED + 5))

    everyday = load_dataset(
        "HuggingFaceTB/smoltalk",
        "everyday-conversations",
        split="train",
        revision=SOURCE_REVISIONS["HuggingFaceTB/smoltalk"],
        streaming=True,
    )
    replay_rows = []
    for row in everyday.take(1_200):
        messages = list(row.get("messages") or [])
        for index, message in enumerate(messages[:-1]):
            if message.get("role") == "user" and messages[index + 1].get("role") == "assistant":
                replay_rows.append(
                    _record(
                        prompt=str(message["content"]),
                        completion=str(messages[index + 1]["content"]),
                        source="smoltalk_everyday_train",
                    )
                )
                break
    records.extend(_take_shuffled(replay_rows, 800, SEED + 6))
    records.extend(build_african_arithmetic())
    return records


def build_african_arithmetic() -> list[dict[str, str]]:
    currencies = ("naira", "cedis", "shillings")
    quantities = (12, 15, 18, 20, 25, 30, 32, 40)
    unit_costs = (120, 150, 180, 200, 240, 300)
    profits = (10, 15, 20, 25, 30)
    rows = []
    for index in range(240):
        quantity = quantities[index % len(quantities)]
        unit_cost = unit_costs[(index // len(quantities)) % len(unit_costs)]
        profit = profits[(index // 3) % len(profits)]
        currency = currencies[index % len(currencies)]
        total_cost = quantity * unit_cost
        selling_total = total_cost * (100 + profit) / 100
        selling_each = selling_total / quantity
        prompt = (
            f"A trader buys {quantity} identical cartons for {total_cost:g} {currency} and "
            f"sells them at a {profit}% profit. What is the selling price of one carton? "
            "Show the calculation."
        )
        completion = (
            f"1. Cost per carton = {total_cost:g} / {quantity} = {unit_cost:g} {currency}.\n"
            f"2. Profit per carton = {profit}% of {unit_cost:g} = "
            f"{unit_cost * profit / 100:g} {currency}.\n"
            f"3. Selling price = {unit_cost:g} + {unit_cost * profit / 100:g} = "
            f"{selling_each:g} {currency}.\n"
            f"Final answer: {selling_each:g} {currency} per carton."
        )
        rows.append(
            _record(
                prompt=prompt,
                completion=completion,
                source="verified_african_arithmetic",
            )
        )
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, str]]) -> str:
    digest = hashlib.sha256()
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            line = json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            handle.write(line)
            digest.update(line.encode("utf-8"))
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", choices=("balanced", "reasoning-heavy"), default="balanced")
    parser.add_argument("--validation-fraction", type=float, default=0.05)
    args = parser.parse_args()
    if not 0 < args.validation_fraction < 0.25:
        raise SystemExit("validation fraction must be between 0 and 0.25")

    records = select_profile(_load_sources(), args.profile)
    random.Random(SEED).shuffle(records)
    validation_count = max(1, round(len(records) * args.validation_fraction))
    validation = records[:validation_count]
    train = records[validation_count:]

    args.output.mkdir(parents=True, exist_ok=True)
    train_sha = _write_jsonl(args.output / "train.jsonl", train)
    validation_sha = _write_jsonl(args.output / "validation.jsonl", validation)
    manifest = {
        "schema_version": 1,
        "seed": SEED,
        "profile": args.profile,
        "source_revisions": SOURCE_REVISIONS,
        "excluded": [
            "all validation and test splits",
            "the ARC-Easy-500 evaluation questions",
            "the two submitted ADTC prompts",
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
