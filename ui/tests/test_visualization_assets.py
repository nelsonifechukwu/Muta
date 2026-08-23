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


def test_model_output_is_data_inside_an_opaque_sandbox() -> None:
    parent = (UI / "visualizations.js").read_text()
    frame = (UI / "viz-frame.js").read_text()
    html = (UI / "viz-frame.html").read_text()

    assert 'frame.sandbox = "allow-scripts"' in parent
    assert "allow-same-origin" not in parent
    assert "new Function" not in parent + frame
    assert "eval(" not in parent + frame
    for network_api in ("fetch(", "XMLHttpRequest", "WebSocket", "EventSource"):
        assert network_api not in frame
    assert "innerHTML" not in frame
    assert "visualizations.js" in html and "viz-frame.js" in html
    assert 'viz-theme.js?v=20260823-viz-progress-1' in html
    assert html.index("viz-theme.js") < html.index("viz-frame.css")
    assert 'viz-frame.js?v=20260823-viz-progress-1' in html
    assert "http://" not in html and "https://" not in html
    assert 'frame.loading = "lazy"' in parent
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
