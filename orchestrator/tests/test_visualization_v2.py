from __future__ import annotations

import json
import math
from itertools import pairwise
from pathlib import Path

import pytest

from orchestrator.gateway.visualization_v2 import (
    MAX_AST_NODES,
    VisualizationV2Error,
    compile_visualization_v2,
    evaluate_expression_v2,
    parse_expression_v2,
    parse_relationship,
    relationship_residual,
    resolve_intent,
    validate_v2_spec,
)

FIXTURES = Path(__file__).parent / "fixtures" / "visualization_v2"


def _cases() -> list[dict]:
    cases: list[dict] = []
    for path in sorted(FIXTURES.glob("*.json")):
        cases.extend(json.loads(path.read_text())["cases"])
    return cases


def test_acceptance_corpus_is_exactly_50_plus_100_plus_50() -> None:
    expected = {
        "stem_supplied.json": 50,
        "math_supplied.json": 100,
        "synthetic_held_out.json": 50,
    }
    cases: list[dict] = []
    for name, count in expected.items():
        data = json.loads((FIXTURES / name).read_text())
        assert data["count"] == len(data["cases"]) == count
        cases.extend(data["cases"])
    assert len(cases) == len({case["id"] for case in cases}) == 200
    repaired = next(case for case in cases if case["id"] == "math-046")
    assert "\n\n" not in repaired["raw_prompt"]  # blank source line normalized by JSON parser
    assert "without an operator" in repaired["normalization_decision"]
    assert "))-exp(" in repaired["normalized_equation"]


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["id"])
def test_every_acceptance_case_compiles_to_the_expected_validated_family(case: dict) -> None:
    raw = compile_visualization_v2(case["raw_prompt"])
    assert raw is not None
    assert raw["family"] == case["expected"]["family"]
    audited_repair = bool(
        case.get("normalized_prompt") and case.get("normalized_prompt") != case["raw_prompt"]
    )
    spec = compile_visualization_v2(case["normalized_prompt"]) if audited_repair else raw
    assert spec is not None
    validated = validate_v2_spec(spec)
    expected = case["expected"]
    assert validated["family"] == expected["family"]
    assert validated["renderer"] == expected["renderer"]
    assert validated["kind"] == expected["spec_kind"]
    actual_controls = [control["id"] for control in validated["controls"]]
    transport = {"play", "pause", "restart"}
    assert [
        control_id for control_id in actual_controls if control_id not in transport
    ] == expected["controls"]
    if transport & set(actual_controls):
        assert transport <= set(actual_controls)
    assert validated["text_fallback"].strip()


def test_every_raw_math_prompt_reaches_the_production_parser() -> None:
    cases = json.loads((FIXTURES / "math_supplied.json").read_text())["cases"]
    for case in cases:
        raw = compile_visualization_v2(case["raw_prompt"])
        assert raw is not None, case["id"]
        assert raw["family"] == case["expected"]["family"], case["id"]
    repaired = next(case for case in cases if case["id"] == "math-046")
    raw_layer = compile_visualization_v2(repaired["raw_prompt"])["scene"]["layers"][0]
    audited_layer = compile_visualization_v2(repaired["normalized_prompt"])["scene"]["layers"][0]
    assert raw_layer["relationship"] != audited_layer["relationship"]
    assert "without an operator" in repaired["normalization_decision"]


def test_supplied_prompt_strings_are_not_imported_by_production_routing() -> None:
    source = (Path(__file__).parents[1] / "gateway" / "visualization_v2.py").read_text().lower()
    for case in _cases():
        assert case["id"].lower() not in source
        prompt = " ".join(case["raw_prompt"].lower().split())
        assert not prompt or prompt not in " ".join(source.split())
    assert "fixtures/visualization_v2" not in source


def test_intent_negation_localized_terms_and_anaphoric_animation() -> None:
    assert not resolve_intent("Show the proof in text only").requested
    assert not resolve_intent("Do not draw a graph; explain it in prose").requested
    assert resolve_intent("Tracez un graphique de cette parabole").requested
    assert resolve_intent("Chora grafu ya projectile motion").requested
    prior = compile_visualization_v2("Plot z=sin(x)*cos(y)")
    assert prior is not None
    intent = resolve_intent("animate it", prior)
    assert intent.requested and intent.animate_previous
    animated = compile_visualization_v2("animate it", previous_spec=prior)
    assert animated is not None
    assert (
        animated["scene"]["layers"][0]["relationship"]
        == prior["scene"]["layers"][0]["relationship"]
    )
    assert animated["scene"]["layers"][0]["animation"] == {"mode": "phase", "duration": 8}

    pythagoras = compile_visualization_v2("Explain Pythagoras with a diagram")
    assert pythagoras is not None
    animated_pythagoras = compile_visualization_v2("animate", previous_spec=pythagoras)
    assert animated_pythagoras is not None
    assert animated_pythagoras["family"] == "pythagoras"
    assert animated_pythagoras["scene"]["layers"] == pythagoras["scene"]["layers"]
    assert animated_pythagoras["scene"]["animation"] == {
        "mode": "guided_reveal",
        "duration": 8,
    }
    assert [control["id"] for control in animated_pythagoras["controls"]] == [
        "a",
        "b",
        "play",
        "pause",
        "restart",
    ]


def test_animation_follow_up_preserves_parameter_view_and_existing_transport_controls() -> None:
    surface = compile_visualization_v2("Plot z=sin(x)*cos(y)")
    assert surface is not None
    prior_ids = [control["id"] for control in surface["controls"]]
    animated = compile_visualization_v2("animate it", previous_spec=surface)
    assert animated is not None
    assert [control["id"] for control in animated["controls"]] == [
        *prior_ids,
        "play",
        "pause",
        "restart",
    ]

    animated_again = compile_visualization_v2("animate it", previous_spec=animated)
    assert animated_again is not None
    ids = [control["id"] for control in animated_again["controls"]]
    assert ids == [*prior_ids, "play", "pause", "restart"]
    assert len(ids) == len(set(ids))

    bounded = json.loads(json.dumps(surface))
    bounded["controls"] = [
        {
            "id": f"parameter_{index}",
            "label": f"Parameter {index}",
            "type": "range",
            "value": 0,
            "min": 0,
            "max": 1,
            "step": 0.1,
        }
        for index in range(8)
    ]
    validate_v2_spec(bounded)
    bounded_animation = compile_visualization_v2("animate", previous_spec=bounded)
    assert bounded_animation is not None
    assert len(bounded_animation["controls"]) == 11
    assert [control["id"] for control in bounded_animation["controls"][-3:]] == [
        "play",
        "pause",
        "restart",
    ]


def test_damped_sine_follow_up_uses_phase_not_unrelated_orbit_animation() -> None:
    prior = compile_visualization_v2("Plot z=4*exp(-y^2/4)*sin(2*x)")
    assert prior is not None
    animated = compile_visualization_v2("animate it", previous_spec=prior)
    assert animated is not None
    assert animated["scene"]["layers"][0]["animation"] == {"mode": "phase", "duration": 8}


def test_initial_explicit_animation_requests_keep_parameters_and_add_transport() -> None:
    requested_ids = {
        "stem-032",
        "stem-041",
        "stem-043",
        "stem-044",
        "stem-045",
        "stem-047",
        "heldout-002",
        "heldout-010",
        "heldout-014",
        "heldout-024",
        "heldout-028",
        "heldout-031",
        "heldout-033",
        "heldout-045",
    }
    cases = {case["id"]: case for case in _cases()}
    assert requested_ids <= cases.keys()
    for case_id in requested_ids:
        spec = compile_visualization_v2(cases[case_id]["raw_prompt"])
        assert spec is not None, case_id
        controls = {control["id"] for control in spec["controls"]}
        assert {"play", "pause", "restart"} <= controls, case_id
        assert "animation" in spec["scene"] or any(
            "animation" in layer for layer in spec["scene"]["layers"]
        ), case_id


def test_animation_language_without_a_visual_request_does_not_false_trigger() -> None:
    assert compile_visualization_v2("Explain animation techniques in text only") is None
    assert compile_visualization_v2("Summarise the simulation result in prose only") is None


def test_damped_sine_acceptance_repairs_copy_transport_control_characters() -> None:
    prompt = (
        'I want a diagram of this equation, "z=4e^{-'
        + chr(12)
        + "rac{1}{4}y^{2}}sin left(2x"
        + chr(13)
        + 'ight)"'
    )
    spec = compile_visualization_v2(prompt)
    assert spec is not None
    assert spec["family"] == "explicit_surface"
    layer = spec["scene"]["layers"][0]
    expression = layer["relationship"]["right"]
    assert evaluate_expression_v2(expression, {"x": 0, "y": 2}) == pytest.approx(0)
    assert evaluate_expression_v2(expression, {"x": math.pi / 4, "y": 0}) == pytest.approx(4)
    assert evaluate_expression_v2(expression, {"x": -math.pi / 4, "y": 0}) == pytest.approx(-4)
    assert abs(evaluate_expression_v2(expression, {"x": math.pi / 4, "y": 2})) < 4


def test_general_parametric_surface_uses_typed_component_expressions() -> None:
    spec = compile_visualization_v2(
        "Plot the parametric surface x(u,v)=cos(u)*(2+v*cos(u/2)), "
        "y(u,v)=sin(u)*(2+v*cos(u/2)), z(u,v)=v*sin(u/2)"
    )
    assert spec is not None
    assert spec["family"] == "parametric_surface"
    layer = spec["scene"]["layers"][0]
    values = {
        axis: evaluate_expression_v2(layer[f"{axis}_expression"], {"u": 0, "v": 1})
        for axis in ("x", "y", "z")
    }
    assert values == pytest.approx({"x": 3, "y": 0, "z": 0})


@pytest.mark.parametrize(
    "learner_text",
    [
        "Show me the answer",
        "Show the derivation",
        "Build an argument for the claim",
        "Compare the two definitions in text",
        "Create a summary",
        "Generate an explanation",
        "What does the word model mean?",
        "Draw a conclusion",
        "Illustrate your reasoning in words",
        "Simulate a conversation",
        "I picture this as a proof",
        "The plot twist was surprising.",
        "The plot of the novel was confusing.",
        "I bought graph paper yesterday.",
        "This sketch comedy was funny.",
        "We need to chart a course for the project.",
        "Tell me the definition of a graph in prose.",
        "The diagram in the book is wrong; explain why in text.",
        "Model good behaviour for the class.",
        "Map the curriculum requirements.",
        "Graph theory is interesting.",
        "Map this concept to the syllabus.",
        "Chart the history of the word without a chart.",
        "Animate the discussion with examples.",
    ],
)
def test_ambiguous_verbs_do_not_create_false_positive_visuals(learner_text: str) -> None:
    assert not resolve_intent(learner_text).requested


@pytest.mark.parametrize(
    "learner_text",
    [
        "Draw a circle",
        "Draw a triangle",
        "Show a circle",
        "Illustrate a triangle",
        "Picture a circle",
    ],
)
def test_explicit_geometry_nouns_create_a_typed_shape_visual(learner_text: str) -> None:
    spec = compile_visualization_v2(learner_text)
    assert spec is not None
    assert spec["family"] == "basic_geometry"
    boundary = next(layer for layer in spec["scene"]["layers"] if layer["type"] == "polyline")
    assert boundary["points"][0] == pytest.approx(boundary["points"][-1])
    assert len(boundary["points"]) >= 4


@pytest.mark.parametrize(
    ("prompt", "family", "required_labels"),
    [
        ("Animate merge sort on [9,4,2].", "merge_sort", ("[9,4,2]", "sorted output [2,4,9]")),
        (
            "Visualize recursive factorial(7) with a recursion stack.",
            "recursion_stack",
            ("factorial(7)", "return 5040"),
        ),
        (
            "Visualize binary search for target 42 on [10,20,30,40,42,50].",
            "binary_search",
            ("[10,20,30,40,42,50]",),
        ),
        ("Build a min-heap from [12,4,9,1].", "heap", ("minimum root 1", "12")),
        (
            "Visualize y=(w*x+b)^3 and backpropagate its gradients.",
            "backprop_graph",
            ("y=u^3=125", "reverse gradient ∂y/∂u=75"),
        ),
    ],
)
def test_parameterized_compositions_use_requested_values(
    prompt: str, family: str, required_labels: tuple[str, ...]
) -> None:
    spec = compile_visualization_v2(prompt)
    assert spec is not None
    assert spec["family"] == family
    labels = {str(layer.get("label", "")) for layer in spec["scene"]["layers"]}
    assert set(required_labels) <= labels
    if family == "binary_search":
        target = next(control for control in spec["controls"] if control["id"] == "target")
        assert target["value"] == "42"
        assert "42" in target["options"]


def test_merge_sort_preserves_equal_key_identity_order() -> None:
    spec = compile_visualization_v2("Animate merge sort on [3,1,3,2].")
    assert spec is not None
    stability = next(
        layer["label"] for layer in spec["scene"]["layers"] if layer.get("id") == "stability"
    )
    assert "3@0" in stability
    assert "3@2" in stability
    assert stability.index("3@0") < stability.index("3@2")


def test_stateful_structure_specs_encode_the_requested_operations() -> None:
    bst = compile_visualization_v2(
        "Visualize a binary search tree. Let me insert values one at a time and animate placement."
    )
    assert bst is not None
    bst_nodes = {layer["id"]: layer for layer in bst["scene"]["layers"] if layer["type"] == "node"}
    assert {
        "root",
        "left",
        "right",
        "left_left",
        "left_right",
        "right_left",
        "right_right",
        "candidate",
    } <= bst_nodes.keys()
    assert any(layer.get("label") == "new-node placement" for layer in bst["scene"]["layers"])

    stack_queue = compile_visualization_v2(
        "Visualize a stack and a queue side by side; add and remove elements to show LIFO and FIFO."
    )
    assert stack_queue is not None
    sq_nodes = {
        layer["id"]: layer for layer in stack_queue["scene"]["layers"] if layer["type"] == "node"
    }
    assert [sq_nodes[f"stack_{index}"]["label"] for index in range(3)] == ["A", "B", "C"]
    assert [sq_nodes[f"queue_{index}"]["label"] for index in range(3)] == ["A", "B", "C"]
    assert sq_nodes["stack_2"]["y"] < sq_nodes["stack_0"]["y"]
    assert sq_nodes["queue_0"]["x"] < sq_nodes["queue_2"]["x"]

    network = compile_visualization_v2(
        "Visualize a neural network with two inputs, one hidden layer and one output; change a weight."
    )
    assert network is not None
    network_nodes = {layer["id"] for layer in network["scene"]["layers"] if layer["type"] == "node"}
    network_edges = {
        (layer["from"], layer["to"])
        for layer in network["scene"]["layers"]
        if layer["type"] == "link"
    }
    assert network_nodes == {"x1", "x2", "h1", "h2", "output"}
    assert network_edges == {
        ("x1", "h1"),
        ("x2", "h1"),
        ("x1", "h2"),
        ("x2", "h2"),
        ("h1", "output"),
        ("h2", "output"),
    }


def test_classifier_spec_is_derived_from_bounded_training_not_a_fake_curve() -> None:
    spec = compile_visualization_v2(
        "Train a tiny two-layer classifier on two clusters and show its decision boundary changing each epoch."
    )
    assert spec is not None
    layers = spec["scene"]["layers"]
    loss = next(
        layer["points"] for layer in layers if layer.get("label") == "training loss versus epoch"
    )
    heatmap = next(layer for layer in layers if layer["type"] == "heatmap")
    samples = next(
        layer["points"] for layer in layers if layer.get("label") == "labelled training samples"
    )
    assert len(loss) == 21
    assert all(next_point[1] <= point[1] for point, next_point in pairwise(loss))
    assert loss[-1][1] < loss[0][1]
    assert len(samples) == 36
    assert min(heatmap["values"]) < 0 < max(heatmap["values"])


def test_wave_optics_and_doppler_specs_encode_the_physical_relationships() -> None:
    slit = compile_visualization_v2(
        "Show a double-slit setup with path-difference rays and the intensity fringe pattern."
    )
    assert slit is not None
    controls = {control["id"]: float(control["value"]) for control in slit["controls"]}
    intensity = next(
        layer["points"] for layer in slit["scene"]["layers"] if layer.get("label") == "intensity"
    )
    half_gap = controls["slit_separation"] / 2
    expected = [
        (
            x,
            math.cos(
                math.pi
                * abs(math.hypot(4.8, x + half_gap) - math.hypot(4.8, x - half_gap))
                / controls["wavelength"]
            )
            ** 2,
        )
        for x, _y in intensity
    ]
    assert all(
        actual == pytest.approx(calculated)
        for actual, calculated in zip(intensity, expected, strict=True)
    )
    paths = {
        layer["label"]: layer["points"]
        for layer in slit["scene"]["layers"]
        if layer.get("label") in {"upper-slit path", "lower-slit path"}
    }
    screen = next(
        layer["points"] for layer in slit["scene"]["layers"] if layer.get("label") == "screen"
    )
    assert paths["upper-slit path"][1][1] - paths["lower-slit path"][1][1] == pytest.approx(
        controls["slit_separation"]
    )
    assert paths["upper-slit path"][-1][0] == pytest.approx(screen[0][0])
    assert paths["lower-slit path"][-1][0] == pytest.approx(screen[0][0])
    screen_y = paths["upper-slit path"][-1][1]
    exact_path_difference = abs(
        sum(math.dist(a, b) for a, b in pairwise(paths["upper-slit path"]))
        - sum(math.dist(a, b) for a, b in pairwise(paths["lower-slit path"]))
    )
    visible_intensity = min(intensity, key=lambda point: abs(point[0] - screen_y))[1]
    expected_visible = math.cos(math.pi * exact_path_difference / controls["wavelength"]) ** 2
    assert visible_intensity == pytest.approx(expected_visible, abs=0.03)


def test_general_vector_field_expressions_drive_probe_divergence_and_curl() -> None:
    field = compile_visualization_v2("Plot vector field F=(y,-x) with a movable probe")
    assert field is not None
    probe = next(layer for layer in field["scene"]["layers"] if layer["type"] == "probe_vector")
    x, y = 1.0, 2.0
    assert evaluate_expression_v2(probe["x_expression"], {"x": x, "y": y}) == pytest.approx(2)
    assert evaluate_expression_v2(probe["y_expression"], {"x": x, "y": y}) == pytest.approx(-1)
    epsilon = 1e-4
    dfxdx = (
        evaluate_expression_v2(probe["x_expression"], {"x": x + epsilon, "y": y})
        - evaluate_expression_v2(probe["x_expression"], {"x": x - epsilon, "y": y})
    ) / (2 * epsilon)
    dfxdy = (
        evaluate_expression_v2(probe["x_expression"], {"x": x, "y": y + epsilon})
        - evaluate_expression_v2(probe["x_expression"], {"x": x, "y": y - epsilon})
    ) / (2 * epsilon)
    dfydx = (
        evaluate_expression_v2(probe["y_expression"], {"x": x + epsilon, "y": y})
        - evaluate_expression_v2(probe["y_expression"], {"x": x - epsilon, "y": y})
    ) / (2 * epsilon)
    dfydy = (
        evaluate_expression_v2(probe["y_expression"], {"x": x, "y": y + epsilon})
        - evaluate_expression_v2(probe["y_expression"], {"x": x, "y": y - epsilon})
    ) / (2 * epsilon)
    assert dfxdx + dfydy == pytest.approx(0, abs=1e-8)
    assert dfydx - dfxdy == pytest.approx(-2, abs=1e-8)

    doppler = compile_visualization_v2(
        "Animate Doppler wavefronts from a moving source and show compressed fronts ahead."
    )
    assert doppler is not None
    fronts = [
        layer["points"] for layer in doppler["scene"]["layers"] if layer.get("label") == "wavefront"
    ]
    extents = sorted(
        ((max(x for x, _y in points), min(x for x, _y in points)) for points in fronts),
        reverse=True,
    )
    front_spacing = [extents[index][0] - extents[index + 1][0] for index in range(2)]
    rear_spacing = [extents[index + 1][1] - extents[index][1] for index in range(2)]
    assert sum(front_spacing) < sum(rear_spacing)


@pytest.mark.parametrize(
    "prompt",
    [
        "Graph the circle x^2+y^2=1",
        "Draw the circle x^2+y^2=1",
        "Show the circle x^2+y^2=1",
        "Illustrate the circle x^2+y^2=1",
        "Picture the circle x^2+y^2=1",
        "Show a graph of x^2+y^2=1",
        "Show me a graph of x^2+y^2=1",
        "Chart x^2+y^2=1",
        "Build a graph of x^2+y^2=1",
        "Create a graph of x^2+y^2=1",
        "Generate a graph of x^2+y^2=1",
        "Make a graph of x^2+y^2=1",
        "Model x^2+y^2=1",
        "Map x^2+y^2=1",
        "Track x^2+y^2=1",
        "Trace x^2+y^2=1",
        "Compare a graph of x^2+y^2=1",
    ],
)
def test_shape_wrapped_equation_reaches_the_generic_implicit_curve(prompt: str) -> None:
    spec = compile_visualization_v2(prompt)
    assert spec is not None
    assert spec["family"] == "implicit_curve"


def test_topic_alone_does_not_force_a_visual_without_visual_intent() -> None:
    assert not resolve_intent("Teach projectile motion").requested
    assert not resolve_intent("Explain molecular geometry in text").requested


def test_unicode_equation_with_trailing_presentation_words_reaches_surface_parser() -> None:
    spec = compile_visualization_v2("Plot z=4e^{−y²/4}sin(2x) as a 3D surface.")
    assert spec is not None
    layer = spec["scene"]["layers"][0]
    assert layer["type"] == "explicit_surface"
    assert evaluate_expression_v2(
        layer["relationship"]["right"], {"x": math.pi / 4, "y": 0}
    ) == pytest.approx(4)


def test_dense_2d_primitives_are_typed_bounded_and_semantically_inspectable() -> None:
    sampling = compile_visualization_v2(
        "Visualize sampling and aliasing with adjustable signal and sampling frequency."
    )
    field = compile_visualization_v2("Plot the saddle vector field F=(x,-y) with a movable probe.")
    spectrogram = compile_visualization_v2(
        "Generate a chirp spectrogram and let me change sweep rate."
    )
    assert sampling and field and spectrogram
    samples = next(layer for layer in sampling["scene"]["layers"] if layer["type"] == "particles")
    vectors = next(layer for layer in field["scene"]["layers"] if layer["type"] == "vector_field")
    probe = next(layer for layer in field["scene"]["layers"] if layer["type"] == "probe_vector")
    heatmap = next(layer for layer in spectrogram["scene"]["layers"] if layer["type"] == "heatmap")
    waveform = next(
        layer for layer in spectrogram["scene"]["layers"] if layer.get("label") == "chirp waveform"
    )
    assert len(samples["points"]) == 13
    assert max(abs(y - math.sin(2 * math.pi * 4 * x)) for x, y in samples["points"]) < 1e-10
    assert len(vectors["vectors"]) == 24
    assert all(dx * x >= 0 and dy * y <= 0 for x, y, dx, dy in vectors["vectors"])
    assert evaluate_expression_v2(probe["x_expression"], {"x": 2, "y": 3}) == pytest.approx(2)
    assert evaluate_expression_v2(probe["y_expression"], {"x": 2, "y": 3}) == pytest.approx(-3)
    assert heatmap["rows"] * heatmap["columns"] == len(heatmap["values"]) <= 4096
    assert (
        max(abs(y - math.sin(2 * math.pi * (2 * x + 5 * x * x))) for x, y in waveform["points"])
        < 1e-10
    )
    panels = [layer for layer in spectrogram["scene"]["layers"] if layer["type"] == "panel"]
    assert len(panels) == 2
    assert {member for panel in panels for member in panel["members"]} == {
        "chirp energy",
        "chirp waveform",
    }

    invalid = json.loads(json.dumps(spectrogram))
    invalid["scene"]["layers"][1]["values"].pop()
    with pytest.raises(VisualizationV2Error):
        validate_v2_spec(invalid)
    duplicate_panel_member = json.loads(json.dumps(spectrogram))
    duplicate_panel_member["scene"]["layers"][-1]["members"].append("chirp energy")
    with pytest.raises(VisualizationV2Error):
        validate_v2_spec(duplicate_panel_member)


@pytest.mark.parametrize("bad_value", ["x", None, True, [], {}])
def test_resource_budget_validation_is_total_for_wrong_types(bad_value: object) -> None:
    spec = compile_visualization_v2("Plot y=x^2")
    assert spec is not None
    for field in ("max_points", "max_triangles", "max_fps"):
        invalid = json.loads(json.dumps(spec))
        invalid["budget"][field] = bad_value
        with pytest.raises(VisualizationV2Error):
            validate_v2_spec(invalid)


@pytest.mark.parametrize(
    ("prompt", "family"),
    [
        ("Plot y=x^0.5", "explicit_curve"),
        ("Plot y=(-x)^0.5", "explicit_curve"),
        ("Plot z=x^0.5+y", "explicit_surface"),
    ],
)
def test_fractional_powers_preserve_real_domain_gaps_without_crashing(
    prompt: str, family: str
) -> None:
    spec = compile_visualization_v2(prompt)
    assert spec is not None
    assert spec["family"] == family
    layer = next(
        layer
        for layer in spec["scene"]["layers"]
        if layer["type"] in {"polyline", "explicit_surface"}
    )
    if layer["type"] == "polyline":
        xs = [point[0] for point in layer["points"]]
        assert xs
        if "(-x)" in prompt:
            assert max(xs) <= 1e-6
        else:
            assert min(xs) >= -1e-6
    else:
        expression = layer["relationship"]["right"]
        with pytest.raises(VisualizationV2Error):
            evaluate_expression_v2(expression, {"x": -1, "y": 0})
        assert evaluate_expression_v2(expression, {"x": 4, "y": 1}) == pytest.approx(3)


def test_decision_boundary_includes_a_real_nonincreasing_training_loss() -> None:
    spec = compile_visualization_v2("Show a decision boundary while training")
    assert spec is not None
    loss = next(
        layer
        for layer in spec["scene"]["layers"]
        if layer.get("label") == "training loss versus epoch"
    )
    values = [point[1] for point in loss["points"]]
    assert len(values) >= 20
    assert all(next_value <= value for value, next_value in pairwise(values))
    assert values[-1] < values[0]


@pytest.mark.parametrize(
    ("prompt", "family", "renderer"),
    [
        ("Plot y=x^2", "explicit_curve", "svg"),
        ("Graph y=sin(x)", "explicit_curve", "svg"),
        ("Draw the line y=2*x+1", "explicit_curve", "svg"),
        ("Plot x^2+y^2=1", "implicit_curve", "svg"),
        ("Plot parametric x=cos(t), y=sin(t)", "parametric_curve", "svg"),
        ("Plot r=cos(3*theta)", "polar_curve", "svg"),
        ("Show a contour map of z=x^2+y^2", "contour_map", "canvas"),
        ("Plot vector field F=(y,-x)", "vector_field", "svg"),
    ],
)
def test_general_2d_planner_selects_the_requested_representation(
    prompt: str, family: str, renderer: str
) -> None:
    spec = compile_visualization_v2(prompt)
    assert spec is not None
    assert spec["family"] == family
    assert spec["renderer"] == renderer
    validate_v2_spec(spec)


@pytest.mark.parametrize(
    ("prompt", "family", "renderer"),
    [
        ("Render the implicit surface x^2+y^2+z^2=1", "implicit_surface", "three"),
        ("Visualize implicit surface x^2+y^2+z^2=1", "implicit_surface", "three"),
        ("Plot x^2+y^2+z^2=1 as an implicit surface", "implicit_surface", "three"),
        ("Plot the implicit curve x^2+y^2=1", "implicit_curve", "svg"),
        ("Plot x^2+y^2=1 as an implicit curve", "implicit_curve", "svg"),
    ],
)
def test_relationship_extraction_strips_only_visual_representation_prose(
    prompt: str, family: str, renderer: str
) -> None:
    spec = compile_visualization_v2(prompt)
    assert spec is not None
    assert spec["family"] == family
    assert spec["renderer"] == renderer
    validate_v2_spec(spec)


def test_multiview_science_families_include_every_requested_representation() -> None:
    prompts_and_labels = {
        "Compare zero-, first-, and second-order concentration curves and their linearized plots using one initial concentration.": (
            "zero-order [A]",
            "first-order [A]",
            "second-order [A]",
            "first-order linearized ln[A]",
            "second-order linearized 1/[A]",
        ),
        "Plot magnitude and phase for a first-order low-pass transfer function and move the cutoff frequency.": (
            "low-pass magnitude (dB)",
            "low-pass phase (degrees)",
        ),
        "Show a simply supported beam under a moving point load with synchronized shear, moment, and deflection diagrams.": (
            "shear V(x)",
            "bending moment M(x)",
            "deflection v(x)",
        ),
        "Plot incompressible flow around a cylinder with streamlines, stagnation points, and adjustable free-stream speed.": (
            "streamline ψ/U=0.35",
            "streamline ψ/U=−0.35",
            "stagnation points",
        ),
        "Show Monte Carlo uncertainty propagation for density ρ=m/V using sampled mass and volume distributions and a density histogram.": (
            "density histogram ρ=m/V",
            "sampled mass and positive volume pairs",
        ),
        "Simulate Lotka–Volterra predator and prey populations with time plots and a phase portrait.": (
            "prey population versus time",
            "predator population versus time",
            "predator-prey phase portrait",
        ),
    }
    for prompt, expected_labels in prompts_and_labels.items():
        spec = compile_visualization_v2(prompt)
        assert spec is not None
        labels = {str(layer.get("label", "")) for layer in spec["scene"]["layers"]}
        assert set(expected_labels) <= labels
        validate_v2_spec(spec)


def test_multiline_plane_system_uses_the_plane_intersection_family() -> None:
    prompt = """Show the intersection of the planes
x + y + z = 1
x - y + z = 0"""
    spec = compile_visualization_v2(prompt)
    assert spec is not None
    assert spec["family"] == "plane_intersection"
    assert spec["renderer"] == "three"
    planes = [layer for layer in spec["scene"]["layers"] if layer["type"] == "plane"]
    line = next(layer for layer in spec["scene"]["layers"] if layer["type"] == "line")
    assert [plane["constant"] for plane in planes] == pytest.approx([1, 0])
    for x, y, z in line["points"]:
        assert x + y + z == pytest.approx(1)
        assert x - y + z == pytest.approx(0)


@pytest.mark.parametrize("equation", ["z=x^2+y^2", "z=x^4+y^4", "z=exp(x+y)"])
def test_explicit_surface_domain_keeps_finite_selected_domain_corners(equation: str) -> None:
    spec = compile_visualization_v2(f"Plot {equation}")
    assert spec is not None
    layer = spec["scene"]["layers"][0]
    for x in layer["x_domain"]:
        for y in layer["y_domain"]:
            z = evaluate_expression_v2(layer["relationship"]["right"], {"x": x, "y": y})
            assert layer["z_domain"][0] <= z <= layer["z_domain"][1]


def test_implicit_domain_selection_has_no_corpus_equation_fragments() -> None:
    source = (Path(__file__).parents[1] / "gateway" / "visualization_v2.py").read_text()
    assert '"((x-5)^2"' not in source
    assert '")^3-x^2*z^3"' not in source


def test_general_expression_parser_is_typed_bounded_and_never_executes_source() -> None:
    expression = parse_expression_v2("sin(5*atan2(y,x))*exp(-0.1*(x^2+y^2))")
    value = evaluate_expression_v2(expression, {"x": 1, "y": 1})
    assert value == pytest.approx(math.sin(5 * math.atan2(1, 1)) * math.exp(-0.2))
    for unsafe in (
        "__import__(os)",
        "x.constructor",  # property access
        "fetch(x)",
        "x;alert(1)",
        "window.location",
        "x=1",
    ):
        with pytest.raises(VisualizationV2Error):
            parse_expression_v2(unsafe)
    oversized = "+".join("x" for _ in range(MAX_AST_NODES + 4))
    with pytest.raises(VisualizationV2Error):
        parse_expression_v2(oversized)


def test_damped_surface_numeric_invariants_and_axis_order() -> None:
    relationship = parse_relationship("z=4*exp(-y^2/4)*sin(2*x)")
    rhs = relationship["right"]
    at = lambda x, y: evaluate_expression_v2(rhs, {"x": x, "y": y, "z": 0})
    for y in (-4, -1, 0, 2, 4):
        assert at(0, y) == pytest.approx(0, abs=1e-12)
    assert at(math.pi / 4, 0) == pytest.approx(4)
    assert at(-math.pi / 4, 0) == pytest.approx(-4)
    assert abs(at(math.pi / 4, 0)) > abs(at(math.pi / 4, 2)) > abs(at(math.pi / 4, 4))
    # Swapping x and y fails both the zero-line and Gaussian-decay invariants.
    assert at(2, math.pi / 4) != pytest.approx(at(math.pi / 4, 2))


@pytest.mark.parametrize(
    ("source", "point"),
    [
        ("x^2+y^2+z^2=16", {"x": 4, "y": 0, "z": 0}),
        ("(sqrt(x^2+y^2)-3)^2+z^2=1", {"x": 4, "y": 0, "z": 0}),
        ("cos(x)+cos(y)+cos(z)=0", {"x": 0, "y": math.pi / 2, "z": math.pi}),
        ("abs(x)+abs(y)+abs(z)=4", {"x": 2, "y": 1, "z": 1}),
    ],
)
def test_implicit_relationship_known_points(source: str, point: dict[str, float]) -> None:
    assert relationship_residual(parse_relationship(source), point) == pytest.approx(0, abs=1e-9)


def test_schema_rejects_unknown_fields_prototype_keys_and_resource_overruns() -> None:
    spec = compile_visualization_v2("Plot z=x^2+y^2")
    assert spec is not None
    invalid = json.loads(json.dumps(spec))
    invalid["script"] = "alert(1)"
    with pytest.raises(VisualizationV2Error):
        validate_v2_spec(invalid)
    invalid = json.loads(json.dumps(spec))
    invalid["scene"]["layers"][0]["resolution"] = [65, 65, 65]
    invalid["scene"]["layers"][0]["type"] = "implicit_surface"
    with pytest.raises(VisualizationV2Error):
        validate_v2_spec(invalid)
    invalid = json.loads(json.dumps(spec))
    invalid["controls"].append({"id": "__proto__", "label": "bad", "type": "button", "value": 0})
    with pytest.raises(VisualizationV2Error):
        validate_v2_spec(invalid)


def test_existing_heart_hydrocarbon_orbit_v1_paths_remain_present() -> None:
    source = (Path(__file__).parents[1] / "gateway" / "visualizations.py").read_text()
    assert "_heart_spec" in source
    assert "_hydrocarbon_spec" in source
    assert "_satellite_orbit_spec" in source
    assert "Retain the hand-tuned shipped heart" in source


def test_robot_arm_spec_starts_at_a_valid_two_link_ik_solution() -> None:
    spec = compile_visualization_v2(
        "Draw a planar two-link robot arm, drag the end effector, and show both inverse-kinematic elbow solutions."
    )
    assert spec is not None
    nodes = {layer["id"]: layer for layer in spec["scene"]["layers"] if layer["type"] == "node"}
    first = math.dist(
        (nodes["base"]["x"], nodes["base"]["y"]),
        (nodes["elbow"]["x"], nodes["elbow"]["y"]),
    )
    second = math.dist(
        (nodes["elbow"]["x"], nodes["elbow"]["y"]),
        (nodes["end_effector"]["x"], nodes["end_effector"]["y"]),
    )
    assert first == pytest.approx(150, abs=1e-3)
    assert second == pytest.approx(135, abs=1e-3)
    assert (nodes["end_effector"]["x"], nodes["end_effector"]["y"]) == pytest.approx(
        (nodes["target"]["x"], nodes["target"]["y"])
    )


def test_lens_spec_obeys_thin_lens_equation_and_has_joined_ray_paths() -> None:
    spec = compile_visualization_v2(
        "Draw a ray diagram for a converging lens and let me move the object."
    )
    assert spec is not None
    nodes = {layer["id"]: layer for layer in spec["scene"]["layers"] if layer["type"] == "node"}
    arrows = {
        layer["label"]: layer for layer in spec["scene"]["layers"] if layer["type"] == "arrow"
    }
    focal = nodes["focal_right"]["x"] - nodes["lens"]["x"]
    object_distance = nodes["lens"]["x"] - nodes["object"]["x"]
    image_distance = nodes["image"]["x"] - nodes["lens"]["x"]
    assert 1 / focal == pytest.approx(1 / object_distance + 1 / image_distance, abs=1e-8)
    assert arrows["parallel incident ray"]["to"] == arrows["refracts through F′"]["from"]
    assert arrows["refracts through F′"]["to"] == pytest.approx(
        [nodes["image"]["x"], nodes["image"]["y"]]
    )


def test_kalman_spec_places_update_between_prior_and_measurement_and_contracts_variance() -> None:
    spec = compile_visualization_v2(
        "Track a noisy moving point with a Kalman estimate and covariance ellipse; step through predict and update."
    )
    assert spec is not None
    lines = {
        layer["label"]: layer["points"]
        for layer in spec["scene"]["layers"]
        if layer["type"] == "polyline"
    }
    assert len(lines["true moving-point trajectory"]) == 21
    assert len(lines["noisy measurements"]) == 21
    assert len(lines["Kalman estimate trajectory"]) == 21
    prior = lines["predicted covariance ellipse P⁻"]
    posterior = lines["posterior covariance ellipse P"]
    prior_centre = sum(point[1] for point in prior) / len(prior)
    posterior_centre = sum(point[1] for point in posterior) / len(posterior)
    measurement = lines["noisy measurements"][0][1]
    assert min(prior_centre, measurement) <= posterior_centre <= max(prior_centre, measurement)
    prior_variance = (
        (max(point[1] for point in prior) - min(point[1] for point in prior)) / 2
    ) ** 2
    posterior_variance = (
        (max(point[1] for point in posterior) - min(point[1] for point in posterior)) / 2
    ) ** 2
    assert 0 < posterior_variance < prior_variance


def test_truss_spec_has_force_balance_member_signs_and_reaction_directions() -> None:
    spec = compile_visualization_v2(
        "Draw a loaded triangular truss and colour members by tension or compression with reaction arrows."
    )
    assert spec is not None
    links = [layer for layer in spec["scene"]["layers"] if layer["type"] == "link"]
    arrows = [layer for layer in spec["scene"]["layers"] if layer["type"] == "arrow"]
    assert sum("compression" in layer["label"] for layer in links) == 2
    assert sum("tension" in layer["label"] for layer in links) == 1
    assert sum(layer["to"][1] > layer["from"][1] for layer in arrows) == 1
    assert sum(layer["to"][1] < layer["from"][1] for layer in arrows) == 2
