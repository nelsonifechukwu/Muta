"""Determinism overlay for the pinned DeepMind Mathematics generator.

The upstream code converts ``Entity`` objects to a set before shuffling them.
Those objects use identity hashes, so ASLR can change their pre-shuffle order
even when both Python's hash seed and the PRNG seeds are fixed.  It also draws
symbols from a set.  This narrowly scoped overlay preserves first occurrence
when deduplicating entities and sorts available symbols before random choice.
The subsequent seeded random choices remain statistically equivalent while
becoming reproducible across fresh processes.
"""

from __future__ import annotations

import random
from typing import Any

OVERLAY_VERSION = "muta-deepmind-determinism-v1"


def install(composition: Any) -> None:
    """Install the reviewed overlay into a pinned upstream module once."""

    if getattr(composition, "_MUTA_DETERMINISM_OVERLAY", None) == OVERLAY_VERSION:
        return
    if not hasattr(composition, "Context") or not hasattr(composition, "Entity"):
        raise RuntimeError("unexpected DeepMind composition module; refusing overlay")

    def stable_pop(context: Any) -> str:
        allowed = (
            composition._ALLOWED_SYMBOLS.difference(context._relation_symbols)
            .difference(context._self_symbols)
            .difference(context._child_symbols)
        )
        if not allowed:
            raise ValueError("Ran out of symbols")
        symbol = random.choice(sorted(allowed))
        context._self_symbols.add(symbol)
        return symbol

    def stable_expand_entities(context: Any, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        kwargs = kwargs.copy()
        entities: list[Any] = []

        def append_once(candidate: Any) -> None:
            if not any(candidate is existing for existing in entities):
                entities.append(candidate)

        for entity in context.child_entities:
            append_once(entity)
        for key, maybe_entity in kwargs.items():
            if isinstance(maybe_entity, composition.Entity):
                append_once(maybe_entity)
                kwargs[key] = maybe_entity.handle
        random.shuffle(entities)

        child_descriptions: list[str] = []
        for entity in entities:
            child_descriptions.append(entity.child_description)
            if not entity.expression_used:
                child_descriptions.append(entity.description)
        child_description = " ".join(value for value in child_descriptions if value)
        return child_description, kwargs

    composition.Context.pop = stable_pop
    composition.expand_entities = stable_expand_entities
    composition._MUTA_DETERMINISM_OVERLAY = OVERLAY_VERSION
