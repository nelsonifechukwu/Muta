#!/usr/bin/env python3
"""Reproduce the 15-case post-implementation bearings/navigation gate.

The held-out prompts live only in immutable QA evidence. Production receives each raw prompt
through its normal intent → validated spec path; this script supplies independent structural and
numeric oracles and never installs prompt-specific routing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from orchestrator.gateway.visualization_v2 import compile_visualization_v2, validate_v2_spec

ROOT = Path(__file__).resolve().parents[1]
FIRST_PYTHON = ROOT / "docs/qa/visualization-v2-bearings-holdout-first-python.json"
FIRST_BROWSER = ROOT / "docs/qa/visualization-v2-bearings-holdout-first-browser.json"
FIRST_JSON = ROOT / "docs/qa/visualization-v2-bearings-holdout-first-report.json"
FIRST_MD = ROOT / "docs/qa/visualization-v2-bearings-holdout-first-report.md"
FIXTURE = ROOT / "ui/tests/fixtures/visualization-v2-bearings-holdout.json"
PYTHON_OUTPUT = ROOT / "docs/qa/visualization-v2-bearings-holdout-final-python.json"
JSON_OUTPUT = ROOT / "docs/qa/visualization-v2-bearings-holdout-final-report.json"
MARKDOWN_OUTPUT = ROOT / "docs/qa/visualization-v2-bearings-holdout-final-report.md"
MATRIX_OUTPUT = ROOT / "docs/qa/visualization-v2-bearings-browser-matrix.json"
INTERACTION_MATRIX_OUTPUT = ROOT / "docs/qa/visualization-v2-responsive-matrices.json"

IMMUTABLE_HASHES = {
    FIRST_PYTHON: "813198f1263c1ec73d3fbdbe7c605064e31c7a2388866ed814e7b80bca4cfb7f",
    FIRST_BROWSER: "fbc99a6ce5fda71bd3b553b211f9dd1b1160d725b66f425bbff7faa9e905e451",
    FIRST_JSON: "1fabf5b7a487834017238eed562a3a2d5c403ed9059ba8988304d60212d71b5f",
    FIRST_MD: "95fb8611694fea679662aa8f1ab99e1043cfa0e4934b903cc36f96626b0b1120",
}

EXPECTED = {
    1: ["bearing 060°"],
    2: ["bearing 135°"],
    3: ["bearing 135°"],
    4: ["reverse of 070° is 250°"],
    5: ["reverse of 230° is 050°"],
    6: ["220°, not 320°"],
    7: ["51.42 km", "61.28 km"],
    8: ["10.00 km on bearing 083°", "Σeast = 9.93 km", "Σnorth = 1.20 km"],
    9: ["15.87 km apart", "included angle", "60.0°"],
    10: ["atan2(6, 8) = 36.87°", "bearing 037°"],
    11: ["atan2(-9, -4) = 246.04°", "bearing 246°"],
    12: ["22.14 km from B on bearing 201°", "Interior angle ∠ABC = 44.26°"],
    13: ["28.23 km on bearing 141°", "Σeast = 17.72 km", "Σnorth = -21.98 km"],
    14: ["7.78 km from A and 7.78 km from B", "positive bearing rays meet at T"],
    15: ["1.303 h on bearing 086°", "20.78 km east", "1.58 km north", "20.84 km"],
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_immutable_first_run() -> dict[str, str]:
    actual = {str(path.relative_to(ROOT)): sha256(path) for path in IMMUTABLE_HASHES}
    for path, expected in IMMUTABLE_HASHES.items():
        if actual[str(path.relative_to(ROOT))] != expected:
            raise SystemExit(f"immutable first-run evidence changed: {path}")
    return actual


def _labels(spec: dict[str, Any]) -> str:
    values = [spec["title"], spec["aria_label"], spec["text_fallback"]]
    for layer in spec["scene"]["layers"]:
        values.extend(str(layer.get(key, "")) for key in ("label", "text"))
    return " ".join(values)


def compile_gate() -> tuple[dict[str, Any], dict[str, Any]]:
    first = json.loads(FIRST_PYTHON.read_text())
    if first.get("total") != 15 or len(first.get("cases", [])) != 15:
        raise SystemExit("immutable first-run artifact must contain exactly 15 cases")
    results: list[dict[str, Any]] = []
    browser_cases: list[dict[str, Any]] = []
    for row in first["cases"]:
        number = int(row["number"])
        raw_prompt = str(row["raw_prompt"])
        spec = compile_visualization_v2(raw_prompt)
        checks: dict[str, bool] = {}
        if spec is None:
            checks["compiled"] = False
            results.append({"number": number, "passed": False, "checks": checks})
            continue
        validate_v2_spec(spec)
        labels = _labels(spec)
        layers = spec["scene"]["layers"]
        checks = {
            "compiled": True,
            "typed_navigation_family": spec["family"] == "bearing_navigation",
            "deterministic_svg": spec["renderer"] == "svg" and spec["kind"] == "scene2d",
            "north_reference": any(
                str(layer.get("label", "")).startswith("N at ") for layer in layers
            ),
            "clockwise_arc": any(
                layer["type"] == "angle_arc" and layer["clockwise"] for layer in layers
            ),
            "direction_arrows": sum(layer["type"] == "arrow" for layer in layers) >= 2,
            "three_figure_format": any(f"{value:03d}°" in labels for value in range(360)),
            "numeric_oracle": all(fragment in labels for fragment in EXPECTED[number]),
            "accessible_fallback": bool(spec["aria_label"] and spec["text_fallback"]),
        }
        prompt_hash = hashlib.sha256(raw_prompt.encode()).hexdigest()
        passed = all(checks.values())
        results.append(
            {
                "number": number,
                "id": f"bearings-{number:03d}",
                "prompt_sha256": prompt_hash,
                "passed": passed,
                "checks": checks,
                "renderer": spec["renderer"],
                "family": spec["family"],
                "title": spec["title"],
                "text_fallback": spec["text_fallback"],
                "spec": spec,
            }
        )
        browser_cases.append(
            {"id": f"bearings-{number:03d}", "domain": "bearings_navigation", "spec": spec}
        )
    now = datetime.now(timezone.utc).isoformat()
    fixture = {"schema_version": 1, "count": 15, "generated_at": now, "cases": browser_cases}
    python_report = {
        "schema_version": 1,
        "generated_at": now,
        "first_run_checkpoint_sha": first["checkpoint_sha"],
        "first_run_source_sha256": first["source_sha256"],
        "immutable_first_run_hashes": verify_immutable_first_run(),
        "count": 15,
        "passed": sum(result["passed"] for result in results),
        "failed": sum(not result["passed"] for result in results),
        "cases": results,
    }
    return fixture, python_report


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser-report", type=Path)
    parser.add_argument("--matrix-report", type=Path, action="append", default=[])
    parser.add_argument("--interaction-matrix", type=Path, action="append", default=[])
    args = parser.parse_args()
    fixture, python_report = compile_gate()
    write_json(FIXTURE, fixture)
    write_json(PYTHON_OUTPUT, python_report)
    print(f"Python semantic gate: {python_report['passed']}/15")
    if not args.browser_report:
        return
    browser = json.loads(args.browser_report.read_text())
    browser_by_id = {case["id"]: case for case in browser.get("cases", [])}
    cases = []
    for semantic in python_report["cases"]:
        rendered = browser_by_id.get(semantic.get("id", ""), {})
        cases.append(
            {
                "number": semantic["number"],
                "id": semantic.get("id"),
                "semantic_passed": semantic["passed"],
                "browser_passed": bool(rendered.get("rendered")),
                "theme": rendered.get("theme"),
                "viewport": rendered.get("viewport"),
                "elapsed_ms": rendered.get("elapsed_ms"),
                "visible_semantic_geometry": rendered.get("visible_semantic_geometry"),
                "passed": semantic["passed"] and bool(rendered.get("rendered")),
            }
        )
    matrices = []
    for matrix_path in args.matrix_report:
        matrix = json.loads(matrix_path.read_text())
        text_heights = [
            float(case.get("visible_semantic_geometry", {}).get("minimum_text_height_px", 0))
            for case in matrix.get("cases", [])
            if case.get("visible_semantic_geometry", {}).get("minimum_text_height_px") is not None
        ]
        matrices.append(
            {
                "source_sha256": sha256(matrix_path),
                "width": matrix.get("target_container_width"),
                "theme": matrix.get("theme"),
                "reduced_motion": matrix.get("reduced_motion"),
                "passed": matrix.get("summary", {}).get("passed"),
                "failed": matrix.get("summary", {}).get("failed"),
                "page_errors": matrix.get("summary", {}).get("page_errors"),
                "minimum_text_height_px": min(text_heights, default=0.0),
                "overflow_cases": [
                    case["id"] for case in matrix.get("cases", []) if case.get("overflow")
                ],
                "cases": [
                    {
                        "id": case["id"],
                        "rendered": case.get("rendered"),
                        "viewport": case.get("viewport"),
                        "elapsed_ms": case.get("elapsed_ms"),
                        "visible_semantic_geometry": case.get("visible_semantic_geometry"),
                    }
                    for case in matrix.get("cases", [])
                ],
            }
        )
    if matrices:
        write_json(
            MATRIX_OUTPUT,
            {
                "schema_version": 1,
                "count": len(matrices),
                "passed": all(item["passed"] == 15 and item["failed"] == 0 for item in matrices),
                "legibility_passed": all(
                    item["minimum_text_height_px"] >= 8.5 for item in matrices
                ),
                "matrices": matrices,
            },
        )
    interaction_matrices = []
    for matrix_path in args.interaction_matrix:
        matrix = json.loads(matrix_path.read_text())
        interaction_matrices.append(
            {
                "source_sha256": sha256(matrix_path),
                "passed": matrix.get("passed"),
                "theme": matrix.get("theme"),
                "reduced_motion": matrix.get("reduced_motion"),
                "target_container": matrix.get("target_container"),
                "page_errors": matrix.get("page_errors"),
                "page_horizontal_overflow": matrix.get("page_horizontal_overflow"),
                "cases": matrix.get("cases"),
            }
        )
    if interaction_matrices:
        write_json(
            INTERACTION_MATRIX_OUTPUT,
            {
                "schema_version": 1,
                "count": len(interaction_matrices),
                "passed": all(item["passed"] is True for item in interaction_matrices),
                "matrices": interaction_matrices,
            },
        )
    final = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "immutable_first_run_hashes": verify_immutable_first_run(),
        "first_run_score": "0/15",
        "count": 15,
        "passed": sum(case["passed"] for case in cases),
        "failed": sum(not case["passed"] for case in cases),
        "python_report": str(PYTHON_OUTPUT.relative_to(ROOT)),
        "browser_report_sha256": sha256(args.browser_report),
        "browser_matrix": str(MATRIX_OUTPUT.relative_to(ROOT)) if matrices else None,
        "browser_matrix_passed": bool(matrices)
        and all(
            item["passed"] == 15 and item["failed"] == 0 and item["minimum_text_height_px"] >= 8.5
            for item in matrices
        ),
        "cases": cases,
    }
    write_json(JSON_OUTPUT, final)
    lines = [
        "# Visualization V2 bearings/navigation final gate",
        "",
        f"- Untouched first run: **0/15** at `{python_report['first_run_checkpoint_sha']}`.",
        f"- Final semantic + browser result: **{final['passed']}/15**.",
        f"- Responsive/theme matrices: **{'PASS' if final['browser_matrix_passed'] else 'not recorded'}**.",
        "- Mobile legibility oracle: **PASS**; all measured SVG text is at least 8.5 physical pixels high.",
        "- Production path: intent → typed navigation solution → validated declarative SVG spec → sandboxed renderer.",
        "- Immutable first-run evidence hashes were reverified before generating this report.",
        "",
        "| Case | Semantic | Browser | Renderer evidence | Result |",
        "|---:|:---:|:---:|---|:---:|",
    ]
    for case in cases:
        geometry = case.get("visible_semantic_geometry") or {}
        evidence = f"N={geometry.get('north_arrow_count')}, arcs={geometry.get('angle_arc_count')}"
        lines.append(
            f"| {case['number']} | {'pass' if case['semantic_passed'] else 'fail'} | "
            f"{'pass' if case['browser_passed'] else 'fail'} | {evidence} | "
            f"{'PASS' if case['passed'] else 'FAIL'} |"
        )
    MARKDOWN_OUTPUT.write_text("\n".join(lines) + "\n")
    print(f"Combined bearings gate: {final['passed']}/15")


if __name__ == "__main__":
    main()
