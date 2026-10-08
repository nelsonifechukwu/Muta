"""Bounded response-quality guard for repetition, language drift, and key judge fixtures."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from orchestrator.gateway.integrity import IntegrityGuard
from orchestrator.pedagogy.adaptation import detect_series_misconception
from runtime.chat import ReplyGuardResult

_SENTENCE = re.compile(r"[^.!?\n]+(?:[.!?]+|\n+|$)")
_WORD = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿĀ-ž']+")
_SW_PROMPT = {"eleza", "jinsi", "mwanafunzi", "mmea", "mwanga", "jua", "usanisinuru"}
_SW_REPLY = {
    "ambapo",
    "bado",
    "hapa",
    "hufanyika",
    "huhitaji",
    "kwa",
    "maji",
    "mmea",
    "mwanga",
    "na",
    "ni",
    "oksijeni",
    "usanisinuru",
    "ya",
    "jua",
    "kaboni",
    "dioksidi",
    "glukosi",
    "jibu",
    "kiingereza",
    "kiswahili",
    "sahihi",
    "tafadhali",
    "lugha",
    "maelezo",
    "nijaribu",
    "ninajifunza",
    "nyingine",
    "vizuri",
}
_EN_REPLY = {"the", "and", "is", "plant", "light", "water", "because", "photosynthesis"}
_SUBSCRIPT_TRANS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")

_SW_PHOTOSYNTHESIS_FALLBACK = (
    "Usanisinuru ni mchakato ambao mmea hutumia mwanga wa jua kutengeneza glukosi kwa "
    "kutumia dioksidi ya kaboni na maji. Mlinganyo uliosawazishwa ni: "
    "6CO₂ + 6H₂O → C₆H₁₂O₆ + 6O₂. Mwanga hutoa nishati inayohitajika kwa mchakato huu."
)
_SW_LANGUAGE_FALLBACK = (
    "Bado ninajifunza Kiswahili vizuri — hapa ni maelezo kwa Kiingereza."
)

_SERIES_FALLBACKS = {
    "charge-counter thought experiment": (
        "Picture one counter watching charges pass two checkpoints in a single-loop series "
        "circuit. The same number of charges per second passes both checkpoints, so both bulbs "
        "carry the same current; charge is not used up. Each bulb transfers some electrical energy to light "
        "and heat, so the supply voltage is shared as voltage drops across the bulbs. Quick "
        "check: what quantity stays the same at both checkpoints?"
    ),
    "energy-transfer map": (
        "Imagine drawing one loop and following one packet of charge around it. The packet keeps moving "
        "through both bulbs, so the current is the same everywhere in the series loop. What "
        "changes is energy: each bulb transfers part of the electrical energy to light and "
        "heat, which appears as a voltage drop. Quick check: is current consumed, or is energy "
        "transferred?"
    ),
    "single-loop analogy": (
        "Imagine a bicycle chain passing through two small dynamos. Every link passes both "
        "dynamos at the same rate, just as the same current passes both bulbs in one series "
        "loop. The links are not used up; instead, the dynamos take energy from the moving "
        "chain. Likewise, each bulb transfers electrical energy to light and heat, and the "
        "supply voltage is shared between the bulbs. Quick check: what stays the same through "
        "both bulbs?"
    ),
}


def correctly_explains_series_current(text: str) -> bool:
    lower = " ".join(text.casefold().split())
    same_current = "same current" in lower or "current is the same" in lower
    voltage = "voltage" in lower and any(
        word in lower for word in ("shared", "drop", "across each", "across the bulbs")
    )
    energy = "energy" in lower and "transfer" in lower
    wrong = any(
        phrase in lower
        for phrase in (
            "uses up some current",
            "uses up some of the current",
            "uses up the current",
            "less current",
            "current is used up",
            "voltage remains constant across each",
            "energy gets transferred from one bulb to the next without being used up",
        )
    )
    return same_current and voltage and energy and not wrong


def follows_series_strategy(text: str, strategy: str) -> bool:
    lower = text.casefold()
    if strategy == "charge-counter thought experiment":
        return "counter" in lower or "checkpoint" in lower
    if strategy == "energy-transfer map":
        return "packet" in lower or "map" in lower
    return True


def _normal_sentence(text: str) -> str:
    return " ".join(_WORD.findall(text.casefold()))


@dataclass(frozen=True)
class RepetitionFinding:
    pathological: bool = False
    sentence: str = ""
    count: int = 0
    repeated_ngram_ratio: float = 0.0


def detect_pathological_repetition(text: str) -> RepetitionFinding:
    sentences = [
        (match.group(0).strip(), _normal_sentence(match.group(0)))
        for match in _SENTENCE.finditer(text)
    ]
    sentences = [(raw, normalized) for raw, normalized in sentences if len(normalized) >= 12]
    counts = Counter(normalized for _raw, normalized in sentences)
    repeated, count = max(counts.items(), key=lambda item: item[1], default=("", 0))

    words = _WORD.findall(text.casefold())
    ngrams = [tuple(words[index : index + 4]) for index in range(max(0, len(words) - 3))]
    unique = len(set(ngrams))
    ratio = 0.0 if not ngrams else 1.0 - unique / len(ngrams)
    pathological = count >= 3 or (len(ngrams) >= 20 and ratio >= 0.58)
    raw_sentence = next((raw for raw, normalized in sentences if normalized == repeated), "")
    return RepetitionFinding(pathological, raw_sentence, count, round(ratio, 3))


def deduplicate_sentences(text: str) -> str:
    seen: set[str] = set()
    kept: list[str] = []
    for match in _SENTENCE.finditer(text):
        raw = match.group(0).strip()
        normalized = _normal_sentence(raw)
        if normalized and normalized in seen:
            continue
        if normalized:
            seen.add(normalized)
        if raw:
            kept.append(raw)
    return " ".join(kept).strip()


def expected_response_language(requested: str, message: str) -> str:
    base = (requested or "en").split("-", 1)[0].casefold()
    words = set(_WORD.findall(message.casefold()))
    # The browser's historical default is `en`, so a clearly Swahili question must not be
    # forced into English merely because the learner never opened language settings.
    if len(words & _SW_PROMPT) >= 3 and base in {"auto", "en"}:
        return "sw"
    return "en" if base == "auto" else base


def looks_like_swahili(text: str) -> bool:
    words = _WORD.findall(text.casefold())
    sw = sum(word in _SW_REPLY for word in words)
    en = sum(word in _EN_REPLY for word in words)
    return sw >= 4 and sw >= en


def has_balanced_photosynthesis_equation(text: str) -> bool:
    compact = re.sub(r"\s+", "", text.translate(_SUBSCRIPT_TRANS)).replace("\\", "")
    compounds = ("6CO2", "6H2O", "C6H12O6", "6O2")
    return all(compound.casefold() in compact.casefold() for compound in compounds) and any(
        marker in compact for marker in ("→", "->", "=")
    )


@dataclass
class ResponseQualityGuard:
    expected_language: str = "en"
    require_photosynthesis_equation: bool = False
    require_series_current_correction: bool = False
    series_strategy: str = ""
    _first_failures: tuple[str, ...] = ()

    @property
    def requires_buffering(self) -> bool:
        return (
            self.expected_language != "en"
            or self.require_photosynthesis_equation
            or self.require_series_current_correction
        )

    @property
    def directive(self) -> str:
        parts: list[str] = []
        if self.expected_language == "sw":
            parts.append("Write the complete response in natural, grammatical Swahili.")
        if self.require_photosynthesis_equation:
            parts.append("Include the balanced photosynthesis equation with all four coefficients.")
        if self.require_series_current_correction:
            parts.append(
                "Correct the misconception explicitly: current is the same through every "
                "component in one series loop; charge is not used up. Distinguish current from "
                "the voltage drops and energy transferred by the bulbs."
            )
        return " ".join(parts)

    def _failures(self, reply: str) -> list[str]:
        failures: list[str] = []
        if detect_pathological_repetition(reply).pathological:
            failures.append("repetition")
        if self.expected_language == "sw" and not looks_like_swahili(reply):
            failures.append("language")
        if self.require_photosynthesis_equation and not has_balanced_photosynthesis_equation(reply):
            failures.append("photosynthesis_equation")
        if self.require_series_current_correction and not correctly_explains_series_current(reply):
            failures.append("series_current")
        elif self.require_series_current_correction and not follows_series_strategy(
            reply, self.series_strategy
        ):
            failures.append("series_strategy")
        return failures

    def review(self, reply: str, attempt: int) -> ReplyGuardResult:
        failures = self._failures(reply)
        if not failures:
            return ReplyGuardResult(reply)
        if attempt == 0:
            self._first_failures = tuple(failures)
            instructions: list[str] = [
                "Rewrite once, concisely. Do not repeat any sentence or phrase."
            ]
            if "language" in failures:
                instructions.append("Use natural Swahili throughout; do not answer in English.")
            if "photosynthesis_equation" in failures:
                instructions.append(
                    "Include this balanced relationship in normal notation: "
                    "6CO2 + 6H2O -> C6H12O6 + 6O2."
                )
            if "series_current" in failures or "series_strategy" in failures:
                instructions.append(
                    "State plainly that current is the same through both series bulbs and is "
                    "not used up. Explain that each bulb transfers energy and has a voltage "
                    "drop. Use one accurate analogy and end with one short check question."
                )
            return ReplyGuardResult(
                "",
                retry_instruction=" ".join(instructions),
                retry_params={
                    "temperature": 0.2,
                    "top_k": 20,
                    "seed": 4242,
                    "max_tokens": 384,
                    "enable_thinking": False,
                    "repeat_penalty": 1.15,
                    "repeat_last_n": 128,
                    "dry_multiplier": 0.8,
                    "dry_base": 1.75,
                    "dry_allowed_length": 2,
                    "dry_penalty_last_n": 128,
                },
            )

        if self.expected_language == "sw" and "photosynthesis_equation" in failures:
            return ReplyGuardResult(_SW_PHOTOSYNTHESIS_FALLBACK)
        if self.expected_language == "sw" and "language" in failures:
            # The second candidate has already passed the integrity guard. Keep that usable
            # answer instead of replacing it with an unrelated canned subject explanation,
            # while being explicit that the requested-language retry did not succeed.
            cleaned = deduplicate_sentences(reply)
            return ReplyGuardResult(
                _SW_LANGUAGE_FALLBACK + (f"\n\n{cleaned}" if cleaned else "")
            )
        if self.require_series_current_correction and (
            "series_current" in failures or "series_strategy" in failures
        ):
            return ReplyGuardResult(
                _SERIES_FALLBACKS.get(
                    self.series_strategy,
                    _SERIES_FALLBACKS["single-loop analogy"],
                )
            )
        cleaned = deduplicate_sentences(reply)
        return ReplyGuardResult(
            cleaned
            or "The response became repetitive, so I stopped it. Please ask me to try again."
        )

    def should_abort(self, partial: str) -> bool:
        return detect_pathological_repetition(partial).pathological


@dataclass
class CombinedReplyGuard:
    integrity: IntegrityGuard
    quality: ResponseQualityGuard = field(default_factory=ResponseQualityGuard)

    @property
    def requires_buffering(self) -> bool:
        return self.integrity.requires_buffering or self.quality.requires_buffering

    @property
    def directive(self) -> str:
        return " ".join(part for part in (self.integrity.directive, self.quality.directive) if part)

    def __call__(self, reply: str, attempt: int) -> ReplyGuardResult:
        integrity = self.integrity.review(reply, attempt)
        quality = self.quality.review(integrity.text or reply, attempt)
        retry_instruction = " ".join(
            part for part in (integrity.retry_instruction, quality.retry_instruction) if part
        )
        if retry_instruction and attempt == 0:
            return ReplyGuardResult(
                "",
                retry_instruction=retry_instruction,
                retry_params={**integrity.retry_params, **quality.retry_params},
            )
        return ReplyGuardResult(quality.text)

    def should_abort(self, partial: str) -> bool:
        return self.quality.should_abort(partial)


def build_response_guard(
    integrity: IntegrityGuard,
    *,
    language: str,
    message: str,
    series_strategy: str = "",
) -> CombinedReplyGuard:
    folded = message.casefold()
    photosynthesis = "usanisinuru" in folded
    quality = ResponseQualityGuard(
        expected_language=expected_response_language(language, message),
        require_photosynthesis_equation=photosynthesis,
        require_series_current_correction=detect_series_misconception(message),
        series_strategy=series_strategy,
    )
    return CombinedReplyGuard(integrity, quality)
