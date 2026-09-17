"""Allowlisted adapters for pinned, open-licensed external datasets.

The adapters are intentionally import-safe without Hugging Face ``datasets``.
Remote materialization is opt-in and fails closed when the pinned dependency is
not installed.  No web scraper or OCR path exists in this package.
"""

from __future__ import annotations

import ast
import decimal
import hashlib
import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from .core import (
    VERIFIER_VERSION,
    HoldoutIndex,
    load_source_registry,
    make_record,
    normalized_sha256,
)
from .deepmind_overlay import OVERLAY_VERSION
from .deepmind_overlay import install as install_deepmind_overlay


class DatasetDependencyError(RuntimeError):
    """Raised when remote adapters are requested without build dependencies."""


def _load_dataset(*args: Any, **kwargs: Any):
    try:
        from datasets import load_dataset
    except ImportError as exc:  # pragma: no cover - exercised in dependency-light environments
        raise DatasetDependencyError(
            "remote sources require `pip install -r "
            "model-development/finetune/muta_dataset_v2/requirements-build.txt`"
        ) from exc
    return load_dataset(*args, **kwargs)


def _source(source_id: str) -> dict[str, Any]:
    source = load_source_registry()[source_id]
    if not str(source.get("revision", "")).strip():
        raise ValueError(f"source {source_id} has no pinned revision")
    return source


def _clean_reasoning(text: str) -> str:
    text = re.sub(
        r"<think\b[^>]*>.*?</think\s*>",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(r"<<[^<>]*>>", "", text)
    text = re.sub(r"\\boxed\{([^{}]+)\}", r"Final answer: \1", text)
    # Drop orphan tags too; well-formed blocks (including their contents) were
    # removed above rather than silently relabelled as visible reasoning.
    text = re.sub(r"</?think>", "", text, flags=re.IGNORECASE)
    return "\n".join(line.rstrip() for line in text.strip().splitlines()).strip()


def _normalise_number(text: str) -> str:
    value = text.strip().replace(",", "")
    if re.fullmatch(r"[-+]?\d+\.0+", value):
        return value.split(".", 1)[0]
    return text.strip()


def _safe_number(text: str) -> Fraction:
    cleaned = text.strip().replace(",", "")
    cleaned = re.sub(r"^[£$€₦]", "", cleaned)
    tree = ast.parse(cleaned, mode="eval")

    def evaluate(node: ast.AST) -> Fraction:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return Fraction(str(node.value))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = evaluate(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp):
            left = evaluate(node.left)
            right = evaluate(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Pow) and right.denominator == 1 and abs(right) <= 10:
                return left**right.numerator
        raise ValueError("expression is outside the arithmetic verifier grammar")

    return evaluate(tree)


TEMPLATEGSM_CONFIG = "templategsm-2000-1k"
TEMPLATEGSM_CHECKER_VERSION = "templategsm-static-prefilter-v1"
TEMPLATEGSM_SNAPSHOT_REVISION = "0c8ed6b60fea0a84f25ddb1b8b761db695df2e19"
TEMPLATEGSM_SNAPSHOT_FILE_COUNT = 2_000
TEMPLATEGSM_SNAPSHOT_TOTAL_BYTES = 2_403_438_064
TEMPLATEGSM_SNAPSHOT_INVENTORY_SHA256 = (
    "9100d9daa8214a5018124e2e44dc1ee0378ecd0a992f4c450430d76f95801132"
)
TEMPLATEGSM_SNAPSHOT_README_SHA256 = (
    "20b70e0f0d41021e54e4a73b1972fde7f6355f405bd67eef00472e4ce711ba7a"
)
TEMPLATEGSM_SNAPSHOT_TEMPLATE_IDS = frozenset(range(2_000))
TEMPLATEGSM_SNAPSHOT_RANGES = (
    ("data/1k/0000-0999", range(1_000)),
    ("data/1k/1000-1999", range(1_000, 2_000)),
)
TEMPLATEGSM_FILTER_AUDIT_PATH = Path(__file__).with_name("templategsm_filter_audit.json")
TEMPLATEGSM_FULL_AUDIT_PATH = Path(__file__).with_name("templategsm_full_audit.json")
TEMPLATEGSM_REFERENCE_CHECKER_PATH = Path(__file__).with_name("templategsm_static_prefilter_v1.py")
TEMPLATEGSM_FULL_AUDIT_REPOSITORY_PATH = (
    "model-development/finetune/muta_dataset_v2/templategsm_full_audit.json"
)
TEMPLATEGSM_REFERENCE_CHECKER_REPOSITORY_PATH = (
    "model-development/finetune/muta_dataset_v2/templategsm_static_prefilter_v1.py"
)
TEMPLATEGSM_FILTER_AUDIT_SHA256 = "b978547bb908320ac0097785a17e016c81ce9a5cc77b39054390e6ccab5e4cbd"
_TEMPLATEGSM_CANONICAL_INPUT = re.compile(r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\Z")
_TEMPLATEGSM_LITERAL = re.compile(r"(?<![\w.])[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?!\w|\.\d)")
_TEMPLATEGSM_FLOAT_ARTIFACT = re.compile(
    r"(?<![\w.])[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{7,}(?!\w|\.\d)"
)
_TEMPLATEGSM_NUMBER = r"(?:[$£€₦]\s*)?[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?"
_TEMPLATEGSM_OPERATOR = r"(?:\+|-|\*|/|×|÷|[xX])"
_TEMPLATEGSM_EQUALITY = re.compile(
    rf"(?<![\w.])(?P<lhs>{_TEMPLATEGSM_NUMBER}"
    rf"(?:\s*{_TEMPLATEGSM_OPERATOR}\s*{_TEMPLATEGSM_NUMBER})+)\s*=\s*"
    rf"(?P<rhs>(?:[$£€₦]\s*)?[+-]?(?:\d{{1,3}}(?:,\d{{3}})+|\d+)"
    rf"(?:\.\d+)?)(?!\w|\.\d)"
)
_TEMPLATEGSM_APPROXIMATION = re.compile(
    r"\b(?:approximately|approx(?:imately)?\.?|about|roughly|estimate(?:d)?|"
    r"rounded|rounding|nearest)\b|[≈~]",
    re.IGNORECASE,
)
_TEMPLATEGSM_PERCENTAGE = re.compile(r"(?<![\w.])([+-]?(?:\d+(?:\.\d+)?|\.\d+))%")
_TEMPLATEGSM_SNAPSHOT_FILENAME = re.compile(r"templategsm-train-problems-(\d+)\.jsonl\Z")


@dataclass(frozen=True)
class TemplateGSMSnapshot:
    """Validated local TemplateGSM snapshot plus its source-text-free receipt."""

    root: Path
    data_files: tuple[Path, ...]
    receipt: dict[str, Any]
    filesystem_identity: tuple[tuple[str, int, int, int, int, int], ...]


def validate_templategsm_snapshot(path: Path) -> TemplateGSMSnapshot:
    """Authenticate the exact pinned 2M-row local snapshot without reading row text."""

    root = path.expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"TemplateGSM snapshot directory is missing: {root}")
    readme = root / "README.md"
    if not readme.is_file() or readme.is_symlink():
        raise FileNotFoundError("TemplateGSM snapshot requires a regular README.md")
    readme_before = readme.stat()
    readme_sha256 = hashlib.sha256(readme.read_bytes()).hexdigest()
    readme_after = readme.stat()
    if (
        readme_before.st_dev,
        readme_before.st_ino,
        readme_before.st_size,
        readme_before.st_mtime_ns,
        readme_before.st_ctime_ns,
    ) != (
        readme_after.st_dev,
        readme_after.st_ino,
        readme_after.st_size,
        readme_after.st_mtime_ns,
        readme_after.st_ctime_ns,
    ):
        raise RuntimeError("TemplateGSM snapshot README changed while hashing")
    if readme_sha256 != TEMPLATEGSM_SNAPSHOT_README_SHA256:
        raise ValueError(
            "TemplateGSM snapshot README hash mismatch: "
            f"expected {TEMPLATEGSM_SNAPSHOT_README_SHA256}, observed {readme_sha256}"
        )

    data_root = root / "data"
    expected_directories = {
        "1k",
        *(Path(name).relative_to("data").as_posix() for name, _ in TEMPLATEGSM_SNAPSHOT_RANGES),
    }
    if not data_root.is_dir() or data_root.is_symlink():
        raise FileNotFoundError("TemplateGSM snapshot data directory is missing or is a symlink")
    observed_directories = {
        item.relative_to(data_root).as_posix() for item in data_root.rglob("*") if item.is_dir()
    }
    if observed_directories != expected_directories:
        raise ValueError(
            "TemplateGSM snapshot directory ranges differ from the pinned layout: "
            f"expected {sorted(expected_directories)}, observed {sorted(observed_directories)}"
        )

    data_files: list[Path] = []
    observed_ids: set[int] = set()
    for relative_directory, allowed_ids_range in TEMPLATEGSM_SNAPSHOT_RANGES:
        directory = root / relative_directory
        if not directory.is_dir() or directory.is_symlink():
            raise FileNotFoundError(
                f"TemplateGSM snapshot path range is missing or is a symlink: {relative_directory}"
            )
        allowed_ids = set(allowed_ids_range)
        for candidate in sorted(directory.iterdir()):
            if not candidate.is_file() or candidate.is_symlink():
                raise ValueError(f"unexpected TemplateGSM snapshot entry: {candidate}")
            match = _TEMPLATEGSM_SNAPSHOT_FILENAME.fullmatch(candidate.name)
            if match is None:
                raise ValueError(f"unexpected TemplateGSM snapshot filename: {candidate.name}")
            template_id = int(match.group(1))
            canonical_name = f"templategsm-train-problems-{template_id}.jsonl"
            if candidate.name != canonical_name:
                raise ValueError(
                    "noncanonical TemplateGSM snapshot filename: "
                    f"expected {canonical_name}, observed {candidate.name}"
                )
            if template_id not in allowed_ids:
                raise ValueError(
                    f"TemplateGSM template {template_id} is outside path range {relative_directory}"
                )
            if template_id in observed_ids:
                raise ValueError(f"duplicate TemplateGSM template file: {template_id}")
            observed_ids.add(template_id)
            data_files.append(candidate)

    observed_data_files = {item for item in data_root.rglob("*") if item.is_file()}
    if observed_data_files != set(data_files):
        unexpected = sorted(
            item.relative_to(root).as_posix() for item in observed_data_files - set(data_files)
        )
        raise ValueError(f"unexpected TemplateGSM snapshot data files: {unexpected[:10]}")

    if observed_ids != TEMPLATEGSM_SNAPSHOT_TEMPLATE_IDS:
        missing = sorted(TEMPLATEGSM_SNAPSHOT_TEMPLATE_IDS - observed_ids)
        extra = sorted(observed_ids - TEMPLATEGSM_SNAPSHOT_TEMPLATE_IDS)
        raise ValueError(
            "TemplateGSM snapshot template ID set mismatch: "
            f"missing={missing[:10]}, extra={extra[:10]}"
        )
    if len(data_files) != TEMPLATEGSM_SNAPSHOT_FILE_COUNT:
        raise ValueError(
            "TemplateGSM snapshot file count mismatch: "
            f"expected {TEMPLATEGSM_SNAPSHOT_FILE_COUNT}, observed {len(data_files)}"
        )

    inventory = hashlib.sha256()
    total_bytes = 0
    filesystem_identity = [
        (
            "README.md",
            readme_before.st_dev,
            readme_before.st_ino,
            readme_before.st_size,
            readme_before.st_mtime_ns,
            readme_before.st_ctime_ns,
        )
    ]
    for data_file in data_files:
        before = data_file.stat()
        file_hash = hashlib.sha256()
        with data_file.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                file_hash.update(chunk)
        after = data_file.stat()
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise RuntimeError(f"TemplateGSM snapshot file changed while hashing: {data_file}")
        relative = data_file.relative_to(root).as_posix()
        filesystem_identity.append(
            (
                relative,
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
        )
        total_bytes += before.st_size
        inventory.update(f"{relative}\t{before.st_size}\t{file_hash.hexdigest()}\n".encode())

    inventory_sha256 = inventory.hexdigest()
    if total_bytes != TEMPLATEGSM_SNAPSHOT_TOTAL_BYTES:
        raise ValueError(
            "TemplateGSM snapshot byte count mismatch: "
            f"expected {TEMPLATEGSM_SNAPSHOT_TOTAL_BYTES}, observed {total_bytes}"
        )
    if inventory_sha256 != TEMPLATEGSM_SNAPSHOT_INVENTORY_SHA256:
        raise ValueError(
            "TemplateGSM snapshot inventory hash mismatch: "
            f"expected {TEMPLATEGSM_SNAPSHOT_INVENTORY_SHA256}, observed {inventory_sha256}"
        )
    source = _source("template_gsm")
    if source["revision"] != TEMPLATEGSM_SNAPSHOT_REVISION:
        raise ValueError(
            "TemplateGSM snapshot revision differs from the source registry: "
            f"snapshot={TEMPLATEGSM_SNAPSHOT_REVISION}, registry={source['revision']}"
        )
    receipt = {
        "resolved_path": str(root),
        "file_count": len(data_files),
        "total_bytes": total_bytes,
        "inventory_sha256": inventory_sha256,
        "readme_sha256": readme_sha256,
        "source_revision": TEMPLATEGSM_SNAPSHOT_REVISION,
        "configuration": TEMPLATEGSM_CONFIG,
        "inventory_order": (
            "lexicographic relative-path order within data/1k/0000-0999, then data/1k/1000-1999"
        ),
        "row_materialization_network_used": False,
    }
    return TemplateGSMSnapshot(
        root=root,
        data_files=tuple(data_files),
        receipt=receipt,
        filesystem_identity=tuple(filesystem_identity),
    )


def _templategsm_fraction(text: str) -> Fraction:
    cleaned = re.sub(r"[$£€₦\s,]", "", text)
    percentage = cleaned.endswith("%")
    cleaned = cleaned.removesuffix("%")
    value = Fraction(decimal.Decimal(cleaned))
    return value / 100 if percentage else value


def _templategsm_evaluate_expression(text: str) -> Fraction:
    """Evaluate only a regex-isolated numeric expression, never publisher code."""

    expression = re.sub(r"[$£€₦,\s]", "", text)
    expression = expression.replace("×", "*").replace("x", "*").replace("X", "*").replace("÷", "/")
    expression = _TEMPLATEGSM_PERCENTAGE.sub(r"(\1/100)", expression)
    tree = ast.parse(expression, mode="eval")

    def evaluate(node: ast.AST) -> Fraction:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return Fraction(str(node.value))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = evaluate(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp):
            left = evaluate(node.left)
            right = evaluate(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
        raise ValueError("expression is outside the TemplateGSM arithmetic grammar")

    return evaluate(tree)


def _templategsm_filter_reasons(
    *, prompt: str, answer: str, solution: str, solution_code: str
) -> tuple[str, ...]:
    """Return conservative, deterministic static-filter rejection reasons.

    The routine deliberately does not parse or execute ``solution_code``.  It
    proves only narrow textual and exact-arithmetic invariants; surviving rows
    remain silver candidates that require an exact-row human audit before SFT.
    """

    reasons: list[str] = []
    if not prompt or not answer or not solution or "result" not in solution_code:
        reasons.append("base_missing")

    answer_value: decimal.Decimal | None = None
    if not _TEMPLATEGSM_CANONICAL_INPUT.fullmatch(answer):
        reasons.append("result_noncanonical")
    else:
        try:
            answer_value = decimal.Decimal(answer.replace(",", ""))
            fractional = answer.replace(",", "").lstrip("+-").partition(".")[2].rstrip("0")
            if (
                not answer_value.is_finite()
                or len(fractional) > 6
                or (answer_value == 0 and answer.startswith("-"))
            ):
                reasons.append("result_noncanonical")
        except decimal.InvalidOperation:
            reasons.append("result_noncanonical")

    if _TEMPLATEGSM_FLOAT_ARTIFACT.search(solution):
        reasons.append("solution_float_artifact")

    if answer_value is None or not answer_value.is_finite():
        reasons.append("target_unsupported")
    else:
        terminal_values: list[decimal.Decimal] = []
        for match in _TEMPLATEGSM_LITERAL.finditer(solution[-512:]):
            try:
                terminal_values.append(decimal.Decimal(match.group().replace(",", "")))
            except decimal.InvalidOperation:
                continue
        if answer_value not in terminal_values:
            reasons.append("target_unsupported")

    contradiction = False
    for match in _TEMPLATEGSM_EQUALITY.finditer(solution):
        context = solution[max(0, match.start() - 120) : min(len(solution), match.end() + 120)]
        if _TEMPLATEGSM_APPROXIMATION.search(context):
            continue
        try:
            left = _templategsm_evaluate_expression(match.group("lhs"))
            right = _templategsm_fraction(match.group("rhs"))
        except (SyntaxError, ValueError, ZeroDivisionError, decimal.InvalidOperation):
            continue
        if left != right:
            contradiction = True
            break
    if contradiction:
        reasons.append("arithmetic_contradiction")
    return tuple(sorted(set(reasons)))


def _load_templategsm_filter_audit(
    path: Path = TEMPLATEGSM_FILTER_AUDIT_PATH,
    *,
    expected_sha256: str = TEMPLATEGSM_FILTER_AUDIT_SHA256,
    full_audit_path: Path = TEMPLATEGSM_FULL_AUDIT_PATH,
    reference_checker_path: Path = TEMPLATEGSM_REFERENCE_CHECKER_PATH,
) -> tuple[frozenset[str], str]:
    """Load the pinned full-source audit and fail closed on any binding drift."""

    raw = path.read_bytes()
    observed_sha256 = hashlib.sha256(raw).hexdigest()
    if observed_sha256 != expected_sha256:
        raise ValueError(
            "TemplateGSM filter audit hash mismatch: "
            f"expected {expected_sha256}, observed {observed_sha256}"
        )
    payload = json.loads(raw)
    source = _source("template_gsm")
    expected_bindings = {
        "checker_version": TEMPLATEGSM_CHECKER_VERSION,
        "source_id": "template_gsm",
        "source_revision": source["revision"],
        "configuration": TEMPLATEGSM_CONFIG,
        "per_template_cap": 400,
    }
    for field, expected in expected_bindings.items():
        if payload.get(field) != expected:
            raise ValueError(
                f"TemplateGSM filter audit {field} mismatch: "
                f"expected {expected!r}, observed {payload.get(field)!r}"
            )
    counts = payload.get("counts") or {}
    templates = payload.get("templates") or {}
    identifiers = templates.get("failing_any_rule_ids")
    if counts.get("total_rows") != 2_000_000 or templates.get("total") != 2_000:
        raise ValueError("TemplateGSM filter audit does not cover the pinned 2M configuration")
    if not isinstance(identifiers, list) or any(
        not isinstance(identifier, str) or not identifier.isdigit() for identifier in identifiers
    ):
        raise ValueError("TemplateGSM filter audit has malformed template identifiers")
    if identifiers != sorted(set(identifiers), key=int):
        raise ValueError("TemplateGSM filter audit identifiers are not unique numeric order")
    if templates.get("failing_any_rule") != len(identifiers):
        raise ValueError("TemplateGSM filter audit failing-template count is inconsistent")
    if templates.get("capacity_with_every_failing_template_quarantined_and_cap400") != 655_200:
        raise ValueError("TemplateGSM filter audit quarantine capacity is inconsistent")

    artifact_bindings = (
        (
            "full_scan_report",
            TEMPLATEGSM_FULL_AUDIT_REPOSITORY_PATH,
            full_audit_path,
        ),
        (
            "reference_checker",
            TEMPLATEGSM_REFERENCE_CHECKER_REPOSITORY_PATH,
            reference_checker_path,
        ),
    )
    for receipt_name, expected_repository_path, artifact_path in artifact_bindings:
        receipt = payload.get(receipt_name) or {}
        if receipt.get("path") != expected_repository_path:
            raise ValueError(f"TemplateGSM {receipt_name} path binding is inconsistent")
        receipt_sha256 = receipt.get("sha256")
        if not isinstance(receipt_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", receipt_sha256):
            raise ValueError(f"TemplateGSM {receipt_name} SHA-256 receipt is malformed")
        artifact_sha256 = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        if artifact_sha256 != receipt_sha256:
            raise ValueError(
                f"TemplateGSM {receipt_name} SHA-256 mismatch: "
                f"expected {receipt_sha256}, observed {artifact_sha256}"
            )

    full_audit = json.loads(full_audit_path.read_bytes())
    for field in ("checker_version", "source_id", "source_revision", "configuration"):
        if full_audit.get(field) != payload.get(field):
            raise ValueError(f"TemplateGSM full audit {field} differs from compact audit")
    if full_audit.get("counts") != counts:
        raise ValueError("TemplateGSM full audit counts differ from compact audit")
    full_templates = full_audit.get("templates") or {}
    for field in (
        "total",
        "fully_passing",
        "failing_any_rule",
        "failing_any_rule_ids",
        "failing_ids_by_reason",
        "pass_row_capacity_with_row_filter_and_cap400",
        "capacity_with_every_failing_template_quarantined_and_cap400",
    ):
        if full_templates.get(field) != templates.get(field):
            raise ValueError(f"TemplateGSM full audit templates.{field} differs from compact audit")
    return frozenset(identifiers), observed_sha256


def _verify_gsm8k_annotations(raw_answer: str, final_answer: str) -> bool:
    annotations = re.findall(r"<<([^<>]*?)=([^<>]*?)>>", raw_answer)
    if not annotations:
        return False
    try:
        observed_results = []
        for expression, result in annotations:
            expected = _safe_number(result)
            if _safe_number(expression) != expected:
                return False
            observed_results.append(expected)
        return observed_results[-1] == _safe_number(final_answer)
    except (SyntaxError, ValueError, ZeroDivisionError):
        return False


def iter_templategsm(
    *,
    holdouts: HoldoutIndex,
    limit: int,
    seed: int,
    split: str,
    per_template_cap: int,
    snapshot: TemplateGSMSnapshot | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield a bounded, template-capped TemplateGSM candidate slice.

    TemplateGSM supplies generated code and its result, but this adapter never
    executes that code.  A pinned full-source audit quarantines every template
    with any observed static-filter failure, and the same row filter runs again
    defensively.  Survivors remain silver candidates until exact-row human
    review approves them.
    """

    if not 1 <= per_template_cap <= 400:
        raise ValueError("TemplateGSM per-template cap must be between 1 and audited maximum 400")
    source = _source("template_gsm")
    quarantined_templates, filter_audit_sha256 = _load_templategsm_filter_audit()
    if snapshot is None:
        dataset = _load_dataset(
            source["url"].removeprefix("https://huggingface.co/datasets/"),
            TEMPLATEGSM_CONFIG,
            split="train",
            revision=source["revision"],
            streaming=True,
        )
    else:
        revalidated = validate_templategsm_snapshot(snapshot.root)
        if (
            revalidated.receipt != snapshot.receipt
            or revalidated.filesystem_identity != snapshot.filesystem_identity
        ):
            raise RuntimeError("TemplateGSM snapshot changed after build preflight")
        dataset = _load_dataset(
            "json",
            data_files=[str(path) for path in revalidated.data_files],
            split="train",
            streaming=True,
        )
    dataset = dataset.shuffle(seed=seed, buffer_size=20_000)
    template_counts: dict[str, int] = {}
    del limit  # The builder owns the accepted-row limit and may reject cross-source duplicates.
    for row in dataset:
        template_id = str(row.get("template_id", ""))
        if (
            not template_id
            or template_id in quarantined_templates
            or template_counts.get(template_id, 0) >= per_template_cap
        ):
            continue
        prompt = str(row.get("problem", "")).strip()
        answer = _normalise_number(str(row.get("result", "")))
        solution = _clean_reasoning(str(row.get("solution_wocode", "")))
        code = str(row.get("solution_code", "")).strip()
        filter_reasons = _templategsm_filter_reasons(
            prompt=prompt,
            answer=answer,
            solution=solution,
            solution_code=code,
        )
        if filter_reasons:
            continue
        completion = f"{solution}\nFinal answer: {answer}."
        record = make_record(
            prompt=prompt + " Show the essential calculation and give the final answer.",
            completion=completion,
            answer=answer,
            subject="mathematics",
            topic="word_problems",
            difficulty="standard",
            response_format="free_response",
            pedagogy="worked_solution",
            mode="chat",
            split=split,
            source_id="template_gsm",
            source_revision=source["revision"],
            source_split="train",
            source_row_id=f"train:template:{template_id}:problem:{row.get('problem_id')}",
            semantic_cluster_id=f"template:{template_id}",
            license_name=source["license"],
            synthetic=True,
            transform=(
                "solution_wocode plus explicit final answer; pinned static semantic prefilter "
                "and whole-template quarantine applied; solution code not executed"
            ),
            country="not-applicable",
            curriculum_authority="none",
            curriculum_version="none",
            exam_era="not-applicable",
            alignment="general school mathematics; not claimed as WAEC aligned",
            verification={
                "status": "silver_pending_audit",
                "method": (
                    "publisher result plus pinned no-code-execution static semantic prefilter "
                    "and whole-template quarantine; exact-row human audit still required"
                ),
                "expected": answer,
                "observed": answer,
                "verifier_version": (f"{VERIFIER_VERSION}+{TEMPLATEGSM_CHECKER_VERSION}"),
                "template_id": template_id,
                "solution_code_present": True,
                "static_filter": {
                    "checker_version": TEMPLATEGSM_CHECKER_VERSION,
                    "audit_sha256": filter_audit_sha256,
                    "configuration": TEMPLATEGSM_CONFIG,
                    "template_quarantined": False,
                    "row_filter_passed": True,
                    "solution_code_executed": False,
                },
                "training_eligible": False,
            },
            holdouts=holdouts,
            source_task=prompt,
        )
        if record is None:
            continue
        template_counts[template_id] = template_counts.get(template_id, 0) + 1
        yield record


_SECONDARY_SCIENCE_TERMS = frozenset(
    {
        "acceleration",
        "acid",
        "atom",
        "base",
        "bond",
        "cell",
        "circuit",
        "concentration",
        "density",
        "diffusion",
        "ecology",
        "electric",
        "energy",
        "equilibrium",
        "force",
        "frequency",
        "gene",
        "genetic",
        "heat",
        "inheritance",
        "ion",
        "light",
        "mass",
        "mole",
        "motion",
        "organism",
        "photosynthesis",
        "pressure",
        "reaction",
        "resistance",
        "respiration",
        "solution",
        "speed",
        "temperature",
        "velocity",
        "voltage",
        "wave",
    }
)
_ADVANCED_OR_CLINICAL_TERMS = frozenset(
    {
        "clinical",
        "chromatograph",
        "drug",
        "eigen",
        "hamiltonian",
        "interferometer",
        "ligand",
        "mach-zehnder",
        "photon",
        "quantum",
        "relativ",
        "surgery",
        "tumor",
        "patient",
        "hammett",
        "marcus",
        "chromophore",
        "pharmac",
        "spectroscopy",
        "university",
    }
)


def _secondary_science_candidate(prompt: str) -> bool:
    words = set(re.findall(r"[a-z]+", prompt.casefold()))
    return bool(words & _SECONDARY_SCIENCE_TERMS) and not bool(words & _ADVANCED_OR_CLINICAL_TERMS)


def _extract_mcq_answer(completion: str) -> str | None:
    patterns = (
        r"best answer is\s+([A-J])\b",
        r"final answer(?: is|:)\s*\**([A-J])\b",
        r"\\boxed\{([A-J])\}",
    )
    for pattern in patterns:
        match = re.search(pattern, completion, flags=re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return None


def iter_nemotron_science(
    *, holdouts: HoldoutIndex, limit: int, seed: int, split: str
) -> Iterator[dict[str, Any]]:
    """Yield secondary-level candidates; all remain audit-gated silver rows."""

    source = _source("nemotron_science_v1")
    repo = source["url"].removeprefix("https://huggingface.co/datasets/")
    dataset = _load_dataset(
        repo,
        split="MCQ",
        revision=source["revision"],
        streaming=True,
    ).shuffle(seed=seed, buffer_size=20_000)
    del limit  # The builder owns the accepted-row limit.
    for row in dataset:
        messages = row.get("messages") or []
        if len(messages) != 2:
            continue
        prompt = str(messages[0].get("content", "")).strip()
        completion = _clean_reasoning(str(messages[1].get("content", "")))
        answer = _extract_mcq_answer(completion)
        if (
            not answer
            or not _secondary_science_candidate(prompt)
            or len(prompt) > 3500
            or len(completion) > 3500
            or len(completion.split()) < 40
            or len(re.findall(r"(?m)^\s*[A-J][).]", prompt)) > 5
        ):
            continue
        prompt_words = set(re.findall(r"[a-z]+", prompt.casefold()))
        if {"cell", "gene", "genetic", "organism", "ecology", "photosynthesis"} & prompt_words:
            subject = "biology"
        elif {"atom", "acid", "base", "bond", "ion", "mole", "reaction", "solution"} & prompt_words:
            subject = "chemistry"
        elif {
            "acceleration",
            "circuit",
            "electric",
            "force",
            "motion",
            "speed",
            "wave",
        } & prompt_words:
            subject = "physics"
        else:
            subject = "integrated_science"
        record = make_record(
            prompt=prompt,
            completion=completion,
            answer=answer,
            subject=subject,
            topic="secondary_science_reasoning",
            difficulty="advanced",
            response_format="multiple_choice",
            pedagogy="worked_solution",
            mode="chat",
            split=split,
            source_id="nemotron_science_v1",
            source_revision=source["revision"],
            source_split="MCQ",
            source_row_id=f"MCQ:{row.get('uuid', '')}",
            semantic_cluster_id=f"row:MCQ:{row.get('uuid', '')}",
            license_name=source["license"],
            synthetic=True,
            transform="two-message MCQ; level/length filter; hidden reasoning discarded",
            country="not-applicable",
            curriculum_authority="none",
            curriculum_version="none",
            exam_era="not-applicable",
            alignment="keyword-screened secondary science candidate; human audit required",
            verification={
                "status": "silver_pending_audit",
                "method": "parse final option from published synthetic response",
                "expected": answer,
                "observed": answer,
                "verifier_version": VERIFIER_VERSION,
                "training_eligible": False,
            },
            holdouts=holdouts,
            source_task=prompt,
        )
        if record is not None:
            yield record


def _choice_text(row: dict[str, Any], answer_key: str) -> str | None:
    choices = row.get("choices") or {}
    labels = [str(value) for value in choices.get("label", [])]
    texts = [str(value) for value in choices.get("text", [])]
    try:
        return texts[labels.index(answer_key)]
    except (ValueError, IndexError):
        return None


def _format_choices(row: dict[str, Any]) -> str:
    choices = row.get("choices") or {}
    return "\n".join(
        f"{label}. {text}"
        for label, text in zip(choices.get("label", []), choices.get("text", []), strict=False)
    )


def iter_qasc(
    *, holdouts: HoldoutIndex, limit: int, seed: int, split: str
) -> Iterator[dict[str, Any]]:
    """Yield train-only QASC anchors with their published answer keys."""

    # ARC is deliberately not included. It was used in Muta's prior run, is a
    # Gate 2 evaluator, and carries ShareAlike obligations that need an explicit
    # project decision. QASC is the only MCQ anchor in this iterator.
    specs = (("qasc", "allenai/qasc", None, "train"),)
    del limit  # The builder owns the accepted-row limit.
    for source_id, repo, config, source_split in specs:
        source = _source(source_id)
        kwargs: dict[str, Any] = {
            "split": source_split,
            "revision": source["revision"],
            "streaming": True,
        }
        dataset = _load_dataset(repo, config, **kwargs) if config else _load_dataset(repo, **kwargs)
        dataset = dataset.shuffle(seed=seed, buffer_size=10_000)
        for row in dataset:
            answer_key = str(row.get("answerKey", "")).strip()
            answer_text = _choice_text(row, answer_key)
            if not answer_key or not answer_text:
                continue
            question = str(row.get("question", "")).strip()
            formatted_choices = _format_choices(row)
            source_task = f"{question}\n{formatted_choices}"
            prompt = f"{source_task}\nChoose the best answer and briefly justify it."
            facts = [str(row.get(key, "")).strip() for key in ("fact1", "fact2")]
            facts = [fact for fact in facts if fact]
            rationale = (
                " ".join(facts)
                or "The keyed option best matches the stated scientific relationship."
            )
            completion = f"{rationale}\nFinal answer: {answer_key}. {answer_text}"
            record = make_record(
                prompt=prompt,
                completion=completion,
                answer=f"{answer_key}. {answer_text}",
                subject="integrated_science",
                topic="multiple_choice_science",
                difficulty="standard",
                response_format="multiple_choice",
                pedagogy="concise_answer",
                mode="chat",
                split=split,
                source_id=source_id,
                source_revision=source["revision"],
                source_split=source_split,
                source_row_id=f"{source_split}:{row.get('id', '')}",
                semantic_cluster_id=f"row:{source_split}:{row.get('id', '')}",
                license_name=source["license"],
                synthetic=False,
                transform="publisher train split; choices rendered; answer-key text expanded",
                country="not-applicable",
                curriculum_authority="none",
                curriculum_version="none",
                exam_era="not-applicable",
                alignment="general school science; not claimed as WAEC aligned",
                verification={
                    "status": "source_verified",
                    "method": "published answer key",
                    "expected": f"{answer_key}. {answer_text}",
                    "observed": f"{answer_key}. {answer_text}",
                    "verifier_version": VERIFIER_VERSION,
                    "training_eligible": False,
                },
                holdouts=holdouts,
                source_task=source_task,
            )
            if record is not None:
                yield record


def iter_gsm8k(
    *, holdouts: HoldoutIndex, limit: int, seed: int, split: str
) -> Iterator[dict[str, Any]]:
    source = _source("gsm8k")
    dataset = _load_dataset(
        "openai/gsm8k",
        "main",
        split="train",
        revision=source["revision"],
        streaming=True,
    ).shuffle(seed=seed, buffer_size=10_000)
    del limit  # The builder owns the accepted-row limit.
    for row in dataset:
        raw_answer = str(row.get("answer", ""))
        match = re.search(r"####\s*([^\n]+)\s*$", raw_answer)
        if not match:
            continue
        answer = _normalise_number(match.group(1))
        if not _verify_gsm8k_annotations(raw_answer, answer):
            continue
        reasoning = _clean_reasoning(raw_answer[: match.start()])
        completion = f"{reasoning}\nFinal answer: {answer}."
        source_task = str(row.get("question", "")).strip()
        record = make_record(
            prompt=source_task + " Show concise, checkable working.",
            completion=completion,
            answer=answer,
            subject="mathematics",
            topic="word_problems",
            difficulty="standard",
            response_format="free_response",
            pedagogy="worked_solution",
            mode="chat",
            split=split,
            source_id="gsm8k",
            source_revision=source["revision"],
            source_split="train",
            source_row_id=f"train:prompt-sha256:{normalized_sha256(str(row.get('question', '')))}",
            semantic_cluster_id=(
                f"row:train:prompt-sha256:{normalized_sha256(str(row.get('question', '')))}"
            ),
            license_name=source["license"],
            synthetic=False,
            transform="remove calculator annotations; retain human solution and final answer",
            country="not-applicable",
            curriculum_authority="none",
            curriculum_version="none",
            exam_era="not-applicable",
            alignment="foundational word problems; not claimed as WAEC aligned",
            verification={
                "status": "programmatic",
                "method": "restricted-AST verification of every GSM8K calculator annotation",
                "expected": answer,
                "observed": answer,
                "verifier_version": VERIFIER_VERSION,
                "training_eligible": False,
            },
            holdouts=holdouts,
            source_task=source_task,
        )
        if record is not None:
            yield record


def public_evaluation_holdouts() -> tuple[list[str], list[dict[str, Any]]]:
    """Fetch sealed prompts plus prompt-free receipts for each pinned public split."""

    prompts: list[str] = []
    receipts: list[dict[str, Any]] = []
    specs = (
        (
            "gsm8k",
            "openai/gsm8k",
            "main",
            ("test",),
            "question",
            _source("gsm8k")["revision"],
        ),
        (
            "ai2_arc",
            "allenai/ai2_arc",
            "ARC-Easy",
            ("validation", "test"),
            "question",
            _source("ai2_arc")["revision"],
        ),
        (
            "ai2_arc",
            "allenai/ai2_arc",
            "ARC-Challenge",
            ("validation", "test"),
            "question",
            _source("ai2_arc")["revision"],
        ),
        (
            "qasc",
            "allenai/qasc",
            None,
            ("validation", "test"),
            "question",
            _source("qasc")["revision"],
        ),
    )
    for source_id, repo, config, splits, field, revision in specs:
        for source_split in splits:
            kwargs = {"split": source_split, "revision": revision, "streaming": True}
            dataset = (
                _load_dataset(repo, config, **kwargs) if config else _load_dataset(repo, **kwargs)
            )
            split_prompts = [str(row[field]) for row in dataset if row.get(field)]
            prompts.extend(split_prompts)
            normalized = HoldoutIndex(split_prompts)
            receipts.append(
                {
                    "source_id": source_id,
                    "repo": repo,
                    "config": config,
                    "split": source_split,
                    "revision": revision,
                    "prompt_field": field,
                    "raw_prompt_count": len(split_prompts),
                    "normalized_prompt_count": normalized.count,
                    "normalized_prompt_set_sha256": normalized.digest,
                }
            )

    # AfriMGSM is reserved for multilingual African transfer evaluation.  Its
    # test split is parallel across all configurations, so seal every rendered
    # language rather than only the English GSM8K originals.
    afrimgsm_revision = _source("afrimgsm")["revision"]
    for language in (
        "amh",
        "eng",
        "ewe",
        "fra",
        "hau",
        "ibo",
        "kin",
        "lin",
        "lug",
        "orm",
        "sna",
        "sot",
        "swa",
        "twi",
        "wol",
        "xho",
        "yor",
        "zul",
    ):
        dataset = _load_dataset(
            "yuntian-deng/afrimgsm",
            language,
            split="test",
            revision=afrimgsm_revision,
            streaming=True,
        )
        split_prompts = [str(row["question"]) for row in dataset if row.get("question")]
        prompts.extend(split_prompts)
        normalized = HoldoutIndex(split_prompts)
        receipts.append(
            {
                "source_id": "afrimgsm",
                "repo": "yuntian-deng/afrimgsm",
                "config": language,
                "split": "test",
                "revision": afrimgsm_revision,
                "prompt_field": "question",
                "raw_prompt_count": len(split_prompts),
                "normalized_prompt_count": normalized.count,
                "normalized_prompt_set_sha256": normalized.digest,
            }
        )
    return prompts, receipts


def public_evaluation_prompts() -> list[str]:
    """Fetch sealed validation/test prompts for exact and near-duplicate exclusion."""

    prompts, _ = public_evaluation_holdouts()
    return prompts


def validate_deepmind_checkout(path: Path) -> None:
    """Reject an absent or incorrectly pinned DeepMind generator checkout."""

    import subprocess

    expected = _source("deepmind_mathematics")["revision"]
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip() != expected:
        raise ValueError(f"DeepMind checkout must be pinned to {expected}")
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )
    if status.stdout.strip():
        raise ValueError(
            "DeepMind checkout has modified or untracked files; refusing shadowable code"
        )


def deepmind_modules(checkout: Path, *, difficulty: str) -> list[tuple[str, Any]]:
    """Load and flatten the pinned generator's train-only module functions."""

    import importlib
    import sys

    validate_deepmind_checkout(checkout)
    sys.path.insert(0, str(checkout))
    previous_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        composition = importlib.import_module("mathematics_dataset.util.composition")
        install_deepmind_overlay(composition)
        modules = importlib.import_module("mathematics_dataset.modules.modules")
        lower, upper = {"easy": (0.0, 1 / 3), "medium": (1 / 3, 2 / 3), "hard": (2 / 3, 1.0)}[
            difficulty
        ]

        def entropy_fn(bounds: tuple[float, float]) -> tuple[float, float]:
            width = bounds[1] - bounds[0]
            return bounds[0] + lower * width, bounds[0] + upper * width

        nested = modules.train(entropy_fn)
        flattened: list[tuple[str, Any]] = []

        def visit(prefix: str, value: Any) -> None:
            if isinstance(value, dict):
                for key in sorted(value):
                    visit(f"{prefix}__{key}" if prefix else key, value[key])
            else:
                flattened.append((prefix, value))

        visit("", nested)
        return flattened
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode
        sys.path.remove(str(checkout))


def iter_deepmind_mathematics(
    *,
    checkout: Path,
    holdouts: HoldoutIndex,
    limit: int,
    seed: int,
    split: str,
) -> Iterator[dict[str, Any]]:
    """Generate deterministic train-only examples from the pinned source tree."""

    import random

    import numpy as np
    from sympy.core.random import seed as seed_sympy

    source = _source("deepmind_mathematics")
    difficulties = ("easy", "medium", "hard")
    modules_by_difficulty = {
        difficulty: deepmind_modules(checkout, difficulty=difficulty) for difficulty in difficulties
    }
    del limit  # Infinite source; the builder stops after its accepted-row quota.
    attempt = 0
    while True:
        difficulty = difficulties[attempt % len(difficulties)]
        module_rows = modules_by_difficulty[difficulty]
        module_name, module_fn = module_rows[(attempt // len(difficulties)) % len(module_rows)]
        per_row_seed = (seed * 1_000_003 + attempt) % (2**32 - 1)
        random.seed(per_row_seed)
        np.random.seed(per_row_seed)
        seed_sympy(per_row_seed)
        attempt += 1
        try:
            problem = module_fn()
        except (
            ArithmeticError,
            AssertionError,
            RuntimeError,
            TypeError,
            ValueError,
            ZeroDivisionError,
        ):
            continue
        prompt = str(problem.question).strip()
        answer = str(problem.answer).strip()
        if not prompt or not answer or len(prompt) > 3000 or len(answer) > 512:
            continue
        completion = (
            f"Use exact arithmetic and preserve the requested form. Final answer: {answer}."
        )
        record = make_record(
            prompt=prompt,
            completion=completion,
            answer=answer,
            subject="mathematics",
            topic=module_name.replace("__", "_"),
            difficulty={"easy": "foundation", "medium": "standard", "hard": "advanced"}[difficulty],
            response_format="free_response",
            pedagogy="concise_answer",
            mode="chat",
            split=split,
            source_id="deepmind_mathematics",
            source_revision=source["revision"],
            source_split=f"train-{difficulty}",
            source_row_id=f"train-{difficulty}:seed:{per_row_seed}:module:{module_name}",
            semantic_cluster_id=f"module:{module_name}",
            license_name=source["license"],
            synthetic=True,
            transform=(
                "fresh train-regime generation; answer emitted by pinned symbolic generator; "
                f"determinism overlay {OVERLAY_VERSION}"
            ),
            country="not-applicable",
            curriculum_authority="none",
            curriculum_version="none",
            exam_era="not-applicable",
            alignment="general school mathematics; not claimed as WAEC aligned",
            verification={
                "status": "programmatic",
                "method": f"deepmind_generator:{module_name}",
                "expected": answer,
                "observed": answer,
                "verifier_version": f"deepmind:{source['revision']}+{OVERLAY_VERSION}",
                "generator_seed": per_row_seed,
                "training_eligible": True,
            },
            holdouts=holdouts,
            source_task=prompt,
        )
        if record is not None:
            yield record


def take(iterable: Iterable[dict[str, Any]], count: int) -> Iterator[dict[str, Any]]:
    for index, row in enumerate(iterable):
        if index >= count:
            return
        yield row
