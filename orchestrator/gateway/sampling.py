"""Sampling profiles, attached per request by the gateway (TDD §6.5).

The rule underneath the table: **anything scored or verified is greedy with a fixed seed**.
Reproducibility is a product feature here, not a nicety — a marking result that cannot be
replayed cannot be disputed by a teacher or debugged by us, and a verifier retry that
samples differently every time turns one flaky answer into an unfalsifiable one.

Dialogue is the opposite case: a tutor that answers identically to the same question every
time reads as a lookup table, so tutor-dialogue keeps temperature and a random seed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: TDD §8.2 fairness: tutor answers are naturally short, and an unbounded generation is one
#: student holding a slot for a minute while five wait.
DEFAULT_MAX_TOKENS = 1200

#: Fixed seed for every reproducible path. Its value is arbitrary; its constancy is not.
REPRODUCIBLE_SEED = 4242


@dataclass(frozen=True)
class SamplingProfile:
    name: str
    temperature: float
    top_p: float
    top_k: int
    min_p: float
    repeat_penalty: float
    seed: int  # -1 = random per request
    requires_schema: bool = False  # emits JSON under a grammar (§7.4)
    max_tokens: int = DEFAULT_MAX_TOKENS

    @property
    def is_greedy(self) -> bool:
        return self.temperature == 0.0 and self.top_k == 1

    @property
    def is_reproducible(self) -> bool:
        return self.is_greedy and self.seed >= 0

    def params(self, *, json_schema: dict[str, Any] | None = None, max_tokens: int | None = None) -> dict[str, Any]:
        """Keyword arguments for `runtime.client.InferenceClient` (OpenAI-compatible)."""
        params: dict[str, Any] = {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "min_p": self.min_p,
            "repeat_penalty": self.repeat_penalty,
            "seed": self.seed,
            "max_tokens": max_tokens or self.max_tokens,
        }
        if json_schema is not None:
            params["response_format"] = {"type": "json_schema", "json_schema": json_schema}
        elif self.requires_schema:
            raise ValueError(
                f"sampling profile {self.name!r} emits structured output — pass json_schema, "
                "otherwise the model is free to answer in prose and the tool loop will "
                "silently drop the turn (§7.4)"
            )
        return params


PROFILES: dict[str, SamplingProfile] = {
    "tutor-dialogue": SamplingProfile("tutor-dialogue", 0.7, 0.95, 40, 0.05, 1.05, -1),
    "worked-solution": SamplingProfile("worked-solution", 0.3, 0.90, 40, 0.05, 1.05, -1),
    # Scored/verified paths: greedy, fixed seed, schema-constrained.
    "marking": SamplingProfile("marking", 0.0, 1.0, 1, 0.0, 1.0, REPRODUCIBLE_SEED, requires_schema=True),
    "tool-call": SamplingProfile("tool-call", 0.0, 1.0, 1, 0.0, 1.0, REPRODUCIBLE_SEED, requires_schema=True, max_tokens=512),
    # Hint mode runs on the draft model when D2-b is active (§7.6); short by construction.
    "hint": SamplingProfile("hint", 0.8, 0.95, 40, 0.05, 1.1, -1, max_tokens=256),
}

#: Public `mode` values (contract) → sampling profile. The contract's vocabulary is about
#: pedagogy; this table is about decoding. Keeping them separate means a sampling change is
#: not an API change.
MODE_TO_PROFILE: dict[str, str] = {
    "dialogue": "tutor-dialogue",
    "socratic": "tutor-dialogue",
    "subgoal": "worked-solution",
    "solution": "worked-solution",
    "marking": "marking",
    "hint": "hint",
}


#: Marking output shape (§S6). Attached automatically when the marking profile is used
#: without an explicit schema, because a greedy profile that raises on a missing grammar
#: would turn "mark this paper" into a 500 rather than a marked paper.
MARKING_SCHEMA: dict[str, Any] = {
    "name": "marking_result",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "marks_awarded": {"type": "number"},
                        "marks_available": {"type": "number"},
                        "error_tags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["description", "marks_awarded", "marks_available"],
                    "additionalProperties": False,
                },
            },
            "total_awarded": {"type": "number"},
            "total_available": {"type": "number"},
            "feedback": {"type": "string"},
        },
        "required": ["steps", "total_awarded", "total_available"],
        "additionalProperties": False,
    },
}


def for_mode(mode: str) -> SamplingProfile:
    return PROFILES[MODE_TO_PROFILE.get(mode, "tutor-dialogue")]


def params_for_mode(mode: str, *, json_schema: dict[str, Any] | None = None, **kw) -> dict[str, Any]:
    """Sampling parameters for a public mode, with the default grammar filled in where the
    profile demands one."""
    profile = for_mode(mode)
    if profile.requires_schema and json_schema is None:
        json_schema = MARKING_SCHEMA
    return profile.params(json_schema=json_schema, **kw)


def verifier_retry() -> SamplingProfile:
    """The one retry a failed verification gets (§7.5): greedy, so the second attempt is a
    different *input* (the failure is injected as a hint), never a different dice roll."""
    return PROFILES["marking"]
