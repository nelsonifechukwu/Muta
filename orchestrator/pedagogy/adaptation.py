"""Deterministic learner-friction detection and strategy selection.

Only explicit preferences and observable work patterns are stored. The harness never infers
ability, culture, personality, or demographic attributes from a learner's wording.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from orchestrator.pedagogy.twin import LearningTwin

if TYPE_CHECKING:
    from orchestrator.gateway.integrity import StudentWorkFinding

_CONFUSION = {
    "en": (
        "i don't understand",
        "i dont understand",
        "still don't understand",
        "still dont understand",
        "still confused",
        "doesn't make sense",
    ),
    "sw": ("sielewi", "bado sijaelewa", "nimechanganyikiwa"),
    "yo": ("ko ye mi", "mi o ye", "mo tun dapo"),
    "ha": ("ban gane ba", "har yanzu ban gane ba", "na rikice"),
    "ig": ("aghọtaghị m", "amataghị m", "m ka gbagwojuru anya"),
    "fr": ("je ne comprends pas", "toujours confus", "ça n'a pas de sens"),
}
_PREFERENCE_PATTERNS: tuple[tuple[str, str, str], ...] = (
    (r"\b(?:learn|understand) better (?:from|with) (?:everyday )?examples?\b", "style", "examples"),
    (r"\b(?:prefer|like) (?:everyday )?examples?\b", "style", "examples"),
    (r"\b(?:show|use) (?:me )?(?:a )?diagram\b|\bvisual learner\b", "style", "visual"),
    (r"\bstep[ -]by[ -]step\b", "pace", "step_by_step"),
    (r"\bexplain why\b|\bwhy the steps work\b", "reasoning", "explain_why"),
    (r"\b(?:keep it|be) (?:short|brief|concise)\b", "length", "concise"),
)

_STRATEGIES = {
    "series_current_used_up": (
        "single-loop analogy",
        "charge-counter thought experiment",
        "energy-transfer map",
    ),
    "distribution_error": ("area model", "substitution check", "term-by-term colour grouping"),
    "inverse_operation_error": (
        "balance-scale analogy",
        "operation-undo table",
        "substitution check",
    ),
    "sign_error": ("number-line check", "substitution check", "balance-scale analogy"),
    "final_answer_wrong": ("substitution check", "work backwards", "one-step diagnostic question"),
    "confusion": ("concrete example", "worked counterexample", "diagnostic question"),
}


def _fold(text: str) -> str:
    value = unicodedata.normalize("NFKD", text.casefold())
    return " ".join("".join(ch for ch in value if not unicodedata.combining(ch)).split())


def detect_confusion(message: str) -> tuple[str, ...]:
    folded = _fold(message)
    return tuple(
        language
        for language, phrases in _CONFUSION.items()
        if any(_fold(phrase) in folded for phrase in phrases)
    )


def detect_preferences(message: str) -> dict[str, str]:
    folded = _fold(message)
    found: dict[str, str] = {}
    for pattern, key, value in _PREFERENCE_PATTERNS:
        if re.search(pattern, folded):
            found[key] = value
    return found


def detect_series_misconception(message: str) -> bool:
    folded = _fold(message)
    return bool(
        re.search(r"first bulb.*(?:uses? up|took).*current", folded)
        or re.search(r"second bulb.*less current", folded)
    )


@dataclass(frozen=True)
class TurnAdaptation:
    directive: str = ""
    preferences: dict[str, str] = field(default_factory=dict)
    friction_tags: tuple[str, ...] = ()
    strategy: str = ""
    previous_strategy: str = ""
    switched_strategy: bool = False
    observation_count: int = 0

    def metadata(self) -> dict | None:
        if not (self.preferences or self.friction_tags or self.strategy):
            return None
        return {
            "preferences": self.preferences,
            "friction_tags": list(self.friction_tags),
            "strategy": self.strategy or None,
            "switched_strategy": self.switched_strategy,
            "observation_count": self.observation_count,
        }


def _mode_instruction(mode: str) -> str:
    if mode in {"hint", "hints"}:
        return "Give one next-step hint and return the work; withhold the final answer."
    if mode in {"subgoal", "solution"}:
        return "Break the explanation into one small subgoal at a time and check it."
    return "Ask one short diagnostic question after the changed explanation."


def plan_turn_adaptation(
    twin: LearningTwin,
    message: str,
    *,
    subject: str,
    mode: str,
    finding: StudentWorkFinding | None = None,
) -> TurnAdaptation:
    """Update the bounded twin facts and produce a prompt-suffix directive for this turn."""
    preferences = detect_preferences(message)
    for key, value in preferences.items():
        twin.record_preference(key, value)

    tags: list[str] = []
    if finding is not None and finding.checked and not finding.equivalent and finding.error_class:
        tags.append(finding.error_class)
    if detect_series_misconception(message):
        tags.append("series_current_used_up")
    if detect_confusion(message):
        tags.append("confusion")
    tags = list(dict.fromkeys(tags))

    primary = tags[0] if tags else ""
    previous = twin.last_strategy.get(primary, "") if primary else ""
    count = twin.record_misconception(primary) if primary else 0
    options = _STRATEGIES.get(primary, _STRATEGIES["confusion"])
    if primary:
        try:
            index = (options.index(previous) + 1) % len(options)
        except ValueError:
            index = 0
        strategy = options[index]
        twin.remember_strategy(primary, strategy)
    else:
        strategy = ""

    parts: list[str] = []
    merged_preferences = {**twin.preferences, **preferences}
    if merged_preferences.get("style") == "examples":
        parts.append("Begin with a concrete everyday example before formulas.")
    elif merged_preferences.get("style") == "visual":
        parts.append("Use a compact spatial or diagram-like explanation before formulas.")
    if merged_preferences.get("reasoning") == "explain_why":
        parts.append(
            "Explain why each operation preserves the relationship; do not give a rule to "
            "memorize."
        )
    if merged_preferences.get("pace") == "step_by_step":
        parts.append("Present exactly one step at a time and check understanding before the next.")
    if merged_preferences.get("length") == "concise":
        parts.append("Keep the response concise.")
    if primary:
        if previous:
            parts.append(
                f"The learner has repeated {primary}. Do not reuse {previous}; switch to "
                f"{strategy}."
            )
        else:
            parts.append(f"Address {primary} using {strategy}.")
        if "different explanation" in _fold(message) or count >= 2:
            alternative = options[(options.index(strategy) + 1) % len(options)]
            parts.append(
                "If the learner repeats the claim inside this task, change again to "
                f"{alternative}; "
                "do not restate the first explanation."
            )
        parts.append(_mode_instruction(mode))
    if subject:
        parts.append(f"Keep the adaptation scientifically accurate for {subject}.")

    return TurnAdaptation(
        directive=" ".join(parts),
        preferences=preferences,
        friction_tags=tuple(tags),
        strategy=strategy,
        previous_strategy=previous,
        switched_strategy=bool(previous and strategy != previous),
        observation_count=count,
    )
