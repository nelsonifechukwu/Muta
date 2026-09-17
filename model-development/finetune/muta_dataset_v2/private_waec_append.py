"""Append independently reviewed WAEC rows to existing Muta artifacts without copying them.

The command is intentionally conservative:

* dry-run is the default; mutation requires ``--apply``;
* existing shards are verified and never rewritten;
* only ``approve_verified`` and ``approve_corrected_verified`` ledger rows are adapted;
* the publisher licence remains the row licence, while the user's private-training
  attestation is recorded separately; and
* each target receives one new shard, an atomically replaced manifest, and a small rollback
  receipt containing the inverse manifest patch.

The compact review ledger supplies ``canonical_answer``, ``worked_solution``,
``verification_method``, ``evidence_summary``, ``source_answer_origin``, and
``correction_applied``.  This adapter derives the clean prompt, completion, exact source hash,
and a content-addressed review ID.  It refuses visual rows and any prompt whose question/answer
boundary cannot be recovered conservatively.  Exclusion decisions are retained in the ledger
but never emitted.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .core import (
    HoldoutIndex,
    make_record,
    normalize_text,
    normalized_sha256,
    sha256_file,
    validate_record,
)
from .tokenization import DEFAULT_MAX_SEQUENCE_TOKENS, QwenTokenCounter

PACKAGE_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = PACKAGE_DIR / "schema.json"
APPEND_SCHEMA_VERSION = 1
ADAPTER_VERSION = "muta-private-waec-append-v1"
REVIEW_PREFIX = "muta_waec_review_v1_"
REVIEWER = "Codex model-assisted independent solve with programmatic checks"
REVIEWER_TYPE = "model_assisted"
REVIEWED_AT = "2026-09-17"
RUBRIC_VERSION = "muta-private-waec-review-v1"
REVIEW_METHOD = "private_exact_row_model_assisted_programmatic_review"
APPROVED_DECISIONS = frozenset({"approve_verified", "approve_corrected_verified"})
_LEDGER_META_PREFIX = "_private_append_"

SOURCE_POLICY = {
    "waec_html": {
        "source_id": "waec_elearning",
        "name": "WAEC e-Learning and Chief Examiners' reports",
        "url": "https://www.waeconline.org.ng/e-learning/",
        "license": "Copyright West African Examinations Council. All rights reserved.",
        "license_url": "https://www.waeconline.org.ng/e-learning/",
        "source_kind": "official_exam_material",
    },
    "cheetah_pdf": {
        "source_id": "cheetahwaec",
        "name": "CheetahWAEC past papers and solutions",
        "url": "https://cheetahwaec.com/past-papers",
        "license": (
            "Cheetah WAEC terms reserve original explanations; third-party rights remain "
            "with their owners. Local educational use only."
        ),
        "license_url": "https://cheetahwaec.com/terms",
        "source_kind": "third_party_exam_material",
    },
}

ALLOWED_DIFFICULTIES = frozenset({"foundation", "standard", "advanced"})
ALLOWED_FORMATS = frozenset(
    {"free_response", "multiple_choice", "misconception", "socratic"}
)
ALLOWED_PEDAGOGIES = frozenset(
    {
        "worked_solution",
        "exam_marking_scheme",
        "misconception_correction",
        "socratic_hint",
        "concise_answer",
    }
)
ALLOWED_ANSWER_ORIGINS = frozenset(
    {
        "publisher_answer_independently_verified",
        "corrected_publisher_answer",
        "independently_solved_missing_answer",
    }
)
ALLOWED_SOURCE_ANSWER_ORIGINS = frozenset(
    {
        "none_in_record",
        "publisher_expected_answer_embedded_in_question_text",
        "publisher_expected_solution_embedded_in_question_text",
        "examiner_comment_embedded_in_question_text_without_full_answer",
        "publisher_worked_solution_in_record",
        "publisher_worked_solution_in_answer_pdf",
    }
)
SUBJECT_MAP = {
    "mathematics": "mathematics",
    "physics": "physics",
    "chemistry": "chemistry",
    "biology": "biology",
    "science": "integrated_science",
}

_ANSWER_MARKER = re.compile(
    r"(?im)^\s*(?:(?:the\s+)?expected\s+(?:answers?|solutions?)|"
    r"suggested\s+answers?|marking\s+scheme|"
    r"solutions?|comments?|examiner(?:'s)?\s+observations?|"
    r"(?:correct\s+)?answers?|ans)\s*:?.*$"
)
_INLINE_ANSWER_MARKER = re.compile(
    r"(?i)\b(?:(?:the\s+)?expected\s+(?:answers?|solutions?)|"
    r"suggested\s+answers?|marking\s+scheme|(?:correct\s+)?answer|ans)"
    r"\s*(?::|is\b|are\b)"
)
_COLLECTOR_SEPARATOR = re.compile(r"^\s*[_=*-]{3,}\s*$")
_PAGE_CHROME = re.compile(
    r"(?i)^\s*(?:home|back\s+to\s+top|waec\s+e-?learning|copyright\b.*|"
    r"all\s+rights\s+reserved|click\s+here.*)\s*$"
)
_UNRESOLVED_ASSET = re.compile(r"(?i)\[asset\s*:")
_UNRESOLVED_VISUAL_DEPENDENCY = re.compile(
    r"(?i)\b(?:diagram|graph|table|figure|drawing|draw|construct|construction|"
    r"histogram|frequency\s+polygon|pie\s+chart|bar\s+chart|map|grid|illustration|"
    r"sketch|ogive|plot)\b"
)
_PDF_EXTRACTION_ARTIFACT = re.compile(
    r"(?i)(?:math\s+input\s+error|undefined\s+control\s+sequence|"
    r"\\(?:frac|sqrt|begin|end)\b|\ufffd|\[asset\s*:|[\x00-\x08\x0b\x0c\x0e-\x1f])"
)
_EXAMINER_PROSE_START = re.compile(
    r"(?i)^\s*(?:part\s*\([ab]\)\.\s*this\s+(?:was|question\b)|"
    r"this\s+was\s+another\b|a\s+popular\s+question\b|"
    r"many\s+candidates\b|candidates\b)"
)
_PROMPT_LEAK = re.compile(
    r"(?i)\b(?:expected\s+(?:answers?|solutions?)|candidates?|performed)\b|"
    r"=\s*25\s*s\b"
)
_TOPIC = re.compile(r"^[a-z0-9_]+$")
_PART_INDEX = re.compile(r"^part-(\d+)")
_CHEETAH_TEXT_ONLY_STATUS = "reviewed_text_only_self_contained"


class AppendRefused(RuntimeError):
    """A fail-closed validation or state error."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def content_address(value: dict[str, Any], *, field: str, prefix: str) -> str:
    payload = {key: item for key, item in value.items() if key != field}
    return prefix + canonical_json_sha256(payload)[:24]


def manifest_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _load_json(path: Path) -> tuple[dict[str, Any], bytes, str]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise AppendRefused(f"expected a JSON object: {path}")
    return value, raw, hashlib.sha256(raw).hexdigest()


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], str]:
    digest = hashlib.sha256()
    rows: list[dict[str, Any]] = []
    with path.open("rb") as handle:
        for line_number, raw in enumerate(handle, start=1):
            digest.update(raw)
            if not raw.strip():
                continue
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise AppendRefused(f"invalid JSON at {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise AppendRefused(f"expected an object at {path}:{line_number}")
            rows.append(value)
    return rows, digest.hexdigest()


def _load_review_ledgers(
    paths: list[Path],
) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]]]:
    if not paths:
        raise AppendRefused("at least one review ledger is required")
    rows: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for path in sorted((item.resolve() for item in paths), key=str):
        ledger_rows, ledger_sha256 = _load_jsonl(path)
        sources.append(
            {
                "path": str(path),
                "sha256": ledger_sha256,
                "row_count": len(ledger_rows),
            }
        )
        for row in ledger_rows:
            annotated = copy.deepcopy(row)
            annotated[f"{_LEDGER_META_PREFIX}path"] = str(path)
            annotated[f"{_LEDGER_META_PREFIX}sha256"] = ledger_sha256
            rows.append(annotated)
    bundle_input = [
        {"sha256": source["sha256"], "row_count": source["row_count"]}
        for source in sorted(sources, key=lambda item: (item["sha256"], item["row_count"]))
    ]
    return rows, canonical_json_sha256(bundle_input), sources


def _validate_attestation(
    attestation: dict[str, Any],
    *,
    corpus_sha256: str,
    corpus_row_count: int,
    review_bundle_sha256: str,
    review_sources: list[dict[str, Any]],
) -> None:
    required = {
        "schema_version",
        "attestation_id",
        "recorded_at",
        "attestor_role",
        "instruction",
        "intended_use",
        "artifact_handling",
        "row_eligibility_adjudication",
        "review_bindings",
        "overlap_adjudications",
        "rights_boundary",
        "quality_boundary",
        "source_snapshot",
    }
    missing = sorted(required.difference(attestation))
    if missing:
        raise AppendRefused(f"private-training attestation is missing: {', '.join(missing)}")
    if attestation["schema_version"] != 1:
        raise AppendRefused("unsupported private-training attestation schema")
    for field in (
        "attestation_id",
        "recorded_at",
        "attestor_role",
        "instruction",
        "rights_boundary",
        "quality_boundary",
    ):
        if not str(attestation[field]).strip():
            raise AppendRefused(f"private-training attestation has blank {field}")
    intended_use = attestation["intended_use"]
    if not isinstance(intended_use, list) or set(intended_use) != {
        "local_model_fine_tuning",
        "private_waec_practice",
        "competition_research",
    }:
        raise AppendRefused("private-training intended_use does not match the recorded scope")
    handling = attestation["artifact_handling"]
    expected_handling = {
        "in_place_augmentation_required": True,
        "duplicate_dataset_artifacts_allowed": False,
        "public_dataset_redistribution_asserted": False,
        "publisher_permission_asserted": False,
    }
    if handling != expected_handling:
        raise AppendRefused(f"private-training artifact_handling must equal {expected_handling!r}")
    adjudication = attestation["row_eligibility_adjudication"]
    expected_adjudication = {
        "status": "approved_for_local_private_training_by_project_owner",
        "scope": "only exact rows that pass the attached content-quality review ledgers",
        "supersedes_review_ledger_training_eligible_for_this_private_artifact": True,
        "does_not_supersede_publisher_rights_status": True,
        "publisher_permission_asserted": False,
        "basis": (
            "The project owner explicitly instructed that the approved WAEC practice rows "
            "be added to the existing 300K and 2.5M training artifacts for local fine-tuning, "
            "private WAEC practice, and competition research."
        ),
    }
    if adjudication != expected_adjudication:
        raise AppendRefused(
            "private-training row_eligibility_adjudication does not match the recorded scope"
        )
    review_bindings = attestation["review_bindings"]
    if not isinstance(review_bindings, dict):
        raise AppendRefused("private-training review_bindings must be an object")
    expected_ledgers = sorted(
        [
            {"sha256": source["sha256"], "row_count": source["row_count"]}
            for source in review_sources
        ],
        key=lambda item: (item["sha256"], item["row_count"]),
    )
    bound_ledgers = sorted(
        review_bindings.get("ledgers") or [],
        key=lambda item: (item.get("sha256", ""), item.get("row_count", -1)),
    )
    if review_bindings.get("bundle_sha256") != review_bundle_sha256:
        raise AppendRefused("private-training attestation binds a different review bundle")
    if bound_ledgers != expected_ledgers:
        raise AppendRefused("private-training attestation binds different review ledgers")
    if not isinstance(attestation["overlap_adjudications"], list):
        raise AppendRefused("private-training overlap_adjudications must be a list")
    snapshot = attestation["source_snapshot"]
    if not isinstance(snapshot, dict) or snapshot.get("sha256") != corpus_sha256:
        raise AppendRefused("private-training attestation binds a different corpus snapshot")
    if snapshot.get("row_count") != corpus_row_count:
        raise AppendRefused("private-training attestation binds a different corpus row count")
    if snapshot.get("path") != "corpus/waec/questions.jsonl":
        raise AppendRefused("private-training attestation names an unexpected corpus path")
    _validate_attested_source_pdfs(attestation)


def _validate_attested_source_pdfs(attestation: dict[str, Any]) -> None:
    """Verify optional raw-PDF bindings carried by a source-specific attestation."""

    bindings = attestation.get("source_pdf_bindings")
    if bindings is None:
        return
    if not isinstance(bindings, list) or not bindings:
        raise AppendRefused("source_pdf_bindings must be a non-empty list")
    repository_root = PACKAGE_DIR.parents[2].resolve()
    seen: set[str] = set()
    for binding in bindings:
        if not isinstance(binding, dict):
            raise AppendRefused("source PDF binding must be an object")
        relative = str(binding.get("path") or "")
        if relative in seen:
            raise AppendRefused(f"duplicate source PDF binding: {relative}")
        seen.add(relative)
        if not relative.startswith("corpus/waec/raw/cheetah/") or not relative.endswith(
            ".pdf"
        ):
            raise AppendRefused(f"unexpected source PDF binding path: {relative!r}")
        resolved = (repository_root / relative).resolve()
        try:
            resolved.relative_to(repository_root)
        except ValueError as exc:
            raise AppendRefused(f"source PDF binding escapes the repository: {relative}") from exc
        if not resolved.is_file():
            raise AppendRefused(f"bound source PDF is absent: {relative}")
        if binding.get("bytes") != resolved.stat().st_size:
            raise AppendRefused(f"bound source PDF size changed: {relative}")
        if binding.get("sha256") != sha256_file(resolved):
            raise AppendRefused(f"bound source PDF hash changed: {relative}")


def _source_record_hash(record: dict[str, Any]) -> str:
    return canonical_json_sha256(record)


def _ledger_entry_payload(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in entry.items() if not key.startswith(_LEDGER_META_PREFIX)
    }


def _review_decision(entry: dict[str, Any]) -> str:
    explicit = entry.get("decision")
    if explicit is not None:
        return str(explicit)
    if entry.get("content_quality_approved") is not True:
        return "exclude_content_quality_not_approved"
    return (
        "approve_corrected_verified"
        if entry.get("correction_applied") is True
        else "approve_verified"
    )


def _contains_normalized_sequence(container: str, candidate: str) -> bool:
    container_tokens = container.split()
    candidate_tokens = candidate.split()
    if not candidate_tokens or len(candidate_tokens) > len(container_tokens):
        return False
    width = len(candidate_tokens)
    return any(
        container_tokens[index : index + width] == candidate_tokens
        for index in range(len(container_tokens) - width + 1)
    )


def _canonical_answer_signatures(answer: str) -> list[str]:
    signatures = [normalize_text(answer)]
    for fragment in re.split(r";|\.(?!\d)", answer):
        signature = normalize_text(fragment)
        if any(character.isdigit() for character in fragment) and len(signature.split()) >= 2:
            signatures.append(signature)
    return [signature for signature in dict.fromkeys(signatures) if signature]


def _token_containment(left: str, right: str) -> float:
    left_tokens = set(normalize_text(left).split())
    right_tokens = set(normalize_text(right).split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))


_LOOSE_MATH_TRANSLATION = str.maketrans(
    {
        "−": "-",
        "–": "-",
        "—": "-",
        "⁻": "-",
        "⁰": "0",
        "¹": "1",
        "²": "2",
        "³": "3",
        "⁴": "4",
        "⁵": "5",
        "⁶": "6",
        "⁷": "7",
        "⁸": "8",
        "⁹": "9",
    }
)
_SUBSCRIPT_DIGITS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")


def _loose_math_signature(value: str) -> str:
    value = re.sub(
        r"[₀₁₂₃₄₅₆₇₈₉]+",
        lambda match: f" {match.group(0).translate(_SUBSCRIPT_DIGITS)} ",
        value,
    )
    value = value.casefold().translate(_LOOSE_MATH_TRANSLATION)
    value = re.sub(r"\blog(10|[2-9])(?=\d)", r"log \1 ", value)
    value = re.sub(r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)", " ", value)
    number_words = {
        "zero": "0",
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "eight": "8",
        "nine": "9",
    }
    for word, digit in number_words.items():
        value = re.sub(rf"\b{word}\b", digit, value)
    value = re.sub(r"(?<=\d),\s*(?=\d{3}\b)", "", value)
    value = value.replace("-", " minus ")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def _marked_options(text: str) -> dict[str, str]:
    text = re.sub(r"(?<=[A-Za-z])-\s*\n\s*(?=[A-Za-z])", "", text)
    marker = re.search(r"(?i)\b(?:possible\s*answers?|options?)\s*:\s*", text)
    tail = text[marker.end() :] if marker else text
    matches = list(
        re.finditer(
            r"(?is)(?:^|[;\n])\s*([A-D])\.\s*(.*?)"
            r"(?=(?:[;\n]\s*|\s+)[A-D]\.\s*|$)",
            tail,
        )
    )
    return {
        match.group(1).upper(): " ".join(match.group(2).split())
        for match in matches
    }


def _validate_source_answer_origin(
    source: dict[str, Any], *, source_origin: str, record_id: str
) -> None:
    question = str(source.get("question_text") or "")
    if source_origin == "none_in_record":
        if source.get("answer_status") == "published":
            raise AppendRefused(f"review says no source answer but corpus says published: {record_id}")
        return
    if source_origin in {
        "publisher_expected_answer_embedded_in_question_text",
        "publisher_expected_solution_embedded_in_question_text",
    }:
        if not (_ANSWER_MARKER.search(question) or _INLINE_ANSWER_MARKER.search(question)):
            raise AppendRefused(f"embedded publisher answer marker is absent: {record_id}")
        return
    if source_origin == "examiner_comment_embedded_in_question_text_without_full_answer":
        if not source.get("examiner_observation") and "candidates" not in question.casefold():
            raise AppendRefused(f"examiner-comment evidence is absent: {record_id}")
        return
    if source_origin == "publisher_worked_solution_in_record" and not any(
        str(source.get(field) or "").strip()
        for field in ("worked_solution", "marking_scheme", "correct_answer")
    ):
        raise AppendRefused(f"publisher worked solution is absent: {record_id}")
    if source_origin == "publisher_worked_solution_in_answer_pdf":
        source_meta = source.get("source") or {}
        if not str(source_meta.get("local_answer_file") or "").strip():
            raise AppendRefused(f"publisher answer PDF is absent: {record_id}")
        if not str(source.get("correct_answer") or "").strip():
            raise AppendRefused(f"publisher answer key is absent: {record_id}")


def _clean_source_prompt(
    text: str, *, canonical_answer: str, allow_answer_option_in_prompt: bool = False
) -> str:
    """Recover only the question side and fail if answer/examiner prose survives."""

    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split())
        if not line or _PAGE_CHROME.fullmatch(line):
            continue
        if _COLLECTOR_SEPARATOR.fullmatch(line):
            break
        if _ANSWER_MARKER.match(line) or _EXAMINER_PROSE_START.match(line):
            break
        inline = _INLINE_ANSWER_MARKER.search(line)
        if inline:
            prefix = line[: inline.start()].strip()
            if prefix:
                lines.append(prefix)
            break
        lines.append(line)
    prompt = "\n".join(lines).strip()
    if _ANSWER_MARKER.search(prompt) or _INLINE_ANSWER_MARKER.search(prompt):
        raise AppendRefused("answer/comment marker remains in cleaned user prompt")
    if _PROMPT_LEAK.search(prompt):
        raise AppendRefused("examiner or answer-side prose remains in cleaned user prompt")
    if _UNRESOLVED_ASSET.search(prompt):
        raise AppendRefused("cleaned user prompt still contains an unresolved asset marker")
    prompt_signature = normalize_text(prompt)
    if not allow_answer_option_in_prompt:
        for answer_signature in _canonical_answer_signatures(canonical_answer):
            if _contains_normalized_sequence(prompt_signature, answer_signature):
                raise AppendRefused("canonical-answer signature remains in cleaned user prompt")
    return prompt


def _validated_mcq_prompt_answer(
    source: dict[str, Any],
    *,
    clean_prompt: str,
    canonical_answer: str,
    corrected: bool,
    reviewed_pdf_transcription: bool = False,
) -> bool:
    options = source.get("options") or []
    by_label = {
        str(option.get("label") or "").strip().upper(): str(
            option.get("text") or ""
        ).strip()
        for option in options
        if isinstance(option, dict)
    }
    if set(by_label) != {"A", "B", "C", "D"}:
        parsed = _marked_options(str(source.get("question_text") or ""))
        if set(parsed) == {"A", "B", "C", "D"}:
            by_label = parsed
    clean_by_label = _marked_options(clean_prompt)
    if set(clean_by_label) != {"A", "B", "C", "D"} or any(
        not value for value in clean_by_label.values()
    ):
        return False
    answer_match = re.match(
        r"\s*(?:OPTION\s+)?([A-D])(?:\s*[.):\-]|\s+)",
        canonical_answer.upper(),
    )
    if answer_match is None:
        return False
    answer_label = answer_match.group(1)
    option_text = _loose_math_signature(clean_by_label[answer_label])
    if not option_text or not _contains_normalized_sequence(
        _loose_math_signature(canonical_answer), option_text
    ):
        return False
    source_label = str(source.get("correct_answer") or "").strip().upper()

    # Some Cheetah PDFs (notably 2025) have a broken embedded text layer: the source row
    # retains the publisher's answer label, but its option expressions are blank.  A review
    # may use the visibly rendered PDF to transcribe all four options.  Keep that exception
    # narrow and explicit so an ordinary ledger cannot invent options merely to bypass the
    # answer-leak guard.
    source_options_complete = set(by_label) == {"A", "B", "C", "D"} and all(
        _loose_math_signature(value) for value in by_label.values()
    )
    if not source_options_complete:
        return (
            reviewed_pdf_transcription
            and source_label in {"A", "B", "C", "D"}
            and (corrected or source_label == answer_label)
        )

    for label in by_label:
        source_signature = _loose_math_signature(by_label[label])
        clean_signature = _loose_math_signature(clean_by_label[label])
        if not source_signature or not clean_signature:
            return False
        if _token_containment(source_signature, clean_signature) < 0.6:
            source_tokens = source_signature.split()
            clean_tokens = clean_signature.split()
            if not (
                all(token.isdigit() or token == "minus" for token in source_tokens)
                and all(token.isdigit() or token == "minus" for token in clean_tokens)
                and "".join(source_tokens) == "".join(clean_tokens)
            ):
                return False
    return not (
        source_label in by_label and source_label != answer_label and not corrected
    )


def _source_prompt_evidence(source: dict[str, Any]) -> str:
    """Return all prompt-side text retained by the collector.

    Older Cheetah multipart free-response blocks were once misclassified as A-D options.  A
    reviewed clean prompt may therefore be reconstructed from both ``question_text`` and the
    retained option texts, but never from answer-side material.
    """

    parts = [str(source.get("question_text") or "")]
    for option in source.get("options") or []:
        if not isinstance(option, dict):
            continue
        label = str(option.get("label") or "").strip()
        text = str(option.get("text") or "").strip()
        if label or text:
            parts.append(f"{label}. {text}".strip())
    return "\n".join(part for part in parts if part.strip())


def _validate_cheetah_text_only_review(
    entry: dict[str, Any], source: dict[str, Any], *, record_id: str
) -> None:
    if (source.get("source") or {}).get("source_type") != "cheetah_pdf":
        raise AppendRefused(
            f"PDF text-only review is only supported for Cheetah rows: {record_id}"
        )
    if source.get("assets"):
        raise AppendRefused(f"PDF review has unresolved source assets: {record_id}")
    if entry.get("all_required_assets_resolved") is not True:
        raise AppendRefused(f"PDF review did not resolve every required asset: {record_id}")
    if entry.get("visual_dependency_status") != _CHEETAH_TEXT_ONLY_STATUS:
        raise AppendRefused(f"PDF review is not explicitly text-only: {record_id}")
    if not str(entry.get("clean_prompt") or "").strip():
        raise AppendRefused(f"PDF review lacks an explicitly reviewed clean prompt: {record_id}")
    source_meta = source.get("source") or {}
    expected_question = str(source_meta.get("local_question_file") or "")
    expected_answer = str(source_meta.get("local_answer_file") or "")
    if str(entry.get("pdf_question_file") or "") != expected_question:
        raise AppendRefused(f"PDF question evidence does not match the source row: {record_id}")
    if str(entry.get("pdf_answer_file") or "") != expected_answer:
        raise AppendRefused(f"PDF answer evidence does not match the source row: {record_id}")


def _compile_review_entry(
    entry: dict[str, Any], source: dict[str, Any]
) -> dict[str, Any] | None:
    payload = _ledger_entry_payload(entry)
    evidence = entry.get("evidence_summary", entry.get("verification_evidence"))
    source_origin = entry.get("source_answer_origin")
    decision = _review_decision(entry)
    if decision not in APPROVED_DECISIONS and not decision.startswith("exclude_"):
        raise AppendRefused(f"invalid review decision for {entry.get('record_id')!r}")
    if decision.startswith("exclude_"):
        if not str(entry.get("record_id") or "").strip():
            raise AppendRefused("exclusion review has a blank record ID")
        if not str(evidence or "").strip():
            raise AppendRefused(
                f"exclusion review for {entry['record_id']!r} has blank evidence"
            )
        return None
    if source_origin is None and "clean_prompt" in entry:
        source_origin = "publisher_worked_solution_in_record"
    for field in (
        "record_id",
        "canonical_answer",
        "worked_solution",
        "verification_method",
    ):
        if not str(entry.get(field, "")).strip():
            raise AppendRefused(f"review entry for {entry.get('record_id')!r} has blank {field}")
    if not str(evidence or "").strip():
        raise AppendRefused(
            f"review entry for {entry.get('record_id')!r} has blank verification evidence"
        )
    if not str(source_origin or "").strip():
        raise AppendRefused(
            f"review entry for {entry.get('record_id')!r} has blank source answer origin"
        )
    if not isinstance(entry.get("correction_applied"), bool):
        raise AppendRefused(f"review entry has non-boolean correction flag: {entry['record_id']}")
    split_correction_provenance = any(
        field in entry
        for field in ("prompt_correction_applied", "answer_correction_applied")
    )
    if split_correction_provenance:
        if not isinstance(entry.get("prompt_correction_applied"), bool) or not isinstance(
            entry.get("answer_correction_applied"), bool
        ):
            raise AppendRefused(
                f"split correction provenance is incomplete for {entry['record_id']}"
            )
        prompt_correction_applied = entry["prompt_correction_applied"]
        answer_correction_applied = entry["answer_correction_applied"]
    else:
        prompt_correction_applied = False
        answer_correction_applied = entry["correction_applied"]
    if entry["correction_applied"] is not (
        prompt_correction_applied or answer_correction_applied
    ):
        raise AppendRefused(
            f"legacy and split correction flags disagree for {entry['record_id']}"
        )
    correction_origin = entry.get("correction_origin")
    source_is_cheetah_pdf = (
        (source.get("source") or {}).get("source_type") == "cheetah_pdf"
    )
    if (
        entry["correction_applied"]
        and (split_correction_provenance or source_is_cheetah_pdf)
        and not str(correction_origin or "").strip()
    ):
        raise AppendRefused(
            f"correction lacks an explicit origin for {entry['record_id']}"
        )
    expected_decision = (
        "approve_corrected_verified"
        if entry["correction_applied"]
        else "approve_verified"
    )
    if decision != expected_decision:
        raise AppendRefused(
            f"review decision/correction flag mismatch for {entry['record_id']}"
        )
    if "content_quality_approved" in entry and entry["content_quality_approved"] is not True:
        raise AppendRefused(f"published-row review is not quality approved: {entry['record_id']}")
    if "subject" in entry and entry["subject"] != source.get("subject"):
        raise AppendRefused(f"review subject does not match source: {entry['record_id']}")
    if "year" in entry and entry["year"] != source.get("year"):
        raise AppendRefused(f"review year does not match source: {entry['record_id']}")
    if source.get("assets"):
        raise AppendRefused(f"approved review has unresolved visual assets: {entry['record_id']}")
    answer = str(entry["canonical_answer"]).strip()
    prompt_source = str(entry.get("clean_prompt") or source.get("question_text") or "")
    source_prompt_evidence = _source_prompt_evidence(source)
    reviewed_pdf_transcription = (
        entry.get("visual_dependency_status") == _CHEETAH_TEXT_ONLY_STATUS
        and entry.get("content_recovery_method")
        in {"rendered_pdf_visual_transcription", "rendered_pdf_ocr_and_visual_review"}
    )
    minimum_prompt_containment = 0.3 if reviewed_pdf_transcription else 0.5
    if entry.get("clean_prompt") and _token_containment(
        prompt_source, source_prompt_evidence
    ) < minimum_prompt_containment:
        raise AppendRefused(f"clean prompt does not match its source row: {entry['record_id']}")
    allow_option_answer = _validated_mcq_prompt_answer(
        source,
        clean_prompt=prompt_source,
        canonical_answer=answer,
        corrected=answer_correction_applied,
        reviewed_pdf_transcription=reviewed_pdf_transcription,
    )
    prompt = _clean_source_prompt(
        prompt_source,
        canonical_answer=answer,
        allow_answer_option_in_prompt=allow_option_answer,
    )
    if not prompt:
        raise AppendRefused(f"approved review has an empty clean prompt: {entry['record_id']}")
    solution = str(entry["worked_solution"]).strip()
    completion = f"{solution}\n\nFinal answer: {answer}"
    if not solution or not answer:
        raise AppendRefused(f"approved review has an empty answer: {entry['record_id']}")
    if _UNRESOLVED_ASSET.search(prompt) or _UNRESOLVED_ASSET.search(completion):
        raise AppendRefused(f"unresolved asset marker remains: {entry['record_id']}")
    if entry.get("visual_dependency_status") == _CHEETAH_TEXT_ONLY_STATUS and (
        _UNRESOLVED_VISUAL_DEPENDENCY.search(prompt)
        or _UNRESOLVED_VISUAL_DEPENDENCY.search(solution)
    ):
        raise AppendRefused(
            f"text-only PDF review still references a visual dependency: {entry['record_id']}"
        )
    if _PDF_EXTRACTION_ARTIFACT.search(prompt) or _PDF_EXTRACTION_ARTIFACT.search(solution):
        raise AppendRefused(f"PDF extraction artifact remains: {entry['record_id']}")
    if len(prompt) > 6000 or len(solution) > 6000:
        raise AppendRefused(f"reviewed PDF row exceeds the conservative text limit: {entry['record_id']}")
    source_origin = str(source_origin)
    if source_origin not in ALLOWED_SOURCE_ANSWER_ORIGINS:
        raise AppendRefused(f"invalid source answer origin: {entry['record_id']}")
    _validate_source_answer_origin(
        source,
        source_origin=source_origin,
        record_id=str(entry["record_id"]),
    )
    if source_origin == "none_in_record":
        answer_origin = "independently_solved_missing_answer"
        source_answer_match: bool | None = None
    elif answer_correction_applied:
        answer_origin = "corrected_publisher_answer"
        source_answer_match = False
    else:
        answer_origin = "publisher_answer_independently_verified"
        source_answer_match = True
    supplied_match = entry.get("source_answer_match", source_answer_match)
    if supplied_match is not source_answer_match:
        raise AppendRefused(f"source answer match is inconsistent: {entry['record_id']}")
    if answer_origin not in ALLOWED_ANSWER_ORIGINS:
        raise AppendRefused(f"invalid derived answer origin: {entry['record_id']}")
    compiled = {
        "record_id": entry["record_id"],
        "decision": decision,
        "source_record_sha256": _source_record_hash(source),
        "ledger_entry_sha256": canonical_json_sha256(payload),
        "review_ledger_path": entry.get(f"{_LEDGER_META_PREFIX}path"),
        "review_ledger_sha256": entry.get(f"{_LEDGER_META_PREFIX}sha256"),
        "prompt": prompt,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "completion": completion,
        "answer": answer,
        "topic": "waec_exam_practice",
        "difficulty": "standard",
        "format": "free_response",
        "pedagogy": "worked_solution",
        "reviewer": REVIEWER,
        "reviewer_type": REVIEWER_TYPE,
        "reviewed_at": REVIEWED_AT,
        "review_method": str(entry["verification_method"]),
        "review_evidence": str(evidence),
        "rubric_version": RUBRIC_VERSION,
        "answer_origin": answer_origin,
        "source_answer_origin": source_origin,
        "source_answer_match": source_answer_match,
        "correction_applied": entry["correction_applied"],
        "prompt_correction_applied": prompt_correction_applied,
        "answer_correction_applied": answer_correction_applied,
        "correction_origin": correction_origin,
        "correction_evidence": str(evidence) if entry["correction_applied"] else None,
        "independent_answer_verified": True,
        "prompt_answer_leak_checked": True,
        "all_required_assets_resolved": entry.get("all_required_assets_resolved", True),
        "visual_dependency_status": entry.get(
            "visual_dependency_status", "not_applicable_no_assets"
        ),
        "content_recovery_method": entry.get(
            "content_recovery_method", "conservative_question_boundary_extraction"
        ),
        "pdf_question_file": entry.get("pdf_question_file"),
        "pdf_answer_file": entry.get("pdf_answer_file"),
        "audit_history": {
            key: entry[key]
            for key in (
                "rights_status",
                "training_eligible",
                "content_quality_approved",
                "source_answer_match_scope",
                "normalization_applied",
            )
            if key in entry
        },
    }
    review_id_payload = {
        key: value for key, value in compiled.items() if key != "review_ledger_path"
    }
    compiled["review_id"] = REVIEW_PREFIX + canonical_json_sha256(review_id_payload)[:24]
    return compiled


def _private_registry(corpus_sha256: str) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    revision = f"sha256:{corpus_sha256}"
    registry: dict[str, dict[str, Any]] = {}
    for source in SOURCE_POLICY.values():
        registry[source["source_id"]] = {
            **source,
            "id": source["source_id"],
            "revision": revision,
            "status": "enabled_silver",
            "allowed_splits": ["private_training"],
            "allowed_verification_statuses": ["model_assisted_reviewed"],
            "warehouse_training_eligible": True,
            "sft_approval_scope": "row_only",
            "synthetic": False,
        }
    policy = {"allowed_licenses": sorted({row["license"] for row in registry.values()})}
    return registry, policy


def _make_token_counter() -> QwenTokenCounter:
    return QwenTokenCounter(max_sequence_tokens=DEFAULT_MAX_SEQUENCE_TOKENS)


def build_approved_records(
    *,
    corpus_rows: list[dict[str, Any]],
    corpus_sha256: str,
    review_rows: list[dict[str, Any]],
    review_sha256: str,
    review_sources: list[dict[str, Any]],
    attestation: dict[str, Any],
    attestation_sha256: str,
    token_counter: Any | None = None,
    holdouts: HoldoutIndex | None = None,
) -> list[dict[str, Any]]:
    _validate_attestation(
        attestation,
        corpus_sha256=corpus_sha256,
        corpus_row_count=len(corpus_rows),
        review_bundle_sha256=review_sha256,
        review_sources=review_sources,
    )
    by_id: dict[str, dict[str, Any]] = {}
    for row in corpus_rows:
        record_id = str(row.get("record_id") or "")
        if not record_id or record_id in by_id:
            raise AppendRefused(f"missing or duplicate corpus record ID: {record_id!r}")
        by_id[record_id] = row
    reviews: dict[str, list[dict[str, Any]]] = {}
    for entry in review_rows:
        record_id = str(entry.get("record_id") or "")
        if record_id not in by_id:
            raise AppendRefused(f"review targets an unknown corpus row: {record_id!r}")
        reviews.setdefault(record_id, []).append(entry)
    registry, source_policy = _private_registry(corpus_sha256)
    holdouts = holdouts or HoldoutIndex.from_repository()
    token_counter = token_counter or _make_token_counter()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    schema_validator = Draft202012Validator(schema)

    overlap_adjudications: dict[str, dict[str, Any]] = {}
    for adjudication in attestation["overlap_adjudications"]:
        record_id = str(adjudication.get("record_id") or "")
        if not record_id or record_id in overlap_adjudications:
            raise AppendRefused("overlap adjudications contain a missing or duplicate record ID")
        overlap_adjudications[record_id] = adjudication
    used_overlap_adjudications: set[str] = set()

    records: list[dict[str, Any]] = []
    for record_id in sorted(reviews):
        source = by_id[record_id]
        source_hash = _source_record_hash(source)
        for entry in reviews[record_id]:
            if entry.get("source_corpus_sha256") != corpus_sha256:
                raise AppendRefused(f"review is not bound to the corpus snapshot: {record_id}")
            if entry.get("source_record_sha256") != source_hash:
                raise AppendRefused(f"review is not bound to the exact source row: {record_id}")
            if _review_decision(entry) in APPROVED_DECISIONS:
                content_status = str(source.get("content_status") or "")
                if content_status == "incomplete":
                    warnings = set(source.get("extraction_warnings") or [])
                    if not str(entry.get("clean_prompt") or "").strip():
                        raise AppendRefused(
                            f"incomplete source lacks an explicitly reviewed clean prompt: {record_id}"
                        )
                    source_type = str((source.get("source") or {}).get("source_type") or "")
                    cheetah_warnings = {
                        "pdf_text_requires_visual_verification",
                        "question_text_missing",
                    }
                    ordinary_warnings = {
                        "answer_section_missing",
                        "published_answer_not_identified",
                    }
                    if source_type == "cheetah_pdf" and warnings and warnings.issubset(
                        cheetah_warnings
                    ):
                        _validate_cheetah_text_only_review(entry, source, record_id=record_id)
                    elif not warnings or not warnings.issubset(ordinary_warnings):
                        raise AppendRefused(
                            f"incomplete source has unresolved extraction warnings: {record_id}"
                        )
                elif content_status == "needs_visual_review":
                    warnings = set(source.get("extraction_warnings") or [])
                    if warnings != {"pdf_text_requires_visual_verification"}:
                        raise AppendRefused(
                            f"PDF source has unresolved extraction warnings: {record_id}"
                        )
                    _validate_cheetah_text_only_review(entry, source, record_id=record_id)
                elif content_status != "complete":
                    raise AppendRefused(
                        f"approved source has unsupported content status {content_status!r}: "
                        f"{record_id}"
                    )
        compiled_rows = [_compile_review_entry(entry, source) for entry in reviews[record_id]]
        approved = [row for row in compiled_rows if row is not None]
        if approved and len(approved) != len(compiled_rows):
            raise AppendRefused(f"conflicting approval and exclusion decisions: {record_id}")
        if not approved:
            continue
        first = approved[0]
        for candidate in approved[1:]:
            if (
                first["source_answer_match"] is not candidate["source_answer_match"]
                or first["correction_applied"] is not candidate["correction_applied"]
            ):
                raise AppendRefused(f"overlapping reviews disagree on provenance: {record_id}")
        normalized_answers = {normalize_text(row["answer"]) for row in approved}
        if len(approved) > 1 and len(normalized_answers) > 1:
            adjudication = overlap_adjudications.get(record_id)
            if adjudication is None:
                raise AppendRefused(f"overlapping reviews disagree on answer: {record_id}")
            if adjudication.get("status") != "independently_equivalent_answers":
                raise AppendRefused(f"invalid overlap adjudication status: {record_id}")
            actual_hashes = {row["ledger_entry_sha256"] for row in approved}
            expected_hashes = {
                adjudication.get("preferred_entry_sha256"),
                adjudication.get("corroborating_entry_sha256"),
            }
            if actual_hashes != expected_hashes:
                raise AppendRefused(f"overlap adjudication does not bind the reviews: {record_id}")
            preferred_hash = adjudication["preferred_entry_sha256"]
            compiled = next(
                row for row in approved if row["ledger_entry_sha256"] == preferred_hash
            )
            used_overlap_adjudications.add(record_id)
        else:
            compiled = max(
                approved,
                key=lambda row: (
                    bool(row["audit_history"].get("content_quality_approved")),
                    len(row["prompt"]),
                    row["review_id"],
                ),
            )
        overlap_receipts = [
            {
                "review_id": row["review_id"],
                "review_ledger_path": row["review_ledger_path"],
                "review_ledger_sha256": row["review_ledger_sha256"],
                "ledger_entry_sha256": row["ledger_entry_sha256"],
                "source_record_sha256": row["source_record_sha256"],
                "prompt_sha256": row["prompt_sha256"],
            }
            for row in sorted(approved, key=lambda row: row["review_id"])
        ]
        prompt = str(compiled["prompt"])
        source_type = str((source.get("source") or {}).get("source_type") or "")
        source_meta = SOURCE_POLICY.get(source_type)
        if source_meta is None:
            raise AppendRefused(f"unsupported source type for {record_id}: {source_type!r}")
        source_notice = str((source.get("source") or {}).get("copyright_notice") or "")
        if source_notice != source_meta["license"]:
            raise AppendRefused(f"publisher notice changed or is missing for {record_id}")
        subject = SUBJECT_MAP.get(str(source.get("subject") or ""))
        if subject is None:
            raise AppendRefused(f"unsupported subject for {record_id}")
        source_row_id = f"private_training:{record_id}"
        answer = str(compiled["answer"])
        record = make_record(
            prompt=prompt,
            completion=str(compiled["completion"]),
            answer=answer,
            subject=subject,
            topic=str(compiled["topic"]),
            difficulty=str(compiled["difficulty"]),
            response_format=str(compiled["format"]),
            pedagogy=str(compiled["pedagogy"]),
            mode="chat",
            split="train",
            source_id=source_meta["source_id"],
            source_revision=f"sha256:{corpus_sha256}",
            source_split="private_training",
            source_row_id=source_row_id,
            semantic_cluster_id=f"row:{source_row_id}",
            license_name=source_meta["license"],
            synthetic=False,
            transform=ADAPTER_VERSION,
            country="multi-country-west-africa",
            curriculum_authority="WAEC/WASSCE",
            curriculum_version=f"private-corpus-sha256:{corpus_sha256}",
            exam_era=str(source.get("year") or "unknown"),
            alignment=(
                "private local fine-tuning WAEC item; model-assisted exact-row independent "
                "answer verification"
            ),
            verification={
                "status": "model_assisted_reviewed",
                "method": REVIEW_METHOD,
                "expected": answer,
                "observed": answer,
                "verifier_version": ADAPTER_VERSION,
                "training_eligible": True,
                "review_id": compiled["review_id"],
                "review_decision": compiled["decision"],
                "review_ledger_sha256": compiled["review_ledger_sha256"],
                "review_ledger_path": compiled["review_ledger_path"],
                "review_bundle_sha256": review_sha256,
                "reviewer": compiled["reviewer"],
                "reviewer_type": compiled["reviewer_type"],
                "reviewed_at": compiled["reviewed_at"],
                "review_method": compiled["review_method"],
                "review_evidence": compiled["review_evidence"],
                "rubric_version": compiled["rubric_version"],
                "source_record_sha256": compiled["source_record_sha256"],
                "ledger_entry_sha256": compiled["ledger_entry_sha256"],
                "clean_prompt_sha256": compiled["prompt_sha256"],
                "answer_origin": compiled["answer_origin"],
                "source_answer_origin": compiled["source_answer_origin"],
                "source_answer_match": compiled["source_answer_match"],
                "correction_applied": compiled["correction_applied"],
                "prompt_correction_applied": compiled[
                    "prompt_correction_applied"
                ],
                "answer_correction_applied": compiled[
                    "answer_correction_applied"
                ],
                "correction_origin": compiled["correction_origin"],
                "correction_evidence": compiled["correction_evidence"],
                "independent_answer_verified": compiled[
                    "independent_answer_verified"
                ],
                "all_required_assets_resolved": compiled[
                    "all_required_assets_resolved"
                ],
                "visual_dependency_status": compiled["visual_dependency_status"],
                "content_recovery_method": compiled["content_recovery_method"],
                "pdf_question_file": compiled["pdf_question_file"],
                "pdf_answer_file": compiled["pdf_answer_file"],
                "prompt_answer_leak_checked": True,
                "private_training_attestation_id": attestation["attestation_id"],
                "private_training_attestation_sha256": attestation_sha256,
                "private_training_adjudication_status": attestation[
                    "row_eligibility_adjudication"
                ]["status"],
                "training_eligibility_basis": "project_owner_private_training_adjudication",
                "publisher_permission_asserted": False,
                "publisher_license_unchanged": True,
                "publisher_copyright_notice": source_notice,
                "publisher_page_url": str(
                    (source.get("source") or {}).get("page_url") or ""
                ),
                "audit_history": compiled["audit_history"],
                "overlap_review_receipts": overlap_receipts,
            },
            holdouts=holdouts,
            source_task=prompt,
        )
        if record is None:
            raise AppendRefused(f"approved prompt overlaps a sealed holdout: {record_id}")
        token_counter.annotate(record)
        errors = validate_record(
            record,
            source_registry=registry,
            source_policy=source_policy,
            holdouts=holdouts,
            token_counter=token_counter,
        )
        schema_errors = sorted(
            schema_validator.iter_errors(record), key=lambda error: list(error.path)
        )
        if errors or schema_errors:
            details = errors + [error.message for error in schema_errors]
            raise AppendRefused(f"adapted record {record_id} is invalid: {details}")
        records.append(record)
    unused_adjudications = sorted(set(overlap_adjudications) - used_overlap_adjudications)
    if unused_adjudications:
        raise AppendRefused(
            "unused overlap adjudications: " + ", ".join(unused_adjudications)
        )
    if not records:
        raise AppendRefused("review ledger contains no approved rows")
    ids = [row["id"] for row in records]
    prompts = [normalize_text(row["prompt"]) for row in records]
    if len(ids) != len(set(ids)) or len(prompts) != len(set(prompts)):
        raise AppendRefused("approved rows contain duplicate IDs or normalized prompts")
    return records


def _dataset_fingerprint(shards: list[dict[str, Any]]) -> str:
    return hashlib.sha256(
        "\n".join(str(shard["sha256"]) for shard in shards).encode("ascii")
    ).hexdigest()


def _safe_child(root: Path, relative: str) -> Path:
    if not relative or Path(relative).is_absolute():
        raise AppendRefused(f"unsafe artifact path: {relative!r}")
    root = root.resolve()
    path = (root / relative).resolve()
    if root not in path.parents:
        raise AppendRefused(f"artifact path escapes target directory: {relative!r}")
    return path


@dataclass
class VerifiedTarget:
    path: Path
    kind: str
    manifest: dict[str, Any]
    manifest_raw: bytes
    manifest_sha256: str
    next_part: int


def _verify_target(
    path: Path, *, new_ids: set[str], new_prompt_hashes: set[str], new_task_hashes: set[str]
) -> VerifiedTarget:
    path = path.resolve()
    manifest_path = path / "manifest.json"
    manifest, raw, manifest_sha = _load_json(manifest_path)
    if manifest_bytes(manifest) != raw:
        raise AppendRefused(f"manifest is not in canonical repository format: {manifest_path}")
    if manifest.get("profile") == "warehouse":
        kind = "warehouse"
    elif manifest.get("dataset_name") == "muta-stem-sft-v2-selected":
        kind = "sft"
    else:
        raise AppendRefused(f"unsupported target artifact: {path}")
    shards = manifest.get("shards")
    if not isinstance(shards, list) or not shards:
        raise AppendRefused(f"target has no shard inventory: {path}")
    listed = [str(item.get("path") or "") for item in shards]
    if len(listed) != len(set(listed)):
        raise AppendRefused(f"target repeats a shard path: {path}")
    actual = {item.name for item in path.glob("part-*.jsonl")}
    if actual != set(listed):
        raise AppendRefused(
            f"target has unlisted or missing shards: {path}; "
            f"extra={sorted(actual - set(listed))}, missing={sorted(set(listed) - actual)}"
        )
    if _dataset_fingerprint(shards) != manifest.get("dataset_fingerprint_sha256"):
        raise AppendRefused(f"manifest dataset fingerprint is inconsistent: {path}")

    observed_rows = 0
    for receipt in shards:
        shard_path = _safe_child(path, str(receipt["path"]))
        digest = hashlib.sha256()
        rows = 0
        with shard_path.open("rb") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                digest.update(raw_line)
                if not raw_line.strip():
                    continue
                rows += 1
                try:
                    row = json.loads(raw_line)
                except json.JSONDecodeError as exc:
                    raise AppendRefused(
                        f"invalid base JSON at {shard_path}:{line_number}: {exc}"
                    ) from exc
                if row.get("id") in new_ids:
                    raise AppendRefused(f"new record ID already exists in {path}: {row['id']}")
                prompt = row.get("prompt")
                if isinstance(prompt, str) and normalized_sha256(prompt) in new_prompt_hashes:
                    raise AppendRefused(f"new normalized prompt already exists in {path}")
                task_hash = (row.get("contamination") or {}).get("source_task_sha256")
                if task_hash in new_task_hashes:
                    raise AppendRefused(f"new source task already exists in {path}")
        if rows != receipt.get("rows"):
            raise AppendRefused(f"base shard row-count mismatch: {shard_path}")
        if shard_path.stat().st_size != receipt.get("bytes"):
            raise AppendRefused(f"base shard byte-count mismatch: {shard_path}")
        if digest.hexdigest() != receipt.get("sha256"):
            raise AppendRefused(f"base shard hash mismatch: {shard_path}")
        observed_rows += rows
    if observed_rows != manifest.get("row_count"):
        raise AppendRefused(f"target row count differs from shard inventory: {path}")
    indices = []
    for name in listed:
        match = _PART_INDEX.match(name)
        if match:
            indices.append(int(match.group(1)))
    if not indices:
        raise AppendRefused(f"target shard names have no part index: {path}")
    return VerifiedTarget(path, kind, manifest, raw, manifest_sha, max(indices) + 1)


def _increment(counter: dict[str, Any], key: str, amount: int = 1) -> None:
    counter[key] = int(counter.get(key, 0)) + amount


def _token_bucket(count: int) -> str:
    if count <= 128:
        return "0001-0128"
    if count <= 256:
        return "0129-0256"
    if count <= 512:
        return "0257-0512"
    if count <= 768:
        return "0513-0768"
    return "0769-plus"


def _record_counters(records: list[dict[str, Any]]) -> dict[str, Counter[str]]:
    counters = {
        key: Counter()
        for key in (
            "source",
            "source_split",
            "subject",
            "topic",
            "difficulty",
            "pedagogy",
            "formula_template_method",
            "curriculum_alignment",
            "source_subject_pedagogy",
            "verification",
            "split",
            "token_buckets",
        )
    }
    for row in records:
        provenance = row["provenance"]
        source_id = provenance["source_id"]
        counters["source"][source_id] += 1
        counters["source_split"][f"{source_id} :: {provenance['source_split']}"] += 1
        for key in ("subject", "topic", "difficulty", "pedagogy", "split"):
            counters[key][row[key]] += 1
        counters["formula_template_method"][
            f"method:{row['verification']['method']}"
        ] += 1
        counters["curriculum_alignment"][row["curriculum"]["alignment"]] += 1
        counters["source_subject_pedagogy"][
            f"{source_id} :: {row['subject']} :: {row['pedagogy']}"
        ] += 1
        counters["verification"][row["verification"]["status"]] += 1
        counters["token_buckets"][_token_bucket(row["tokenization"]["sequence_tokens"])] += 1
    return counters


def _merge_counter(target: dict[str, Any], delta: Counter[str]) -> None:
    for key, amount in sorted(delta.items()):
        _increment(target, key, amount)


def _counter_total(value: dict[str, Any], *, label: str) -> int:
    total = 0
    for key, count in value.items():
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise AppendRefused(f"{label}.{key} is not a non-negative integer count")
        total += count
    return total


def _nested_counter_total(value: dict[str, Any], *, label: str) -> int:
    total = 0
    for source_id, splits in value.items():
        if not isinstance(splits, dict):
            raise AppendRefused(f"{label}.{source_id} is not a mapping")
        for split, counts in splits.items():
            if not isinstance(counts, dict):
                raise AppendRefused(f"{label}.{source_id}.{split} is not a mapping")
            total += _counter_total(counts, label=f"{label}.{source_id}.{split}")
    return total


def _assert_manifest_totals(manifest: dict[str, Any], *, kind: str) -> None:
    expected = int(manifest["row_count"])
    if sum(int(shard["rows"]) for shard in manifest["shards"]) != expected:
        raise AppendRefused(f"{kind} shard counts do not sum to row_count")
    if kind == "warehouse":
        if _counter_total(manifest["requested_counts"], label="requested_counts") != expected:
            raise AppendRefused("warehouse requested_counts do not sum to row_count")
        if sum(int(source["rows"]) for source in manifest["sources"]) != expected:
            raise AppendRefused("warehouse source rows do not sum to row_count")
        if (
            _counter_total(
                manifest["training_disposition_totals"],
                label="training_disposition_totals",
            )
            != expected
        ):
            raise AppendRefused("warehouse training dispositions do not sum to row_count")
        for key in (
            "source",
            "source_split",
            "subject",
            "topic",
            "difficulty",
            "pedagogy",
            "formula_template_method",
            "curriculum_alignment",
            "source_subject_pedagogy",
            "verification",
            "eligibility",
            "audit_eligibility",
            "split",
        ):
            if _counter_total(manifest["counts"][key], label=f"counts.{key}") != expected:
                raise AppendRefused(f"warehouse counts.{key} does not sum to row_count")
        matrix = manifest["counts"]["source_warehouse_split_eligibility"]
        if _nested_counter_total(matrix, label="counts.source_warehouse_split_eligibility") != expected:
            raise AppendRefused("warehouse eligibility matrix does not sum to row_count")
        if _counter_total(manifest["tokenization"]["buckets"], label="tokenization.buckets") != expected:
            raise AppendRefused("warehouse token buckets do not sum to row_count")
        return
    for key in ("source", "subject", "pedagogy", "authorization"):
        if _counter_total(manifest["counts"][key], label=f"counts.{key}") != expected:
            raise AppendRefused(f"SFT counts.{key} does not sum to row_count")
    for key in ("source", "subject", "pedagogy"):
        if _counter_total(
            manifest["required_margins"][key], label=f"required_margins.{key}"
        ) != expected:
            raise AppendRefused(f"SFT required_margins.{key} does not sum to row_count")
    selected = manifest["source_attribution"]["selected_count_by_source"]
    if _counter_total(selected, label="source_attribution.selected_count_by_source") != expected:
        raise AppendRefused("SFT source attribution does not sum to row_count")


def _set_with_reverse(
    manifest: dict[str, Any], reverse: list[dict[str, Any]], key: str, value: Any
) -> None:
    reverse.append(
        {
            "top_level_key": key,
            "existed": key in manifest,
            "value": copy.deepcopy(manifest.get(key)),
        }
    )
    manifest[key] = value


def _apply_reverse_patch(
    manifest: dict[str, Any], reverse: list[dict[str, Any]]
) -> dict[str, Any]:
    restored = copy.deepcopy(manifest)
    for item in reversed(reverse):
        if item["existed"]:
            restored[item["top_level_key"]] = copy.deepcopy(item["value"])
        else:
            restored.pop(item["top_level_key"], None)
    return restored


def _source_manifest_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(row["provenance"]["source_id"] for row in records)
    by_id = {row["source_id"]: row for row in SOURCE_POLICY.values()}
    revision = records[0]["provenance"]["source_revision"]
    return [
        {
            "id": source_id,
            "name": by_id[source_id]["name"],
            "url": by_id[source_id]["url"],
            "revision": revision,
            "license": by_id[source_id]["license"],
            "license_url": by_id[source_id]["license_url"],
            "source_kind": by_id[source_id]["source_kind"],
            "registry_status": "private_exact_row_model_assisted_programmatic_review",
            "rows": count,
        }
        for source_id, count in sorted(counts.items())
    ]


def _append_metadata(
    *,
    append_id: str,
    records: list[dict[str, Any]],
    shard: dict[str, Any],
    corpus_path: Path,
    corpus_sha256: str,
    review_sources: list[dict[str, Any]],
    review_bundle_sha256: str,
    attestation_path: Path,
    attestation: dict[str, Any],
    attestation_sha256: str,
    tool_sha256: str,
) -> dict[str, Any]:
    source_counts = Counter(row["provenance"]["source_id"] for row in records)
    return {
        "append_id": append_id,
        "adapter_version": ADAPTER_VERSION,
        "attestation_recorded_at": attestation["recorded_at"],
        "row_count": len(records),
        "source_counts": dict(sorted(source_counts.items())),
        "review_receipts": [
            {
                "record_id": row["provenance"]["source_row_id"].removeprefix(
                    "private_training:"
                ),
                "review_id": row["verification"]["review_id"],
                "decision": row["verification"]["review_decision"],
                "source_record_sha256": row["verification"]["source_record_sha256"],
                "ledger_entry_sha256": row["verification"]["ledger_entry_sha256"],
                "clean_prompt_sha256": row["verification"]["clean_prompt_sha256"],
                "answer_origin": row["verification"]["answer_origin"],
                "source_answer_match": row["verification"]["source_answer_match"],
                "correction_applied": row["verification"]["correction_applied"],
                "prompt_correction_applied": row["verification"][
                    "prompt_correction_applied"
                ],
                "answer_correction_applied": row["verification"][
                    "answer_correction_applied"
                ],
                "correction_origin": row["verification"]["correction_origin"],
            }
            for row in records
        ],
        "shard": shard,
        "authorization": {
            "type": "approved_exact_row_private_training_review",
            "review_ledgers": review_sources,
            "review_bundle_sha256": review_bundle_sha256,
            "private_training_attestation": {
                "path": str(attestation_path.resolve()),
                "sha256": attestation_sha256,
                "attestation_id": attestation["attestation_id"],
                "recorded_at": attestation["recorded_at"],
                "attestor_role": attestation["attestor_role"],
                "intended_use": attestation["intended_use"],
                "artifact_handling": attestation["artifact_handling"],
                "row_eligibility_adjudication": attestation[
                    "row_eligibility_adjudication"
                ],
                "review_bindings": attestation["review_bindings"],
                "source_snapshot": attestation["source_snapshot"],
                "source_pdf_bindings": attestation.get("source_pdf_bindings", []),
                "overlap_adjudications": attestation["overlap_adjudications"],
                "rights_boundary": attestation["rights_boundary"],
            },
        },
        "publisher_licences_by_source": {
            source_id: {
                "name": next(
                    item["license"]
                    for item in SOURCE_POLICY.values()
                    if item["source_id"] == source_id
                ),
                "url": next(
                    item["license_url"]
                    for item in SOURCE_POLICY.values()
                    if item["source_id"] == source_id
                ),
                "unchanged_by_user_attestation": True,
            }
            for source_id in sorted(source_counts)
        },
        "corpus": {"path": str(corpus_path.resolve()), "sha256": corpus_sha256},
        "tool_sha256": tool_sha256,
        "distribution_warning": (
            "The user attestation records intended local fine-tuning, private WAEC practice, "
            "and competition research. It is not publisher permission and asserts no public "
            "dataset redistribution. It makes no claim about later submission or distribution "
            "of trained weights."
        ),
    }


def _update_warehouse_manifest(
    manifest: dict[str, Any],
    *,
    records: list[dict[str, Any]],
    shard: dict[str, Any],
    append_metadata: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    updated = copy.deepcopy(manifest)
    reverse: list[dict[str, Any]] = []
    counters = _record_counters(records)
    new_shards = [*updated["shards"], shard]
    _set_with_reverse(updated, reverse, "shards", new_shards)
    _set_with_reverse(
        updated, reverse, "row_count", int(updated["row_count"]) + len(records)
    )
    _set_with_reverse(
        updated, reverse, "dataset_fingerprint_sha256", _dataset_fingerprint(new_shards)
    )

    requested = copy.deepcopy(updated.get("requested_counts") or {})
    _merge_counter(requested, counters["source"])
    _set_with_reverse(updated, reverse, "requested_counts", requested)

    sources = copy.deepcopy(updated.get("sources") or [])
    existing_sources = {row["id"]: row for row in sources}
    for row in _source_manifest_rows(records):
        if row["id"] in existing_sources:
            raise AppendRefused(f"warehouse already declares private source {row['id']}")
        sources.append(row)
    sources.sort(key=lambda row: row["id"])
    _set_with_reverse(updated, reverse, "sources", sources)

    semantics = copy.deepcopy(updated.get("verification_semantics_by_source") or {})
    for source_id in counters["source"]:
        semantics[source_id] = {
            "scope": "private_exact_row_model_assisted_programmatic_review",
            "independent_answer_rederivation": True,
            "reviewer_type": REVIEWER_TYPE,
            "semantic_correctness_assurance": "model_assisted_with_programmatic_checks",
            "summary": (
                "The exact final prompt, completion, and canonical answer are bound to a "
                "content-addressed compiled review receipt. Answers are independently solved "
                "or checked with the ledger's stated formal evidence; this is not human review."
            ),
        }
    _set_with_reverse(updated, reverse, "verification_semantics_by_source", semantics)

    disposition = copy.deepcopy(updated.get("training_disposition_totals") or {})
    _increment(disposition, "private_exact_row_eligible", len(records))
    _set_with_reverse(updated, reverse, "training_disposition_totals", disposition)

    counts = copy.deepcopy(updated["counts"])
    for key in (
        "source",
        "source_split",
        "subject",
        "topic",
        "difficulty",
        "pedagogy",
        "formula_template_method",
        "curriculum_alignment",
        "source_subject_pedagogy",
        "verification",
        "split",
    ):
        counts.setdefault(key, {})
        _merge_counter(counts[key], counters[key])
    counts.setdefault("eligibility", {})
    counts.setdefault("audit_eligibility", {})
    _increment(counts["eligibility"], "eligible", len(records))
    _increment(counts["audit_eligibility"], "training_eligible", len(records))
    matrix = counts.setdefault("source_warehouse_split_eligibility", {})
    clusters = counts.setdefault("semantic_cluster_count_by_source", {})
    for source_id, amount in counters["source"].items():
        train = matrix.setdefault(source_id, {}).setdefault("train", {})
        _increment(train, "training_eligible", amount)
        _increment(clusters, source_id, amount)
    _set_with_reverse(updated, reverse, "counts", counts)

    tokenization = copy.deepcopy(updated["tokenization"])
    before_rows = int(manifest["row_count"])
    old_mean = float(tokenization["mean_sequence_tokens"])
    token_values = [row["tokenization"]["sequence_tokens"] for row in records]
    tokenization["minimum_sequence_tokens"] = min(
        int(tokenization["minimum_sequence_tokens"]), min(token_values)
    )
    tokenization["maximum_sequence_tokens"] = max(
        int(tokenization["maximum_sequence_tokens"]), max(token_values)
    )
    tokenization["mean_sequence_tokens"] = round(
        (old_mean * before_rows + sum(token_values)) / (before_rows + len(records)), 6
    )
    buckets = tokenization.setdefault("buckets", {})
    _merge_counter(buckets, counters["token_buckets"])
    _set_with_reverse(updated, reverse, "tokenization", tokenization)

    warning = str(updated.get("training_warning") or "").rstrip()
    private_warning = append_metadata["distribution_warning"]
    _set_with_reverse(
        updated,
        reverse,
        "training_warning",
        f"{warning} {private_warning}".strip(),
    )
    history = copy.deepcopy(updated.get("private_training_appends") or [])
    history.append(append_metadata)
    _set_with_reverse(updated, reverse, "private_training_appends", history)
    _assert_manifest_totals(updated, kind="warehouse")
    return updated, reverse


def _update_sft_manifest(
    manifest: dict[str, Any],
    *,
    records: list[dict[str, Any]],
    shard: dict[str, Any],
    append_metadata: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if any(row["verification"].get("training_eligible") is not True for row in records):
        raise AppendRefused("selected SFT append contains a non-training-eligible row")
    updated = copy.deepcopy(manifest)
    reverse: list[dict[str, Any]] = []
    counters = _record_counters(records)
    new_shards = [*updated["shards"], shard]
    _set_with_reverse(updated, reverse, "shards", new_shards)
    _set_with_reverse(
        updated, reverse, "row_count", int(updated["row_count"]) + len(records)
    )
    _set_with_reverse(
        updated, reverse, "dataset_fingerprint_sha256", _dataset_fingerprint(new_shards)
    )

    counts = copy.deepcopy(updated["counts"])
    for key in ("source", "subject", "pedagogy"):
        counts.setdefault(key, {})
        _merge_counter(counts[key], counters[key])
    counts.setdefault("authorization", {})
    _increment(counts["authorization"], "private_exact_row_review", len(records))
    _set_with_reverse(updated, reverse, "counts", counts)

    margins = copy.deepcopy(updated["required_margins"])
    for key in ("source", "subject", "pedagogy"):
        margins.setdefault(key, {})
        _merge_counter(margins[key], counters[key])
    _set_with_reverse(updated, reverse, "required_margins", margins)

    attribution = copy.deepcopy(updated["source_attribution"])
    attribution["inventory_scope"] = "base_selector_output_before_private_training_appends"
    attribution.setdefault("selected_count_by_source", {})
    _merge_counter(attribution["selected_count_by_source"], counters["source"])
    attribution.setdefault("license_by_source", {})
    for source in _source_manifest_rows(records):
        attribution["license_by_source"][source["id"]] = {
            "name": source["license"],
            "url": source["license_url"],
            "archived_evidence": [],
            "private_training_attestation_is_not_a_publisher_license": True,
        }
    latest_attribution = {
        "append_id": append_metadata["append_id"],
        "row_count": len(records),
        "publisher_licences_by_source": append_metadata["publisher_licences_by_source"],
        "private_training_attestation": append_metadata["authorization"][
            "private_training_attestation"
        ],
        "distribution_warning": append_metadata["distribution_warning"],
    }
    attribution["private_training_append"] = latest_attribution
    attribution_history = copy.deepcopy(attribution.get("private_training_appends") or [])
    existing_pointer = manifest.get("source_attribution", {}).get("private_training_append")
    if existing_pointer and not attribution_history:
        attribution_history.append(copy.deepcopy(existing_pointer))
    if not any(
        row.get("append_id") == latest_attribution["append_id"]
        for row in attribution_history
    ):
        attribution_history.append(copy.deepcopy(latest_attribution))
    attribution["private_training_appends"] = attribution_history
    _set_with_reverse(updated, reverse, "source_attribution", attribution)

    history = copy.deepcopy(updated.get("private_training_appends") or [])
    history.append(append_metadata)
    _set_with_reverse(updated, reverse, "private_training_appends", history)
    _assert_manifest_totals(updated, kind="sft")
    return updated, reverse


@dataclass
class TargetPlan:
    target: VerifiedTarget
    shard_path: Path
    shard_bytes: bytes
    shard_receipt: dict[str, Any]
    updated_manifest: dict[str, Any]
    updated_manifest_bytes: bytes
    reverse_patch: list[dict[str, Any]]
    receipt_path: Path
    receipt_bytes: bytes


def _build_target_plan(
    target: VerifiedTarget,
    *,
    append_id: str,
    records: list[dict[str, Any]],
    shared_metadata: dict[str, Any],
) -> TargetPlan:
    shard_name = f"part-{target.next_part:05d}-private-waec-{append_id[-12:]}.jsonl"
    shard_path = target.path / shard_name
    shard_bytes = b"".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        for row in records
    )
    shard_receipt = {
        "path": shard_name,
        "rows": len(records),
        "bytes": len(shard_bytes),
        "sha256": hashlib.sha256(shard_bytes).hexdigest(),
    }
    metadata = copy.deepcopy(shared_metadata)
    metadata["shard"] = shard_receipt
    updater = _update_warehouse_manifest if target.kind == "warehouse" else _update_sft_manifest
    updated, reverse = updater(
        target.manifest,
        records=records,
        shard=shard_receipt,
        append_metadata=metadata,
    )
    updated_bytes = manifest_bytes(updated)
    restored = _apply_reverse_patch(updated, reverse)
    if manifest_bytes(restored) != target.manifest_raw:
        raise AppendRefused(f"inverse manifest patch is not byte-exact for {target.path}")
    receipt_name = f"private-waec-append-{append_id[-12:]}.receipt.json"
    receipt_path = target.path / receipt_name
    receipt = {
        "schema_version": APPEND_SCHEMA_VERSION,
        "append_id": append_id,
        "artifact_kind": target.kind,
        "before": {
            "manifest_sha256": target.manifest_sha256,
            "dataset_fingerprint_sha256": target.manifest["dataset_fingerprint_sha256"],
            "row_count": target.manifest["row_count"],
        },
        "after": {
            "manifest_sha256": hashlib.sha256(updated_bytes).hexdigest(),
            "dataset_fingerprint_sha256": updated["dataset_fingerprint_sha256"],
            "row_count": updated["row_count"],
        },
        "appended_shard": shard_receipt,
        "review_receipts": shared_metadata["review_receipts"],
        "authorization": shared_metadata["authorization"],
        "publisher_licences_by_source": shared_metadata["publisher_licences_by_source"],
        "inverse_manifest_patch": reverse,
        "rollback": {
            "order": [
                "verify current manifest SHA-256 equals after.manifest_sha256",
                "apply inverse_manifest_patch and verify before.manifest_sha256",
                "atomically replace manifest.json with the verified restored bytes",
                f"remove only {shard_name}",
                f"remove only {receipt_name}",
            ],
            "base_shard_backup_required": False,
        },
    }
    receipt_bytes = manifest_bytes(receipt)
    return TargetPlan(
        target=target,
        shard_path=shard_path,
        shard_bytes=shard_bytes,
        shard_receipt=shard_receipt,
        updated_manifest=updated,
        updated_manifest_bytes=updated_bytes,
        reverse_patch=reverse,
        receipt_path=receipt_path,
        receipt_bytes=receipt_bytes,
    )


def _operation_id(
    *,
    corpus_sha256: str,
    review_sha256: str,
    attestation_sha256: str,
    tool_sha256: str,
    records: list[dict[str, Any]],
) -> str:
    payload = {
        "adapter_version": ADAPTER_VERSION,
        "corpus_sha256": corpus_sha256,
        "review_sha256": review_sha256,
        "attestation_sha256": attestation_sha256,
        "tool_sha256": tool_sha256,
        "record_sha256": [canonical_json_sha256(row) for row in records],
    }
    return "muta_private_waec_append_v1_" + canonical_json_sha256(payload)[:24]


def _existing_append_state(target: Path, append_id: str) -> str:
    manifest, _, _ = _load_json(target / "manifest.json")
    matches = [
        row
        for row in manifest.get("private_training_appends") or []
        if row.get("append_id") == append_id
    ]
    if len(matches) > 1:
        raise AppendRefused(f"manifest repeats append ID {append_id}: {target}")
    if not matches:
        return "absent"
    verified = _verify_target(
        target,
        new_ids=set(),
        new_prompt_hashes=set(),
        new_task_hashes=set(),
    )
    manifest = verified.manifest
    shard = matches[0].get("shard") or {}
    inventory_matches = [
        item for item in manifest["shards"] if item.get("path") == shard.get("path")
    ]
    if inventory_matches != [shard]:
        raise AppendRefused(f"private append shard is inconsistent with inventory: {target}")
    shard_path = _safe_child(target, str(shard.get("path") or ""))
    if not shard_path.is_file():
        raise AppendRefused(f"manifest declares a missing private shard: {shard_path}")
    if shard_path.stat().st_size != shard.get("bytes") or sha256_file(shard_path) != shard.get(
        "sha256"
    ):
        raise AppendRefused(f"declared private shard is corrupt: {shard_path}")
    receipt_path = target / f"private-waec-append-{append_id[-12:]}.receipt.json"
    receipt, _, _ = _load_json(receipt_path)
    if receipt.get("append_id") != append_id or receipt.get("appended_shard") != shard:
        raise AppendRefused(f"private append receipt is inconsistent: {receipt_path}")
    return "applied"


def plan_append(
    *,
    corpus_path: Path,
    review_paths: list[Path],
    attestation_path: Path,
    warehouse_path: Path,
    sft_path: Path,
    token_counter: Any | None = None,
    holdouts: HoldoutIndex | None = None,
) -> tuple[str, list[dict[str, Any]], list[TargetPlan], dict[str, Any]]:
    if warehouse_path.resolve() == sft_path.resolve():
        raise AppendRefused("warehouse and SFT targets must be different directories")
    corpus_rows, corpus_sha = _load_jsonl(corpus_path)
    review_rows, review_sha, review_sources = _load_review_ledgers(review_paths)
    attestation, _attestation_raw, attestation_sha = _load_json(attestation_path)
    records = build_approved_records(
        corpus_rows=corpus_rows,
        corpus_sha256=corpus_sha,
        review_rows=review_rows,
        review_sha256=review_sha,
        review_sources=review_sources,
        attestation=attestation,
        attestation_sha256=attestation_sha,
        token_counter=token_counter,
        holdouts=holdouts,
    )
    tool_sha = sha256_file(Path(__file__))
    append_id = _operation_id(
        corpus_sha256=corpus_sha,
        review_sha256=review_sha,
        attestation_sha256=attestation_sha,
        tool_sha256=tool_sha,
        records=records,
    )
    states = {
        "warehouse": _existing_append_state(warehouse_path, append_id),
        "sft": _existing_append_state(sft_path, append_id),
    }
    if len(set(states.values())) != 1:
        raise AppendRefused(f"append is only partially applied across targets: {states}")
    if states["warehouse"] == "applied":
        return append_id, records, [], {"status": "already_applied", "targets": states}

    new_ids = {row["id"] for row in records}
    new_prompt_hashes = {row["contamination"]["normalized_prompt_sha256"] for row in records}
    new_task_hashes = {row["contamination"]["source_task_sha256"] for row in records}
    warehouse = _verify_target(
        warehouse_path,
        new_ids=new_ids,
        new_prompt_hashes=new_prompt_hashes,
        new_task_hashes=new_task_hashes,
    )
    sft = _verify_target(
        sft_path,
        new_ids=new_ids,
        new_prompt_hashes=new_prompt_hashes,
        new_task_hashes=new_task_hashes,
    )
    shared = _append_metadata(
        append_id=append_id,
        records=records,
        shard={},
        corpus_path=corpus_path,
        corpus_sha256=corpus_sha,
        review_sources=review_sources,
        review_bundle_sha256=review_sha,
        attestation_path=attestation_path,
        attestation=attestation,
        attestation_sha256=attestation_sha,
        tool_sha256=tool_sha,
    )
    plans = [
        _build_target_plan(
            target, append_id=append_id, records=records, shared_metadata=shared
        )
        for target in (warehouse, sft)
    ]
    summary = {
        "status": "ready",
        "append_id": append_id,
        "approved_rows": len(records),
        "counts": {
            "source": dict(
                sorted(Counter(row["provenance"]["source_id"] for row in records).items())
            ),
            "subject": dict(sorted(Counter(row["subject"] for row in records).items())),
            "pedagogy": dict(sorted(Counter(row["pedagogy"] for row in records).items())),
        },
        "publisher_licences": shared["publisher_licences_by_source"],
        "private_training_attestation": shared["authorization"][
            "private_training_attestation"
        ],
        "review_ledgers": shared["authorization"]["review_ledgers"],
        "review_bundle_sha256": shared["authorization"]["review_bundle_sha256"],
        "cleaned_prompt_review": [
            {
                "record_id": row["provenance"]["source_row_id"].removeprefix(
                    "private_training:"
                ),
                "review_id": row["verification"]["review_id"],
                "normalized_prompt_sha256": row["contamination"][
                    "normalized_prompt_sha256"
                ],
                "prompt": row["prompt"],
            }
            for row in records
        ],
        "targets": [
            {
                "path": str(plan.target.path),
                "kind": plan.target.kind,
                "before_rows": plan.target.manifest["row_count"],
                "after_rows": plan.updated_manifest["row_count"],
                "new_shard": plan.shard_receipt,
                "rollback_receipt": plan.receipt_path.name,
            }
            for plan in plans
        ],
    }
    return append_id, records, plans, summary


def _write_exclusive(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _replace_bytes(path: Path, data: bytes, *, suffix: str) -> None:
    partial = path.with_name(path.name + suffix)
    _write_exclusive(partial, data)
    partial.replace(path)


def _planned_collision_keys(
    plan: TargetPlan,
) -> tuple[set[str], set[str], set[str]]:
    rows = [json.loads(line) for line in plan.shard_bytes.splitlines() if line.strip()]
    return (
        {str(row["id"]) for row in rows},
        {str(row["contamination"]["normalized_prompt_sha256"]) for row in rows},
        {str(row["contamination"]["source_task_sha256"]) for row in rows},
    )


def apply_plans(plans: list[TargetPlan]) -> None:
    if not plans:
        return
    locks: list[Path] = []
    partials: list[Path] = []
    committed_shards: list[Path] = []
    committed_receipts: list[Path] = []
    replaced_manifests: list[TargetPlan] = []
    try:
        for plan in plans:
            lock = plan.target.path / ".private-waec-append.lock"
            _write_exclusive(lock, (plan.receipt_path.stem + "\n").encode("utf-8"))
            locks.append(lock)
        for plan in plans:
            new_ids, new_prompt_hashes, new_task_hashes = _planned_collision_keys(plan)
            verified = _verify_target(
                plan.target.path,
                new_ids=new_ids,
                new_prompt_hashes=new_prompt_hashes,
                new_task_hashes=new_task_hashes,
            )
            if verified.manifest_sha256 != plan.target.manifest_sha256:
                raise AppendRefused(f"target changed after planning: {plan.target.path}")
        for plan in plans:
            current = (plan.target.path / "manifest.json").read_bytes()
            if hashlib.sha256(current).hexdigest() != plan.target.manifest_sha256:
                raise AppendRefused(f"manifest changed after validation: {plan.target.path}")
            for final_path in (plan.shard_path, plan.receipt_path):
                if final_path.exists():
                    raise AppendRefused(f"refusing to overwrite append output: {final_path}")
            shard_partial = plan.shard_path.with_suffix(plan.shard_path.suffix + ".partial")
            receipt_partial = plan.receipt_path.with_suffix(plan.receipt_path.suffix + ".partial")
            manifest_partial = plan.target.path / "manifest.json.private-waec.partial"
            for path in (shard_partial, receipt_partial, manifest_partial):
                if path.exists():
                    raise AppendRefused(f"stale append partial exists: {path}")
            _write_exclusive(shard_partial, plan.shard_bytes)
            _write_exclusive(receipt_partial, plan.receipt_bytes)
            _write_exclusive(manifest_partial, plan.updated_manifest_bytes)
            partials.extend((shard_partial, receipt_partial, manifest_partial))

        for plan in plans:
            shard_partial = plan.shard_path.with_suffix(plan.shard_path.suffix + ".partial")
            receipt_partial = plan.receipt_path.with_suffix(plan.receipt_path.suffix + ".partial")
            shard_partial.replace(plan.shard_path)
            committed_shards.append(plan.shard_path)
            receipt_partial.replace(plan.receipt_path)
            committed_receipts.append(plan.receipt_path)
        for plan in plans:
            manifest_partial = plan.target.path / "manifest.json.private-waec.partial"
            manifest_partial.replace(plan.target.path / "manifest.json")
            replaced_manifests.append(plan)

        for plan in plans:
            if sha256_file(plan.shard_path) != plan.shard_receipt["sha256"]:
                raise AppendRefused(f"committed shard hash mismatch: {plan.shard_path}")
            if hashlib.sha256((plan.target.path / "manifest.json").read_bytes()).hexdigest() != (
                hashlib.sha256(plan.updated_manifest_bytes).hexdigest()
            ):
                raise AppendRefused(f"committed manifest hash mismatch: {plan.target.path}")
    except BaseException as original:
        rollback_failures: list[str] = []
        unsafe_targets: set[Path] = set()
        for plan in reversed(replaced_manifests):
            try:
                _replace_bytes(
                    plan.target.path / "manifest.json",
                    plan.target.manifest_raw,
                    suffix=".private-waec.rollback.partial",
                )
            except OSError as exc:
                unsafe_targets.add(plan.target.path)
                rollback_failures.append(f"{plan.target.path}: {exc}")
        for path in reversed(committed_shards + committed_receipts):
            if path.parent in unsafe_targets:
                continue
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        if rollback_failures:
            details = "; ".join(rollback_failures)
            raise AppendRefused(
                "append failed and manifest rollback was incomplete; retained the new shard "
                f"and receipt for affected targets: {details}"
            ) from original
        raise
    finally:
        for path in partials:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        for lock in locks:
            try:
                lock.unlink()
            except FileNotFoundError:
                pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument(
        "--review-ledger",
        dest="review_ledgers",
        action="append",
        type=Path,
        required=True,
        help="approved/excluded review ledger; repeat for additional compatible ledgers",
    )
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--warehouse", type=Path, required=True)
    parser.add_argument("--sft", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="validate only (the default)")
    mode.add_argument("--apply", action="store_true", help="append after all validation passes")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        _append_id, _records, plans, summary = plan_append(
            corpus_path=args.corpus,
            review_paths=args.review_ledgers,
            attestation_path=args.attestation,
            warehouse_path=args.warehouse,
            sft_path=args.sft,
        )
        if args.apply and plans:
            apply_plans(plans)
            summary["status"] = "applied"
        elif args.apply:
            summary["status"] = "already_applied"
        else:
            summary["mode"] = "dry_run"
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except (AppendRefused, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
