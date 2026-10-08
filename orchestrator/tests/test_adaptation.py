from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.gateway.integrity import StudentWorkFinding
from orchestrator.pedagogy.adaptation import (
    detect_confusion,
    detect_preferences,
    plan_turn_adaptation,
)
from orchestrator.pedagogy.twin import LearningTwin

FIXTURES = Path(__file__).parent / "fixtures" / "semifinal_judge_prompts.json"
JUDGE_PROMPTS = json.loads(FIXTURES.read_text(encoding="utf-8"))


def test_exact_series_judge_prompt_honours_preference_and_plans_distinct_explanations():
    twin = LearningTwin("judge")

    plan = plan_turn_adaptation(
        twin,
        JUDGE_PROMPTS["series_adaptation"],
        subject="physics",
        mode="socratic",
    )

    assert twin.preferences["style"] == "examples"
    assert twin.misconception_counts["series_current_used_up"] == 1
    assert plan.strategy == "single-loop analogy"
    assert "Begin with a concrete everyday example" in plan.directive
    assert "change again to charge-counter thought experiment" in plan.directive
    assert "Ask one short diagnostic question" in plan.directive


def test_repeated_misconception_switches_strategy_instead_of_repeating():
    twin = LearningTwin("repeat")
    first = plan_turn_adaptation(
        twin,
        "I think the first bulb uses up current, so the second bulb gets less current.",
        subject="physics",
        mode="socratic",
    )
    second = plan_turn_adaptation(
        twin,
        "I still think the first bulb took some current before it reached the second bulb.",
        subject="physics",
        mode="socratic",
    )

    assert first.strategy == "single-loop analogy"
    assert second.strategy == "charge-counter thought experiment"
    assert second.previous_strategy == first.strategy
    assert second.switched_strategy
    assert second.observation_count == 2
    assert "Do not reuse single-loop analogy" in second.directive


@pytest.mark.parametrize(
    "message,language",
    [
        ("I still don't understand this step", "en"),
        ("Bado sijaelewa hatua hii", "sw"),
        ("Ko ye mi rara", "yo"),
        ("Har yanzu ban gane ba", "ha"),
        ("Aghọtaghị m nzọụkwụ a", "ig"),
        ("Je ne comprends pas cette étape", "fr"),
    ],
)
def test_confusion_detection_is_multilingual(message: str, language: str):
    assert language in detect_confusion(message)


@pytest.mark.parametrize(
    "message,expected",
    [
        ("I learn better from everyday examples than formulas.", {"style": "examples"}),
        ("Please show me a diagram.", {"style": "visual"}),
        ("Can we do this step-by-step?", {"pace": "step_by_step"}),
        ("Explain why the steps work, not a rule.", {"reasoning": "explain_why"}),
        ("Keep it brief.", {"length": "concise"}),
    ],
)
def test_only_explicit_preference_statements_become_facts(message: str, expected: dict[str, str]):
    assert detect_preferences(message) == expected


def test_checked_math_error_becomes_stable_twin_tag_and_mode_specific_instruction():
    twin = LearningTwin("math")
    finding = StudentWorkFinding(
        checked=True,
        equivalent=False,
        error_class="distribution_error",
    )

    plan = plan_turn_adaptation(
        twin,
        "I don't understand why this is wrong.",
        subject="math",
        mode="hint",
        finding=finding,
    )

    assert plan.friction_tags == ("distribution_error", "confusion")
    assert twin.misconception_counts["distribution_error"] == 1
    assert "Give one next-step hint" in plan.directive
    assert "withhold the final answer" in plan.directive


def test_neutral_turn_does_not_infer_personality_or_ability():
    twin = LearningTwin("private")
    plan = plan_turn_adaptation(
        twin,
        "What is photosynthesis?",
        subject="biology",
        mode="socratic",
    )

    assert twin.preferences == {}
    assert twin.misconception_counts == {}
    assert plan.friction_tags == ()
    assert "ability" not in plan.directive.casefold()
    assert "personality" not in plan.directive.casefold()
