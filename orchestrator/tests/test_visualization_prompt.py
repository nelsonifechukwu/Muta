"""Visual intent, prose pass, renderer selection, and constrained schemas."""

from __future__ import annotations

import json
import threading
from types import SimpleNamespace

from orchestrator.gateway.deps import load_prompt
from orchestrator.gateway.routes import _sampling_for_request
from orchestrator.gateway.visualizations import (
    _UNSUPPORTED_VISUAL,
    _normalize_generated_spec,
    _vector_addition_spec,
    append_visualization,
    generate_visualization,
    resolve_visualization_request,
    select_kind,
    select_library,
    turn_instruction,
    visualization_schema,
    wants_live_visual,
)


def test_primary_prompt_stays_small_and_voice_safe() -> None:
    load_prompt.cache_clear()
    for mode in ("socratic", "subgoal", "not-a-mode"):
        assert "## Live visual explanations" not in load_prompt(mode)


def test_visual_request_makes_the_primary_completion_prose_only() -> None:
    request = "Explain why y = x squared makes a U-shaped graph."
    assert wants_live_visual(request)
    instruction = turn_instruction(request, "Reply in English.")
    assert "Reply in English." in instruction
    assert "at least two complete" in instruction
    assert "Never refuse" in instruction
    assert "claim that you are text-only" in instruction
    assert "do not output JSON" in instruction
    assert "muta-viz fence" in instruction
    assert "```" not in instruction
    assert not wants_live_visual("Help me factor x squared minus four.")
    assert not wants_live_visual("Do not draw a graph; text only.")


def test_visual_intent_and_renderer_selection_cover_common_requests() -> None:
    for direct_request in (
        "Draw y = x squared.",
        "Sketch this curve.",
        "Show the coordinate axes.",
        "Make that interactive.",
        "Rotate it so I can see the other side.",
        "Tracez un graphique de cette fonction.",
        "Chora grafu hii.",
        "ارسم رسم بياني للدالة.",
    ):
        assert wants_live_visual(direct_request)

    expected = {
        "Build a Three.js 3D vector scene.": ("three", "scene3d"),
        "Explain vector addition with a diagram.": ("three", "scene3d"),
        "Animate this with GSAP.": ("gsap", "animation"),
        "Use Anime.js for this animation.": ("anime", "animation"),
        "Use Motion.js to move the dot.": ("motion", "animation"),
        "Make a D3 bar chart.": ("d3", "bar"),
        "Draw a force network.": ("d3", "force"),
        "Plot a scatter graph.": ("d3", "scatter"),
        "Plot this curve.": ("d3", "line"),
    }
    for prompt, (library, kind) in expected.items():
        assert select_library(prompt) == library
        assert select_kind(prompt, library) == kind
        schema = visualization_schema(library, kind, prompt)["schema"]
        assert schema["properties"]["library"]["enum"] == [library]
        assert schema["properties"]["kind"]["enum"] == [kind]
    assert _UNSUPPORTED_VISUAL.search("Draw a diagram of a triangle with angles 50, 60, 70.")
    assert _UNSUPPORTED_VISUAL.search("Make a pie graph showing 25 and 75 percent.")


def test_anaphoric_visual_follow_up_recovers_only_the_previous_learner_topic() -> None:
    class Store:
        def get_messages(self, conversation_id, limit=None):
            assert conversation_id == "vector-chat" and limit == 8
            return [
                {"role": "user", "content": "Explain vector addition with a diagram."},
                {"role": "assistant", "content": "Vectors add head to tail."},
                {"role": "user", "content": "No, animate it."},
                {"role": "assistant", "content": "The application will add the visual."},
            ]

    engine = SimpleNamespace(store=Store())
    resolved = resolve_visualization_request(engine, "No, animate it.", "vector-chat")
    assert resolved.startswith("Explain vector addition with a diagram.")
    assert resolved.endswith("FOLLOW-UP VISUAL REQUEST: No, animate it.")
    assert resolve_visualization_request(engine, "Plot y = x².", "vector-chat") == "Plot y = x²."


def test_vector_addition_specs_are_exact_and_library_driven() -> None:
    request = "Explain vector addition for A=(2, 3) and B=(-1, 4) with a diagram."
    scene = _vector_addition_spec(request, request)
    assert scene["library"] == "three" and scene["kind"] == "scene3d"
    assert scene["objects"][0]["from"] == [0, 0, 0]
    assert scene["objects"][0]["to"] == [2, 3, 0]
    assert scene["objects"][1]["from"] == [2, 3, 0]
    assert scene["objects"][1]["to"] == [1, 7, 0]
    assert scene["objects"][2]["to"] == [1, 7, 0]
    assert "A + B = (1, 7)" in scene["aria_label"]

    for current, library in (
        ("Animate it.", "anime"),
        ("Use GSAP to animate it.", "gsap"),
        ("Use Motion.js to animate it.", "motion"),
    ):
        animation = _vector_addition_spec(request, current)
        assert animation["library"] == library and animation["kind"] == "animation"
        assert {track["target"] for track in animation["tracks"]} == {
            "vector_b",
            "resultant",
        }
        moving_b = animation["tracks"][0]
        assert (moving_b["to"]["x"], moving_b["to"]["y"]) != (
            moving_b["from"]["x"],
            moving_b["from"]["y"],
        )
        assert "A + B = (1, 7)" in animation["aria_label"]


def test_vector_addition_without_operands_uses_a_correct_teaching_example() -> None:
    spec = _vector_addition_spec(
        "Can you explain vector addition with a diagram example?",
        "Can you explain vector addition with a diagram example?",
    )
    assert spec["objects"][0]["to"] == [2, 1, 0]
    assert spec["objects"][1]["from"] == [2, 1, 0]
    assert spec["objects"][1]["to"] == [3, 3, 0]
    assert spec["objects"][2]["to"] == [3, 3, 0]


def test_animation_schema_constrains_the_requested_action() -> None:
    cases = {
        "Use GSAP for a rectangle scaling from 1 to 2.": "scale",
        "Use Anime.js to rotate a rectangle 180 degrees.": "rotate",
        "Use Motion.js to move a dot vertically from y=280 to y=60.": "y",
    }
    for request, field in cases.items():
        library = select_library(request)
        schema = visualization_schema(library, "animation", request)["schema"]
        track = schema["properties"]["tracks"]["items"]
        assert track["properties"]["target"]["enum"] == ["subject"]
        assert set(track["properties"]["to"]["properties"]) == {field}
        assert track["properties"]["duration"]["enum"] == [2]


def test_line_schema_cannot_exhaust_the_visual_decode_budget_with_points() -> None:
    single = visualization_schema("d3", "line", "Plot y = x squared.")["schema"]
    compared = visualization_schema("d3", "line", "Compare both curves.")["schema"]
    single_series = single["properties"]["series"]
    compared_series = compared["properties"]["series"]

    assert single_series["maxItems"] == 1
    assert compared_series["maxItems"] == 2
    assert single_series["items"]["properties"]["points"]["maxItems"] == 24
    three = visualization_schema("three", "scene3d", "Draw a 3D scene.")["schema"]
    assert three["properties"]["objects"]["maxItems"] == 8


def test_visual_turn_reserves_completion_budget_instead_of_hidden_reasoning() -> None:
    class EcoPower:
        def adjust_sampling(self, params, **_kwargs):
            return {**params, "enable_thinking": True, "reasoning_budget_tokens": 256}

    sampling = _sampling_for_request(
        "subgoal",
        "auto",
        power=EcoPower(),
        power_enabled=True,
        visualizations=True,
    )
    assert sampling["enable_thinking"] is False
    assert "reasoning_budget_tokens" not in sampling


class _RecordingVisualClient:
    def __init__(self, payload: object, after_call=None) -> None:
        self.payload = payload
        self.after_call = after_call
        self.calls: list[tuple[list[dict], dict]] = []
        self.closed = False

    def stream_events(self, messages, **params):
        self.calls.append((messages, params))
        raw = json.dumps(self.payload)
        try:
            if self.after_call is not None:
                self.after_call()
            yield "content", raw[: max(1, len(raw) // 2)]
            yield "content", raw[max(1, len(raw) // 2) :]
        finally:
            self.closed = True


class _VisualEngine:
    def __init__(self, local: _RecordingVisualClient) -> None:
        self.cloud_calls = 0
        self.local = local
        self.client = SimpleNamespace(
            local=local,
            chat_with_timings=lambda *_args, **_kwargs: setattr(
                self, "cloud_calls", self.cloud_calls + 1
            ),
        )
        self.fit_calls: list[tuple[list[dict], dict, int]] = []

    def _fit_request(self, messages, params, *, protected_tail_messages):
        self.fit_calls.append((messages, params, protected_tail_messages))
        return messages, {**params, "max_tokens": min(params["max_tokens"], 320)}


def _bar_spec() -> dict:
    return {
        "version": 1,
        "library": "d3",
        "kind": "bar",
        "title": "Fruit count",
        "aria_label": "A bar chart comparing two fruit counts.",
        "height": 300,
        "data": [{"label": "apples", "value": 3}, {"label": "bananas", "value": 7}],
    }


def test_constrained_pass_uses_local_client_fitter_and_durable_protocol() -> None:
    local = _RecordingVisualClient(_bar_spec())
    engine = _VisualEngine(local)

    generations = []
    spec = generate_visualization(
        engine,
        "Draw a D3 bar chart with apples 3 and bananas 7.",
        "Bananas have four more items than apples.",
        on_generation=generations.append,
    )

    assert spec == _bar_spec()
    assert engine.cloud_calls == 0
    assert len(engine.fit_calls) == len(local.calls) == 1
    assert local.closed is True
    assert len(generations) == 1 and generations[0].completion_tokens == 2
    assert engine.fit_calls[0][2] == 1
    messages, params = local.calls[0]
    assert "apples 3 and bananas 7" in messages[-1]["content"]
    assert params["max_tokens"] == 320
    schema = params["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["kind"]["enum"] == ["bar"]
    reply = append_visualization("Complete prose.", spec)
    assert reply.startswith("Complete prose.\n\n```muta-viz\n")
    assert reply.endswith("\n```")


def test_canonical_vector_addition_does_not_depend_on_a_second_model_decode() -> None:
    local = _RecordingVisualClient({"this": "must not be used"})
    engine = _VisualEngine(local)

    spec = generate_visualization(
        engine,
        "Can you explain vector addition with a diagram example?",
        "Vector addition places the second vector head to tail.",
    )

    assert spec is not None and spec["library"] == "three"
    assert spec["objects"][2]["to"] == [3, 3, 0]
    assert local.calls == []
    assert engine.fit_calls == []


def test_constrained_pass_degrades_on_invalid_data_and_honours_cancellation() -> None:
    invalid = _RecordingVisualClient({"version": 1, "library": "d3", "kind": "bar"})
    assert (
        generate_visualization(
            _VisualEngine(invalid), "Draw a D3 bar chart.", "A complete explanation."
        )
        is None
    )

    cancelled = threading.Event()
    cancelled.set()
    never_called = _RecordingVisualClient(_bar_spec())
    assert (
        generate_visualization(
            _VisualEngine(never_called),
            "Draw a D3 bar chart.",
            "A complete explanation.",
            cancel_event=cancelled,
        )
        is None
    )
    assert not never_called.calls

    cancelled.clear()
    cancelled_after_decode = _RecordingVisualClient(_bar_spec(), after_call=cancelled.set)
    assert (
        generate_visualization(
            _VisualEngine(cancelled_after_decode),
            "Draw a D3 bar chart.",
            "A complete explanation.",
            cancel_event=cancelled,
        )
        is None
    )
    assert len(cancelled_after_decode.calls) == 1
    assert cancelled_after_decode.closed is True


def test_exact_quadratic_normalizer_does_not_rewrite_shifted_or_scaled_equations() -> None:
    original = {
        "kind": "line",
        "series": [{"label": "model data", "points": [[-1, 4], [0, 3], [1, 4]]}],
    }
    for request in ("Plot y = x² + 3.", "Plot y = x squared - 4.", "Plot y = 2*x^2."):
        candidate = json.loads(json.dumps(original))
        assert _normalize_generated_spec(candidate, "d3", request) == original


def test_generated_animation_repeats_are_finite_and_request_bounded() -> None:
    for request, expected in (
        ("Animate this once.", 0),
        ("Loop this animation.", 1),
        ("Repeat this 12 times.", 3),
    ):
        schema = visualization_schema("anime", "animation", request)["schema"]
        repeat = schema["properties"]["tracks"]["items"]["properties"]["repeat"]
        assert repeat["enum"] == [expected]
