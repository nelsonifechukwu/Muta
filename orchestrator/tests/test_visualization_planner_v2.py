"""Adversarial tests for the bounded model-to-V2 semantic planner."""

from __future__ import annotations

import json
import threading
from types import SimpleNamespace

import pytest

from orchestrator.gateway.visualization_planner_v2 import (
    MAX_PLANNER_ATTEMPTS,
    _explicit_entity_groups,
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
        "budget": {"max_points": 512, "max_triangles": 4096, "max_fps": 20},
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
    assert schema["schema"]["properties"]["budget"]["properties"]["max_triangles"]["enum"] == [4096]
    binding = schema["schema"]["properties"]["controls"]["items"]["properties"]["binding"]
    assert binding["additionalProperties"] is False
    assert (
        "select"
        not in schema["schema"]["properties"]["controls"]["items"]["properties"]["type"]["enum"]
    )


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


def test_planner_forwards_cancellation_to_the_blocking_local_stream() -> None:
    engine = _PlannerEngine([_food_web_spec()])
    cancel = threading.Event()

    spec = plan_visualization_v2(
        engine,
        "Draw a mangrove food web from algae to crab to heron.",
        "Energy follows the arrows.",
        cancel_event=cancel,
    )

    assert spec == _food_web_spec()
    assert engine.local.calls[0][1]["_muta_cancel_event"] is cancel


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


@pytest.mark.parametrize(
    "resource",
    [
        "https://example.invalid/payload.js",
        "//example.invalid/payload.js",
        "data:text/html,payload",
        "file:///tmp/payload",
        "url(external.png)",
        "@import external.css",
    ],
)
def test_model_authored_network_and_resource_tokens_are_rejected(resource: str) -> None:
    candidate = _food_web_spec()
    candidate["text_fallback"] = resource

    errors = _plan_errors(
        candidate,
        "Draw a mangrove food web from algae to crab to heron.",
    )

    assert "authored_source_forbidden" in {error["code"] for error in errors}


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


def test_semantic_oracle_rejects_catch_all_labels_and_undirected_relationships() -> None:
    catch_all = _food_web_spec()
    catch_all["scene"]["layers"] = [
        {
            "type": "rect",
            "x": 100,
            "y": 100,
            "width": 120,
            "height": 60,
            "label": "mangrove food",
            "color": "green",
        }
    ]
    errors = _plan_errors(catch_all, "Draw a mangrove food web showing algae, crab, and heron.")
    assert {error["code"] for error in errors} == {
        "topic_not_grounded",
        "relationship_not_grounded",
    }

    undirected = _food_web_spec()
    for layer in undirected["scene"]["layers"]:
        if layer["type"] == "link":
            layer["arrow"] = False
    errors = _plan_errors(
        undirected,
        "Draw a mangrove food web showing energy from algae to crab to heron.",
    )
    assert {error["code"] for error in errors} == {"relationship_not_grounded"}


def test_semantic_oracle_requires_distinct_connected_entity_nodes() -> None:
    catch_all = _food_web_spec()
    for layer in catch_all["scene"]["layers"]:
        if layer["type"] == "node":
            layer["label"] = "Algae crab heron"
    errors = _plan_errors(
        catch_all,
        "Draw a mangrove food web showing algae, crab, and heron.",
    )
    assert {error["code"] for error in errors} == {
        "topic_not_grounded",
        "relationship_not_grounded",
    }

    isolated = _food_web_spec()
    isolated["scene"]["layers"] = [
        layer
        for layer in isolated["scene"]["layers"]
        if not (layer["type"] == "link" and layer["from"] == "crab")
    ]
    errors = _plan_errors(
        isolated,
        "Draw a mangrove food web showing algae, crab, and heron.",
    )
    assert {error["code"] for error in errors} == {"relationship_not_grounded"}


def test_semantic_oracle_requires_every_term_of_each_multiword_entity() -> None:
    partial = _food_web_spec()
    labels = {
        "algae": "Green producer",
        "crab": "Crab consumer",
        "heron": "Great predator",
    }
    for layer in partial["scene"]["layers"]:
        if layer["type"] == "node":
            layer["label"] = labels[layer["id"]]
    request = "Draw a food web showing green algae, blue crab, and great blue heron."

    assert {error["code"] for error in _plan_errors(partial, request)} == {
        "topic_not_grounded",
        "relationship_not_grounded",
    }

    complete = _food_web_spec()
    labels = {
        "algae": "Green algae producer",
        "crab": "Blue crab consumer",
        "heron": "Great blue heron predator",
    }
    for layer in complete["scene"]["layers"]:
        if layer["type"] == "node":
            layer["label"] = labels[layer["id"]]
    assert _plan_errors(complete, request) == []


@pytest.mark.parametrize(
    "introducer",
    ("with", "including", "containing", "composed of"),
)
def test_semantic_oracle_recognizes_common_entity_list_introducers(introducer: str) -> None:
    missing_fish = _food_web_spec()
    request = f"Draw a food web {introducer} algae, crab, fish, and heron."

    assert {error["code"] for error in _plan_errors(missing_fish, request)} == {
        "topic_not_grounded",
        "relationship_not_grounded",
    }
    assert (
        _plan_errors(
            _food_web_spec(),
            f"Draw a food web {introducer} algae, crab, and heron.",
        )
        == []
    )


def test_semantic_oracle_preserves_short_scientific_entities_and_slash_notation() -> None:
    pathway = _food_web_spec()
    for layer, label in zip(
        (layer for layer in pathway["scene"]["layers"] if layer["type"] == "node"),
        ("DNA", "RNA", "ATP"),
        strict=True,
    ):
        layer["label"] = label
    assert _plan_errors(pathway, "Draw a pathway showing DNA, RNA, and ATP.") == []

    generic = _food_web_spec()
    for layer in generic["scene"]["layers"]:
        if layer["type"] == "node":
            layer["label"] = "Pathway"
    assert {
        error["code"]
        for error in _plan_errors(generic, "Draw a pathway showing DNA, RNA, and ATP.")
    } == {"topic_not_grounded"}

    architecture = _food_web_spec()
    for layer, label in zip(
        (layer for layer in architecture["scene"]["layers"] if layer["type"] == "node"),
        ("CPU", "ALU", "RAM"),
        strict=True,
    ):
        layer["label"] = label
    architecture["scene"]["layers"].extend(
        [
            {
                "type": "node",
                "id": "io",
                "x": 650,
                "y": 100,
                "width": 100,
                "height": 50,
                "label": "I/O",
                "color": "purple",
            },
            {"type": "link", "from": "heron", "to": "io", "arrow": True, "label": "data"},
        ]
    )
    assert (
        _plan_errors(
            architecture,
            "Draw a computer architecture containing CPU, ALU, RAM, and I/O.",
        )
        == []
    )

    short_pair = _food_web_spec()
    for layer, label in zip(
        (layer for layer in short_pair["scene"]["layers"] if layer["type"] == "node"),
        ("pH", "I/O", "Context"),
        strict=True,
    ):
        layer["label"] = label
    assert _plan_errors(short_pair, "Draw a network showing pH and I/O.") == []


def test_semantic_oracle_splits_connecting_with_and_directional_via_phrases() -> None:
    assert (
        _plan_errors(
            _food_web_spec(),
            "Draw a food web connecting algae with crab as well as heron.",
        )
        == []
    )

    no_links = _food_web_spec()
    no_links["scene"]["layers"] = [
        layer for layer in no_links["scene"]["layers"] if layer["type"] != "link"
    ]
    assert {
        error["code"] for error in _plan_errors(no_links, "Draw a diagram connecting algae and crab.")
    } == {"relationship_not_grounded"}


def test_with_presentation_modifiers_are_not_invented_as_entity_nodes() -> None:
    for request in (
        "Draw a diagram with clear labels and measurements.",
        "Draw a diagram with high contrast and dark theme.",
    ):
        assert _explicit_entity_groups(request) == []

    semantic = _food_web_spec()
    semantic["scene"]["layers"][0]["label"] = "Food producer"
    assert _plan_errors(semantic, "Draw a food web with clear labels and measurements.") == []
    assert (
        _plan_errors(
            _food_web_spec(),
            "Draw a food web showing energy from algae via crab to heron.",
        )
        == []
    )


def test_semantic_oracle_requires_requested_directional_paths() -> None:
    reversed_web = _food_web_spec()
    for layer in reversed_web["scene"]["layers"]:
        if layer["type"] == "link":
            layer["from"], layer["to"] = layer["to"], layer["from"]

    errors = _plan_errors(
        reversed_web,
        "Draw a mangrove food web showing energy from algae to crab to heron.",
    )

    assert {error["code"] for error in errors} == {"relationship_not_grounded"}
    assert (
        _plan_errors(
            _food_web_spec(),
            "Draw a mangrove food web showing energy from algae to crab to heron.",
        )
        == []
    )


def test_semantic_oracle_preserves_repeated_entities_in_directional_cycles() -> None:
    request = "Draw a food cycle showing energy flow from algae to crab to algae."
    incomplete = _food_web_spec()
    incomplete["scene"]["layers"] = [
        layer
        for layer in incomplete["scene"]["layers"]
        if not (layer["type"] == "link" and layer["from"] == "crab")
    ]
    assert {error["code"] for error in _plan_errors(incomplete, request)} == {
        "relationship_not_grounded"
    }

    complete = _food_web_spec()
    for layer in complete["scene"]["layers"]:
        if layer["type"] == "link" and layer["from"] == "crab":
            layer["to"] = "algae"
    assert _plan_errors(complete, request) == []

    self_cycle_request = "Draw a food cycle showing energy from algae to algae. Include crab."
    assert {error["code"] for error in _plan_errors(_food_web_spec(), self_cycle_request)} == {
        "relationship_not_grounded"
    }
    assert _plan_errors(complete, self_cycle_request) == []


def test_direction_parser_distinguishes_viewpoint_prose_tails_and_toward_steps() -> None:
    for perspective in ("viewed from above", "view from above", "from above"):
        assert (
            _plan_errors(
                _food_web_spec(),
                f"Draw a mangrove food web {perspective} and drawn to scale showing algae, crab, "
                "and heron.",
            )
            == []
        )

    interactive = _food_web_spec()
    interactive["controls"] = [
        {
            "id": "heron_height",
            "label": "Heron height",
            "type": "range",
            "value": 0,
            "min": -40,
            "max": 40,
            "step": 10,
            "binding": {"target_label": "Heron", "effect": "translate_y"},
        }
    ]
    assert (
        _plan_errors(
            interactive,
            "Draw a food web showing energy from algae to crab to heron with labels and an "
            "adjustable heron height.",
        )
        == []
    )
    assert (
        _plan_errors(
            _food_web_spec(),
            "Draw a food web showing energy from algae toward crab and then heron.",
        )
        == []
    )


def test_planner_rejects_family_specific_controls_without_inert_bindings() -> None:
    candidate = _food_web_spec()
    candidate["controls"] = [
        {
            "id": "mode",
            "label": "Mode",
            "type": "select",
            "value": "one",
            "options": ["one", "two"],
        }
    ]
    errors = _plan_errors(
        candidate,
        "Draw an interactive mangrove food web showing algae, crab, and heron.",
    )
    assert {error["code"] for error in errors} == {
        "control_unsupported",
        "interaction_missing",
    }


def test_parameter_controls_require_a_valid_semantic_geometry_binding() -> None:
    interactive = _food_web_spec()
    interactive["controls"] = [
        {
            "id": "crab_height",
            "label": "Crab height",
            "type": "range",
            "value": 0,
            "min": -40,
            "max": 40,
            "step": 10,
            "binding": {"target_label": "Crab", "effect": "translate_y"},
        }
    ]
    request = (
        "Draw an interactive mangrove food web from algae to crab to heron and let me adjust "
        "the crab height."
    )

    assert _plan_errors(interactive, request) == []

    del interactive["controls"][0]["binding"]
    errors = _plan_errors(interactive, request)
    assert {error["code"] for error in errors} == {"control_unbound"}


def test_animation_transport_ids_cannot_masquerade_as_parameters_or_static_controls() -> None:
    numeric_play = _food_web_spec()
    numeric_play["controls"] = [
        {
            "id": "play",
            "label": "Crab height",
            "type": "range",
            "value": 0,
            "min": -40,
            "max": 40,
            "step": 10,
            "binding": {"target_label": "Crab", "effect": "translate_y"},
        }
    ]
    errors = _plan_errors(
        numeric_play,
        "Draw an interactive mangrove food web showing algae, crab, and heron.",
    )
    assert {error["code"] for error in errors} == {"schema_invalid"}

    stray_play = _food_web_spec()
    stray_play["controls"] = [
        {"id": "play", "label": "Play", "type": "button", "value": False}
    ]
    errors = _plan_errors(
        stray_play,
        "Draw a mangrove food web showing algae, crab, and heron.",
    )
    assert {error["code"] for error in errors} == {"schema_invalid"}


def test_animation_requires_and_accepts_one_complete_transport_set() -> None:
    animated = _food_web_spec()
    animated["scene"]["animation"] = {"mode": "guided_reveal", "duration": 6}
    animated["controls"] = [
        {"id": "play", "label": "Play", "type": "button", "value": False}
    ]
    errors = _plan_errors(
        animated,
        "Animate a mangrove food web showing algae, crab, and heron.",
    )
    assert {error["code"] for error in errors} == {"schema_invalid"}

    animated["controls"] = [
        {"id": control_id, "label": control_id.title(), "type": "button", "value": False}
        for control_id in ("play", "pause", "restart")
    ]
    assert (
        _plan_errors(
            animated,
            "Animate a mangrove food web showing algae, crab, and heron.",
        )
        == []
    )
