"""Adversarial tests for the bounded model-to-V2 semantic planner."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from orchestrator.gateway.visualization_planner_v2 import (
    MAX_PLANNER_ATTEMPTS,
    _plan_errors,
    plan_visualization_v2,
    planner_schema_v2,
    should_use_semantic_planner,
)
from orchestrator.gateway.visualizations import generate_visualization


def _food_web_spec() -> dict:
    return {
        "version": 2,
        "library": "d3",
        "renderer": "svg",
        "kind": "scene2d",
        "family": "trophic_network",
        "title": "Mangrove food web",
        "aria_label": "A mangrove food web with energy arrows from algae to crab to heron.",
        "text_fallback": (
            "Algae supplies energy to the crab, and the crab supplies energy to the heron."
        ),
        "height": 420,
        "controls": [],
        "budget": {"max_points": 512, "max_triangles": 1, "max_fps": 20},
        "scene": {
            "coordinate_system": "screen",
            "layers": [
                {
                    "type": "node",
                    "id": "algae",
                    "x": 100,
                    "y": 260,
                    "width": 100,
                    "height": 50,
                    "label": "Algae",
                    "color": "green",
                },
                {
                    "type": "node",
                    "id": "crab",
                    "x": 300,
                    "y": 180,
                    "width": 100,
                    "height": 50,
                    "label": "Crab",
                    "color": "orange",
                },
                {
                    "type": "node",
                    "id": "heron",
                    "x": 500,
                    "y": 100,
                    "width": 100,
                    "height": 50,
                    "label": "Heron",
                    "color": "blue",
                },
                {
                    "type": "link",
                    "from": "algae",
                    "to": "crab",
                    "arrow": True,
                    "label": "energy",
                },
                {
                    "type": "link",
                    "from": "crab",
                    "to": "heron",
                    "arrow": True,
                    "label": "energy",
                },
            ],
        },
    }


class _SequenceClient:
    def __init__(self, payloads: list[object]) -> None:
        self.payloads = list(payloads)
        self.calls: list[tuple[list[dict], dict]] = []
        self.closed = 0

    def stream_events(self, messages, **params):
        self.calls.append((messages, params))
        payload = self.payloads[min(len(self.calls) - 1, len(self.payloads) - 1)]
        raw = json.dumps(payload)
        try:
            yield "content", raw[: max(1, len(raw) // 2)]
            yield "content", raw[max(1, len(raw) // 2) :]
        finally:
            self.closed += 1


class _PlannerEngine:
    def __init__(self, payloads: list[object]) -> None:
        self.local = _SequenceClient(payloads)
        self.client = SimpleNamespace(local=self.local)
        self.fit_calls: list[tuple[list[dict], dict, int]] = []

    def _fit_request(self, messages, params, *, protected_tail_messages):
        self.fit_calls.append((messages, params, protected_tail_messages))
        return messages, params


def test_planner_schema_is_closed_and_has_no_executable_source_fields() -> None:
    schema = planner_schema_v2()
    assert schema["strict"] is True
    assert schema["schema"]["additionalProperties"] is False
    assert schema["schema"]["properties"]["version"]["enum"] == [2]
    serialized = json.dumps(schema)
    for forbidden in ("javascript", "html", "shader", "url", "source", "function"):
        assert f'"{forbidden}"' not in serialized.lower()
    layers = schema["schema"]["properties"]["scene"]["properties"]["layers"]
    assert layers["maxItems"] == 24
    assert layers["items"]["additionalProperties"] is False


@pytest.mark.parametrize(
    "prompt, expected",
    [
        ("Sketch a trophic network linking marsh grass, snail, fish, and osprey.", True),
        ("Illustrate heat transfer through an insulated bottle.", True),
        ("Map how a request travels through an unfamiliar service architecture.", True),
        ("Make a bar chart for apples 3 and bananas 7.", False),
        ("Plot y = 2x + 1.", False),
    ],
)
def test_planner_routing_is_general_and_preserves_deterministic_fast_paths(
    prompt: str, expected: bool
) -> None:
    assert should_use_semantic_planner(prompt) is expected


def test_unseen_composition_is_validated_as_v2_without_source_execution() -> None:
    engine = _PlannerEngine([_food_web_spec()])
    request = "Draw a mangrove food web showing energy from algae to crab to heron."

    spec = plan_visualization_v2(engine, request, "Energy follows the arrows.")

    assert spec == _food_web_spec()
    assert len(engine.local.calls) == len(engine.fit_calls) == 1
    messages, params = engine.local.calls[0]
    assert request in messages[-1]["content"]
    assert "Never emit JavaScript" in messages[0]["content"]
    assert params["response_format"]["json_schema"]["name"].endswith("semantic_plan")
    assert params["max_tokens"] == 1200
    assert engine.local.closed == 1


def test_invalid_authored_source_gets_one_structured_repair_attempt() -> None:
    unsafe = _food_web_spec()
    unsafe["text_fallback"] = "<script>eval(payload)</script>"
    engine = _PlannerEngine([unsafe, _food_web_spec()])

    spec = plan_visualization_v2(
        engine,
        "Draw a mangrove food web showing algae, crab, and heron.",
        "Energy transfer should be explicit.",
    )

    assert spec == _food_web_spec()
    assert len(engine.local.calls) == MAX_PLANNER_ATTEMPTS
    repair_prompt = engine.local.calls[1][0][-1]["content"]
    assert '"code":"authored_source_forbidden"' in repair_prompt
    assert "<script>" not in repair_prompt


def test_unknown_primitive_is_rejected_and_repaired_without_execution() -> None:
    invalid = _food_web_spec()
    invalid["scene"]["layers"][0] = {
        "type": "script",
        "source": "globalThis.compromised = true",
    }
    engine = _PlannerEngine([invalid, _food_web_spec()])

    spec = plan_visualization_v2(
        engine,
        "Visualize a mangrove food web from algae to crab to heron.",
        "A food web is a directed relationship.",
    )

    assert spec == _food_web_spec()
    assert len(engine.local.calls) == 2
    assert '"code":"schema_invalid"' in engine.local.calls[1][0][-1]["content"]
    assert "globalThis" not in engine.local.calls[1][0][-1]["content"]


def test_two_invalid_plans_fall_back_and_never_enter_legacy_model_decode() -> None:
    invalid = {"version": 2, "html": "<canvas onload=eval(payload)>"}
    engine = _PlannerEngine([invalid, invalid, _food_web_spec()])

    spec = generate_visualization(
        engine,
        "Illustrate an unfamiliar geothermal heat-exchange loop with a diagram.",
        "Heat circulates between the ground loop and the building loop.",
    )

    assert spec is not None
    assert (spec["version"], spec["library"], spec["kind"]) == (1, "d3", "diagram")
    assert len(engine.local.calls) == MAX_PLANNER_ATTEMPTS
    assert all(
        call[1]["response_format"]["json_schema"]["name"].endswith("semantic_plan")
        for call in engine.local.calls
    )


def test_semantic_oracles_reject_ungrounded_or_interaction_free_plans() -> None:
    generic = _food_web_spec()
    generic["title"] = "Generic boxes"
    generic["aria_label"] = "Boxes connected by arrows."
    generic["text_fallback"] = "Three generic boxes connect in sequence."
    for layer in generic["scene"]["layers"]:
        if "label" in layer:
            layer["label"] = "item"

    errors = _plan_errors(
        generic,
        "Create an interactive geothermal exchanger diagram with an adjustable pump.",
    )

    assert {error["code"] for error in errors} == {
        "topic_not_grounded",
        "interaction_missing",
    }
