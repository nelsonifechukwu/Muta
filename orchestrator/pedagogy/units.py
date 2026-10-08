"""Authoritative offline unit catalogue used by the checkpoint verifier."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from runtime.paths import resource_root

_source_units = Path(__file__).resolve().parents[2] / "ui" / "units"


def resolve_units_dir(root: Path | None = None) -> Path:
    """Resolve source and packaged unit layouts, preferring the shipped browser bundle."""
    installed_root = root or resource_root()
    candidates = (
        installed_root / "ui" / "dist" / "units",
        installed_root / "ui" / "units",
        _source_units,
    )
    return next((candidate for candidate in candidates if candidate.is_dir()), _source_units)


UNITS_DIR = resolve_units_dir()
KNOWN_UNITS = {
    "linear-equations-keeping-the-balance": "linear-equations-keeping-the-balance.json",
    "forces-and-motion": "forces-and-motion.json",
    "balancing-chemical-equations": "balancing-chemical-equations.json",
    "photosynthesis-energy-flow": "photosynthesis-energy-flow.json",
}
UNIT_ANSWER_KEYS = {
    "linear-equations-keeping-the-balance": {
        "q1": "8",
        "q2": "-4",
        "q3": "5",
        "q4": "3",
        "q5": "7",
    },
    "forces-and-motion": {"q1": "0", "q2": "4", "q3": "5", "q4": "12", "q5": "-3"},
    "balancing-chemical-equations": {
        "q1": "2", "q2": "1", "q3": "3", "q4": "2", "q5": "3",
    },
    "photosynthesis-energy-flow": {
        "q1": "6", "q2": "6", "q3": "6", "q4": "6", "q5": "12",
    },
}
VERIFIED_UNIT_TOPICS = frozenset(
    {"linear_equations", "forces_motion", "chemical_equations", "photosynthesis"}
)


@lru_cache(maxsize=len(KNOWN_UNITS))
def load_unit(unit_id: str) -> dict:
    """Load only a checked-in unit; browser imports never define answer authority."""
    filename = KNOWN_UNITS.get(unit_id)
    if filename is None:
        raise KeyError(unit_id)
    path = UNITS_DIR / filename
    if not path.is_file() and UNITS_DIR != _source_units:
        path = _source_units / filename
    payload = json.loads(path.read_text())
    if payload.get("id") != unit_id or payload.get("version") != 1:
        raise ValueError(f"invalid offline unit: {unit_id}")
    questions = payload.get("checkpoint", {}).get("questions", [])
    answer_key = UNIT_ANSWER_KEYS[unit_id]
    if len(questions) != 5 or {row.get("id") for row in questions} != set(answer_key):
        raise ValueError(f"invalid checkpoint: {unit_id}")
    for question in questions:
        question["expected"] = answer_key[question["id"]]
    return payload
