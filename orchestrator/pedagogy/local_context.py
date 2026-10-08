"""Small, reviewed country context for locally meaningful examples and exam framing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).resolve().parent / "data" / "africa_context.json"
_SETTING_KEYS = ("study_country", "study_country_code", "country", "country_code")


@dataclass(frozen=True)
class LocalContext:
    code: str
    name: str
    currency: str = ""
    exams: tuple[str, ...] = ()

    @property
    def directive(self) -> str:
        parts = [
            f"The learner's selected study country is {self.name}.",
            "Use local context only when it makes the idea clearer; never force a cultural story.",
        ]
        if self.currency:
            parts.append(
                f"For useful money examples, use {self.currency}; do not substitute dollars "
                "or another currency."
            )
        if self.exams:
            parts.append("For relevant exam framing, use " + ", ".join(self.exams) + ".")
        parts.append(
            "Country context must never change whether a factual or mathematical claim is true."
        )
        return " ".join(parts)


@lru_cache(maxsize=1)
def country_contexts() -> dict[str, LocalContext]:
    raw = json.loads(_DATA.read_text(encoding="utf-8"))
    return {
        code: LocalContext(
            code=code,
            name=str(value["name"]),
            currency=str(value.get("currency") or ""),
            exams=tuple(str(item) for item in value.get("exams") or ()),
        )
        for code, value in raw.items()
    }


def context_from_settings(settings: dict | None) -> LocalContext | None:
    if not isinstance(settings, dict):
        return None
    value = next((settings.get(key) for key in _SETTING_KEYS if settings.get(key)), None)
    if not isinstance(value, str):
        return None
    contexts = country_contexts()
    normalized = value.strip().upper()
    if normalized in contexts:
        return contexts[normalized]
    folded = value.strip().casefold()
    return next((item for item in contexts.values() if item.name.casefold() == folded), None)
