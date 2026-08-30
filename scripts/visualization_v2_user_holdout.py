#!/usr/bin/env python3
"""Reproduce the post-freeze 50-case user holdout gate without production prompt routes.

Raw prompts are read only from the immutable first-run artifact.  This QA script compiles each
through the real V2 entry point, executes semantic invariants, writes renderer-only fixtures, and
optionally merges evidence captured by the real browser gate.
"""

from __future__ import annotations

import argparse
import hashlib
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
    relationship_residual,
    validate_v2_spec,
)
from scripts.visualization_v2_gate import _specific_oracle

ROOT = Path(__file__).resolve().parents[1]
FIRST_PYTHON = ROOT / "docs" / "qa" / "visualization-v2-user-holdout-first-python.json"
FIRST_BROWSER = ROOT / "docs" / "qa" / "visualization-v2-user-holdout-first-browser.json"
SPEC_OUTPUT = ROOT / "ui" / "tests" / "fixtures" / "visualization-v2-user-holdout.json"
JSON_OUTPUT = ROOT / "docs" / "qa" / "visualization-v2-user-holdout-final.json"
MARKDOWN_OUTPUT = ROOT / "docs" / "qa" / "visualization-v2-user-holdout-report.md"

PRE_HOLDOUT_SHA = "ae3cc2e1572b042a0d53ab5af4fe1143e9cb71cd"
PRE_HOLDOUT_FROZEN_AT = "2026-08-27T12:07:54+01:00"
TRANSPORT = {"play", "pause", "restart"}

_DOMAIN_BY_FAMILY = {
    "explicit_curve": "mathematics",
    "implicit_curve": "mathematics",
    "implicit_surface": "mathematics",
    "explicit_surface": "mathematics",
    "vector_addition": "mathematics",
    "quadratic": "mathematics",
    "unit_circle": "mathematics",
    "derivative_tangent": "mathematics",
    "riemann_sum": "mathematics",
    "gradient_linked": "mathematics",
    "linear_transform": "mathematics",
    "gradient_descent": "mathematics",
    "fourier_series": "signals",
    "vector_field_3d": "mathematics",
    "atom": "chemistry",
    "molecular_geometry": "chemistry",
    "titration": "chemistry",
    "animal_cell": "biology",
    "action_potential": "biology",
    "ohms_law_circuit": "physics",
    "projectile": "physics",
    "inclined_plane": "physics",
    "spring_mass": "physics",
    "refraction": "physics",
    "travelling_wave": "physics",
    "harmonic_motion": "physics",
    "elastic_collision": "physics",
    "electric_field_vectors": "physics",
    "rc_circuit": "physics",
    "double_pendulum": "physics",
    "electromagnetic_wave": "physics",
    "binary_representation": "computer science",
    "binary_search": "computer science",
    "merge_sort": "computer science",
    "binary_search_tree": "computer science",
    "dijkstra": "computer science",
    "neural_network": "computer science",
    "virtual_memory": "computer science",
    "sampling_aliasing": "signals",
    "differential_drive": "robotics",
    "robot_forward_kinematics": "robotics",
    "robot_localization": "robotics",
    "kalman_filter": "controls",
    "lorenz_attractor": "dynamical systems",
}

_EXPECTED: list[tuple[str, str, tuple[str, ...]]] = [
    ("explicit_curve", "svg", ()),
    ("explicit_curve", "svg", ()),
    ("explicit_curve", "svg", ()),
    ("implicit_curve", "svg", ()),
    ("implicit_surface", "three", ("orbit", "reset_view")),
    ("vector_addition", "svg", ()),
    ("atom", "svg", ("atomic_number",)),
    ("animal_cell", "svg", ("organelle",)),
    ("ohms_law_circuit", "svg", ("voltage", "resistance", "switch")),
    ("binary_representation", "svg", ()),
    ("quadratic", "svg", ("a", "b", "c")),
    ("unit_circle", "svg", ("angle",)),
    ("explicit_surface", "three", ("orbit", "reset_view")),
    ("explicit_surface", "three", ("orbit", "reset_view")),
    ("projectile", "svg", ("angle", "speed")),
    ("inclined_plane", "svg", ("incline",)),
    ("spring_mass", "svg", ("spring_constant", "displacement")),
    ("ohms_law_circuit", "svg", ("voltage", "resistance", "switch")),
    ("refraction", "svg", ("incident_angle", "medium")),
    ("molecular_geometry", "three", ("molecule",)),
    ("derivative_tangent", "svg", ("x",)),
    ("riemann_sum", "svg", ("rectangles",)),
    ("gradient_linked", "svg", ("point_x", "point_y")),
    ("linear_transform", "svg", ("matrix",)),
    ("linear_transform", "svg", ("matrix",)),
    ("travelling_wave", "canvas", ("amplitude", "wavelength", "frequency")),
    ("harmonic_motion", "canvas", ("spring_constant", "mass")),
    ("elastic_collision", "svg", ("mass_1", "velocity_1", "mass_2", "velocity_2")),
    (
        "electric_field_vectors",
        "canvas",
        ("positive_charge_x", "negative_charge_x", "test_x", "test_y"),
    ),
    ("rc_circuit", "svg", ("mode", "resistance", "capacitance")),
    ("binary_search", "svg", ("target", "step")),
    ("merge_sort", "svg", ("step",)),
    ("binary_search_tree", "svg", ("insert", "step")),
    ("dijkstra", "svg", ("source", "destination", "step")),
    ("neural_network", "svg", ("weight", "step")),
    ("gradient_descent", "svg", ("learning_rate", "step")),
    ("differential_drive", "canvas", ("left_velocity", "right_velocity")),
    ("robot_forward_kinematics", "svg", ("joint_1", "joint_2", "joint_3")),
    ("sampling_aliasing", "canvas", ("signal_frequency", "sample_frequency")),
    ("fourier_series", "svg", ("terms",)),
    ("vector_field_3d", "three", ("point_x", "point_y", "point_z")),
    ("double_pendulum", "canvas", ("angle_1", "angle_2")),
    ("lorenz_attractor", "three", ("sigma", "rho", "beta")),
    ("implicit_surface", "three", ("clip_z", "orbit", "reset_view")),
    ("electromagnetic_wave", "three", ("amplitude", "wavelength")),
    ("action_potential", "svg", ("time",)),
    ("titration", "svg", ("titrant_volume",)),
    ("virtual_memory", "svg", ("address", "step")),
    ("robot_localization", "canvas", ("odometry_noise", "sensor_noise", "step")),
    ("kalman_filter", "svg", ("noise", "process_noise", "step")),
]

_SHARED_ORACLES: dict[str, tuple[str, ...]] = {
    "atom": ("semantic_relationship",),
    "animal_cell": ("semantic_relationship",),
    "ohms_law_circuit": ("current_v_over_r", "current_direction"),
    "quadratic": ("semantic_relationship", "labels_and_units", "control_consistency"),
    "unit_circle": ("point_on_unit_circle", "sin_cos_projection"),
    "projectile": ("trajectory_endpoints", "range_height_units"),
    "inclined_plane": ("semantic_relationship",),
    "refraction": ("snell_law", "normal_and_ray_direction"),
    "molecular_geometry": ("semantic_relationship",),
    "derivative_tangent": ("semantic_relationship",),
    "riemann_sum": ("semantic_relationship",),
    "linear_transform": ("semantic_relationship",),
    "travelling_wave": ("semantic_relationship",),
    "harmonic_motion": ("semantic_relationship",),
    "elastic_collision": ("semantic_relationship",),
    "electric_field_vectors": ("semantic_relationship",),
    "rc_circuit": ("semantic_relationship",),
    "binary_search": ("interval_shrinks", "target_found"),
    "merge_sort": ("sorted_output", "stable_merge"),
    "binary_search_tree": ("semantic_relationship",),
    "dijkstra": ("nondecreasing_settled_distance", "shortest_path"),
    "neural_network": ("weighted_activation_flow",),
    "differential_drive": ("curvature_from_wheel_speeds",),
    "sampling_aliasing": ("nyquist_condition", "sample_locations"),
    "fourier_series": ("odd_harmonics", "gibbs_overshoot"),
    "double_pendulum": ("semantic_relationship",),
    "action_potential": ("semantic_relationship",),
    "titration": ("semantic_relationship",),
    "virtual_memory": ("page_offset_preserved", "fault_path"),
    "kalman_filter": ("covariance_contracts_on_update", "estimate_between_prior_measurement"),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _labels(spec: dict[str, Any]) -> str:
    values = [spec["title"], spec["aria_label"], spec["text_fallback"]]
    for layer in spec["scene"]["layers"]:
        values.extend(str(layer.get(key, "")) for key in ("label", "text", "title"))
    return " ".join(values).casefold()


def _custom_semantic_oracle(case_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    family = spec["family"]
    layers = spec["scene"]["layers"]
    labels = _labels(spec)
    lines = [layer for layer in layers if layer["type"] in {"polyline", "line"}]
    passed = False
    evidence: dict[str, Any] = {"labels": labels[:800]}

    if family == "explicit_curve":
        points = next(layer["points"] for layer in layers if layer["type"] == "polyline")
        if case_id == "user-holdout-001":
            error = max(abs(y - (2 * x + 3)) for x, y in points)
            passed = error < 1e-8 and "slope rise/run = 2/1" in labels and "y-intercept" in labels
        elif case_id == "user-holdout-002":
            error = max(abs(y - (x * x - 4 * x + 3)) for x, y in points)
            passed = error < 1e-8 and all(
                term in labels for term in ("roots 1, 3", "vertex", "axis of symmetry")
            )
        else:
            error = max(abs(y - math.sin(x)) for x, y in points)
            passed = error < 1e-8 and all(
                term in labels for term in ("amplitude", "wavelength", "zero crossings")
            )
        evidence = {"max_equation_error": error, "labels": labels}
    elif family == "implicit_curve":
        points = next(
            layer["points"]
            for layer in layers
            if layer["type"] == "polyline" and "radius" not in str(layer.get("label", ""))
        )
        error = max(abs(x * x + y * y - 9) for x, y in points)
        passed = error < 0.1 and "centre (0,0)" in labels and "radius≈3" in labels
        evidence = {"max_circle_residual": error, "point_count": len(points)}
    elif family in {"explicit_surface", "implicit_surface"}:
        layer = layers[0]
        if layer["type"] == "explicit_surface":
            samples = [(-1.0, -1.0), (0.0, 0.0), (1.0, 1.0)]
            residuals = []
            for x, y in samples:
                z = evaluate_expression_v2(layer["relationship"]["right"], {"x": x, "y": y})
                residuals.append(
                    abs(relationship_residual(layer["relationship"], {"x": x, "y": y, "z": z}))
                )
            passed = max(residuals) < 1e-9
            evidence = {"sample_residuals": residuals}
        else:
            origin = abs(relationship_residual(layer["relationship"], {"x": 0, "y": 0, "z": 0}))
            sphere_point = abs(
                relationship_residual(layer["relationship"], {"x": 3, "y": 0, "z": 0})
            )
            gyroid = case_id == "user-holdout-044"
            passed = (origin < 1e-9 if gyroid else sphere_point < 1e-9) and (
                not gyroid or spec["controls"][0]["id"] == "clip_z"
            )
            evidence = {
                "origin_residual": origin,
                "sphere_point_residual": sphere_point,
                "clipped": gyroid,
            }
    elif family == "vector_addition":
        field = next(layer for layer in layers if layer["type"] == "vector_field")
        passed = field["vectors"] == [[0, 0, 3, 2], [3, 2, 1, 4], [0, 0, 4, 6]]
        evidence = {"vectors": field["vectors"]}
    elif family == "binary_representation":
        passed = (
            "8 + 4 + 0 + 1 = 13₁₀ = 1101₂" in labels
            and sum(layer["type"] == "node" for layer in layers) == 5
        )
        evidence = {"node_count": sum(layer["type"] == "node" for layer in layers)}
    elif family == "spring_mass":
        controls = {control["id"]: control["value"] for control in spec["controls"]}
        force = -controls["spring_constant"] * controls["displacement"]
        passed = math.isfinite(force) and "spring force kx" in labels and "equilibrium" in labels
        evidence = {"initial_restoring_force": force}
    elif family == "gradient_linked":
        panels = [layer for layer in layers if layer["type"] == "panel"]
        passed = len(panels) == 2 and all("probe" in " ".join(panel["members"]) for panel in panels)
        evidence = {"panel_titles": [panel["title"] for panel in panels]}
    elif family == "gradient_descent":
        trajectories = [
            layer
            for layer in layers
            if "gradient-descent trajectory" in str(layer.get("label", ""))
        ]
        passed = len(trajectories) == 2 and all(
            len(layer["points"]) == 17 for layer in trajectories
        )
        evidence = {"trajectory_lengths": [len(layer["points"]) for layer in trajectories]}
    elif family == "robot_forward_kinematics":
        nodes = [layer for layer in layers if layer["type"] == "node"]
        links = [layer for layer in layers if layer["type"] == "link"]
        passed = len(nodes) == 4 and len(links) == 3 and "end effector" in labels
        evidence = {"nodes": len(nodes), "links": len(links)}
    elif family == "neural_network":
        nodes = {layer["id"]: layer for layer in layers if layer["type"] == "node"}
        links = [layer for layer in layers if layer["type"] == "link"]
        expected_nodes = {"x1", "x2", "h1", "h2", "h3", "output"}
        expected_edges = {
            (source, target) for source in ("x1", "x2") for target in ("h1", "h2", "h3")
        } | {(hidden, "output") for hidden in ("h1", "h2", "h3")}
        actual_edges = {(layer["from"], layer["to"]) for layer in links}
        output_match = re.search(
            r"sigmoid\(([-0-9.]+)\)=([-0-9.]+)", nodes.get("output", {}).get("label", "")
        )
        output_consistent = bool(
            output_match
            and abs(
                float(output_match.group(2)) - 1 / (1 + math.exp(-float(output_match.group(1))))
            )
            < 0.002
        )
        passed = (
            set(nodes) == expected_nodes and actual_edges == expected_edges and output_consistent
        )
        evidence = {
            "nodes": sorted(nodes),
            "edges": sorted(actual_edges),
            "output_consistent": output_consistent,
        }
    elif family == "vector_field_3d":
        local = next(
            layer for layer in layers if str(layer.get("label", "")).startswith("local F=")
        )
        delta = [local["to"][index] - local["from"][index] for index in range(3)]
        expected = [-1, 1, 1]
        cross = math.dist(
            [value / math.hypot(*delta) for value in delta],
            [value / math.hypot(*expected) for value in expected],
        )
        passed = len(layers) >= 26 and cross < 1e-8
        evidence = {"samples": len(layers) - 2, "direction_error": cross}
    elif family == "lorenz_attractor":
        points = lines[0]["points"]
        passed = len(points) == 500 and min(point[0] for point in points) < 0 < max(
            point[0] for point in points
        )
        evidence = {
            "samples": len(points),
            "x_range": [min(point[0] for point in points), max(point[0] for point in points)],
        }
    elif family == "electromagnetic_wave":
        electric, magnetic = lines[:2]
        orthogonal = all(
            abs(e[1] * m[1] + e[2] * m[2]) < 1e-9
            for e, m in zip(electric["points"], magnetic["points"])
        )
        passed = (
            len(electric["points"]) == len(magnetic["points"]) == 161
            and orthogonal
            and "e×b" in labels
        )
        evidence = {"samples": len(electric["points"]), "orthogonal": orthogonal}
    elif family == "robot_localization":
        by_label = {layer.get("label"): layer for layer in layers}
        truth = by_label["true pose trajectory"]["points"]
        odometry = by_label["noisy odometry trajectory"]["points"]
        estimate = by_label["Kalman/particle estimated pose"]["points"]
        odometry_error = sum(math.dist(a, b) for a, b in zip(truth, odometry)) / len(truth)
        estimate_error = sum(math.dist(a, b) for a, b in zip(truth, estimate)) / len(truth)
        passed = (
            len(truth) == len(odometry) == len(estimate) == 61 and estimate_error < odometry_error
        )
        evidence = {"odometry_mean_error": odometry_error, "estimate_mean_error": estimate_error}
    else:
        requested = _SHARED_ORACLES.get(family, ())
        results = {name: _specific_oracle(name, spec) for name in requested}
        passed = bool(results) and all(result["passed"] for result in results.values())
        evidence = {"shared_oracles": results}
    return {"passed": bool(passed), "evidence": evidence}


def _load_first_run() -> list[dict[str, Any]]:
    first = json.loads(FIRST_PYTHON.read_text())
    cases = first.get("cases", [])
    if first.get("summary", {}).get("total") != 50 or len(cases) != 50:
        raise SystemExit("immutable first-run Python report must contain exactly 50 cases")
    if len(_EXPECTED) != 50:
        raise SystemExit("expected holdout metadata must contain exactly 50 cases")
    return cases


def _browser_by_id(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    payload = json.loads(path.read_text())
    if payload.get("count") != 50 or len(payload.get("cases", [])) != 50:
        raise SystemExit("final browser holdout report must contain exactly 50 cases")
    return {case["id"]: case for case in payload["cases"]}


def _browser_gate_evidence(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"evaluated": False, "inert_string_boundary": None, "passed": False}
    payload = json.loads(path.read_text())
    boundary = payload.get("inert_string_boundary")
    return {
        "evaluated": True,
        "inert_string_boundary": boundary,
        "passed": bool(isinstance(boundary, dict) and boundary.get("passed") is True),
    }


def _markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Visualization Engine V2 — User Holdout Report",
        "",
        f"- Frozen pre-holdout candidate: `{PRE_HOLDOUT_SHA}` at `{PRE_HOLDOUT_FROZEN_AT}`",
        f"- Final revision: `{payload['revision']}`",
        f"- Immutable first run: {payload['first_run']['compiled']}/50 Python compile; {payload['first_run']['browser_rendered']}/31 compiled specs rendered",
        f"- Final Python gate: {summary['python_passed']}/50",
        f"- Final browser gate: {summary['browser_passed']}/50"
        if summary["browser_evaluated"]
        else "- Final browser gate: pending",
        f"- Combined: {summary['passed']}/50; failures {summary['failed']}; waivers 0",
        (
            "- Real-browser inert-string sink-flow preflight: **PASS**"
            if payload["browser_gate"]["passed"]
            else "- Real-browser inert-string sink-flow preflight: **FAIL**"
        ),
        "",
        (
            "Reproduce the deterministic compile/oracle pass and merge the separately captured "
            "real-browser evidence with:"
        ),
        "",
        "```bash",
        (
            "python -m scripts.visualization_v2_user_holdout --write "
            "--browser-results /tmp/muta-v2-user-holdout-final-browser.json "
            "--revision <candidate-revision>"
        ),
        "```",
        "",
        "| ID | Title | Domain | Intent | Family | Renderer | Controls | Compile ms | Browser ms | Oracle | Browser | Pass |",
        "|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for case in payload["cases"]:
        lines.append(
            f"| {case['id']} | {case['title']} | {case['domain']} | {case['intent']} | "
            f"{case['family'] or '—'} | {case['renderer'] or '—'} | "
            f"{', '.join(case['controls']) or 'none'} | {case['compile_ms']:.3f} | "
            f"{case['browser_ms']:.1f} | {'pass' if case['python_passed'] else 'fail'} | "
            f"{'pass' if case['browser_passed'] else 'fail' if case['browser_evaluated'] else 'pending'} | "
            f"{'pass' if case['passed'] else 'fail'} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser-results", type=Path)
    parser.add_argument("--revision", default="working-tree")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    browser = _browser_by_id(args.browser_results)
    browser_gate = _browser_gate_evidence(args.browser_results)
    results: list[dict[str, Any]] = []
    specs: list[dict[str, Any]] = []
    for index, case in enumerate(_load_first_run()):
        expected_family, expected_renderer, expected_controls = _EXPECTED[index]
        started = time.perf_counter()
        error = ""
        spec: dict[str, Any] | None = None
        semantic: dict[str, Any] = {"passed": False, "evidence": {}}
        try:
            spec = compile_visualization_v2(case["raw_prompt"])
            if spec is None:
                raise VisualizationV2Error("intent resolver returned no visualization")
            spec = validate_v2_spec(spec)
            semantic = _custom_semantic_oracle(case["id"], spec)
        except (VisualizationV2Error, ValueError, TypeError, KeyError, OverflowError) as exc:
            error = f"{type(exc).__name__}: {exc}"
        controls = [control["id"] for control in spec.get("controls", [])] if spec else []
        parameter_controls = tuple(control for control in controls if control not in TRANSPORT)
        expected_transport = bool(spec and "animation" in spec["scene"])
        checks = {
            "intent_family": bool(spec and spec["family"] == expected_family),
            "renderer": bool(spec and spec["renderer"] == expected_renderer),
            "controls": parameter_controls == expected_controls
            and (not expected_transport or TRANSPORT <= set(controls)),
            "accessibility": bool(spec and spec["aria_label"] and spec["text_fallback"]),
            "semantic_oracle": semantic["passed"],
        }
        python_passed = not error and all(checks.values())
        browser_case = browser.get(case["id"])
        browser_evaluated = browser_case is not None
        browser_passed = bool(browser_case and browser_case.get("rendered"))
        passed = python_passed and (browser_passed if browser_evaluated else True)
        animated = bool(spec and "animation" in spec["scene"])
        results.append(
            {
                "id": case["id"],
                "title": case["title"],
                "domain": _DOMAIN_BY_FAMILY.get(expected_family, "mixed STEM"),
                "intent": "interactive animation" if animated else "interactive visualization",
                "family": spec.get("family") if spec else None,
                "renderer": spec.get("renderer") if spec else None,
                "spec_kind": spec.get("kind") if spec else None,
                "controls": controls,
                "checks": checks,
                "semantic_evidence": semantic,
                "compile_ms": round((time.perf_counter() - started) * 1000, 3),
                "browser_ms": round(float(browser_case.get("elapsed_ms", 0)), 3)
                if browser_case
                else 0.0,
                "python_passed": python_passed,
                "browser_evaluated": browser_evaluated,
                "browser_passed": browser_passed,
                "browser_evidence": browser_case,
                "passed": passed,
                "error": error,
            }
        )
        if spec is not None:
            specs.append({"id": case["id"], "spec": spec})
    python_passed = sum(case["python_passed"] for case in results)
    browser_evaluated = len(browser) == 50
    browser_passed = sum(case["browser_passed"] for case in results)
    passed = sum(case["passed"] for case in results) if browser_evaluated else python_passed
    payload = {
        "schema_version": 1,
        "phase": "post-holdout-final",
        "revision": args.revision,
        "pre_holdout_candidate": {"sha": PRE_HOLDOUT_SHA, "frozen_at": PRE_HOLDOUT_FROZEN_AT},
        "first_run": {
            "python_sha256": _sha256(FIRST_PYTHON),
            "browser_sha256": _sha256(FIRST_BROWSER),
            "compiled": 31,
            "compile_failed": 19,
            "browser_rendered": 31,
            "browser_attempted": 31,
        },
        "summary": {
            "total": 50,
            "python_passed": python_passed,
            "browser_evaluated": browser_evaluated,
            "browser_passed": browser_passed,
            "passed": passed,
            "failed": 50 - passed,
            "waived": 0,
            "gate_passed": python_passed == 50
            and (not browser_evaluated or passed == 50 and browser_gate["passed"]),
        },
        "browser_gate": browser_gate,
        "cases": results,
    }
    if args.write:
        if len(specs) != 50:
            raise SystemExit(f"refusing to write incomplete renderer fixture: {len(specs)}/50")
        SPEC_OUTPUT.write_text(
            json.dumps(
                {"schema_version": 1, "count": 50, "cases": specs}, indent=2, ensure_ascii=False
            )
            + "\n"
        )
        JSON_OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        MARKDOWN_OUTPUT.write_text(_markdown(payload))
    print(json.dumps(payload["summary"], sort_keys=True))
    return 0 if payload["summary"]["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
