"""Deployment and trust-boundary checks for generated live visualizations."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "ui"


def _contrast(foreground: str, background: str) -> float:
    def luminance(value: str) -> float:
        channels = [int(value[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [
            channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
            for channel in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _blend(foreground: str, background: str, opacity: float) -> str:
    front = [int(foreground[index:index + 2], 16) for index in (1, 3, 5)]
    back = [int(background[index:index + 2], 16) for index in (1, 3, 5)]
    channels = [round(left * opacity + right * (1 - opacity)) for left, right in zip(front, back)]
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def test_chat_loads_visualization_parser_before_the_chat_client() -> None:
    html = (UI / "index.html").read_text()
    assert html.index('src="visualizations.js') < html.index('src="app.js')
    assert "renderCompletedReply(wrap, prose, full)" in (UI / "app.js").read_text()


def test_model_output_is_data_inside_a_network_isolated_trusted_renderer() -> None:
    parent = (UI / "visualizations.js").read_text()
    frame = (UI / "viz-frame.js").read_text()
    frame_v2 = (UI / "viz-frame-v2.js").read_text()
    html = (UI / "viz-frame.html").read_text()
    browser_gate = (UI / "tests" / "visualization-v2-browser-gate.js").read_text()
    browser_gate_html = (UI / "tests" / "visualization-v2-browser-gate.html").read_text()

    # WebKit refuses to render the local Three.js/SVG surface in an opaque-origin iframe. The
    # trusted same-origin frame is still isolated from every network and injection sink below.
    assert 'frame.sandbox = "allow-scripts allow-same-origin"' in parent
    assert "new Function" not in parent + frame + frame_v2
    assert "eval(" not in parent + frame + frame_v2
    for network_api in ("fetch(", "XMLHttpRequest", "WebSocket", "EventSource"):
        assert network_api not in frame + frame_v2
    assert "innerHTML" not in frame + frame_v2
    assert "visualizations.js" in html and "viz-frame.js" in html
    assert 'viz-theme.js?v=20260825-mac-media-2' in html
    assert html.index("viz-theme.js") < html.index("viz-frame.css")
    assert "viz-frame.js?v=20260827-v2-53" in html
    assert 'loadTrustedScript("viz-frame-v2.js?v=20260827-v2-54")' in frame
    assert "forceSinglePass: true" in frame_v2
    assert "gpuBudgetRespected" in browser_gate
    assert "visualization-v2-browser-gate.js?v=20260827-v2-48" in browser_gate_html
    assert "http://" not in html and "https://" not in html
    assert "frame.src = source" in parent
    assert 'frame.loading = "lazy"' not in parent
    assert 'frame.removeAttribute("src")' not in parent
    assert "let intersecting = true" in parent
    assert "muta-viz-visibility" in parent and "muta-viz-visibility" in frame
    assert 'document.addEventListener("muta:themechange", refreshTheme)' in parent
    assert 'viz-frame.html?theme=${safeTheme}#' in parent
    assert "window.MutaViz?.cleanup(messagesEl)" in (UI / "app.js").read_text()
    assert "requestAnimationFrame(tick)" not in frame
    assert "render on demand" in frame
    assert "stopAll();" in frame
    assert "applyState(record.group, record.base);" in frame
    assert "renderDiagram(spec)" in frame
    assert 'role="group"' in html


def test_v2_proposal_strings_have_only_inert_text_sinks() -> None:
    parent = (UI / "visualizations.js").read_text()
    frame = (UI / "viz-frame-v2.js").read_text()
    html = (UI / "viz-frame.html").read_text()
    trusted = parent + frame

    for executable_sink in (
        r"\.innerHTML\s*=",
        r"\.outerHTML\s*=",
        r"\.insertAdjacentHTML\s*\(",
        r"\beval\s*\(",
        r"\bnew\s+Function\b",
        r"\bimport\s*\(",
        r"\bWorker\s*\(",
    ):
        assert re.search(executable_sink, trusted) is None
    for network_sink in ("fetch(", "XMLHttpRequest", "WebSocket", "EventSource"):
        assert network_sink not in frame

    assert "node.textContent = text" in frame
    assert 'html("p", "", spec.text_fallback)' in frame
    assert "title.textContent = spec.title" in parent
    assert "ctx.fillText(" in frame
    assert 'connect-src \'none\'' in html
    assert 'worker-src \'none\'' in html
    assert 'object-src \'none\'' in html
    assert 'base-uri \'none\'' in html
    assert 'spec.family === "semantic_composition"' not in frame


def test_math_surface_is_responsive_accessible_and_lifecycle_bounded() -> None:
    parser = (UI / "visualizations.js").read_text()
    frame = (UI / "viz-frame.js").read_text()
    html = (UI / "viz-frame.html").read_text()
    css = (UI / "viz-frame.css").read_text()

    assert '"surface"' in parser
    assert "evaluateSurfaceExpression" in parser
    assert "new Function" not in parser + frame and "eval(" not in parser + frame
    assert "surfaceObject(object)" in frame
    assert "(x - xCenter) * xScale" in frame
    assert "(z - zCenter) * zScale" in frame
    assert "(y - yCenter) * yScale" in frame
    assert "window.requestAnimationFrame(drawAnimation)" in frame
    assert "window.cancelAnimationFrame(animationFrame)" in frame
    assert "resizeObserver.disconnect()" in frame
    assert "renderer.forceContextLoss?.()" in frame
    assert 'id="viz-surface-play"' in html
    assert 'id="viz-surface-pause"' in html
    assert 'id="viz-surface-restart"' in html
    assert "min-width: 44px" in css and "min-height: 44px" in css
    assert "@media (max-width: 430px)" in css
    assert "@media (pointer: coarse), (max-width: 700px) and (max-height: 650px)" in css
    reduced = re.search(r"@media \(prefers-reduced-motion: reduce\)\s*\{(?P<body>.*?)\}", css, re.DOTALL)
    assert reduced and "#viz-surface-controls" in reduced.group("body")


def test_dark_visualization_geometry_keeps_non_text_contrast() -> None:
    css = (UI / "viz-frame.css").read_text()
    block = re.search(r':root\[data-theme="dark"\]\s*\{(?P<body>.*?)\}', css, re.DOTALL)
    assert block
    tokens = dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", block.group("body")))

    assert _contrast(tokens["viz-border"], tokens["viz-bg"]) >= 3
    grid = _blend(tokens["viz-border"], tokens["viz-bg"], 0.55)
    assert _contrast(grid, tokens["viz-bg"]) >= 3


def test_every_renderer_is_pinned_and_exported_for_offline_use() -> None:
    dockerfile = (ROOT / "docker" / "frontend.Dockerfile").read_text()
    exporter = (ROOT / "scripts" / "export_native_linux.py").read_text()
    runner = (UI / "viz-frame.js").read_text()
    expected = (
        "d3.v7.9.0.min.js",
        "three.r160.min.js",
        "gsap.v3.13.0.min.js",
        "anime.v3.2.2.min.js",
        "motion.v11.11.13.js",
    )
    for asset in expected:
        assert asset in dockerfile
        assert asset in exporter
        assert asset in runner
        assert (UI / "vendor" / "viz" / asset).stat().st_size > 10_000
    assert "@latest" not in dockerfile
    assert "sha256sum -c -" in dockerfile
    notices = (UI / "VISUALIZATION-LICENSES.txt").read_text()
    for package in (
        "D3 7.9.0",
        "Three.js 0.160.1",
        "GSAP 3.13.0",
        "Anime.js 3.2.2",
        "Motion 11.11.13",
    ):
        assert package in notices


def test_csp_allows_only_same_origin_frames_and_scripts() -> None:
    nginx = (ROOT / "docker" / "nginx.conf.template").read_text()
    assert "script-src 'self'" in nginx
    assert "frame-src 'self'" in nginx
    assert "add_header X-Frame-Options $muta_x_frame_options always" in nginx
    assert '/chat/viz-frame.html "SAMEORIGIN"' in nginx
    assert "add_header Content-Security-Policy $muta_content_security_policy always" in nginx
    assert "/chat/viz-frame.html \"default-src 'none'; script-src 'self';" in nginx
    assert "connect-src 'none'" in nginx
    assert "frame-ancestors 'self'" in nginx
    assert 'default "DENY"' in nginx
    assert "'unsafe-eval'" not in nginx
