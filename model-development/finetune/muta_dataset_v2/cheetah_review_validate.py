"""Validate the complete Cheetah PDF review ledger before a private in-place append."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

APPROVED = {"approve_verified", "approve_corrected_verified"}
TEXT_ONLY_STATUS = "reviewed_text_only_self_contained"
VISUAL = re.compile(
    r"(?i)\b(?:diagram|graph|table|figure|drawing|draw|construct|construction|"
    r"histogram|frequency\s+polygon|pie\s+chart|bar\s+chart|map|grid|illustration|"
    r"sketch|ogive|plot)\b"
)
ARTIFACT = re.compile(
    r"(?i)(?:math\s+input\s+error|undefined\s+control\s+sequence|"
    r"\\(?:frac|sqrt|begin|end)\b|\ufffd|\[asset\s*:|[\x00-\x08\x0b\x0c\x0e-\x1f])"
)
PART = re.compile(r"(?i)(?<![A-Za-z0-9])\((a|b|c|d|i|ii|iii|iv|v)\)")


class ReviewError(RuntimeError):
    pass


def canonical_sha256(value: dict[str, Any]) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def normalize(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


_SUPERSCRIPT = str.maketrans(
    "⁰¹²³⁴⁵⁶⁷⁸⁹⁻₀₁₂₃₄₅₆₇₈₉−–—",
    "0123456789-0123456789---",
)


def loose_math(value: str) -> str:
    value = value.casefold().translate(_SUPERSCRIPT)
    value = re.sub(r"(?<=\d),\s*(?=\d{3}\b)", "", value)
    value = re.sub(r"\blog(10|[2-9])(?=\d)", r"log \1 ", value)
    value = re.sub(r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)", " ", value)
    value = value.replace("-", " minus ")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def contains_tokens(container: str, candidate: str) -> bool:
    container_tokens = container.split()
    candidate_tokens = candidate.split()
    if not candidate_tokens or len(candidate_tokens) > len(container_tokens):
        return False
    width = len(candidate_tokens)
    return any(
        container_tokens[index : index + width] == candidate_tokens
        for index in range(len(container_tokens) - width + 1)
    )


def token_containment(left: str, right: str) -> float:
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReviewError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ReviewError(f"{path}:{line_number}: expected an object")
        rows.append(row)
    return rows


def write_2025_exclusions(corpus_path: Path, output_path: Path) -> None:
    raw = corpus_path.read_bytes()
    corpus_sha256 = hashlib.sha256(raw).hexdigest()
    corpus = [json.loads(line) for line in raw.splitlines() if line.strip()]
    rows = []
    for source in corpus:
        if (
            (source.get("source") or {}).get("source_type") != "cheetah_pdf"
            or source.get("year") != 2025
        ):
            continue
        rows.append(
            {
                "record_id": source["record_id"],
                "decision": "exclude_missing_pdf_math_layer",
                "evidence_summary": (
                    "The PDF text layer omits the mathematical expressions and most option "
                    "values; safe recovery requires visual transcription, so the row is not "
                    "self-contained text and is excluded."
                ),
                "source_corpus_sha256": corpus_sha256,
                "source_record_sha256": canonical_sha256(source),
            }
        )
    rows.sort(key=lambda row: int(next(
        source["question_number"]
        for source in corpus
        if source.get("record_id") == row["record_id"]
    )))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.partial")
    temporary.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )
    temporary.replace(output_path)


def validate(corpus_path: Path, ledgers: list[Path]) -> dict[str, Any]:
    raw = corpus_path.read_bytes()
    corpus_sha256 = hashlib.sha256(raw).hexdigest()
    corpus = [json.loads(line) for line in raw.splitlines() if line.strip()]
    cheetah = {
        row["record_id"]: row
        for row in corpus
        if (row.get("source") or {}).get("source_type") == "cheetah_pdf"
    }
    reviews: dict[str, dict[str, Any]] = {}
    for path in ledgers:
        for row in load_jsonl(path):
            record_id = str(row.get("record_id") or "")
            if record_id in reviews:
                raise ReviewError(f"duplicate review decision: {record_id}")
            reviews[record_id] = row
    if set(reviews) != set(cheetah):
        missing = sorted(set(cheetah) - set(reviews))
        extra = sorted(set(reviews) - set(cheetah))
        raise ReviewError(
            f"review coverage mismatch: missing={len(missing)} extra={len(extra)} "
            f"examples={missing[:3] + extra[:3]}"
        )

    decisions: Counter[str] = Counter()
    years: Counter[int] = Counter()
    for record_id, review in reviews.items():
        source = cheetah[record_id]
        decision = str(review.get("decision") or "")
        if decision not in APPROVED and not decision.startswith("exclude_"):
            raise ReviewError(f"invalid decision for {record_id}: {decision!r}")
        if review.get("source_corpus_sha256") != corpus_sha256:
            raise ReviewError(f"corpus binding mismatch: {record_id}")
        if review.get("source_record_sha256") != canonical_sha256(source):
            raise ReviewError(f"source-row binding mismatch: {record_id}")
        evidence = str(review.get("evidence_summary") or "").strip()
        if not evidence:
            raise ReviewError(f"blank evidence: {record_id}")
        decisions[decision] += 1
        if source.get("year") == 2025:
            source_meta = source.get("source") or {}
            for kind in ("question", "answer"):
                relative_path = str(source_meta.get(f"local_{kind}_file") or "")
                if review.get(f"pdf_{kind}_file") != relative_path:
                    raise ReviewError(f"{kind} PDF binding mismatch: {record_id}")
                pdf_path = corpus_path.parent / relative_path
                actual_sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
                if review.get(f"pdf_{kind}_sha256") != actual_sha256:
                    raise ReviewError(f"{kind} PDF hash mismatch: {record_id}")
        if decision not in APPROVED:
            continue

        years[int(source["year"])] += 1
        for field in ("clean_prompt", "canonical_answer", "worked_solution"):
            if not str(review.get(field) or "").strip():
                raise ReviewError(f"blank {field}: {record_id}")
        if review.get("all_required_assets_resolved") is not True:
            raise ReviewError(f"assets not resolved: {record_id}")
        if review.get("visual_dependency_status") != TEXT_ONLY_STATUS:
            raise ReviewError(f"not explicitly text-only: {record_id}")
        if decision == "approve_corrected_verified" and source.get("year") == 2025:
            prompt_corrected = review.get("prompt_correction_applied") is True
            answer_corrected = review.get("answer_correction_applied") is True
            if review.get("correction_applied") is not True or not (
                prompt_corrected or answer_corrected
            ):
                raise ReviewError(f"corrected row lacks correction binding: {record_id}")
            if review.get("source_answer_match") is not (not answer_corrected):
                raise ReviewError(f"corrected row answer-match flag is inconsistent: {record_id}")
        source_meta = source.get("source") or {}
        if review.get("pdf_question_file") != source_meta.get("local_question_file"):
            raise ReviewError(f"question PDF binding mismatch: {record_id}")
        if review.get("pdf_answer_file") != source_meta.get("local_answer_file"):
            raise ReviewError(f"answer PDF binding mismatch: {record_id}")
        prompt = str(review["clean_prompt"])
        solution = str(review["worked_solution"])
        answer = str(review["canonical_answer"])
        if VISUAL.search(prompt) or VISUAL.search(solution):
            raise ReviewError(f"visual dependency remains: {record_id}")
        if ARTIFACT.search(prompt) or ARTIFACT.search(solution):
            raise ReviewError(f"PDF extraction artifact remains: {record_id}")
        if len(prompt) > 6000 or len(solution) > 6000:
            raise ReviewError(f"conservative text limit exceeded: {record_id}")
        if re.search(r"(?i)\bmain\s+concepts?\b", solution):
            raise ReviewError(f"solution still contains boilerplate: {record_id}")
        labels = list(dict.fromkeys(PART.findall(prompt)))
        if len(labels) > 1:
            answer_folded = answer.casefold()
            absent = [
                label
                for label in labels
                if f"({label.casefold()})" not in answer_folded
            ]
            if absent:
                raise ReviewError(
                    f"multipart canonical answer omits {absent}: {record_id}"
                )
        options = source.get("options") or []
        source_answer = str(source.get("correct_answer") or "").strip().upper()
        if source.get("year") == 2025 and source_answer in {"A", "B", "C", "D"}:
            if review.get("content_recovery_method") not in {
                "rendered_pdf_visual_transcription",
                "rendered_pdf_ocr_and_visual_review",
            }:
                raise ReviewError(f"2025 recovery method is absent: {record_id}")
            option_blob = prompt.partition("Options:")[2].strip()
            pieces = re.split(r"(?:^|;\s+)([A-D])\.\s*", option_blob)
            recovered_options = {
                pieces[index]: pieces[index + 1].strip().rstrip(".")
                for index in range(1, len(pieces) - 1, 2)
            }
            if set(recovered_options) != {"A", "B", "C", "D"}:
                raise ReviewError(f"recovered options are incomplete: {record_id}")
            label_match = re.match(
                r"\s*(?:option\s+)?([a-d])(?:\s*[.):\-]|\s+)",
                answer.casefold(),
            )
            if label_match is None:
                raise ReviewError(f"canonical MCQ answer omits its label: {record_id}")
            answer_label = label_match.group(1).upper()
            corrected = decision == "approve_corrected_verified"
            if not corrected and answer_label != source_answer:
                raise ReviewError(f"canonical MCQ label disagrees with key: {record_id}")
            if corrected:
                prompt_corrected = review.get("prompt_correction_applied") is True
                answer_corrected = review.get("answer_correction_applied") is True
                if review.get("correction_applied") is not True or not (
                    prompt_corrected or answer_corrected
                ):
                    raise ReviewError(
                        f"corrected MCQ lacks explicit correction binding: {record_id}"
                    )
                expected_match = not answer_corrected
                if review.get("source_answer_match") is not expected_match:
                    raise ReviewError(
                        f"corrected MCQ answer-match flag is inconsistent: {record_id}"
                    )
            option_text = loose_math(recovered_options[answer_label])
            if option_text and token_containment(loose_math(answer), option_text) < 0.75:
                raise ReviewError(f"canonical MCQ omits recovered option text: {record_id}")
        elif options and source_answer in {"A", "B", "C", "D"}:
            option = next(
                (item for item in options if str(item.get("label")).upper() == source_answer),
                None,
            )
            if option is None:
                raise ReviewError(f"answer label is absent from options: {record_id}")
            label_match = re.match(
                r"\s*(?:option\s+)?([a-d])(?:\s*[.):\-]|\s+)",
                answer.casefold(),
            )
            if label_match is None or label_match.group(1).upper() != source_answer:
                raise ReviewError(f"canonical MCQ answer omits its label: {record_id}")
            option_text = loose_math(str(option.get("text") or ""))
            if option_text and token_containment(loose_math(answer), option_text) < 0.75:
                raise ReviewError(f"canonical MCQ answer omits option text: {record_id}")

    return {
        "corpus_sha256": corpus_sha256,
        "reviewed_rows": len(reviews),
        "approved_rows": sum(decisions[key] for key in APPROVED),
        "excluded_rows": sum(
            amount for key, amount in decisions.items() if key.startswith("exclude_")
        ),
        "approved_by_year": dict(sorted(years.items())),
        "decisions": dict(sorted(decisions.items())),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--ledger", action="append", type=Path, default=[])
    parser.add_argument("--write-2025-exclusions", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.write_2025_exclusions:
        write_2025_exclusions(args.corpus, args.write_2025_exclusions)
    if args.ledger:
        print(json.dumps(validate(args.corpus, args.ledger), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
