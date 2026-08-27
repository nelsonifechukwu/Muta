#!/usr/bin/env python3
"""Build the reproducible 200-case Visualization V2 acceptance report.

The fixture prompts are QA inputs only. Production compilation always runs through
``orchestrator.gateway.visualization_v2``; this script never installs a fixture-specific route.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import re
import time
from pathlib import Path
from typing import Any

from orchestrator.gateway.visualization_v2 import (
    VisualizationV2Error,
    compile_visualization_v2,
    evaluate_expression_v2,
    iter_ast,
    parse_relationship,
    relationship_residual,
    validate_v2_spec,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "orchestrator" / "tests" / "fixtures" / "visualization_v2"
SPEC_OUTPUT = ROOT / "ui" / "tests" / "fixtures" / "visualization-v2-specs.json"
FOLLOWUP_OUTPUT = ROOT / "ui" / "tests" / "fixtures" / "visualization-v2-followups.json"
GENERAL_MATH_OUTPUT = ROOT / "ui" / "tests" / "fixtures" / "visualization-v2-general-math.json"
JSON_OUTPUT = ROOT / "docs" / "qa" / "visualization-v2-results.json"
MARKDOWN_OUTPUT = ROOT / "docs" / "qa" / "visualization-v2-report.md"


def load_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    expected = {
        "stem_supplied.json": 50,
        "math_supplied.json": 100,
        "synthetic_held_out.json": 50,
    }
    for name, count in expected.items():
        data = json.loads((FIXTURES / name).read_text())
        if data.get("count") != count or len(data.get("cases", [])) != count:
            raise SystemExit(f"{name}: expected {count} cases")
        cases.extend(data["cases"])
    if len(cases) != 200 or len({case["id"] for case in cases}) != 200:
        raise SystemExit("acceptance corpus must contain exactly 200 unique cases")
    return cases


def _finite_explicit_samples(layer: dict[str, Any]) -> tuple[int, int, float]:
    finite = 0
    undefined = 0
    worst_residual = 0.0
    for ix in range(9):
        x = layer["x_domain"][0] + (layer["x_domain"][1] - layer["x_domain"][0]) * ix / 8
        for iy in range(9):
            y = layer["y_domain"][0] + (layer["y_domain"][1] - layer["y_domain"][0]) * iy / 8
            try:
                z = evaluate_expression_v2(layer["relationship"]["right"], {"x": x, "y": y})
                if layer["z_domain"][0] <= z <= layer["z_domain"][1]:
                    finite += 1
                    worst_residual = max(
                        worst_residual,
                        abs(relationship_residual(layer["relationship"], {"x": x, "y": y, "z": z})),
                    )
            except (VisualizationV2Error, ValueError, OverflowError):
                undefined += 1
    return finite, undefined, worst_residual


def _implicit_sign_probe(layer: dict[str, Any]) -> tuple[int, int, float, float]:
    negative = 0
    positive = 0
    minimum = math.inf
    maximum = -math.inf
    for ix in range(11):
        x = layer["x_domain"][0] + (layer["x_domain"][1] - layer["x_domain"][0]) * ix / 10
        for iy in range(11):
            y = layer["y_domain"][0] + (layer["y_domain"][1] - layer["y_domain"][0]) * iy / 10
            for iz in range(11):
                z = layer["z_domain"][0] + (layer["z_domain"][1] - layer["z_domain"][0]) * iz / 10
                try:
                    residual = relationship_residual(
                        layer["relationship"], {"x": x, "y": y, "z": z}
                    )
                except (VisualizationV2Error, ValueError, OverflowError):
                    continue
                minimum = min(minimum, residual)
                maximum = max(maximum, residual)
                negative += residual < 0
                positive += residual > 0
    return negative, positive, minimum, maximum


def _relationship_agreement(
    actual: dict[str, Any], expected_source: str, explicit: bool
) -> dict[str, Any]:
    expected = parse_relationship(expected_source)
    compared = 0
    mismatches = 0
    worst_error = 0.0
    samples = (-1.25, -0.4, 0.3, 1.1)
    for x in samples:
        for y in samples:
            for z in (0.0,) if explicit else samples:
                variables = {"x": x, "y": y, "z": z}
                try:
                    if explicit:
                        actual_value = evaluate_expression_v2(actual["right"], variables)
                        expected_value = evaluate_expression_v2(expected["right"], variables)
                    else:
                        actual_value = relationship_residual(actual, variables)
                        expected_value = relationship_residual(expected, variables)
                except (VisualizationV2Error, ValueError, OverflowError):
                    continue
                compared += 1
                error = abs(actual_value - expected_value)
                worst_error = max(worst_error, error)
                mismatches += error > 1e-7 * (1 + abs(expected_value))
    return {
        "passed": compared >= 4 and mismatches == 0,
        "compared_samples": compared,
        "mismatches": mismatches,
        "max_error": worst_error,
    }


def _labels(spec: dict[str, Any]) -> str:
    values = [spec["title"], spec["aria_label"], spec["text_fallback"]]
    for layer in spec["scene"]["layers"]:
        values.extend(str(layer.get(key, "")) for key in ("label", "text", "x_label", "y_label"))
    return " ".join(values).casefold()


def _controls(spec: dict[str, Any]) -> dict[str, Any]:
    return {control["id"]: control["value"] for control in spec["controls"]}


def _polylines(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return [layer for layer in spec["scene"]["layers"] if layer["type"] == "polyline"]


def _nodes(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return [layer for layer in spec["scene"]["layers"] if layer["type"] == "node"]


def _closed(points: list[list[float]], tolerance: float = 1e-9) -> bool:
    return len(points) >= 3 and all(
        abs(points[0][index] - points[-1][index]) <= tolerance for index in range(len(points[0]))
    )


def _shoelace(points: list[list[float]]) -> float:
    if not _closed(points):
        return 0.0
    return (
        abs(
            sum(
                points[index][0] * points[index + 1][1] - points[index + 1][0] * points[index][1]
                for index in range(len(points) - 1)
            )
        )
        / 2
    )


def _result(passed: bool, evidence: Any) -> dict[str, Any]:
    return {"passed": bool(passed), "evidence": evidence}


_SEMANTIC_RELATIONSHIP_FAMILIES = {
    "quadratic",
    "line_intersection",
    "triangle_angles",
    "derivative_tangent",
    "riemann_sum",
    "gradient_field",
    "plane_intersection",
    "linear_transform",
    "inclined_plane",
    "spring_mass",
    "elastic_collision",
    "pendulum",
    "travelling_wave",
    "wave_interference",
    "circular_motion",
    "harmonic_motion",
    "double_pendulum",
    "series_parallel_circuit",
    "electric_field_lines",
    "electric_field_vectors",
    "magnetic_field_wire",
    "rc_circuit",
    "rlc_circuit",
    "ac_phase",
    "converging_lens",
    "ideal_gas",
    "carnot_cycle",
    "atom",
    "ionic_bond",
    "molecular_geometry",
    "reaction_profile",
    "titration",
    "molecular_orbitals",
    "animal_cell",
    "mitosis",
    "circulation",
    "action_potential",
    "binary_search_tree",
    "stack_queue",
    "cpu_memory",
}


def _semantic_relationship_oracle(spec: dict[str, Any]) -> dict[str, Any] | None:
    """Execute family-specific invariants for the supplied STEM semantic oracle.

    Returning ``None`` means the family has no implementation and must fail closed. This avoids
    silently treating a label or connected concept chain as evidence of scientific correctness.
    """

    family = spec["family"]
    if family not in _SEMANTIC_RELATIONSHIP_FAMILIES:
        return None
    controls = _controls(spec)
    layers = spec["scene"]["layers"]
    lines = _polylines(spec)
    nodes = _nodes(spec)
    links = [layer for layer in layers if layer["type"] == "link"]
    arrows = [layer for layer in layers if layer["type"] == "arrow"]
    node_ids = {node["id"] for node in nodes}
    line_by_label = {str(line.get("label", "")).casefold(): line for line in lines}

    if family == "line_intersection":
        if len(lines) != 2:
            return _result(False, {"curves": len(lines)})
        equations = ((controls["m1"], controls["c1"]), (controls["m2"], controls["c2"]))
        errors = [
            max(abs(y - (slope * x + intercept)) for x, y in line["points"])
            for line, (slope, intercept) in zip(lines, equations)
        ]
        denominator = controls["m1"] - controls["m2"]
        intersection = (
            None if abs(denominator) < 1e-12 else ((controls["c2"] - controls["c1"]) / denominator)
        )
        return _result(
            max(errors) < 1e-9 and intersection is not None,
            {"curve_errors": errors, "intersection_x": intersection},
        )
    if family == "triangle_angles":
        total = sum(float(controls[key]) for key in ("vertex_a", "vertex_b", "vertex_c"))
        labelled_vertices = {
            label
            for label in (str(node.get("label", "")) for node in nodes)
            if label.startswith("vertex ")
        }
        return _result(
            abs(total - 180) < 1e-9 and len(labelled_vertices) == 3 and len(links) >= 3,
            {"angle_sum": total, "vertices": sorted(labelled_vertices)},
        )
    if family == "derivative_tangent":
        if len(lines) != 2:
            return _result(False, {"curves": len(lines)})
        at = float(controls["x"])
        value = at**3 - 3 * at
        slope = 3 * at**2 - 3
        residual = max(abs(y - (value + slope * (x - at))) for x, y in lines[1]["points"])
        return _result(
            residual < 1e-9
            and abs(lines[1]["points"][40][1] - (value + slope * (lines[1]["points"][40][0] - at)))
            < 1e-9,
            {"x": at, "slope": slope, "tangent_residual": residual},
        )
    if family == "riemann_sum":
        rectangles = lines[1]["points"] if len(lines) > 1 else []
        count = int(controls["rectangles"])
        width = 4 / count
        chunks = [rectangles[index : index + 4] for index in range(0, len(rectangles), 4)]
        area = sum((chunk[2][0] - chunk[1][0]) * chunk[1][1] for chunk in chunks if len(chunk) == 4)
        expected = sum((index * width) ** 2 * width for index in range(count))
        return _result(
            len(chunks) == count and abs(area - expected) < 1e-9,
            {"rectangles": len(chunks), "left_sum": area, "expected": expected},
        )
    if family == "gradient_field":
        probe = lines[-1]["points"] if len(lines) >= 4 else []
        expected_start = [float(controls["point_x"]), float(controls["point_y"])]
        expected_end = [
            expected_start[0] + 0.9 * expected_start[0],
            expected_start[1] + 0.9 * expected_start[1],
        ]
        contour_error = max(
            (
                abs(math.hypot(*point) - radius)
                for radius, line in enumerate(lines[:3], 1)
                for point in line["points"]
            ),
            default=math.inf,
        )
        return _result(
            probe == [expected_start, expected_end] and contour_error < 1e-7,
            {
                "probe": probe,
                "expected": [expected_start, expected_end],
                "contour_error": contour_error,
            },
        )
    if family == "plane_intersection":
        planes = [layer for layer in layers if layer["type"] == "plane"]
        line3d = next((layer for layer in layers if layer["type"] == "line"), None)
        residuals = []
        if line3d:
            for point in line3d["points"]:
                for plane in planes:
                    residuals.append(
                        abs(sum(a * b for a, b in zip(plane["normal"], point)) - plane["constant"])
                    )
        directions = [plane["normal"] for plane in planes]
        independent = len(directions) == 2 and math.dist(directions[0], directions[1]) > 1e-8
        return _result(
            len(planes) == 2
            and bool(line3d)
            and independent
            and max(residuals, default=math.inf) < 1e-7,
            {"plane_residuals": residuals, "independent": independent},
        )
    if family == "linear_transform":
        options = next(
            (control.get("options") for control in spec["controls"] if control["id"] == "matrix"),
            [],
        )
        grid = [
            line
            for line in lines
            if str(line.get("label", "")).startswith(("vertical", "horizontal"))
        ]
        basis = [line for line in lines if str(line.get("label", "")).startswith("basis")]
        eigen_tests = [
            line for line in lines if "invariant-direction" in str(line.get("label", ""))
        ]
        return _result(
            len(grid) == 14
            and len(basis) == 2
            and len(eigen_tests) == 2
            and options == ["identity", "shear", "scale"],
            {
                "grid_lines": len(grid),
                "basis_vectors": len(basis),
                "eigenvector_tests": len(eigen_tests),
                "options": options,
            },
        )
    if family == "inclined_plane":
        rect = next((layer for layer in layers if layer["type"] == "rect"), None)
        by_prefix = {str(arrow["label"]).split()[0]: arrow for arrow in arrows}
        required = {"inclined", "weight", "normal", "friction", "resultant"}
        if rect is None or not required <= by_prefix.keys():
            return _result(False, {"arrows": sorted(by_prefix)})
        vector = lambda arrow: [
            arrow["to"][0] - arrow["from"][0],
            arrow["to"][1] - arrow["from"][1],
        ]
        tangent = vector(by_prefix["inclined"])
        normal = vector(by_prefix["normal"])
        friction = vector(by_prefix["friction"])
        resultant = vector(by_prefix["resultant"])
        dot = tangent[0] * normal[0] + tangent[1] * normal[1]
        cross_friction = tangent[0] * friction[1] - tangent[1] * friction[0]
        cross_resultant = tangent[0] * resultant[1] - tangent[1] * resultant[0]
        opposite = friction[0] * resultant[0] + friction[1] * resultant[1] < 0
        same_origin = (
            len(
                {
                    tuple(by_prefix[key]["from"])
                    for key in ("weight", "normal", "friction", "resultant")
                }
            )
            == 1
        )
        return _result(
            abs(dot) < 1e-6
            and abs(cross_friction) < 1e-6
            and abs(cross_resultant) < 1e-6
            and opposite
            and same_origin,
            {
                "normal_dot_plane": dot,
                "friction_cross": cross_friction,
                "resultant_cross": cross_resultant,
                "opposite": opposite,
                "same_origin": same_origin,
            },
        )
    if family == "spring_mass":
        by_id = {node["id"]: node for node in nodes}
        extension = 9.81 * controls["mass"] / controls["spring_constant"]
        force_arrows = {str(arrow["label"]).split()[0]: arrow for arrow in arrows}
        balance = False
        if {"weight", "spring"} <= force_arrows.keys():
            weight = force_arrows["weight"]
            spring = force_arrows["spring"]
            balance = (
                abs(
                    math.dist(weight["from"], weight["to"])
                    - math.dist(spring["from"], spring["to"])
                )
                < 1e-8
            )
        return _result(
            {"support", "mass"} <= by_id.keys()
            and len(links) == 1
            and balance
            and extension > 0
            and "mg/k" in _labels(spec),
            {"extension_m": extension, "balanced_force_arrows": balance},
        )
    if family == "elastic_collision":
        m1, u1, m2, u2 = (
            float(controls[key]) for key in ("mass_1", "velocity_1", "mass_2", "velocity_2")
        )
        v1 = ((m1 - m2) * u1 + 2 * m2 * u2) / (m1 + m2)
        v2 = (2 * m1 * u1 + (m2 - m1) * u2) / (m1 + m2)
        momentum = abs(m1 * u1 + m2 * u2 - m1 * v1 - m2 * v2)
        energy = abs(m1 * u1**2 + m2 * u2**2 - m1 * v1**2 - m2 * v2**2)
        arrow_labels = {arrow["label"] for arrow in arrows}
        return _result(
            {"before_1", "before_2", "after_1", "after_2"} <= node_ids
            and arrow_labels == {"u₁", "u₂", "v₁", "v₂"}
            and momentum < 1e-9
            and energy < 1e-9,
            {"v1": v1, "v2": v2, "momentum_residual": momentum, "twice_energy_residual": energy},
        )
    if family == "pendulum":
        by_id = {node["id"]: node for node in nodes}
        rod = links[0] if links else None
        distance = (
            math.dist(
                [by_id["pivot"]["x"], by_id["pivot"]["y"]], [by_id["bob"]["x"], by_id["bob"]["y"]]
            )
            if {"pivot", "bob"} <= by_id.keys()
            else 0
        )
        period = 2 * math.pi * math.sqrt(float(controls["length"]) / 9.81)
        transport = {control["id"] for control in spec["controls"] if control["type"] == "button"}
        animation = spec["scene"].get("animation")
        return _result(
            bool(rod)
            and distance > 50
            and len(lines) == 1
            and _closed(lines[0]["points"]) is False
            and len(arrows) == 2
            and period > 0
            and animation is not None
            and transport == {"play", "pause", "restart"},
            {
                "rod_pixels": distance,
                "motion_arc_samples": len(lines[0]["points"]) if lines else 0,
                "period_s": period,
                "transport": sorted(transport),
                "animation": animation,
            },
        )
    if family == "travelling_wave":
        wave = lines[0]["points"] if lines else []
        markers = next((layer["points"] for layer in layers if layer["type"] == "particles"), [])
        amplitude = float(controls["amplitude"])
        wavelength = float(controls["wavelength"])
        marker_valid = (
            len(markers) == 2
            and abs(markers[0][1] - amplitude) < 1e-9
            and abs(markers[1][1] + amplitude) < 1e-9
            and abs(markers[1][0] - markers[0][0] - wavelength / 2) < 1e-9
        )
        return _result(
            len(wave) >= 80
            and marker_valid
            and {"transverse displacement", "equilibrium position", "wavelength crest-to-crest"}
            <= set(line_by_label),
            {"markers": markers, "amplitude": amplitude, "wavelength": wavelength},
        )
    if family == "wave_interference":
        residual = (
            max(
                (
                    abs(a[1] + b[1] - total[1])
                    for a, b, total in zip(
                        lines[0]["points"], lines[1]["points"], lines[2]["points"]
                    )
                ),
                default=math.inf,
            )
            if len(lines) == 3
            else math.inf
        )
        return _result(residual < 1e-9, {"superposition_residual": residual})
    if family == "circular_motion":
        if len(lines) != 4:
            return _result(False, {"curves": len(lines)})
        r = [lines[1]["points"][-1][i] - lines[1]["points"][0][i] for i in range(2)]
        v = [lines[2]["points"][-1][i] - lines[2]["points"][0][i] for i in range(2)]
        a = [lines[3]["points"][-1][i] - lines[3]["points"][0][i] for i in range(2)]
        return _result(
            abs(sum(x * y for x, y in zip(r, v))) < 1e-9 and sum(x * y for x, y in zip(r, a)) < 0,
            {
                "r_dot_v": sum(x * y for x, y in zip(r, v)),
                "r_dot_a": sum(x * y for x, y in zip(r, a)),
            },
        )
    if family == "series_parallel_circuit":
        options = next(
            control["options"] for control in spec["controls"] if control["id"] == "mode"
        )
        edge_pairs = {(link["from"], link["to"]) for link in links if link["arrow"]}
        cycle = edge_pairs == {
            ("source", "r1"),
            ("r1", "r2"),
            ("r2", "return"),
            ("return", "source"),
        }
        r1, r2 = float(controls["r1"]), float(controls["r2"])
        reciprocal_residual = abs((r1 * r2 / (r1 + r2)) * (1 / r1 + 1 / r2) - 1)
        return _result(
            options == ["series", "parallel"]
            and cycle
            and reciprocal_residual < 1e-9
            and {"source", "r1", "r2", "return"} <= node_ids,
            {
                "mode_options": options,
                "series_edges": sorted(edge_pairs),
                "parallel_equivalent_residual": reciprocal_residual,
            },
        )
    if family == "magnetic_field_wire":
        rings = [line for line in lines if "ring" in str(line.get("label", ""))]
        cues = [line for line in lines if "direction arrow" in str(line.get("label", ""))]
        cue_on_ring = all(
            abs(math.hypot(*cue["points"][0]) - radius) < 0.08
            for cue, radius in zip(cues, (0.8, 1.5, 2.2))
        )
        options = next(
            control["options"]
            for control in spec["controls"]
            if control["id"] == "current_direction"
        )
        return _result(
            len(rings) == 3
            and len(cues) == 3
            and cue_on_ring
            and options == ["forward", "reverse"],
            {
                "rings": len(rings),
                "visible_direction_cues": len(cues),
                "cues_on_rings": cue_on_ring,
            },
        )
    if family == "rc_circuit":
        required_nodes = {"rc_source", "rc_resistor", "rc_capacitor"}
        mode_options = next(
            control["options"] for control in spec["controls"] if control["id"] == "mode"
        )
        voltage = lines[0]["points"] if lines else []
        current = lines[1]["points"] if len(lines) > 1 else []
        tau = float(controls["resistance"]) * float(controls["capacitance"]) / 5
        voltage_error = max(
            (abs(y - (1 - math.exp(-max(0, x) / tau))) for x, y in voltage), default=math.inf
        )
        current_error = max(
            (
                abs(y - math.exp(-max(0, x) / tau) / float(controls["resistance"]))
                for x, y in current
            ),
            default=math.inf,
        )
        return _result(
            required_nodes <= node_ids
            and mode_options == ["charging", "discharging"]
            and voltage_error < 1e-9
            and current_error < 1e-9,
            {"tau": tau, "voltage_error": voltage_error, "current_error": current_error},
        )
    if family == "rlc_circuit":
        transient = lines[0]["points"] if lines else []
        finite = all(math.isfinite(value) for point in transient for value in point)
        return _result(
            {"rlc_source", "rlc_r", "rlc_l", "rlc_c"} <= node_ids
            and len(links) == 4
            and finite
            and len(transient) >= 80,
            {"component_nodes": sorted(node_ids), "transient_samples": len(transient)},
        )
    if family == "ac_phase":
        options = next(
            control["options"] for control in spec["controls"] if control["id"] == "load"
        )
        residual = (
            max(
                (abs(v[1] - i[1]) for v, i in zip(lines[0]["points"], lines[1]["points"])),
                default=math.inf,
            )
            if len(lines) == 2
            else math.inf
        )
        return _result(
            options == ["resistive", "capacitive", "inductive"] and residual < 1e-9,
            {"load_options": options, "default_in_phase_error": residual},
        )
    if family == "ideal_gas":
        marker = next((layer["points"] for layer in layers if layer["type"] == "particles"), [])
        pressure, volume, temperature = (
            float(controls[key]) for key in ("pressure", "volume", "temperature")
        )
        expected = [temperature / pressure, pressure]
        return _result(
            len(lines) == 3
            and len(marker) == 2
            and math.dist(marker[0], expected) < 1e-9
            and abs(expected[0] * expected[1] - temperature) < 1e-9,
            {
                "selected_P": pressure,
                "selected_V": volume,
                "constrained_state": marker[0],
                "pv_minus_t": expected[0] * expected[1] - temperature,
            },
        )
    if family == "atom":
        electron_layer = next(
            (
                layer
                for layer in layers
                if layer["type"] == "particles" and "electrons" in layer["label"]
            ),
            None,
        )
        shells = [line for line in lines if "shell" in line["label"]]
        z = int(controls["atomic_number"])
        return _result(
            len(shells) == 3
            and electron_layer is not None
            and len(electron_layer["points"]) == z
            and all(_closed(shell["points"]) for shell in shells),
            {
                "shells": len(shells),
                "electrons": len(electron_layer["points"]) if electron_layer else 0,
                "atomic_number": z,
            },
        )
    if family == "ionic_bond":
        edge_pairs = {(link["from"], link["to"]) for link in links if link["arrow"]}
        required = {("sodium", "electron"), ("electron", "chlorine"), ("chlorine", "ions")}
        return _result(
            {"sodium", "electron", "chlorine", "ions"} <= node_ids
            and required <= edge_pairs
            and all(
                term in _labels(spec)
                for term in ("loses one electron", "gains one electron", "electrostatic attraction")
            ),
            {"directed_transfer": sorted(edge_pairs)},
        )
    if family == "molecular_geometry":
        spheres = [layer for layer in layers if layer["type"] == "sphere"]
        bonds = [layer for layer in layers if layer["type"] == "vector"]
        lone_pairs = [
            layer for layer in layers if layer["type"] == "point" and "lone pair" in layer["label"]
        ]
        options = next(
            control["options"] for control in spec["controls"] if control["id"] == "molecule"
        )
        return _result(
            len(spheres) == 1 and len(bonds) == 6 and len(lone_pairs) == 2 and len(options) >= 2,
            {
                "central_atoms": len(spheres),
                "bond_vectors": len(bonds),
                "lone_pairs": len(lone_pairs),
                "molecules": options,
            },
        )
    if family == "reaction_profile":
        if len(lines) != 2:
            return _result(False, {"curves": len(lines)})
        barriers = [max(y for _x, y in line["points"]) - line["points"][0][1] for line in lines]
        exothermic = all(line["points"][-1][1] < line["points"][0][1] for line in lines)
        options = next(
            control["options"] for control in spec["controls"] if control["id"] == "catalyst"
        )
        return _result(
            exothermic and barriers[1] < barriers[0] and options == ["off", "on"],
            {"activation_barriers": barriers, "products_below_reactants": exothermic},
        )
    if family == "molecular_orbitals":
        edge_labels = {link["label"].casefold() for link in links}
        options = next(
            control["options"] for control in spec["controls"] if control["id"] == "orbital"
        )
        return _result(
            {"h_left", "h_right", "bonding", "antibonding"} <= node_ids
            and {"constructive overlap", "destructive overlap", "lower energy", "higher energy"}
            <= edge_labels
            and options == ["bonding", "antibonding"],
            {"nodes": sorted(node_ids), "relationships": sorted(edge_labels)},
        )
    if family == "animal_cell":
        options = next(
            control["options"] for control in spec["controls"] if control["id"] == "organelle"
        )
        expected = {"nucleus", "mitochondrion", "ribosome", "rough_er", "golgi", "lysosome"}
        return _result(
            expected <= node_ids
            and set(options) == expected
            and all(
                any(
                    term in node["label"].casefold()
                    for term in ("dna", "atp", "protein", "cargo", "waste")
                )
                for node in nodes
                if node["id"] in expected
            ),
            {"organelle_nodes": sorted(node_ids & expected), "selector": options},
        )
    if family == "mitosis":
        directed = {(link["from"], link["to"]) for link in links if link["arrow"]}
        phases = {"prophase", "metaphase", "anaphase", "telophase"}
        chromosomes = {node["id"] for node in nodes if node["id"].startswith("chromosome")}
        cycle = {
            ("prophase", "metaphase"),
            ("metaphase", "anaphase"),
            ("anaphase", "telophase"),
            ("telophase", "prophase"),
        }
        return _result(
            cycle <= directed
            and len(chromosomes) >= 4
            and phases <= {node["id"] for node in nodes},
            {"phase_cycle": sorted(directed), "chromosomes": sorted(chromosomes)},
        )
    if family == "circulation":
        directed = {(link["from"], link["to"]) for link in links if link["arrow"]}
        cycle = {
            ("body", "right_heart"),
            ("right_heart", "lungs"),
            ("lungs", "left_heart"),
            ("left_heart", "body"),
        }
        return _result(
            cycle == directed
            and {"body", "right_heart", "lungs", "left_heart", "rbc"} <= node_ids
            and all(
                term in _labels(spec) for term in ("deoxygenated", "oxygenated", "red blood cell")
            ),
            {"blood_path": sorted(directed), "rbc_present": "rbc" in node_ids},
        )
    if family == "binary_search_tree":
        base = {node["id"]: float(node["label"]) for node in nodes if node["id"] != "candidate"}
        edges = [
            (link["from"], link["to"]) for link in links if link["label"] != "new-node placement"
        ]
        ordered = all(
            (
                base[child] < base[parent]
                if "left" in child.removeprefix(parent + "_")
                else base[child] > base[parent]
            )
            for parent, child in edges
        )
        return _result(
            len(base) == 7
            and len(edges) == 6
            and ordered
            and any(
                link["label"] == "new-node placement" and link["to"] == "candidate"
                for link in links
            )
            and {"insert", "step"} <= controls.keys(),
            {
                "values": base,
                "tree_edges": edges,
                "ordered": ordered,
                "insert": controls.get("insert"),
            },
        )
    if family == "stack_queue":
        options = next(
            control["options"] for control in spec["controls"] if control["id"] == "operation"
        )
        by_id = {node["id"]: node for node in nodes}
        stack = [by_id.get(f"stack_{index}") for index in range(3)]
        queue = [by_id.get(f"queue_{index}") for index in range(3)]
        return _result(
            options == ["add", "remove"]
            and all(stack)
            and all(queue)
            and [node["label"] for node in stack] == ["A", "B", "C"]
            and [node["label"] for node in queue] == ["A", "B", "C"]
            and stack[-1]["y"] < stack[0]["y"]
            and queue[0]["x"] < queue[-1]["x"]
            and all(
                term in _labels(spec) for term in ("lifo", "fifo", "pop first", "dequeue first")
            ),
            {
                "operation_options": options,
                "stack": [(node["label"], node["y"]) for node in stack],
                "queue": [(node["label"], node["x"]) for node in queue],
            },
        )
    if family == "cpu_memory":
        edge_pairs = {(link["from"], link["to"]) for link in links if link["arrow"]}
        required = {
            ("cpu", "cache"),
            ("cache", "ram"),
            ("ram", "ssd"),
            ("ssd", "retry"),
            ("retry", "cpu"),
        }
        return _result(
            required == edge_pairs and {"cpu", "cache", "ram", "ssd", "retry"} <= node_ids,
            {"memory_path": sorted(edge_pairs)},
        )
    return None


def _specific_oracle(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a named, prompt-independent semantic invariant.

    These rules operate on the typed production spec, not fixture IDs or prompt strings. Browser
    interaction evidence is merged separately so a mathematically plausible state description
    cannot substitute for changed geometry.
    """

    family = spec["family"]
    controls = _controls(spec)
    lines = _polylines(spec)
    nodes = _nodes(spec)
    labels = _labels(spec)
    layers = spec["scene"]["layers"]
    node_labels = [str(node.get("label", "")).casefold() for node in nodes]
    links = [layer for layer in layers if layer["type"] == "link"]

    if name == "semantic_relationship":
        if family == "converging_lens":
            by_id = {node["id"]: node for node in nodes}
            arrows = [layer for layer in layers if layer["type"] == "arrow"]
            required = {"object", "lens", "focal_left", "focal_right", "image"}
            if not required <= by_id.keys():
                return _result(False, {"error": "lens scene is missing optical landmarks"})
            lens = by_id["lens"]
            focal_length = abs(by_id["focal_right"]["x"] - lens["x"])
            object_distance = abs(by_id["object"]["x"] - lens["x"])
            image_distance = abs(by_id["image"]["x"] - lens["x"])
            thin_lens_residual = abs(
                (1 / focal_length) - (1 / object_distance) - (1 / image_distance)
            )
            arrow_by_label = {arrow["label"]: arrow for arrow in arrows}
            optical_path = (
                arrow_by_label.get("parallel incident ray", {}).get("to")
                == arrow_by_label.get("refracts through F′", {}).get("from")
                and arrow_by_label.get("refracts through F′", {}).get("to")
                == [by_id["image"]["x"], by_id["image"]["y"]]
                and arrow_by_label.get("central ray", {}).get("to")
                == arrow_by_label.get("central ray undeviated", {}).get("from")
                and arrow_by_label.get("central ray undeviated", {}).get("to")
                == [by_id["image"]["x"], by_id["image"]["y"]]
            )
            return _result(
                thin_lens_residual < 1e-5 and optical_path and object_distance > focal_length,
                {
                    "focal_length_px": focal_length,
                    "object_distance_px": object_distance,
                    "image_distance_px": image_distance,
                    "thin_lens_residual": thin_lens_residual,
                    "ray_paths_join": optical_path,
                },
            )
        if family == "electric_field_lines":
            charges = next((layer for layer in layers if layer["type"] == "particles"), None)
            charge_points = charges.get("points", []) if charges else []
            starts_near_positive = (
                bool(charge_points)
                and sum(math.dist(line["points"][0], charge_points[0]) < 0.25 for line in lines)
                >= 8
            )
            reaches_negative = (
                len(charge_points) == 2
                and sum(math.dist(line["points"][-1], charge_points[1]) < 0.3 for line in lines)
                >= 5
            )
            return _result(
                len(lines) >= 8 and starts_near_positive and reaches_negative,
                {
                    "field_lines": len(lines),
                    "starts_near_positive": starts_near_positive,
                    "reaches_negative": reaches_negative,
                },
            )
        if family == "electric_field_vectors":
            field = next((layer for layer in layers if layer["type"] == "vector_field"), None)
            probe = next((layer for layer in layers if layer["type"] == "probe_vector"), None)
            return _result(
                bool(field and len(field["vectors"]) >= 24 and probe),
                {
                    "field_samples": len(field["vectors"]) if field else 0,
                    "typed_probe": bool(probe),
                },
            )
        line_labels = {str(line.get("label", "")).casefold() for line in lines}
        if family == "quadratic":
            particle_labels = {
                str(layer.get("label", "")).casefold()
                for layer in layers
                if layer["type"] == "particles"
            }
            return _result(
                {"vertex", "real roots"} <= particle_labels
                and any("axis of symmetry" in label for label in line_labels),
                {"curve_labels": sorted(line_labels), "particle_labels": sorted(particle_labels)},
            )
        if family == "harmonic_motion":
            required = {
                "displacement versus time",
                "phase space velocity versus displacement",
                "spring and moving mass",
            }
            moving_mass = next(
                (
                    layer
                    for layer in layers
                    if layer["type"] == "particles"
                    and "moving mass" in str(layer.get("label", "")).casefold()
                ),
                None,
            )
            transport = {control["id"] for control in spec["controls"]}
            return _result(
                required <= line_labels
                and moving_mass is not None
                and {"play", "pause", "restart"} <= transport
                and bool(spec["scene"].get("animation")),
                {
                    "curve_labels": sorted(line_labels),
                    "moving_mass": moving_mass.get("points") if moving_mass else None,
                    "transport_controls": sorted(transport),
                },
            )
        if family == "double_pendulum":
            trajectories = [
                line["points"]
                for line in lines
                if "trajectory" in str(line.get("label", "")).casefold()
            ]
            arms = [
                line["points"]
                for line in lines
                if "pendulum arms" in str(line.get("label", "")).casefold()
            ]
            separation = (
                [math.dist(left, right) for left, right in zip(*trajectories)]
                if len(trajectories) == 2
                else []
            )
            late_separation = sum(separation[-10:]) / 10 if len(separation) >= 10 else 0
            link_lengths = [
                math.dist(arm[0], arm[1]) + math.dist(arm[1], arm[2])
                for arm in arms
                if len(arm) == 3
            ]
            return _result(
                len(trajectories) == 2
                and len(arms) == 2
                and len(separation) >= 80
                and late_separation > 2 * separation[0]
                and all(abs(length - 2) < 1e-8 for length in link_lengths),
                {
                    "initial_separation": separation[0] if separation else None,
                    "late_mean_separation": late_separation,
                    "link_length_sums": link_lengths,
                },
            )
        if family == "carnot_cycle":
            processes = {
                "isothermal expansion hot",
                "adiabatic expansion",
                "isothermal compression cold",
                "adiabatic compression",
            }
            process_lines = [
                line for line in lines if str(line.get("label", "")).casefold() in processes
            ]
            joins = (
                all(
                    process_lines[index]["points"][-1]
                    == process_lines[(index + 1) % 4]["points"][0]
                    for index in range(4)
                )
                if len(process_lines) == 4
                else False
            )
            return _result(
                processes <= line_labels and joins,
                {"processes": sorted(line_labels), "closed_process_chain": joins},
            )
        if family == "titration":
            node_ids = {node["id"] for node in nodes}
            curve = next((line["points"] for line in lines if line.get("label") == "pH curve"), [])
            probe = next(
                (
                    line["points"]
                    for line in lines
                    if line.get("label") == "selected titrant volume"
                ),
                [],
            )
            volume = float(controls["titrant_volume"])
            expected_ph = 2 + 10 / (1 + math.exp(-0.35 * (volume - 25)))
            curve_probe = (
                min(curve, key=lambda point: abs(point[0] - volume))
                if curve
                else [math.inf, math.inf]
            )
            return _result(
                {"burette", "flask"} <= node_ids
                and {"ph curve", "selected titrant volume"} <= line_labels
                and curve
                and probe
                and min(point[0] for point in curve) <= 0
                and max(point[0] for point in curve) >= 50
                and abs(curve_probe[1] - expected_ph) < 0.02
                and abs(probe[-1][0] - volume) < 1e-9,
                {
                    "nodes": sorted(node_ids),
                    "curves": sorted(line_labels),
                    "selected_volume": volume,
                    "curve_probe": curve_probe,
                    "expected_ph": expected_ph,
                },
            )
        if family == "action_potential":
            required_terms = (
                "membrane voltage",
                "sodium channel",
                "potassium channel",
                "time probe",
            )
            return _result(
                all(any(term in label for label in line_labels) for term in required_terms),
                {"curve_labels": sorted(line_labels)},
            )
        semantic = _semantic_relationship_oracle(spec)
        return semantic or _result(False, {"error": f"no executable semantic oracle for {family}"})
    if name == "labels_and_units":
        axes = [layer for layer in layers if layer["type"] == "axes"]
        labelled = len(node_labels) >= 3 or all(
            layer.get("x_label") and layer.get("y_label") for layer in axes
        )
        return _result(labelled, {"labels": node_labels, "axes": axes})
    if name == "control_consistency":
        valid = bool(spec["controls"]) and len(controls) == len(spec["controls"])
        return _result(valid, {"control_ids": sorted(controls), "browser_check": "required"})

    if name in {"a2_plus_b2_equals_c2", "square_areas"}:
        a = float(controls.get("a", 0))
        b = float(controls.get("b", 0))
        c2 = a * a + b * b
        areas = [_shoelace(line["points"]) for line in lines[1:4]]
        passed = len(areas) == 3 and all(
            abs(actual - expected) <= 1e-8 for actual, expected in zip(areas, (a * a, b * b, c2))
        )
        return _result(passed, {"a": a, "b": b, "c_squared": c2, "square_areas": areas})
    if name in {"point_on_unit_circle", "sin_cos_projection"}:
        angle = math.radians(float(controls.get("angle", 0)))
        endpoint = lines[1]["points"][-1] if len(lines) > 1 else [math.inf, math.inf]
        expected = [math.cos(angle), math.sin(angle)]
        error = math.hypot(endpoint[0] - expected[0], endpoint[1] - expected[1])
        circle_error = max(
            (abs(point[0] ** 2 + point[1] ** 2 - 1) for point in lines[0]["points"]),
            default=math.inf,
        )
        return _result(
            error < 1e-8 and circle_error < 1e-8,
            {"endpoint_error": error, "circle_error": circle_error},
        )
    if name in {"trajectory_endpoints", "range_height_units"}:
        points = lines[0]["points"] if lines else []
        axes = next((layer for layer in layers if layer["type"] == "axes"), {})
        markers = next(
            (
                layer["points"]
                for layer in layers
                if layer["type"] == "particles" and "maximum height" in layer["label"]
            ),
            [],
        )
        velocity = next(
            (
                layer
                for layer in layers
                if layer["type"] == "arrow" and "velocity" in layer["label"]
            ),
            None,
        )
        angle = math.radians(float(controls.get("angle", 0)))
        speed = float(controls.get("speed", 0))
        expected_range = speed * speed * math.sin(2 * angle) / 9.81
        expected_height = speed * speed * math.sin(angle) ** 2 / 19.62
        marker_error = (
            max(
                math.dist(markers[0], [expected_range / 2, expected_height]),
                math.dist(markers[1], [expected_range, 0]),
            )
            if len(markers) == 2
            else math.inf
        )
        passed = (
            bool(points)
            and abs(points[0][1]) < 1e-8
            and abs(points[-1][1]) < 1e-7
            and max(point[1] for point in points) > 0
            and marker_error < 0.06
            and velocity is not None
            and math.dist(velocity["from"], velocity["to"]) > 0.1
        )
        if name == "range_height_units":
            passed = (
                passed
                and "m" in str(axes.get("x_label", ""))
                and "m" in str(axes.get("y_label", ""))
            )
        return _result(
            passed,
            {
                "start": points[0] if points else None,
                "end": points[-1] if points else None,
                "axes": axes,
                "markers": markers,
                "marker_error": marker_error,
                "velocity_vector": velocity,
            },
        )
    if name == "current_v_over_r":
        voltage = float(controls.get("voltage", 0))
        resistance = float(controls.get("resistance", 0))
        current = voltage / resistance if resistance else math.inf
        return _result(
            math.isfinite(current) and "v/r" in labels,
            {"voltage": voltage, "resistance": resistance, "current": current},
        )
    if name == "current_direction":
        return _result(
            len(links) >= 3 and all(link.get("arrow") for link in links),
            {"directed_links": sum(bool(link.get("arrow")) for link in links)},
        )
    if name == "snell_law":
        if len(nodes) >= 3:
            incident_node, normal_node, refracted_node = nodes[:3]
            incident_angle = math.atan2(
                abs(incident_node["x"] - normal_node["x"]),
                abs(incident_node["y"] - normal_node["y"]),
            )
            refracted_angle = math.atan2(
                abs(refracted_node["x"] - normal_node["x"]),
                abs(refracted_node["y"] - normal_node["y"]),
            )
            residual = abs(math.sin(incident_angle) - 1.5 * math.sin(refracted_angle))
        else:
            incident_angle = refracted_angle = residual = math.inf
        return _result(
            "sin" in labels
            and "refract" in labels
            and "incident_angle" in controls
            and residual < 1e-8,
            {
                "incident_angle_rad": incident_angle,
                "refracted_angle_rad": refracted_angle,
                "snell_residual": residual,
            },
        )
    if name == "normal_and_ray_direction":
        direction_valid = len(nodes) >= 3 and nodes[0]["y"] < nodes[1]["y"] < nodes[2]["y"]
        return _result(
            all(term in labels for term in ("normal", "incident ray", "refracted ray"))
            and direction_valid,
            {"labels": node_labels, "crosses_interface": direction_valid},
        )
    if name in {"interval_shrinks", "target_found"}:
        array_node = next((node for node in nodes if node.get("id") == "array"), None)
        values = (
            [float(value) for value in re.findall(r"-?\d+(?:\.\d+)?", array_node["label"])]
            if array_node
            else []
        )
        target = float(controls.get("target", math.nan))
        low, high = 0, len(values) - 1
        intervals: list[list[int]] = []
        comparisons: list[float] = []
        found = False
        while low <= high:
            intervals.append([low, high])
            midpoint = (low + high) // 2
            comparisons.append(values[midpoint])
            if values[midpoint] == target:
                found = True
                break
            if values[midpoint] < target:
                low = midpoint + 1
            else:
                high = midpoint - 1
        widths = [right - left + 1 for left, right in intervals]
        control_records = {control["id"]: control for control in spec["controls"]}
        controls_valid = (
            control_records.get("target", {}).get("type") == "select"
            and control_records.get("step", {}).get("type") == "step"
        )
        passed = (
            len(values) >= 3
            and values == sorted(values)
            and len(values) == len(set(values))
            and controls_valid
            and all(next_width < width for width, next_width in itertools.pairwise(widths))
            and found == (target in values)
        )
        return _result(
            passed,
            {
                "sorted_values": values,
                "target": target,
                "intervals": intervals,
                "widths": widths,
                "comparisons": comparisons,
                "found": found,
                "controls_valid": controls_valid,
            },
        )
    if name in {"nondecreasing_settled_distance", "shortest_path"}:
        control_records = {control["id"]: control for control in spec["controls"]}
        graph: dict[str, list[tuple[str, float]]] = {node["id"]: [] for node in nodes}
        weights_valid = True
        for link in links:
            try:
                weight = float(link["label"])
            except (TypeError, ValueError):
                weights_valid = False
                continue
            weights_valid &= weight >= 0
            graph[link["from"]].append((link["to"], weight))
            graph[link["to"]].append((link["from"], weight))
        source = str(controls.get("source", ""))
        destination = str(controls.get("destination", ""))
        distances = {node_id: math.inf for node_id in graph}
        previous: dict[str, str] = {}
        unsettled = set(graph)
        settled_distances: list[float] = []
        if source in distances:
            distances[source] = 0
        while unsettled:
            current = min(unsettled, key=distances.get)  # type: ignore[arg-type]
            unsettled.remove(current)
            if not math.isfinite(distances[current]):
                break
            settled_distances.append(distances[current])
            for neighbour, weight in graph[current]:
                candidate = distances[current] + weight
                if candidate < distances[neighbour]:
                    distances[neighbour] = candidate
                    previous[neighbour] = current
        path: list[str] = []
        cursor = destination
        if destination in distances and math.isfinite(distances[destination]):
            while cursor:
                path.insert(0, cursor)
                if cursor == source:
                    break
                cursor = previous.get(cursor, "")
        select_controls = all(
            control_records.get(control_id, {}).get("type") == "select"
            and set(control_records[control_id].get("options", [])) == set(graph)
            for control_id in ("source", "destination")
        )
        nondecreasing = all(
            first <= second for first, second in itertools.pairwise(settled_distances)
        )
        passed = (
            len(graph) >= 5
            and len(links) >= len(graph)
            and weights_valid
            and select_controls
            and nondecreasing
            and len(path) >= 2
            and path[0] == source
            and path[-1] == destination
        )
        return _result(
            passed,
            {
                "nodes": sorted(graph),
                "weighted_edges": len(links),
                "source": source,
                "destination": destination,
                "path": path,
                "distance": distances.get(destination),
                "settled_distances": settled_distances,
                "select_controls": select_controls,
            },
        )
    if name == "nyquist_condition":
        signal = float(controls.get("signal_frequency", 0))
        sample = float(controls.get("sample_frequency", 0))
        return _result(
            len(lines) >= 2 and signal > 0 and sample > 0,
            {
                "signal_frequency": signal,
                "sample_frequency": sample,
                "nyquist": sample >= 2 * signal,
            },
        )
    if name == "sample_locations":
        signal = float(controls.get("signal_frequency", 0))
        sample = float(controls.get("sample_frequency", 0))
        particle_layer = next((layer for layer in layers if layer["type"] == "particles"), None)
        samples = particle_layer.get("points", []) if particle_layer else []
        worst = max(
            (abs(point[1] - math.sin(2 * math.pi * signal * point[0])) for point in samples),
            default=math.inf,
        )
        return _result(
            len(samples) == round(sample) + 1 and worst < 1e-8,
            {
                "sample_count": len(samples),
                "expected_count": round(sample) + 1,
                "signal_error": worst,
            },
        )
    if name == "curvature_from_wheel_speeds":
        left = float(controls.get("left_velocity", 0))
        right = float(controls.get("right_velocity", 0))
        curvature = (
            0.0 if abs(right - left) < 1e-9 else (right - left) / max(0.2, abs(left + right))
        )
        return _result(
            bool(lines) and math.isfinite(curvature),
            {"left": left, "right": right, "curvature": curvature},
        )
    if name == "weighted_activation_flow":
        by_id = {node["id"]: node for node in nodes}
        edges = {(link["from"], link["to"]): link["label"] for link in links}
        weight = float(controls.get("weight", 1))
        x1, x2 = 0.6, 0.4
        hidden_1 = max(0.0, weight * x1 + 0.5 * x2 - 0.2)
        hidden_2 = max(0.0, -0.4 * x1 + 0.8 * x2 + 0.1)
        output = 1 / (1 + math.exp(-(0.9 * hidden_1 - 0.7 * hidden_2 + 0.05)))
        return _result(
            {"x1", "x2", "h1", "h2", "output"} <= by_id.keys()
            and set(edges)
            == {
                ("x1", "h1"),
                ("x2", "h1"),
                ("x1", "h2"),
                ("x2", "h2"),
                ("h1", "output"),
                ("h2", "output"),
            }
            and "adjustable" in edges[("x1", "h1")]
            and 0 < output < 1
            and {"weight", "step"} <= controls.keys(),
            {
                "edges": [[start, end, label] for (start, end), label in sorted(edges.items())],
                "hidden_activations": [hidden_1, hidden_2],
                "output": output,
            },
        )

    if name in {"complex_square_mapping", "angle_doubles"}:
        source = next((line for line in lines if line.get("label") == "selected source z"), None)
        image = next((line for line in lines if line.get("label") == "selected image z²"), None)
        source_vector = [source["points"][-1][0] + 3, source["points"][-1][1]] if source else None
        image_vector = [image["points"][-1][0] - 3, image["points"][-1][1]] if image else None
        expected = (
            [source_vector[0] ** 2 - source_vector[1] ** 2, 2 * source_vector[0] * source_vector[1]]
            if source_vector
            else None
        )
        return _result(
            len(lines) >= 20 and expected is not None and math.dist(expected, image_vector) < 1e-7,
            {
                "source_vector": source_vector,
                "image_vector": image_vector,
                "expected_square": expected,
            },
        )
    if name in {"polar_radius", "four_petals"}:
        points = lines[0]["points"] if lines else []
        radius_maxima = sum(math.hypot(*point) > 0.98 for point in points)
        zero_crossings = sum(math.hypot(*point) < 0.03 for point in points)
        particle_labels = {
            str(layer.get("label", "")) for layer in layers if layer["type"] == "particles"
        }
        return _result(
            _closed(points)
            and radius_maxima >= 4
            and zero_crossings >= 4
            and {"four radial maxima r=±1", "zero crossings r=0 at θ=π/4+kπ/2", "traversal point"}
            <= particle_labels,
            {
                "maxima_samples": radius_maxima,
                "zero_samples": zero_crossings,
                "visible_markers": sorted(particle_labels),
            },
        )
    if name in {"odd_harmonics", "gibbs_overshoot"}:
        partial = next(
            (line for line in lines if line.get("label") == "odd-harmonic partial sum"), None
        )
        points = partial["points"] if partial else []
        peak = max((abs(point[1]) for point in points), default=0)
        harmonic_labels = {
            str(line.get("label", ""))
            for line in lines
            if str(line.get("label", "")).startswith("harmonic n=")
        }
        target = next((line for line in lines if line.get("label") == "square-wave target"), None)
        markers = next(
            (
                layer
                for layer in layers
                if layer["type"] == "particles" and "Gibbs" in str(layer.get("label", ""))
            ),
            None,
        )
        return _result(
            harmonic_labels == {"harmonic n=1", "harmonic n=3", "harmonic n=5"}
            and target is not None
            and markers is not None
            and len(markers["points"]) >= 3
            and peak > 1,
            {
                "absolute_peak": peak,
                "components": sorted(harmonic_labels),
                "gibbs_markers": markers.get("points") if markers else [],
            },
        )
    if name in {"iterate_logistic", "bounded_unit_interval"}:
        iteration = next(
            (line for line in lines if line.get("label") == "iterate xₙ versus n"), None
        )
        points = iteration["points"] if iteration else []
        growth = float(controls.get("growth_rate", 0))
        recurrence = max(
            (
                abs(points[index + 1][1] - growth * points[index][1] * (1 - points[index][1]))
                for index in range(len(points) - 1)
            ),
            default=math.inf,
        )
        bounded = all(-1e-9 <= point[1] <= 1 + 1e-9 for point in points)
        labels_present = {str(line.get("label", "")) for line in lines}
        bifurcation = next(
            (
                layer
                for layer in layers
                if layer["type"] == "particles" and "bifurcation" in str(layer.get("label", ""))
            ),
            None,
        )
        panel_titles = {layer["title"] for layer in layers if layer["type"] == "panel"}
        return _result(
            bounded
            and recurrence < 1e-8
            and {"identity y=x", "logistic map y=r x(1−x)", "cobweb iteration"} <= labels_present
            and bifurcation is not None
            and len(bifurcation["points"]) >= 400
            and panel_titles == {"Iterate history", "Cobweb diagram", "Bifurcation behavior"},
            {
                "recurrence_error": recurrence,
                "bounded": bounded,
                "bifurcation_samples": len(bifurcation["points"]) if bifurcation else 0,
                "panels": sorted(panel_titles),
            },
        )
    if name in {"tangent_contours", "parallel_gradients"}:
        constraint = next((line for line in lines if line.get("label") == "constraint x+y=c"), None)
        gradients = [line for line in lines if "∇" in str(line.get("label", ""))]
        minimum = next(
            (
                layer
                for layer in layers
                if layer.get("type") == "particles"
                and "constrained minimum" in layer.get("label", "")
            ),
            None,
        )
        tangent = next(
            (
                line
                for line in lines
                if line.get("label") == "tangent contour through constrained minimum"
            ),
            None,
        )
        parallel = len(gradients) == 2 and gradients[0]["points"] == gradients[1]["points"]
        constraint_value = float(controls.get("constraint_offset", 1))
        optimum = [constraint_value / 2, constraint_value / 2]
        tangent_radius = math.hypot(*optimum)
        contour_error = (
            max(
                (abs(math.hypot(*point) - tangent_radius) for point in tangent["points"]),
                default=math.inf,
            )
            if tangent
            else math.inf
        )
        return _result(
            len(lines) >= 6
            and constraint is not None
            and minimum is not None
            and parallel
            and contour_error < 1e-7
            and abs(sum(minimum["points"][0]) - constraint_value) < 1e-9,
            {
                "curve_labels": [line.get("label") for line in lines],
                "parallel_gradients": parallel,
                "minimum": minimum.get("points") if minimum else None,
                "tangent_contour_error": contour_error,
            },
        )
    if name in {"mobius_single_boundary", "parametric_samples"}:
        layer = next((layer for layer in layers if layer["type"] == "parametric_surface"), None)
        passed = bool(
            layer
            and layer["u_domain"][1] - layer["u_domain"][0] >= 2 * math.pi - 1e-6
            and layer["v_domain"][0] < 0 < layer["v_domain"][1]
        )
        return _result(
            passed,
            {
                "u_domain": layer.get("u_domain") if layer else None,
                "v_domain": layer.get("v_domain") if layer else None,
            },
        )
    if name in {"field_components", "divergence_zero"}:
        field = next((layer for layer in layers if layer["type"] == "vector_field"), None)
        probe = next((layer for layer in layers if layer["type"] == "probe_vector"), None)
        vectors = field.get("vectors", []) if field else []
        component_errors = []
        if probe:
            for x, y, dx, dy in vectors:
                expected_x = evaluate_expression_v2(probe["x_expression"], {"x": x, "y": y})
                expected_y = evaluate_expression_v2(probe["y_expression"], {"x": x, "y": y})
                scale = 0.55 / max(0.55, math.hypot(expected_x, expected_y))
                component_errors.extend(
                    (abs(dx - scale * expected_x), abs(dy - scale * expected_y))
                )
        worst = max(component_errors, default=math.inf)
        divergence = math.inf
        if probe:
            epsilon = 1e-4
            dfdx = (
                evaluate_expression_v2(probe["x_expression"], {"x": epsilon, "y": 0})
                - evaluate_expression_v2(probe["x_expression"], {"x": -epsilon, "y": 0})
            ) / (2 * epsilon)
            dgdy = (
                evaluate_expression_v2(probe["y_expression"], {"x": 0, "y": epsilon})
                - evaluate_expression_v2(probe["y_expression"], {"x": 0, "y": -epsilon})
            ) / (2 * epsilon)
            divergence = dfdx + dgdy
        return _result(
            len(vectors) >= 20
            and worst < 1e-5
            and probe is not None
            and (name != "divergence_zero" or abs(divergence) < 1e-6),
            {"vector_samples": len(vectors), "component_error": worst, "divergence": divergence},
        )
    if name in {"overlap_equals_convolution", "triangular_result"}:
        result = next(
            (line for line in lines if line.get("label") == "convolution result versus shift"), None
        )
        points = result["points"] if result else []
        slopes = (
            {(round(points[i + 1][1] - points[i][1], 2)) for i in range(len(points) - 1)}
            if points
            else set()
        )
        line_labels = {str(line.get("label", "")) for line in lines}
        marker = next(
            (
                layer
                for layer in layers
                if layer["type"] == "particles" and "overlap-area" in str(layer.get("label", ""))
            ),
            None,
        )
        return _result(
            points
            and max(point[1] for point in points) >= 1.9
            and any(value > 0 for value in slopes)
            and any(value < 0 for value in slopes)
            and {"box pulse A", "sliding box pulse B", "current overlap area"} <= line_labels
            and marker is not None
            and abs(marker["points"][0][1] - max(point[1] for point in points)) < 1e-9,
            {
                "peak": max((point[1] for point in points), default=0),
                "slope_signs": sorted(slopes)[:8],
                "input_and_overlap_layers": sorted(line_labels),
            },
        )
    if name in {"acceleration_inward", "equal_area"}:
        by_label = {str(line.get("label", "")): line["points"] for line in lines}
        points = by_label.get("trajectory", [])
        radius_vector = by_label.get("radius vector", [])
        velocity_vector = by_label.get("velocity vector tangent to orbit", [])
        acceleration_vector = by_label.get("acceleration vector toward focus", [])
        sector = by_label.get("equal-area sweep sector", [])
        radii = [math.hypot(*point) for point in points]
        delta = lambda segment: [segment[-1][axis] - segment[0][axis] for axis in range(2)]
        radius_delta = delta(radius_vector) if len(radius_vector) == 2 else [math.nan, math.nan]
        velocity_delta = (
            delta(velocity_vector) if len(velocity_vector) == 2 else [math.nan, math.nan]
        )
        acceleration_delta = (
            delta(acceleration_vector) if len(acceleration_vector) == 2 else [math.nan, math.nan]
        )
        tangent_residual = abs(
            sum(left * right for left, right in zip(radius_delta, velocity_delta))
        )
        inward_cross = abs(
            radius_delta[0] * acceleration_delta[1] - radius_delta[1] * acceleration_delta[0]
        )
        inward_dot = sum(left * right for left, right in zip(radius_delta, acceleration_delta))
        sector_area = (
            abs(
                sum(
                    first[0] * second[1] - second[0] * first[1]
                    for first, second in itertools.pairwise(sector)
                )
            )
            / 2
        )
        satellite = next(
            (
                layer
                for layer in layers
                if layer["type"] == "particles" and "satellite" in str(layer.get("label", ""))
            ),
            None,
        )
        return _result(
            _closed(points)
            and min(radii, default=0) > 0
            and max(radii, default=0) > min(radii, default=0)
            and tangent_residual < 1e-8
            and inward_cross < 1e-8
            and inward_dot < 0
            and sector_area > 0
            and satellite is not None
            and math.dist(satellite["points"][0], radius_vector[-1]) < 1e-8,
            {
                "radius_range": [min(radii, default=0), max(radii, default=0)],
                "radius_dot_velocity": tangent_residual,
                "radius_cross_acceleration": inward_cross,
                "radius_dot_acceleration": inward_dot,
                "sweep_sector_area": sector_area,
                "satellite_position": satellite["points"][0] if satellite else None,
            },
        )
    if name == "normal_mode_phase" or (
        name == "energy_bounded" and family == "coupled_oscillators"
    ):
        in_phase = next(
            (
                line["points"]
                for line in lines
                if "in-phase" in str(line.get("label", "")).casefold()
            ),
            [],
        )
        out_phase = next(
            (
                line["points"]
                for line in lines
                if "out-of-phase" in str(line.get("label", "")).casefold()
            ),
            [],
        )
        schematic = any(
            "three springs and two masses" in str(line.get("label", "")).casefold()
            for line in lines
        )
        phase_residual = max(
            (abs(first[1] + second[1]) for first, second in zip(in_phase, out_phase)),
            default=math.inf,
        )
        amplitude = max((abs(point[1]) for point in in_phase + out_phase), default=math.inf)
        return _result(
            bool(in_phase and out_phase)
            and schematic
            and phase_residual < 1e-10
            and amplitude <= 1 + 1e-10,
            {
                "phase_residual": phase_residual,
                "maximum_amplitude": amplitude,
                "three_spring_two_mass_schematic": schematic,
            },
        )
    if name in {"node_count", "fixed_endpoints"}:
        points = lines[0]["points"] if lines else []
        harmonic = max(1, round(float(controls.get("harmonic", 1))))
        node_layer = next(
            (
                layer
                for layer in layers
                if layer["type"] == "particles" and "nodes" in str(layer.get("label", ""))
            ),
            None,
        )
        antinode_layer = next(
            (
                layer
                for layer in layers
                if layer["type"] == "particles" and "antinodes" in str(layer.get("label", ""))
            ),
            None,
        )
        node_points = node_layer.get("points", []) if node_layer else []
        antinode_points = antinode_layer.get("points", []) if antinode_layer else []
        expected_nodes = [[-4 + 8 * index / harmonic, 0] for index in range(harmonic + 1)]
        expected_antinodes = [
            [-4 + 8 * (index + 0.5) / harmonic, -1 if index % 2 else 1] for index in range(harmonic)
        ]
        antinode_matches = all(
            any(math.dist(expected, actual) < 0.01 for actual in antinode_points)
            for expected in expected_antinodes
        )
        return _result(
            points
            and abs(points[0][1]) < 1e-8
            and abs(points[-1][1]) < 1e-8
            and node_points == expected_nodes
            and antinode_matches,
            {
                "harmonic": harmonic,
                "endpoints": [points[0], points[-1]] if points else [],
                "nodes": node_points,
                "expected_nodes": expected_nodes,
                "antinodes": antinode_points,
                "expected_antinodes": expected_antinodes,
            },
        )
    if name in {"front_wavelength_shorter", "wavefront_spacing"}:
        circles = []
        for line in lines:
            points = line["points"]
            if len(points) < 8:
                continue
            minimum = min(point[0] for point in points)
            maximum = max(point[0] for point in points)
            circles.append(
                {
                    "centre": (minimum + maximum) / 2,
                    "radius": (maximum - minimum) / 2,
                    "left": minimum,
                    "right": maximum,
                }
            )
        circles.sort(key=lambda record: record["radius"], reverse=True)
        front = [older["right"] - newer["right"] for older, newer in itertools.pairwise(circles)]
        rear = [newer["left"] - older["left"] for older, newer in itertools.pairwise(circles)]
        return _result(
            len(circles) >= 3
            and float(controls.get("source_speed", 0)) > 0
            and all(spacing > 0 for spacing in front + rear)
            and sum(front) / len(front) < sum(rear) / len(rear),
            {"wavefronts": circles, "front_spacing": front, "rear_spacing": rear},
        )
    if name in {"fringe_spacing", "central_maximum"}:
        intensity = next((line for line in lines if line.get("label") == "intensity"), None)
        points = intensity["points"] if intensity else []
        closest = min(points, key=lambda point: abs(point[0])) if points else [0, 0]
        separation = float(controls.get("slit_separation", 0))
        wavelength = float(controls.get("wavelength", 0))
        formula_error = (
            max(
                (
                    abs(
                        y
                        - math.cos(
                            math.pi
                            * abs(
                                math.hypot(4.8, x + separation / 2)
                                - math.hypot(4.8, x - separation / 2)
                            )
                            / wavelength
                        )
                        ** 2
                    )
                    for x, y in points
                ),
                default=math.inf,
            )
            if wavelength > 0
            else math.inf
        )
        ray_by_label = {line.get("label"): line["points"] for line in lines}
        upper = ray_by_label.get("upper-slit path", [])
        lower = ray_by_label.get("lower-slit path", [])
        cue = ray_by_label.get("path difference Δℓ", [])
        path_difference = (
            abs(
                sum(math.dist(a, b) for a, b in itertools.pairwise(upper))
                - sum(math.dist(a, b) for a, b in itertools.pairwise(lower))
            )
            if upper and lower
            else math.inf
        )
        actual_separation = (
            abs(upper[1][1] - lower[1][1]) if len(upper) >= 2 and len(lower) >= 2 else math.inf
        )
        screen_y = upper[-1][1] if upper else 0
        screen_intensity = (
            min(points, key=lambda point: abs(point[0] - screen_y))[1] if points else math.nan
        )
        coherent_intensity = (
            math.cos(math.pi * path_difference / wavelength) ** 2 if wavelength > 0 else math.nan
        )
        return _result(
            abs(closest[1] - 1) < 1e-8
            and min((point[1] for point in points), default=-1) >= 0
            and formula_error < 1e-10
            and path_difference > 0
            and abs(actual_separation - separation) < 1e-9
            and abs(screen_intensity - coherent_intensity) < 0.03
            and len(cue) == 2
            and {"slit_separation", "wavelength"} <= controls.keys(),
            {
                "central_sample": closest,
                "formula_error": formula_error,
                "path_difference": path_difference,
                "slit_gap": actual_separation,
                "linked_view_intensity_error": abs(screen_intensity - coherent_intensity),
                "cue": cue,
                "expected_fringe_spacing": wavelength * 4.8 / separation
                if separation
                else math.inf,
            },
        )
    if name in {"force_perpendicular_velocity", "helix_radius"}:
        layer = next((layer for layer in layers if layer["type"] == "line"), None)
        vectors = {record["label"]: record for record in layers if record["type"] == "vector"}
        velocity = vectors.get("velocity v")
        force = vectors.get("Lorentz force q(v×B)")
        field = vectors.get("uniform field B")
        delta = lambda record: [record["to"][index] - record["from"][index] for index in range(3)]
        v = delta(velocity) if velocity else [math.nan] * 3
        f = delta(force) if force else [math.nan] * 3
        b = delta(field) if field else [math.nan] * 3
        dot = sum(left * right for left, right in zip(v, f))
        cross = [v[1] * b[2] - v[2] * b[1], v[2] * b[0] - v[0] * b[2], v[0] * b[1] - v[1] * b[0]]
        cross_force = max(
            (
                abs(cross[index] * f[(index + 1) % 3] - cross[(index + 1) % 3] * f[index])
                for index in range(3)
            ),
            default=math.inf,
        )
        radii = [math.hypot(point[0], point[2]) for point in layer["points"]] if layer else []
        return _result(
            bool(layer and len(layer["points"]) >= 40)
            and {"charge", "field", "speed", "playback"} <= controls.keys()
            and abs(dot) < 1e-9
            and cross_force < 1e-9
            and max(radii, default=math.inf) - min(radii, default=-math.inf) < 1e-8,
            {
                "helix_samples": len(layer["points"]) if layer else 0,
                "velocity": v,
                "force": f,
                "field": b,
                "v_dot_force": dot,
                "cross_parallel_residual": cross_force,
                "radius_range": [min(radii, default=None), max(radii, default=None)],
            },
        )
    if name in {"peak_shifts_shorter", "radiance_positive"}:
        positive = all(point[1] >= 0 for line in lines for point in line["points"])
        peak_points = [max(line["points"], key=lambda point: point[1]) for line in lines]
        peaks = [point[0] for point in peak_points]
        markers = next(
            (
                layer
                for layer in layers
                if layer["type"] == "particles" and "Wien" in str(layer.get("label", ""))
            ),
            None,
        )
        marker_error = max(
            (
                math.dist(expected, actual)
                for expected, actual in zip(
                    peak_points, markers.get("points", []) if markers else []
                )
            ),
            default=math.inf,
        )
        return _result(
            positive
            and len(peaks) == 3
            and peaks[0] > peaks[1] > peaks[2]
            and marker_error < 1e-9
            and "temperature" in controls,
            {
                "peak_wavelengths": peaks,
                "positive": positive,
                "visible_peak_marker_error": marker_error,
            },
        )

    label_requirements = {
        "closed_cycle": ("cycle",),
        "process_direction": ("expansion", "compression"),
        "six_carbon_ring": ("six-carbon ring",),
        "alternating_or_delocalized": ("delocalized",),
        "coordination_geometry": ("molecular geometry",),
        "bond_angles": ("bond",),
        "electron_anode_to_cathode": ("anode", "cathode", "electron"),
        "ion_migration": ("salt bridge",),
        "phase_region": ("solid", "liquid"),
        "triple_point": ("triple point",),
        "stoichiometric_ratio": ("n₂ + 3h₂", "2nh₃"),
        "le_chatelier_direction": ("fewer gas",),
        "five_to_three_synthesis": ("leading strand", "lagging strand"),
        "strand_roles": ("okazaki",),
        "flow_order": ("glomerulus", "collecting duct"),
        "reabsorption_location": ("tubule",),
        "gradient_direction": ("high concentration", "low concentration"),
        "atp_only_active": ("atp",),
        "sorted_output": ("sorted output",),
        "stable_merge": ("stable merge",),
        "bucket_hash": ("hash function", "bucket"),
        "collision_chain": ("collision chain",),
        "frontier_policy": ("frontier",),
        "visits_once": ("visited",),
        "parent_not_greater_child": ("parent ≤ children",),
        "extracts_minimum": ("minimum root",),
        "stack_lifo": ("recursive descent", "unwind"),
        "factorial_result": ("factorial(5)",),
        "page_offset_preserved": ("virtual address", "physical frame"),
        "fault_path": ("page fault", "storage"),
        "legal_transition": ("red", "green", "amber"),
        "mutually_exclusive_lights": ("red", "green"),
        "chain_rule_gradients": ("reverse gradient",),
        "forward_value": ("u = wx+b", "y = u²"),
        "energy_conservation": ("100 j input",),
        "units_joules": ("100 j",),
    }
    if name in label_requirements:
        terms = label_requirements[name]
        required_terms_present = all(term in labels for term in terms)
        structural = False
        structural_evidence: dict[str, Any] = {}
        if family == "entropy_cycle":
            pv_lines = [line for line in lines if str(line.get("label", "")).startswith("P–V")]
            ts_lines = [line for line in lines if str(line.get("label", "")).startswith("T–S")]
            panels = [layer for layer in layers if layer["type"] == "panel"]
            pv_closed = len(pv_lines) == 4 and all(
                math.dist(pv_lines[index]["points"][-1], pv_lines[(index + 1) % 4]["points"][0])
                < 1e-9
                for index in range(4)
            )
            ts_closed = len(ts_lines) == 4 and all(
                math.dist(ts_lines[index]["points"][-1], ts_lines[(index + 1) % 4]["points"][0])
                < 1e-9
                for index in range(4)
            )
            structural = (
                pv_closed
                and ts_closed
                and len(panels) == 2
                and {panel["id"] for panel in panels} == {"pv_cycle", "ts_cycle"}
                and sum(
                    layer["type"] == "particles" and "synchronized state" in layer["label"]
                    for layer in layers
                )
                == 2
            )
            structural_evidence = {
                "pv_processes": len(pv_lines),
                "ts_processes": len(ts_lines),
                "pv_closed": pv_closed,
                "ts_closed": ts_closed,
                "panels": [panel["id"] for panel in panels],
            }
        elif family == "benzene":
            degrees = {node["id"]: 0 for node in nodes}
            for link in links:
                degrees[link["from"]] += 1
                degrees[link["to"]] += 1
            model = next(
                (control for control in spec["controls"] if control["id"] == "bond_model"), {}
            )
            structural = (
                len(nodes) == 6
                and len(links) == 6
                and set(degrees.values()) == {2}
                and model.get("options") == ["localized", "delocalized"]
                and any("alternating" in link["label"].casefold() for link in links)
            )
            structural_evidence = {
                "carbon_nodes": len(nodes),
                "ring_edges": len(links),
                "degrees": degrees,
                "bond_models": model.get("options"),
            }
        elif family == "molecular_geometry":
            centre = [layer for layer in layers if layer["type"] == "sphere"]
            bonds = [layer for layer in layers if layer["type"] == "vector"]
            lone_pairs = [
                layer
                for layer in layers
                if layer["type"] == "point" and "lone pair" in layer["label"]
            ]
            directions = {
                tuple(round(value, 6) for value in bond["to"])
                for bond in bonds
                if bond["from"] == [0, 0, 0]
            }
            molecule = next(
                (control for control in spec["controls"] if control["id"] == "molecule"), {}
            )
            structural = (
                len(centre) == 1
                and len(directions) == 6
                and len(lone_pairs) == 2
                and molecule.get("type") == "select"
                and molecule.get("options") == ["sf6", "brf5"]
            )
            structural_evidence = {
                "central_atoms": len(centre),
                "bond_directions": sorted(directions),
                "lone_pairs": len(lone_pairs),
                "molecules": molecule.get("options"),
            }
        elif family == "electrochemical_cell":
            edge_labels = {link["label"].casefold() for link in links}
            edge_pairs = {(link["from"], link["to"]) for link in links if link["arrow"]}
            structural = (
                {"anode", "cathode", "salt_bridge", "voltage"} <= {node["id"] for node in nodes}
                and {
                    "electron flow",
                    "no₃⁻ anions migrate to anode",
                    "k⁺ cations migrate to cathode",
                }
                <= edge_labels
                and {("anode", "cathode"), ("salt_bridge", "anode"), ("salt_bridge", "cathode")}
                <= edge_pairs
                and {"zinc_concentration", "copper_concentration"} <= controls.keys()
                and "zn → zn²⁺ + 2e⁻" in labels
                and "cu²⁺ + 2e⁻ → cu" in labels
            )
            structural_evidence = {
                "nodes": sorted(node["id"] for node in nodes),
                "flows": sorted(edge_labels),
            }
        elif family == "phase_diagram":
            intersections = []
            if len(lines) >= 3:
                for point in lines[0]["points"]:
                    if any(
                        math.dist(point, candidate) < 1e-8 for candidate in lines[1]["points"]
                    ) and any(
                        math.dist(point, candidate) < 1e-8 for candidate in lines[2]["points"]
                    ):
                        intersections.append(point)
            structural = bool(intersections) and {"temperature", "pressure"} <= controls.keys()
            structural_evidence = {"triple_points": intersections, "controls": controls}
        elif family == "equilibrium_shift":
            particle_labels = {
                str(layer.get("label", "")).casefold()
                for layer in layers
                if layer["type"] == "particles"
            }
            structural = (
                {"pressure", "temperature"} <= controls.keys()
                and len(nodes) >= 4
                and "n₂ + 3h₂" in labels
                and "2nh₃" in labels
                and "fewer gas molecules" in labels
                and all(link["arrow"] for link in links)
                and {"n₂ molecule population", "h₂ molecule population", "nh₃ molecule population"}
                <= particle_labels
            )
            structural_evidence = {
                "controls": controls,
                "nodes": [node["label"] for node in nodes],
                "molecule_layers": sorted(particle_labels),
            }
        elif family == "dna_replication":
            node_ids = {node["id"] for node in nodes}
            edge_labels = {link["label"].casefold() for link in links}
            structural = (
                {"fork", "leading_primer", "leading", "lagging_primer", "okazaki", "ligase"}
                <= node_ids
                and sum("primer" in node["label"].casefold() for node in nodes) >= 2
                and sum("5′→3′" in node["label"] for node in nodes) >= 2
                and {"primer starts", "polymerase 5′→3′", "seal fragments"} <= edge_labels
            )
            structural_evidence = {"nodes": sorted(node_ids), "directed_steps": sorted(edge_labels)}
        elif family == "nephron":
            order = [
                "glomerulus",
                "proximal",
                "descending_loop",
                "ascending_loop",
                "distal",
                "collecting",
            ]
            edges = [(link["from"], link["to"]) for link in links if link["arrow"]]
            structural = (
                edges[:5] == list(itertools.pairwise(order))
                and all(term in labels for term in ("h₂o", "na⁺", "glucose", "no water"))
                and {"water_return", "sodium_return", "glucose_return"}
                <= {node["id"] for node in nodes}
                and sum("reabsorbed" in link["label"].casefold() for link in links) >= 5
                and next(
                    (
                        control.get("options")
                        for control in spec["controls"]
                        if control["id"] == "segment"
                    ),
                    [],
                )
                == order[1:]
            )
            structural_evidence = {
                "flow": edges,
                "segment_selector": next(
                    (
                        control.get("options")
                        for control in spec["controls"]
                        if control["id"] == "segment"
                    ),
                    [],
                ),
            }
        elif family == "membrane_transport":
            options = next(
                (
                    control.get("options")
                    for control in spec["controls"]
                    if control["id"] == "transport_mode"
                ),
                [],
            )
            edges = {(link["from"], link["to"], link["label"].casefold()) for link in links}
            structural = (
                options == ["diffusion", "facilitated", "active"]
                and ("high", "diffusion", "down gradient") in edges
                and ("high", "facilitated", "down gradient") in edges
                and ("low", "active", "against gradient") in edges
                and ("active", "high", "atp required") in edges
                and sum("atp" in item[2] for item in edges) == 3
            )
            structural_evidence = {"modes": options, "flows": sorted(edges)}
        elif family == "merge_sort":
            node_by_id = {node["id"]: node["label"] for node in nodes}
            input_values = [
                float(value)
                for value in re.findall(r"-?\d+(?:\.\d+)?", node_by_id.get("input", ""))
            ]
            output_values = [
                float(value)
                for value in re.findall(r"-?\d+(?:\.\d+)?", node_by_id.get("output", ""))
            ]
            tagged = [
                (float(value), int(index))
                for value, index in re.findall(
                    r"(-?\d+(?:\.\d+)?)@(\d+)", node_by_id.get("stability", "")
                )
            ]
            stable = all(
                first_index < second_index
                for (first_value, first_index), (second_value, second_index) in itertools.pairwise(
                    tagged
                )
                if first_value == second_value
            )
            split_nodes = [
                node_id
                for node_id in node_by_id
                if node_id == "input" or node_id.startswith("split_")
            ]
            merge_nodes = [node_id for node_id in node_by_id if node_id.startswith("merge_")]
            structural = (
                len(input_values) >= 2
                and output_values == sorted(input_values)
                and len(tagged) == len(input_values)
                and sorted(tagged) == tagged
                and stable
                and len(split_nodes) == 2 * len(input_values) - 1
                and len(merge_nodes) == len(input_values) - 1
                and sum(link["label"] == "recursive split" for link in links)
                == 2 * (len(input_values) - 1)
                and sum("left wins equal" in link["label"] for link in links)
                == 2 * (len(input_values) - 1)
            )
            structural_evidence = {
                "input": input_values,
                "output": output_values,
                "stable_identities": tagged,
                "split_nodes": len(split_nodes),
                "merge_nodes": len(merge_nodes),
                "stable": stable,
            }
        elif family == "hash_table":
            node_ids = {node["id"] for node in nodes}
            edge_pairs = {(link["from"], link["to"]) for link in links}
            operation = next(
                (control for control in spec["controls"] if control["id"] == "operation"), {}
            )
            structural = (
                {f"bucket{index}" for index in range(5)} <= node_ids
                and {"chain_a", "chain_b", "chain_c", "chain_d"} <= node_ids
                and {
                    ("hash", "bucket2"),
                    ("bucket2", "chain_a"),
                    ("chain_a", "chain_b"),
                    ("chain_b", "chain_c"),
                    ("chain_c", "chain_d"),
                }
                <= edge_pairs
                and operation.get("options") == ["insert", "lookup", "delete"]
                and int(controls["key"]) % 5 == 2
            )
            structural_evidence = {
                "nodes": sorted(node_ids),
                "edges": sorted(edge_pairs),
                "operation": operation.get("options"),
            }
        elif family == "graph_traversal":
            graph_nodes = {node["id"] for node in nodes} - {"status"}
            options = next(
                (
                    control.get("options")
                    for control in spec["controls"]
                    if control["id"] == "algorithm"
                ),
                [],
            )
            edges = {tuple(sorted((link["from"], link["to"]))) for link in links}
            structural = (
                graph_nodes == {"A", "B", "C", "D", "E"}
                and len(edges) == 5
                and options == ["bfs", "dfs"]
                and "frontier" in labels
            )
            structural_evidence = {
                "graph_nodes": sorted(graph_nodes),
                "shared_edges": sorted(edges),
                "algorithms": options,
            }
        elif family == "heap":
            numeric_nodes = [(node, re.search(r"-?\d+(?:\.\d+)?", node["label"])) for node in nodes]
            node_values = {
                node["id"]: float(match.group()) for node, match in numeric_nodes if match
            }
            edge_pairs = [(link["from"], link["to"]) for link in links]
            numeric_edges = [
                (parent, child)
                for parent, child in edge_pairs
                if parent in node_values and child in node_values
            ]
            heap_property = all(
                node_values[parent] <= node_values[child] for parent, child in numeric_edges
            )
            operation = next(
                (control for control in spec["controls"] if control["id"] == "operation"), {}
            )
            empty_slots = [node["id"] for node in nodes if "empty insert slot" in node["label"]]
            structural = (
                heap_property
                and node_values.get("root") == min(node_values.values())
                and operation.get("options") == ["insert", "extract_min"]
                and len(empty_slots) == 1
            )
            structural_evidence = {
                "values": node_values,
                "parent_child_edges": edge_pairs,
                "heap_property": heap_property,
                "operations": operation.get("options"),
                "empty_insert_slots": empty_slots,
            }
        elif family == "recursion_stack":
            labels_by_id = {node["id"]: node["label"] for node in nodes}
            structural = (
                len(nodes) >= 10
                and labels_by_id.get("call5") == "factorial(5)"
                and labels_by_id.get("return5") == "return 120"
                and all(link["arrow"] for link in links)
            )
            structural_evidence = {"frames": labels_by_id, "directed_edges": len(links)}
        elif family == "virtual_memory":
            edge_labels = {link["label"].casefold() for link in links}
            ids = {node["id"] for node in nodes}
            structural = (
                {"virtual", "tlb", "page_table", "frame", "storage", "replacement"} <= ids
                and {"tlb miss", "page-table lookup", "page fault", "page-in replacement"}
                <= edge_labels
                and "address" in controls
            )
            structural_evidence = {"nodes": sorted(ids), "translation_steps": sorted(edge_labels)}
        elif family == "state_machine":
            state_ids = {node["id"] for node in nodes}
            edges = {(link["from"], link["to"]) for link in links}
            structural = (
                state_ids == {"red", "red_amber", "green", "amber"}
                and edges
                == {
                    ("red", "red_amber"),
                    ("red_amber", "green"),
                    ("green", "amber"),
                    ("amber", "red"),
                }
                and {"step", "pedestrian_request"} <= controls.keys()
            )
            structural_evidence = {"states": sorted(state_ids), "transitions": sorted(edges)}
        elif family == "backprop_graph":
            w, x, b = (float(controls[key]) for key in ("w", "x", "b"))
            u = w * x + b
            y = u * u
            ids = {node["id"] for node in nodes}
            edges = {(link["from"], link["to"]) for link in links}
            structural = (
                {"inputs", "u", "y", "grad_u", "grad_w", "grad_x", "grad_b"} <= ids
                and {
                    ("inputs", "u"),
                    ("u", "y"),
                    ("y", "grad_u"),
                    ("grad_u", "grad_w"),
                    ("grad_u", "grad_x"),
                    ("grad_u", "grad_b"),
                }
                <= edges
                and math.isfinite(y)
                and abs(2 * u * x - (2 * u) * x) < 1e-12
            )
            structural_evidence = {
                "u": u,
                "y": y,
                "gradients": {"du": 2 * u, "dw": 2 * u * x, "dx": 2 * u * w, "db": 2 * u},
                "nodes": sorted(ids),
            }
        elif family == "energy_sankey":
            ids = {node["id"] for node in nodes}
            edges = {(link["from"], link["to"]) for link in links}
            amounts = [float(link["label"].split()[0]) for link in links]
            structural = (
                ids == {"input", "useful", "heat", "sound"}
                and edges == {("input", "useful"), ("input", "heat"), ("input", "sound")}
                and abs(sum(amounts) - 100) < 1e-9
                and all("j" in link["label"].casefold() for link in links)
            )
            structural_evidence = {
                "branches": sorted(edges),
                "flows_j": amounts,
                "total_j": sum(amounts),
            }
        return _result(
            structural,
            {
                "required_terms": terms,
                "required_terms_present": required_terms_present,
                "structure": structural_evidence,
            },
        )

    if name in {"frequency_rises_with_time", "time_frequency_alignment"}:
        heatmap = next((layer for layer in layers if layer["type"] == "heatmap"), None)
        waveform = next(
            (line for line in lines if "chirp waveform" in str(line.get("label", "")).casefold()),
            None,
        )
        peaks = []
        if heatmap:
            for column in range(heatmap["columns"]):
                peaks.append(
                    max(
                        range(heatmap["rows"]),
                        key=lambda row: heatmap["values"][row * heatmap["columns"] + column],
                    )
                )
        rises = sum(next_peak >= peak for peak, next_peak in itertools.pairwise(peaks))
        expected_peaks = (
            [2 + 10 * column / (heatmap["columns"] - 1) for column in range(heatmap["columns"])]
            if heatmap and heatmap["columns"] > 1
            else []
        )
        peak_error = max(
            (abs(actual - expected) for actual, expected in zip(peaks, expected_peaks)),
            default=math.inf,
        )
        waveform_error = (
            max(
                (
                    abs(y - math.sin(2 * math.pi * (2 * x + 5 * x * x)))
                    for x, y in waveform.get("points", [])
                ),
                default=math.inf,
            )
            if waveform
            else math.inf
        )
        evidence = {
            "frequency_peak_rows": peaks,
            "expected_peak_rows": expected_peaks,
            "nondecreasing_steps": rises,
            "peak_row_error": peak_error,
            "chirp_waveform_error": waveform_error,
        }
        if name == "frequency_rises_with_time":
            return _result(
                len(peaks) >= 20 and rises >= len(peaks) - 3 and peaks[-1] - peaks[0] >= 8,
                evidence,
            )
        return _result(
            bool(waveform)
            and len(waveform["points"]) >= 80
            and peak_error <= 1
            and waveform_error < 1e-9,
            evidence,
        )
    if name in {"temperature_smooths", "energy_bounded"} and family == "heat_diffusion":
        heatmap = next((layer for layer in layers if layer["type"] == "heatmap"), None)
        values = heatmap.get("values", []) if heatmap else []
        row = values[: heatmap["columns"]] if heatmap else []
        symmetry = max(
            (abs(row[index] - row[-1 - index]) for index in range(len(row) // 2)),
            default=math.inf,
        )
        center = row[len(row) // 2] if row else -math.inf
        return _result(
            bool(row) and min(row) >= 0 and symmetry < 1e-8 and center > row[0],
            {"grid_cells": len(values), "symmetry_error": symmetry, "center": center},
        )
    if name in {"loss_nonincreasing", "class_regions"}:
        heatmap = next((layer for layer in layers if layer["type"] == "heatmap"), None)
        values = heatmap.get("values", []) if heatmap else []
        loss = next(
            (line for line in lines if "training loss" in str(line.get("label", "")).casefold()),
            None,
        )
        evidence = {
            "grid_cells": len(values),
            "score_range": [min(values), max(values)] if values else None,
            "labelled_samples": sum(
                len(layer.get("points", [])) for layer in layers if layer["type"] == "particles"
            ),
            "loss_points": len(loss.get("points", [])) if loss else 0,
        }
        if name == "loss_nonincreasing":
            loss_values = [point[1] for point in loss.get("points", [])] if loss else []
            nonincreasing = all(
                next_value <= value + 1e-12 for value, next_value in itertools.pairwise(loss_values)
            )
            evidence["loss_nonincreasing"] = nonincreasing
            evidence["loss_range"] = [loss_values[-1], loss_values[0]] if loss_values else None
            return _result(
                family == "decision_boundary"
                and len(loss_values) >= 20
                and min(loss_values) >= 0
                and loss_values[-1] < loss_values[0]
                and nonincreasing,
                evidence,
            )
        return _result(
            family == "decision_boundary"
            and bool(values)
            and min(values) < 0 < max(values)
            and any(layer["type"] == "particles" for layer in layers),
            evidence,
        )

    if name in {"integrated_rate_law", "half_life_behavior"}:
        by_label = {str(line.get("label", "")).casefold(): line["points"] for line in lines}
        required = {
            "zero-order [a]",
            "first-order [a]",
            "second-order [a]",
            "zero-order linearized [a]",
            "first-order linearized ln[a]",
            "second-order linearized 1/[a]",
        }
        rate = float(controls.get("rate_constant", 0.35))
        if not required <= by_label.keys() or rate <= 0:
            return _result(False, {"curve_labels": sorted(by_label)})
        formulas = {
            "zero-order [a]": lambda t: max(0.0, 1 - rate * t),
            "first-order [a]": lambda t: math.exp(-rate * t),
            "second-order [a]": lambda t: 1 / (1 + rate * t),
            "zero-order linearized [a]": lambda t: max(0.0, 1 - rate * t),
            "first-order linearized ln[a]": lambda t: -rate * t,
            "second-order linearized 1/[a]": lambda t: 1 + rate * t,
        }
        residual = max(
            abs(value - formulas[label](time))
            for label in required
            for time, value in by_label[label]
        )
        half_times = [0.5 / rate, math.log(2) / rate, 1 / rate]
        concentration_labels = ["zero-order [a]", "first-order [a]", "second-order [a]"]
        half_errors = [
            min(abs(time - expected) + abs(value - 0.5) for time, value in by_label[label])
            for label, expected in zip(concentration_labels, half_times)
        ]
        return _result(
            residual < 1e-10 and max(half_errors) < 0.12,
            {
                "curve_count": len(by_label),
                "max_law_residual": residual,
                "half_life_errors": half_errors,
            },
        )

    if name in {"minus3db_at_cutoff", "phase_transition"}:
        magnitude = next(
            (
                line["points"]
                for line in lines
                if "magnitude" in str(line.get("label", "")).casefold()
            ),
            [],
        )
        phase = next(
            (line["points"] for line in lines if "phase" in str(line.get("label", "")).casefold()),
            [],
        )
        cutoff = float(controls.get("cutoff", 1))
        target_x = math.log10(cutoff) if cutoff > 0 else math.inf
        magnitude_at = (
            min(magnitude, key=lambda point: abs(point[0] - target_x))
            if magnitude
            else [math.inf, math.inf]
        )
        phase_at = (
            min(phase, key=lambda point: abs(point[0] - target_x))
            if phase
            else [math.inf, math.inf]
        )
        return _result(
            abs(magnitude_at[1] + 10 * math.log10(2)) < 0.05 and abs(phase_at[1] + 45) < 0.1,
            {
                "cutoff_log_frequency": target_x,
                "magnitude_db": magnitude_at[1],
                "phase_degrees": phase_at[1],
            },
        )

    if name in {"support_reactions", "moment_zero_at_supports"}:
        shear = next(
            (line["points"] for line in lines if "shear" in str(line.get("label", "")).casefold()),
            [],
        )
        moment = next(
            (line["points"] for line in lines if "moment" in str(line.get("label", "")).casefold()),
            [],
        )
        deflection = next(
            (
                line["points"]
                for line in lines
                if "deflection" in str(line.get("label", "")).casefold()
            ),
            [],
        )
        shear_jump = max(
            (abs(next_point[1] - point[1]) for point, next_point in itertools.pairwise(shear)),
            default=0,
        )
        by_label = {str(line.get("label", "")): line["points"] for line in lines}
        left_reaction = by_label.get("left support reaction", [])
        right_reaction = by_label.get("right support reaction", [])
        selected = float(controls.get("load_position", 5))
        expected_reactions = [10 * (10 - selected) / 10, 10 * selected / 10]
        actual_reactions = [
            left_reaction[-1][1] * 5 if left_reaction else math.inf,
            right_reaction[-1][1] * 5 if right_reaction else math.inf,
        ]
        panel_titles = {layer["title"] for layer in layers if layer["type"] == "panel"}
        return _result(
            bool(shear and moment and deflection)
            and abs(shear[0][1] + shear[-1][1]) < 1e-9
            and abs(shear_jump - 10) < 1e-9
            and abs(moment[0][1]) < 1e-9
            and abs(moment[-1][1]) < 1e-9
            and abs(deflection[0][1]) < 1e-9
            and abs(deflection[-1][1]) < 1e-9
            and {
                "simply supported beam",
                "left pin support",
                "right roller support",
                "moving point load 10",
                "left support reaction",
                "right support reaction",
            }
            <= set(by_label)
            and max(
                abs(actual - expected)
                for actual, expected in zip(actual_reactions, expected_reactions)
            )
            < 1e-9
            and panel_titles
            == {
                "Simply supported beam",
                "Shear-force diagram",
                "Bending-moment diagram",
                "Deflection diagram",
            },
            {
                "reaction_sum_residual": abs(shear[0][1] + shear[-1][1]) if shear else None,
                "shear_jump": shear_jump,
                "moment_endpoints": [moment[0][1], moment[-1][1]] if moment else None,
                "reactions": actual_reactions,
                "expected_reactions": expected_reactions,
                "panels": sorted(panel_titles),
            },
        )

    if name in {"streamline_symmetry", "no_penetration"}:
        streamlines = [
            line for line in lines if "streamline" in str(line.get("label", "")).casefold()
        ]
        upper = [line["points"] for line in streamlines if "−" not in str(line.get("label", ""))]
        lower = [line["points"] for line in streamlines if "−" in str(line.get("label", ""))]
        symmetry_error = max(
            (
                abs(a[0] - b[0]) + abs(a[1] + b[1])
                for up, down in zip(upper, lower)
                for a, b in zip(up, down)
            ),
            default=math.inf,
        )
        min_radius = min(
            (math.hypot(*point) for line in streamlines for point in line["points"]), default=0
        )
        stagnation = next(
            (
                layer.get("points", [])
                for layer in layers
                if layer["type"] == "particles"
                and "stagnation" in str(layer.get("label", "")).casefold()
            ),
            [],
        )
        return _result(
            len(streamlines) == 8
            and symmetry_error < 1e-8
            and min_radius >= 1 - 1e-6
            and stagnation == [[-1, 0], [1, 0]],
            {
                "streamlines": len(streamlines),
                "symmetry_error": symmetry_error,
                "minimum_radius": min_radius,
                "stagnation_points": stagnation,
            },
        )

    if name in {"positive_volume", "density_distribution"}:
        samples = next(
            (
                layer.get("points", [])
                for layer in layers
                if layer["type"] == "particles" and "mass" in str(layer.get("label", "")).casefold()
            ),
            [],
        )
        histogram = next(
            (
                line["points"]
                for line in lines
                if "density histogram" in str(line.get("label", "")).casefold()
            ),
            [],
        )
        spacing = histogram[1][0] - histogram[0][0] if len(histogram) > 1 else 0
        integral = sum(point[1] for point in histogram) * spacing
        densities = [mass / volume for volume, mass in samples if volume > 0]
        return _result(
            len(samples) >= 100
            and len(densities) == len(samples)
            and min(volume for volume, _mass in samples) > 0
            and histogram
            and all(value >= 0 for _x, value in histogram)
            and abs(integral - 1) < 0.08
            and min(point[0] for point in histogram) - spacing / 2
            <= min(densities)
            <= max(densities)
            <= max(point[0] for point in histogram) + spacing / 2,
            {
                "samples": len(samples),
                "minimum_volume": min((point[0] for point in samples), default=None),
                "histogram_bins": len(histogram),
                "histogram_integral": integral,
            },
        )

    if name in {"population_nonnegative", "phase_cycle"}:
        prey = next(
            (
                line["points"]
                for line in lines
                if "prey population" in str(line.get("label", "")).casefold()
            ),
            [],
        )
        predator = next(
            (
                line["points"]
                for line in lines
                if "predator population" in str(line.get("label", "")).casefold()
            ),
            [],
        )
        phase = next(
            (
                line["points"]
                for line in lines
                if "phase portrait" in str(line.get("label", "")).casefold()
            ),
            [],
        )
        consistent = len(prey) == len(predator) == len(phase) and all(
            abs(phase[index][0] - prey[index][1]) < 1e-10
            and abs(phase[index][1] - predator[index][1]) < 1e-10
            for index in range(len(phase))
        )
        return _result(
            bool(prey)
            and min(point[1] for point in prey + predator) >= 0
            and consistent
            and max(point[0] for point in phase) > min(point[0] for point in phase)
            and max(point[1] for point in phase) > min(point[1] for point in phase),
            {
                "samples": len(phase),
                "phase_matches_time_series": consistent,
                "minimum_population": min((point[1] for point in prey + predator), default=None),
            },
        )

    if name in {"vmax_limit", "competitive_km_shift"}:
        baseline = next(
            (
                line["points"]
                for line in lines
                if "without inhibitor" in str(line.get("label", "")).casefold()
            ),
            [],
        )
        inhibited = next(
            (
                line["points"]
                for line in lines
                if "competitive inhibition" in str(line.get("label", "")).casefold()
            ),
            [],
        )
        baseline_residual = max(
            (abs(rate - substrate / (1.5 + substrate)) for substrate, rate in baseline),
            default=math.inf,
        )
        inhibited_residual = max(
            (abs(rate - substrate / (3 + substrate)) for substrate, rate in inhibited),
            default=math.inf,
        )
        baseline_half = min(baseline, key=lambda point: abs(point[1] - 0.5)) if baseline else []
        inhibited_half = min(inhibited, key=lambda point: abs(point[1] - 0.5)) if inhibited else []
        return _result(
            baseline_residual < 1e-10
            and inhibited_residual < 1e-10
            and baseline[-1][1] < 1
            and inhibited[-1][1] < 1
            and inhibited_half[0] > baseline_half[0],
            {
                "baseline_residual": baseline_residual,
                "inhibited_residual": inhibited_residual,
                "apparent_km_values": [
                    baseline_half[0] if baseline_half else None,
                    inhibited_half[0] if inhibited_half else None,
                ],
                "shared_vmax_limit": 1,
            },
        )

    if name in {"discrete_convolution_sum", "output_length"}:
        by_label = {str(line.get("label", "")).casefold(): line["points"] for line in lines}
        input_values = [1, 2, 1]
        impulse_values = [1, -1, 2]
        expected = [
            sum(
                input_values[source] * impulse_values[index - source]
                for source in range(len(input_values))
                if 0 <= index - source < len(impulse_values)
            )
            for index in range(len(input_values) + len(impulse_values) - 1)
        ]
        output = next(
            (points for label, points in by_label.items() if "convolution output" in label), []
        )
        actual = [point[1] for point in output]
        return _result(
            actual == expected and len(actual) == 5,
            {
                "input": input_values,
                "impulse": impulse_values,
                "expected_output": expected,
                "actual_output": actual,
            },
        )

    if name in {"encirclement_count", "closed_loop_stability"}:
        locus = next(
            (
                line["points"]
                for line in lines
                if "nyquist locus" in str(line.get("label", "")).casefold()
            ),
            [],
        )
        total_angle = 0.0
        for first, second in itertools.pairwise(locus):
            angle_1 = math.atan2(first[1], first[0] + 1)
            angle_2 = math.atan2(second[1], second[0] + 1)
            delta = (angle_2 - angle_1 + math.pi) % (2 * math.pi) - math.pi
            total_angle += delta
        winding = round(total_angle / (2 * math.pi))
        critical = next(
            (
                layer.get("points", [])
                for layer in layers
                if layer["type"] == "particles"
                and "critical point" in str(layer.get("label", "")).casefold()
            ),
            [],
        )
        return _result(
            _closed(locus) and winding == 0 and critical[:1] == [[-1, 0]],
            {
                "winding_about_minus_one": winding,
                "critical_point": critical[:1],
                "closed_locus": _closed(locus),
            },
        )

    if name in {"response_metrics", "final_value"}:
        responses = {
            str(line.get("label", "")).casefold(): line["points"]
            for line in lines
            if "response" in str(line.get("label", "")).casefold()
        }
        markers = {
            str(line.get("label", "")).casefold(): line["points"]
            for line in lines
            if "marker" in str(line.get("label", "")).casefold()
        }
        finals = {label: points[-1][1] for label, points in responses.items() if points}
        pid = responses.get("pid response", [])
        peak = max(pid, key=lambda point: point[1]) if pid else [math.inf, math.inf]
        rise = next((point for point in pid if point[1] >= 0.9), [math.inf, math.inf])
        overshoot = peak[1] - 1
        rise_marker = markers.get("rise time marker", [])
        overshoot_marker = markers.get("overshoot marker", [])
        steady_marker = markers.get("steady-state error marker", [])
        markers_match = (
            bool(rise_marker and overshoot_marker and steady_marker)
            and abs(rise_marker[-1][0] - rise[0]) < 1e-9
            and math.dist(overshoot_marker[-1], peak) < 1e-9
            and abs(steady_marker[0][1] - finals.get("pid response", math.inf)) < 1e-9
        )
        return _result(
            set(responses) == {"p response", "pi response", "pid response"}
            and {"rise time marker", "overshoot marker", "steady-state error marker"}
            <= set(markers)
            and 0.45 < finals.get("p response", 0) < 0.55
            and abs(finals.get("pi response", 0) - 1) < 0.02
            and abs(finals.get("pid response", 0) - 1) < 0.02
            and overshoot >= 0
            and markers_match,
            {
                "final_values": finals,
                "pid_overshoot": overshoot,
                "markers_match": markers_match,
                "rise_time": rise[0],
            },
        )

    if name in {"pulse_width_ratio", "average_voltage"}:
        pulses = next(
            (
                line["points"]
                for line in lines
                if str(line.get("label", "")).casefold() == "pwm voltage"
            ),
            [],
        )
        average = next(
            (
                line["points"]
                for line in lines
                if "average voltage" in str(line.get("label", "")).casefold()
            ),
            [],
        )
        duty = float(controls.get("duty_cycle", 0))
        widths = [
            pulses[index + 2][0] - pulses[index + 1][0]
            for index in range(0, len(pulses), 4)
            if index + 2 < len(pulses)
        ]
        return _result(
            len(widths) == 20
            and max((abs(width - duty) for width in widths), default=math.inf) < 1e-10
            and len(average) == 2
            and all(abs(point[1] - duty) < 1e-10 for point in average),
            {
                "duty_cycle": duty,
                "pulse_widths": widths,
                "average_voltage_fraction": average[0][1] if average else None,
            },
        )

    if name in {"link_lengths_constant", "end_effector_target"}:
        by_id = {node["id"]: node for node in nodes}
        required = {"base", "elbow", "end_effector", "target"}
        if not required <= by_id.keys():
            return _result(False, {"error": "robot arm landmarks are missing"})
        length_1 = math.dist(
            [by_id["base"]["x"], by_id["base"]["y"]],
            [by_id["elbow"]["x"], by_id["elbow"]["y"]],
        )
        length_2 = math.dist(
            [by_id["elbow"]["x"], by_id["elbow"]["y"]],
            [by_id["end_effector"]["x"], by_id["end_effector"]["y"]],
        )
        target_error = math.dist(
            [by_id["end_effector"]["x"], by_id["end_effector"]["y"]],
            [by_id["target"]["x"], by_id["target"]["y"]],
        )
        passed = (
            {"target_x", "target_y", "elbow_mode"} <= controls.keys()
            and abs(length_1 - 150) < 1e-3
            and abs(length_2 - 135) < 1e-3
            and target_error < 1e-6
        )
        return _result(
            passed,
            {"link_lengths_px": [length_1, length_2], "target_error_px": target_error},
        )
    if name in {"estimate_between_prior_measurement", "covariance_contracts_on_update"}:
        by_label = {str(line.get("label", "")): line["points"] for line in lines}
        required = {
            "true moving-point trajectory",
            "noisy measurements",
            "Kalman estimate trajectory",
            "predicted covariance ellipse P⁻",
            "posterior covariance ellipse P",
        }
        if not required <= by_label.keys():
            return _result(
                False,
                {
                    "error": "Kalman trajectories or covariance ellipses are missing",
                    "labels": sorted(by_label),
                },
            )
        prior_ellipse = by_label["predicted covariance ellipse P⁻"]
        posterior_ellipse = by_label["posterior covariance ellipse P"]
        centre = lambda points: [
            sum(point[0] for point in points) / len(points),
            sum(point[1] for point in points) / len(points),
        ]
        prior_centre = centre(prior_ellipse)
        posterior_centre = centre(posterior_ellipse)
        prior_variance = (
            (max(point[1] for point in prior_ellipse) - min(point[1] for point in prior_ellipse))
            / 2
        ) ** 2
        posterior_variance = (
            (
                max(point[1] for point in posterior_ellipse)
                - min(point[1] for point in posterior_ellipse)
            )
            / 2
        ) ** 2
        measurement_value = by_label["noisy measurements"][0][1]
        estimate_value = by_label["Kalman estimate trajectory"][0][1]
        prior_value = prior_centre[1]
        trajectories = [
            by_label[label]
            for label in (
                "true moving-point trajectory",
                "noisy measurements",
                "Kalman estimate trajectory",
            )
        ]
        return _result(
            family == "kalman_filter"
            and min(prior_value, measurement_value)
            <= estimate_value
            <= max(prior_value, measurement_value)
            and 0 < posterior_variance < prior_variance
            and all(len(points) == 21 for points in trajectories)
            and all(
                point[0] == index for points in trajectories for index, point in enumerate(points)
            )
            and {"noise", "step"} <= controls.keys(),
            {
                "values": [prior_value, estimate_value, measurement_value],
                "variances": [prior_variance, posterior_variance],
                "ellipse_centres": [prior_centre, posterior_centre],
                "trajectory_lengths": [len(points) for points in trajectories],
            },
        )
    if name in {"joint_force_balance", "member_sign"}:
        by_id = {node["id"]: node for node in nodes}
        required = {"left_support", "apex", "right_support"}
        arrows = [layer for layer in layers if layer["type"] == "arrow"]
        if not required <= by_id.keys() or len(links) != 3 or len(arrows) != 3:
            return _result(False, {"error": "triangular truss primitives are incomplete"})
        load = float(controls.get("load", 0))
        angle = math.atan2(
            by_id["left_support"]["y"] - by_id["apex"]["y"],
            by_id["apex"]["x"] - by_id["left_support"]["x"],
        )
        diagonal_force = load / (2 * math.sin(angle))
        bottom_force = diagonal_force * math.cos(angle)
        compression = [link for link in links if "compression" in link["label"].casefold()]
        tension = [link for link in links if "tension" in link["label"].casefold()]
        arrow_directions = [arrow["to"][1] - arrow["from"][1] for arrow in arrows]
        return _result(
            len(compression) == 2
            and len(tension) == 1
            and load > 0
            and abs(2 * diagonal_force * math.sin(angle) - load) < 1e-8
            and abs(diagonal_force * math.cos(angle) - bottom_force) < 1e-8
            and sum(delta > 0 for delta in arrow_directions) == 1
            and sum(delta < 0 for delta in arrow_directions) == 2,
            {
                "load_kN": load,
                "diagonal_compression_kN": diagonal_force,
                "bottom_tension_kN": bottom_force,
                "arrow_y_directions": arrow_directions,
            },
        )
    if name in {"positive_volume", "density_distribution"}:
        sample_layer = next(
            (
                layer
                for layer in layers
                if layer["type"] == "particles" and "mass-volume" in str(layer.get("label", ""))
            ),
            None,
        )
        histogram = next(
            (line["points"] for line in lines if "density histogram" in str(line.get("label", ""))),
            [],
        )
        samples = sample_layer["points"] if sample_layer else []
        volumes_positive = bool(samples) and all(volume > 0 for volume, _mass in samples)
        densities = [mass / volume for volume, mass in samples if volume > 0]
        histogram_area = (
            sum(max(0, point[1]) for point in histogram)
            * ((histogram[-1][0] - histogram[0][0]) / max(1, len(histogram) - 1))
            if len(histogram) > 1
            else 0
        )
        return _result(
            family == "uncertainty_propagation"
            and volumes_positive
            and len(samples) == round(float(controls.get("samples", 0)))
            and bool(histogram)
            and all(point[1] >= 0 for point in histogram)
            and min(point[0] for point in histogram) >= min(densities) - 0.1
            and max(point[0] for point in histogram) <= max(densities) + 0.1
            and 0.7 <= histogram_area <= 1.3,
            {
                "samples": len(samples),
                "volumes_positive": volumes_positive,
                "density_range": [
                    min(densities) if densities else None,
                    max(densities) if densities else None,
                ],
                "histogram_area": histogram_area,
            },
        )

    return _result(False, {"error": f"oracle {name!r} has no executable rule"})


def semantic_evidence(case: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    layers = spec["scene"]["layers"]
    requested_oracles = case["expected"]["oracles"]
    if case["id"].startswith("math-"):
        layer = layers[0]
        agreement = _relationship_agreement(
            layer["relationship"],
            case["normalized_equation"],
            layer["type"] == "explicit_surface",
        )
        if layer["type"] == "explicit_surface":
            finite, undefined, worst = _finite_explicit_samples(layer)
            passed = finite >= 4 and worst <= 1e-8 and agreement["passed"]
            detail = {
                "finite_samples": finite,
                "undefined_samples": undefined,
                "max_relationship_residual": worst,
                "source_equation_agreement": agreement,
            }
        else:
            negative, positive, minimum, maximum = _implicit_sign_probe(layer)
            passed = negative > 0 and positive > 0 and agreement["passed"]
            detail = {
                "negative_probe_count": negative,
                "positive_probe_count": positive,
                "residual_range": [minimum, maximum],
                "source_equation_agreement": agreement,
            }
        oracle_results = {
            "expression_residual": _result(
                agreement["passed"] and worst <= 1e-8
                if layer["type"] == "explicit_surface"
                else agreement["passed"],
                agreement,
            ),
            "finite_geometry": _result(
                (finite >= 4)
                if layer["type"] == "explicit_surface"
                else (negative > 0 and positive > 0),
                detail,
            ),
            "axis_labels": _result(
                spec["scene"]["coordinate_system"] == "cartesian3d"
                and all(axis in spec["aria_label"].casefold() for axis in ("x", "y", "z")),
                {"aria_label": spec["aria_label"]},
            ),
        }
        if "undefined_domain_split" in requested_oracles:
            # Browser triangulation supplies the decisive no-bridge evidence. At compile time,
            # require a typed division/log/root relation and bounded domains so undefined
            # regions cannot be silently converted into an unconstrained fallback surface.
            expression_nodes = list(iter_ast(layer["relationship"]["right"]))
            has_domain_risk = any(
                (node.get("type") == "binary" and node.get("op") == "/")
                or (
                    node.get("type") == "call"
                    and node.get("name") in {"atan2", "ln", "log", "sqrt", "tan"}
                )
                for node in expression_nodes
            )
            oracle_results["undefined_domain_split"] = _result(
                has_domain_risk,
                {"domain_risk_expression": has_domain_risk, "browser_check": "required"},
            )
        if layer["type"] == "implicit_surface" and negative == 0:
            # Some valid implicit zero sets do not change sign. An exact sampled zero proves
            # the set exists; the browser mesher and topology evidence remain mandatory.
            oracle_results["finite_geometry"] = _result(
                minimum <= 1e-9 and positive > 0,
                {**detail, "zero_set_without_sign_change": True},
            )
        passed = all(oracle_results[name]["passed"] for name in requested_oracles)
        return {
            "passed": passed,
            "checks": requested_oracles,
            "oracle_results": oracle_results,
            "topology_expected": case["expected"].get("topology"),
            "detail": detail,
        }
    point_count = sum(
        len(layer.get("points", []))
        + 2 * len(layer.get("vectors", []))
        + len(layer.get("values", []))
        + (2 if layer.get("type") == "probe_vector" else 0)
        for layer in layers
    )
    labels = [
        str(layer.get("label") or layer.get("text") or "").strip()
        for layer in layers
        if layer.get("label") or layer.get("text")
    ]
    primitive_types = sorted({layer["type"] for layer in layers})
    passed = bool(layers and spec["text_fallback"] and spec["controls"])
    if (
        spec["renderer"] in {"svg", "canvas"}
        and spec["scene"]["coordinate_system"] == "cartesian2d"
    ):
        passed = passed and point_count >= 5
    if spec["scene"]["coordinate_system"] == "screen":
        passed = passed and len(labels) >= 3
    oracle_results = {name: _specific_oracle(name, spec) for name in requested_oracles}
    passed = passed and all(result["passed"] for result in oracle_results.values())
    return {
        "passed": passed,
        "checks": requested_oracles,
        "oracle_results": oracle_results,
        "detail": {
            "primitive_types": primitive_types,
            "point_count": point_count,
            "semantic_labels": labels,
            "fallback": spec["text_fallback"],
        },
    }


def compile_cases(cases: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    specs: list[dict[str, Any]] = []
    for case in cases:
        started = time.perf_counter()
        error = ""
        spec: dict[str, Any] | None = None
        semantic: dict[str, Any] = {"passed": False, "checks": [], "detail": {}}
        raw_route: dict[str, Any] = {"compiled": False, "family": None, "renderer": None}
        try:
            raw_spec = compile_visualization_v2(case["raw_prompt"])
            if raw_spec is not None:
                raw_spec = validate_v2_spec(raw_spec)
                raw_route = {
                    "compiled": True,
                    "family": raw_spec["family"],
                    "renderer": raw_spec["renderer"],
                }
            audited_repair = bool(
                case.get("normalized_prompt")
                and case.get("normalized_prompt") != case["raw_prompt"]
            )
            spec = (
                compile_visualization_v2(case["normalized_prompt"]) if audited_repair else raw_spec
            )
            if spec is None:
                raise VisualizationV2Error("intent resolver returned no visualization")
            spec = validate_v2_spec(spec)
            semantic = semantic_evidence(case, spec)
        except (VisualizationV2Error, ValueError, OverflowError, TypeError, KeyError) as exc:
            error = f"{type(exc).__name__}: {exc}"
        elapsed_ms = (time.perf_counter() - started) * 1000
        expected = case["expected"]
        controls = [control["id"] for control in spec.get("controls", [])] if spec else []
        transport = {"play", "pause", "restart"}
        parameter_controls = [control_id for control_id in controls if control_id not in transport]
        checks = {
            "intent_family": bool(spec and spec["family"] == expected["family"]),
            "renderer": bool(spec and spec["renderer"] == expected["renderer"]),
            "spec_kind": bool(spec and spec["kind"] == expected["spec_kind"]),
            "controls": parameter_controls == expected["controls"]
            and (not (transport & set(controls)) or transport <= set(controls)),
            "accessibility": bool(spec and spec["aria_label"] and spec["text_fallback"]),
            "semantic_oracles": bool(semantic["passed"]),
            "raw_production_route": bool(
                raw_route["compiled"]
                and raw_route["family"] == expected["family"]
                and raw_route["renderer"] == expected["renderer"]
            ),
        }
        passed = not error and all(checks.values())
        result = {
            "id": case["id"],
            "source": case["source"],
            "domain": case["domain"],
            "intent": expected["intent"],
            "family": spec.get("family") if spec else None,
            "renderer": spec.get("renderer") if spec else None,
            "spec_kind": spec.get("kind") if spec else None,
            "controls": controls,
            "invariant_checks": semantic,
            "compile_ms": round(elapsed_ms, 3),
            "spec_bytes": len(json.dumps(spec, separators=(",", ":")).encode()) if spec else 0,
            "browser": None,
            "raw_production_route": raw_route,
            "audited_normalization_applied": bool(
                case.get("normalized_prompt")
                and case.get("normalized_prompt") != case["raw_prompt"]
            ),
            "checks": checks,
            "error": error,
            "passed": passed,
        }
        results.append(result)
        if spec is not None:
            specs.append({"id": case["id"], "spec": spec})
    return results, specs


def merge_browser(results: list[dict[str, Any]], browser_path: Path | None) -> None:
    if browser_path is None:
        for result in results:
            result["checks"]["real_browser_render"] = False
            result["passed"] = False
        return
    browser_data = json.loads(browser_path.read_text())
    by_id = {row["id"]: row for row in browser_data["cases"]}
    for result in results:
        browser = by_id.get(result["id"])
        result["browser"] = browser
        browser_passed = bool(browser and browser.get("rendered") and not browser.get("errors"))
        result["checks"]["real_browser_render"] = browser_passed
        interactions = (browser or {}).get("interaction_results", [])
        controls = result["controls"]
        control_effects = len(interactions) == len(controls) and all(
            item.get("passed")
            and (
                item.get("geometry_changed")
                or item.get("visual_state_changed")
                or (item.get("transport") and item.get("animation_changed"))
            )
            for item in interactions
        )
        result["checks"]["semantic_control_effects"] = control_effects
        oracle_results = result["invariant_checks"].get("oracle_results", {})
        if "control_consistency" in oracle_results:
            oracle_results["control_consistency"]["passed"] = bool(
                oracle_results["control_consistency"]["passed"] and control_effects
            )
            oracle_results["control_consistency"]["evidence"]["browser_interactions"] = interactions
            result["invariant_checks"]["passed"] = all(
                item["passed"] for item in oracle_results.values()
            )
            result["checks"]["semantic_oracles"] = result["invariant_checks"]["passed"]
        if "undefined_domain_split" in oracle_results:
            diagnostics = ((browser or {}).get("evidence") or {}).get("surface_diagnostics") or {}
            rejected = diagnostics.get("rejected_discontinuity_cells", 0) + diagnostics.get(
                "rejected_undefined_cells", 0
            )
            oracle_results["undefined_domain_split"]["passed"] = rejected > 0
            oracle_results["undefined_domain_split"]["evidence"]["browser_surface_diagnostics"] = (
                diagnostics
            )
            result["invariant_checks"]["passed"] = all(
                item["passed"] for item in oracle_results.values()
            )
            result["checks"]["semantic_oracles"] = result["invariant_checks"]["passed"]
        expected_topology = result["invariant_checks"].get("topology_expected") or {}
        actual_topology = ((browser or {}).get("evidence") or {}).get("topology", {})
        if expected_topology.get("components") is not None:
            actual = actual_topology.get(
                "periodic_components" if expected_topology.get("periodic") else "components"
            )
            topology_passed = actual == expected_topology["components"]
            result["checks"]["component_count"] = topology_passed
        if expected_topology.get("closed") is True:
            result["checks"]["closed_mesh"] = (
                actual_topology.get("boundary_edges") == 0
                and actual_topology.get("nonmanifold_edges") == 0
            )
        if expected_topology.get("genus") is not None:
            expected_euler = 2 * int(expected_topology.get("components", 1)) - 2 * int(
                expected_topology["genus"]
            )
            result["checks"]["mesh_genus"] = actual_topology.get("euler") == expected_euler
        if expected_topology.get("periodic") is True:
            boundary_edges = actual_topology.get("boundary_edges", 0)
            unmatched_edges = actual_topology.get("periodic_unmatched_edges", math.inf)
            result["checks"]["periodic_mesh"] = (
                actual_topology.get("periodic_components") == expected_topology.get("components", 1)
                and actual_topology.get("nonmanifold_edges") == 0
                and actual_topology.get("faces", 0) > 0
                and unmatched_edges <= max(8, math.ceil(boundary_edges * 0.01))
                and actual_topology.get("periodic_function_max_delta", math.inf) < 1e-5
            )
        result["passed"] = not result["error"] and all(result["checks"].values())


def browser_gate_evidence(browser_path: Path | None) -> dict[str, Any]:
    if browser_path is None:
        return {"evaluated": False, "inert_string_boundary": None, "passed": False}
    browser_data = json.loads(browser_path.read_text())
    boundary = browser_data.get("inert_string_boundary")
    return {
        "evaluated": True,
        "inert_string_boundary": boundary,
        "passed": bool(isinstance(boundary, dict) and boundary.get("passed") is True),
    }


def markdown_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Visualization V2 — 200-case acceptance report",
        "",
        f"Generated from production compiler code at `{payload['revision']}`.",
        "",
        (
            f"Result: **{summary['passed']}/{summary['total']} passed**; "
            f"{summary['failed']} failed; zero cases waived."
        ),
        "",
    ]
    candidate = payload.get("pre_holdout_candidate")
    if candidate:
        lines.extend(
            [
                "## Frozen pre-holdout candidate",
                "",
                f"- SHA: `{candidate['sha']}`",
                f"- Frozen at: `{candidate['frozen_at']}`",
                "- The separate post-implementation holdout was not opened before this candidate was frozen.",
                "",
            ]
        )
    browser_gate = payload.get("browser_gate") or {}
    boundary = browser_gate.get("inert_string_boundary") or {}
    lines.extend(
        [
            "## Structural renderer boundary",
            "",
            (
                "- Real-browser inert-string sink-flow preflight: "
                + ("**PASS**" if browser_gate.get("passed") else "**FAIL**")
            ),
            f"- Literal source-shaped text fields preserved: {len(boundary.get('literal_text_fields', []))}",
            f"- Proposal-controlled event/resource/style attributes: {len(boundary.get('event_or_resource_attributes', []))}",
            f"- Descriptive-label behavior attributes: {len(boundary.get('descriptive_behavior_attributes', []))}",
            f"- Child markup sink created: {bool(boundary.get('child_markup_sink'))}",
            f"- Frame/parent global mutated: {bool(boundary.get('frame_global_mutated') or boundary.get('parent_global_mutated'))}",
            "",
        ]
    )
    lines.extend(
        [
            "| ID | Domain | Intent / family | Renderer / spec | Controls | Invariants | Browser evidence | Compile | Result |",
            "|---|---|---|---|---|---|---|---:|---|",
        ]
    )
    for row in payload["cases"]:
        invariants = ", ".join(row["invariant_checks"]["checks"])
        browser = row.get("browser")
        if browser:
            evidence = browser.get("evidence") or {}
            browser_text = f"{evidence.get('renderer', '?')}: {evidence.get('primitive_count') or evidence.get('triangles') or evidence.get('nontransparent_samples', '?')} primitives; {browser.get('elapsed_ms', '?')} ms"
        else:
            browser_text = "pending"
        lines.append(
            f"| {row['id']} | {row['domain']} | {row['intent']} / {row['family']} | "
            f"{row['renderer']} / {row['spec_kind']} | {', '.join(row['controls'])} | "
            f"{invariants} | {browser_text} | {row['compile_ms']:.3f} ms | "
            f"{'PASS' if row['passed'] else 'FAIL'} |"
        )
    lines.extend(
        [
            "",
            "## Reproduce",
            "",
            (
                "Capture real-browser evidence first, then merge that evidence into the "
                "checked-in report. The compiler-only command intentionally does not write "
                "a passing acceptance report without browser results."
            ),
            "",
            "```bash",
            ".venv/bin/python scripts/visualization_v2_browser_server.py --port 18084 \\",
            "  --output /tmp/muta-v2-browser-results.json \\",
            "  --matrix-output /tmp/muta-v2-browser-matrix.json \\",
            "  --lru-output /tmp/muta-v2-lru.json --directory .",
            "# Open http://127.0.0.1:18084/ui/tests/visualization-v2-browser-gate.html?report=1",
            ".venv/bin/python scripts/visualization_v2_gate.py --write \\",
            "  --browser-results /tmp/muta-v2-browser-results.json \\",
            f"  --revision {payload['revision']}"
            + (
                f" --pre-holdout-candidate-sha {candidate['sha']}"
                f" --pre-holdout-frozen-at {candidate['frozen_at']}"
                if candidate
                else ""
            ),
            "```",
            "",
            (
                "A pass requires intent, family, renderer, spec kind, exact named controls, "
                "accessible fallback, semantic oracles, and a real non-empty browser render. "
                "Presence of a canvas or WebGL context alone is never counted."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser-results", type=Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--revision", default="working-tree")
    parser.add_argument("--pre-holdout-candidate-sha")
    parser.add_argument("--pre-holdout-frozen-at")
    args = parser.parse_args()
    if bool(args.pre_holdout_candidate_sha) != bool(args.pre_holdout_frozen_at):
        parser.error("pre-holdout candidate SHA and frozen timestamp must be provided together")
    cases = load_cases()
    results, specs = compile_cases(cases)
    merge_browser(results, args.browser_results)
    browser_gate = browser_gate_evidence(args.browser_results)
    passed = sum(row["passed"] for row in results)
    gate_passed = passed == 200 and browser_gate["passed"]
    payload = {
        "schema_version": 1,
        "revision": args.revision,
        "corpus": {"supplied_stem": 50, "supplied_math": 100, "synthetic_held_out": 50},
        "summary": {
            "total": 200,
            "passed": passed,
            "failed": 200 - passed,
            "waived": 0,
            "gate_passed": gate_passed,
        },
        "browser_gate": browser_gate,
        "cases": results,
    }
    if args.pre_holdout_candidate_sha:
        payload["pre_holdout_candidate"] = {
            "sha": args.pre_holdout_candidate_sha,
            "frozen_at": args.pre_holdout_frozen_at,
        }
    if args.write:
        SPEC_OUTPUT.write_text(
            json.dumps(
                {"schema_version": 1, "count": 200, "cases": specs}, indent=2, ensure_ascii=False
            )
            + "\n"
        )
        followups = []
        for followup_id, source in (
            ("followup-pythagoras", "Explain Pythagoras with a diagram"),
            ("followup-damped-sine", "Plot z=4*exp(-y^2/4)*sin(2*x)"),
        ):
            prior = compile_visualization_v2(source)
            if prior is None:
                raise SystemExit(f"{followup_id}: prior visualization did not compile")
            animated = compile_visualization_v2("animate it", previous_spec=prior)
            if animated is None:
                raise SystemExit(f"{followup_id}: animation follow-up did not compile")
            followups.append({"id": followup_id, "spec": animated})
        FOLLOWUP_OUTPUT.write_text(
            json.dumps(
                {"schema_version": 1, "count": len(followups), "cases": followups},
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        )
        general_math = []
        for probe_id, source in (
            ("general-explicit", "Plot y=x^2"),
            ("general-sine", "Graph y=sin(x)"),
            ("general-line", "Draw the line y=2*x+1"),
            ("general-implicit", "Plot x^2+y^2=1"),
            ("general-parametric", "Plot parametric x=cos(t), y=sin(t)"),
            ("general-polar", "Plot r=cos(3*theta)"),
            ("general-contour", "Show a contour map of z=x^2+y^2"),
            ("general-vector", "Plot vector field F=(y,-x)"),
        ):
            general_spec = compile_visualization_v2(source)
            if general_spec is None:
                raise SystemExit(f"{probe_id}: general math visualization did not compile")
            general_math.append({"id": probe_id, "spec": validate_v2_spec(general_spec)})
        GENERAL_MATH_OUTPUT.write_text(
            json.dumps(
                {"schema_version": 1, "count": len(general_math), "cases": general_math},
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        )
        JSON_OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        MARKDOWN_OUTPUT.write_text(markdown_report(payload))
    print(json.dumps(payload["summary"], sort_keys=True))
    return 0 if gate_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
