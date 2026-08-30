#!/usr/bin/env python3
"""Build reproducible source/browser resource evidence for Visualization Engine V2."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_JSON = ROOT / "docs" / "qa" / "visualization-v2-performance.json"
OUTPUT_MD = ROOT / "docs" / "qa" / "visualization-v2-performance.md"
MATRIX_OUTPUT = ROOT / "docs" / "qa" / "visualization-v2-browser-matrix.json"
LRU_OUTPUT = ROOT / "docs" / "qa" / "visualization-v2-lru.json"
SCREENSHOT_DIR = ROOT / "docs" / "qa" / "screenshots"
SYNC_ASSETS = ("ui/visualizations.js", "ui/viz-frame.js", "ui/viz-frame.css", "ui/viz-frame.html")
SYNC_JS_ASSETS = ("ui/visualizations.js", "ui/viz-frame.js")
LAZY_ASSETS = ("ui/viz-frame-v2.js",)


def _git_bytes(revision: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{revision}:{path}"], cwd=ROOT, capture_output=True, check=False
    )
    return result.stdout if result.returncode == 0 else b""


def _parse_ms(source: bytes) -> float:
    if not source:
        return 0.0
    program = """
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync(0, 'utf8');
const samples = [];
for (let i = 0; i < 80; i += 1) {
  const start = process.hrtime.bigint();
  new vm.Script(`${source}\n// cold-parse-sample-${i}`, { filename: 'muta-ui.js' });
  samples.push(Number(process.hrtime.bigint() - start) / 1e6);
}
samples.sort((a, b) => a - b);
process.stdout.write(String(samples[Math.floor(samples.length / 2)]));
"""
    result = subprocess.run(
        ["node", "-e", program], input=source, cwd=ROOT, capture_output=True, check=True
    )
    return round(float(result.stdout.decode()), 4)


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * quantile))]


def _vendor_bytes() -> int:
    directory = ROOT / "ui" / "vendor" / "viz"
    return sum(path.stat().st_size for path in directory.rglob("*") if path.is_file())


def _screenshot_artifacts() -> list[dict[str, Any]]:
    artifacts = []
    for path in sorted(SCREENSHOT_DIR.glob("*.png")):
        raw = path.read_bytes()
        artifacts.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    return artifacts


def _markdown(payload: dict[str, Any]) -> str:
    source = payload["source_impact"]
    browser = payload["browser"]
    matrix = payload["responsive_matrix"]
    lru = payload["active_frame_lru"]
    lines = [
        "# Visualization V2 performance and resource evidence",
        "",
        f"Compared with base revision `{payload['base_revision']}` on the local macOS development host.",
        "",
        "## Source and startup impact",
        "",
        "| Measurement | Before | After | Delta |",
        "|---|---:|---:|---:|",
        f"| Synchronous chat UI source | {source['sync_before_bytes']} B | {source['sync_after_bytes']} B | {source['sync_delta_bytes']:+d} B |",
        f"| Median Node parse time for synchronous JS | {source['sync_parse_before_ms']:.4f} ms | {source['sync_parse_after_ms']:.4f} ms | {source['sync_parse_delta_ms']:+.4f} ms |",
        f"| Lazy V2 renderer source | 0 B | {source['lazy_v2_bytes']} B | +{source['lazy_v2_bytes']} B |",
        f"| Existing vendored visualization libraries | {source['vendor_bytes']} B | {source['vendor_bytes']} B | 0 B |",
        "",
        "The V2 renderer is loaded only inside a validated visualization iframe; ordinary text chat does not fetch it. No CDN or new vendor package was added.",
        "",
        "## Real-browser acceptance rendering",
        "",
        f"The full gate rendered {browser['case_count']} cases. Peak measured browser JS heap across the responsive matrix was {matrix['peak_used_js_heap_bytes']} bytes.",
        f"All {browser['gpu_triangle_budget']['three_cases']} Three.js cases stayed within their declared GPU triangle budgets; the largest submitted frame contained {browser['gpu_triangle_budget']['maximum_submitted_triangles']} triangles.",
        "",
        "| Renderer | Cases | Mean first render | p95 | Maximum |",
        "|---|---:|---:|---:|---:|",
    ]
    for renderer, values in browser["by_renderer"].items():
        lines.append(
            f"| {renderer} | {values['count']} | {values['mean_elapsed_ms']:.2f} ms | "
            f"{values['p95_elapsed_ms']:.2f} ms | {values['max_elapsed_ms']:.2f} ms |"
        )
    lines.extend(["", "## Browser screenshots", ""])
    for artifact in payload["browser_screenshots"]:
        lines.append(
            f"- `{artifact['path']}` — {artifact['bytes']} B; SHA-256 `{artifact['sha256']}`"
        )
    lines.extend(
        [
            "",
            "## Hard runtime caps",
            "",
            f"- AST: {payload['caps']['ast_nodes']} nodes, depth {payload['caps']['ast_depth']}.",
            f"- Implicit work: {payload['caps']['implicit_cells']} cells; {payload['caps']['triangles']} triangles.",
            f"- Dense 2D: {payload['caps']['heatmap_cells']} cells; {payload['caps']['particles']} particles; {payload['caps']['points']} declared points.",
            f"- Animation: {payload['caps']['max_fps']} fps, finite duration; active iframe LRU {payload['caps']['active_frames']}.",
            f"- LRU browser proof: {lru['total']} visualizations, {lru['initial_active']} active, {lru['initial_suspended']} suspended; restore kept the cap: {str(lru['restored_with_cap_preserved']).lower()}.",
            "",
            "## Scope note",
            "",
            "Browser JS heap and render timings are measured evidence for this macOS QA run. They are not the competition target's whole-process-tree RSS or thermal result. Target x86 RSS, frame pacing, and thermals must be recorded by the later packaging/target-box task; this task is explicitly prohibited from packaging.",
            "",
            "## Reproduce",
            "",
            "```bash",
            ".venv/bin/python scripts/visualization_v2_performance.py \\",
            "  --browser-results /tmp/muta-v2-browser-results.json \\",
            "  --matrix /tmp/matrix-desktop-light.json /tmp/matrix-desktop-dark.json \\",
            "            /tmp/matrix-mobile-375.json /tmp/matrix-mobile-430-dark.json \\",
            "            /tmp/matrix-landscape.json /tmp/matrix-reduced.json \\",
            "  --lru /tmp/muta-v2-lru.json",
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser-results", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, nargs="+", required=True)
    parser.add_argument("--lru", type=Path, required=True)
    parser.add_argument("--base-revision", default="238b95ff4e0cd38f2636c25d08e6e1c9eb53ded1")
    args = parser.parse_args()

    browser_payload = json.loads(args.browser_results.read_text())
    matrices = [json.loads(path.read_text()) for path in args.matrix]
    lru = json.loads(args.lru.read_text())
    if browser_payload.get("count") != 200 or len(browser_payload.get("cases", [])) != 200:
        raise SystemExit("browser result must contain exactly 200 cases")
    if (
        browser_payload.get("summary", {}).get("passed") != 200
        or any(case.get("rendered") is not True for case in browser_payload["cases"])
    ):
        raise SystemExit("browser result must contain 200 passing real renders")
    if any(
        case.get("gpu_budget_respected") is not True for case in browser_payload["cases"]
    ):
        raise SystemExit("every browser case must prove its GPU triangle budget was respected")
    if any(matrix.get("count") != 5 or not matrix.get("passed") for matrix in matrices):
        raise SystemExit("every responsive matrix must contain five passing scenes")
    if not (
        lru.get("passed") is True
        and lru.get("total") == 6
        and lru.get("initial_active") == 4
        and lru.get("initial_suspended") == 2
        and lru.get("restored_with_cap_preserved") is True
    ):
        raise SystemExit(
            "LRU evidence must prove six total, four active, two suspended, and restore"
        )

    before_sync = b"\n".join(_git_bytes(args.base_revision, path) for path in SYNC_ASSETS)
    after_sync = b"\n".join((ROOT / path).read_bytes() for path in SYNC_ASSETS)
    before_sync_js = b"\n".join(_git_bytes(args.base_revision, path) for path in SYNC_JS_ASSETS)
    after_sync_js = b"\n".join((ROOT / path).read_bytes() for path in SYNC_JS_ASSETS)
    by_renderer: dict[str, dict[str, Any]] = {}
    for renderer in ("svg", "canvas", "three"):
        rows = [
            row
            for row in browser_payload["cases"]
            if row.get("evidence", {}).get("renderer") == renderer
        ]
        elapsed = [float(row["elapsed_ms"]) for row in rows]
        by_renderer[renderer] = {
            "count": len(rows),
            "mean_elapsed_ms": round(statistics.mean(elapsed), 3) if elapsed else 0,
            "p95_elapsed_ms": round(_percentile(elapsed, 0.95), 3),
            "max_elapsed_ms": round(max(elapsed), 3) if elapsed else 0,
        }
    intervals = [
        float(case.get("evidence", {}).get("observed_frame_interval_ms", 0))
        for matrix in matrices
        for case in matrix["cases"]
        if float(case.get("evidence", {}).get("observed_frame_interval_ms", 0)) > 0
    ]
    three_rows = [
        case
        for case in browser_payload["cases"]
        if case.get("evidence", {}).get("renderer") == "three"
    ]
    matrix_summaries = [
        {
            "theme": matrix["theme"],
            "viewport": matrix["viewport"],
            "target_container": matrix["target_container"],
            "reduced_motion": matrix["reduced_motion"],
            "simultaneous_frames": matrix["simultaneous_frames"],
            "used_js_heap_bytes": matrix.get("used_js_heap_bytes"),
            "trusted_browser_input": matrix.get("trusted_browser_input"),
            "page_errors": matrix["page_errors"],
            "passed": matrix["passed"],
        }
        for matrix in matrices
    ]
    payload = {
        "schema_version": 1,
        "base_revision": args.base_revision,
        "measurement_host": "macOS development browser; not target x86",
        "source_impact": {
            "sync_before_bytes": len(before_sync),
            "sync_after_bytes": len(after_sync),
            "sync_delta_bytes": len(after_sync) - len(before_sync),
            "sync_parse_before_ms": _parse_ms(before_sync_js),
            "sync_parse_after_ms": _parse_ms(after_sync_js),
            "sync_parse_delta_ms": 0,
            "lazy_v2_bytes": sum((ROOT / path).stat().st_size for path in LAZY_ASSETS),
            "vendor_bytes": _vendor_bytes(),
            "new_network_dependencies": 0,
        },
        "browser": {
            "case_count": 200,
            "summary": browser_payload.get("summary", {}),
            "by_renderer": by_renderer,
            "maximum_triangles": max(
                (
                    int(row.get("evidence", {}).get("triangles", 0))
                    for row in browser_payload["cases"]
                ),
                default=0,
            ),
            "gpu_triangle_budget": {
                "three_cases": len(three_rows),
                "all_respected": all(
                    case.get("gpu_budget_respected") is True
                    for case in browser_payload["cases"]
                ),
                "maximum_submitted_triangles": max(
                    (
                        int(case.get("evidence", {}).get("gpu_triangles", 0))
                        for case in three_rows
                    ),
                    default=0,
                ),
            },
            "observed_animation_frame_interval_ms": {
                "minimum": round(min(intervals), 3) if intervals else None,
                "median": round(statistics.median(intervals), 3) if intervals else None,
                "maximum": round(max(intervals), 3) if intervals else None,
            },
        },
        "responsive_matrix": {
            "artifact": "docs/qa/visualization-v2-browser-matrix.json",
            "runs": matrix_summaries,
            "peak_used_js_heap_bytes": max(
                int(matrix.get("used_js_heap_bytes", 0)) for matrix in matrices
            ),
            "all_passed": all(matrix["passed"] for matrix in matrices),
        },
        "active_frame_lru": {
            "artifact": "docs/qa/visualization-v2-lru.json",
            **lru,
        },
        "browser_screenshots": _screenshot_artifacts(),
        "caps": {
            "ast_nodes": 160,
            "ast_depth": 24,
            "points": 4096,
            "heatmap_cells": 4096,
            "particles": 800,
            "implicit_cells": 32768,
            "triangles": 32000,
            "max_fps": 30,
            "active_frames": 4,
        },
    }
    payload["source_impact"]["sync_parse_delta_ms"] = round(
        payload["source_impact"]["sync_parse_after_ms"]
        - payload["source_impact"]["sync_parse_before_ms"],
        4,
    )
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    OUTPUT_MD.write_text(_markdown(payload))
    MATRIX_OUTPUT.write_text(
        json.dumps(
            {"schema_version": 1, "count": len(matrices), "runs": matrices},
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    LRU_OUTPUT.write_text(json.dumps(lru, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "cases": 200,
                "matrix_runs": len(matrices),
                "peak_js_heap": payload["responsive_matrix"]["peak_used_js_heap_bytes"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
