"""Shared schema, provenance, leakage, and quality controls."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .tokenization import (
    CHAT_TEMPLATE_SHA256,
    DEFAULT_MAX_SEQUENCE_TOKENS,
    TOKENIZER_ID,
    TOKENIZER_REVISION,
)

VERIFIER_VERSION = "muta-stem-v2.4"
ALLOWED_SOURCE_STATUSES = {
    "enabled",
    "enabled_anchor",
    "enabled_optional",
    "enabled_silver",
}
FORBIDDEN_OUTPUT_MARKERS = (
    "<think>",
    "</think>",
    "[start thinking]",
    "[end thinking]",
    "as an ai language model",
)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def normalize_text(text: str) -> str:
    """Canonicalise text without erasing mathematically meaningful symbols.

    A word-only normaliser makes ``x = 5`` indistinguishable from ``x = -5``
    and turns decimal/fraction changes into hash collisions.  The canonical
    form intentionally keeps arithmetic relations while discarding prose
    punctuation and layout.
    """

    # Canonicalise conventional thousands grouping before punctuation is
    # discarded.  Without this, ``18,000`` became ``18 000`` while ``18000``
    # remained one token, allowing a formatting-only holdout bypass.
    grouped_number = re.compile(
        r"(?<![\w.])[+-]?\d{1,3}(?:[,\u00a0\u202f ]\d{3})+(?:\.\d+)?(?!\w|\.\d)"
    )
    text = grouped_number.sub(
        lambda match: re.sub(r"[,\u00a0\u202f ]", "", match.group(0)),
        text,
    )

    fraction_map = {
        "½": "1/2",
        "⅓": "1/3",
        "⅔": "2/3",
        "¼": "1/4",
        "¾": "3/4",
        "⅕": "1/5",
        "⅖": "2/5",
        "⅗": "3/5",
        "⅘": "4/5",
        "⅙": "1/6",
        "⅚": "5/6",
        "⅛": "1/8",
        "⅜": "3/8",
        "⅝": "5/8",
        "⅞": "7/8",
    }
    superscript_map = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻", "0123456789+-")
    text = "".join(fraction_map.get(character, character) for character in text)
    text = re.sub(
        r"[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+",
        lambda match: "^" + match.group(0).translate(superscript_map),
        text,
    )
    text = text.replace("√", " sqrt ").replace("⁄", "/")
    text = unicodedata.normalize("NFKC", text).casefold()
    text = text.translate(
        str.maketrans(
            {
                "−": "-",
                "–": "-",
                "—": "-",
                "×": "*",
                "·": "*",
                "÷": "/",
            }
        )
    )
    tokens = re.findall(r"[a-z]+|\d+(?:\.\d+)?|<=|>=|!=|[+\-*/=<>%^]", text)
    return " ".join(tokens)


def normalized_sha256(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def word_ngrams(text: str, width: int = 5) -> frozenset[str]:
    words = normalize_text(text).split()
    if not words:
        return frozenset()
    if len(words) < width:
        return frozenset({" ".join(words)})
    return frozenset(" ".join(words[i : i + width]) for i in range(len(words) - width + 1))


def jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import holdout module {path}")
    module = importlib.util.module_from_spec(spec)
    # dataclasses and a few other stdlib helpers resolve annotations through
    # sys.modules while a module is executing.
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


def _local_holdout_prompts(root: Path) -> list[str]:
    prompts: list[str] = []
    modules = (
        (root / "bench" / "judges_prompt_suite.py", "muta_judge_holdouts"),
        (root / "bench" / "stem_prompt_suite.py", "muta_stem_holdouts"),
    )
    for path, name in modules:
        if not path.exists():
            raise FileNotFoundError(
                f"required holdout source is missing: {path}; refusing a leakage-blind build"
            )
        module = _load_module(path, name)
        prompts.extend(str(item.text) for item in module.prompts())

    live_battery = root / "bench" / "live_prompt_battery.py"
    if not live_battery.exists():
        raise FileNotFoundError(
            f"required holdout source is missing: {live_battery}; refusing a leakage-blind build"
        )
    live_module = _load_module(live_battery, "muta_live_prompt_holdouts")
    prompts.extend(str(item["text"]) for item in live_module.PROMPTS)

    metadata_paths = (
        root / "bench" / "submission" / "metadata.json",
        root / "muta-adtc-2026" / "metadata.json",
    )
    for path in metadata_paths:
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        prompts.extend(
            str(item["prompt"]) for item in payload.get("test_prompts", []) if item.get("prompt")
        )
    return prompts


class HoldoutIndex:
    """Fast exact and five-gram overlap checks against sealed local evaluations."""

    def __init__(self, prompts: Iterable[str], *, threshold: float = 0.82) -> None:
        unique = {normalize_text(prompt): prompt for prompt in prompts if normalize_text(prompt)}
        self.threshold = threshold
        self._normalized = frozenset(unique)
        self._ngrams = [word_ngrams(prompt) for prompt in unique.values()]
        self._inverted: dict[str, set[int]] = defaultdict(set)
        for index, grams in enumerate(self._ngrams):
            for gram in grams:
                self._inverted[gram].add(index)
        joined = "\n".join(sorted(self._normalized))
        self.digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()

    @classmethod
    def from_repository(cls, root: Path | None = None, *, threshold: float = 0.82) -> HoldoutIndex:
        return cls(_local_holdout_prompts(root or repository_root()), threshold=threshold)

    @property
    def count(self) -> int:
        return len(self._normalized)

    def compare(self, prompt: str) -> tuple[bool, float]:
        normalized = normalize_text(prompt)
        if normalized in self._normalized:
            return True, 1.0
        grams = word_ngrams(prompt)
        candidate_ids: set[int] = set()
        for gram in grams:
            candidate_ids.update(self._inverted.get(gram, ()))

        def similarity(index: int) -> float:
            heldout = self._ngrams[index]
            intersection = len(grams & heldout)
            containment = intersection / min(len(grams), len(heldout))
            return max(jaccard(grams, heldout), containment)

        maximum = max((similarity(i) for i in candidate_ids), default=0.0)
        return maximum >= self.threshold, maximum


def load_source_registry(path: Path | None = None) -> dict[str, dict[str, Any]]:
    registry_path = path or Path(__file__).with_name("source_registry.json")
    payload = load_source_registry_document(registry_path)
    return index_source_registry_document(payload)


def index_source_registry_document(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Validate and index one already-loaded source-registry snapshot."""

    if not isinstance(payload.get("policy"), dict):
        raise TypeError("source registry must contain a policy object")
    rows = payload.get("sources")
    if not isinstance(rows, list):
        raise TypeError("source registry must contain a sources list")
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        source_id = str(row.get("id", ""))
        if not source_id or source_id in indexed:
            raise ValueError(f"invalid or duplicate source id {source_id!r}")
        indexed[source_id] = row
    return indexed


def load_source_registry_document(path: Path | None = None) -> dict[str, Any]:
    registry_path = path or Path(__file__).with_name("source_registry.json")
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("policy"), dict):
        raise TypeError("source registry must contain a policy object")
    return payload


def current_git_revision(root: Path | None = None) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root or repository_root(),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def record_id_for(record: dict[str, Any]) -> str:
    """Recompute the immutable identity fields for a record."""

    provenance = record.get("provenance") or {}
    stable = json.dumps(
        [
            provenance.get("source_id"),
            provenance.get("source_revision"),
            provenance.get("source_split"),
            provenance.get("source_row_id"),
            provenance.get("semantic_cluster_id"),
            (record.get("contamination") or {}).get("source_task_sha256"),
            record.get("prompt"),
            record.get("completion"),
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return "muta2_" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:24]


def make_record(
    *,
    prompt: str,
    completion: str,
    answer: str,
    subject: str,
    topic: str,
    difficulty: str,
    response_format: str,
    pedagogy: str,
    mode: str,
    split: str,
    source_id: str,
    source_revision: str,
    source_split: str,
    source_row_id: str,
    semantic_cluster_id: str,
    license_name: str,
    synthetic: bool,
    transform: str,
    country: str,
    curriculum_authority: str,
    curriculum_version: str,
    exam_era: str,
    alignment: str,
    verification: dict[str, Any],
    holdouts: HoldoutIndex,
    source_task: str | None = None,
) -> dict[str, Any] | None:
    prompt = prompt.strip()
    completion = completion.strip()
    answer = answer.strip()
    source_task = (source_task if source_task is not None else prompt).strip()
    blocked, similarity = holdouts.compare(prompt)
    if blocked:
        return None
    record = {
        "id": "",
        "prompt": prompt,
        "completion": completion,
        "messages": [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": completion},
        ],
        "answer": answer,
        "subject": subject,
        "topic": topic,
        "difficulty": difficulty,
        "format": response_format,
        "pedagogy": pedagogy,
        "language": "en",
        "mode": mode,
        "split": split,
        "curriculum": {
            "country": country,
            "authority": curriculum_authority,
            "version": curriculum_version,
            "exam_era": exam_era,
            "alignment": alignment,
        },
        "provenance": {
            "source_id": source_id,
            "source_revision": source_revision,
            "source_split": source_split,
            "source_row_id": source_row_id,
            "semantic_cluster_id": semantic_cluster_id,
            "license": license_name,
            "synthetic": synthetic,
            "transform": transform,
        },
        "verification": verification,
        "contamination": {
            "source_task_sha256": normalized_sha256(source_task),
            "normalized_prompt_sha256": normalized_sha256(prompt),
            "holdout_checked": True,
            "max_holdout_5gram_similarity": round(similarity, 6),
        },
    }
    record["id"] = record_id_for(record)
    return record


def _answer_signature(text: str) -> str:
    return normalize_text(text)


def _contains_token_sequence(container: str, candidate: str) -> bool:
    container_tokens = container.split()
    candidate_tokens = candidate.split()
    if not candidate_tokens or len(candidate_tokens) > len(container_tokens):
        return False
    width = len(candidate_tokens)
    return any(
        container_tokens[index : index + width] == candidate_tokens
        for index in range(len(container_tokens) - width + 1)
    )


def validate_record(
    record: dict[str, Any],
    *,
    source_registry: dict[str, dict[str, Any]] | None = None,
    source_policy: dict[str, Any] | None = None,
    holdouts: HoldoutIndex | None = None,
    token_counter: Any | None = None,
) -> list[str]:
    errors: list[str] = []
    required = {
        "id",
        "prompt",
        "completion",
        "messages",
        "answer",
        "subject",
        "topic",
        "difficulty",
        "format",
        "pedagogy",
        "language",
        "mode",
        "split",
        "curriculum",
        "provenance",
        "verification",
        "contamination",
    }
    missing = sorted(required - set(record))
    if missing:
        return [f"missing fields: {', '.join(missing)}"]
    prompt = record.get("prompt")
    completion = record.get("completion")
    answer = record.get("answer")
    if not isinstance(prompt, str) or not isinstance(completion, str):
        return ["prompt and completion must be strings"]
    if not isinstance(answer, str):
        return ["answer must be a string"]
    if not prompt.strip() or not completion.strip():
        errors.append("empty prompt or completion")
    if len(prompt) > 6000 or len(completion) > 6000:
        errors.append("prompt or completion exceeds 6000 characters")
    messages = record.get("messages")
    expected_messages = [
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": completion},
    ]
    if messages != expected_messages:
        errors.append("messages do not mirror prompt/completion")
    if record.get("id") != record_id_for(record):
        errors.append("record id does not match immutable identity fields")
    lowered = completion.casefold()
    if any(marker in lowered for marker in FORBIDDEN_OUTPUT_MARKERS):
        errors.append("completion contains hidden-reasoning or model-disclaimer marker")
    answer_signature = _answer_signature(answer)
    completion_signature = _answer_signature(completion)
    if record.get("pedagogy") != "socratic_hint" and not _contains_token_sequence(
        completion_signature, answer_signature
    ):
        errors.append("answer is not present in completion")
    if record.get("pedagogy") == "socratic_hint" and "final answer" in lowered:
        errors.append("socratic hint discloses a final answer")
    verification = record.get("verification") or {}
    verified_statuses = {
        "programmatic",
        "source_verified",
        "human_reviewed",
        "silver_pending_audit",
        "model_assisted_reviewed",
    }
    if verification.get("status") in verified_statuses and str(verification.get("expected")) != str(
        verification.get("observed")
    ):
        errors.append("verification expected/observed mismatch")
    if verification.get("status") in verified_statuses and str(verification.get("expected")) != str(
        record.get("answer")
    ):
        errors.append("verification expected does not match record answer")
    contamination = record.get("contamination") or {}
    if not contamination.get("holdout_checked"):
        errors.append("holdout check missing")
    expected_prompt_hash = normalized_sha256(str(record.get("prompt", "")))
    if contamination.get("normalized_prompt_sha256") != expected_prompt_hash:
        errors.append("normalized prompt hash mismatch")
    source_task_hash = contamination.get("source_task_sha256")
    if not isinstance(source_task_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", source_task_hash):
        errors.append("canonical source-task hash is missing or malformed")
    if holdouts is not None:
        blocked, similarity = holdouts.compare(str(record.get("prompt", "")))
        if blocked:
            errors.append("prompt overlaps a sealed holdout")
        if contamination.get("max_holdout_5gram_similarity") != round(similarity, 6):
            errors.append("stored holdout similarity does not match recomputation")
    curriculum = record.get("curriculum") or {}
    for field in ("country", "authority", "version", "exam_era", "alignment"):
        if not str(curriculum.get(field, "")).strip():
            errors.append(f"curriculum.{field} is missing")
    registry = source_registry or load_source_registry()
    policy = (
        source_policy
        if source_policy is not None
        else load_source_registry_document().get("policy", {})
    )
    allowed_licenses = set(policy.get("allowed_licenses") or ())
    provenance = record.get("provenance", {})
    source_id = provenance.get("source_id")
    source = registry.get(source_id)
    if source is None:
        errors.append(f"source {source_id!r} absent from registry")
    elif source.get("status") not in ALLOWED_SOURCE_STATUSES:
        errors.append(f"source {source_id!r} is not enabled")
    elif provenance.get("license") != source.get("license"):
        errors.append("row licence does not match source registry")
    else:
        if provenance.get("license") not in allowed_licenses:
            errors.append("row licence is not in the registry policy allowlist")
        source_revision = str(provenance.get("source_revision", ""))
        registry_revision = str(source.get("revision", ""))
        if registry_revision == "resolved_from_content_snapshot_at_build_time":
            if re.fullmatch(r"sha256:[0-9a-f]{64}", source_revision) is None:
                errors.append("generated source revision is not a content-addressed SHA-256")
        elif source_revision != registry_revision:
            errors.append("row source revision does not match source registry")
        source_split = str(provenance.get("source_split", ""))
        allowed_splits = set(source.get("allowed_splits") or ())
        if source_split not in allowed_splits:
            errors.append("row source split is not allowed by the source registry")
        source_row_id = str(provenance.get("source_row_id", ""))
        if not source_row_id.startswith(f"{source_split}:"):
            errors.append("source row id is not namespaced by its source split")
        allowed_statuses = set(source.get("allowed_verification_statuses") or ())
        if verification.get("status") not in allowed_statuses:
            errors.append("verification status is not allowed for this source")
        expected_eligibility = source.get("warehouse_training_eligible")
        if not isinstance(expected_eligibility, bool):
            errors.append("source registry omits warehouse training eligibility")
        elif verification.get("training_eligible") is not expected_eligibility:
            errors.append("row training eligibility does not match the source audit gate")
        expected_synthetic = source.get("synthetic")
        if not isinstance(expected_synthetic, bool):
            errors.append("source registry omits synthetic provenance policy")
        elif provenance.get("synthetic") is not expected_synthetic:
            errors.append("row synthetic flag does not match the source registry")
    if not str(provenance.get("source_row_id", "")).strip():
        errors.append("source row id is missing")
    semantic_cluster_id = str(provenance.get("semantic_cluster_id", ""))
    if not semantic_cluster_id:
        errors.append("semantic cluster id is missing")
    elif source_id == "muta_verified_stem_v2":
        if semantic_cluster_id != f"formula:{verification.get('method', '')}":
            errors.append("local semantic cluster does not match its formula family")
    elif source_id == "deepmind_mathematics":
        method = str(verification.get("method", ""))
        expected_cluster = f"module:{method.removeprefix('deepmind_generator:')}"
        if not method.startswith("deepmind_generator:") or semantic_cluster_id != expected_cluster:
            errors.append("DeepMind semantic cluster does not match its generator module")
    elif source_id == "template_gsm":
        if semantic_cluster_id != f"template:{verification.get('template_id', '')}":
            errors.append("TemplateGSM semantic cluster does not match its template")
    elif (
        source_id
        in {
            "nemotron_science_v1",
            "qasc",
            "gsm8k",
        }
        and semantic_cluster_id != f"row:{provenance.get('source_row_id', '')}"
    ):
        errors.append("row-level semantic cluster does not match its source row")
    if source_id == "muta_verified_stem_v2" and verification.get("status") == "programmatic":
        # Import lazily to avoid a module cycle at import time.  This prevents
        # an attacker from changing answer/completion/expected together and
        # merely recomputing the record ID.
        from .generators import verify_local_record

        if not verify_local_record(record):
            errors.append("local answer does not recompute from verifier inputs")
    tokenization = record.get("tokenization")
    if tokenization is not None:
        sequence_tokens = tokenization.get("sequence_tokens")
        maximum = tokenization.get("max_sequence_tokens")
        if not isinstance(sequence_tokens, int) or not isinstance(maximum, int):
            errors.append("tokenization counts must be integers")
        elif sequence_tokens <= 0 or maximum <= 0 or sequence_tokens > maximum:
            errors.append("training sequence exceeds the configured token limit")
        if tokenization.get("within_limit") is not True:
            errors.append("tokenization is not marked within_limit")
        if tokenization.get("tokenizer_id") != TOKENIZER_ID:
            errors.append("tokenizer id does not match the pinned base model")
        if tokenization.get("tokenizer_revision") != TOKENIZER_REVISION:
            errors.append("tokenizer revision does not match the pinned base model")
        if tokenization.get("chat_template_sha256") != CHAT_TEMPLATE_SHA256:
            errors.append("chat template hash does not match the pinned base model")
        if isinstance(maximum, int) and maximum > DEFAULT_MAX_SEQUENCE_TOKENS:
            errors.append("tokenization limit exceeds the training context limit")
        if token_counter is not None and not token_counter.validate(record):
            errors.append("stored token count does not match exact re-tokenization")
    return errors


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
