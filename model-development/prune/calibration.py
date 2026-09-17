#!/usr/bin/env python3
"""Build the BI calibration set from the healing train split, guarded against eval prompts.

Usage:
  calibration.py --train ../finetune/data-metric-licensed-hybrid/train.jsonl \
      --banned ../../bench/measurements/semifinal-20260916/prompts.json \
      --banned ../../muta-iq/metadata.json \
      --per-source 22 --output calibration.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_finetune(name: str):
    spec = importlib.util.spec_from_file_location(
        name, HERE.parent / "finetune" / f"{name}.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render_text(row: dict) -> str:
    if row["mode"] == "chat":
        return (
            f"<|im_start|>user\n{row['prompt']}<|im_end|>\n"
            f"<|im_start|>assistant\n{row['completion']}<|im_end|>"
        )
    return _load_finetune("train_lora").join_raw_prompt_completion(
        row["prompt"], row["completion"]
    )


def stratified_sample(rows: list[dict], per_source: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    by_source: dict[str, list[dict]] = {}
    for row in rows:
        by_source.setdefault(row["source"], []).append(row)
    out: list[dict] = []
    for source in sorted(by_source):
        pool = list(by_source[source])
        rng.shuffle(pool)
        out.extend(pool[:per_source])
    return out


def normalize(text: str) -> str:
    text = text.lower().replace("₦", " ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _ngrams(text: str, n: int) -> set[tuple[str, ...]]:
    words = normalize(text).split()
    return {tuple(words[i : i + n]) for i in range(max(0, len(words) - n + 1))}


def contaminated(
    text: str, banned: list[str], ngram: int = 8, threshold: float = 0.5
) -> bool:
    norm = normalize(text)
    for phrase in banned:
        if normalize(phrase) in norm:
            return True
        grams = _ngrams(phrase, ngram)
        if grams and len(grams & _ngrams(text, ngram)) / len(grams) >= threshold:
            return True
    return False


def load_banned(paths: list[Path]) -> list[str]:
    banned: list[str] = []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else data.get("test_prompts", [])
        banned.extend(item["prompt"] for item in items)
    return banned


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--banned", type=Path, action="append", required=True)
    parser.add_argument("--per-source", type=int, default=22)
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows = [
        json.loads(line)
        for line in args.train.open(encoding="utf-8")
        if line.strip()
    ]
    banned = load_banned(args.banned)
    hits = [row for row in rows if contaminated(render_text(row), banned)]
    if hits:
        raise SystemExit(
            f"{len(hits)} training rows overlap banned prompts; first: {hits[0]}"
        )
    sample = stratified_sample(rows, args.per_source, args.seed)
    with args.output.open("w", encoding="utf-8") as handle:
        for row in sample:
            handle.write(
                json.dumps({"source": row["source"], "text": render_text(row)}) + "\n"
            )
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    manifest = {
        "schema_version": 1,
        "train": {
            "path": str(args.train),
            "sha256": hashlib.sha256(args.train.read_bytes()).hexdigest(),
        },
        "banned_files": [str(p) for p in args.banned],
        "banned_count": len(banned),
        "per_source": args.per_source,
        "seed": args.seed,
        "rows": len(sample),
        "sources": sorted({row["source"] for row in sample}),
        "output": {"path": str(args.output), "sha256": digest},
    }
    args.output.with_name("calibration-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
