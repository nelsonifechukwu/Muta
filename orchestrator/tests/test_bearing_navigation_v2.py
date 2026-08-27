"""General and held-out regression checks for the deterministic navigation planner."""

from __future__ import annotations

import copy
import json
import math
import random
from pathlib import Path

import pytest

from orchestrator.gateway.bearing_navigation_v2 import (
    _components,
    _coordinate_bearing,
    compile_bearing_navigation_v2,
    is_bearing_navigation_request,
)
from orchestrator.gateway.visualization_v2 import (
    VisualizationV2Error,
    compile_visualization_v2,
    validate_v2_spec,
)

FIRST_RUN = (
    Path(__file__).parents[2]
    / "docs"
    / "qa"
    / "visualization-v2-bearings-holdout-first-python.json"
)


def _heldout_rows() -> list[dict[str, object]]:
    return json.loads(FIRST_RUN.read_text())["cases"]


def test_all_exact_bearings_holdout_prompts_now_compile_to_valid_navigation_specs() -> None:
    rows = _heldout_rows()
    assert len(rows) == 15
    for row in rows:
        spec = compile_visualization_v2(str(row["raw_prompt"]))
        assert spec is not None
        assert spec["family"] == "bearing_navigation"
        assert spec["renderer"] == "svg"
        assert validate_v2_spec(spec) == spec
        assert any(layer["type"] == "arrow" for layer in spec["scene"]["layers"])
        assert any(layer["type"] == "angle_arc" for layer in spec["scene"]["layers"])
        assert any("N at" in layer.get("label", "") for layer in spec["scene"]["layers"])


@pytest.mark.parametrize(
    ("case_number", "required_text"),
    [
        (1, "bearing 060°"),
        (2, "bearing 135°"),
        (3, "bearing 135°"),
        (4, "250°"),
        (5, "050°"),
        (6, "220°, not 320°"),
        (7, "east = 80 sin 40° = 51.42 km; north = 80 cos 40° = 61.28 km"),
        (8, "10.00 km on bearing 083°"),
        (9, "15.87 km apart"),
        (10, "bearing 037°"),
        (11, "bearing 246°"),
        (12, "22.14 km from B on bearing 201°"),
        (13, "28.23 km on bearing 141°"),
        (14, "7.78 km from A and 7.78 km from B"),
        (15, "1.303 h on bearing 086°"),
    ],
)
def test_bearings_holdout_semantic_oracles(case_number: int, required_text: str) -> None:
    row = _heldout_rows()[case_number - 1]
    spec = compile_visualization_v2(str(row["raw_prompt"]))
    assert spec is not None
    assert required_text in spec["text_fallback"]


def test_navigation_coordinate_convention_and_quadrants() -> None:
    east, north = _components(80, 40)
    assert east == pytest.approx(51.4230088)
    assert north == pytest.approx(61.2835554)
    assert _coordinate_bearing(6, 8) == pytest.approx(36.8698976)
    assert _coordinate_bearing(-9, -4) == pytest.approx(246.037511)
    assert _coordinate_bearing(0, -1) == pytest.approx(180)
    assert _coordinate_bearing(-1, 0) == pytest.approx(270)


def test_bearing_component_round_trip_property() -> None:
    for angle in range(0, 360, 7):
        east, north = _components(37.5, angle)
        assert math.hypot(east, north) == pytest.approx(37.5)
        assert _coordinate_bearing(east, north) == pytest.approx(angle % 360)


def test_reverse_bearing_property_and_claim_grading() -> None:
    for angle in range(0, 360, 11):
        reverse = (angle + 180) % 360
        spec = compile_bearing_navigation_v2(
            f"Draw the reverse bearing when a vessel travels on bearing {angle:03d}°."
        )
        assert spec is not None
        assert f"{reverse:03d}°" in spec["text_fallback"]
    correct_claim = compile_bearing_navigation_v2(
        "A student says B is on bearing 010° from A, so A is on bearing 190° from B. Draw it."
    )
    assert correct_claim is not None
    assert "claim 190° is correct" in correct_claim["text_fallback"]


def test_unseen_navigation_paraphrases_use_general_solver_not_exact_prompt_routes() -> None:
    reverse = compile_bearing_navigation_v2(
        "Visualise a kayak from X to Y on bearing 275 degrees; find and mark the reverse bearing."
    )
    components = compile_bearing_navigation_v2(
        "Sketch a drone flying 25 km on bearing 315° and show its east and north components."
    )
    coordinates = compile_bearing_navigation_v2(
        "Draw a navigation triangle for a beacon 12 km west and 5 km north of a vessel."
    )
    mapped = compile_bearing_navigation_v2(
        "Map a hiker's 14 km displacement on bearing 205 degrees."
    )
    assert reverse is not None and "095°" in reverse["text_fallback"]
    assert components is not None and "= -17.68 km" in components["text_fallback"]
    assert coordinates is not None and "bearing 293°" in coordinates["text_fallback"]
    assert mapped is not None and "bearing 205°" in mapped["text_fallback"]


def test_non_visual_or_non_navigation_requests_do_not_trigger() -> None:
    assert not is_bearing_navigation_request(
        "Show the proof that reverse bearings differ by 180 degrees in text only"
    )
    assert not is_bearing_navigation_request("Draw a labelled plant cell")
    assert compile_bearing_navigation_v2("Explain what a bearing is without a diagram") is None


def test_malformed_navigation_fuzz_fails_closed_without_exceptions() -> None:
    generator = random.Random(20260827)
    alphabet = "bearing draw north south east west ()°0123456789\\text{km};:-_\n"
    for _ in range(300):
        prompt = "".join(generator.choice(alphabet) for _ in range(generator.randrange(0, 500)))
        spec = compile_bearing_navigation_v2(prompt)
        if spec is not None:
            assert validate_v2_spec(spec) == spec
            assert spec["family"] == "bearing_navigation"


def test_angle_arc_schema_is_strict_and_bounded() -> None:
    spec = compile_bearing_navigation_v2("Draw point B on bearing 060° from A")
    assert spec is not None
    arc_index = next(
        index for index, layer in enumerate(spec["scene"]["layers"]) if layer["type"] == "angle_arc"
    )
    malformed = copy.deepcopy(spec)
    malformed["scene"]["layers"][arc_index]["clockwise"] = "yes"
    with pytest.raises(VisualizationV2Error, match="angle arc"):
        validate_v2_spec(malformed)
    oversized = copy.deepcopy(spec)
    oversized["scene"]["layers"][arc_index]["r"] = math.inf
    with pytest.raises(VisualizationV2Error, match="angle arc"):
        validate_v2_spec(oversized)


def test_production_navigation_source_contains_no_holdout_fixture_or_case_routes() -> None:
    source = (
        (Path(__file__).parents[1] / "gateway" / "bearing_navigation_v2.py").read_text().casefold()
    )
    assert "muta-bearings-heldout" not in source
    assert "visualization-v2-bearings-holdout" not in source
    assert "case 15" not in source
    assert "prompt 15" not in source
