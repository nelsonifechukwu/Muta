"""Sampling profile tests (TDD §6.5)."""

from __future__ import annotations

import pytest

from orchestrator.gateway.sampling import (
    DEFAULT_MAX_TOKENS,
    PROFILES,
    REPRODUCIBLE_SEED,
    for_mode,
    verifier_retry,
)


@pytest.mark.parametrize("name", ["marking", "tool-call"])
def test_scored_paths_are_greedy_and_seeded(name):
    """Anything scored or verified must be replayable: a marking result a teacher disputes,
    or a tool call we have to debug, is worthless if it cannot be reproduced."""
    p = PROFILES[name]
    assert p.temperature == 0.0 and p.top_k == 1 and p.top_p == 1.0
    assert p.seed == REPRODUCIBLE_SEED
    assert p.is_greedy and p.is_reproducible


@pytest.mark.parametrize("name", ["tutor-dialogue", "worked-solution", "hint"])
def test_conversational_paths_sample(name):
    p = PROFILES[name]
    assert p.temperature > 0 and p.seed == -1
    assert not p.is_reproducible


def test_the_tdd_table_values():
    d = PROFILES["tutor-dialogue"]
    assert (d.temperature, d.top_p, d.top_k, d.min_p, d.repeat_penalty) == (0.7, 0.95, 40, 0.05, 1.05)
    s = PROFILES["worked-solution"]
    assert (s.temperature, s.top_p) == (0.3, 0.90)
    h = PROFILES["hint"]
    assert (h.temperature, h.repeat_penalty) == (0.8, 1.1)


def test_params_are_ready_for_the_inference_client():
    params = PROFILES["tutor-dialogue"].params()
    assert params["temperature"] == 0.7 and params["seed"] == -1
    assert params["max_tokens"] == DEFAULT_MAX_TOKENS  # §8.2 fairness cap


def test_structured_profiles_refuse_to_run_without_a_schema():
    """Without the grammar the model may answer in prose, the tool loop drops the turn, and
    the failure looks like the model 'ignoring' the tool — a bad hour to debug live."""
    with pytest.raises(ValueError, match="pass json_schema"):
        PROFILES["marking"].params()


def test_schema_is_passed_through_as_response_format():
    schema = {"name": "marks", "schema": {"type": "object"}}
    params = PROFILES["marking"].params(json_schema=schema)
    assert params["response_format"] == {"type": "json_schema", "json_schema": schema}


def test_max_tokens_override_for_a_long_worked_solution():
    assert PROFILES["worked-solution"].params(max_tokens=2000)["max_tokens"] == 2000


def test_hint_mode_is_short_by_construction():
    assert PROFILES["hint"].max_tokens < DEFAULT_MAX_TOKENS


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("dialogue", "tutor-dialogue"),
        ("socratic", "tutor-dialogue"),  # the existing contract vocabulary still routes
        ("solution", "worked-solution"),
        ("subgoal", "worked-solution"),
        ("marking", "marking"),
        ("hint", "hint"),
        ("something-new", "tutor-dialogue"),  # unknown modes degrade to dialogue, never crash
    ],
)
def test_mode_routing(mode, expected):
    assert for_mode(mode).name == expected


def test_verifier_retry_is_greedy():
    assert verifier_retry().is_reproducible
