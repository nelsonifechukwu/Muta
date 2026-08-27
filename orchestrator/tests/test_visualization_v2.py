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


def test_declared_triangle_budget_covers_fixed_three_geometry_and_surfaces() -> None:
    surface = compile_visualization_v2("Plot z=sin(x)*cos(y)")
    assert surface is not None
    underdeclared_surface = json.loads(json.dumps(surface))
    underdeclared_surface["budget"]["max_triangles"] = 1
    with pytest.raises(VisualizationV2Error, match="triangle budget"):
        validate_v2_spec(underdeclared_surface)
    surface_layer = surface["scene"]["layers"][0]
    surface_mesh_triangles = (
        2 * (surface_layer["resolution"][0] - 1) * (surface_layer["resolution"][1] - 1)
    )
    exact_mesh_only = json.loads(json.dumps(surface))
    exact_mesh_only["budget"]["max_triangles"] = surface_mesh_triangles
    with pytest.raises(VisualizationV2Error, match="triangle budget"):
        validate_v2_spec(exact_mesh_only)
    exact_mesh_only["budget"]["max_triangles"] = surface_mesh_triangles + 24
    validate_v2_spec(exact_mesh_only)

    implicit = compile_visualization_v2("Plot implicit surface x^2+y^2+z^2=1")
    assert implicit is not None
    implicit["budget"]["max_triangles"] = 24
    with pytest.raises(VisualizationV2Error, match="triangle budget"):
        validate_v2_spec(implicit)
    implicit["budget"]["max_triangles"] = 25
    validate_v2_spec(implicit)

    parametric = compile_visualization_v2(
        "Plot parametric surface x(u,v)=cos(u), y(u,v)=sin(u), z(u,v)=v"
    )
    assert parametric is not None
    parametric_layer = parametric["scene"]["layers"][0]
    parametric_mesh_triangles = (
        2 * (parametric_layer["resolution"][0] - 1) * (parametric_layer["resolution"][1] - 1)
    )
    parametric["budget"]["max_triangles"] = parametric_mesh_triangles
    with pytest.raises(VisualizationV2Error, match="triangle budget"):
        validate_v2_spec(parametric)
    parametric["budget"]["max_triangles"] = parametric_mesh_triangles + 352
    validate_v2_spec(parametric)

    spheres = json.loads(json.dumps(surface))
    spheres["controls"] = []
    spheres["scene"] = {
        "coordinate_system": "cartesian3d",
        "layers": [
            {
                "type": "sphere",
                "position": [index % 6, index // 6, 0],
                "size": 0.2,
                "label": f"sample {index}",
                "color": "blue",
            }
            for index in range(24)
        ],
    }
    spheres["budget"] = {"max_points": 1, "max_triangles": 1, "max_fps": 20}
    with pytest.raises(VisualizationV2Error, match="triangle budget"):
        validate_v2_spec(spheres)
    spheres["budget"]["max_triangles"] = 24 * 720
    assert validate_v2_spec(spheres)["budget"]["max_triangles"] == 24 * 720


def test_typed_control_binding_targets_one_compatible_labelled_layer() -> None:
    spec = compile_visualization_v2("Draw a process diagram showing intake, transform, and output")
    assert spec is not None
    spec["controls"] = [
        {
            "id": "process_height",
            "label": "Process height",
            "type": "range",
            "value": 0,
            "min": -40,
            "max": 40,
            "step": 10,
            "binding": {"target_label": "Concept Process", "effect": "translate_y"},
        }
    ]
    assert validate_v2_spec(spec)["controls"][0]["binding"]["effect"] == "translate_y"

    missing = json.loads(json.dumps(spec))
    missing["controls"][0]["binding"]["target_label"] = "not present"
    with pytest.raises(VisualizationV2Error, match="unique labelled layer"):
        validate_v2_spec(missing)

    incompatible = json.loads(json.dumps(spec))
    incompatible["controls"][0]["binding"]["effect"] = "radius"
    with pytest.raises(VisualizationV2Error, match="incompatible"):
        validate_v2_spec(incompatible)

    invisible = json.loads(json.dumps(spec))
    invisible["renderer"] = "canvas"
    invisible["kind"] = "simulation2d"
    with pytest.raises(VisualizationV2Error, match="not rendered"):
        validate_v2_spec(invisible)


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


def test_server_schema_matches_browser_safe_family_and_numeric_types() -> None:
    spec = compile_visualization_v2("Plot z=x^2+y^2")
    assert spec is not None

    unsafe_family = json.loads(json.dumps(spec))
    unsafe_family["family"] = "not safe!"
    with pytest.raises(VisualizationV2Error, match="family is invalid"):
        validate_v2_spec(unsafe_family)

    boolean_ast = json.loads(json.dumps(spec))
    boolean_ast["scene"]["layers"][0]["relationship"]["right"] = {
        "type": "number",
        "value": True,
    }
    with pytest.raises(VisualizationV2Error, match="invalid numeric expression node"):
        validate_v2_spec(boolean_ast)

    boolean_resolution = json.loads(json.dumps(spec))
    boolean_resolution["scene"]["layers"][0]["resolution"][0] = True
    with pytest.raises(VisualizationV2Error, match="surface resolution is invalid"):
        validate_v2_spec(boolean_resolution)

    boolean_height = json.loads(json.dumps(spec))
    boolean_height["height"] = True
    with pytest.raises(VisualizationV2Error, match="height is outside"):
        validate_v2_spec(boolean_height)


def test_server_schema_fails_closed_on_cross_runtime_conformance_mutations() -> None:
    surface = compile_visualization_v2("Plot z=x^2+y^2")
    assert surface is not None

    def clone() -> dict:
        return json.loads(json.dumps(surface))

    def balanced_expression(leaves: int) -> dict:
        if leaves == 1:
            return {"type": "variable", "name": "x"}
        half = leaves // 2
        return {
            "type": "binary",
            "op": "+",
            "left": balanced_expression(half),
            "right": balanced_expression(leaves - half),
        }

    candidates: dict[str, dict] = {"none": clone()}
    candidate = clone()
    candidate["budget"]["max_points"] = 4096.5
    candidates["fractional_budget"] = candidate

    pythagoras = compile_visualization_v2("Explain Pythagoras with a diagram")
    assert pythagoras is not None
    candidate = json.loads(json.dumps(pythagoras))
    candidate["controls"][0]["id"] = "Height"
    candidates["unsafe_control_id"] = candidate
    candidate = json.loads(json.dumps(pythagoras))
    candidate["controls"][0]["label"] = "x" * 81
    candidates["oversize_control_label"] = candidate

    candidate = clone()
    candidate["scene"]["layers"] = [
        {"type": "sphere", "position": [1001, 0, 0], "size": 1, "label": "", "color": "teal"}
    ]
    candidates["invalid_sphere"] = candidate
    candidate = clone()
    candidate["scene"]["layers"] = [
        {
            "type": "line",
            "points": [[float(index), 0, 0] for index in range(513)],
            "label": "bounded line",
            "color": "teal",
        }
    ]
    candidates["oversize_line"] = candidate

    candidate = clone()
    candidate.update({"library": "d3", "renderer": "canvas", "kind": "simulation2d"})
    candidate["scene"] = {
        "coordinate_system": "screen",
        "layers": [
            {
                "type": "particles",
                "points": [[float(index), 0] for index in range(801)],
                "label": "particles",
                "color": "teal",
            }
        ],
    }
    candidates["oversize_particles"] = candidate

    candidate = clone()
    candidate["scene"]["layers"][0]["relationship"]["right"] = balanced_expression(64)
    candidate["scene"]["layers"][0]["resolution"] = [65, 65]
    candidates["oversize_surface_work"] = candidate

    candidate = clone()
    candidate["scene"]["layers"][0]["animation"] = ["mode", "duration"]
    candidates["malformed_animation"] = candidate

    candidate = clone()
    candidate["scene"]["layers"] = [
        {
            "type": "plane",
            "normal": [0, 0, 1],
            "constant": "oops",
            "label": "plane",
            "color": "teal",
        }
    ]
    candidates["malformed_plane"] = candidate

    candidate = clone()
    candidate["controls"] = [
        {"id": "choice", "label": "Choice", "type": "select", "value": "x", "options": [{}]}
    ]
    candidates["malformed_select"] = candidate

    candidate = json.loads(json.dumps(pythagoras))
    candidate["controls"][0]["step"] = 1e-7
    candidates["tiny_control_step"] = candidate

    candidate = clone()
    candidate["scene"]["layers"] = [
        {"type": "text", "x": 0, "y": index, "text": "界" * 160, "color": "teal"}
        for index in range(96)
    ]
    candidates["oversize_utf8"] = candidate

    candidate = clone()
    del candidate["scene"]["layers"][0]["z_domain"]
    candidates["missing_layer_field"] = candidate

    candidate = clone()
    candidate["scene"]["layers"][0]["relationship"]["right"] = balanced_expression(81)
    candidate["scene"]["layers"][0]["resolution"] = [9, 9]
    candidates["oversize_combined_ast"] = candidate

    candidate = clone()
    candidate.update({"library": "d3", "renderer": "svg", "kind": "scene2d"})
    candidate["scene"] = {
        "coordinate_system": "screen",
        "layers": [
            {"type": "circle", "x": 10001, "y": 0, "r": 2, "label": "circle", "color": "teal"}
        ],
    }
    candidates["invalid_circle_position"] = candidate

    candidate = json.loads(json.dumps(candidate))
    candidate["scene"]["layers"] = [
        {"type": "text", "x": 0, "y": 0, "text": "", "color": "teal"}
    ]
    candidates["empty_text"] = candidate

    candidate = clone()
    candidate["renderer"] = []
    candidates["malformed_renderer"] = candidate

    candidate = json.loads(json.dumps(pythagoras))
    candidate["controls"][0]["type"] = {}
    candidates["malformed_control_type"] = candidate

    candidate = clone()
    candidate["scene"]["coordinate_system"] = []
    candidates["malformed_coordinate_system"] = candidate

    candidate = clone()
    candidate["scene"]["layers"][0]["relationship"]["right"]["type"] = {}
    candidates["malformed_ast_type"] = candidate

    candidate = clone()
    candidate["scene"]["layers"][0]["relationship"]["right"] = {
        "type": "call",
        "name": {},
        "args": [{"type": "variable", "name": "x"}],
    }
    candidates["malformed_ast_function"] = candidate

    candidate = clone()
    candidate["scene"]["layers"][0]["animation"] = {"mode": {}, "duration": 8}
    candidates["malformed_animation_mode"] = candidate

    candidate = clone()
    candidate.update({"library": "d3", "renderer": "svg", "kind": "scene2d", "controls": []})
    candidate["scene"] = {
        "coordinate_system": "screen",
        "layers": [
            {
                "type": "node", "id": "a", "x": 0, "y": 0, "width": 20, "height": 20,
                "label": "A", "color": "teal",
            },
            {
                "type": "node", "id": "b", "x": 40, "y": 0, "width": 20, "height": 20,
                "label": "B", "color": "teal",
            },
            {"type": "link", "from": [], "to": "b", "arrow": True, "label": "edge"},
        ],
    }
    candidates["malformed_link_id"] = candidate

    candidate = json.loads(json.dumps(pythagoras))
    candidate["controls"][0]["binding"] = {"target_label": "triangle", "effect": {}}
    candidates["malformed_binding_effect"] = candidate

    candidate = clone()
    candidate.update({"library": "d3", "renderer": "svg", "kind": "scene2d"})
    candidate["scene"] = {
        "coordinate_system": "screen",
        "layers": [
            {
                "type": "panel",
                "id": "panel",
                "title": "Panel",
                "x_label": "x",
                "y_label": "y",
                "members": [{}],
            }
        ],
    }
    candidates["malformed_panel_members"] = candidate

    candidate = clone()
    candidate["renderer"] = ["three"]
    candidates["renderer_array"] = candidate
    candidate = clone()
    candidate["family"] = ["explicit_surface"]
    candidates["family_array"] = candidate
    candidate = clone()
    candidate["family"] = False
    candidates["family_boolean"] = candidate
    candidate = json.loads(json.dumps(pythagoras))
    candidate["controls"][0]["id"] = False
    candidates["control_id_boolean"] = candidate
    candidate = json.loads(json.dumps(pythagoras))
    candidate["controls"][0]["id"] = None
    candidates["control_id_null"] = candidate

    candidate = clone()
    candidate.update({"library": "d3", "renderer": "svg", "kind": "scene2d"})
    candidate["scene"] = {
        "coordinate_system": "screen",
        "layers": [
            {"type": "circle", "x": 10, "y": 10, "r": 2, "label": "circle", "color": ["gold"]}
        ],
    }
    candidates["color_array"] = candidate

    candidate = clone()
    candidate.update({"library": "d3", "renderer": "svg", "kind": "scene2d"})
    candidate["scene"] = {
        "coordinate_system": "screen",
        "layers": [
            {
                "type": "node", "id": ["n0"], "x": 0, "y": 0, "width": 20,
                "height": 20, "label": "Node", "color": "teal",
            }
        ],
    }
    candidates["node_id_array"] = candidate

    candidate = clone()
    candidate.update({"library": "d3", "renderer": "svg", "kind": "scene2d"})
    candidate["scene"] = {
        "coordinate_system": "screen",
        "layers": [
            {"type": "polyline", "label": "trace", "points": [[0, 0], [1, 1]], "color": "teal"},
            {
                "type": "panel", "id": ["panel"], "title": "Panel", "x_label": "x",
                "y_label": "y", "members": ["trace"],
            },
        ],
    }
    candidates["panel_id_array"] = candidate

    candidate = clone()
    candidate["scene"]["layers"][0]["relationship"]["right"] = {
        "type": "number", "value": 1e100,
    }
    candidates["large_ast_number"] = candidate

    candidate = clone()
    candidate["scene"]["layers"] = [
        {"type": "text", "x": 0, "y": index, "text": "界" * 160, "color": "teal"}
        for index in range(60)
    ]
    candidates["utf8_within_byte_budget"] = candidate

    conformance_path = (
        Path(__file__).parents[2]
        / "ui"
        / "tests"
        / "fixtures"
        / "visualization-v2-schema-conformance.json"
    )
    conformance = json.loads(conformance_path.read_text())
    assert {case["operation"] for case in conformance["cases"]} == candidates.keys()
    for case in conformance["cases"]:
        candidate = candidates[case["operation"]]
        if case["accepted"]:
            validate_v2_spec(candidate)
        else:
            with pytest.raises(VisualizationV2Error, match=".+"):
                validate_v2_spec(candidate)


def test_schema_generated_type_mutations_are_total_and_fail_closed() -> None:
    bases = [
        compile_visualization_v2("Plot z=x^2+y^2"),
        compile_visualization_v2("Explain Pythagoras with a diagram"),
    ]
    assert all(base is not None for base in bases)

    def paths(value: object, prefix: tuple[object, ...] = ()):
        if isinstance(value, dict):
            for key, child in value.items():
                path = (*prefix, key)
                yield path, [] if isinstance(child, dict) else {} if isinstance(child, list) else [] if isinstance(child, str) else {}
                yield from paths(child, path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                path = (*prefix, index)
                yield path, [] if isinstance(child, dict) else {} if isinstance(child, list) else [] if isinstance(child, str) else {}
                yield from paths(child, path)

    mutation_count = 0
    for base in bases:
        assert base is not None
        for path, replacement in paths(base):
            candidate = json.loads(json.dumps(base))
            parent: object = candidate
            for part in path[:-1]:
                parent = parent[part]  # type: ignore[index]
            parent[path[-1]] = replacement  # type: ignore[index]
            mutation_count += 1
            with pytest.raises(VisualizationV2Error, match=".+"):
                validate_v2_spec(candidate)
    assert mutation_count >= 100


def test_schema_rejects_huge_json_integers_with_only_the_domain_error() -> None:
    surface = compile_visualization_v2("Plot z=x^2+y^2")
    pythagoras = compile_visualization_v2("Explain Pythagoras with a diagram")
    assert surface is not None and pythagoras is not None

    surface["scene"]["layers"][0]["relationship"]["right"] = {
        "type": "number", "value": 10**1000,
    }
    pythagoras["controls"][0]["value"] = 10**1000
    for candidate in (surface, pythagoras):
        with pytest.raises(VisualizationV2Error, match=".+"):
            validate_v2_spec(candidate)


def test_schema_rejects_type_confused_incomplete_or_static_animation_transport() -> None:
    static = compile_visualization_v2("Plot z=x^2+y^2")
    assert static is not None

    numeric_play = json.loads(json.dumps(static))
    numeric_play["controls"].append(
        {
            "id": "play",
            "label": "Play",
            "type": "range",
            "value": 0,
            "min": 0,
            "max": 1,
            "step": 0.1,
        }
    )
    with pytest.raises(VisualizationV2Error, match="transport controls must be buttons"):
        validate_v2_spec(numeric_play)

    stray_play = json.loads(json.dumps(static))
    stray_play["controls"].append(
        {"id": "play", "label": "Play", "type": "button", "value": 0}
    )
    with pytest.raises(VisualizationV2Error, match="animation requires"):
        validate_v2_spec(stray_play)

    incomplete = json.loads(json.dumps(static))
    incomplete["scene"]["layers"][0]["animation"] = {"mode": "orbit", "duration": 8}
    incomplete["controls"].append(
        {"id": "play", "label": "Play", "type": "button", "value": 0}
    )
    with pytest.raises(VisualizationV2Error, match="animation requires"):
        validate_v2_spec(incomplete)

    misleading = json.loads(json.dumps(static))
    misleading["scene"]["layers"][0]["animation"] = {"mode": "orbit", "duration": 8}
    misleading["controls"].extend(
        [
            {"id": "play", "label": "Delete diagram", "type": "button", "value": 0},
            {"id": "pause", "label": "Export result", "type": "button", "value": 0},
            {"id": "restart", "label": "Submit answer", "type": "button", "value": 0},
        ]
    )
    with pytest.raises(VisualizationV2Error, match="labels must match their action"):
        validate_v2_spec(misleading)


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


def test_markdown_heading_does_not_hide_a_later_visual_action() -> None:
    prompt = (
        "**Dynamics study**\nUse a labelled diagram to illustrate a spring and its restoring force."
    )
    intent = resolve_intent(prompt)
    assert intent.requested
    spec = compile_visualization_v2(prompt)
    assert spec is not None
    assert spec["family"] == "spring_mass"


def test_named_multiview_family_owns_its_embedded_equation() -> None:
    spec = compile_visualization_v2(
        "Animate optimization for f(x,y)=x^2+2*y^2 on linked surface and contour views."
    )
    assert spec is not None
    assert spec["family"] == "gradient_descent"
    panels = [layer for layer in spec["scene"]["layers"] if layer["type"] == "panel"]
    labels = {layer.get("label") for layer in spec["scene"]["layers"]}
    assert len(panels) == 2
    assert "gradient-descent trajectory on projected surface" in labels
    assert "gradient-descent trajectory on contour map" in labels
    controls = {control["id"]: control for control in spec["controls"]}
    assert controls["step"]["max"] == 16
    validate_v2_spec(spec)


@pytest.mark.parametrize(
    ("prompt", "family", "renderer", "required_layer"),
    [
        ("Draw the head-to-tail sum of vectors a and b.", "vector_addition", "svg", "vector_field"),
        (
            "Show an eight-four-two-one binary place-value diagram.",
            "binary_representation",
            "svg",
            "node",
        ),
        (
            "Visualise a selectable three-dimensional vector field F=(−y,x,z).",
            "vector_field_3d",
            "three",
            "vector",
        ),
        (
            "Animate the Lorenz system while varying its three parameters.",
            "lorenz_attractor",
            "three",
            "line",
        ),
        (
            "Model perpendicular electric and magnetic waves propagating in 3D.",
            "electromagnetic_wave",
            "three",
            "line",
        ),
        (
            "Map true, odometry, and fused robot poses with uncertainty.",
            "robot_localization",
            "canvas",
            "particles",
        ),
        (
            "Draw a three-link manipulator controlled by its joint angles.",
            "robot_forward_kinematics",
            "svg",
            "link",
        ),
    ],
)
def test_post_holdout_general_families_are_typed_and_validated(
    prompt: str,
    family: str,
    renderer: str,
    required_layer: str,
) -> None:
    spec = compile_visualization_v2(prompt)
    assert spec is not None
    assert spec["family"] == family
    assert spec["renderer"] == renderer
    assert any(layer["type"] == required_layer for layer in spec["scene"]["layers"])
    validate_v2_spec(spec)


def test_localization_controls_cover_the_entire_deterministic_trajectory() -> None:
    spec = compile_visualization_v2(
        "Simulate robot localization with adjustable odometry and sensor noise and a step control."
    )
    assert spec is not None
    controls = {control["id"]: control for control in spec["controls"]}
    assert controls["step"] == {
        "id": "step",
        "label": "Step",
        "type": "step",
        "value": 30,
        "min": 0,
        "max": 60,
        "step": 1,
    }
    assert (
        len(
            next(
                layer
                for layer in spec["scene"]["layers"]
                if layer.get("label") == "true pose trajectory"
            )["points"]
        )
        == 61
    )


@pytest.mark.parametrize(
    ("prompt", "labels"),
    [
        (
            "Plot y = 2x + 3 and label the slope and intercept.",
            {"y-intercept (0,3)", "slope rise/run = 2/1"},
        ),
        (
            "Plot y = x^2 - 4x + 3 and show roots, vertex and axis of symmetry.",
            {"vertex (2,-1); roots 1, 3", "axis of symmetry x=2"},
        ),
        (
            "Plot y = 2 sin(3x) and show amplitude, wavelength, maxima, minimum, and zero crossings.",
            {"amplitude≈2; wavelength≈2.09; extrema and zero crossings"},
        ),
        (
            "Draw x^2+y^2=9 and label its centre and radius.",
            {"centre (0,0) and radius point", "radius≈3"},
        ),
    ],
)
def test_generic_equation_annotations_are_derived_from_the_typed_relationship(
    prompt: str, labels: set[str]
) -> None:
    spec = compile_visualization_v2(prompt)
    assert spec is not None
    actual = {str(layer.get("label")) for layer in spec["scene"]["layers"]}
    assert labels <= actual
    assert spec["family"] in {"explicit_curve", "implicit_curve"}
    validate_v2_spec(spec)


def test_hooke_source_charge_network_kalman_and_clipping_controls_are_semantic() -> None:
    spring = compile_visualization_v2(
        "Illustrate Hooke law with spring constant and displacement controls; show restoring force."
    )
    assert spring is not None
    assert [control["id"] for control in spring["controls"]] == [
        "spring_constant",
        "displacement",
    ]

    source_charges = compile_visualization_v2(
        "Simulate electric field vectors for two point charges and let either charge move."
    )
    assert source_charges is not None
    assert [control["id"] for control in source_charges["controls"][:4]] == [
        "positive_charge_x",
        "negative_charge_x",
        "test_x",
        "test_y",
    ]
    movable_test = compile_visualization_v2(
        "Show electric field vectors for two point charges and move a test charge."
    )
    assert movable_test is not None
    assert [control["id"] for control in movable_test["controls"]] == ["test_x", "test_y"]

    network = compile_visualization_v2(
        "Draw a neural network architecture 2-3-1 with weights and activations."
    )
    assert network is not None
    node_ids = {layer["id"] for layer in network["scene"]["layers"] if layer["type"] == "node"}
    assert {"x1", "x2", "h1", "h2", "h3", "output"} == node_ids

    kalman = compile_visualization_v2(
        "Visualize a Kalman filter with measurement noise, process noise, and step controls."
    )
    assert kalman is not None
    assert [control["id"] for control in kalman["controls"]] == [
        "noise",
        "process_noise",
        "step",
    ]

    gyroid = compile_visualization_v2(
        "Plot sin(x)*cos(y)+sin(y)*cos(z)+sin(z)*cos(x)=0 as a 3D gyroid surface with clipping."
    )
    assert gyroid is not None
    assert gyroid["family"] == "implicit_surface"
    assert gyroid["controls"][0]["id"] == "clip_z"
    for spec in (spring, source_charges, movable_test, network, kalman, gyroid):
        validate_v2_spec(spec)
