"""Deterministic exam-prep item selection over a curated question bank.

Self-contained: no FastAPI, no network, no engine. The lead engineer wires
``generate()`` into the ``exam`` sub-app's ``/generate_question`` route; this module
just turns a request (subject, topic, difficulty, exam_board, count) into a list of
dicts that are each shaped *exactly* like ``contracts.models.GeneratedQuestion`` — so
``GeneratedQuestion(**d)`` validates without massaging.

Design notes (the "why", per the working method):

* **Deterministic.** The same request always yields the same items in the same order.
  Selection is a pure ranking of the bank — no randomness, no clock. Reproducibility is
  a hard requirement of the contract test and of any contamination/eval work that diffs
  real-vs-generated items.
* **Relax, don't starve.** The request's ``topic`` and ``difficulty`` are *preferences*,
  not hard filters. We score every item of the subject and take the best ``count`` of
  them, so a request never returns fewer items than the bank can supply for that subject
  — it just returns less well-matched ones once the good matches run out. The one true
  filter is ``subject``: if nothing matches the subject, we return ``[]`` (degradation,
  not an error — the caller decides what to tell the student).
* **exam_board is advisory here.** The bank is uniformly WAEC/WASSCE/JAMB-style secondary
  material; ``exam_board`` is accepted for API symmetry and reserved for future
  board-specific pools, but does not currently narrow selection.
"""

from __future__ import annotations

import json
from pathlib import Path

# The public shape of a returned item — the field set of contracts.models.GeneratedQuestion.
# We project every bank row onto exactly these keys so the bank's private "subject"/"topic"
# bookkeeping never leaks into the API payload.
_QUESTION_FIELDS: tuple[str, ...] = (
    "question_text",
    "options",
    "correct_answer",
    "worked_solution",
    "marking_scheme",
    "topic_tags",
    "difficulty",
)

_DEFAULT_BANK_PATH = Path(__file__).with_name("question_bank.json")

# path (resolved, as str) -> parsed item list. Loading is idempotent and cheap to cache;
# the bank is a static asset that does not change at runtime.
_CACHE: dict[str, list[dict]] = {}


def load_bank(path: str | Path | None = None) -> list[dict]:
    """Load and cache the question bank.

    Defaults to the sibling ``question_bank.json``. Returns the list under the file's
    ``"items"`` key. The returned list is the cached object — callers must treat it as
    read-only (``generate()`` never mutates it; it builds fresh projected dicts).
    """
    resolved = Path(path) if path is not None else _DEFAULT_BANK_PATH
    key = str(resolved.resolve())
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    with resolved.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    items = data.get("items", []) if isinstance(data, dict) else []
    _CACHE[key] = items
    return items


def _project(item: dict) -> dict:
    """Reduce a bank row to exactly the GeneratedQuestion field set.

    Missing optional fields default the way the pydantic model does (``options`` and
    ``marking_scheme`` -> None, ``topic_tags`` -> [], ``difficulty`` -> 3), so the result
    always validates even if a future row omits an optional key.
    """
    projected: dict = {}
    for field in _QUESTION_FIELDS:
        if field in item:
            projected[field] = item[field]
    projected.setdefault("options", None)
    projected.setdefault("marking_scheme", None)
    projected.setdefault("topic_tags", [])
    projected.setdefault("difficulty", 3)
    return projected


def _topic_matches(item: dict, needle: str) -> bool:
    """True when ``needle`` (already lowercased) is a substring of the item's topic or of
    any of its topic tags. Substring, not equality, so 'quadratic' finds
    'quadratic_equations' and 'algebra'-tagged items alike."""
    haystacks = [str(item.get("topic", ""))]
    haystacks.extend(str(tag) for tag in item.get("topic_tags", []) or [])
    return any(needle in h.lower() for h in haystacks)


def generate(
    subject: str,
    topic: str | None,
    difficulty: int,
    exam_board: str,
    count: int,
) -> list[dict]:
    """Select up to ``count`` bank items for the request, best matches first.

    Ranking key per item (all ascending, so smaller = preferred):

    1. topic mismatch  — 0 if the request has no topic or the item matches the topic, else 1.
    2. outside ±1 band — 0 if |item.difficulty − requested| ≤ 1, else 1.
    3. difficulty gap  — |item.difficulty − requested|, to order within a band.
    4. bank position   — the item's original index, a stable deterministic tie-break.

    The result is the top ``count`` of the subject's items under this order. Because it is
    a ranking rather than a hard filter, filters "relax" automatically: topic matches come
    first, then near-difficulty items, then the rest — but we never drop below what the
    subject can supply. Returns ``[]`` when no item matches ``subject`` at all.
    """
    bank = load_bank()

    subject_key = (subject or "").strip().lower()
    subject_items = [
        (idx, item)
        for idx, item in enumerate(bank)
        if str(item.get("subject", "")).lower() == subject_key
    ]
    if not subject_items:
        return []

    # Guard the inputs the same way the contract does (ge=1/le=20 on count, ge=1/le=5 on
    # difficulty) so a caller that bypasses pydantic still gets sane behaviour.
    want = max(0, min(int(count), len(subject_items)))
    if want == 0:
        return []
    target_difficulty = max(1, min(int(difficulty), 5))

    needle = topic.strip().lower() if topic and topic.strip() else None

    def sort_key(entry: tuple[int, dict]) -> tuple[int, int, int, int]:
        idx, item = entry
        topic_mismatch = 0 if (needle is None or _topic_matches(item, needle)) else 1
        try:
            item_difficulty = int(item.get("difficulty", 3))
        except (TypeError, ValueError):
            item_difficulty = 3
        gap = abs(item_difficulty - target_difficulty)
        outside_band = 0 if gap <= 1 else 1
        return (topic_mismatch, outside_band, gap, idx)

    ranked = sorted(subject_items, key=sort_key)
    return [_project(item) for _, item in ranked[:want]]


def topics(subject: str) -> list[str]:
    """Distinct topics available for ``subject``, sorted. Empty when the subject is unknown.

    Draws from each item's ``topic`` field and its ``topic_tags`` so callers can surface
    both the coarse topic and the finer tags a request's ``topic`` substring can hit.
    """
    subject_key = (subject or "").strip().lower()
    found: set[str] = set()
    for item in load_bank():
        if str(item.get("subject", "")).lower() != subject_key:
            continue
        topic_value = item.get("topic")
        if topic_value:
            found.add(str(topic_value))
        for tag in item.get("topic_tags", []) or []:
            found.add(str(tag))
    return sorted(found)
